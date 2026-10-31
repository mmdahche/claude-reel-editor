---
name: reel-hook-check
description: Free, deterministic hook and retention lint for a reel, run before anything is rendered. Checks that frame 0 shows b-roll and the face together, the spoken, text and visual hooks land inside 5 s, a lock-in beat with a named method, a picture change in every 2 s window, no two full-face (B) beats in a row, mode hold limits, words per second, runtime and the CTA ending, plus a script checklist (thread drift, contrast, value signal, open loop, key point said twice, reading level, sentence-length variety). Use it after every shot list or transcript, and whenever the editor asks "is this hook good", "check the script", "will people keep watching" or "is it too long". Use it instead of any paid virality predictor.
allowed-tools:
  - Read
  - Write
  - Bash
---

# reel-hook-check

Catches structural retention problems while they are still cheap to fix, before a render. It can
tell whether the hook is *built* right. It cannot tell whether the hook is *good*: that is the
editor's and the client's call, so say so every time.

## When to use
- Right after `reel-shotlist` writes `shotlist.json`, and again once `transcript.json` exists.
- The editor asks whether the opening works, or the runtime looks long.
- Before every render of a new video or a re-cut.

## When NOT to use
- Writing or re-cutting the beats: `reel-shotlist`. Phone UI overlap on the picture: `reel-safezone-qa`.

## Inputs
- `V=videos/<client>/<slug>`: `SCRIPT.md`, `SHOTLIST.md` (thread, emotion and lock-in method in its
  header), `input/shotlist.json`, and once recorded `input/transcript.json`.
- `clients/<client>/BRAND.md`: runtime target, reading level, whether the video ends on a comment
  keyword CTA.

## Steps
1. **Structural lint** (read-only; exits 1 if anything is flagged):
   ```bash
   python3 -I .claude/skills/reel-hook-check/scripts/hook_lint.py \
     --shotlist $V/input/shotlist.json --transcript $V/input/transcript.json \
     --kind standard        # "tip" for a single-tip video (35 s or less)
     # optional: --min 30 --max 45 (the client's runtime target), --no-cta (no keyword ending, on purpose)
   ```
   It prints the beat table, then PASS or FLAG for: runtime (default 40-55 s, tip 35 s or less,
   ceiling 60 s); frame 0 shows footage and face (A2 or an A scene beat, never a title-only card);
   a full-face lock-in beat inside 8 s; a text hook (`hook-title`) before 5 s; a visual hook before
   5 s; a spoken hook (4+ words before 5 s, first word under 1 s); at least one LOCKIN beat; no two
   B in a row (1.2 s punch exception); max hold per mode (A/A2 6 s, B 4 s, C 5 s, table and CTA
   8 s, hook title 3 s); every 2 s window has a cut, overlay or new word; 2.0-3.4 words per second;
   sentence-length variety; ending on a `cta`; 2 word slams or fewer. Without `--transcript` it
   skips the word rules, so run it again once the take exists.
2. **Lock-in method.** The SHOTLIST.md header must name one of: tease the proof, favourable
   transformation, contrast, magic box, objection handling, bold-claim double-down. None = FLAG.
3. **Script checklist.** Read SCRIPT.md line by line and mark each yes or no, quoting the line:
   - The thread is named and no line drifts more than one step from it; the hook's subject (or a
     pronoun for it) shows up at least every 2-3 sentences.
   - The common belief and the contrarian claim both appear in the first two lines.
   - Value is signalled within 5 s.
   - At least one concrete example or step the viewer can copy.
   - At least one open loop opened and later closed (a loop never closed is a FLAG).
   - The key point is said twice: once tight, once with an example.
   - Reading level about grade 6 or lower (or the level BRAND.md asks for): short words, active voice.
   - The target emotion is named, and the stakes and sound choices fit it.
   - Every beat earns its place. Propose cuts; the editor and client decide.
4. **Fixes.** For each FLAG, propose the smallest fix: a mode swap, splitting a long beat, an
   overlay in a dead window, or a script cut. Script changes need the client's yes (through the
   editor). Structure fixes go back through `reel-shotlist`.

## What to tell the editor (plain English)
One verdict sentence ("The hook is built right and it runs 47 seconds" or "Two things to fix before
I build"), then each flag as one sentence with its fix. End with: "This checks how the hook is built,
not whether it's good. That part is your call." Save the full output to `$V/review/hook-check.txt`.

## Checklist
- [ ] `hook_lint.py` ran with the transcript once one exists; the exit code was recorded.
- [ ] The lock-in method is named, or flagged.
- [ ] All script-checklist items are marked, with quotes.
- [ ] Every flag has a proposed fix. Script changes wait for a yes.
- [ ] The editor was told the lint cannot judge the hook's quality.
