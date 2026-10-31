# claude-reel-kit

A Claude Code setup that edits short vertical videos (Reels, TikTok, Shorts) from a person talking
to camera. Your client records a raw take of their script; your Claude Code agent cuts the pauses,
finds retakes and false starts against the script, shows you the cut before it builds anything,
cleans the voice, transcribes it word by word, lines graphics up with the voice, burns
in captions, adds sound effects and a music bed, masters the loudness, and hands back a finished
1080x1920 video in two versions: with music and without.

It keeps a separate look for each of your clients, and it ships no look of its own: an interview
with your agent sets up each client's colours, fonts, caption style and sound.

## What it does
- Plans the video from the script (beats, scenes, layout) and checks the hook's structure.
- Rough-cuts the raw take: cuts long pauses, never inside a word, and marks retakes and false starts
  against the script so the last take of each line is kept. Check the cut before the build; the
  automatic retake tool (`scripts/retake_ranges.py`) is new and not yet proven on real footage.
- Builds the picture with HyperFrames: scenes, the face, real footage as a split or a card, captions
  on a fixed line inside every app's safe zone.
- Mixes and masters the sound, renders both exports, checks safe zones and loudness, and writes
  the post caption and a log. It never posts for you.

## What you need
- A Mac with Apple Silicon (recommended; a few steps are macOS-only).
- Claude Code, Node.js 22+, ffmpeg, Python 3. Free, on-device tools for the rest (full list in
  `DEPENDENCIES.md`). No API keys, no paid accounts.
- Your own licensed sound effects, music and client fonts (the kit cannot redistribute them).

## Start here
1. Open Claude Code in this folder and paste `INSTALL-PROMPT.md`. It installs and checks everything,
   asking before each optional piece.
2. Paste `DESIGN-INTERVIEW.md` to set up your first client's look.
3. Hand your agent `AGENT-SETUP.md`; it walks every video from script to finished file.

| File | For |
|---|---|
| `INSTALL-PROMPT.md` | one prompt that installs and verifies everything |
| `DESIGN-INTERVIEW.md` | one prompt that interviews you about a client's brand and writes its files |
| `AGENT-SETUP.md` | the full hand-off for your agent: install, verify, onboard a client, each video |
| `WORKFLOW.md` | the method, step by step, and the format rules |
| `DEPENDENCIES.md` | every tool, plugin and model, with sources, versions and licences |
| `NOTICE.md` | third-party licences |

Made by @aiwithmurda
