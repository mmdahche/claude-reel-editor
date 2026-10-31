#!/bin/bash
# OPTIONAL. DeepFilterNet voice clean-up (`deep-filter -D -a 24` on a 48 kHz mono wav) on a worker
# laptop instead of this Mac (local is the default: scripts/clean-voice.sh). Run from the kit folder:
#
#   bash scripts/remote/deepfilter-remote.sh <voice.wav> <out dir> [deep-filter options, default -D -a 24]
#
# Copies the wav and the deep-filter binary (DEEP_FILTER=<path>, else the one on PATH; it is a
# self-contained binary) to the worker, runs it there, and copies <out dir>/<same file name>
# back: the same file `deep-filter -o <out dir> <voice.wav>` writes here. Mux it back under the
# picture as scripts/clean-voice.sh does.
# Env: DEEP_FILTER, plus WORKER, WORKERS_CONF, WORKER_KIT_DIR, REMOTE_JOB as in run-on-worker.sh.
# Exit codes: as run-on-worker.sh.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd -P)"
RUN="$ROOT/scripts/remote/run-on-worker.sh"
DFN="${DEEP_FILTER:-$(command -v deep-filter || true)}"
die() { echo "[deepfilter-remote] $*" >&2; exit 64; }

[[ $# -ge 2 ]] || die "usage: deepfilter-remote.sh <voice.wav> <out dir> [deep-filter options, default -D -a 24]"
WAV="$1"; OUT="${2%/}"; shift 2
[[ -f "$WAV" ]] || die "wav not found: $WAV"
[[ -n "$DFN" && -x "$DFN" ]] || die "DeepFilterNet not found (set DEEP_FILTER=<path to deep-filter>)"
OPTS=("$@"); [[ ${#OPTS[@]} -gt 0 ]] || OPTS=(-D -a 24)

exec bash "$RUN" --name deep-filter --in "$DFN" --in "$WAV" --out "$OUT/$(basename "$WAV")" -- \
  "$DFN" "${OPTS[@]}" -o "$OUT" "$WAV"
