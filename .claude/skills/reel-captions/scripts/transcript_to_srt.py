#!/usr/bin/env python3
"""Word-level transcript.json -> word-grouped SRT for a reel.

Groups follow the caption rules: up to --max-words words (default 3, the
--caption-max-words token), break after punctuation and at speech gaps over --gap seconds,
never close a group on a small joining word, and fold a one-word tail into the group before it.
Times are the transcript times, which is the same clock the build uses for burned captions
(an optional outro is appended after the body, so it does not shift them). Read-only on the input.

  python3 -I transcript_to_srt.py input/<slug>/transcript.json <video folder>/final/<slug>-v1.srt
"""
import argparse, json, re

ap = argparse.ArgumentParser()
ap.add_argument("transcript")
ap.add_argument("out")
ap.add_argument("--max-words", type=int, default=3)
ap.add_argument("--gap", type=float, default=0.3)
a = ap.parse_args()

STOP = {"a", "an", "the", "to", "and", "or", "but", "of", "in", "on", "for", "with", "at", "by", "from", "is", "my", "your"}
words = [w for w in json.load(open(a.transcript)) if isinstance(w.get("text"), str) and w["text"].strip()]
words.sort(key=lambda w: w["start"])

groups, cur = [], []
for i, w in enumerate(words):
    cur.append(w)
    nxt = words[i + 1] if i + 1 < len(words) else None
    punct = bool(re.search(r"[.,!?;:]$", w["text"].strip()))
    gap = nxt is not None and nxt["start"] - w["end"] > a.gap
    full = len(cur) >= a.max_words
    joiner = re.sub(r"\W", "", w["text"].lower()) in STOP
    ends_next = nxt is not None and not gap and bool(re.search(r"[.!?]$", nxt["text"].strip()))
    if nxt is None or punct or gap or (full and not joiner and not ends_next) or len(cur) >= a.max_words + 1:
        groups.append(cur)
        cur = []
if len(groups) > 1 and len(groups[-1]) == 1:
    prev = groups[-2]
    if not re.search(r"[.!?]$", prev[-1]["text"].strip()) and groups[-1][0]["start"] - prev[-1]["end"] <= a.gap:
        tail = groups.pop()
        groups[-1] = prev + tail

def ts(t):
    ms = int(round(max(0.0, t) * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"

lines = []
for n, g in enumerate(groups, 1):
    start, end = g[0]["start"], g[-1]["end"]
    if n < len(groups):
        end = min(end, groups[n][0]["start"])
    text = " ".join(w["text"].strip() for w in g)
    lines += [str(n), f"{ts(start)} --> {ts(end)}", text, ""]
open(a.out, "w").write("\n".join(lines))
print(f"wrote {a.out}: {len(groups)} captions from {len(words)} words")
