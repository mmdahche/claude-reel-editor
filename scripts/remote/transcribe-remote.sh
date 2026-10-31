#!/bin/bash
# OPTIONAL. The transcribe step on a worker laptop instead of this Mac (local is the default:
# see WORKFLOW.md). Run from the kit folder:
#
#   bash scripts/remote/transcribe-remote.sh <media> <dir> [more hyperframes transcribe options]
#
# Runs on the worker, in its copy of the folder you are in:
#   npx --yes hyperframes@<pin> transcribe <media> --dir <dir> [options; default: -e auto --language en]
# then copies <dir>/transcript.json back here, overwriting the one here (back it up first).
#
# - The pin is read from the HF= line of scripts/render.sh, so it never drifts.
# - The worker needs its own speech engine: `hyperframes models install parakeet` run there once,
#   or whisper.cpp on its PATH. Optional: WHISPER_BUNDLE=<folder holding a whisper-cli launcher>
#   is copied along and used, with --no-runtime-install so hyperframes never tries to install
#   anything on the worker.
# Env: WHISPER_BUNDLE, plus WORKER, WORKERS_CONF, WORKER_KIT_DIR, REMOTE_JOB as in run-on-worker.sh.
# Exit codes: as run-on-worker.sh.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd -P)"
RUN="$ROOT/scripts/remote/run-on-worker.sh"
die() { echo "[transcribe-remote] $*" >&2; exit 64; }

[[ $# -ge 2 ]] || die "usage: transcribe-remote.sh <media> <dir> [more hyperframes transcribe options]"
MEDIA="$1"; DIR="$2"; shift 2
[[ -f "$MEDIA" ]] || die "media not found: $MEDIA"
[[ -d "$DIR" ]] || die "folder not found: $DIR"
OPTS=("$@"); [[ ${#OPTS[@]} -gt 0 ]] || OPTS=(-e auto --language en)

PIN="$(sed -n 's/^HF=(npx --yes \(hyperframes@[0-9][0-9.]*\))$/\1/p' "$ROOT/scripts/render.sh" | head -1)"
[[ -n "$PIN" ]] || die "could not read the hyperframes pin from the HF= line of scripts/render.sh"

if [[ -n "${WHISPER_BUNDLE:-}" ]]; then
  [[ -x "$WHISPER_BUNDLE/whisper-cli" ]] || die "WHISPER_BUNDLE has no executable whisper-cli: $WHISPER_BUNDLE"
  exec bash "$RUN" --name transcribe --need node --need npx --need ffmpeg \
    --in "$MEDIA" --in "$WHISPER_BUNDLE" --out "${DIR%/}/transcript.json" -- \
    env HYPERFRAMES_NO_TELEMETRY=1 "HYPERFRAMES_WHISPER_PATH=$WHISPER_BUNDLE/whisper-cli" \
    npx --yes "$PIN" transcribe "$MEDIA" --dir "$DIR" --no-runtime-install "${OPTS[@]}"
fi
exec bash "$RUN" --name transcribe --need node --need npx --need ffmpeg \
  --in "$MEDIA" --out "${DIR%/}/transcript.json" -- \
  env HYPERFRAMES_NO_TELEMETRY=1 npx --yes "$PIN" transcribe "$MEDIA" --dir "$DIR" "${OPTS[@]}"
