#!/bin/bash
# Speeds a whole take up (default 1.08x: picture and voice together, pitch kept), re-encoded at
# 30 fps. Run it on the clean cut, BEFORE cleaning the voice and transcribing, so every word time
# comes from the sped-up file. Optional; the default 1.08x reads a little tighter without
# sounding rushed. Skip it (or use 1.0) if the client speaks fast already.
#
#   bash scripts/speed.sh <in.mp4> <out.mp4> [factor]      factor 0.5-2.0, default 1.08
#
# HDR/HLG phone takes keep their colour tags and 10-bit depth, so the render's SDR tone-map
# still sees them.
set -euo pipefail
IN="${1:?usage: speed.sh <in.mp4> <out.mp4> [factor]}"
OUT="${2:?usage: speed.sh <in.mp4> <out.mp4> [factor]}"
F="${3:-1.08}"
[[ -s "$IN" ]] || { echo "[speed] not found: $IN" >&2; exit 1; }
[[ "$IN" != "$OUT" ]] || { echo "[speed] write to a new file; never overwrite the input" >&2; exit 1; }
awk -v f="$F" 'BEGIN { exit !(f >= 0.5 && f <= 2.0) }' || { echo "[speed] factor must be 0.5-2.0" >&2; exit 1; }
probe() { ffprobe -v error -select_streams v:0 -show_entries "stream=$1" -of default=nw=1:nk=1 "$IN" | head -1; }
PIX="$(probe pix_fmt)"; PRIM="$(probe color_primaries)"; TRC="$(probe color_transfer)"; SPACE="$(probe color_space)"
FMT=yuv420p; PROFILE=high
[[ "$PIX" == *10* ]] && { FMT=yuv420p10le; PROFILE=high10; }
TAGS=()
[[ -n "${PRIM:-}" && "$PRIM" != "unknown" ]] && TAGS+=(-color_primaries "$PRIM")
[[ -n "${TRC:-}" && "$TRC" != "unknown" ]] && TAGS+=(-color_trc "$TRC")
[[ -n "${SPACE:-}" && "$SPACE" != "unknown" ]] && TAGS+=(-colorspace "$SPACE")
ffmpeg -v error -y -i "$IN" -filter_complex "[0:v]setpts=PTS/$F,fps=30[v];[0:a]atempo=$F[a]" -map "[v]" -map "[a]" \
  -c:v libx264 -profile:v "$PROFILE" -preset medium -crf 14 -pix_fmt "$FMT" -g 30 ${TAGS[@]+"${TAGS[@]}"} \
  -c:a aac -b:a 320k -ar 48000 -movflags +faststart "$OUT"
echo "[speed] wrote $OUT at ${F}x ($(ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT") s)"
