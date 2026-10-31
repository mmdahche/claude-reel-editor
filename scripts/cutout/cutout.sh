#!/bin/bash
# macOS ONLY. Removes the background behind the speaker with Apple Vision person segmentation and
# writes a VP9 WebM with alpha that the build can stand "free" on the stage (shot list
# "face": {"free": {...}}). Optional: skip it and the face sits in the face box as usual.
#
#   bash scripts/cutout/cutout.sh <face.mp4> <out.webm> <work dir> [process_masks.py options]
#
# Steps (all local; the Vision pass can run on a worker with scripts/remote/seg-remote.sh):
#   1. frames: every frame as JPEG; HDR/HLG takes are tone-mapped to SDR first with the same
#      hable curve the renderer uses, so the colours match the rest of the reel
#   2. seg.swift: one person mask per frame (Vision, "accurate"), compiled once with swiftc
#   3. process_masks.py: temporal median, levels, choke, feather, solid bottom rows (needs numpy
#      and Pillow). Tune problems with its options, never by hand.
#   4. merge: VP9 yuva420p WebM (alpha_mode=1), keyframe every second, Opus voice delayed by
#      exactly 960 samples, because ffmpeg's input seek (which the renderer uses) shifts
#      Opus-in-WebM 20 ms early.
# Disk: the work dir holds every frame as JPEG plus two sets of masks (roughly 0.5-1 GB per
# minute at 1080x1920). It is not deleted, so a step can be re-run; delete it when done.
# Heavy job: about a minute of compute per minute of footage on a recent Apple Silicon Mac.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
IN="${1:?usage: cutout.sh <face.mp4> <out.webm> <work dir> [process_masks options]}"
OUT="${2:?usage: cutout.sh <face.mp4> <out.webm> <work dir> [process_masks options]}"
WORK="${3:?usage: cutout.sh <face.mp4> <out.webm> <work dir> [process_masks options]}"
shift 3
[[ "$(uname)" == "Darwin" ]] || { echo "[cutout] macOS only (Apple Vision). Skip this step on other systems." >&2; exit 1; }
command -v swiftc >/dev/null || { echo "[cutout] swiftc not found: install the Xcode Command Line Tools (xcode-select --install)" >&2; exit 1; }
python3 -c "import numpy, PIL" 2>/dev/null || { echo "[cutout] process_masks.py needs numpy and Pillow (python3 -m pip install numpy pillow)" >&2; exit 1; }
[[ -s "$IN" ]] || { echo "[cutout] not found: $IN" >&2; exit 1; }
mkdir -p "$WORK/frames" "$WORK/masks" "$WORK/masks-clean" "$HERE/.bin"

TRC="$(ffprobe -v error -select_streams v:0 -show_entries stream=color_transfer -of csv=p=0 "$IN")"
VF="format=yuvj420p"
if [[ "$TRC" == "arib-std-b67" || "$TRC" == "smpte2084" ]]; then
  echo "[cutout] HDR take ($TRC): tone-mapping to SDR"
  VF="zscale=t=linear:npl=100,tonemap=hable:desat=0,zscale=p=bt709:t=bt709:m=bt709:r=tv,format=yuvj420p"
fi
echo "[cutout] 1/4 frames"
ffmpeg -v error -y -i "$IN" -vf "fps=30,$VF" -q:v 2 "$WORK/frames/f_%05d.jpg"

BIN="$HERE/.bin/seg"
if [[ ! -x "$BIN" || "$HERE/seg.swift" -nt "$BIN" ]]; then
  echo "[cutout] compiling seg.swift"
  swiftc -O "$HERE/seg.swift" -o "$BIN"
fi
echo "[cutout] 2/4 Vision masks ($(ls "$WORK/frames" | wc -l | tr -d ' ') frames)"
nice -n 10 "$BIN" "$WORK/frames" "$WORK/masks"

echo "[cutout] 3/4 mask clean-up"
python3 "$HERE/process_masks.py" "$WORK/masks" "$WORK/masks-clean" "$@"

echo "[cutout] 4/4 merge to WebM with alpha"
AUDIO=(-an)
if ffprobe -v error -select_streams a:0 -show_entries stream=index -of csv=p=0 "$IN" | grep -q .; then
  AUDIO=(-map 2:a:0 -af "aresample=48000,adelay=delays=960S:all=1" -c:a libopus -b:a 192k)
fi
ffmpeg -v error -y -framerate 30 -i "$WORK/frames/f_%05d.jpg" -framerate 30 -i "$WORK/masks-clean/f_%05d.png" -i "$IN" \
  -filter_complex "[1:v]format=gray,scale=iw:ih[m];[0:v][m]alphamerge,format=yuva420p[v]" -map "[v]" "${AUDIO[@]}" \
  -c:v libvpx-vp9 -pix_fmt yuva420p -crf 18 -b:v 0 -g 30 -row-mt 1 \
  -color_primaries bt709 -color_trc bt709 -colorspace bt709 -metadata:s:v:0 alpha_mode=1 "$OUT"
echo "[cutout] wrote $OUT (alpha_mode=$(ffprobe -v error -select_streams v:0 -show_entries stream_tags=alpha_mode -of csv=p=0 "$OUT"))"
echo "[cutout] next: set the recording src to this file and measure face.free values per run (WORKFLOW.md)"
