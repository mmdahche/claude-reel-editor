#!/usr/bin/env python3
"""Structural hook + retention lint for a vertical reel (WORKFLOW.md: rhythm rules, script check).

Reads shotlist.json (+ transcript.json if given) and prints one PASS/FLAG line per rule.
Read-only. Exit 0 when every rule passes, 1 when anything is flagged, 2 on bad input.

  python3 -I hook_lint.py --shotlist input/<slug>/shotlist.json \
      [--transcript input/<slug>/transcript.json] [--kind standard|tip] [--min 40 --max 55] [--no-cta]
Runtime defaults: standard 40-55 s, tip 35 s or less, hard ceiling 60 s. A client's BRAND.md
may set its own target: pass it with --min/--max.
"""
import argparse, json, re, sys

ap = argparse.ArgumentParser()
ap.add_argument("--shotlist", required=True)
ap.add_argument("--transcript")
ap.add_argument("--kind", choices=["standard", "tip"], default="standard")
ap.add_argument("--min", type=float, help="shortest runtime in seconds (overrides --kind)")
ap.add_argument("--max", type=float, help="longest runtime in seconds (overrides --kind; 60 s ceiling still applies)")
ap.add_argument("--no-cta", action="store_true", help="this video ends without a comment/keyword CTA on purpose")
a = ap.parse_args()
try:
    sl = json.load(open(a.shotlist))
    words = json.load(open(a.transcript)) if a.transcript else []
except Exception as e:  # noqa: BLE001
    print(f"bad input: {e}"); sys.exit(2)

beats = sl.get("beats", [])
if not beats:
    print("bad input: shotlist has no beats"); sys.exit(2)
D = float(sl.get("duration", beats[-1]["end"]))
words = [w for w in words if isinstance(w.get("text"), str) and "start" in w]
flags = []

def rule(name, ok, detail):
    print(f"{'PASS' if ok else 'FLAG'}  {name}: {detail}")
    if not ok:
        flags.append(name)

def stype(b):
    return (b.get("scene") or {}).get("type", "")

def eff_mode(b):  # what the viewer sees (with --proof-split on), as build.mjs decides it
    if b["mode"] == "A" and b.get("proof") and b.get("layout") != "card":
        return "A2"
    if b["mode"] == "A2" and b.get("layout") == "card":
        return "A"
    return b["mode"]

print("beats:")
for b in beats:
    ov = ",".join(o.get("type", "?") for o in b.get("overlays", []))
    print(f"  {b['id']:<6} {str(b.get('tag', '-')):<7} {eff_mode(b):<3} {b['start']:7.2f}-{b['end']:7.2f}"
          f" ({b['end'] - b['start']:4.2f}s) {stype(b) or '-'} {b.get('layout', '')} {ov}")

lo, hi = (40, 55) if a.kind == "standard" else (0, 35)
if a.min is not None:
    lo = a.min
if a.max is not None:
    hi = a.max
rule("runtime", lo <= D <= hi and D <= 60, f"{D:.1f}s (target {lo:g}-{hi:g}s, hard ceiling 60s)")

early = [b for b in beats if b["start"] < 5.0]
text_hook = any(stype(b) == "hook-title" for b in early)
visual_hook = any(eff_mode(b) in ("A", "A2") and (b.get("scene") or b.get("proof")) for b in early)
spoken = [w for w in words if w["start"] < 5.0]
rule("text hook <5s", text_hook, "hook-title scene starts inside 5s" if text_hook else "no hook-title beat before 5s")
rule("visual hook <5s", visual_hook, "A/A2 beat with a scene or proof before 5s" if visual_hook else "no A/A2 visual before 5s")
if words:
    rule("spoken hook <5s", len(spoken) >= 4 and words[0]["start"] < 1.0,
         f"{len(spoken)} words before 5s, first word at {words[0]['start']:.2f}s")
seq = [eff_mode(b) for b in early]
first = beats[0]
frame0 = eff_mode(first) in ("A", "A2") and bool(first.get("scene") or first.get("proof"))
rule("frame 0: b-roll + face", frame0, f"first beat {first['id']} is {eff_mode(first)}" + ("" if frame0 else " (open on footage or a scene WITH the face visible, never a title-only card or a bare face)"))
rule("lock-in face beat <8s", any(eff_mode(b) == "B" and b["start"] < 8.0 for b in beats), " > ".join(eff_mode(b) for b in beats if b["start"] < 8.0) or "none")

lock = [b for b in beats if str(b.get("tag", "")).upper() == "LOCKIN"]
rule("lock-in beat", bool(lock), f"{len(lock)} LOCKIN beat(s): " + ", ".join(f"{b['id']} {eff_mode(b)}" for b in lock))

bb = [f"{p['id']}+{q['id']}" for p, q in zip(beats, beats[1:]) if eff_mode(p) == "B" and eff_mode(q) == "B"
      and not (p["end"] - p["start"] <= 1.2 and q["end"] - q["start"] <= 1.2)]
rule("no two B in a row", not bb, ", ".join(bb) or "none")

MAXH = {"A": 6, "A2": 6, "B": 4, "C": 5}
long_ = []
for b in beats:
    cap = 8 if stype(b) in ("table", "cta") else (3 if stype(b) == "hook-title" else MAXH[eff_mode(b)])
    if b["end"] - b["start"] > cap + 0.05:
        long_.append(f"{b['id']} {b['end'] - b['start']:.1f}s>{cap}s")
rule("max hold per mode", not long_, ", ".join(long_) or "all beats inside their hold")

events = [b["start"] for b in beats] + [o.get("at", b["start"]) for b in beats for o in b.get("overlays", [])]
events += [w["start"] for w in words]
dead, t = [], 0.0
while t < D - 0.5:
    if not any(t <= e < t + 2.0 for e in events):
        dead.append(f"{t:.0f}-{t + 2:.0f}s")
    t += 2.0
rule("change every 2s", not dead, ("empty windows " + ", ".join(dead)) if dead else "every 2s window has a cut, overlay or new word")

if words:
    span = max(0.1, words[-1]["end"] - words[0]["start"])
    wps = len(words) / span
    rule("words per second", 2.0 <= wps <= 3.4, f"{wps:.2f} w/s over {span:.1f}s (typical ~2.6; flag <2.0 or >3.4)")
    text = " ".join(w["text"] for w in words)
    sents = [len(s.split()) for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    runs = [i for i in range(len(sents) - 2) if max(sents[i:i + 3]) - min(sents[i:i + 3]) <= 2]
    rule("sentence-length variety", not runs, f"lengths {sents}" + (f"; 3 similar in a row at sentence {runs[0] + 1}" if runs else ""))

last = beats[-1]
if a.no_cta:
    print(f"SKIP  ends on CTA: --no-cta (last beat {last['id']} {eff_mode(last)} {stype(last) or '-'})")
else:
    rule("ends on CTA (C)", eff_mode(last) == "C" and stype(last) == "cta", f"last beat {last['id']} {eff_mode(last)} {stype(last) or '-'}")
slams = sum(1 for b in beats for o in b.get("overlays", []) if o.get("type") == "word-slam") + sum(1 for b in beats if stype(b) == "word-slam")
rule("word slams <=2", slams <= 2, f"{slams}")

print(f"\n{len(flags)} flag(s)" + (": " + ", ".join(flags) if flags else ""))
sys.exit(1 if flags else 0)
