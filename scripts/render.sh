#!/bin/bash
# Renders one finished vertical reel, both exports, on THIS machine (the default).
#
#   bash scripts/render.sh <client> <input-dir> <out-dir> [--name <slug-vN>] [--music <file>]
#                          [--bed-lufs <n>] [--sfx|--no-sfx] [--voice-eq on|off] [--outro <file>]
#     <client>     a client folder name (clients/<client>/brand.json) or a path to a brand.json
#     <input-dir>  folder with face.mp4 + transcript.json + shotlist.json, relative to the kit
#                  (e.g. videos/<client>/<slug>/input)
#     <out-dir>    where the exports go (e.g. videos/<client>/<slug>/final)
#     --name n     export name (default: the video folder name). Use <slug>-v1, -v2 ... per review
#                  round so a new round never overwrites the last one.
#     --music f    lay a licensed music bed, ducked under the voice (needs a licence row first)
#     --bed-lufs n bed level in the gaps, final LUFS (default -19)
#     --sfx/--no-sfx  sound effects on the beats (default: brand.json "audio": {"sfx": ...}, else on)
#     --voice-eq   presence EQ on the voice (default: brand.json "audio": {"voiceEq": ...}, else on)
#     --outro f    append a finished outro clip as-is. Off by default (a silent outro can hurt
#                  retention; end on the body unless the client asks for one)
#
# Steps: build index.html -> hyperframes check (fails on errors) -> hyperframes render (body)
#        -> audio pass (voice chain, SFX, optional bed: renders/<name>.audio/)
#        -> master twice: <out-dir>/<name>.mp4 and <out-dir>/<name>-nomusic.mp4 (always both)
# Heavy step: the body render. On a slow machine use scripts/remote/render-remote.sh (optional
# worker laptop) with the same arguments. On ANY failure, run the doctor first:
#   HYPERFRAMES_NO_TELEMETRY=1 npx --yes hyperframes@0.8.143 doctor
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SFX=""; MUSIC=""; BED_LUFS="-19"; VOICE_EQ=""; OUTRO=""; NAME=""; POS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --sfx) SFX=1; shift ;;
    --no-sfx) SFX=0; shift ;;
    --music) MUSIC="${2:?--music needs a file}"; shift 2 ;;
    --bed-lufs) BED_LUFS="${2:?--bed-lufs needs a number}"; shift 2 ;;
    --voice-eq) VOICE_EQ="${2:?--voice-eq needs on or off}"; shift 2 ;;
    --outro) OUTRO="${2:?--outro needs a file}"; shift 2 ;;
    --name) NAME="${2:?--name needs a name}"; shift 2 ;;
    --*) echo "[render] unknown flag $1" >&2; exit 1 ;;
    *) POS+=("$1"); shift ;;
  esac
done
[[ ${#POS[@]} -eq 3 ]] || { echo "usage: render.sh <client> <input-dir> <out-dir> [--name <slug-vN>] [--music <file>] [--bed-lufs <n>] [--sfx|--no-sfx] [--voice-eq on|off] [--outro <file>]" >&2; exit 1; }
CLIENT="${POS[0]}"; INPUT="${POS[1]}"; OUT="${POS[2]}"
if [[ "$CLIENT" == *.json ]]; then BRAND="$CLIENT"; else BRAND="clients/$CLIENT/brand.json"; fi
[[ -f "$ROOT/$BRAND" ]] || { echo "[render] brand file not found: $BRAND (run DESIGN-INTERVIEW.md for this client first)" >&2; exit 1; }
[[ -d "$ROOT/$INPUT" ]] || { echo "[render] input folder not found: $INPUT (give it relative to the kit folder)" >&2; exit 1; }
if [[ -z "$NAME" ]]; then
  NAME="$(basename "$INPUT")"
  [[ "$NAME" == "input" ]] && NAME="$(basename "$(dirname "$INPUT")")"   # videos/<client>/<slug>/input -> <slug>
fi
[[ "$NAME" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "[render] --name may use letters, digits, dot, dash and underscore only" >&2; exit 1; }
HF=(npx --yes hyperframes@0.8.143)
export HYPERFRAMES_NO_TELEMETRY=1

if [[ -n "$MUSIC" ]]; then
  [[ -f "$MUSIC" ]] || { echo "[render] music not found: $MUSIC" >&2; exit 1; }
  MUSIC="$(cd "$(dirname "$MUSIC")" && pwd)/$(basename "$MUSIC")"
fi
[[ -z "$OUTRO" || -f "$OUTRO" ]] || { echo "[render] outro not found: $OUTRO" >&2; exit 1; }
# brand audio defaults
read -r B_SFX B_EQ < <(node -e 'const fs=require("fs");let a={};try{a=JSON.parse(fs.readFileSync(process.argv[1],"utf8")).audio||{}}catch(e){}process.stdout.write(`${a.sfx===false?0:1} ${a.voiceEq===false?"off":"on"}\n`)' "$ROOT/$BRAND")
SFX="${SFX:-$B_SFX}"; VOICE_EQ="${VOICE_EQ:-$B_EQ}"
[[ "$VOICE_EQ" == "on" || "$VOICE_EQ" == "off" ]] || { echo "[render] --voice-eq must be on or off" >&2; exit 1; }

mkdir -p "$ROOT/renders" "$OUT"
BODY="$ROOT/renders/$NAME.body.mp4"
AUD_DIR="$ROOT/renders/$NAME.audio"
CUES="$ROOT/renders/$NAME.sfx-cues.json"
fail_hint() { echo "[render] $1 failed. First run: (cd $ROOT && ${HF[*]} doctor)" >&2; exit 1; }

echo "[render] $NAME: build ($BRAND)"
(cd "$ROOT" && node scripts/build.mjs --input "$INPUT" --brand "$BRAND" --cues "$CUES") || fail_hint "build"

echo "[render] $NAME: check"
(cd "$ROOT" && "${HF[@]}" check . --no-contrast >/dev/null) || {
  echo "[render] check failed; see the details with: (cd $ROOT && ${HF[*]} check .)" >&2
  fail_hint "check"
}

echo "[render] $NAME: render body (the heavy step)"
# --sdr: phone takes often carry HLG/BT.2020 tags; without it the render is promoted to HDR and the
# SDR H.264 master would be wrong.
(cd "$ROOT" && "${HF[@]}" render . --quality delivery --fps 30 --sdr --output "renders/$NAME.body.mp4" --quiet) || fail_hint "render"
[[ -s "$BODY" ]] || fail_hint "render (no body file)"

echo "[render] $NAME: audio pass (sfx=$SFX, voice-eq=$VOICE_EQ${MUSIC:+, music=$MUSIC})"
if [[ "$SFX" != "1" ]]; then
  # keep the cue sheet but play no cues
  node -e 'const fs=require("fs");const p=process.argv[1];const s=JSON.parse(fs.readFileSync(p,"utf8"));s.dropped=(s.dropped||[]).concat((s.cues||[]).map(c=>({...c,reason:"--no-sfx"})));s.cues=[];fs.writeFileSync(p,JSON.stringify(s,null,2)+"\n")' "$CUES"
fi
(cd "$ROOT" && node scripts/audio-pass.mjs --body "$BODY" --cues "$CUES" --out "$AUD_DIR" --voice-eq "$VOICE_EQ" --bed-lufs "$BED_LUFS" ${MUSIC:+--music "$MUSIC"}) || fail_hint "audio pass"

bash "$ROOT/scripts/master.sh" "$BODY" "$AUD_DIR/mix.wav" "$OUT/$NAME.mp4" ${OUTRO:+--outro "$OUTRO"}
bash "$ROOT/scripts/master.sh" "$BODY" "$AUD_DIR/mix-nomusic.wav" "$OUT/$NAME-nomusic.mp4" ${OUTRO:+--outro "$OUTRO"}
[[ -n "$MUSIC" ]] || echo "[render] note: no music bed was given, so $NAME.mp4 and $NAME-nomusic.mp4 have the same audio. Post the -nomusic file and add music in the app, or re-render with a licensed --music bed."
echo "[render] done: $OUT/$NAME.mp4 and $OUT/$NAME-nomusic.mp4"
