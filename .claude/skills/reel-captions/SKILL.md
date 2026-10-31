---
name: reel-captions
description: Make, fix and export the burned-in captions for a reel. Covers local transcription with word times, snapping brand and product names to the script's spelling, the caption style from the client's brand (big words one at a time, or a short pill) on the fixed caption line inside the safe zone, snapshot checks and the word-grouped SRT. Use it whenever the editor mentions captions, subtitles, "the words on screen", a misspelled or mistimed word, an SRT file, or a fresh take that needs transcribing, even if they just say "the text is wrong".
allowed-tools:
  - Read
  - Edit
  - Write
  - Bash
---

# reel-captions

Captions are burned in by the build from `transcript.json`, so words, timing and look all come from
one place. Fixing a caption means fixing the transcript or a brand token, then rebuilding. Never
hand-edit `index.html`: it is generated.

## When to use
- A new `face.mp4` is in `videos/<client>/<slug>/input/` and needs a word-level transcript.
- A word is wrong ("Cloud" for Claude, a client's product name split in two), mistimed, or a caption
  looks crowded.
- The editor wants the `.srt` for an editor app or a platform upload.

## When NOT to use
- The hook title or other designed text: that is a scene input (`reel-shotlist`).
- Changing the caption style: that is the client's look (`clients/<client>/brand.json`, set by
  DESIGN-INTERVIEW.md). Change it only when the editor asks.

## Inputs
- `V=videos/<client>/<slug>`: `input/face.mp4` (the clean take), `SCRIPT.md` (spelling reference).
- `clients/<client>/terms.txt` (one name per line: brand, product and people names to protect) and
  `clients/<client>/brand.json` caption tokens: `--caption-style` (bigword | pill),
  `--caption-max-words`, `--bigword-size` (the build shrinks long words, never below 56 px).
- Fixed geometry (not brand): caption line `--caption-y` 1280 px, max width 780 px (x 150-930).

## Steps
1. **Transcribe locally** (free, on-device; Parakeet when installed, else whisper.cpp):
   `HYPERFRAMES_NO_TELEMETRY=1 npx --yes hyperframes@0.8.143 transcribe $V/input/face.mp4 -e auto --language en --dir $V/input`
   Output: `$V/input/transcript.json`, `[{"text","start","end"}]` in seconds. Copy it once to
   `transcript.raw.json` before any edit. (Optional worker laptop: `scripts/remote/transcribe-remote.sh`.)
2. **Snap names to the script** (times never change):
   `python3 scripts/script_snap.py --transcript $V/input/transcript.json --script $V/SCRIPT.md --terms-file clients/<client>/terms.txt --out $V/input/transcript.json`
   The original is kept as `*.pre-snap.json`. Read the change list and the "differences from the
   script": they show anything the cut clipped or left in. Keep the speaker's real wording where
   they ad-libbed, because captions must match the voice. If word times look 0.2-0.4 s off on noisy
   audio, say so and cross-check another engine before building.
3. **Grouping** (the build applies it; check it in step 5): big words show one word at a time, a
   very fast short word (under 0.25 s) may pair with the next, up to 3 words and 12 characters.
   The pill groups 2-4 words, breaks at punctuation and pauses over about 0.3 s, never ends on a
   small joining word (to, the, and), no one-word orphan. Captions stop under a word slam. Captions
   never use the serif accent; that is for titles only.
4. **Build:** `node scripts/build.mjs --input $V/input --brand clients/<client>/brand.json`. The
   `[build] tokens:` line shows the caption style in use.
5. **Look at the captions.** Snapshot 4-6 moments (a long word, a brand name, a fast run, the CTA):
   `HYPERFRAMES_NO_TELEMETRY=1 npx --yes hyperframes@0.8.143 snapshot . --at 3.2,9.8,15.1,21.0 --describe false --output $V/review/captions`
   Always pass `--describe false`: otherwise it sends frames to Gemini (a paid API) whenever a Gemini key
   is set in the environment. Open the PNGs.
   Each caption is one line, centred on y 1280, inside x 150-930, readable over every mode.
6. **Gate:** `HYPERFRAMES_NO_TELEMETRY=1 npx --yes hyperframes@0.8.143 check .` shows 0 errors.
7. **SRT:** `python3 -I .claude/skills/reel-captions/scripts/transcript_to_srt.py $V/input/transcript.json $V/final/<slug>-v1.srt`
   Same grouping rules and clock as the burned captions. Spot-check two lines against the video.
8. **No-caption export:** the build has no switch for it. If asked, say so plainly and offer the SRT.

## What to tell the editor (plain English)
Two or three sentences: captions are on in the client's style, which words were corrected (named,
not a table), and where the SRT is. If a caption breaks awkwardly, say which line and what changed.

## Checklist
- [ ] `transcript.raw.json` kept; names snapped against SCRIPT.md and terms.txt; times untouched.
- [ ] Snapshots looked at: one line, centred on y 1280, inside x 150-930.
- [ ] `check .` shows 0 errors.
- [ ] The SRT was written and spot-checked.
