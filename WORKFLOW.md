# WORKFLOW: how a reel gets made

The method behind the kit, in order. The agent follows it for every video; the skills in
`.claude/skills/` hold the detailed checklists. Commands run from the kit folder.

**Who is who.** The *editor* runs this kit and talks to the agent. The *client* is the person or
brand the video is for (often the person on camera). The agent never posts, never contacts the
client directly, and never spends money (paid AI tools, paid APIs) without the editor's explicit
yes for that video.

**The one rule that carries across every video:** the client's kit (colours, fonts, caption style,
footage grade, sound) stays the same; the layout changes to fit each recording. If a video plan
drops any part of the kit or any default below, the plan names it under "Skipped rules" and the
editor (and client) approve it before the build starts.

---

## 1. Folders

```
clients/<client>/            BRAND.md, brand.json, terms.txt, logo and font files
videos/<client>/<slug>/      one folder per video (git-ignored: client footage)
  SCRIPT.md                  the client's script, one sentence per line
  SHOTLIST.md                script check, thread, emotion, lock-in method, beat table
  NEEDS.md                   captures still needed, hold / look cues per beat
  recording/raw.mp4          the raw take, as recorded (never edited)
  captures/                  screen recordings, screenshots, b-roll
  work/                      contact sheet, cuts, face fit, cutout work files
  input/                     what the build reads: face.mp4, transcript.json, shotlist.json
  final/                     <slug>-v1.mp4, <slug>-v1-nomusic.mp4, v2 ..., cover.jpg, .srt
  audio/                     voice-clean.wav, sfx-cues.json, music.txt
  review/                    hook check, QA sheets, caption snapshots
  POST.md, LOG.md
```

Media paths inside `shotlist.json` and `brand.json` are relative to the kit folder
(`videos/<client>/<slug>/input/face.mp4`); the build refuses paths outside it.

---

## 2. Script first, then record

1. The client writes `SCRIPT.md`, one sentence per line, in their own voice (BRAND.md has their tone).
2. Run `reel-shotlist`, then `reel-hook-check`. Put the thread (the one subject the hook promises),
   the target emotion, the lock-in method and the script checks at the top of `SHOTLIST.md`.
   The agent flags; the editor and client decide. A script with no lock-in method is a script
   problem: stop and say so before anything is built. Never judge whether a hook is *good*.
3. Write `NEEDS.md`: captures the client must send, and hold / look cues per beat
   ("beat 4: open palm toward the top of the frame, hold 1 s"), so they know where graphics land.
4. Only then does the client record.

## 3. Recording (send this list to the client)

- Raw take, 1080x1920 or 4K vertical, no edits, captions, music, filters or grade. Same spot and
  framing every time.
- Light on the face, some distance from the wall (cleaner cutouts), quiet room, mic close.
- Energy one notch above normal conversation, especially the hook and the CTA. Say the CTA slowly.
- One second of pause between lines. Stumbled? Pause and say the whole line again. **The last
  take of each line is the one that is kept.**
- Before stopping, step out of frame for 2-3 s (a clean plate of the empty background).
- After any setup change (new room, light, camera), send a 5-second test clip first; check the
  framing on a few frames before the real take.
- Screen recordings and screenshots go in `captures/` (phone 1080x1920, desktop 1920x1080).

---

## 4. Build steps, in order

`V=videos/<client>/<slug>`, `HF="HYPERFRAMES_NO_TELEMETRY=1 npx --yes hyperframes@0.8.143"`.
Every step runs locally by default. Steps marked *(optional worker)* have a wrapper in
`scripts/remote/` for editors with a second Mac; it is never required.

1. **Look at the take first**, one frame per second, before the shot list is final:
   `ffmpeg -v error -y -i $V/recording/raw.mp4 -vf "fps=1,scale=160:-1,tile=12x10" -frames:v 1 $V/work/contact-sheet.jpg`
2. **Rough cut: keep the last take of each line, cut pauses over 0.3 s, never inside a word.**
   - Transcribe the raw take: `$HF transcribe $V/recording/raw.mp4 -e auto --language en --dir $V/work`
   - `python3 scripts/retake_ranges.py --transcript $V/work/transcript.json --script $V/SCRIPT.md --video $V/recording/raw.mp4 --out $V/work/keep-ranges.json --dry-run`
     Read the decision for every line, then run again without `--dry-run` and add `--render`
     (writes `work/retake-cut.mp4`; frame-accurate re-encode, never a stream copy).
   - Silence pass (optional tool, auto-editor): `auto-editor $V/work/retake-cut.mp4 --edit audio:-30dB --margin 0.15s,0.25s -o $V/work/clean.mp4`
     (-30 dB is a first guess; check the result). Without auto-editor, use `retake-cut.mp4` as the clean cut.
   - Keep a beat of silence before a punchline. Effects go on after the cut, never before.
   - Fallback: the client's own clean cut of the keepers, exported with no effects.
3. **Speed (default 1.08x, optional):** `bash scripts/speed.sh $V/work/clean.mp4 $V/work/fast.mp4 1.08`
4. **Clean the voice (DeepFilterNet):** `bash scripts/clean-voice.sh $V/work/fast.mp4 $V/input/face.mp4`
   *(optional worker: `scripts/remote/deepfilter-remote.sh`)*. Never edit `recording/raw.mp4`.
5. **Transcribe the clean file with word times**, then snap names to the script:
   `$HF transcribe $V/input/face.mp4 -e auto --language en --dir $V/input` *(optional worker:
   `scripts/remote/transcribe-remote.sh`)*, copy it to `transcript.raw.json`, then
   `python3 scripts/script_snap.py --transcript $V/input/transcript.json --script $V/SCRIPT.md --terms-file clients/<client>/terms.txt --out $V/input/transcript.json`
6. **Face fit (macOS):** one fixed framing per take, never frame-by-frame tracking:
   `python3 scripts/face_fit.py $V/input/face.mp4 --out $V/work/face-fit.json --preview $V/work/face-fit-check.jpg --shotlist $V/input/shotlist.json --write-shotlist $V/input/shotlist.json`
   Look at the preview. Not on macOS: set `recording.eyeX/eyeY` by hand from a frame.
7. **Background cutout (macOS only, optional):** `bash scripts/cutout/cutout.sh $V/input/face.mp4 $V/input/face-cutout.webm $V/work/cutout`
   *(optional worker for the Vision pass: `scripts/remote/seg-remote.sh`)*, then measure the
   free-face values: `python3 scripts/cutout/free_face_fit.py $V/input/face-cutout.webm $V/work/free-face.json --ref-px 440 --top-at 1335 --run b05:12.0:18.1 ...`
   and point `recording.src` at the WebM. Skip this step and the face sits in the face box.
8. **Shot list:** `reel-shotlist` writes `$V/input/shotlist.json`; snap beat times to word times.
9. **Build:** `node scripts/build.mjs --input $V/input --brand clients/<client>/brand.json`
   Read every warning, including the layout line for each footage beat.
10. **Check (must be 0 errors):** `$HF check . --caption-zone "x0=.08;y0=.64;x1=.92;y1=.693;severity=error"`
    On any failure, run `$HF doctor` first.
11. **Render, both exports:** `bash scripts/render.sh <client> $V/input $V/final --name <slug>-v1 --music assets/music/<licensed bed>`
    *(optional worker: `scripts/remote/render-remote.sh`, same arguments)*. Writes
    `final/<slug>-v1.mp4` and `final/<slug>-v1-nomusic.mp4`. Heavy step: one render at a time.
12. **QA:** `reel-safezone-qa` and `reel-audio-gate`. Pick `final/cover.jpg`.
13. **Hand-off:** `reel-post` writes `POST.md` and the `LOG.md` entry. The agent never posts.

## 5. Review loop

The editor (with the client) watches `final/` on a phone and says "ship" or sends notes, **one
change per line, with the time**: "At 0:07 the logo covers the face." Each round renders the next
version (`--name <slug>-v2`, `-v3` ...) and keeps the earlier ones. Every round goes into `LOG.md`,
each note mapped to a beat id. A wording tweak, logo swap or "less music" is a JSON/HTML edit and a
re-render; a re-take is a re-render too.

---

## 6. Format essentials

**Canvas:** 1080x1920, 30 fps. One export for Reels, TikTok and Shorts.

**Layout modes**

| Mode | On screen | Use for | Max hold |
|---|---|---|---|
| A, stage split | scene panel on top (1080x1440), face in a rounded box below (x 40-1040, y 1400-1880) | built graphics: line-ups, tables, steps, stats, quotes, receipts; footage beats set to `card` | 6 s |
| A2, proof split | real footage full-bleed above y 1280, face full-bleed below, hard seam | footage beats set to `split` | 6 s |
| B, full face | the recording fills the frame | the lock-in sentence, punchlines, the ask | 4 s |
| C, full visual | a scene on the whole stage; optional face circle (PiP) | tables, stats, stakes, word slam, CTA | 5 s (table and CTA 8 s) |

**Rhythm**
1. Something in the picture changes every 2-4 s (captions do not count).
2. Switch mode every 1-2 sentences, and on every topic change.
3. **Frame 0 shows b-roll and the face together** (A2 split or an A scene with the face), with the
   hook title over it. Never a title-only opening. A full-face lock-in beat follows within ~5-8 s.
4. Group A and A2 into runs with B as the hinge; never ping-pong every beat.
5. Never two B beats in a row, unless a deliberate B-B-B punch of three lines of 1.2 s or less.
6. One word slam per video, two at most.
7. End on the ask. **No outro by default** (a silent end card can hurt retention); add one only
   when the client asks (`--outro <file>`).
8. Hard cuts between modes; dissolves only inside a panel.

**Real footage: card or split, per beat.** Split for the first reveal of real footage and for
anything the viewer must read on the phone or screen. Card when the stage graphic carries the
point and the footage backs it up. The client may override any beat. A footage beat with no
`layout` follows the brand's `--proof-split` token. Raw phone screen recordings go in a phone
mockup, never full-bleed (full-bleed reads as a repost).

**Safe zones (union of Reels, TikTok and Shorts; third-party measurements).** Words live between
y 270 and y 1330, left of x 930 (to x 1000 above y 900). The face lives below y 1280. Nothing
important on the right edge or in the top 270 px. Hook title starts at y 285. Scene text stays
above y 1180. Cover title inside y 285-1440, x 80-1000. These are tokens in `src/shell.html`; if a
real posted reel shows different overlays, change the token, not the scenes.

**Captions.** One fixed line at y 1280 in every mode, max 780 px wide (x 150-930), never moving.
Style from the client's brand: big words (one word at a time, uppercase, a fast short word may pair
with the next) or a short pill (2-4 words, breaks at punctuation and pauses, never ends on "to /
the / and"). Captions stop while a word slam is up. Never the serif accent in captions.

**Titles.** One serif-italic accent word per title at most (`*word*`), and it is the hinge of the
sentence, never a filler word.

**Grade.** Camera footage gets the client's grade (brand.json `grade` at `--grade-intensity`);
screen recordings and UI captures get `"grade": false`. The client exports ungraded; the build grades.

**Sound** (every video: voice, SFX and a bed, and always both exports)

| Part | Rule | Target |
|---|---|---|
| Voice | DeepFilterNet (`-D -a 24`, 48 kHz mono) first; then highpass 80 Hz, -3 dB @300 Hz, +6 dB @3.2 kHz, high shelf +4 dB @6.5 kHz, limiter. No compressor, no de-esser, no second denoise. | -16 LUFS |
| SFX | quiet and tactile; one per on-screen event, at most ~1 per 2 s; never on caption changes; none under the hook sentence except the title's own cue | 6-10 dB under the voice |
| Music bed | licensed only (a licence row per bed); starts at 0:00 with a 0.5 s fade-in, ducks ~7-8 dB under speech, fades over the last 1.5 s | -19 LUFS in the gaps |
| Master | one fixed gain + oversampled peak limiter (two passes, linear; never a dynamic loudness mode) | -14.5 LUFS, true peak -1.5 dBTP |
| Gate | fails outside -15..-13 LUFS or above -1 dBTP | both exports |

Always export with-music and `-nomusic`. If a platform mutes a reel, re-upload the `-nomusic` file
and add a track from the platform's own library.

**Export spec:** 1080x1920, 30 fps constant, H.264 High, yuv420p, ~11 Mbps VBR (12 Mbps cap), closed
1 s keyframe group, fast-start, AAC-LC 48 kHz stereo 192 kbps.

**Paid AI shots.** Default 0. Only when every condition holds: a story image, not a fact; nothing
in the captures or the scenes can show it within an hour; it lands in the first 10 s or the stakes
beat; the prompt has no text or UI (image models never render text). Still image first, video last.
Never without the editor's yes for that video; log any spend in `LOG.md`.

---

## 7. Scenes (`compositions/`)

Each scene's inputs are listed at the top of its file; the build warns on unknown inputs.

| Scene | Use |
|---|---|
| `hook-title` | the designed text hook; one `*serif*` word; optional kicker and visual tile; `persist` keeps it over the next beat |
| `lineup` | introduce 2-4 named things (logo tiles or images drop in) |
| `face-off` | two or three options side by side, "VS" seal, optional pick |
| `table` | rows x columns with a highlight sweep; optional "IN THE GUIDE" locks |
| `stat` / `fx-stat-decimal` | one number counting up in a ring; win / burn / accent tone |
| `steps` | 3-5 steps landing one per beat with checks |
| `screen-frame` | a screen recording in a phone or card frame (footage placed by the build) |
| `quote` | a post, quote or DM thread on a light plate, key phrase highlighted |
| `chapter` | pill row for "next item of a list" (0.6-1.2 s) |
| `receipt` | a log / commit list / bill typing in, one line highlighted |
| `stamp` (overlay) | a stakes stamp over the current scene |
| `word-slam` (overlay) | one giant word on the caption line (max two per video) |
| `cta` | "Comment KEYWORD", typed comment, DM reply with a guide cover, client footer |
| `cta-footer` (overlay) | only the client footer, for an ask that is not a comment keyword |
| `stage-bg` | the background, whole video (added by the build) |
| `fx-checklist`, `fx-chart-grow`, `fx-cover-story`, `fx-glass-type`, `fx-pills`, `fx-digital-zoom` | effect layers for the free-standing cutout (some have a "back" layer behind the face and a "front" overlay) |

---

## 8. shotlist.json

```jsonc
{
  "duration": 32.0,
  "recording": { "src": "videos/<client>/<slug>/input/face.mp4", "offset": 0, "eyeX": 0.5, "eyeY": 0.4 },
  "captures": { "screen": { "src": "videos/<client>/<slug>/captures/screen.mp4", "grade": false } },
  "beats": [
    { "id": "b01", "start": 0, "end": 3.0, "tag": "HOOK", "mode": "A2", "layout": "split",
      "proof": { "capture": "screen", "at": 0, "label": "LIVE", "focusY": 0.5 },
      "scene": { "type": "hook-title", "inputs": { "line1": "...", "line2": "One *word*." } } },
    { "id": "b02", "start": 3.0, "end": 5.5, "tag": "LOCKIN", "mode": "B" },
    { "id": "b03", "start": 5.5, "end": 9.0, "tag": "BODY", "mode": "A", "scene": { "type": "steps", "inputs": { } } },
    { "id": "b04", "start": 9.0, "end": 12.0, "tag": "STAKES", "mode": "C", "scene": { "type": "table", "inputs": { } },
      "overlays": [ { "type": "stamp", "at": 10.8, "inputs": { } } ], "pip": { "start": 9.5, "end": 12.0 } }
  ]
}
```

- Beats run back to back from 0; the last `end` equals `duration`. Times are seconds on the
  recording; the build snaps them to frames. Put beat and PiP starts on a 0.1 s grid (frame
  multiples of 3) to avoid a one-frame face lag seen on some renders.
- `mode`: A | A2 | B | C. A2 needs `proof: {capture, at, label?, focusY?}`. `layout`: card | split.
- `scene.continue: true` keeps the previous beat's scene playing. `scene.persist` (hook title)
  keeps it over the next beat.
- Sound: `tag` drives SFX restraint (HOOK keeps only the title's cue, LOCKIN only thuds);
  `"sfx": false` mutes a beat; `"sfx": [{"at": 12.3, "cue": "pop"}]` adds one.
- Opt-in fields: `"pip": {"continue": true}` (same circle through the next C beat);
  `"face": {"grade": false}` (leave a stretch ungraded); `"media": {"centerX": 636}` on
  `screen-frame`; `"ownAudio": true` (footage with its own sound cut into the take: kept out of the
  voice chain, the bed dips under it); `"face": {"free": {scale, topY, topAt, centerX?, oval?}}` on
  A/A2 beats or `pip.face` (the cutout stands free; values from `free_face_fit.py`).

---

## 9. Lessons already paid for

1. Never style `#root` with a background inside a scene (every scene root is `#root`); the main
   root is `#stage-root`.
2. A scene variable id must never match a token name (a variable `plate` overrode `--plate`).
3. Media inside a scene is placed at root level by the build (seek-safe); the face is cropped with
   `clip-path` (the renderer keeps `clip-path` and `border-radius`, not `border`).
4. Phone recordings often start the audio a little after the picture; `retake_ranges.py` probes
   and applies the offset.
5. Speech engines drift 0.2-0.6 s on some takes. Check a few words against the waveform; if times
   are late, try another engine before building.
6. Accent colour as text on a dark stage often fails contrast: that is what `--accent-text` is for.
7. The build reads tokens one declaration per line; never start a line in the token block with
   `--name:` inside a comment.
8. iPhone takes carry HLG/HDR tags: the render uses `--sdr`, and the cutout tone-maps first.
9. Opus audio in WebM comes out 20 ms early after an input seek; `cutout.sh` pre-delays it 960 samples.
10. ffmpeg's two-pass loudnorm silently switches to a dynamic (compressing) mode when peaks have
    no room. `scripts/master.sh` uses one fixed gain and a limiter instead.
11. Never hand-edit the generated `index.html`; change the shot list, the brand, or a scene.
12. Never loosen a gate (check, loudness, contrast) to get a pass. Fix the cause or say so.
