#!/bin/bash
# OPTIONAL, macOS worker only. The Apple Vision person segmentation step of scripts/cutout/cutout.sh
# on a worker laptop instead of this Mac. Run from the kit folder:
#
#   bash scripts/remote/seg-remote.sh <frames dir> <masks dir>
#
# Copies scripts/cutout/seg.swift and the frames (.png/.jpg, e.g. cutout.sh's <work>/frames) to the
# worker, compiles seg.swift there with the Command Line Tools' swiftc -O (cached by content in
# ~/render-remote/cache/ on the worker, so each version compiles once), runs `seg <frames> <masks>`,
# and copies the masks folder back. Same files as cutout.sh's step 2 on this Mac. Then run
# process_masks.py and the merge (cutout.sh steps 3-4) here.
# Env: WORKER, WORKERS_CONF, WORKER_KIT_DIR, REMOTE_JOB as in run-on-worker.sh. Exit codes: as run-on-worker.sh.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd -P)"
RUN="$ROOT/scripts/remote/run-on-worker.sh"
SWIFT="$ROOT/scripts/cutout/seg.swift"
die() { echo "[seg-remote] $*" >&2; exit 64; }

[[ $# -eq 2 ]] || die "usage: seg-remote.sh <frames dir> <masks dir>"
FRAMES="${1%/}"; MASKS="${2%/}"
[[ -f "$SWIFT" ]] || die "missing $SWIFT"
[[ -d "$FRAMES" ]] || die "frames folder not found: $FRAMES"
[[ -n "$(find "$FRAMES" -maxdepth 1 \( -name '*.png' -o -name '*.jpg' \) -print -quit)" ]] || die "no .png or .jpg frames in $FRAMES"

# $1 seg.swift, $2 frames, $3 masks (all rewritten to the worker's copies by run-on-worker.sh)
COMPILE_AND_RUN='set -e
b="$HOME/render-remote/cache/seg-$(shasum -a 256 "$1" | cut -c1-16)"
if [ ! -x "$b" ]; then
  mkdir -p "${b%/*}"
  echo "[seg-remote] compiling $(basename "$1") with $(swiftc --version 2>&1 | head -1)"
  swiftc -O "$1" -o "$b.tmp.$$" && mv "$b.tmp.$$" "$b"
fi
mkdir -p "$3"
exec "$b" "$2" "$3"'

# what to run on this Mac instead
B="$ROOT/scripts/cutout/.bin/seg"
LOCAL="mkdir -p $(printf '%q' "${B%/*}") $(printf '%q' "$MASKS") && swiftc -O $(printf '%q' "$SWIFT") -o $(printf '%q' "$B") && nice -n 10 $(printf '%q' "$B") $(printf '%q' "$FRAMES") $(printf '%q' "$MASKS")"

exec bash "$RUN" --name seg --need swiftc --need shasum --local "(cd $(printf '%q' "$(pwd -P)") && $LOCAL)" \
  --in "$SWIFT" --in "$FRAMES" --out "$MASKS/" -- \
  bash -c "$COMPILE_AND_RUN" seg "$SWIFT" "$FRAMES" "$MASKS"
