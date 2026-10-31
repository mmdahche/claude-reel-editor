# Standing rules for the agent (reel kit)

You build short vertical reels (1080x1920) for the editor's clients with this kit. Read
`WORKFLOW.md` before working on any video; it has the build steps in order and the format rules.
The skills in `.claude/skills/` (`reel-shotlist`, `reel-hook-check`, `reel-captions`,
`reel-audio-gate`, `reel-safezone-qa`, `reel-post`) hold the checklists for each step.

## Before any video
- Read the client's `clients/<client>/BRAND.md`. It wins over the defaults in WORKFLOW.md where
  they differ. No client folder yet? Run `DESIGN-INTERVIEW.md` with the editor first. The kit has
  no look of its own and the build refuses to run without the client's `brand.json`.
- `clients/_demo-test-only/` is for the install test only. Never use or copy it for a client.

## Hard rules
- Script first, then record, then build. The last take of each line is the one kept.
- Frame 0 shows b-roll and the face together. Never a title-only opening.
- Always two exports: with music and `-nomusic`. No outro unless the client asks.
- Versioned renders (`<slug>-v1`, `-v2` ...); never overwrite an earlier version. Never edit the
  client's raw footage; work on copies.
- Never post, schedule or reply on the client's behalf.
- Never call a paid tool or paid API (AI image/video generators, cloud transcription, a
  snapshot `--describe` call) without the editor's explicit yes for that video. Use
  `snapshot --describe false`.
- No music bed in a posted video without a licence row (`assets/music/README.md`). The kit ships no
  SFX, music, fonts, logos or GSAP file; never add third-party files to the repository.
- Never hand-edit the generated `index.html`. Never loosen a gate (check, contrast, loudness) to
  get a pass; fix the cause or tell the editor.
- One heavy job at a time (render, cutout, DeepFilterNet). Local is the default; the
  `scripts/remote/` worker wrappers are optional and need `scripts/remote/workers.conf`.
- Secrets never go in this repository or in chat. No API keys are needed for the default pipeline.

## HyperFrames
- HyperFrames is a Claude Code plugin installed at **project** scope (see `AGENT-SETUP.md`). Its
  skills load from the plugin; never copy them into `.claude/skills/`.
- **Never run bare `hyperframes init` or `hyperframes skills update`, and never let a skill run
  them.** They write into the user's `~/.claude/` folder. Plugin updates go through the plugin
  manager only.
- CLI work always uses the pinned form from the kit folder:
  `HYPERFRAMES_NO_TELEMETRY=1 npx --yes hyperframes@0.8.143 <command>`.
- If the pin ever changes, change it everywhere in one go (`package.json`, the `HF=` line of
  `scripts/render.sh`, the docs and skills) and re-run the install check.
- On any failure, run `... hyperframes@0.8.143 doctor` first.

## Talking to the editor
Plain English, short. Lead with the outcome, end with the next step. Put tables, logs and numbers
in files (`LOG.md`, `review/`) and point to them in one sentence. Say plainly what was not checked.
