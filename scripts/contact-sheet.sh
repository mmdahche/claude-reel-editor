#!/bin/bash
# Labelled contact sheet: one row per video, the same moments in each row.
#   bash scripts/contact-sheet.sh <out.jpg> <video.mp4>...
# Env: TIMES="0.9 2.3 3.8 6.5 16.3 23.5"   moments in seconds (default: six, evenly spread over the
#                                          first video)
#      LABELS="hook|split|..."               one label per moment (default: the time)
#      FONT=<path to a .ttf>                 label font (default: a macOS system font; no labels
#                                            if none is found)
# For a quick look at a raw take instead (one frame per second), use:
#   ffmpeg -v error -y -i <raw.mp4> -vf "fps=1,scale=160:-1,tile=12x10" -frames:v 1 contact-sheet.jpg
set -euo pipefail
OUT="${1:?usage: contact-sheet.sh <out.jpg> <video.mp4>...}"; shift
[[ $# -ge 1 ]] || { echo "need at least one mp4" >&2; exit 1; }
for MP4 in "$@"; do [[ -s "$MP4" ]] || { echo "missing $MP4" >&2; exit 1; }; done
if [[ -z "${TIMES:-}" ]]; then
  DUR="$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$1")"
  TIMES="$(awk -v d="$DUR" 'BEGIN { for (i = 0; i < 6; i++) printf "%.2f ", d * (i + 0.5) / 6 }')"
fi
read -r -a T <<< "$TIMES"
IFS='|' read -r -a LABELS <<< "${LABELS:-}"
FONT="${FONT:-}"
if [[ -z "$FONT" ]]; then
  for f in /System/Library/Fonts/Supplemental/Arial.ttf /Library/Fonts/Arial.ttf /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf; do
    [[ -f "$f" ]] && { FONT="$f"; break; }
  done
fi
label() { # <text> <x> <y> <size>: a drawtext filter, or nothing when no font is available
  [[ -n "$FONT" ]] || return 0
  printf ',drawtext=fontfile=%s:text=%s:x=%s:y=%s:fontsize=%s:fontcolor=0xdddddd' "$FONT" "'$1'" "$2" "$3" "$4"
}
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
W=270; H=480; LABW=300; BG=0x202020

rows=(); r=0
for MP4 in "$@"; do
  NAME="$(basename "$MP4" .mp4)"
  ins=()
  ffmpeg -v error -y -f lavfi -i "color=c=$BG:s=${LABW}x$((H + 40))" -frames:v 1 \
    -vf "null$(label "${NAME//[-_:\']/ }" 18 40 21)" "$TMP/l$r.png"
  ins+=(-i "$TMP/l$r.png")
  for i in "${!T[@]}"; do
    t="${T[$i]}"; lab="${LABELS[$i]:-${t}s}"
    ffmpeg -v error -y -ss "$t" -i "$MP4" -frames:v 1 \
      -vf "scale=${W}:${H},pad=${W}:$((H + 40)):0:40:color=$BG$(label "${lab//[:\']/ }" 8 12 16)" "$TMP/r${r}_$i.png"
    ins+=(-i "$TMP/r${r}_$i.png")
  done
  ffmpeg -v error -y "${ins[@]}" -filter_complex "hstack=inputs=$(( ${#T[@]} + 1 ))" "$TMP/row$r.png"
  rows+=(-i "$TMP/row$r.png")
  r=$((r + 1))
done
if [[ $r -gt 1 ]]; then
  ffmpeg -v error -y "${rows[@]}" -filter_complex "vstack=inputs=$r" -q:v 3 "$OUT"
else
  ffmpeg -v error -y "${rows[@]}" -q:v 3 "$OUT"
fi
echo "[contact-sheet] wrote $OUT"
