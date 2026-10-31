---
name: reel-audio-gate
description: Run and prove the reel's sound mix. Voice cleaned with DeepFilterNet then a light presence EQ and levelled to -16 LUFS, quiet SFX 6-10 dB under the voice on the beats, a licensed music bed ducked under the voice at -19 LUFS, and a linear master at -14.5 LUFS integrated with true peak -1.5 dBTP. The gate fails outside -15..-13 LUFS or above -1 dBTP, and every video ships both the with-music and the no-music export. Use it for every render with sound, and whenever the editor says "too loud", "too quiet", "can't hear the music", "music", "sound effects", "loudness", "muffled", "no-music version" or "trending sound", or before handing over a final.
allowed-tools:
  - Read
  - Write
  - Bash
---

# reel-audio-gate

Sound is part of the client's identity: quiet, tactile SFX, a bed you can feel but would not call
"music", the same loudness on every video, and always a no-music export so the client can add a
trending sound in-app.

## When to use
- Rendering any video (the with-music and `-nomusic` exports).
- A level complaint, an SFX on the wrong word, or `LOUDNESS GATE FAILED` in a render log.
- Checking a re-render after any audio or picture change.

## When NOT to use
- Choosing new SFX or music: that is a licensing job first (`assets/sfx/README.md`,
  `assets/music/README.md`). No file enters the kit without a licence row.
- Caption or picture problems: `reel-captions`, `reel-safezone-qa`.

## Inputs
- `V=videos/<client>/<slug>` with `input/face.mp4`, `input/transcript.json`, `input/shotlist.json`
  (beat `tag`s drive SFX restraint).
- `clients/<client>/BRAND.md` (sound section: mood, SFX on/off, music mood, voice EQ on/off) and
  `brand.json` `"audio"`.
- SFX files: `assets/sfx/<cue>.wav|mp3` for whoosh, tick, pop, thud, keys (the editor supplies them;
  a missing cue is skipped with a warning). Music beds: `assets/music/` with a row in
  `assets/music/LICENSES.md` for every bed.

## The voice chain (in this order)
1. Before the build: `bash scripts/clean-voice.sh <take.mp4> <take-clean.mp4>` (DeepFilterNet
   `-D -a 24` on a 48 kHz mono wav; picture copied untouched).
2. In the audio pass: highpass 80 Hz, -3 dB at 300 Hz, +6 dB at 3.2 kHz, high shelf +4 dB at
   6.5 kHz, level to -16 LUFS, limiter at -1 dBFS. No compressor, no de-esser, no second denoise
   (they made voices muffled or added static in listening tests). `--voice-eq off` drops the EQ for
   a voice that is already bright.

## Steps
1. **Render with sound** (build, check, render, audio pass, master, both exports):
   ```bash
   bash scripts/render.sh <client> $V/input $V/final --name <slug>-v1 --music assets/music/<bed> --bed-lufs -19
   ```
   Writes `$V/final/<slug>-v1.mp4` and `<slug>-v1-nomusic.mp4`. Stems go to
   `renders/<slug>-v1.audio/` (`voice-clean.wav`, `sfx.wav`, `music-bed.wav`, `mix.wav`,
   `mix-nomusic.wav`, `sfx-cues.json`, `report.json`). Bump `-v2`, `-v3` per review round; earlier
   versions stay. No licensed bed yet? Leave `--music` out: both files then carry the same audio,
   and the client posts the `-nomusic` file and adds music in the app.
   On a slow machine: `bash scripts/remote/render-remote.sh` with the same arguments (optional worker).
2. **Read the log for both exports**: `[master] ... final X LUFS integrated, true peak Y dBTP` and
   `loudness gate passed`. A `LOUDNESS GATE FAILED` means stop.
3. **Measure again, independently**, on each file:
   `ffmpeg -hide_banner -nostats -i $V/final/<slug>-v1.mp4 -af ebur128=peak=true -f null - 2>&1 | sed -n '/Summary:/,$p'`
   Pass: I between -15 and -13 LUFS (target -14.5), true peak -1.0 dBTP or lower (target -1.5).
4. **Check `report.json`**: `voice.I` about -16; `music.startsAt` 0 (the bed starts at 0:00 with a
   0.5 s fade-in and fades over the last 1.5 s); the ducked bed sits about 7-8 dB under speech;
   `mix` and `mixNoMusic` both exist.
5. **Check SFX restraint** in `sfx-cues.json`: HOOK beats keep only the hook title's cue, LOCKIN
   beats only thuds, whoosh/pop at least 1.0 s apart, nothing on caption changes, SFX peaks 6-10 dB
   under the voice. Read `dropped` and its reasons. To move or mute a cue, edit the beat's `sfx` in
   the shot list and re-render. Never edit a mix by hand.
6. **If it fails**, fix the cause (the voice chain, a hot SFX file, the bed level). Never widen the
   gate in `scripts/master.sh` or `scripts/audio-pass.mjs` to get a pass: a gate passed by
   loosening it is not a pass. Tell the editor instead.
7. **Package**: copy `voice-clean.wav` and `sfx-cues.json` to `$V/audio/`, and write
   `$V/audio/music.txt` with the bed file and its licence row (or "none").

## What to tell the editor (plain English)
Two sentences: "Sound is done: voice, sound effects and a quiet music bed at the usual loudness, and
the no-music version is next to it." One more for anything unusual: no bed, a dropped cue, a gate
failure and its fix. Numbers go in LOG.md, not chat.

## Checklist
- [ ] Both `<slug>-vN.mp4` and `<slug>-vN-nomusic.mp4` exist.
- [ ] Log and independent ebur128 pass for both files: -15..-13 LUFS, true peak -1 dBTP or lower.
- [ ] The bed has a licence row in `assets/music/LICENSES.md`, or there is no bed.
- [ ] SFX restraint holds; dropped cues reviewed.
- [ ] No gate threshold was changed. Stems copied to `$V/audio/`.
