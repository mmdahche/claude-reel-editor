# shellcheck shell=bash
# OPTIONAL. Shared worker-laptop plumbing for editors who have a second Mac to offload heavy jobs
# to. Nothing in the kit needs it: every step runs locally by default. Sourced (never run) by:
#   scripts/remote/run-on-worker.sh     (any heavy job)
#   scripts/remote/render-remote.sh     (video renders)
# One copy of the rules both must agree on: which worker, how to reach it, where a path on this
# Mac lives on the worker, and the worker lock (~/render-remote/lock) that keeps one heavy job at a
# time per machine. A job is ~/render-remote/jobs/<job>/run.sh on the worker; the lock's stale
# check depends on that path, so every job must live there.
#
# Provides:
#   KIT_ROOT                      this machine's kit folder (symlinks resolved)
#   to_worker <abs path>          that path on the worker, relative to the worker's home
#   worker_select                 reads workers.conf (WORKER=, WORKERS_CONF=); sets W_NAME W_USER
#                                 W_ADDR W_ALIAS W_KEY SSH_OPTS DEST RSH. Returns 1 with WL_ERR set.
#   wssh <cmd...>                 ssh to the selected worker
#   worker_try_lock <lock> <job> <stale secs>    prints GOT, GOT_STALE <holder> or BUSY <holder> <since>
#   worker_release_lock <lock> <job>             frees the lock if <job> holds it and never started
#   worker_run_preamble <job> <lock> <jobdir> <what>   prints the shared head of a run.sh (sets
#                                 JOB LOCK JOBDIR, defines finish <rc>, checks the lock, records
#                                 the pid, traps signals, touches "started")
#   worker_launch <run.sh path on the worker>    starts it fully detached

KIT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
WL_DEFAULT_CONF="$KIT_ROOT/scripts/remote/workers.conf"
# where the kit lives on the worker, relative to the worker's home (env WORKER_KIT_DIR to change)
WL_KIT_DIR="${WORKER_KIT_DIR:-claude-reel-kit}"
WL_ERR=""

# where a path on this Mac lives on the worker, relative to the worker's home
to_worker() {
  case "$1" in
    "$KIT_ROOT") printf '%s' "$WL_KIT_DIR" ;;
    "$KIT_ROOT"/*) printf '%s/%s' "$WL_KIT_DIR" "${1#"$KIT_ROOT"/}" ;;
    *) printf 'render-remote/external%s' "$1" ;;
  esac
}

worker_select() {
  local conf="${WORKERS_CONF:-$WL_DEFAULT_CONF}" line
  if [[ ! -f "$conf" ]]; then WL_ERR="no worker list at $conf (copy scripts/remote/workers.conf.example to workers.conf and fill it in)"; return 1; fi
  line="$(awk -v w="${WORKER:-}" '!/^[[:space:]]*(#|$)/ && NF >= 5 && (w == "" || $1 == w) { print; exit }' "$conf")"
  if [[ -z "$line" ]]; then WL_ERR="no worker ${WORKER:+named $WORKER }in $conf"; return 1; fi
  read -r W_NAME W_USER W_ADDR W_ALIAS W_KEY <<< "$line"
  case "$W_KEY" in "~/"*) W_KEY="$HOME/${W_KEY#\~/}" ;; esac
  SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=4
    -o IdentitiesOnly=yes -i "$W_KEY")
  [[ "$W_ALIAS" == "-" ]] || SSH_OPTS+=(-o "HostKeyAlias=$W_ALIAS")
  DEST="$W_USER@$W_ADDR"
  RSH="ssh ${SSH_OPTS[*]}"
  return 0
}

wssh() { ssh "${SSH_OPTS[@]}" "$DEST" "$@"; }

worker_release_lock() {
  wssh bash -s -- "$1" "$2" <<'EOF' >/dev/null 2>&1 || true
[ "$(cat "$1/job" 2>/dev/null)" = "$2" ] && [ ! -f "$1/pid" ] && rm -rf "$1"
EOF
}

# take the worker's lock, or report who holds it; a lock whose job died is cleared
worker_try_lock() {
  wssh bash -s -- "$1" "$2" "$3" <<'EOF'
L="$1"; JOB="$2"; STALE="$3"
mkdir -p "$(dirname "$L")/jobs"
take() { echo "$JOB" > "$L/job"; date +%s > "$L/since"; }
if mkdir "$L" 2>/dev/null; then take; echo GOT; exit 0; fi
holder="$(cat "$L/job" 2>/dev/null || echo unknown)"
since="$(cat "$L/since" 2>/dev/null || stat -f %m "$L" 2>/dev/null || date +%s)"
pid="$(cat "$L/pid" 2>/dev/null || true)"
stale=0
if [ -n "$pid" ]; then
  ps -p "$pid" -o command= 2>/dev/null | grep -q 'render-remote/jobs/.*/run\.sh' || stale=1
elif [ $(( $(date +%s) - since )) -gt "$STALE" ]; then
  stale=1
fi
if [ "$stale" = 1 ]; then
  rm -rf "$L"
  if mkdir "$L" 2>/dev/null; then take; echo "GOT_STALE $holder"; exit 0; fi
fi
echo "BUSY $holder $since"
EOF
}

worker_run_preamble() {
  echo "JOB=$(printf '%q' "$1"); LOCK=$(printf '%q' "$2"); JOBDIR=$(printf '%q' "$3")"
  echo "WHAT=$(printf '%q' "$4")"
  cat <<'EOF'
cd "$JOBDIR" || exit 1
release() { [ "$(cat "$LOCK/job" 2>/dev/null)" = "$JOB" ] && rm -rf "$LOCK"; }
finish() { echo "$1" > exit.tmp && mv exit.tmp exit; release; }
if [ "$(cat "$LOCK/job" 2>/dev/null)" != "$JOB" ]; then
  echo "[remote] this job does not hold the worker lock; not starting" >> log; finish 97; exit 1
fi
echo $$ > "$LOCK/pid"
trap 'echo "[remote] $WHAT stopped by a signal on the worker" >> log; finish 98; exit 1' TERM INT
touch started; sleep 1
EOF
}

# </dev/null matters: without it HyperFrames cancels with render_cancelled_parent_exited
worker_launch() { wssh "nohup bash $(printf '%q' "$1") </dev/null >/dev/null 2>&1 & disown"; }
