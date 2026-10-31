#!/bin/bash
# Makes the synthetic test reel inputs, so an install can be checked without any client footage.
# No real person appears anywhere: the "face" is an ffmpeg test pattern and the voice is the
# macOS text-to-speech voice (`say`). Without `say` (not macOS) the voice becomes short tones.
#
#   bash scripts/make-demo.sh            writes demo-synthetic/face.mp4, captures/screen.mp4,
#                                        transcript.json (overwrites them; they are git-ignored)
#
# Each script line gets a fixed time slot that matches demo-synthetic/shotlist.json, so the shot
# list never changes. Word times inside a line are spread by word length over the spoken audio:
# good enough to test captions and the build. For a real transcription test, run the transcribe
# step in AGENT-SETUP.md on demo-synthetic/face.mp4 afterwards.
# Needs: ffmpeg, ffprobe, python3. Uses: say (macOS, optional).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
D="$ROOT/demo-synthetic"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
command -v ffmpeg >/dev/null || { echo "[demo] ffmpeg is not installed" >&2; exit 1; }
command -v ffprobe >/dev/null || { echo "[demo] ffprobe is not installed" >&2; exit 1; }
command -v python3 >/dev/null || { echo "[demo] python3 is not installed" >&2; exit 1; }
mkdir -p "$D/captures"

# slot start | slot end | line (must match demo-synthetic/SCRIPT.md and shotlist.json beat times)
LINES=(
  "0.0|3.0|This is a test reel, made by a script."
  "3.0|6.0|No real person is in it, only test patterns."
  "6.0|8.5|That keeps the install check private."
  "8.5|12.0|Build it, check it, then look at it."
  "12.0|15.0|The check must show zero errors."
  "15.0|18.5|Compare the two exports side by side."
  "18.5|21.0|A client quote sits on a light plate."
  "21.0|24.0|Screen footage can sit in a card."
  "24.0|26.5|Logs type in line by line."
  "26.5|28.5|And then we are done."
  "28.5|32.0|Comment TEST and I will send the guide."
)
DUR=32.0
HAVE_SAY=0
command -v say >/dev/null && HAVE_SAY=1
[[ "$HAVE_SAY" == 1 ]] || echo "[demo] no macOS 'say' here: the voice will be short tones instead of speech"

# 1. one audio piece per line, placed at slot start + 0.1 s, squeezed (never over 1.6x) to fit
inputs=(); filters=(); meta="$TMP/meta.txt"; : > "$meta"
i=0
for row in "${LINES[@]}"; do
  IFS='|' read -r s e text <<< "$row"
  if [[ "$HAVE_SAY" == 1 ]]; then
    say -r 185 -o "$TMP/l$i.aiff" "$text"
    ffmpeg -v error -y -i "$TMP/l$i.aiff" -ac 1 -ar 48000 "$TMP/l$i.wav"
  else
    n="$(wc -w <<< "$text" | tr -d ' ')"
    ffmpeg -v error -y -f lavfi -i "sine=frequency=330:sample_rate=48000:duration=0.18" -af "apad=pad_dur=0.06" "$TMP/beep.wav"
    for ((k = 0; k < n; k++)); do echo "file '$TMP/beep.wav'"; done > "$TMP/l$i.txt"
    ffmpeg -v error -y -f concat -safe 0 -i "$TMP/l$i.txt" -ac 1 -ar 48000 "$TMP/l$i.wav"
  fi
  len="$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$TMP/l$i.wav")"
  room="$(awk -v s="$s" -v e="$e" 'BEGIN { printf "%.3f", e - s - 0.3 }')"
  tempo="$(awk -v l="$len" -v r="$room" 'BEGIN { t = l / r; if (t < 1) t = 1; printf "%.4f", t }')"
  awk -v t="$tempo" 'BEGIN { exit !(t > 1.6) }' && { echo "[demo] line $((i + 1)) is too long for its slot" >&2; exit 1; }
  spoken="$(awk -v l="$len" -v t="$tempo" 'BEGIN { printf "%.3f", l / t }')"
  start="$(awk -v s="$s" 'BEGIN { printf "%.3f", s + 0.1 }')"
  printf '%s|%s|%s\n' "$start" "$spoken" "$text" >> "$meta"
  inputs+=(-i "$TMP/l$i.wav")
  filters+=("[$i:a]atempo=$tempo,adelay=delays=$(awk -v s="$start" 'BEGIN { printf "%d", s * 1000 }'):all=1[a$i]")
  i=$((i + 1))
done
mix=""; for ((k = 0; k < i; k++)); do mix="$mix[a$k]"; done
ffmpeg -v error -y "${inputs[@]}" -filter_complex "$(IFS=';'; echo "${filters[*]}");${mix}amix=inputs=$i:normalize=0:duration=longest,apad,atrim=duration=$DUR,volume=6dB[v]" \
  -map "[v]" -ac 2 -ar 48000 "$TMP/voice.wav"

# 2. the "face": a moving test pattern, 1080x1920, 30 fps, with the voice
ffmpeg -v error -y -f lavfi -i "testsrc2=size=1080x1920:rate=30:duration=$DUR" -i "$TMP/voice.wav" \
  -c:v libx264 -preset veryfast -crf 42 -pix_fmt yuv420p -g 30 -c:a aac -b:a 128k -ar 48000 -shortest -movflags +faststart \
  "$D/face.mp4"

# 3. a "screen recording": colour bars, 1080x1920, 12 s, no sound
ffmpeg -v error -y -f lavfi -i "smptehdbars=size=1080x1920:rate=30:duration=12" -vf "hue=H=2*PI*t/12" \
  -c:v libx264 -preset veryfast -crf 30 -pix_fmt yuv420p -g 30 -an -movflags +faststart "$D/captures/screen.mp4"

# 4. transcript.json: [{id, text, start, end}], words spread by length over each spoken line
python3 -I - "$meta" "$D/transcript.json" <<'PY'
import json, sys
words, n = [], 0
for row in open(sys.argv[1]):
    start, spoken, text = row.rstrip("\n").split("|", 2)
    start, spoken = float(start), float(spoken)
    toks = text.split()
    weights = [len(t) + 1 for t in toks]
    total, t = float(sum(weights)), start
    for tok, w in zip(toks, weights):
        d = spoken * w / total
        words.append({"id": f"w{n}", "text": tok, "start": round(t, 3), "end": round(t + d * 0.92, 3)})
        n += 1
        t += d
json.dump(words, open(sys.argv[2], "w"), indent=1)
print(f"[demo] transcript: {len(words)} words")
PY
echo "[demo] wrote $D/face.mp4, $D/captures/screen.mp4, $D/transcript.json"
