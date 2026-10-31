#!/usr/bin/env python3
"""script_snap.py - spell brand and product names in a transcript the way SCRIPT.md spells them.

Raw-take recipe (WORKFLOW.md, "Raw take to clean take"):
  transcribe -> retake_ranges -> ffmpeg re-encode -> auto-editor silence pass -> speed
  -> clean voice -> re-transcribe -> script_snap -> face_fit -> build

What it does
  Speech engines have no vocabulary prompt here, so "Claude" comes back as "Cloud" or "CLON",
  "Codex" as "Kodak" or "codecs", a brand name as two plain words. We know what was
  said: it is in SCRIPT.md. This script lines the transcript up against the script word by
  word, and for every name in the script it looks at the transcript words around the same
  spot (within --window words). If one of them sounds or reads close enough (--min-similarity
  0.72), it rewrites that word's TEXT to the script's spelling. When the heard word sits exactly
  in the name's slot (the script words on both sides were heard as written: "your CLON and"),
  a lower bar applies (--slot-similarity 0.45). Punctuation and a possessive 's stay.

  Names it protects: a short list of common tech names (DEFAULT_TERMS below, when they appear
  in the script), plus --terms / --terms-file (use the client's clients/<name>/terms.txt), plus every capitalised word in the middle of a
  script sentence (proper nouns such as a first name or "Friday"; turn off with --no-auto-terms).
  Only names are touched. Other misheard words are listed, not changed.

Timings never change. A word keeps its start and end. When a name was split into several
words ("back bone"), they become one word that runs from the first word's start to the last
word's end (turn off with --no-merge). The script checks this before writing.

It also prints the differences between the transcript and the script after the fixes. Run on
the re-transcribed clean cut, that list shows words a retake cut clipped or left in.

Usage
  python3 script_snap.py --transcript input/<slug>/transcript.json --script SCRIPT.md --dry-run
  python3 script_snap.py --transcript input/<slug>/transcript.json --script SCRIPT.md \\
      --out input/<slug>/transcript.json        # same path: the original is kept as *.pre-snap.json
  options: --terms "Brand Name,Product"  --terms-file clients/<name>/terms.txt  --window 6  --min-similarity 0.72
           --changes changes.json  --no-auto-terms  --no-merge

Output is the same JSON shape as the input (a list of words, or {"words": [...]} with every other
key kept). Needs Python 3.9+ and script_text.py from the same folder. Standard library only.
Tested on hand-checked and Whisper transcripts plus a synthetic split/joined/possessive name test.
"""

import argparse
import copy
import json
import math
import os
import re
import shutil
import sys
from difflib import SequenceMatcher

from script_text import UserError, fail, norm_tokens, read_script_lines, read_transcript_json

DEFAULT_TERMS = [
    "Claude", "Claude Code", "Codex", "Anthropic", "OpenAI", "ChatGPT", "Gemini", "HyperFrames", "GitHub",
]
NOT_NAMES = {"I", "I'm", "I've", "I'll", "I'd", "OK", "Okay"}
_AFFIX = re.compile(r"^([^\w]*)(.*?)([^\w]*)$", re.S)
_POSS = re.compile(r"(['’]s)$", re.I)


# ----------------------------------------------------------------------------- word helpers
def split_word(text):
    """'"Cloud's,' -> ('"', 'Cloud', "'s", ',')  (prefix, core, possessive, suffix)."""
    pre, core, suf = _AFFIX.match(text).groups()
    m = _POSS.search(core)
    poss = ""
    if m and len(core) > 2:
        poss, core = m.group(1), core[: m.start()]
    return pre, core, poss, suf


def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def phonetic(s):
    """Rough sound key: 'Claude' and 'Cloud' -> 'kld', 'Codex' and 'codecs' -> 'kdks'."""
    s = re.sub(r"[^a-z]", "", s.lower())
    if not s:
        return s
    for a, b in (("ph", "f"), ("ck", "k"), ("qu", "kw"), ("q", "k"), ("x", "ks"), ("z", "s"), ("c", "k"),
                 ("dg", "j"), ("gh", "g"), ("wr", "r"), ("kn", "n")):
        s = s.replace(a, b)
    out = s[0]
    for ch in re.sub(r"[aeiouyhw]", "", s[1:]):
        if ch != out[-1]:
            out += ch
    return out


def similarity(a, b):
    """0..1. Spelling likeness, lifted by sound likeness ('cloud' vs 'claude' = 0.86)."""
    if not a or not b:
        return 0.0
    r1 = SequenceMatcher(None, a, b).ratio()
    pa, pb = phonetic(a), phonetic(b)
    r2 = SequenceMatcher(None, pa, pb).ratio() if pa and pb else 0.0
    best = max(r1, (r1 + r2) / 2)
    if min(len(a), len(b)) <= 3 and r1 < 0.6:  # short names ("Al", "Jo") need real spelling overlap too
        best = min(best, r1)
    return best


# ----------------------------------------------------------------------------- script side
def script_words(lines):
    """Every script word with its line, its spelling and whether it opens a sentence."""
    out = []
    for ln in lines:
        prev = None
        for raw in ln["text"].split():
            pre, core, poss, suf = split_word(raw)
            if not norm(core):
                prev = raw
                continue
            opens = prev is None or bool(re.search(r"[.!?:]['\")”’]*$", prev))
            out.append({"line": ln["line"], "raw": raw, "core": core, "norm": norm(core + poss),
                        "base": norm(core), "opens": opens, "punct_after": bool(suf.strip())})
            prev = raw
    return out


def looks_like_name(w):
    c = w["core"]
    if c in NOT_NAMES or not c[:1].isalpha():
        return False
    if re.search(r"[a-z][A-Z]|[A-Z]{2}", c) or (re.search(r"\d", c) and re.search(r"[A-Za-z]", c)):
        return True
    return c[0].isupper() and not w["opens"]


def find_terms(sw, extra, auto):
    known = {tuple(norm(x) for x in t.split()) for t in DEFAULT_TERMS + extra if t.strip()}
    known = sorted(known, key=len, reverse=True)
    occ, p = [], 0
    while p < len(sw):
        hit = 0
        for kn in known:
            if tuple(w["base"] for w in sw[p:p + len(kn)]) == kn:
                hit = len(kn)
                break
        if not hit and auto and looks_like_name(sw[p]):
            hit = 1
            # "Product Name": consecutive capitalised words with no punctuation between them are one name
            while p + hit < len(sw) and not sw[p + hit - 1]["punct_after"] and sw[p + hit]["core"][:1].isupper() \
                    and sw[p + hit]["core"] not in NOT_NAMES and sw[p + hit]["line"] == sw[p]["line"]:
                hit += 1
        if hit:
            occ.append((p, p + hit))
            p += hit
        else:
            p += 1
    return occ


# ----------------------------------------------------------------------------- matching
def anchors(S, T):
    """Script position -> transcript position for every word the two agree on exactly."""
    m = {}
    for a, b, size in SequenceMatcher(None, S, T, autojunk=False).get_matching_blocks():
        for k in range(size):
            m[a + k] = b + k
    return m


def expected_pos(p, amap, nS, nT):
    before = [a for a in amap if a < p]
    after = [a for a in amap if a > p]
    if before and after:
        pa, pb = max(before), min(after)
        qa, qb = amap[pa], amap[pb]
        return qa + (p - pa) * (qb - qa) / (pb - pa)
    if before:
        pa = max(before)
        return amap[pa] + (p - pa)
    if after:
        pb = min(after)
        return amap[pb] - (pb - p)
    return p * nT / max(1, nS)


def snap(words, lines, args):
    sw = script_words(lines)
    S = [w["norm"] for w in sw]
    tparts = [split_word(str(w.get("text", ""))) for w in words]
    T = [norm(core + poss) for _, core, poss, _ in tparts]
    amap = anchors(S, T)
    occ = find_terms(sw, args.extra_terms, not args.no_auto_terms)
    term_pos = {p for a, b in occ for p in range(a, b)}
    protected = {q for p, q in amap.items() if p not in term_pos}  # agreed words that are not names
    claimed, changes, missed, already = set(), [], [], 0

    for a, b in occ:
        k = b - a
        term_cores = [sw[p]["core"] for p in range(a, b)]
        term_text = " ".join(term_cores)
        term_key = "".join(sw[p]["base"] for p in range(a, b))
        line_no = sw[a]["line"]
        # 1) the transcript already has these exact words here: only spelling/case can differ
        if all(p in amap for p in range(a, b)) and all(amap[p + 1] == amap[p] + 1 for p in range(a, b - 1)):
            q0 = amap[a]
            for i, p in enumerate(range(a, b)):
                q = q0 + i
                pre, core, poss, suf = tparts[q]
                claimed.add(q)
                if core != sw[p]["core"]:
                    changes.append({"q": [q], "to": pre + sw[p]["core"] + poss + suf, "sim": 1.0, "line": line_no,
                                    "term": term_text})
                else:
                    already += 1
            continue
        # 2) the name's exact slot: the words on both sides agree with the script and 1..k+1 heard
        #    words sit between them ("your CLON and"). Position is strong evidence, so the bar is lower.
        best, need = None, args.min_similarity
        if (a - 1) in amap and b in amap:
            slot = list(range(amap[a - 1] + 1, amap[b]))
            if 1 <= len(slot) <= k + 1 and not any(x in claimed or x in protected for x in slot) \
                    and not (args.no_merge and len(slot) not in (1, k)):
                sim = similarity("".join(norm(tparts[x][1]) for x in slot), term_key)
                if sim >= args.slot_similarity:
                    best, need = (sim, sim, slot), args.slot_similarity
        # 3) otherwise the best-sounding span of 1..k+1 words near where the name should be
        q = expected_pos(a, amap, len(S), len(T))
        lo, hi = max(0, math.floor(q) - args.window), min(len(T) - 1, math.ceil(q) + args.window)
        for s in range(lo, hi + 1) if best is None else ():
            for L in range(1, min(k + 1, 3) + 1):
                span = list(range(s, s + L))
                if span[-1] >= len(T) or any(x in claimed or x in protected for x in span):
                    continue
                if L not in (1, k) and args.no_merge:
                    continue
                cand = "".join(norm(tparts[x][1]) for x in span)
                sim = similarity(cand, term_key)
                score = sim - 0.01 * abs(s - q) - 0.02 * abs(L - k)
                if best is None or score > best[0]:
                    best = (score, sim, span)
        if not best or best[1] < need:
            missed.append({"term": term_text, "line": line_no,
                           "nearest": " ".join(str(words[x].get("text")) for x in best[2]) if best else "",
                           "sim": round(best[1], 2) if best else 0})
            continue
        _, sim, span = best
        claimed.update(span)
        if len(span) == k:
            for i, x in enumerate(span):
                pre, core, poss, suf = tparts[x]
                if core != term_cores[i]:
                    changes.append({"q": [x], "to": pre + term_cores[i] + poss + suf, "sim": sim, "line": line_no,
                                    "term": term_text})
                else:
                    already += 1
        else:
            pre = tparts[span[0]][0]
            _, _, poss, suf = tparts[span[-1]]
            changes.append({"q": span, "to": pre + term_text + poss + suf, "sim": sim, "line": line_no, "term": term_text})
    return changes, missed, already, occ, sw


def apply(words, changes):
    out, skip = [], set()
    by_first = {c["q"][0]: c for c in changes}
    for c in changes:
        skip.update(c["q"][1:])
    for i, w in enumerate(words):
        if i in skip:
            continue
        c = by_first.get(i)
        if not c:
            out.append(w)
            continue
        nw = copy.deepcopy(w)
        nw["text"] = c["to"]
        if len(c["q"]) > 1:
            nw["end"] = words[c["q"][-1]]["end"]
        out.append(nw)
    return out


def timing_check(before, after, changes):
    """Walks the words in order: each output word must carry an input word's start, and that
    word's end (or, for joined words, the last joined word's end). Returns problems (empty = fine)."""
    last = {c["q"][0]: c["q"][-1] for c in changes}
    skip = {q for c in changes for q in c["q"][1:]}
    expect = [(before[i]["start"], before[last.get(i, i)]["end"]) for i in range(len(before)) if i not in skip]
    got = [(w["start"], w["end"]) for w in after]
    if len(expect) != len(got):
        return [f"{len(got)} words out, expected {len(expect)}"]
    return [f"word {w.get('text')!r}: {g} instead of {e}" for w, g, e in zip(after, got, expect) if g != e]


def script_diff(words_after, lines):
    """Differences between transcript and script, as plain sentences with times."""
    S, T, t_word = [], [], []
    for ln in lines:
        S += norm_tokens(ln["text"])
    for i, w in enumerate(words_after):
        for t in norm_tokens(str(w.get("text", ""))):
            T.append(t)
            t_word.append(i)
    sm = SequenceMatcher(None, S, T, autojunk=False)
    out = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        at = float(words_after[t_word[j1]]["start"]) if j1 < len(T) else (float(words_after[-1]["end"]) if words_after else 0.0)
        script_part = " ".join(S[i1:i2])
        said = " ".join(T[j1:j2])
        if op == "replace":
            out.append({"at": at, "kind": "different", "script": script_part, "transcript": said})
        elif op == "delete":
            out.append({"at": at, "kind": "missing", "script": script_part, "transcript": ""})
        else:
            out.append({"at": at, "kind": "extra", "script": "", "transcript": said})
    same = sum(size for _, _, size in sm.get_matching_blocks())
    return out, same, len(S)


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="script_snap.py",
        description="Spell brand and product names in a word-level transcript the way SCRIPT.md spells them. "
        "Timings never change. See the docstring at the top of this file for details.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--transcript", required=True, help="word-level transcript JSON (hyperframes transcribe format)")
    p.add_argument("--script", required=True, help="SCRIPT.md, one spoken sentence per line")
    p.add_argument("--out", help="corrected transcript to write (required unless --dry-run)")
    p.add_argument("--dry-run", action="store_true", help="print the changes and write nothing")
    p.add_argument("--changes", help="also write the change list and script differences as JSON here")
    p.add_argument("--terms", default="", help="extra names, comma-separated (spelled as in the script)")
    p.add_argument("--terms-file", help="extra names, one per line")
    p.add_argument("--window", type=int, default=6, help="how many words either side of the expected spot to search")
    p.add_argument("--min-similarity", type=float, default=0.72, help="0-1; how close a heard word must be to a name")
    p.add_argument("--slot-similarity", type=float, default=0.45,
                   help="0-1; the lower bar used when the heard word sits exactly in the name's slot (script words agree on both sides)")
    p.add_argument("--no-auto-terms", action="store_true", help="only the built-in and given names, not every capitalised word")
    p.add_argument("--no-merge", action="store_true", help="never join several heard words into one name")
    args = p.parse_args(argv)
    if not args.out and not args.dry_run:
        fail("Say where to write the corrected transcript with --out (or use --dry-run to only look).")

    extra = [t.strip() for t in args.terms.split(",") if t.strip()]
    if args.terms_file:
        try:
            with open(args.terms_file, encoding="utf-8") as f:
                extra += [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
        except FileNotFoundError:
            fail(f"Terms file not found: {args.terms_file}")
    args.extra_terms = extra

    data, words = read_transcript_json(args.transcript)
    lines = read_script_lines(args.script)
    changes, missed, already, occ, sw = snap(words, lines, args)
    new_words = apply(words, changes)
    problems = timing_check(words, new_words, changes)
    if problems:
        fail("Internal check failed, nothing written (timings would have changed): " + "; ".join(problems[:5]))

    names = sorted({" ".join(sw[p]["core"] for p in range(a, b)) for a, b in occ})
    print(f"Script names checked ({len(occ)} mentions): {', '.join(names) if names else 'none'}")
    if changes:
        print(f"{len(changes)} spelling fix{'es' if len(changes) != 1 else ''} (timings unchanged):")
        for c in changes:
            src = " ".join(str(words[q].get("text")) for q in c["q"])
            merged = f"  [{len(c['q'])} words joined into one]" if len(c["q"]) > 1 else ""
            print(f"  {float(words[c['q'][0]]['start']):7.2f} s  {src!r:<18} -> {c['to']!r:<18} "
                  f"similarity {c['sim']:.2f}  (script line {c['line']}){merged}")
    else:
        print("No spelling fixes needed.")
    if already:
        print(f"{already} name word{'s were' if already != 1 else ' was'} already spelled right.")
    for m in missed:
        near = f" (closest: {m['nearest']!r}, similarity {m['sim']:.2f})" if m["nearest"] else ""
        print(f"  Not found near its spot: {m['term']!r} from script line {m['line']}{near}. Check by hand.")

    diffs, same, total = script_diff(new_words, lines)
    print(f"Compared with the script: {same} of {total} script words heard as written.")
    if diffs:
        print("Differences from the script (other words are left as heard; check that these were really said):")
        for d in diffs:
            if d["kind"] == "different":
                print(f"  {d['at']:7.2f} s  heard {d['transcript']!r}, script says {d['script']!r}")
            elif d["kind"] == "missing":
                print(f"  {d['at']:7.2f} s  not heard: {d['script']!r}")
            else:
                print(f"  {d['at']:7.2f} s  extra, not in the script: {d['transcript']!r}")

    if args.changes and not args.dry_run:
        with open(args.changes, "w", encoding="utf-8") as f:
            json.dump({"changes": [{"start": float(words[c["q"][0]]["start"]), "from": " ".join(str(words[q].get("text")) for q in c["q"]),
                                    "to": c["to"], "similarity": round(c["sim"], 3), "script_line": c["line"],
                                    "words_joined": len(c["q"])} for c in changes],
                       "not_found": missed, "script_differences": diffs}, f, indent=2)
            f.write("\n")
    if args.dry_run:
        print("Dry run: nothing written.")
        return 0

    out_data = new_words
    if isinstance(data, dict):
        out_data = dict(data)
        out_data["words"] = new_words
    out = os.path.abspath(args.out)
    if os.path.exists(out) and os.path.samefile(out, os.path.abspath(args.transcript)):
        keep = re.sub(r"\.json$", "", out) + ".pre-snap.json"
        if not os.path.exists(keep):
            shutil.copy2(out, keep)
            print(f"Kept the original as {keep}")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(out_data, f, indent=2)
        f.write("\n")
    print(f"Wrote {out} ({len(new_words)} words; was {len(words)}).")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)  # keep progress and error lines in order when piped
    try:
        sys.exit(main())
    except UserError as e:
        print(f"script_snap: {e}", file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        sys.exit(130)
