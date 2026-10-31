# NOTICE: third-party software and content

The MIT licence in `LICENSE` covers only the original code and documents in this repository
(the build and audio scripts, the scene compositions, the skills, the docs). It does **not** cover
any third-party software, model, font, sound or library listed below. None of those are included
in this repository: each is installed from its own official source and stays under its own licence.

How each licence was confirmed: **on disk** = read from the installed package's own metadata on the
machine where the kit was assembled; **repo** = the project's licence file or its code host's
licence field; **not verified** = stated by the project but not checked by us.

| Component | Used for | Licence | Confirmed |
|---|---|---|---|
| HyperFrames (CLI `hyperframes` 0.8.143 and the Claude Code plugin `hyperframes@hyperframes` 0.8.143), https://github.com/heygen-com/hyperframes | composition, check, render, transcribe, snapshot; 21 agent skills | Apache-2.0 | on disk (npm `package.json`; plugin `plugin.json` and `LICENSE`) and repo |
| GSAP 3.15.0, https://gsap.com | scene animation | GSAP Standard "no charge" licence, https://gsap.com/standard-license | on disk (npm `package.json`). Not redistributed here: its terms grant use and reproduction for permitted uses but do not clearly allow redistributing the file in another repository, so it is installed from npm and copied at build time into a git-ignored folder. The licence also prohibits use in no-code visual animation builders that compete with Webflow; this kit is not one |
| @remotion/captions 4.0.534, https://www.npmjs.com/package/@remotion/captions | caption grouping helper | MIT | on disk (`package.json`). **Caveat:** the package ships no LICENSE file of its own, and the Remotion repository's root `LICENSE.md` is the separate Remotion License (free for individuals and small companies, a company licence above that), which does not list the MIT packages. The package's own MIT declaration is what applies to it, and this kit uses no other Remotion code. The original pipeline could not read Remotion's own licence page to confirm that MIT packages are exempt, so that sentence is unconfirmed. If this matters to you, the default big-word captions do not call the package and it can be removed |
| Parakeet TDT 0.6B v3, NVIDIA, https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3 | on-device transcription | CC-BY-4.0 (commercial use allowed) | repo (Hugging Face model metadata). The int8 ONNX files HyperFrames downloads come from the mirror `csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8`, which declares no licence of its own; it is described as a conversion of NVIDIA's v3, so it is taken to carry CC-BY-4.0 (not verified further). The weights stay on your machine and are not redistributed here. CC BY applies to the model, not to transcripts you make with it |
| sherpa-onnx-node 1.13.8, https://github.com/k2-fsa/sherpa-onnx | Parakeet runtime (installed by HyperFrames) | Apache-2.0 | repo and npm registry metadata |
| whisper.cpp 1.8.4, https://github.com/ggml-org/whisper.cpp | fallback transcription | MIT | on disk (Homebrew `LICENSE`). Whisper model weights: MIT per OpenAI's whisper repository (not verified) |
| DeepFilterNet 0.5.6, https://github.com/Rikorose/DeepFilterNet | voice noise clean-up | MIT OR Apache-2.0 | repo (`LICENSE`: "Licensed under either of"). The release binary has no licence metadata to read on disk |
| auto-editor 31.7.2, https://github.com/WyattBlue/auto-editor | silence pass (optional) | Unlicense (public domain) | repo. Its README says release binaries may bundle libraries under other open-source licences; not inspected |
| FFmpeg, https://ffmpeg.org | cutting, encoding, measuring | LGPL-2.1+ in general; the Homebrew build is GPL-3.0-or-later | on disk (`ffmpeg -L`). Called as a separate program; not redistributed here |
| numpy, Pillow | cutout mask clean-up (optional) | numpy BSD-3-Clause (with MIT, Zlib, CC0, 0BSD parts); Pillow MIT-CMU | on disk (package metadata) |
| Apple Vision, Swift (Xcode Command Line Tools) | face finding and person segmentation (optional, macOS) | Apple licence | not applicable (system frameworks) |
| Claude Code, https://docs.claude.com/en/docs/claude-code | the agent | Anthropic terms (not open source) | not applicable |
| watch@claude-video 0.2.0, https://github.com/bradautomates/claude-video | optional, not used by the kit | MIT | on disk (`plugin.json`) and repo |
| claude-video-vision 1.2.0, https://github.com/jordanrendric/claude-video-vision | optional, not used by the kit | MIT | on disk (`plugin.json`) and repo |

## Not included
- **Fonts:** none. Each client's fonts (and their licence files) live in that client's folder.
- **Sound effects and music:** none. Free SFX and music licences (for example the Pixabay Content
  License and the Mixkit free licences) allow use inside videos but not redistribution of the files.
  See `assets/sfx/README.md` and `assets/music/README.md`.
- **Logos, avatars, brand marks, tool logos, cutouts, real footage:** none. The demo footage is
  generated on your machine by `scripts/make-demo.sh` (an ffmpeg test pattern and text-to-speech).

## Methods
Parts of the script-checking method draw on public talks and posts by short-form creators about
hooks, lock-in lines and retention. No third-party text or code from those sources is included.

This notice is a plain reading of each licence, not legal advice.
