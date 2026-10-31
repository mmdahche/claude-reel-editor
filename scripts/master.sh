#!/bin/bash
# Linear master + final encode for one export.
#
#   bash scripts/master.sh <body.mp4> <mix.wav> <out.mp4> [--outro <file.mp4>]
#
# Audio: one fixed gain to -14.5 LUFS integrated, then a peak limiter at 4x oversampling set to
# -2.0 dBFS (true peak target -1.5 dBTP). Two passes: measure and apply, then one small correction
# if the limiter shaved more than 0.1 dB. No gain riding, so the voice never sounds pumped or
# "shouty" (ffmpeg's loudnorm silently switches to a dynamic mode when the peaks have no room).
# Picture: the body render, re-encoded once to the platform spec: 1080x1920, 30 fps CFR, H.264
# High, yuv420p, ~11 Mbps VBR, closed 1 s GOP, +faststart, AAC-LC 48 kHz stereo 192 kbps.
# --outro appends a finished clip as-is (its picture only; silent audio under it). Off by default.
# Gate: fails outside -15..-13 LUFS integrated or above -1.0 dBTP true peak.
set -euo pipefail

BODY="${1:?usage: master.sh <body.mp4> <mix.wav> <out.mp4> [--outro <file>]}"
MIX="${2:?mix.wav}"
OUT="${3:?out.mp4}"
shift 3
OUTRO=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --outro) OUTRO="${2:?--outro needs a file}"; shift 2 ;;
    *) echo "[master] unknown argument $1" >&2; exit 1 ;;
  esac
done
TARGET_I="-14.5"
LIMIT="0.794"   # -2.0 dBFS
for f in "$BODY" "$MIX" ${OUTRO:+"$OUTRO"}; do [[ -s "$f" ]] || { echo "[master] missing: $f" >&2; exit 1; }; done
NAME="$(basename "$OUT" .mp4)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

loud() { ffmpeg -hide_banner -nostats -i "$1" -af ebur128=peak=true -f null - 2>&1 | sed -n '/Summary:/,$p'; }
field() { printf '%s\n' "$1" | sed -n "s/^ *$2: *\(-*[0-9.]*\) .*/\1/p" | head -1; }
peak() { printf '%s\n' "$1" | sed -n 's/^ *Peak: *\(-*[0-9.inf]*\) dBFS/\1/p' | head -1; }

BODY_DUR="$(ffprobe -v error -select_streams v:0 -show_entries stream=duration -of csv=p=0 "$BODY")"
[[ -n "$BODY_DUR" ]] || { echo "[master] cannot read the body duration" >&2; exit 1; }
MI="$(field "$(loud "$MIX")" I)"
[[ -n "$MI" && "$MI" != "-inf" ]] || { echo "[master] could not measure the mix (silent?)" >&2; exit 1; }
GAIN="$(awk -v t="$TARGET_I" -v i="$MI" 'BEGIN { printf "%.2f", t - i }')"
echo "[master] $NAME: mix ${MI} LUFS; gain ${GAIN} dB, limiter -2.0 dBFS at 4x"

master_wav() {
  ffmpeg -v error -y -i "$MIX" -filter_complex "\
[0:a]aformat=sample_rates=48000:channel_layouts=stereo,volume=${1}dB,aresample=192000,alimiter=limit=${LIMIT}:attack=1:release=60:level=false:latency=1,aresample=48000,apad,atrim=duration=${BODY_DUR},asetpts=PTS-STARTPTS[a]" \
    -map "[a]" -c:a pcm_s24le "$WORK/master.wav"
}
master_wav "$GAIN"
I="$(field "$(loud "$WORK/master.wav")" I)"
FIX="$(awk -v t="$TARGET_I" -v i="$I" 'BEGIN { d = t - i; if (d > 0.1) printf "%.2f", d; else print "" }')"
if [[ -n "$FIX" ]]; then
  GAIN="$(awk -v g="$GAIN" -v f="$FIX" 'BEGIN { printf "%.2f", g + f }')"
  echo "[master] $NAME: landed at ${I} LUFS; second pass with gain ${GAIN} dB"
  master_wav "$GAIN"
fi

ENC=(-c:v libx264 -profile:v high -preset slow -pix_fmt yuv420p -r 30
  -b:v 11M -maxrate 12M -bufsize 22M -g 30 -keyint_min 30 -sc_threshold 0 -flags +cgop
  -c:a aac -b:a 192k -ar 48000 -ac 2 -movflags +faststart)
mkdir -p "$(dirname "$OUT")"
if [[ -z "$OUTRO" ]]; then
  ffmpeg -v error -y -i "$BODY" -i "$WORK/master.wav" -filter_complex "\
[0:v]fps=30,scale=1080:1920:flags=lanczos,setsar=1,format=yuv420p,trim=duration=$BODY_DUR,setpts=PTS-STARTPTS[v]" \
    -map "[v]" -map 1:a "${ENC[@]}" "$OUT"
else
  OUTRO_DUR="$(ffprobe -v error -select_streams v:0 -show_entries stream=duration -of csv=p=0 "$OUTRO")"
  echo "[master] $NAME: appending the outro (${OUTRO_DUR}s, silent)"
  ffmpeg -v error -y -i "$BODY" -i "$OUTRO" -i "$WORK/master.wav" -f lavfi -t "$OUTRO_DUR" -i "anullsrc=r=48000:cl=stereo" -filter_complex "\
[0:v]fps=30,scale=1080:1920:flags=lanczos,setsar=1,format=yuv420p,trim=duration=$BODY_DUR,setpts=PTS-STARTPTS[v0];\
[1:v]fps=30,scale=1080:1920:flags=lanczos,setsar=1,format=yuv420p,trim=duration=$OUTRO_DUR,setpts=PTS-STARTPTS[v1];\
[2:a]aformat=sample_rates=48000:channel_layouts=stereo[a0];\
[3:a]aformat=sample_rates=48000:channel_layouts=stereo[a1];\
[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]" \
    -map "[v]" -map "[a]" "${ENC[@]}" "$OUT"
fi

ffprobe -v error -show_entries stream=codec_name,profile,width,height,r_frame_rate,pix_fmt,sample_rate,channels:format=duration,bit_rate -of compact "$OUT"
FL="$(loud "$OUT")"; FI="$(field "$FL" I)"; FTP="$(peak "$FL")"; FLRA="$(field "$FL" LRA)"
echo "[master] $NAME: final ${FI} LUFS integrated, true peak ${FTP} dBTP, LRA ${FLRA} LU"
awk -v tp="$FTP" 'BEGIN { if (tp > -1.5) print "[master] note: true peak above the -1.5 dBTP target (the gate still passes up to -1.0)" }'
awk -v i="$FI" -v tp="$FTP" 'BEGIN { if (i < -15 || i > -13 || tp > -1) { print "[master] LOUDNESS GATE FAILED"; exit 1 } else print "[master] loudness gate passed (-15..-13 LUFS, <= -1 dBTP)" }'
echo "[master] wrote $(cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")"
