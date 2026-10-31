#!/bin/bash
# OPTIONAL. Renders one video on a worker laptop instead of this Mac. Same arguments as
# scripts/render.sh (which renders locally and is the default):
#
#   bash scripts/remote/render-remote.sh <client> <input-dir> <out-dir> [--name <slug-vN>] [--music <file>]
#        [--bed-lufs <n>] [--sfx|--no-sfx] [--voice-eq on|off] [--outro <file>]
#
# 1. Waits its turn: one render at a time per worker (a lock folder on the worker,
#    ~/render-remote/lock; a lock whose render died is cleared automatically).
# 2. Copies the kit (no renders/, input/, videos/, node_modules/, .git or .bak-*), the input folder, any
#    input folder its shotlist.json points into, and every file argument that lives outside the
#    kit (the --music file, the --outro file) to the worker. Files inside the kit keep the same
#    place under the worker's ~/claude-reel-kit (WORKER_KIT_DIR); anything else goes to
#    ~/render-remote/external/<full path>.
# 3. Runs scripts/render.sh there fully detached (it survives a dropped connection), logging to
#    ~/render-remote/jobs/<job>/log, and prints its [render] and [master] lines here as they come.
# 4. Copies back what render.sh would have written on this Mac: <out-dir>/<name>.mp4 and
#    <name>-nomusic.mp4, plus renders/<name>.body.mp4, renders/<name>.audio/ and
#    renders/<name>.sfx-cues.json. The worker's full log is copied to renders/<name>.remote.log.
#
# Workers: scripts/remote/workers.conf (copy workers.conf.example and fill it in). Env:
#   WORKER=<name>         use that line of workers.conf (default: the first line)
#   WORKERS_CONF=<file>   use another worker list
#   WORKER_KIT_DIR=<dir>  where the kit lives on the worker, relative to its home (default claude-reel-kit)
#   REMOTE_JOB=<job id>   skip the upload and pick up a job already on the worker (after this
#                         Mac lost contact), then copy its results back. Give the same arguments.
# The worker needs: Remote Login (ssh) on, this Mac's ssh key, node + npx + ffmpeg + ffprobe on the
# PATH of a non-interactive shell, and the kit's own one-time setup (AGENT-SETUP.md) done there.
# Exit: 0 done, 1 bad arguments, 2 worker unreachable or upload failed, 3 render failed on the
#       worker, 4 lost contact while rendering (the render goes on there; see REMOTE_JOB).
# Never falls back to rendering on this Mac; on failure it prints the local command instead.
set -euo pipefail
export LC_ALL=C

ROOT="$(cd "$(dirname "$0")/../.." && pwd -P)"
# worker list, ssh options, path mapping, the worker lock and the detached launch are shared with
# run-on-worker.sh (one copy, so a render and any other heavy job never overlap on a worker)
# shellcheck source=worker-lib.sh
source "$ROOT/scripts/remote/worker-lib.sh"
CALLER_PWD="$(pwd)"
ORIG_ARGS=("$@")
POLL_SECS=5          # how often to read the worker's log while it renders
WAIT_POLL_SECS=15    # how often to check whether a busy worker is free
GIVE_UP_SECS=600     # lost contact this long while rendering: stop following (exit 4)
STALE_SYNC_SECS=1800 # a lock still uploading (no render started) after this long is abandoned

say() { echo "[remote] $*"; }
q() { printf '%q' "$1"; }
local_cmd() {
  local a s=""
  for a in ${ORIG_ARGS[@]+"${ORIG_ARGS[@]}"}; do s="$s $(q "$a")"; done
  printf '(cd %s && bash %s%s)' "$(q "$CALLER_PWD")" "$(q "$ROOT/scripts/render.sh")" "$s"
}
die() { local code="$1"; shift; echo "[remote] $*" >&2; exit "$code"; }
die_local() {
  local code="$1"; shift
  echo "[remote] $*" >&2
  echo "[remote] Nothing was rendered on this Mac. To render here instead, run:" >&2
  echo "  $(local_cmd)" >&2
  exit "$code"
}
mmss() { printf '%d:%02d' $(($1 / 60)) $(($1 % 60)); }

# ---- arguments: parsed exactly like render.sh
SFX=""; MUSIC=""; BED_LUFS=""; VOICE_EQ=""; OUTRO=""; NAME=""; POS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --sfx) SFX=1; shift ;;
    --no-sfx) SFX=0; shift ;;
    --music) MUSIC="${2:?--music needs a file}"; shift 2 ;;
    --bed-lufs) BED_LUFS="${2:?--bed-lufs needs a number}"; shift 2 ;;
    --voice-eq) VOICE_EQ="${2:?--voice-eq needs on or off}"; shift 2 ;;
    --outro) OUTRO="${2:?--outro needs a file}"; shift 2 ;;
    --name) NAME="${2:?--name needs a name}"; shift 2 ;;
    --*) die 1 "unknown flag $1" ;;
    *) POS+=("$1"); shift ;;
  esac
done
[[ ${#POS[@]} -eq 3 ]] || die 1 "usage: render-remote.sh <client> <input-dir> <out-dir> [--name <slug-vN>] [--music <file>] [--bed-lufs <n>] [--sfx|--no-sfx] [--voice-eq on|off] [--outro <file>]"

abs_file() { (cd "$(dirname "$1")" && printf '%s/%s\n' "$(pwd -P)" "$(basename "$1")"); }
abs_dir() { (cd "$1" && pwd -P); }
# to_worker <abs path>: where it lives on the worker (worker-lib.sh)

SYNC_FILES=()   # files outside the kit sync (absolute paths on this Mac)
SYNC_DIRS=()    # input folders (absolute paths on this Mac)

CLIENT="${POS[0]}"
if [[ "$CLIENT" == *.json ]]; then BRAND="$CLIENT"; else BRAND="clients/$CLIENT/brand.json"; fi
[[ -f "$ROOT/$BRAND" ]] || die 1 "brand file not found: $BRAND (it must be inside the kit)"

INPUT="${POS[1]}"
[[ "$INPUT" != /* ]] || die 1 "give the input folder relative to the kit folder (as render.sh does): $INPUT"
IDIR="$ROOT/$INPUT"
[[ -d "$IDIR" ]] || die 1 "input folder not found: $INPUT"
IDIR="$(abs_dir "$IDIR")"
if [[ -z "$NAME" ]]; then
  NAME="$(basename "$IDIR")"
  [[ "$NAME" == "input" ]] && NAME="$(basename "$(dirname "$IDIR")")"
fi
SYNC_DIRS+=("$IDIR")
# media in a shotlist is kit-relative; another video's input folder must come along too
if [[ -f "$IDIR/shotlist.json" ]]; then
  for p in $( (grep -o -E '"(input/[^/"]*|videos/[^/"]*/[^/"]*/input)/' "$IDIR/shotlist.json" || true) | tr -d '"' | sort -u); do
    d="$ROOT/${p%/}"
    if [[ -d "$d" ]]; then d="$(abs_dir "$d")"; [[ "$d" == "$IDIR" ]] || SYNC_DIRS+=("$d"); fi
  done
fi

OUT="${POS[2]}"
mkdir -p "$OUT" || die 1 "cannot create the out folder: $OUT"
OUT="$(abs_dir "$OUT")"

if [[ -n "$MUSIC" ]]; then
  [[ -f "$MUSIC" ]] || die 1 "music not found: $MUSIC"
  MUSIC="$(abs_file "$MUSIC")"
  case "$MUSIC" in "$ROOT"/*) ;; *) SYNC_FILES+=("$MUSIC") ;; esac
fi
if [[ -n "$OUTRO" ]]; then
  [[ -f "$OUTRO" ]] || die 1 "outro not found: $OUTRO"
  OUTRO="$(abs_file "$OUTRO")"
  case "$OUTRO" in "$ROOT"/*) ;; *) SYNC_FILES+=("$OUTRO") ;; esac
fi

# ---- worker
WORKERS_CONF="${WORKERS_CONF:-$ROOT/scripts/remote/workers.conf}"
worker_select || die 1 "$WL_ERR"   # sets W_NAME W_USER W_ADDR W_ALIAS W_KEY SSH_OPTS DEST RSH; wssh

say "worker $W_NAME ($DEST): checking it is reachable"
PRE="$(wssh 'for t in node ffmpeg ffprobe; do command -v $t >/dev/null || echo "MISSING $t"; done; echo "HOME $HOME"' 2>/dev/null)" ||
  die_local 2 "Can't reach the worker laptop $W_NAME at $W_ADDR. Check it is switched on, plugged in, awake and on the same network or VPN."
if grep -q '^MISSING' <<< "$PRE"; then
  die_local 2 "The worker $W_NAME is reachable but is missing: $(sed -n 's/^MISSING //p' <<< "$PRE" | tr '\n' ' ')"
fi
RHOME="$(sed -n 's/^HOME //p' <<< "$PRE")"
[[ "$RHOME" == /* ]] || die_local 2 "The worker $W_NAME did not report its home folder."

RT="$RHOME/$(to_worker "$ROOT")"          # the kit on the worker
RBASE="$RHOME/render-remote"
RLOCK="$RBASE/lock"
JOB="${REMOTE_JOB:-$NAME-$(date +%Y%m%d-%H%M%S)-$$}"
RJOB="$RBASE/jobs/$JOB"
LOGCOPY="$ROOT/renders/$NAME.remote.log"
LOGTMP="$LOGCOPY.$$.tmp"   # per run, so two runs of the same video never share it
mkdir -p "$ROOT/renders"

# what to hand render.sh on the worker: kit-relative inside the kit, else absolute
warg() { case "$1" in "$ROOT"/*) printf '%s' "${1#"$ROOT"/}" ;; *) printf '%s/%s' "$RHOME" "$(to_worker "$1")" ;; esac; }

HOLDING=0; STARTED=0
# the worker lock (worker_try_lock / worker_release_lock) lives in bin/worker-lib.sh
on_exit() { rm -f "$LOGTMP"; if [[ "$HOLDING" == "1" && "$STARTED" == "0" ]]; then worker_release_lock "$RLOCK" "$JOB"; fi; }
trap on_exit EXIT
on_signal() {
  echo
  if [[ "$STARTED" == "1" ]]; then
    say "stopped following. The render keeps going on $W_NAME. To copy it back when it is done:"
    say "  (cd $(q "$CALLER_PWD") && REMOTE_JOB=$JOB bash $(q "$ROOT/scripts/render-remote.sh")$(for a in ${ORIG_ARGS[@]+"${ORIG_ARGS[@]}"}; do printf ' %q' "$a"; done))"
  else
    say "cancelled; nothing is running on $W_NAME for this job."
  fi
  exit 130
}
trap on_signal INT TERM

if [[ -z "${REMOTE_JOB:-}" ]]; then
  # ---- 1. wait our turn
  waited=0; t_wait=$(date +%s); last_note=0; fails=0
  while :; do
    if ! R="$(worker_try_lock "$RLOCK" "$JOB" "$STALE_SYNC_SECS")"; then
      fails=$((fails + 1))
      [[ $fails -lt 5 ]] || die_local 2 "Lost contact with the worker $W_NAME while waiting for it to be free."
      sleep "$WAIT_POLL_SECS"; continue
    fi
    fails=0
    case "$R" in
      GOT*)
        HOLDING=1
        [[ "$R" == GOT_STALE* ]] && say "cleared a lock left by a render that is no longer running (${R#GOT_STALE })"
        [[ $waited == 1 ]] && say "worker is free after $(mmss $(( $(date +%s) - t_wait ))) of waiting"
        break ;;
      BUSY*)
        read -r _ holder since <<< "$R"
        now=$(date +%s)
        if [[ $waited == 0 ]]; then
          say "worker $W_NAME is busy with $holder (since $(date -r "$since" +%H:%M)); this render waits its turn"
          waited=1; last_note=$now
        elif (( now - last_note >= 60 )); then
          say "still waiting for $holder ($(mmss $(( now - t_wait ))) so far)"; last_note=$now
        fi
        sleep "$WAIT_POLL_SECS" ;;
      *) die_local 2 "Unexpected answer from the worker $W_NAME: $R" ;;
    esac
  done

  # ---- 2. copy the kit, the inputs and outside files to the worker
  say "job $JOB: copying the kit and inputs to $W_NAME"
  t_sync=$(date +%s)
  PARENTS=("$RJOB/out" "$(dirname "$RT")")
  for d in "${SYNC_DIRS[@]}"; do PARENTS+=("$(dirname "$RHOME/$(to_worker "$d")")"); done
  for f in ${SYNC_FILES[@]+"${SYNC_FILES[@]}"}; do PARENTS+=("$(dirname "$RHOME/$(to_worker "$f")")"); done
  mk="mkdir -p"; for d in "${PARENTS[@]}"; do mk="$mk $(q "$d")"; done
  wssh "$mk" || die_local 2 "Could not create folders on the worker $W_NAME."
  (cd "$ROOT/.." && rsync -a -e "$RSH" --exclude 'renders/' --exclude '.bak-*' --exclude 'input/*' \
    --exclude 'node_modules/' --exclude '.git/' --exclude '.bin/' --exclude 'videos/' \
    "$(basename "$ROOT")/" "$DEST:$RT/") || die_local 2 "Copying the kit to the worker $W_NAME failed."
  for d in "${SYNC_DIRS[@]}"; do
    rsync -a -e "$RSH" --exclude '.bak-*' "$d" "$DEST:$(dirname "$RHOME/$(to_worker "$d")")/" ||
      die_local 2 "Copying $d to the worker $W_NAME failed."
  done
  for f in ${SYNC_FILES[@]+"${SYNC_FILES[@]}"}; do
    rsync -a -e "$RSH" "$f" "$DEST:$(dirname "$RHOME/$(to_worker "$f")")/" ||
      die_local 2 "Copying $f to the worker $W_NAME failed."
  done
  say "copied in $(mmss $(( $(date +%s) - t_sync )))"

  # ---- 3. start render.sh on the worker, detached
  RARGS=("$BRAND" "$(warg "$IDIR")" "$RJOB/out" --name "$NAME")
  [[ "$SFX" == "1" ]] && RARGS+=(--sfx)
  [[ "$SFX" == "0" ]] && RARGS+=(--no-sfx)
  [[ -n "$MUSIC" ]] && RARGS+=(--music "$(warg "$MUSIC")")
  [[ -n "$BED_LUFS" ]] && RARGS+=(--bed-lufs "$BED_LUFS")
  [[ -n "$VOICE_EQ" ]] && RARGS+=(--voice-eq "$VOICE_EQ")
  [[ -n "$OUTRO" ]] && RARGS+=(--outro "$(warg "$OUTRO")")
  {
    echo '#!/bin/bash'
    echo "# written by render-remote.sh on $(hostname -s) at $(date '+%Y-%m-%d %H:%M %Z')"
    echo "T=$(q "$RT"); NAME=$(q "$NAME")"
    printf 'ARGS=('; for a in "${RARGS[@]}"; do printf ' %q' "$a"; done; echo ' )'
    worker_run_preamble "$JOB" "$RLOCK" "$RJOB" render   # lock check, pid, signal trap, finish <rc>
    cat <<'EOF'
mkdir -p out renders
echo "[remote] $(date '+%H:%M:%S') render.sh ${ARGS[*]}" >> log
( cd "$T" && bash scripts/render.sh "${ARGS[@]}" ) >> log 2>&1
rc=$?
if [ "$rc" = 0 ]; then
  # keep this job's own copies, so the next job on this worker cannot overwrite them before
  # the Mac copies them back (APFS clones: instant, no extra space)
  stash() { cp -cR "$1" renders/ 2>/dev/null || cp -R "$1" renders/ || rc=96; }
  for f in "$T/renders/$NAME.body.mp4" "$T/renders/$NAME.sfx-cues.json"; do
    [ -n "$(find "$f" -newer started 2>/dev/null)" ] && stash "$f"
  done
  A="$T/renders/$NAME.audio"
  [ -n "$(find "$A" -type f -newer started 2>/dev/null | head -1)" ] && stash "$A"
  [ "$rc" = 0 ] || echo "[remote] could not keep a copy of the renders/ files" >> log
fi
echo "[remote] $(date '+%H:%M:%S') finished, exit $rc" >> log
finish "$rc"
EOF
  } | wssh "mkdir -p $(q "$RJOB") && cat > $(q "$RJOB/run.sh")" || die_local 2 "Could not send the job to the worker $W_NAME."
  worker_launch "$RJOB/run.sh" || die_local 2 "Could not start the render on the worker $W_NAME."
  STARTED=1; HOLDING=0
  say "rendering on $W_NAME (job $JOB). Safe to lose the connection: it keeps going there."
else
  say "picking up job $JOB on $W_NAME"
  STARTED=1
fi

# ---- 4. follow the worker's log
t_start=$(date +%s); last_print=$t_start; seen=0; first_fail=0; STATUS=""
while :; do
  if wssh "if [ -f $(q "$RJOB/exit") ]; then cat $(q "$RJOB/exit"); elif [ -d $(q "$RJOB") ]; then echo running; else echo missing; fi; cat $(q "$RJOB/log") 2>/dev/null; true" > "$LOGTMP" 2>/dev/null; then
    if [[ $first_fail != 0 ]]; then say "back in contact with $W_NAME"; first_fail=0; fi
    STATUS="$(head -1 "$LOGTMP")"
    tail -n +2 "$LOGTMP" > "$LOGCOPY"
    n=$(wc -l < "$LOGCOPY" | tr -d ' ')
    if (( n > seen )); then
      if [[ -n "$(awk -v a=$((seen + 1)) -v b="$n" 'NR >= a && NR <= b && /^\[(render|master)\]/' "$LOGCOPY")" ]]; then
        awk -v a=$((seen + 1)) -v b="$n" 'NR >= a && NR <= b && /^\[(render|master)\]/' "$LOGCOPY" | sed "s#$RJOB/out#$OUT#g"
        last_print=$(date +%s)
      fi
      seen=$n
    fi
    [[ "$STATUS" == "missing" ]] && die 1 "there is no job $JOB on the worker $W_NAME"
    [[ "$STATUS" == "running" ]] || break
  else
    now=$(date +%s)
    if [[ $first_fail == 0 ]]; then
      first_fail=$now
      say "lost contact with $W_NAME; retrying. The render keeps going there."
    elif (( now - first_fail >= GIVE_UP_SECS )); then
      say "no contact with $W_NAME for $(mmss $(( now - first_fail ))); stopped following." >&2
      say "When the worker is back, copy the result with:" >&2
      say "  (cd $(q "$CALLER_PWD") && REMOTE_JOB=$JOB bash $(q "$ROOT/scripts/render-remote.sh")$(for a in ${ORIG_ARGS[@]+"${ORIG_ARGS[@]}"}; do printf ' %q' "$a"; done))" >&2
      exit 4
    fi
  fi
  now=$(date +%s)
  if (( now - last_print >= 60 )); then say "still rendering on $W_NAME ($(mmss $(( now - t_start ))))"; last_print=$now; fi
  sleep "$POLL_SECS"
done

if [[ "$STATUS" != "0" ]]; then
  echo "[remote] ---- last lines of the worker's log ----" >&2
  tail -n 30 "$LOGCOPY" >&2
  die_local 3 "The render failed on the worker $W_NAME (exit $STATUS). Full log: $LOGCOPY"
fi

# ---- 5. copy the results back
say "copying the results back from $W_NAME"
FILES="$(wssh "cd $(q "$RJOB/out") && ls")" || die 4 "could not list the results on $W_NAME; retry with REMOTE_JOB=$JOB"
[[ -n "$FILES" ]] || die 3 "the worker $W_NAME finished but wrote no video; see $LOGCOPY"
rsync -a -e "$RSH" "$DEST:$RJOB/out/" "$OUT/" || die 4 "copying the videos back failed; retry with REMOTE_JOB=$JOB"
rsync -a -e "$RSH" "$DEST:$RJOB/renders/" "$ROOT/renders/" || die 4 "copying renders/ back failed; retry with REMOTE_JOB=$JOB"
while IFS= read -r f; do
  [[ -s "$OUT/$f" ]] || die 4 "$OUT/$f is missing after the copy; retry with REMOTE_JOB=$JOB"
  say "wrote $OUT/$f"
done <<< "$FILES"
# the job's copies are now on this Mac; drop them on the worker (log and run.sh stay)
wssh "rm -rf $(q "$RJOB/out") $(q "$RJOB/renders")" || say "note: could not tidy $RJOB/out on $W_NAME (harmless)"
say "done in $(mmss $(( $(date +%s) - t_start ))) on $W_NAME; worker log: $LOGCOPY"
