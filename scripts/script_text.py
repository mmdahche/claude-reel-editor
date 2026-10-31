"""script_text.py - shared helpers for retake_ranges.py and script_snap.py (not a command).

Reading the hyperframes transcript JSON, reading SCRIPT.md (one spoken line per sentence),
and turning text into comparable word tokens ("621" and "six hundred and twenty-one" both
become six/hundred/twenty/one). Standard library only.
"""

import json
import re


class UserError(Exception):
    """A problem the user can fix; the scripts print it as a plain sentence, no traceback."""


def fail(msg):
    raise UserError(msg)


def read_transcript_json(path):
    """-> (data, words). `data` is the file as loaded (a list, or a dict with "words"); `words`
    is the list of word dicts inside it, checked for text/start/end, untouched otherwise."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        fail(f"Transcript not found: {path}")
    except json.JSONDecodeError as e:
        fail(f"The transcript is not valid JSON ({path}, line {e.lineno}): {e.msg}")
    words = data.get("words") if isinstance(data, dict) else data
    if not isinstance(words, list) or not words:
        fail(
            f"The transcript has no words: {path}. Expected the hyperframes transcribe JSON, "
            'a list like [{"text": "Hello", "start": 0.1, "end": 0.4}, ...].'
        )
    for i, w in enumerate(words):
        if not isinstance(w, dict):
            fail(f"Word {i + 1} in the transcript is not an object: {w!r}")
        if w.get("text", w.get("word")) is None:
            fail(f"Word {i + 1} in the transcript has no text: {w!r}")
        try:
            float(w["start"])
            float(w["end"])
        except (KeyError, TypeError, ValueError):
            fail(f"Word {i + 1} ({w.get('text')!r}) in the transcript has no usable start/end times.")
    return data, words


def read_script_lines(path):
    """SCRIPT.md -> [{"line", "src_line", "text"}], one entry per spoken line.
    Skips blank lines, '#' headings, '>' quotes, '|' tables, HTML comments, code fences and
    YAML front matter; strips list markers, *emphasis* and [stage directions]."""
    try:
        with open(path, encoding="utf-8") as f:
            raw = f.read()
    except FileNotFoundError:
        fail(f"Script not found: {path}")
    raw = re.sub(r"<!--.*?-->", lambda m: "\n" * m.group(0).count("\n"), raw, flags=re.S)
    lines = raw.splitlines()
    start = 0
    if lines and lines[0].strip() == "---":  # YAML front matter
        for k in range(1, len(lines)):
            if lines[k].strip() in ("---", "..."):
                start = k + 1
                break
    out, fence = [], False
    for n in range(start, len(lines)):
        s = lines[n].strip()
        if s.startswith("```") or s.startswith("~~~"):
            fence = not fence
            continue
        if fence or not s or s[0] in "#>|" or re.fullmatch(r"[-*_=\s]{3,}", s):
            continue
        s = re.sub(r"^(?:[-*+]|\d+[.)])\s+", "", s)
        s = re.sub(r"\[[^\]]*\]", " ", s)
        s = s.replace("**", "").replace("__", "").replace("`", "").replace("*", "")
        s = " ".join(s.split())
        if re.search(r"[A-Za-z0-9]", s):
            out.append({"line": len(out) + 1, "src_line": n + 1, "text": s})
    if not out:
        fail(f"No spoken lines found in {path}. Put one sentence per line (headings and blank lines are skipped).")
    return out


_ONES = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
         "sixteen seventeen eighteen nineteen").split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()
NUMBER_WORDS = set(_ONES) | set(_TENS[2:]) | {"hundred", "thousand", "million", "billion"}


def int_words(n):
    """621 -> ['six', 'hundred', 'twenty', 'one']."""
    if n < 20:
        return [_ONES[n]]
    if n < 100:
        return [_TENS[n // 10]] + ([_ONES[n % 10]] if n % 10 else [])
    if n < 1000:
        return [_ONES[n // 100], "hundred"] + (int_words(n % 100) if n % 100 else [])
    for div, name in ((10 ** 9, "billion"), (10 ** 6, "million"), (1000, "thousand")):
        if n >= div:
            return int_words(n // div) + [name] + (int_words(n % div) if n % div else [])
    return [str(n)]


def norm_tokens(text):
    """Lower-case word tokens for matching: punctuation dropped, hyphens split, digits spelled
    out, and the spoken 'and' inside a number ('six hundred AND twenty-one') removed."""
    t = text.lower().replace("’", "'").replace("‘", "'")
    t = re.sub(r"(?<=\d),(?=\d{3})", "", t)            # 1,000 -> 1000
    t = re.sub(r"(\d)\.(\d)", r"\1 point \2", t)       # 6.4 -> 6 point 4
    t = t.replace("%", " percent ")
    t = re.sub(r"[-–—/]+", " ", t)
    out = []
    for raw in t.split():
        w = re.sub(r"[^a-z0-9]", "", raw)
        if w.isdigit() and len(w) <= 12:
            out.extend(int_words(int(w)))
        elif w:
            out.append(w)
    return [w for k, w in enumerate(out)
            if not (w == "and" and 0 < k < len(out) - 1 and out[k - 1] in NUMBER_WORDS and out[k + 1] in NUMBER_WORDS)]
