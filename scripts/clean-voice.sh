#!/bin/bash
# Cleans the voice of a take with DeepFilterNet, then puts it back under the same picture.
# Step 1 of the voice chain; the presence EQ, levelling and limiter happen later in the audio pass.
#
#   bash scripts/clean-voice.sh <in.mp4> <out.mp4> [deep-filter options, default -D -a 24]
#
# - Picture is copied bit for bit; only the audio changes (48 kHz mono voice -> DeepFilterNet ->
#   AAC 320k). DeepFilterNet adds no delay, so lips stay in sync.
# - Finds deep-filter on PATH, or set DEEP_FILTER=<path to the binary> (AGENT-SETUP.md installs it).
# - On a slow machine, scripts/remote/deepfilter-remote.sh runs the same step on a worker laptop.
set -euo pipefail
IN="${1:?usage: clean-voice.sh <in.mp4> <out.mp4> [deep-filter options]}"
OUT="${2:?usage: clean-voice.sh <in.mp4> <out.mp4> [deep-filter options]}"
shift 2
OPTS=("$@"); [[ ${#OPTS[@]} -gt 0 ]] || OPTS=(-D -a 24)
[[ -s "$IN" ]] || { echo "[clean-voice] not found: $IN" >&2; exit 1; }
[[ "$IN" != "$OUT" ]] || { echo "[clean-voice] write to a new file; never overwrite the input" >&2; exit 1; }
DFN="${DEEP_FILTER:-$(command -v deep-filter || true)}"
[[ -n "$DFN" && -x "$DFN" ]] || { echo "[clean-voice] DeepFilterNet (deep-filter) not found. Install it (AGENT-SETUP.md) or set DEEP_FILTER=<path>." >&2; exit 1; }
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
ffmpeg -v error -y -i "$IN" -vn -ac 1 -ar 48000 -c:a pcm_s16le "$TMP/voice.wav"
"$DFN" "${OPTS[@]}" -o "$TMP/out" "$TMP/voice.wav"
[[ -s "$TMP/out/voice.wav" ]] || { echo "[clean-voice] DeepFilterNet wrote no file" >&2; exit 1; }
ffmpeg -v error -y -i "$IN" -i "$TMP/out/voice.wav" -map 0:v:0 -map 1:a:0 -c:v copy -c:a aac -b:a 320k -ar 48000 -movflags +faststart "$OUT"
echo "[clean-voice] wrote $OUT (picture copied, voice cleaned with: deep-filter ${OPTS[*]})"
