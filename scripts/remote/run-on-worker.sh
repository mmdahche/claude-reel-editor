#!/bin/bash
# OPTIONAL. Runs one heavy command on a worker laptop instead of this Mac, then copies its results
# back. Only for editors with a second Mac set up in scripts/remote/workers.conf; every step in the
# kit runs locally without it.
#
#   scripts/remote/run-on-worker.sh [--in <path>]... [--out <path>]... [--need <tool>]... [--name <label>]
#                        [--log <file>] [--local <text>] [--] <command> [args...]
#
#   --in <path>     a file or folder the command reads. Copied to the worker before it starts
#                   (.bak-* folders are skipped). Repeat for each one.
#   --out <path>    a file or folder the command writes. When the command succeeds it is copied
#                   back to the same place here. Repeat for each one. A folder that does not exist
#                   on this Mac yet: end it with /, so it is created on the worker before the run.
#   --need <tool>   a program the worker must have on its PATH; checked before anything is copied.
#                   (The command's own program is always checked, after the copy.)
#   --name <label>  job label (default: the command's program name)
#   --log <file>    also save the worker's log here
#   --local <text>  the command to show for running it on this Mac instead, when the worker can't
#                   be used (default: the command itself, in this folder). For wrapper scripts.
#
# 1. Waits its turn: the worker's lock (~/render-remote/lock) is shared with render-remote.sh,
#    so a cutout never runs while a render does. One heavy job at a time per machine.
# 2. Copies every --in to the worker. A path inside the kit keeps the same place under the
#    worker's ~/claude-reel-kit (WORKER_KIT_DIR); anything else goes to ~/render-remote/external/<full path>.
# 3. Runs the command there fully detached (it survives a dropped connection), in the worker's copy
#    of the folder you ran this from, logging to ~/render-remote/jobs/<job>/log, and prints the
#    log here as it grows.
# 4. If it exits 0, copies every --out back to the same path on this Mac.
#
# Paths in the command: every argument that is an absolute path inside the kit, or at or
# inside an --in/--out path or the folder holding one (so `-o <dir>` with `--out <dir>/<file>`
# works outside the kit too), is rewritten to the worker's copy, and so is the /path part of
# --flag=/path and NAME=/path. Relative paths work as they are (same working folder). Other
# absolute paths (/usr/bin/swift, /dev/null) are left alone. Paths written INSIDE one quoted
# script string (bash -c '...') are not rewritten: pass them as separate arguments ("$1", "$2").
#
# Env: WORKER=<name> (a line of workers.conf; default the first), WORKERS_CONF=<file>,
#      REMOTE_JOB=<job id> (pick up a job already started on the worker; give the same arguments).
# Worker list: scripts/remote/workers.conf (shared with render-remote.sh; start from workers.conf.example).
# Exit: the command's own exit code when it ran on the worker. Otherwise:
#   64 bad arguments; 75 nothing ran: worker unreachable, missing a tool, or the copy failed;
#   76 lost contact while it ran (it keeps going there; see REMOTE_JOB);
#   77 it succeeded on the worker but a result is missing or could not be copied back.
# Never falls back to this Mac. When the worker can't be used it prints the local command instead.
set -euo pipefail
export LC_ALL=C

LIB="$(cd "$(dirname "$0")" && pwd -P)/worker-lib.sh"
# shellcheck source=worker-lib.sh
source "$LIB"

CALLER_PWD="$(pwd -P)"
ORIG_ARGS=("$@")
SELF="$(cd "$(dirname "$0")" && pwd -P)/$(basename "$0")"
POLL_SECS=3          # how often to read the worker's log
WAIT_POLL_SECS=15    # how often to check whether a busy worker is free
GIVE_UP_SECS=600     # lost contact this long while running: stop following (exit 76)
STALE_SYNC_SECS=1800 # a lock still uploading (no job started) after this long is abandoned

say() { echo "[worker] $*"; }
q() { printf '%q' "$1"; }
die() { local code="$1"; shift; echo "[worker] $*" >&2; exit "$code"; }
mmss() { printf '%d:%02d' $(($1 / 60)) $(($1 % 60)); }

# ---- arguments
INS=(); OUTS=(); NEEDS=(); LABEL=""; LOGFILE=""; LOCAL_HINT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --in) INS+=("${2:?--in needs a path}"); shift 2 ;;
    --out) OUTS+=("${2:?--out needs a path}"); shift 2 ;;
    --need) NEEDS+=("${2:?--need needs a program name}"); shift 2 ;;
    --name) LABEL="${2:?--name needs a label}"; shift 2 ;;
    --log) LOGFILE="${2:?--log needs a file}"; shift 2 ;;
    --local) LOCAL_HINT="${2:?--local needs a command}"; shift 2 ;;
    --) shift; break ;;
    --*) die 64 "unknown option $1 (put -- before the command if it starts with a dash)" ;;
    *) break ;;
  esac
done
CMD=("$@")
[[ ${#CMD[@]} -gt 0 ]] || die 64 "usage: run-on-worker.sh [--in <path>]... [--out <path>]... [--need <tool>]... [--name <label>] [--log <file>] [--local <text>] [--] <command> [args...]"

local_cmd() {
  [[ -z "$LOCAL_HINT" ]] || { printf '%s' "$LOCAL_HINT"; return; }
  local a s=""
  for a in "${CMD[@]}"; do s="$s $(q "$a")"; done
  printf '(cd %s &&%s)' "$(q "$CALLER_PWD")" "$s"
}
die_local() {
  local code="$1"; shift
  echo "[worker] $*" >&2
  echo "[worker] Nothing ran on this Mac. To run it here instead, run:" >&2
  echo "  $(local_cmd)" >&2
  exit "$code"
}
pickup_cmd() {
  local a s=""
  for a in ${ORIG_ARGS[@]+"${ORIG_ARGS[@]}"}; do s="$s $(q "$a")"; done
  printf '(cd %s && REMOTE_JOB=%s bash %s%s)' "$(q "$CALLER_PWD")" "$JOB" "$(q "$SELF")" "$s"
}

# absolute, with symlinks resolved in the part that exists (so a symlinked path and /tmp/...
# map the same way as their real paths)
canon() {
  local p="$1" tail="" d
  [[ "$p" == /* ]] || p="$CALLER_PWD/$p"
  while [[ "$p" == */ && "$p" != / ]]; do p="${p%/}"; done
  d="$p"
  while [[ ! -d "$d" ]]; do tail="/$(basename "$d")$tail"; d="$(dirname "$d")"; done
  d="$(cd "$d" && pwd -P)"
  if [[ "$d" == / ]]; then printf '/%s' "${tail#/}"; else printf '%s%s' "$d" "$tail"; fi
}

IN_ABS=(); OUT_ABS=(); OUT_DIRHINT=()
for p in ${INS[@]+"${INS[@]}"}; do
  [[ -e "$p" ]] || die 64 "input not found: $p"
  IN_ABS+=("$(canon "$p")")
done
for p in ${OUTS[@]+"${OUTS[@]}"}; do
  a="$(canon "$p")"
  [[ "$a" != / && "$a" != "$KIT_ROOT" && "$a" != "$HOME" ]] || die 64 "refusing to copy back over $a"
  OUT_ABS+=("$a")
  if [[ "$p" == */ || -d "$p" ]]; then OUT_DIRHINT+=(1); else OUT_DIRHINT+=(0); fi
done

# is <abs path> one the worker has a copy of (so a command argument naming it gets rewritten)?
is_mapped() {
  local p="$1" x
  case "$p" in "$KIT_ROOT"|"$KIT_ROOT"/*) return 0 ;; esac
  for x in ${IN_ABS[@]+"${IN_ABS[@]}"} ${OUT_ABS[@]+"${OUT_ABS[@]}"}; do
    [[ "$p" == "$x" || "$p" == "$x"/* ]] && return 0
    x="$(dirname "$x")"
    [[ "$x" != / && ( "$p" == "$x" || "$p" == "$x"/* ) ]] && return 0
  done
  return 1
}
map_word() {
  local w="$1" pre="" p slash=""
  if [[ "$w" =~ ^(--?[A-Za-z0-9][A-Za-z0-9_.-]*=|[A-Za-z_][A-Za-z0-9_]*=)(/.*)$ ]]; then
    pre="${BASH_REMATCH[1]}"; w="${BASH_REMATCH[2]}"
  fi
  if [[ "$w" == /* && "$w" != / ]]; then
    p="$(canon "$w")"
    [[ "$w" == */ ]] && slash=/
    if is_mapped "$p"; then printf '%s%s/%s%s' "$pre" "$RHOME" "$(to_worker "$p")" "$slash"; return; fi
  fi
  printf '%s' "$1"
}

LABEL="${LABEL:-$(basename "${CMD[0]}")}"
LABEL="$(printf '%s' "$LABEL" | tr -c 'A-Za-z0-9._-' '-' | cut -c1-40)"

# ---- worker
worker_select || die 64 "$WL_ERR"
say "worker $W_NAME ($DEST): checking it is reachable"
needs=""; for t in ${NEEDS[@]+"${NEEDS[@]}"}; do needs="$needs $(q "$t")"; done
PRE="$(wssh "set --$needs; for t in \"\$@\"; do command -v \"\$t\" >/dev/null || echo \"MISSING \$t\"; done; echo \"HOME \$HOME\"" 2>/dev/null)" ||
  die_local 75 "Can't reach the worker laptop $W_NAME at $W_ADDR. Check it is switched on, plugged in, awake and on the same network or VPN."
if grep -q '^MISSING' <<< "$PRE"; then
  die_local 75 "The worker $W_NAME is reachable but is missing: $(sed -n 's/^MISSING //p' <<< "$PRE" | tr '\n' ' ')"
fi
RHOME="$(sed -n 's/^HOME //p' <<< "$PRE")"
[[ "$RHOME" == /* ]] || die_local 75 "The worker $W_NAME did not report its home folder."

RCMD=(); for w in "${CMD[@]}"; do RCMD+=("$(map_word "$w")"); done
RCWD="$RHOME/$(to_worker "$CALLER_PWD")"
ROUT=(); for a in ${OUT_ABS[@]+"${OUT_ABS[@]}"}; do ROUT+=("$RHOME/$(to_worker "$a")"); done
RBASE="$RHOME/render-remote"
RLOCK="$RBASE/lock"
JOB="${REMOTE_JOB:-$LABEL-$(date +%Y%m%d-%H%M%S)-$$}"
RJOB="$RBASE/jobs/$JOB"
TMPF="$(mktemp -t run-on-worker)"

HOLDING=0; STARTED=0
on_exit() { rm -f "$TMPF"; if [[ "$HOLDING" == "1" && "$STARTED" == "0" ]]; then worker_release_lock "$RLOCK" "$JOB"; fi; }
trap on_exit EXIT
on_signal() {
  echo
  if [[ "$STARTED" == "1" ]]; then
    say "stopped following. The job keeps going on $W_NAME. To copy its results back when it is done:"
    say "  $(pickup_cmd)"
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
      [[ $fails -lt 5 ]] || die_local 75 "Lost contact with the worker $W_NAME while waiting for it to be free."
      sleep "$WAIT_POLL_SECS"; continue
    fi
    fails=0
    case "$R" in
      GOT*)
        HOLDING=1
        [[ "$R" == GOT_STALE* ]] && say "cleared a lock left by a job that is no longer running (${R#GOT_STALE })"
        [[ $waited == 1 ]] && say "worker is free after $(mmss $(( $(date +%s) - t_wait ))) of waiting"
        break ;;
      BUSY*)
        read -r _ holder since <<< "$R"
        now=$(date +%s)
        if [[ $waited == 0 ]]; then
          say "worker $W_NAME is busy with $holder (since $(date -r "$since" +%H:%M)); this job waits its turn"
          waited=1; last_note=$now
        elif (( now - last_note >= 60 )); then
          say "still waiting for $holder ($(mmss $(( now - t_wait ))) so far)"; last_note=$now
        fi
        sleep "$WAIT_POLL_SECS" ;;
      *) die_local 75 "Unexpected answer from the worker $W_NAME: $R" ;;
    esac
  done

  # ---- 2. copy the inputs
  say "job $JOB: copying ${#IN_ABS[@]} input(s) to $W_NAME"
  t_sync=$(date +%s)
  PARENTS=("$RJOB" "$RCWD")
  for a in ${IN_ABS[@]+"${IN_ABS[@]}"}; do PARENTS+=("$(dirname "$RHOME/$(to_worker "$a")")"); done
  for ((i = 0; i < ${#ROUT[@]}; i++)); do
    if [[ "${OUT_DIRHINT[$i]}" == 1 ]]; then PARENTS+=("${ROUT[$i]}"); else PARENTS+=("$(dirname "${ROUT[$i]}")"); fi
  done
  mk="mkdir -p"; for d in "${PARENTS[@]}"; do mk="$mk $(q "$d")"; done
  wssh "$mk" || die_local 75 "Could not create folders on the worker $W_NAME."
  for a in ${IN_ABS[@]+"${IN_ABS[@]}"}; do
    dst="$(dirname "$RHOME/$(to_worker "$a")")/"
    if [[ -d "$a" ]]; then
      rsync -a -e "$RSH" --exclude '.bak-*' "$a" "$DEST:$dst" || die_local 75 "Copying $a to the worker $W_NAME failed."
    else
      rsync -aL -e "$RSH" "$a" "$DEST:$dst" || die_local 75 "Copying $a to the worker $W_NAME failed."
    fi
  done
  say "copied in $(mmss $(( $(date +%s) - t_sync )))"

  # the command's own program must exist there (after the copy, in case it was one of the inputs)
  wssh "cd $(q "$RCWD") && command -v $(q "${RCMD[0]}") >/dev/null" 2>/dev/null ||
    die_local 75 "The worker $W_NAME has no program called ${CMD[0]} (as ${RCMD[0]})."

  # ---- 3. start the command on the worker, detached
  {
    echo '#!/bin/bash'
    echo "# written by run-on-worker.sh on $(hostname -s) at $(date '+%Y-%m-%d %H:%M %Z')"
    echo "CWD=$(q "$RCWD")"
    printf 'CMD=('; for a in "${RCMD[@]}"; do printf ' %q' "$a"; done; echo ' )'
    printf 'OUTS=('; for a in ${ROUT[@]+"${ROUT[@]}"}; do printf ' %q' "$a"; done; echo ' )'
    worker_run_preamble "$JOB" "$RLOCK" "$RJOB" "job"
    cat <<'EOF'
mkdir -p out
echo "[worker] $(date '+%H:%M:%S') in $CWD: ${CMD[*]}" >> log
( cd "$CWD" && "${CMD[@]}" ) >> log 2>&1
rc=$?
if [ "$rc" = 0 ]; then
  # keep this job's own copies, so the next job on this worker cannot overwrite them before
  # the Mac copies them back (APFS clones: instant, no extra space)
  for i in "${!OUTS[@]}"; do
    o="${OUTS[$i]}"
    [ -e "$o" ] || { echo "[worker] result missing: $o" >> log; continue; }
    cp -cR "$o" "out/$i" 2>/dev/null || { rm -rf "out/$i"; cp -R "$o" "out/$i"; } ||
      { echo "[worker] could not keep a copy of $o" >> log; rc=96; }
  done
fi
echo "[worker] $(date '+%H:%M:%S') finished, exit $rc" >> log
finish "$rc"
EOF
  } | wssh "mkdir -p $(q "$RJOB") && cat > $(q "$RJOB/run.sh")" || die_local 75 "Could not send the job to the worker $W_NAME."
  worker_launch "$RJOB/run.sh" || die_local 75 "Could not start the job on the worker $W_NAME."
  STARTED=1; HOLDING=0
  say "running on $W_NAME (job $JOB). Safe to lose the connection: it keeps going there."
else
  say "picking up job $JOB on $W_NAME"
  STARTED=1
fi

# ---- 4. follow the worker's log
[[ -z "$LOGFILE" ]] || : > "$LOGFILE"
t_start=$(date +%s); last_print=$t_start; off=0; first_fail=0; STATUS=""
while :; do
  if wssh "cd $(q "$RJOB") 2>/dev/null || { echo missing; exit 0; }; if [ -f exit ]; then cat exit; else echo running; fi; tail -c +$((off + 1)) log 2>/dev/null; true" > "$TMPF" 2>/dev/null; then
    if [[ $first_fail != 0 ]]; then say "back in contact with $W_NAME"; first_fail=0; fi
    STATUS="$(head -1 "$TMPF")"
    hb=$(head -1 "$TMPF" | wc -c | tr -d ' ')
    tb=$(wc -c < "$TMPF" | tr -d ' ')
    if (( tb > hb )); then
      tail -c +$((hb + 1)) "$TMPF"
      [[ -z "$LOGFILE" ]] || tail -c +$((hb + 1)) "$TMPF" >> "$LOGFILE"
      off=$((off + tb - hb)); last_print=$(date +%s)
    fi
    [[ "$STATUS" == "missing" ]] && die 64 "there is no job $JOB on the worker $W_NAME"
    [[ "$STATUS" == "running" ]] || break
  else
    now=$(date +%s)
    if [[ $first_fail == 0 ]]; then
      first_fail=$now
      say "lost contact with $W_NAME; retrying. The job keeps going there."
    elif (( now - first_fail >= GIVE_UP_SECS )); then
      say "no contact with $W_NAME for $(mmss $(( now - first_fail ))); stopped following." >&2
      say "When the worker is back, copy the results with:" >&2
      say "  $(pickup_cmd)" >&2
      exit 76
    fi
  fi
  now=$(date +%s)
  if (( now - last_print >= 60 )); then say "still running on $W_NAME ($(mmss $(( now - t_start ))))"; last_print=$now; fi
  sleep "$POLL_SECS"
done

[[ "$STATUS" =~ ^[0-9]+$ ]] || die 77 "the worker $W_NAME wrote an unreadable exit status ($STATUS) for job $JOB"
if [[ "$STATUS" != "0" ]]; then
  say "the command failed on $W_NAME (exit $STATUS). Nothing was copied back; the worker's log is ~/render-remote/jobs/$JOB/log there." >&2
  exit "$STATUS"
fi

# ---- 5. copy the results back
if [[ ${#OUT_ABS[@]} -gt 0 ]]; then
  say "copying ${#OUT_ABS[@]} result(s) back from $W_NAME"
  ids=""; for ((i = 0; i < ${#OUT_ABS[@]}; i++)); do ids="$ids $i"; done
  KINDS="$(wssh "cd $(q "$RJOB/out") 2>/dev/null || exit 0; for i in$ids; do if [ -d \"\$i\" ]; then echo D; elif [ -e \"\$i\" ]; then echo F; else echo M; fi; done")" ||
    die 77 "could not list the results on $W_NAME; retry with: $(pickup_cmd)"
  kinds=(); while IFS= read -r k; do [[ -n "$k" ]] && kinds+=("$k"); done <<< "$KINDS"
  [[ ${#kinds[@]} -eq ${#OUT_ABS[@]} ]] || die 77 "the results of job $JOB are no longer on $W_NAME (already copied back, or tidied)"
  bad=0
  for ((i = 0; i < ${#OUT_ABS[@]}; i++)); do
    a="${OUT_ABS[$i]}"
    case "${kinds[$i]}" in
      D) mkdir -p "$a" && rsync -a -e "$RSH" "$DEST:$RJOB/out/$i/" "$a/" && say "wrote $a/" ||
           { say "copying back $a failed" >&2; bad=1; } ;;
      F) mkdir -p "$(dirname "$a")" && rsync -a -e "$RSH" "$DEST:$RJOB/out/$i" "$a" && say "wrote $a" ||
           { say "copying back $a failed" >&2; bad=1; } ;;
      *) say "the command did not write $a on $W_NAME" >&2; bad=1 ;;
    esac
  done
  [[ $bad == 0 ]] || die 77 "not every result came back. To retry the copy: $(pickup_cmd)"
  # the job's copies are now on this Mac; drop them on the worker (log and run.sh stay)
  wssh "rm -rf $(q "$RJOB/out")" || say "note: could not tidy $RJOB/out on $W_NAME (harmless)"
fi
say "done in $(mmss $(( $(date +%s) - t_start ))) on $W_NAME (job $JOB)"
exit 0
