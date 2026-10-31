#!/usr/bin/env python3
"""retake_ranges.py - keep the LAST take of every SCRIPT.md line in a raw talking-head take.

Raw-take recipe (WORKFLOW.md, "Raw take to clean take"):
  transcribe -> retake_ranges -> ffmpeg re-encode -> auto-editor silence pass -> speed
  -> clean voice -> re-transcribe -> script_snap -> face_fit -> build

What it does
  Reads the word-level transcript of the RAW take (the `hyperframes transcribe` JSON:
  [{"id", "text", "start", "end"}], seconds) and the video's SCRIPT.md (one line per
  sentence). For every script line it finds each time the line was said, keeps the LAST
  complete take and drops the rest: earlier takes, false starts ("Okay, so the read-only...
  Okay, so the read-only build is ready..."), restarts inside a line ("the permission rule
  you, the permission rule you approved") and off-script chatter between takes. Kept words
  get a margin (default 0.12 s before, 0.25 s after) that never reaches into a dropped word.

  Matching is fuzzy (word-level local alignment), so a few misheard words, fillers or a
  skipped word still count as a take. A take is "complete" when it starts at the top of the
  line, reaches its last words and covers at least --min-coverage of the line's words.
  Lines play in script order. If the last take of a line was recorded after a later line,
  the cut moves it into script order and says so.

Outputs (written next to --out; nothing is written with --dry-run)
  keep-ranges.json         ranges to keep, in play order, in the VIDEO's time (seconds),
                           plus the decision for every line and every dropped span
  keep-ranges.filter.txt   ffmpeg filter graph: one trim/atrim pair per range, then concat
  keep-ranges.sh           the ffmpeg command that reads it and RE-ENCODES (libx264 crf 14,
                           30 fps CFR, AAC 48 kHz). Never stream-copy: copy cuts snap to
                           keyframes and drift.

Usage
  python3 retake_ranges.py --transcript work/raw-transcript.json --script SCRIPT.md --dry-run
  python3 retake_ranges.py --transcript work/raw-transcript.json --script SCRIPT.md \\
      --video recording/selects.mp4 --out work/keep-ranges.json
  sh work/keep-ranges.sh                 # or add --render to run ffmpeg straight away

SCRIPT.md format
  One spoken line per sentence. Blank lines, '#' headings, '>' quotes, '|' tables, HTML
  comments, code fences and YAML front matter are ignored. List markers ('- ', '1. ') and
  *emphasis* are stripped. Anything in [square brackets] is a stage direction and ignored.

Time base
  `hyperframes transcribe` pulls the audio out with ffmpeg, so word times count from the
  first AUDIO sample. Phone recordings often start the audio a little after the picture
  (about 0.2 s is common). With --video the offset is probed and added
  (--audio-offset auto, the default); pass a number to override it.

Accuracy
  Cut points sit on the transcript's word times plus the margins, so the cut is only as exact
  as those times. On a spliced test take, true word times gave 96 of
  96 words right, mid-line restart included. Whisper small.en times (up to 0.6 s late, and it
  dropped the repeated phrase entirely) gave 86 of 96. Transcribe the raw take with the most
  accurate engine available, then re-transcribe the cut and run script_snap.py, whose
  "differences from the script" list shows anything clipped or left in.

Needs Python 3.9+, and ffmpeg + ffprobe on PATH for --video / --render. Standard library only.
Needs script_text.py from the same folder.
Tested on a spliced "raw take" with false starts and repeated lines; thresholds are first guesses,
so always read the --dry-run decisions before cutting.
"""

import argparse
import json
import math
import os
import shlex
import shutil
import subprocess
import sys
from datetime import datetime
from difflib import SequenceMatcher

from script_text import UserError, fail, norm_tokens, read_script_lines, read_transcript_json

GAP = 1  # alignment penalty for a skipped word on either side


# ----------------------------------------------------------------------------- inputs
def load_transcript(path):
    """-> [{"text", "start", "end"}] in time order."""
    _, words = read_transcript_json(path)
    out = []
    for w in words:
        s, e = float(w["start"]), float(w["end"])
        out.append({"text": str(w.get("text", w.get("word"))), "start": s, "end": max(s, e)})
    order = sorted(range(len(out)), key=lambda k: out[k]["start"])
    if order != list(range(len(out))):
        print("Note: transcript words were not in time order; sorted them by start time.", file=sys.stderr)
        out = [out[k] for k in order]
    return out


# ----------------------------------------------------------------------------- matching
_score_cache = {}


def pair_score(a, b):
    """+2 same word, +1 close spelling (misheard), -1 different word."""
    if a == b:
        return 2
    key = (a, b)
    v = _score_cache.get(key)
    if v is None:
        v = 1 if (len(a) >= 3 and len(b) >= 3 and SequenceMatcher(None, a, b).ratio() >= 0.75) else -1
        _score_cache[key] = v
    return v


def local_align(L, T, blocked):
    """Best local alignment (Smith-Waterman) of script tokens L inside transcript tokens T.
    Blocked transcript tokens cannot take part. Ties go to the later spot in the transcript.
    Returns (score, pairs) with pairs = [(script_idx, transcript_idx, pair_score)]."""
    n, m = len(L), len(T)
    H = [[0] * (m + 1) for _ in range(n + 1)]
    best, bi, bj = 0, 0, 0
    for i in range(1, n + 1):
        li, Hi, Hp = L[i - 1], H[i], H[i - 1]
        for j in range(1, m + 1):
            if blocked[j - 1]:
                continue
            v = Hp[j - 1] + pair_score(li, T[j - 1])
            u = Hp[j] - GAP
            if u > v:
                v = u
            u = Hi[j - 1] - GAP
            if u > v:
                v = u
            if v <= 0:
                continue
            Hi[j] = v
            if v > best or (v == best and j >= bj):
                best, bi, bj = v, i, j
    pairs = []
    i, j = bi, bj
    while i > 0 and j > 0 and H[i][j] > 0:
        s = pair_score(L[i - 1], T[j - 1])
        if not blocked[j - 1] and H[i][j] == H[i - 1][j - 1] + s:  # prefer matching (keeps the later repeat)
            pairs.append((i - 1, j - 1, s))
            i, j = i - 1, j - 1
        elif H[i][j] == H[i][j - 1] - GAP:
            j -= 1
        elif H[i][j] == H[i - 1][j] - GAP:
            i -= 1
        else:
            break
    pairs.reverse()
    while pairs and pairs[0][2] <= 0:
        pairs.pop(0)
    return best, pairs


def find_candidates(L, T, max_takes=60):
    """Every place the line was (partly) said, best first."""
    n, m = len(L), len(T)
    min_score = min(3, 2 * n)
    blocked = [False] * m
    found = []
    for _ in range(max_takes):
        score, pairs = local_align(L, T, blocked)
        if score < min_score or not pairs:
            break
        t0, t1 = pairs[0][1], pairs[-1][1]
        found.append({"score": score, "pairs": pairs, "t0": t0, "t1": t1})
        for k in range(t0, t1 + 1):
            blocked[k] = True
    return found


def classify(c, n, min_cov):
    matched = sorted({p[0] for p in c["pairs"] if p[2] > 0})
    cov = len(matched) / n
    slack = 1 if n >= 5 else 0
    starts = matched[0] <= slack
    ends = matched[-1] >= n - 1 - slack
    if cov >= min_cov and starts and ends:
        kind = "complete"
    elif starts:
        kind = "false start"
    else:
        kind = "fragment"
    c.update(coverage=round(cov, 3), kind=kind)


def restart_runs(c, T, min_restart, cut_adlibs):
    """Transcript-token runs inside a take that should be cut: a restart (the words are said
    again straight after) or, with --cut-adlibs N, any off-script run of N+ words."""
    aligned = {p[1] for p in c["pairs"]}
    runs, cur = [], []
    for j in range(c["t0"], c["t1"] + 1):
        if j in aligned:
            if cur:
                runs.append(cur)
            cur = []
        else:
            cur.append(j)
    cuts = []
    for run in runs:
        r = len(run)
        after = run[-1] + 1
        same = sum(1 for k in range(r) if after + k < len(T) and pair_score(T[run[k]], T[after + k]) > 0)
        if r >= min_restart and same >= max(1, math.ceil(0.6 * r)):
            cuts.append({"tokens": run, "why": "restart"})
        elif cut_adlibs and r >= cut_adlibs:
            cuts.append({"tokens": run, "why": "off-script words inside the line"})
    return cuts


# ----------------------------------------------------------------------------- media
def probe(video):
    if not shutil.which("ffprobe"):
        fail("ffprobe was not found on PATH. Install ffmpeg (brew install ffmpeg) or drop --video.")
    if not os.path.isfile(video):
        fail(f"Video not found: {video}")
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=index,codec_type,start_time,avg_frame_rate:format=duration,start_time", "-of", "json", video],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        fail(f"ffprobe could not read {video}: {r.stderr.strip()[:300]}")
    info = json.loads(r.stdout or "{}")
    streams = info.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if not v:
        fail(f"{video} has no video stream.")
    fmt = info.get("format", {})
    f_start = float(fmt.get("start_time") or 0)
    return {
        "duration": float(fmt.get("duration") or 0),
        "has_audio": a is not None,
        "audio_offset": (float(a.get("start_time") or 0) - f_start) if a else 0.0,
    }


def fmt_t(t):
    return f"{t:6.2f}"


def quote_words(words, idxs, limit=12):
    ws = [words[k]["text"] for k in idxs]
    s = " ".join(ws[:limit]) + (" ..." if len(ws) > limit else "")
    return f'"{s}"'


# ----------------------------------------------------------------------------- main
def build_plan(words, lines, args):
    T, tok_word = [], []
    for wi, w in enumerate(words):
        for t in norm_tokens(w["text"]):
            T.append(t)
            tok_word.append(wi)
    if not T:
        fail("The transcript words contain no letters or digits.")
    for ln in lines:
        ln["tokens"] = norm_tokens(ln["text"])

    # candidates per distinct line text (identical lines share one candidate set)
    by_key = {}
    for ln in lines:
        by_key.setdefault(tuple(ln["tokens"]), []).append(ln)
    cands = []
    for key, group in by_key.items():
        for c in find_candidates(list(key), T):
            c["key"] = key
            classify(c, len(key), args.min_coverage)
            cands.append(c)

    # one transcript stretch belongs to one line: strongest match wins
    accepted = []
    for c in sorted(cands, key=lambda c: (-c["score"], -c["t1"])):
        if all(c["t1"] < a["t0"] or c["t0"] > a["t1"] for a in accepted):
            accepted.append(c)
    accepted.sort(key=lambda c: c["t0"])

    for key, group in by_key.items():
        takes = [c for c in accepted if c["key"] == key]
        complete = [c for c in takes if c["kind"] == "complete"]
        # identical lines: the last copy gets the last complete take, the one before it the one before
        for k, ln in enumerate(reversed(group)):
            ln["takes"] = takes
            if k < len(complete):
                ln["chosen"] = complete[len(complete) - 1 - k]
                ln["status"] = "ok"
            elif takes and not complete and k == 0:
                ln["chosen"] = sorted(takes, key=lambda c: (c["coverage"], c["t0"]))[-1]
                ln["status"] = "incomplete"
            else:
                ln["chosen"] = None
                ln["status"] = "not found" if not takes else "no take left"
        if len(group) > 1:
            print(f"Note: script lines {', '.join(str(g['line']) for g in group)} are word-for-word the same; "
                  "each gets its own take, latest take to the latest line.", file=sys.stderr)

    # kept words per line, in script order, minus restarts inside the take
    word_toks = {}
    for j, wi in enumerate(tok_word):
        word_toks.setdefault(wi, []).append(j)
    runs = []
    for ln in lines:
        c = ln["chosen"]
        if not c:
            continue
        cuts = restart_runs(c, T, args.min_restart, args.cut_adlibs) if not args.keep_stumbles else []
        cut_tok = {t for cut in cuts for t in cut["tokens"]}
        w0, w1 = tok_word[c["t0"]], tok_word[c["t1"]]
        keep = []
        for wi in range(w0, w1 + 1):
            toks = word_toks.get(wi, [])
            if toks and all(j in cut_tok for j in toks):
                continue
            keep.append(wi)
        ln["cuts"] = [{"words": sorted({tok_word[t] for t in cut["tokens"]}), "why": cut["why"]} for cut in cuts]
        cur = []
        for wi in keep:
            if cur and wi != cur[-1] + 1:
                runs.append({"words": cur, "lines": [ln["line"]]})
                cur = []
            cur.append(wi)
        if cur:
            runs.append({"words": cur, "lines": [ln["line"]]})

    # neighbouring lines said in one breath stay one piece (keeps the natural pause)
    merged = []
    for r in runs:
        if merged and r["words"][0] == merged[-1]["words"][-1] + 1:
            merged[-1]["words"] += r["words"]
            merged[-1]["lines"] = sorted(set(merged[-1]["lines"] + r["lines"]))
        else:
            merged.append({"words": list(r["words"]), "lines": list(r["lines"])})
    return T, tok_word, accepted, merged


def to_ranges(words, runs, args, offset, duration, fps):
    kept = {wi for r in runs for wi in r["words"]}
    ranges = []
    for r in runs:
        a, b = r["words"][0], r["words"][-1]
        ws, we = words[a]["start"], words[b]["end"]
        # margin, clamped so it never reaches into a neighbouring word that is not in this range
        s = ws - args.margin_before
        e = we + args.margin_after
        if a > 0:
            s = max(s, min(words[a - 1]["end"], ws))
        if b + 1 < len(words):
            e = min(e, max(words[b + 1]["start"], we))
        s, e = s + offset, e + offset
        s = max(0.0, s)
        if duration:
            e = min(duration, e)
        s = round(s * fps) / fps
        e = round(e * fps) / fps
        if e <= s:
            e = s + 1 / fps
        ranges.append({"start": round(s, 4), "end": round(e, 4), "lines": r["lines"], "words": [a, b]})
    # touching ranges in time order become one
    out = []
    for rg in ranges:
        if out and out[-1]["start"] <= rg["start"] <= out[-1]["end"] + 1e-6:
            out[-1]["end"] = max(out[-1]["end"], rg["end"])
            out[-1]["lines"] = sorted(set(out[-1]["lines"] + rg["lines"]))
            out[-1]["words"][1] = rg["words"][1]
        else:
            out.append(rg)
    dropped, cur = [], []
    for wi in range(len(words)):
        if wi in kept:
            if cur:
                dropped.append(cur)
            cur = []
        else:
            cur.append(wi)
    if cur:
        dropped.append(cur)
    return out, dropped


def label_dropped(span, accepted, tok_word, lines, cut_lookup):
    by_key = {tuple(ln["tokens"]): ln for ln in lines}
    wi = span[0]
    if wi in cut_lookup:
        return cut_lookup[wi]
    for c in accepted:
        w0, w1 = tok_word[c["t0"]], tok_word[c["t1"]]
        if w0 <= wi <= w1:
            ln = by_key.get(c["key"])
            n = ln["line"] if ln else "?"
            kind = {"complete": "earlier take", "false start": "false start", "fragment": "partial take"}[c["kind"]]
            if ln and ln.get("chosen") is c:
                return f"inside the kept take of line {n}"
            return f"{kind} of line {n}"
    return "off-script"


def filter_graph(ranges, has_audio, fade):
    parts, pads = [], []
    for k, rg in enumerate(ranges):
        s, e = rg["start"], rg["end"]
        parts.append(f"[0:v]trim=start={s:.6f}:end={e:.6f},setpts=PTS-STARTPTS[v{k}]")
        if has_audio:
            d = e - s
            f = min(fade, d / 4)
            a = f"[0:a]atrim=start={s:.6f}:end={e:.6f},asetpts=PTS-STARTPTS"
            if f > 0:
                a += f",afade=t=in:st=0:d={f:.4f},afade=t=out:st={d - f:.6f}:d={f:.4f}"
            parts.append(a + f"[a{k}]")
            pads.append(f"[v{k}][a{k}]")
        else:
            pads.append(f"[v{k}]")
    tail = f"concat=n={len(ranges)}:v=1:a={1 if has_audio else 0}" + ("[v][a]" if has_audio else "[v]")
    parts.append("".join(pads) + tail)
    return ";\n".join(parts) + "\n"


def ffmpeg_cmd(video, filter_path, cut_path, has_audio, fps):
    cmd = ["ffmpeg", "-hide_banner", "-y", "-i", video, "-/filter_complex", filter_path, "-map", "[v]"]
    if has_audio:
        cmd += ["-map", "[a]"]
    cmd += ["-fps_mode", "cfr", "-r", str(fps), "-c:v", "libx264", "-preset", "medium", "-crf", "14",
            "-pix_fmt", "yuv420p"]
    if has_audio:
        cmd += ["-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
    cmd += ["-movflags", "+faststart", cut_path]
    return cmd


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="retake_ranges.py",
        description="Keep the last take of every SCRIPT.md line in a raw take; write keep-ranges JSON "
        "and a re-encoding ffmpeg cut. See the docstring at the top of this file for the full recipe.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--transcript", required=True, help="word-level transcript JSON of the RAW take (hyperframes transcribe format)")
    p.add_argument("--script", required=True, help="SCRIPT.md, one spoken sentence per line")
    p.add_argument("--video", help="the raw take the transcript came from (needed for the ffmpeg command)")
    p.add_argument("--out", help="keep-ranges JSON to write (default: keep-ranges.json next to the transcript)")
    p.add_argument("--cut", help="where the ffmpeg command writes the cut video (default: retake-cut.mp4 next to --out)")
    p.add_argument("--dry-run", action="store_true", help="print the decision for every line and write nothing")
    p.add_argument("--render", action="store_true", help="run the ffmpeg command now (needs --video)")
    p.add_argument("--margin-before", type=float, default=0.12, help="seconds kept before the first word of a range")
    p.add_argument("--margin-after", type=float, default=0.25, help="seconds kept after the last word of a range")
    p.add_argument("--audio-offset", default="auto", help="seconds added to transcript times to get video times; 'auto' probes --video")
    p.add_argument("--fps", type=int, default=30, help="cut points snap to this frame rate, and the cut is encoded at it")
    p.add_argument("--min-coverage", type=float, default=0.6, help="share of a line's words a take must hit to count as complete")
    p.add_argument("--min-restart", type=int, default=2, help="shortest repeated run (words) inside a line that is cut as a restart")
    p.add_argument("--cut-adlibs", type=int, default=0, help="also cut off-script runs of this many words inside a line (0 = keep them)")
    p.add_argument("--keep-stumbles", action="store_true", help="do not cut restarts inside a line")
    p.add_argument("--fade", type=float, default=0.008, help="audio fade at each cut, seconds (stops clicks)")
    args = p.parse_args(argv)

    words = load_transcript(args.transcript)
    lines = read_script_lines(args.script)
    info = probe(args.video) if args.video else None
    if args.render and not args.video:
        fail("--render needs --video (the raw take to cut).")
    if args.audio_offset == "auto":
        offset = info["audio_offset"] if info else 0.0
    else:
        try:
            offset = float(args.audio_offset)
        except ValueError:
            fail(f"--audio-offset must be 'auto' or a number of seconds, got {args.audio_offset!r}.")
    duration = info["duration"] if info else 0.0

    T, tok_word, accepted, runs = build_plan(words, lines, args)
    ranges, dropped = to_ranges(words, runs, args, offset, duration, args.fps)
    if not ranges:
        fail("None of the script lines were found in the transcript. Check that the script and the take match.")

    cut_lookup = {}
    for ln in lines:
        for cut in ln.get("cuts", []):
            for wi in cut["words"]:
                cut_lookup[wi] = f"{cut['why']} inside line {ln['line']}"

    # ---- report
    v = lambda t: t + offset  # noqa: E731  (video time)
    span = lambda c: (v(words[tok_word[c["t0"]]]["start"]), v(words[tok_word[c["t1"]]]["end"]))  # noqa: E731
    total_in = duration or (words[-1]["end"] + offset)
    total_out = sum(r["end"] - r["start"] for r in ranges)
    print(f"Script: {len(lines)} lines. Transcript: {len(words)} words. Take length: {total_in:.2f} s.")
    if offset:
        print(f"Audio starts {offset:.3f} s after the picture; times below are video times.")
    problems = 0
    line_report = []
    prev_end = -1.0
    for ln in lines:
        takes = ln.get("takes", [])
        c = ln.get("chosen")
        desc = ", ".join(f"{fmt_t(span(t)[0]).strip()}-{fmt_t(span(t)[1]).strip()} {t['kind']}" for t in takes) or "none"
        print(f'Line {ln["line"]:>2}  "{ln["text"]}"')
        if ln["status"] == "ok":
            s, e = span(c)
            what = "keep it" if len(takes) == 1 else f"keep the last complete take ({s:.2f}-{e:.2f})"
            print(f"          {len(takes)} take{'s' if len(takes) != 1 else ''}: {desc} -> {what}")
        elif ln["status"] == "incomplete":
            problems += 1
            print(f"          {len(takes)} take(s): {desc} -> NO COMPLETE TAKE; keeping the fullest one "
                  f"({c['coverage']:.0%} of the words). Check this line.")
        else:
            problems += 1
            print(f"          NOT FOUND in the transcript. Re-record it, or check the script wording. ({ln['status']})")
        for cut in ln.get("cuts", []):
            ws = cut["words"]
            print(f"          cutting a {cut['why']}: {quote_words(words, ws)} "
                  f"({v(words[ws[0]]['start']):.2f}-{v(words[ws[-1]]['end']):.2f})")
        if c:
            s, e = span(c)
            if s < prev_end:
                print("          note: this take was recorded before the previous line's take; the cut plays it in script order.")
            prev_end = e
        line_report.append({
            "line": ln["line"], "text": ln["text"], "status": ln["status"],
            "takes": [{"start": round(span(t)[0], 3), "end": round(span(t)[1], 3), "kind": t["kind"],
                       "coverage": t["coverage"], "kept": t is c} for t in takes],
            "cuts": [{"start": round(v(words[cu["words"][0]]["start"]), 3), "end": round(v(words[cu["words"][-1]]["end"]), 3),
                      "text": " ".join(words[k]["text"] for k in cu["words"]), "why": cu["why"]} for cu in ln.get("cuts", [])],
        })
    drop_report = []
    if dropped:
        print("Dropped (not in any kept take):")
        for d in dropped:
            why = label_dropped(d, accepted, tok_word, lines, cut_lookup)
            s, e = v(words[d[0]]["start"]), v(words[d[-1]]["end"])
            print(f"  {fmt_t(s)}-{fmt_t(e)}  {why}: {quote_words(words, d)}")
            drop_report.append({"start": round(s, 3), "end": round(e, 3), "why": why,
                                "text": " ".join(words[k]["text"] for k in d)})
    print(f"Result: {len(ranges)} range{'s' if len(ranges) != 1 else ''} kept, {total_in:.2f} s in -> {total_out:.2f} s out"
          f" (margins {args.margin_before:.2f} s before, {args.margin_after:.2f} s after).")
    print("Cut points sit on the transcript's word times, so the cut is only as exact as those times "
          "(Whisper small.en was up to 0.6 s late in testing). Re-transcribe the cut and check it against the script.")
    if problems:
        print(f"Warning: {problems} line(s) need a look (see above).")
    if args.dry_run:
        print("Dry run: nothing written.")
        return 0

    out = os.path.abspath(args.out or os.path.join(os.path.dirname(os.path.abspath(args.transcript)), "keep-ranges.json"))
    base = out[:-5] if out.endswith(".json") else out
    os.makedirs(os.path.dirname(out), exist_ok=True)
    cut_path = os.path.abspath(args.cut or os.path.join(os.path.dirname(out), "retake-cut.mp4"))
    has_audio = info["has_audio"] if info else True
    doc = {
        "tool": "retake_ranges.py",
        "created": datetime.now().astimezone().isoformat(timespec="seconds"),
        "transcript": os.path.abspath(args.transcript),
        "script": os.path.abspath(args.script),
        "video": os.path.abspath(args.video) if args.video else None,
        "time_base": "video seconds (transcript time + audio_offset)",
        "audio_offset": round(offset, 4),
        "fps": args.fps,
        "margin": {"before": args.margin_before, "after": args.margin_after},
        "duration_in": round(total_in, 3),
        "duration_out": round(total_out, 3),
        "ranges": [{"start": r["start"], "end": r["end"], "lines": r["lines"]} for r in ranges],
        "keep": [[r["start"], r["end"]] for r in ranges],
        "lines": line_report,
        "dropped": drop_report,
    }
    with open(out, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2)
        f.write("\n")
    written = [out]
    if args.video:
        fpath = base + ".filter.txt"
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(filter_graph(ranges, has_audio, args.fade))
        cmd = ffmpeg_cmd(os.path.abspath(args.video), fpath, cut_path, has_audio, args.fps)
        spath = base + ".sh"
        with open(spath, "w", encoding="utf-8") as f:
            f.write("#!/bin/sh\n")
            f.write(f"# Generated by retake_ranges.py ({doc['created']}).\n")
            f.write(f"# Joins {len(ranges)} kept ranges of the raw take and RE-ENCODES every frame, so cuts are\n")
            f.write("# frame-accurate. Never swap this for a stream copy (-c copy snaps cuts to keyframes).\n")
            f.write("set -e\n")
            f.write(" ".join(shlex.quote(x) for x in cmd) + "\n")
        os.chmod(spath, 0o755)
        written += [fpath, spath]
    else:
        print("No --video given, so no ffmpeg command was written (the ranges JSON is in transcript time + offset 0).")
    print("Wrote: " + ", ".join(written))
    if args.render:
        if not shutil.which("ffmpeg"):
            fail("ffmpeg was not found on PATH. Install it (brew install ffmpeg) or run the .sh file elsewhere.")
        print(f"Rendering {cut_path} (re-encode, this takes a moment) ...")
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            fail("ffmpeg failed while cutting. Last lines of its log:\n" + "\n".join(r.stderr.strip().splitlines()[-8:]))
        print(f"Rendered: {cut_path}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)  # keep progress and error lines in order when piped
    try:
        sys.exit(main())
    except UserError as e:
        print(f"retake_ranges: {e}", file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        sys.exit(130)
