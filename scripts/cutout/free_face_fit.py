#!/usr/bin/env python3
"""macOS cutout step 5 (optional): measure the cutout's alpha over each face run and write the shot
list's "face": {"free": {...}} values, so the speaker's whole head sits below the caption line,
un-boxed, and never gets clipped or faded. Input: the WebM from scripts/cutout/cutout.sh.

Reads face-cutout.webm (VP9 + alpha) frame by frame for each run, decoded with libvpx-vp9 so the
alpha plane is real. Per run, in recording pixels (1080x1920):
  hair_top_min / p50   highest / median hair row (first row with >= MIN_PX alpha pixels on)
  head_cx_p50          median x centre of the head (alpha centre of mass, 300 rows under the hair top)
  edge_row_min / p50   first row where the cutout touches the recording's left or right edge (the
                       shoulders running off the source frame: a scaled-down cutout shows that cut
                       as a straight line unless it is faded)
Size: each run's scale makes the hair-top-to-shoulder-line distance (edge_row_p50 - hair_top_p50)
land on --ref-px canvas pixels, so the head is the same size in every run even when the speaker sits
closer to the camera in some (or pass --scale for one fixed scale).
Placement: the run's highest hair row lands on canvas y --top-at; the head centre on x 540.
Oval shoulder fade (build.mjs face.free.oval): ellipse centred on the recording's middle (x 0.5),
cy = topY + --oval-dcy, radii --oval-rx/--oval-ry, solid inside --oval-inner. Checked on every
frame of the run:
  head_mask_min    lowest mask value on any head pixel (hair top down 85% of the way to the
                   shoulder line); must be 1.0 = nothing on the head is faded
  cut_edge_max     highest mask value on the cutout's straight cut edges (outer 4 columns, from the
                   shoulder line to the bottom of the frame); must be <= 0.05 = the cut is hidden
  chest_mask_min   mask value at the chest centre 10 rows above the bottom of the frame; must be 1.0

usage: python3 free_face_fit.py <face-cutout.webm> <out.json> (--ref-px 440 | --scale 0.55)
         --top-at 1335 [--oval-dcy 0.40 --oval-rx 0.5 --oval-ry 0.75 --oval-inner 0.7 | --no-oval]
         --run b05:12.0:18.1 --run b10:30.4:33.5 ...
Headroom trim: build.mjs clips the recording's empty area more than HEADROOM px above
topAt (so the layout checker does not read the transparent top of the video as covering scene
text). hair_clearance_px: px between the trim line and the highest hair row (must be > 0).
trim_check.max_visible_value_removed: the most visible pixel the trim removes in any frame, as
alpha x oval mask in 0-255 units; under 0.5 means the trim changes nothing visible.
Read-only on the media; writes only <out.json>. Exit 2 if any check fails. Run under `nice -n 19`.
"""
import argparse
import json
import subprocess
import sys

import numpy as np

W, H = 1080, 1920
FPS = 30
MIN_PX = 6        # a row counts as "hair" once this many alpha pixels are on (ignores lone specks)
ON = 128          # alpha threshold (0-255)
HEADROOM = 40     # build.mjs FREE_HEADROOM: canvas px kept above topAt; the empty area above is trimmed


def runs_arg(s):
    try:
        rid, a, b = s.split(":")
        return rid, float(a), float(b)
    except ValueError:
        raise argparse.ArgumentTypeError(f"--run wants id:start:end, got {s!r}")


def alpha_frames(src, start, end):
    """Yield raw alpha planes (uint8 HxW) for every frame in [start, end)."""
    n = int(round((end - start) * FPS))
    cmd = ["ffmpeg", "-v", "error", "-c:v", "libvpx-vp9", "-ss", f"{start:.4f}", "-i", src,
           "-frames:v", str(n), "-vf", "alphaextract", "-f", "rawvideo", "-pix_fmt", "gray", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    size = W * H
    count = 0
    try:
        while True:
            buf = proc.stdout.read(size)
            if not buf or len(buf) < size:
                break
            count += 1
            yield np.frombuffer(buf, np.uint8).reshape(H, W)
    finally:
        proc.stdout.close()
        err = proc.stderr.read().decode("utf8", "replace").strip()
        rc = proc.wait()
    if rc != 0:
        raise RuntimeError(f"ffmpeg failed ({rc}): {err}")
    if count == 0:
        raise RuntimeError(f"no frames decoded for {start}-{end}")


def landmarks(on):
    rows = on.sum(axis=1)
    hair = np.nonzero(rows >= MIN_PX)[0]
    if hair.size == 0:
        return None
    top = int(hair[0])
    _, xs = np.nonzero(on[top:top + 300])
    cx = float(xs.mean()) if xs.size else W / 2
    edge = np.nonzero(on[:, :3].any(axis=1) | on[:, -3:].any(axis=1))[0]
    edge_row = int(edge[0]) if edge.size else H
    return top, cx, edge_row


def oval_mask(ov):
    """Mask value per recording pixel, as CSS radial-gradient(ellipse rx ry at cx cy, #000 inner, transparent 100%)."""
    yy, xx = np.mgrid[0:H, 0:W]
    r = np.sqrt(((xx / W - ov["cx"]) / ov["rx"]) ** 2 + ((yy / H - ov["cy"]) / ov["ry"]) ** 2)
    return np.clip((1 - r) / (1 - ov["inner"]), 0, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--run", type=runs_arg, action="append", required=True)
    size = ap.add_mutually_exclusive_group(required=True)
    size.add_argument("--ref-px", type=float, help="canvas px for the hair-top-to-shoulder-line distance")
    size.add_argument("--scale", type=float, help="one fixed recording scale for every run")
    ap.add_argument("--top-at", type=float, required=True, help="canvas y for the run's highest hair row")
    ap.add_argument("--no-oval", action="store_true", help="write no oval shoulder fade")
    ap.add_argument("--oval-dcy", type=float, default=0.40, help="oval centre y = topY + this (recording fraction)")
    ap.add_argument("--oval-rx", type=float, default=0.5)
    ap.add_argument("--oval-ry", type=float, default=0.75)
    ap.add_argument("--oval-inner", type=float, default=0.7)
    a = ap.parse_args()
    report = {"src": a.src, "refPx": a.ref_px, "scale": a.scale, "topAt": a.top_at, "minPx": MIN_PX, "alphaOn": ON,
              "oval": None if a.no_oval else {"dcy": a.oval_dcy, "rx": a.oval_rx, "ry": a.oval_ry, "inner": a.oval_inner},
              "runs": {}}
    ok = True
    for rid, s, e in a.run:
        raw = list(alpha_frames(a.src, s, e))
        marks = [lm for lm in (landmarks(al >= ON) for al in raw) if lm is not None]
        if len(marks) != len(raw):
            print(f"[fit] {rid}: {len(raw) - len(marks)} frame(s) with no cutout", file=sys.stderr)
            sys.exit(1)
        tops, cxs, edges = (np.array(v) for v in zip(*marks))
        r = {
            "start": s, "end": e, "frames": len(raw),
            "hair_top_min": int(tops.min()), "hair_top_p50": float(np.median(tops)),
            "head_cx_p50": round(float(np.median(cxs)), 1),
            "edge_row_min": int(edges.min()), "edge_row_p50": float(np.median(edges)),
        }
        ref_src = r["edge_row_p50"] - r["hair_top_p50"]
        sc = round(a.ref_px / ref_src, 3) if a.ref_px else a.scale
        cx = round(r["head_cx_p50"] / W, 4)
        top_y = round(r["hair_top_min"] / H, 4)
        free = {"scale": sc, "centerX": cx, "topY": top_y, "topAt": a.top_at}
        w, h = W * sc, H * sc
        left = 540 - cx * w
        top = a.top_at - top_y * h
        bottom_row = min(H - 1, int((1920 - top) / sc))
        r["canvas"] = {
            "left": round(left, 1), "right": round(left + w, 1), "top": round(top, 1), "bottom": round(top + h, 1),
            "hair_top_p50": round(top + r["hair_top_p50"] * sc, 1),
            "shoulder_line_p50": round(top + r["edge_row_p50"] * sc, 1),
            "recording_row_at_1920": bottom_row,
            "anchored_to_bottom": bool(top + h >= 1919.5),
            # build.mjs trims the recording area above topAt - HEADROOM (see trim check below)
            "trim_line": round(a.top_at - HEADROOM, 1),
            "hair_clearance_px": round(top + r["hair_top_min"] * sc - (a.top_at - HEADROOM), 1),
        }
        run_ok = r["canvas"]["anchored_to_bottom"] and r["canvas"]["hair_clearance_px"] > 0
        if not a.no_oval:
            ov = {"cy": round(top_y + a.oval_dcy, 4), "rx": a.oval_rx, "ry": a.oval_ry, "inner": a.oval_inner}
            free["oval"] = ov
            m = oval_mask({"cx": 0.5, **ov})
            head_min, edge_max, chest_min = 1.0, 0.0, 1.0
            for al, (t, hcx, er) in zip(raw, marks):
                on = al >= ON
                hb = t + int(0.85 * (er - t))
                head_min = min(head_min, float(m[t:hb][on[t:hb]].min()))
                side = np.zeros_like(on)
                side[er:bottom_row, :4] = True
                side[er:bottom_row, -4:] = True
                sv = m[side & on]
                if sv.size:
                    edge_max = max(edge_max, float(sv.max()))
                chest_min = min(chest_min, float(m[bottom_row - 10, int(hcx)]))
            r["oval_check"] = {"head_mask_min": round(head_min, 4), "cut_edge_max": round(edge_max, 4), "chest_mask_min": round(chest_min, 4)}
            run_ok = run_ok and head_min >= 0.999 and edge_max <= 0.05 and chest_min >= 0.999
        # trim check: the most visible pixel the trim removes, over every frame = max(alpha x oval
        # mask) above the trim line, in 0-255 units. Under 0.5 means the trim changes nothing visible.
        trim_row = max(0, min(H, int(np.ceil((a.top_at - HEADROOM - top) / sc))))
        mt = (m[:trim_row] if not a.no_oval else np.ones((trim_row, W)))
        trimmed_max = max((float((al[:trim_row].astype(np.float32) * mt).max()) if trim_row else 0.0) for al in raw)
        r["trim_check"] = {"recording_rows_trimmed": trim_row, "max_visible_value_removed": round(trimmed_max, 3)}
        run_ok = run_ok and trimmed_max < 0.5
        r["free"] = free
        r["ok"] = bool(run_ok)
        ok = ok and run_ok
        report["runs"][rid] = r
        print(f"[fit] {rid}: {json.dumps(r)}")
    report["ok"] = bool(ok)
    with open(a.out, "w") as fh:
        json.dump(report, fh, indent=2)
        fh.write("\n")
    print(f"[fit] ok={ok}; wrote {a.out}")
    sys.exit(0 if ok else 2)


if __name__ == "__main__":
    main()
