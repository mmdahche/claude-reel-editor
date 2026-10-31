---
name: reel-safezone-qa
description: Check a reel against the phone safe zones before the client sees it. One file goes to Instagram Reels, TikTok and YouTube Shorts, so the safe area is the union of all three. Text and logos inside x 80-930 and y 270-1440 (to x 1000 above y 900), captions on the fixed y 1280 line inside x 150-930, nothing readable under the right action rail, the top bar or the bottom caption/username area, and contrast must pass. Runs hyperframes check with full contrast and no-text bands, pulls frames with the zones drawn on, and does a visual pass. Use it after every render, and whenever the editor says "QA it", "will the buttons cover it", "safe zone", "is the text cut off", or "check the cover".
allowed-tools:
  - Read
  - Write
  - Bash
---

# reel-safezone-qa

The build already places text inside the safe area. This skill proves the finished video does too,
before the client finds a problem on their phone.

## When to use
- After `scripts/render.sh` writes `$V/final/<slug>-vN.mp4`, and after any re-render.
- Before choosing or regenerating `cover.jpg`.
- When a scene, a brand token or a composition has changed.

## When NOT to use
- Rhythm or hook structure: `reel-hook-check`. Loudness: `reel-audio-gate`.

## Inputs
- The kit folder with `index.html` built for this video (render.sh leaves it that way; if unsure:
  `node scripts/build.mjs --input $V/input --brand clients/<client>/brand.json`).
- `V=videos/<client>/<slug>` with `final/<slug>-vN.mp4`. QA output goes to `$V/review/qa/`.
- Safe-zone tokens (platform geometry, in `src/shell.html`, not brand): `--safe-left` 80,
  `--safe-right` 150, `--safe-right-upper` 80, `--safe-top` 270, `--hook-top` 285,
  `--content-bottom` 1180, `--caption-y` 1280, `--caption-max-w` 780. These come from third-party
  measurements; the apps do not publish them.

## Steps
1. **Full gate, contrast on** (render.sh runs check with `--no-contrast`, so run the full one here):
   `HYPERFRAMES_NO_TELEMETRY=1 npx --yes hyperframes@0.8.143 check . --caption-zone "x0=.08;y0=.64;x1=.92;y1=.693;severity=error"`
   0 errors. A contrast failure names the colour pair and a passing colour: fix the client's brand
   token (and tell the editor the look changed), never the gate.
2. **No-text bands.** `--caption-zone` flags any text box overlapping a band (fractions of
   1080x1920): top bar (y 0-270), bottom UI (y 1440-1920), left edge (x 0-80), right rail (x 932+,
   y 900-1440), upper right (x 1002+, y 270-900). Run each once:
   ```bash
   SEEK="seek=.02,.06,.10,.14,.18,.22,.26,.30,.34,.38,.42,.46,.50,.54,.58,.62,.66,.70,.74,.78,.82,.86,.90,.94,.98"
   for Z in "x0=0;y0=0;x1=1;y1=.1406" "x0=0;y0=.75;x1=1;y1=1" "x0=0;y0=0;x1=.0741;y1=1" \
            "x0=.863;y0=.4688;x1=1;y1=.75" "x0=.9278;y0=.1406;x1=1;y1=.4688"; do
     HYPERFRAMES_NO_TELEMETRY=1 npx --yes hyperframes@0.8.143 check . --no-contrast --caption-zone "$Z;severity=error;$SEEK" || echo "BAND FAILED: $Z"
   done
   ```
   One finding is expected: the `word-slam` overlay deliberately bleeds off both edges and is sized
   to read with the right 150 px covered. Note it, do not fail it. Any other text in a band is a
   real failure: fix the scene input, rebuild, run again.
3. **Caption line unchanged**: `grep -n "caption-y\|caption-max-w" src/shell.html` shows 1280px and 780px.
4. **Frames with the zones drawn on** (lime = text-safe, red = no text, yellow = caption band):
   ```bash
   mkdir -p $V/review/qa; F=$V/final/<slug>-vN.mp4
   ZONES="drawbox=x=80:y=270:w=850:h=1170:color=lime@0.9:t=3,drawbox=x=930:y=270:w=70:h=630:color=lime@0.5:t=2,drawbox=x=930:y=900:w=150:h=1020:color=red@0.3:t=fill,drawbox=x=0:y=0:w=1080:h=270:color=red@0.3:t=fill,drawbox=x=0:y=1440:w=930:h=480:color=red@0.2:t=fill,drawbox=x=150:y=1210:w=780:h=140:color=yellow@0.9:t=3"
   for t in $(python3 -I -c 'import json,sys;[print("%06.2f" % ((b["start"]+b["end"])/2)) for b in json.load(open(sys.argv[1]))["beats"]]' $V/input/shotlist.json); do
     ffmpeg -v error -y -ss $t -i $F -frames:v 1 -vf "$ZONES" $V/review/qa/zones-$t.png; done
   ffmpeg -v error -y -pattern_type glob -i "$V/review/qa/zones-*.png" -vf "scale=360:-1,tile=6x4" -frames:v 1 $V/review/qa/zones-sheet.jpg
   bash scripts/contact-sheet.sh $V/review/qa/sheet.jpg $F
   ```
5. **Visual pass.** Open both sheets. Look for words inside red, words cut at the top, captions off
   the yellow band, a logo or the CTA arrow in the right rail, captions over the mouth, low-contrast
   text on light plates, and a title-only first frame (frame 0 must show footage and the face).
   Do not hand the video to a "watch" tool that can fall back to a paid transcription API.
6. **Cover frame.** The cover title sits inside y 285-1440 and x 80-1000 (the profile grid crops to
   3:4 and loses 240 px top and bottom). Pull it with `ZONES` and look.
7. **Write it down**: `$V/review/qa/RESULT.md` with the check result, each band (pass, or which
   element failed), the word-slam note, and visual findings with timestamps.

## What to tell the editor (plain English)
One verdict sentence ("Nothing important sits under the buttons, and the captions stay on their
line"), then one sentence per real problem with its time and fix. Mention the safe-zone numbers are
third-party measurements until someone checks a real posted reel on each app.

## Checklist
- [ ] The full `check .` with contrast shows 0 errors.
- [ ] All five bands pass, or the only finding is the word slam.
- [ ] Caption geometry unchanged (1280 / 780).
- [ ] The zone sheet and contact sheet were looked at; findings are in RESULT.md.
- [ ] The cover title is inside y 285-1440, x 80-1000.
