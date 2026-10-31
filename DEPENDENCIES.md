# Dependencies: everything the pipeline uses

Every outside tool, package, plugin and model the kit calls on, with where it comes from, how to
install it, the version the kit was built and checked with, its licence, and whether you need it.
Nothing here is copied into the kit: each item is installed from its own official source.
No item needs an API key or a paid account for the default pipeline.

"Checked with" is the version on the machine where the kit was assembled. "Licence" says how it was
confirmed: **on disk** (the package's own metadata on that machine), **repo** (the project's
licence file or the code host's licence field), or **not verified** (said plainly).

## Required

| # | What | Does in the pipeline | Official source | Install | Checked with | Licence |
|---|---|---|---|---|---|---|
| 1 | macOS on Apple Silicon (recommended) | everything; face fit, cutout and the demo voice are macOS-only | apple.com | - | macOS 27, Apple M4 | Apple licence |
| 2 | Claude Code | the agent that runs the workflow and the skills | https://docs.claude.com/en/docs/claude-code/setup | follow the official setup page (for example `npm install -g @anthropic-ai/claude-code`) | 2.1.314 | Anthropic commercial terms (not open source) |
| 3 | Homebrew | installs ffmpeg and whisper.cpp | https://brew.sh | the one-line installer on brew.sh | 7.0.10 | BSD-2-Clause (repo, not verified on disk) |
| 4 | Node.js (with npm and npx) | runs the build, the audio pass and the HyperFrames CLI | https://nodejs.org | `brew install node` (HyperFrames needs Node 22 or newer) | 26.4.0 | MIT (not verified on disk) |
| 5 | ffmpeg + ffprobe | every cut, encode, measurement and the master. Needs libx264, libvpx-vp9, libopus, zscale, drawtext: the Homebrew build has all of them | https://ffmpeg.org | `brew install ffmpeg` | 8.1 | GPL-3.0-or-later for this build (on disk: `ffmpeg -L`) |
| 6 | Python 3 | rough cut, name snapping, face fit, lint, SRT (standard library only) | https://www.python.org | preinstalled on macOS, or `brew install python` | 3.14.4 (3.9+ works) | PSF licence (not verified on disk) |
| 7 | HyperFrames Claude Code plugin `hyperframes@hyperframes` | 21 skills that teach the agent HyperFrames compositions, captions, audio and QA (`embedded-captions`, `faceless-explainer`, `figma`, `general-video`, `hyperframes`, `hyperframes-animation`, `hyperframes-audio`, `hyperframes-cli`, `hyperframes-core`, `hyperframes-creative`, `hyperframes-keyframes`, `hyperframes-registry`, `hyperframes-studio`, `media-use`, `motion-graphics`, `music-to-video`, `pr-to-video`, `product-launch-video`, `remotion-to-hyperframes`, `slideshow`, `talking-head-recut`) | https://github.com/heygen-com/hyperframes | in the kit folder: `claude plugin marketplace add heygen-com/hyperframes` then `claude plugin install hyperframes@hyperframes --scope project` | 0.8.143 | Apache-2.0 (on disk: the plugin's `plugin.json` and `LICENSE`) |
| 8 | HyperFrames CLI | `check`, `render`, `transcribe`, `snapshot`, `doctor`, `models` | https://github.com/heygen-com/hyperframes (npm package `hyperframes`) | no install: always `HYPERFRAMES_NO_TELEMETRY=1 npx --yes hyperframes@0.8.143 <command>`. First use downloads a headless browser and caches into `~/.cache/hyperframes` | 0.8.143 (pinned) | Apache-2.0 (on disk: the npm `package.json`) |
| 9 | npm package `gsap` | the animation library every scene uses; copied into `assets/vendor/` at build time | https://gsap.com (npm `gsap`) | `npm install` in the kit folder (pinned in `package.json`) | 3.15.0 (exact pin) | GSAP Standard "no charge" licence, https://gsap.com/standard-license (on disk: the npm `package.json`) |
| 10 | npm package `@remotion/captions` | caption-grouping helper kept from the original pipeline (the default big-word style does not call it) | https://www.npmjs.com/package/@remotion/captions | `npm install` (pinned in `package.json`) | 4.0.534 (exact pin) | MIT (on disk: its `package.json`); see the caveat in NOTICE.md |
| 11 | A local speech engine: **Parakeet TDT 0.6B v3 (int8)** | word-level transcripts on the device (25 European languages) | model: https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3 ; files come from the int8 ONNX mirror `csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8` (pinned revision `2bda32ec70b097a55adaa07d9a7173915b43cc78`, each file sha256-checked by HyperFrames) ; runtime `sherpa-onnx-node` https://github.com/k2-fsa/sherpa-onnx | `HYPERFRAMES_NO_TELEMETRY=1 npx --yes hyperframes@0.8.143 models install parakeet` (about 640 MB into `~/.cache/hyperframes/parakeet/`) | model v3 int8, runtime `sherpa-onnx-node` 1.13.8 | model CC-BY-4.0 (Hugging Face model metadata); runtime Apache-2.0 (npm registry metadata); **the mirror repo declares no licence of its own** (not verified beyond "converted from NVIDIA v3") |
| 11b | ... or **whisper.cpp** (fallback engine) | same job when Parakeet is not installed (`-e auto` picks it); its word times can run late, so check a few | https://github.com/ggml-org/whisper.cpp | `brew install whisper-cpp`; the `small.en` model (about 490 MB) downloads on first use | 1.8.4 | MIT (on disk: Homebrew `LICENSE`). Whisper model weights: MIT per OpenAI's whisper repository (not verified on disk) |
| 12 | DeepFilterNet (`deep-filter` binary) | first step of the voice chain: removes room noise without dulling the voice | https://github.com/Rikorose/DeepFilterNet (release v0.5.6) | download `deep-filter-0.5.6-aarch64-apple-darwin` from the v0.5.6 release, rename to `deep-filter`, `chmod +x`, put it on your PATH (for example `~/.local/bin/`), or set `DEEP_FILTER=<path>` | 0.5.6 | MIT OR Apache-2.0 (repo `LICENSE`: "Licensed under either of"). The release binary carries no licence metadata of its own |

Without #12 the pipeline still runs (skip `scripts/clean-voice.sh`); the voice just keeps its room noise.

## Optional

| # | What | Does | Official source | Install | Checked with | Licence |
|---|---|---|---|---|---|---|
| 13 | auto-editor | silence pass after the retake cut (removes pauses over 0.3 s) | https://github.com/WyattBlue/auto-editor (release 31.7.2) | download `auto-editor-macos-arm64` from the 31.7.2 release, check its sha256 against the digest shown on the release (`874310a405c88c4d06b9ee7b60b3a4e59ecbb09cfecd56ff54f1bf712b3b776e` for 31.7.2), rename to `auto-editor`, `chmod +x`, put it on your PATH. Do not use `pip`/`uv tool install` (they install an older version without the flags the workflow uses) | 31.7.2 | Unlicense (repo); the README notes release binaries may bundle libraries under other open-source licences (not inspected) |
| 14 | Xcode Command Line Tools (`swiftc`) | compiles the two Apple Vision helpers: eye finding for face fit, person segmentation for the cutout | https://developer.apple.com/xcode/resources/ | `xcode-select --install` | Apple Swift 6.4 | Apple licence |
| 15 | numpy + Pillow | mask clean-up in the background cutout (`scripts/cutout/process_masks.py`) | https://numpy.org , https://python-pillow.org | `python3 -m pip install --user numpy pillow` | numpy 2.4.4, Pillow 12.2.0 | numpy BSD-3-Clause (plus bundled MIT, Zlib, CC0, 0BSD parts), Pillow MIT-CMU (on disk: package metadata) |
| 16 | macOS `say` | the text-to-speech voice of the synthetic demo | built into macOS | - | macOS 27 | Apple licence. Without it the demo uses tones |
| 17 | A second Mac as a worker laptop (ssh, rsync) | offloads renders, cutout, DeepFilterNet and transcription (`scripts/remote/`) | built into macOS (Remote Login) | see `scripts/remote/workers.conf.example` | - | - |
| 18 | `faster-whisper` (Python) | a second opinion on word times when the main engine drifts on a noisy take | https://github.com/SYSTRAN/faster-whisper | `python3 -m pip install --user faster-whisper` | not installed on the build machine (the original pipeline used it once, offline, with a cached small model) | MIT (repo, not verified on disk) |
| 19 | Claude Code plugin `watch@claude-video` | lets the agent watch a reference video by URL | https://github.com/bradautomates/claude-video | `claude plugin marketplace add bradautomates/claude-video` then `claude plugin install watch@claude-video` | 0.2.0 | MIT (on disk: `plugin.json`). **Cost note:** for videos without captions it falls back to a cloud Whisper API that needs a key and bills per use; it also installs yt-dlp via Homebrew on first run. Never use it on client footage. Not used by any kit step |
| 20 | Claude Code plugin `claude-video-vision` | frames + audio perception of a video | https://github.com/jordanrendric/claude-video-vision | `claude plugin marketplace add https://github.com/jordanrendric/claude-video-vision.git` then `claude plugin install claude-video-vision@claude-video-vision` | 1.2.0 | MIT (on disk: `plugin.json`). **Cost note:** offers Gemini and OpenAI backends (keys, possible charges) besides local Whisper; choose local. Not used by any kit step |
| 21 | Paid AI image/video generators (any vendor's CLI, MCP server or skills) | the rare paid "hero shot" | the vendor | the vendor's instructions | not used by default | vendor terms, paid. Only with the editor's explicit yes per video (WORKFLOW.md section 6) |

## Not shipped, supplied by you

| What | Why not shipped | Where to get it |
|---|---|---|
| Sound effects (whoosh, tick, pop, thud, keys) | free SFX licences do not allow handing out the files themselves | `assets/sfx/README.md` |
| Music beds | same for free music licences | `assets/music/README.md` |
| Fonts | no default look; each client's fonts and licences live in its own folder | `assets/fonts/README.md` |
| Logos, avatars, brand marks | client property | `clients/<client>/` |

## Install-time side effects to know about
- HyperFrames caches a headless browser, fonts and speech models under `~/.cache/hyperframes`
  (more than 1 GB with Parakeet and a Whisper model). Check free disk space first.
- The plugin install writes to the kit's `.claude/settings.json` (project scope) and Claude Code's
  own plugin cache. It does not need `hyperframes init` or `hyperframes skills update`; never run those.
- `npm install` creates `node_modules/` in the kit folder (git-ignored).

## Pins and updates
- The HyperFrames CLI pin (0.8.143) lives in `package.json`, the `HF=` line of `scripts/render.sh`,
  and the docs and skills. Change them together, then re-run the install check in `AGENT-SETUP.md`.
- The plugin manager installs the plugin's current version; the kit was checked with 0.8.143. If a
  newer plugin version is installed, the pinned CLI still drives every build and render. Whether
  `claude plugin install` accepts a version pin was not confirmed, so this is not enforced.
