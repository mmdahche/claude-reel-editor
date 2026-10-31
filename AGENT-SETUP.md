# AGENT-SETUP: hand-off for your Claude Code agent

Open Claude Code in this kit folder and paste this file (or say "read AGENT-SETUP.md and follow
it"). The short, paste-able install-only version is `INSTALL-PROMPT.md`; the full list of what
gets installed and why is `DEPENDENCIES.md`.

---

**To the agent:** you are setting up and then running a reel-editing kit for an editor who makes
short vertical videos for their clients. Read `CLAUDE.md` and `WORKFLOW.md` in this folder first.
Work in this folder only. Ask the editor before installing anything, and ask before any optional
step. Never run bare `hyperframes init` or `hyperframes skills update`. No API keys or paid
accounts are needed; if any step asks for one, stop and tell the editor.

## 1. Prerequisites (check, do not assume)

- macOS on Apple Silicon is recommended. On other systems the build, check and render work, but
  face fit, the background cutout and the demo voice (macOS `say`) do not.
- Claude Code (you are running in it).
- Homebrew, Node.js 22 or newer, ffmpeg + ffprobe, Python 3.9 or newer.

Check with: `sw_vers -productVersion; uname -m; brew --version; node --version; ffmpeg -version | head -1; python3 --version`
Missing tools: `brew install node ffmpeg python` (ask first).

## 2. Install, in this order

1. **Kit packages** (pinned GSAP and the captions helper):
   `npm install`
2. **HyperFrames plugin, project scope** (21 skills; run inside this folder):
   `claude plugin marketplace add heygen-com/hyperframes`
   `claude plugin install hyperframes@hyperframes --scope project`
   Then tell the editor to start a new Claude Code session in this folder (or run `/reload-plugins`)
   so the skills load. Do not copy the plugin's skills into `.claude/skills/`.
3. **HyperFrames CLI** (pinned; nothing to install, first run downloads a headless browser):
   `HYPERFRAMES_NO_TELEMETRY=1 npx --yes hyperframes@0.8.143 doctor`
4. **Speech engine, Parakeet** (about 640 MB, on-device):
   `HYPERFRAMES_NO_TELEMETRY=1 npx --yes hyperframes@0.8.143 models install parakeet`
   Fallback if Parakeet cannot be installed: `brew install whisper-cpp` (the `-e auto` engine
   choice then uses whisper.cpp).
5. **DeepFilterNet 0.5.6** (voice clean-up): download `deep-filter-0.5.6-aarch64-apple-darwin` from
   https://github.com/Rikorose/DeepFilterNet/releases/tag/v0.5.6, then
   `mkdir -p ~/.local/bin && mv <download> ~/.local/bin/deep-filter && chmod +x ~/.local/bin/deep-filter`
   (make sure `~/.local/bin` is on PATH, or set `DEEP_FILTER=<path>`). Check: `deep-filter --version`.
   macOS may block an unsigned download the first time; the editor allows it in System Settings,
   Privacy & Security.
6. **Optional, ask first: auto-editor 31.7.2** (silence pass): download `auto-editor-macos-arm64`
   from https://github.com/WyattBlue/auto-editor/releases/tag/31.7.2, check
   `shasum -a 256 <file>` equals `874310a405c88c4d06b9ee7b60b3a4e59ecbb09cfecd56ff54f1bf712b3b776e`,
   then move it to `~/.local/bin/auto-editor` and `chmod +x`. Check: `auto-editor --version`.
   Never install it with pip or uv (older version, missing flags).
7. **Optional, ask first, macOS: Xcode Command Line Tools** (face fit and cutout): `xcode-select --install`.
8. **Optional, ask first: cutout mask clean-up**: `python3 -m pip install --user numpy pillow`.

## 3. Verify the install (no client footage needed)

```bash
bash scripts/make-demo.sh                                   # synthetic clip: test pattern + text-to-speech
node scripts/build.mjs --input demo-synthetic --brand clients/_demo-test-only/brand.json --cues renders/demo.sfx-cues.json
HYPERFRAMES_NO_TELEMETRY=1 npx --yes hyperframes@0.8.143 check . --caption-zone "x0=.08;y0=.64;x1=.92;y1=.693;severity=error"
```
Pass = the build prints `wrote .../index.html` and check ends with `Check passed` and 0 errors
(one "track too dense" lint warning about the caption track is normal). Then:

- Speech engine: `HYPERFRAMES_NO_TELEMETRY=1 npx --yes hyperframes@0.8.143 transcribe demo-synthetic/face.mp4 -e auto --language en --dir renders/transcribe-test`
  then compare a few words of `renders/transcribe-test/transcript.json` with `demo-synthetic/SCRIPT.md`.
  (Never point `--dir` at `demo-synthetic/`: it would overwrite the demo transcript.)
- Stills, no render: `HYPERFRAMES_NO_TELEMETRY=1 npx --yes hyperframes@0.8.143 snapshot . --at 1.5,10.5,17.9,31 --describe false --output renders/snap`
  and look at the PNGs. Always `--describe false` (otherwise frames go to a paid API when a key is set).
- Hook lint: `python3 -I .claude/skills/reel-hook-check/scripts/hook_lint.py --shotlist demo-synthetic/shotlist.json --transcript demo-synthetic/transcript.json --min 25 --max 40`
  (one sentence-length flag on the demo script is expected).
- Optional full render (heavy; ask the editor first): `bash scripts/render.sh _demo-test-only demo-synthetic renders/demo-final --name demo-v1`

Report to the editor in plain words: what passed, what failed, what was skipped.

## 4. Onboard a new client

1. `cp -R clients/_example clients/<client-name>` (lowercase, dashes).
2. Run `DESIGN-INTERVIEW.md` with the editor: one question at a time, then it writes
   `clients/<client-name>/BRAND.md`, `brand.json` and `terms.txt`.
3. The editor adds the client's logo and licensed font files to that folder.
4. Check it: build the demo with the new brand and run the full check (contrast on):
   `node scripts/build.mjs --input demo-synthetic --brand clients/<client-name>/brand.json && HYPERFRAMES_NO_TELEMETRY=1 npx --yes hyperframes@0.8.143 check .`
   Any contrast failure: change the brand colour with the editor's OK, never the gate.
5. Show the editor a few `snapshot --describe false` stills of the demo in the new look before the
   first real video.

## 5. Every video, in order (details in WORKFLOW.md)

1. Client writes `videos/<client>/<slug>/SCRIPT.md`. Run `reel-shotlist` (draft) and
   `reel-hook-check`; flag a missing lock-in. Write `NEEDS.md` (captures, hold / look cues).
2. Client records the raw take (checklist in WORKFLOW.md section 3) into `recording/raw.mp4`.
3. Contact sheet of the take; rough cut (last take of each line, pauses over 0.3 s cut, never
   inside a word); speed 1.08x if the brand says so; DeepFilterNet; transcribe with word times;
   snap names to the script; face fit; optional cutout.
4. Finish the shot list on the real word times; build; check (0 errors).
5. Render both exports: `bash scripts/render.sh <client> videos/<client>/<slug>/input videos/<client>/<slug>/final --name <slug>-v1 [--music assets/music/<licensed bed>]`
6. `reel-safezone-qa`, `reel-audio-gate`, pick the cover, `reel-post` (POST.md, LOG.md).
7. Review loop: notes one per line with a time; next version `-v2`, earlier versions kept.
   Never post for the client.
