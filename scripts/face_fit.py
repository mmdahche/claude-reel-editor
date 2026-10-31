#!/usr/bin/env python3
"""face_fit.py - one fixed framing per take that puts the speaker's eyes on the eye line.

Raw-take recipe (WORKFLOW.md, "Raw take to clean take"):
  transcribe -> retake_ranges -> ffmpeg re-encode -> auto-editor silence pass -> speed
  -> clean voice -> re-transcribe -> script_snap -> face_fit -> build

What it does
  Samples frames from the clean take (every --interval seconds, at most --max-samples),
  finds the face and both pupils on each with Apple's Vision framework (offline, built into
  macOS) and takes the MEDIAN eye point and face size. Then it works out one scale + offset
  for the whole take, per face mode, so the eyes land on the eye line in the 1080x1920 frame:
    mode A  (stage split, face box x 40-1040, y 1400-1880)   eyes on y 1560 (--eye-line-a)
    mode A2 (proof split, face full-bleed y 1280-1920)       eyes on y 1520 (--eye-line-a2)
  One static fit, not per-frame tracking: same chair, same camera, and tracking reads as a
  wobbling digital gimbal.

  The face boxes are read from build.mjs (FACE_BOX), so this stays in step with the build.
  At zoom 1 the recording fills the box edge to edge, so the eyes can be put on the line but
  not moved sideways; --center zooms in just enough to centre them (never past the recording's
  own resolution unless --allow-upscale).

Output (face-fit.json, default next to the video)
  "eyes"      median eye point in recording pixels and as a fraction of the frame, plus spread
  "modes"     per mode: scale, the placed rectangle, where the eyes land, chin check, an ffmpeg
              crop for the box, and "face": {eyeX, eyeY, zoom} in the shot-list format
  "shotlist"  the values the build reads today: "recording": {eyeX, eyeY} for the shot list's
              recording block, and "A" / "A2" face objects for beats in those modes.
              build.mjs aims its own eye point (A y 1575 at the time of writing), so the "face"
              values are worked out to land the measured eyes on THIS script's eye line.
  With --shotlist IN --write-shotlist OUT it writes a copy of the shot list with those values
  filled in (beats that already have a "face" keep it unless --overwrite-faces). The face box a
  beat uses follows build.mjs: an A beat with proof footage on a split layout uses the A2 box.

Usage
  python3 face_fit.py work/clean.mp4                                  # writes work/face-fit.json
  python3 face_fit.py work/clean.mp4 --out motion/face-fit.json --preview work/face-fit-check.jpg
  python3 face_fit.py input/<slug>/face.mp4 --shotlist input/<slug>/shotlist.json \\
      --write-shotlist input/<slug>/shotlist.json          # same path: original kept as *.pre-face-fit.json

Needs macOS with swiftc (Xcode Command Line Tools) for the Vision helper face_landmarks.swift,
which is compiled once into scripts/.bin/ (about 30 s, rebuilt when the .swift file changes),
and ffmpeg + ffprobe on PATH. No OpenCV, no pip packages.
macOS only. Tested on upscaled 720p phone footage cut from several framings; thresholds are first
guesses, so look at the --preview image every time.
"""

import argparse
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
HELPER_SRC = os.path.join(HERE, "face_landmarks.swift")
BIN_DIR = os.path.join(HERE, ".bin")
HELPER_BIN = os.path.join(BIN_DIR, "face_landmarks")
BUILD_MJS = os.path.join(HERE, "build.mjs")
CANVAS_W, CANVAS_H = 1080, 1920
# Used only when build.mjs cannot be read; the live values come from its FACE_BOX block.
FALLBACK_BOXES = {
    "A": {"x": 40, "y": 1400, "w": 1000, "h": 480, "ex": 540, "ey": 1575},
    "A2": {"x": 0, "y": 1280, "w": 1080, "h": 640, "ex": 540, "ey": 1520},
}


class UserError(Exception):
    """A problem the user can fix; printed as a plain sentence, no traceback."""


def fail(msg):
    raise UserError(msg)


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


# ----------------------------------------------------------------------------- inputs
def probe(video):
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            fail(f"{tool} was not found on PATH. Install ffmpeg (brew install ffmpeg).")
    if not os.path.isfile(video):
        fail(f"Video not found: {video}")
    r = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=width,height:stream_tags=rotate:stream_side_data=rotation:format=duration", "-of", "json", video])
    if r.returncode != 0:
        fail(f"ffprobe could not read {video}: {r.stderr.strip()[:300]}")
    info = json.loads(r.stdout or "{}")
    st = (info.get("streams") or [{}])[0]
    if not st.get("width"):
        fail(f"{video} has no video stream.")
    rot = 0
    for sd in st.get("side_data_list") or []:
        if "rotation" in sd:
            rot = int(float(sd["rotation"]))
    rot = rot or int(float((st.get("tags") or {}).get("rotate", 0)))
    w, h = int(st["width"]), int(st["height"])
    if abs(rot) % 180 == 90:
        w, h = h, w
    return {"w": w, "h": h, "rotation": rot, "duration": float((info.get("format") or {}).get("duration") or 0)}


def face_boxes():
    """FACE_BOX from build.mjs (A, A2), or the fallback with a note."""
    try:
        with open(BUILD_MJS, encoding="utf-8") as f:
            src = f.read()
        block = re.search(r"const FACE_BOX = \{(.*?)\n\};", src, re.S).group(1)
        boxes = {}
        for name in ("A", "A2"):
            m = re.search(rf"\b{name}:\s*\{{([^}}]*)\}}", block)
            vals = dict(re.findall(r"(\w+):\s*(-?[\d.]+)", m.group(1)))
            boxes[name] = {k: float(vals[k]) for k in ("x", "y", "w", "h", "ex", "ey")}
        return boxes, "build.mjs"
    except (OSError, AttributeError, KeyError):
        return FALLBACK_BOXES, "fallback (could not read FACE_BOX from build.mjs; check it by hand)"


# ----------------------------------------------------------------------------- Vision helper
def ensure_helper():
    if sys.platform != "darwin":
        fail("face_fit.py needs macOS: it uses Apple's Vision framework to find the eyes.")
    if not os.path.isfile(HELPER_SRC):
        fail(f"The Vision helper source is missing: {HELPER_SRC}")
    if os.path.isfile(HELPER_BIN) and os.path.getmtime(HELPER_BIN) >= os.path.getmtime(HELPER_SRC):
        return HELPER_BIN
    if not shutil.which("swiftc"):
        fail("swiftc was not found. Install the Xcode Command Line Tools (xcode-select --install) and run again.")
    cache, tmp = os.path.join(BIN_DIR, "module-cache"), os.path.join(BIN_DIR, "tmp")
    os.makedirs(cache, exist_ok=True)
    os.makedirs(tmp, exist_ok=True)
    print("Building the Vision face finder (first run only, about 30 s) ...", file=sys.stderr)
    env = dict(os.environ, TMPDIR=tmp + os.sep, CLANG_MODULE_CACHE_PATH=cache)
    r = run(["swiftc", "-O", HELPER_SRC, "-o", HELPER_BIN, "-module-cache-path", cache], env=env)
    if r.returncode != 0:
        fail("Could not build the Vision helper with swiftc:\n" + "\n".join(r.stderr.strip().splitlines()[-8:]))
    return HELPER_BIN


def sample_times(duration, start, end, interval, max_samples):
    end = min(end or duration, duration) if duration else (end or 0)
    if end <= start:
        fail(f"Nothing to sample: start {start:.2f} s is not before end {end:.2f} s.")
    span = end - start
    n = int(span / interval) + 1
    if n > max_samples:
        interval = span / max_samples
        n = max_samples
    # stay a frame away from the very end, where seeking can come back empty
    return [round(min(start + 0.25 * interval + k * interval, end - 0.05), 3) for k in range(n)], interval


def grab_frames(video, times, work, src_h):
    paths = []
    scale = ["-vf", "scale=-2:1920"] if src_h > 1920 else []
    for k, t in enumerate(times):
        p = os.path.join(work, f"f{k:04d}.jpg")
        r = run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", video, "-frames:v", "1", *scale, "-q:v", "2", p])
        if r.returncode == 0 and os.path.isfile(p):
            paths.append((t, p))
    if not paths:
        fail(f"ffmpeg could not pull any frames from {video}.")
    return paths


def detect(helper, frames, rec):
    r = run([helper] + [p for _, p in frames])
    if r.returncode != 0 and not r.stdout:
        fail("The Vision helper failed:\n" + "\n".join(r.stderr.strip().splitlines()[-6:]))
    by_file = {}
    for line in r.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            obj = json.loads(line)
            by_file[obj.get("file")] = obj
    out = []
    for t, p in frames:
        obj = by_file.get(p) or {}
        faces = obj.get("faces") or []
        k = rec["h"] / float(obj.get("h") or rec["h"])  # frame px -> recording px
        rec_one = {"t": t, "file": p, "faces": len(faces)}
        if faces:
            f = max(faces, key=lambda f: f["bbox"][2] * f["bbox"][3])
            lp, rp = f.get("leftPupil"), f.get("rightPupil")
            if not (lp and rp):
                lp, rp = f.get("leftEye"), f.get("rightEye")
            if lp and rp:
                bx, by, bw, bh = f["bbox"]
                rec_one.update(
                    eye_x=(lp[0] + rp[0]) / 2 * k, eye_y=(lp[1] + rp[1]) / 2 * k,
                    eye_dist=((lp[0] - rp[0]) ** 2 + (lp[1] - rp[1]) ** 2) ** 0.5 * k,
                    face_w=bw * k, face_top=by * k, face_bottom=(by + bh) * k, roll=f.get("roll", 0.0),
                )
        out.append(rec_one)
    return out


# ----------------------------------------------------------------------------- geometry
def fit_mode(box, target_y, eyes, face, rec, zoom, center, allow_upscale):
    """One scale + offset that puts the median eye point on (box.ex, target_y)."""
    ex, ey = eyes["x"], eyes["y"]
    cover = max(box["w"] / rec["w"], box["h"] / rec["h"])
    notes = []
    if center:
        need = [cover]
        if ex > 0:
            need.append((box["ex"] - box["x"]) / ex)
        if rec["w"] - ex > 0:
            need.append((box["x"] + box["w"] - box["ex"]) / (rec["w"] - ex))
        zoom = max(zoom, max(need) / cover)
    s = cover * zoom
    if s > 1.0 + 1e-6 and not allow_upscale and zoom > 1.0:
        capped = max(cover, 1.0)
        notes.append(f"zoom {zoom:.2f} would enlarge the recording past its own pixels; capped at {capped / cover:.2f} "
                     "(use --allow-upscale to go further, or record at 4K)")
        zoom, s = capped / cover, capped
    w, h = rec["w"] * s, rec["h"] * s
    left = min(box["x"], max(box["x"] + box["w"] - w, box["ex"] - ex * s))
    top = min(box["y"], max(box["y"] + box["h"] - h, target_y - ey * s))
    at_x, at_y = left + ex * s, top + ey * s
    if abs(at_y - target_y) > 1:
        notes.append(f"eyes land on y {at_y:.0f}, not {target_y:.0f}: the recording runs out at the "
                     f"{'top' if top >= box['y'] - 1e-6 else 'bottom'} of the box (zoom in or reframe)")
    if abs(at_x - box["ex"]) > 1:
        fix = ("--allow-upscale lets it zoom further, or record at 4K" if center
               else "use --center to zoom in until it can")
        notes.append(f"eyes land on x {at_x:.0f}, not the centre {box['ex']:.0f}: at this zoom the recording "
                     f"fills the box edge to edge, so it cannot move sideways ({fix})")
    chin_y = top + face["bottom"] * s
    if chin_y > box["y"] + box["h"]:
        notes.append(f"the chin (face bottom y {chin_y:.0f}) falls below the box bottom ({box['y'] + box['h']:.0f})")
    if s > 1.0 + 1e-6:
        notes.append(f"the recording is enlarged {s:.2f}x here (softer than native)")
    crop_x, crop_y = round(box["x"] - left), round(box["y"] - top)
    sw, sh = round(w / 2) * 2, round(h / 2) * 2
    face_val = {"eyeX": round((box["ex"] - left) / w, 5), "eyeY": round((box["ey"] - top) / h, 5), "zoom": round(zoom, 4)}
    return {
        "box": {k: box[k] for k in ("x", "y", "w", "h")},
        "target": {"x": box["ex"], "y": target_y},
        "build_eye_point": {"x": box["ex"], "y": box["ey"]},
        "zoom": round(zoom, 4),
        "scale": round(s, 5),
        "rect": {"left": round(left, 2), "top": round(top, 2), "width": round(w, 2), "height": round(h, 2)},
        "eyes_at": {"x": round(at_x, 1), "y": round(at_y, 1)},
        "on_eye_line": abs(at_y - target_y) <= 1,
        "upscaled": s > 1.0 + 1e-6,
        "chin_y": round(chin_y, 1),
        "chin_inside_box": chin_y <= box["y"] + box["h"],
        "ffmpeg_box_filter": f"scale={sw}:{sh}:flags=lanczos,crop={int(box['w'])}:{int(box['h'])}:{crop_x}:{crop_y}",
        "face": face_val,
        "notes": notes,
    }


def effective_mode(beat, proof_split):
    """The face box build.mjs gives a beat (keep in step with its layout rule)."""
    mode, layout = beat.get("mode"), beat.get("layout")
    split = layout == "split" or (layout != "card" and proof_split)
    if mode == "A2" and not split:
        return "A"
    if mode == "A" and beat.get("proof") and split:
        return "A2"
    return mode


def write_preview(video, t_frame, fits, out, eye_px):
    """A and A2 side by side on a dark grey canvas: the eye line in cyan, the box outline,
    and a red mark where this frame's eyes land."""
    parts, labels = [], []
    for k, (name, fit) in enumerate(fits.items()):
        b, r = fit["box"], fit["rect"]
        sw, sh = round(r["width"] / 2) * 2, round(r["height"] / 2) * 2
        cx, cy = round(b["x"] - r["left"]), round(b["y"] - r["top"])
        ex = r["left"] + eye_px[0] * fit["scale"]
        ey = r["top"] + eye_px[1] * fit["scale"]
        ty = fit["target"]["y"]
        parts.append(
            f"[{k}:v]scale={sw}:{sh}:flags=lanczos,crop={int(b['w'])}:{int(b['h'])}:{cx}:{cy},"
            f"pad={CANVAS_W}:{CANVAS_H}:{int(b['x'])}:{int(b['y'])}:color=0x202020,"
            f"drawbox=x={int(b['x'])}:y={int(b['y'])}:w={int(b['w'])}:h={int(b['h'])}:color=white@0.5:t=2,"
            f"drawbox=x=0:y={int(ty) - 2}:w={CANVAS_W}:h=4:color=0x00c8ff@0.95:t=fill,"
            f"drawbox=x={int(ex) - 9}:y={int(ey) - 9}:w=18:h=18:color=red@0.95:t=fill[p{k}]"
        )
        labels.append(f"[p{k}]")
    graph = ";".join(parts) + ";" + "".join(labels) + f"hstack=inputs={len(labels)},scale={CANVAS_W}:-2"
    cmd = ["ffmpeg", "-v", "error", "-y"]
    for _ in fits:
        cmd += ["-ss", f"{t_frame:.3f}", "-i", video]
    cmd += ["-filter_complex", graph, "-frames:v", "1", "-q:v", "3", out]
    r = run(cmd)
    if r.returncode != 0:
        print("Note: could not draw the preview: " + r.stderr.strip()[-300:], file=sys.stderr)
        return False
    return True


# ----------------------------------------------------------------------------- main
def main(argv=None):
    p = argparse.ArgumentParser(
        prog="face_fit.py",
        description="Find the eyes on sampled frames (Apple Vision) and write one fixed framing per face mode "
        "that puts them on the eye line (A y 1560, A2 y 1520). See the docstring for details.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("video", help="the clean take (work/clean.mp4 or input/<slug>/face.mp4)")
    p.add_argument("--out", help="face-fit JSON to write (default: face-fit.json next to the video)")
    p.add_argument("--eye-line-a", type=float, default=1560, help="eye line for mode A, y in the 1080x1920 frame")
    p.add_argument("--eye-line-a2", type=float, default=1520, help="eye line for mode A2")
    p.add_argument("--zoom-a", type=float, default=1.0, help="zoom for mode A (1 = recording just fills the box)")
    p.add_argument("--zoom-a2", type=float, default=1.0, help="zoom for mode A2")
    p.add_argument("--center", action="store_true", help="zoom in just enough to centre the eyes left-right too")
    p.add_argument("--allow-upscale", action="store_true", help="let --center enlarge past the recording's own pixels")
    p.add_argument("--interval", type=float, default=0.5, help="seconds between sampled frames")
    p.add_argument("--max-samples", type=int, default=40, help="most frames to sample (the interval widens to fit)")
    p.add_argument("--start", type=float, default=0.0, help="sample from this time (s)")
    p.add_argument("--end", type=float, default=0.0, help="sample up to this time (s; 0 = end of video)")
    p.add_argument("--preview", help="also write a check image (A and A2 side by side, eye line drawn)")
    p.add_argument("--shotlist", help="shot list to fill in (with --write-shotlist)")
    p.add_argument("--write-shotlist", help="write a copy of --shotlist with recording eyes + A/A2 beat faces filled in")
    p.add_argument("--overwrite-faces", action="store_true", help="replace beats' existing \"face\" values too")
    p.add_argument("--proof-split", choices=["on", "off"], default="on",
                   help="the --proof-split token of the client's brand.json; decides A vs A2 boxes")
    p.add_argument("--keep-frames", action="store_true", help="keep the sampled frames (next to the output)")
    args = p.parse_args(argv)
    if bool(args.shotlist) != bool(args.write_shotlist):
        fail("Use --shotlist and --write-shotlist together (read one shot list, write the filled-in copy).")
    if args.interval <= 0 or args.max_samples < 1:
        fail("--interval must be above 0 and --max-samples at least 1.")

    video = os.path.abspath(args.video)
    rec = probe(video)
    out = os.path.abspath(args.out or os.path.join(os.path.dirname(video), "face-fit.json"))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    helper = ensure_helper()
    boxes, box_src = face_boxes()
    times, interval = sample_times(rec["duration"], args.start, args.end, args.interval, args.max_samples)

    work = tempfile.mkdtemp(prefix=".face_fit-", dir=os.path.dirname(out))
    try:
        frames = grab_frames(video, times, work, rec["h"])
        det = detect(helper, frames, rec)
    finally:
        if args.keep_frames:
            print(f"Sampled frames kept in {work}")
        else:
            shutil.rmtree(work, ignore_errors=True)

    good = [d for d in det if "eye_x" in d]
    print(f"Video: {rec['w']}x{rec['h']}, {rec['duration']:.2f} s. Sampled {len(det)} frames every {interval:.2f} s; "
          f"eyes found on {len(good)}.")
    if not good:
        fail("No face with both eyes was found on any sampled frame. Check the take is the face recording, well lit, "
             "with the face toward the camera.")
    notes = []
    if len(good) < 0.6 * len(det):
        notes.append(f"eyes found on only {len(good)} of {len(det)} frames; the fit may be off")
    multi = sum(1 for d in det if d["faces"] > 1)
    if multi:
        notes.append(f"{multi} frame(s) show more than one face; the biggest face was used")
    if rec["rotation"]:
        notes.append(f"the recording carries a {rec['rotation']} degree rotation flag; build.mjs reads the stored size, "
                     "so re-encode it upright before the build")

    med = lambda key: statistics.median(d[key] for d in good)  # noqa: E731
    mad = lambda key: statistics.median(abs(d[key] - med(key)) for d in good)  # noqa: E731
    eyes = {"x": med("eye_x"), "y": med("eye_y")}
    face = {"width": med("face_w"), "bottom": med("face_bottom"), "top": med("face_top"), "eye_distance": med("eye_dist")}
    spread = {"x": mad("eye_x"), "y": mad("eye_y")}
    if max(spread.values()) > 0.03 * rec["h"]:
        notes.append(f"the eyes move a lot during this take (typical drift {spread['x']:.0f} px across, {spread['y']:.0f} px "
                     "down); one fixed framing will not suit every part, so check the preview and set per-beat \"face\" "
                     "values where it is off")

    fits = {
        "A": fit_mode(boxes["A"], args.eye_line_a, eyes, face, rec, args.zoom_a, args.center, args.allow_upscale),
        "A2": fit_mode(boxes["A2"], args.eye_line_a2, eyes, face, rec, args.zoom_a2, args.center, args.allow_upscale),
    }
    doc = {
        "tool": "face_fit.py",
        "created": datetime.now().astimezone().isoformat(timespec="seconds"),
        "video": video,
        "recording": {"w": rec["w"], "h": rec["h"], "duration": round(rec["duration"], 3), "rotation": rec["rotation"]},
        "samples": {"frames": len(det), "with_eyes": len(good), "interval": round(interval, 3),
                    "times": [d["t"] for d in det]},
        "eyes": {"x": round(eyes["x"], 1), "y": round(eyes["y"], 1),
                 "eyeX": round(eyes["x"] / rec["w"], 5), "eyeY": round(eyes["y"] / rec["h"], 5),
                 "spread_px": {k: round(v, 1) for k, v in spread.items()},
                 "range_px": {"x": [round(min(d["eye_x"] for d in good), 1), round(max(d["eye_x"] for d in good), 1)],
                              "y": [round(min(d["eye_y"] for d in good), 1), round(max(d["eye_y"] for d in good), 1)]}},
        "face": {k: round(v, 1) for k, v in face.items()},
        "face_boxes_from": box_src,
        "modes": fits,
        "shotlist": {
            "recording": {"eyeX": round(eyes["x"] / rec["w"], 5), "eyeY": round(eyes["y"] / rec["h"], 5)},
            "A": fits["A"]["face"],
            "A2": fits["A2"]["face"],
            "how": "Put 'recording' into the shot list's recording block and the A / A2 object as \"face\" on beats "
                   "that use that face box (or run with --shotlist/--write-shotlist).",
        },
        "notes": notes + [f"{m}: {n}" for m, f in fits.items() for n in f["notes"]],
    }
    with open(out, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2)
        f.write("\n")

    print(f"Median eyes at x {eyes['x']:.0f}, y {eyes['y']:.0f} in the recording "
          f"({eyes['x'] / rec['w']:.3f}, {eyes['y'] / rec['h']:.3f} of the frame); typical drift "
          f"{spread['x']:.0f} px across, {spread['y']:.0f} px down. Face about {face['width']:.0f} px wide.")
    for m, fit in fits.items():
        print(f"Mode {m}: zoom {fit['zoom']:.2f} (scale {fit['scale']:.3f}); eyes land on x {fit['eyes_at']['x']:.0f}, "
              f"y {fit['eyes_at']['y']:.0f} (eye line {fit['target']['y']:.0f}); chin "
              f"{'inside' if fit['chin_inside_box'] else 'OUTSIDE'} the box. Shot-list face: {json.dumps(fit['face'])}")
    for n in doc["notes"]:
        print(f"Note: {n}")
    print(f"Face boxes read from {box_src}. Wrote {out}")

    if args.preview:
        best = min(good, key=lambda d: (d["eye_x"] - eyes["x"]) ** 2 + (d["eye_y"] - eyes["y"]) ** 2)
        if write_preview(video, best["t"], fits, os.path.abspath(args.preview), (best["eye_x"], best["eye_y"])):
            print(f"Preview (frame at {best['t']:.2f} s, the one closest to the median): {os.path.abspath(args.preview)}")

    if args.write_shotlist:
        try:
            with open(args.shotlist, encoding="utf-8") as f:
                sl = json.load(f)
        except FileNotFoundError:
            fail(f"Shot list not found: {args.shotlist}")
        except json.JSONDecodeError as e:
            fail(f"The shot list is not valid JSON ({args.shotlist}, line {e.lineno}): {e.msg}")
        sl.setdefault("recording", {})
        sl["recording"]["eyeX"] = doc["shotlist"]["recording"]["eyeX"]
        sl["recording"]["eyeY"] = doc["shotlist"]["recording"]["eyeY"]
        filled, kept = [], []
        for b in sl.get("beats", []):
            eff = effective_mode(b, args.proof_split == "on")
            if eff not in ("A", "A2"):
                continue
            if "face" in b and not args.overwrite_faces:
                kept.append(b.get("id"))
                continue
            b["face"] = dict(fits[eff]["face"])
            filled.append(f"{b.get('id')} ({eff})")
        dst = os.path.abspath(args.write_shotlist)
        if os.path.exists(dst) and os.path.samefile(dst, os.path.abspath(args.shotlist)):
            keep = re.sub(r"\.json$", "", dst) + ".pre-face-fit.json"
            if not os.path.exists(keep):
                shutil.copy2(dst, keep)
                print(f"Kept the original shot list as {keep}")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "w", encoding="utf-8") as f:
            json.dump(sl, f, indent=2)
            f.write("\n")
        print(f"Shot list written to {dst}: recording eyes set; face filled on {', '.join(filled) or 'no beats'}"
              + (f"; kept the existing face on {', '.join(kept)} (use --overwrite-faces to replace)" if kept else "") + ".")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)  # keep progress and error lines in order when piped
    try:
        sys.exit(main())
    except UserError as e:
        print(f"face_fit: {e}", file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        sys.exit(130)
