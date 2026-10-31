# INSTALL-PROMPT

Open Claude Code in this kit folder, then copy everything inside the box below and paste it as
your first message.

---

```text
Set up this reel-editing kit on my machine. Work only inside this folder.

First read CLAUDE.md, DEPENDENCIES.md and AGENT-SETUP.md here. DEPENDENCIES.md is the list of
everything to install, with official sources and pinned versions. Install only from those sources.

Rules while you do this:
- Go in order. Tell me in one plain sentence what each step installs before you run it.
- REQUIRED items (DEPENDENCIES.md "Required", numbers 1-12): install and verify each one, in order.
  If one is already installed, check its version against the "Checked with" column and tell me if it
  differs. If an install fails, stop, tell me what failed and what you suggest. Do not try a third
  approach without asking me.
- OPTIONAL items (numbers 13-21): ask me before each one, one question at a time, and say what it
  is for. Skip anything I say no to. Never install the paid generators (21) or the video-watching
  plugins (19, 20) unless I ask for them by name.
- Never run bare `hyperframes init` or `hyperframes skills update`. Install HyperFrames only as the
  project-scoped plugin plus the pinned `npx --yes hyperframes@0.8.143` command.
- Never ask me for, or store, API keys, tokens or passwords. None are needed. If a step asks for
  one, stop and tell me.
- Do not change anything in my home folder except what the official installers write (Homebrew,
  ~/.local/bin for the two release binaries, the HyperFrames cache). Do not edit my shell profile
  without asking.

After installing, run the verify steps in AGENT-SETUP.md section 3 (synthetic demo, build, check,
transcribe test, snapshot with --describe false, hook lint). Do NOT run the full render unless I
say yes.

Finish with a short plain-English report:
1. Each required item: passed / failed / version found.
2. Each optional item: installed / skipped (my choice) / failed.
3. The check result (number of errors).
4. Anything that did not work, and the one next step you suggest.
```
