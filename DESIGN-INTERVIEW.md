# DESIGN-INTERVIEW

This kit has no look of its own. Before the first video for a client, run this interview: your
Claude Code agent asks you (or your client) about the brand, one question at a time, and writes
`clients/<client-name>/BRAND.md`, `brand.json` and `terms.txt` from the answers.

Open Claude Code in the kit folder, copy everything in the box below, and paste it.

---

```text
Run the design interview for a new client of this reel kit.

Before asking anything, read: CLAUDE.md, WORKFLOW.md (sections 6 and 7), clients/README.md,
clients/_example/BRAND.md, clients/_example/brand.json, the token comments in src/shell.html, and
assets/fonts/README.md. Do not read or copy clients/_demo-test-only: its greys are a test fixture,
not a design, and must not influence anything you suggest.

How to interview me:
- Plain English, one question per message, short. Wait for my answer before the next question.
- Start by asking the client's name and handle, then make the folder:
  cp -R clients/_example clients/<client-name>   (lowercase, dashes)
- Then cover these areas in order. Skip a question if an earlier answer already settled it.
  1. Who they are, what they do, who watches, which platforms.
  2. Tone: how they talk, reading level, words or topics to avoid, the feeling a video should leave.
  3. References: 1-3 accounts or videos whose look they like, and what exactly they like in each.
     (Do not watch or download anything; just take notes from my answer.)
  4. Colours: stage (background) colour, the one accent colour and how loud it should be, text
     colour, a "good" colour (wins, money saved), a "stakes" colour (warnings), the light plate
     colour behind phone mockups and quotes. Accept names, hex codes, or "you suggest".
  5. Shapes: sharp, soft or round corners.
  6. Fonts: a heavy sans for headlines and captions, a mono for small labels, and optionally one
     serif italic for a single accent word per title. Ask where the font files come from and
     whether the licence allows embedding in video. If they have none, offer two or three
     open-licence (OFL) options and explain they must download them from the official source,
     with the licence file, into clients/<client-name>/fonts/.
  7. Captions: big words one at a time, or a short pill of 2-4 words. Caption colour.
  8. Layout: real footage as split, card, or "decide per beat"; face in a rounded box or cut out
     and standing free (macOS only); whole take at 1.08x or natural speed; runtime target.
  9. Footage grade: none, or a feel (warm, cool, neutral) and how strong.
  10. Logo: file(s), and where it may appear (CTA footer only is the safe default; never a
      watermark unless asked). Avatar image for the CTA's DM reply (optional).
  11. Call to action: the comment keyword and what it delivers, safe CTA wording, an optional short
      footer line, and whether some videos end with no keyword.
  12. Sound: sound effects on or off, the music mood, and whether the voice already sounds bright
      (voice EQ off) or needs the presence lift (voice EQ on, the default).
  13. Names the transcriber might misspell (brand, products, people) for terms.txt.
  14. Any default in WORKFLOW.md they want changed or dropped.

When you suggest values ("you suggest"), give two or three concrete options with a one-line reason
each and let me choose. Do not invent a brand: every value must trace to an answer or a choice I made.

Writing the files (only after I confirm a short summary of all answers):
- clients/<client-name>/BRAND.md: fill every section of the template in plain words, including WHY
  each choice was made, and a "Rules this client changed" section with today's date.
- clients/<client-name>/brand.json: fill EVERY token in "tokens" (the build refuses empty ones).
  Rules: tokens marked (hex) in src/shell.html must be #rrggbb; rgba() is fine for the see-through
  ones; px values need "px". Derive the secondary tokens from the main colours (glow colours from
  the stage, --line and --card-border from the text or accent colour, --accent-text as a lighter
  tint of the accent that passes contrast on the stage, --accent-ink as a dark colour readable on
  the accent). Keep text light on a darker stage: the scenes are built for that.
  "fonts": family names plus "files" with paths inside the client folder. "grade": {} with
  --grade-intensity 0 if they want none; otherwise a HyperFrames color-grading payload (read the
  hyperframes color-grading docs from the plugin) and an intensity between 0.3 and 0.7.
  "cta" and "audio" from the answers.
- clients/<client-name>/terms.txt: one name per line.

Then check it:
- node scripts/build.mjs --input demo-synthetic --brand clients/<client-name>/brand.json
  (run bash scripts/make-demo.sh first if demo-synthetic/face.mp4 is missing)
- HYPERFRAMES_NO_TELEMETRY=1 npx --yes hyperframes@0.8.143 check .
  Contrast must pass. If a colour fails, show me the failing pair and two fixes, and let me choose.
- HYPERFRAMES_NO_TELEMETRY=1 npx --yes hyperframes@0.8.143 snapshot . --at 1.5,10.5,17.9,31 --describe false --output renders/look-<client-name>
  and show me the stills. Ask "keep, or change something?" and loop until I say keep.

Finish with one plain sentence on what was written and where, and the next step (the first script).
```

---

**After the interview:** the client folder is private client material and is git-ignored by
default (see `clients/README.md`). Re-run any part of the interview later by asking the agent to
"update the brand for <client-name>": it should change only what you name and re-run the check.
