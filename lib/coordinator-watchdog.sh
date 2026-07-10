#!/usr/bin/env bash
# coordinator-watchdog.sh — Portable timeout and cooperative loop watchdog library
#
# Purpose: provides two primitives for bounding long-running operations without
# requiring GNU coreutils:
#
#   cs_timeout <secs> -- <cmd...>
#       Runs <cmd...> with a wall-clock cap of <secs> seconds. Uses system
#       `timeout` / `gtimeout` when available; falls back to a background-kill
#       approach on macOS and other systems lacking the tool. Returns 124 on
#       timeout (mirroring GNU timeout's exit code contract), or the command's
#       own exit code on normal exit.
#
#   cs_watchdog_check <ceiling_secs> <stall_count> <interval_secs> <probe_cmd...>
#       Cooperative per-iteration check intended to be called at the TOP of a
#       long-running loop. Returns non-zero ("bail") when the wall-clock ceiling
#       is exceeded OR when the probe command's output has been unchanged for
#       <stall_count> consecutive calls. NO backgrounding — executes in the
#       caller's shell so caller accumulators survive.
#
#   cs_watchdog_reset
#       Clears all watchdog state so a fresh cs_watchdog_check cycle can begin.
#
# Source this file; do NOT execute it directly. Safe to source multiple times.
#
# Spec backlink: docs/plans/2026-06-27-coordinator-watchdog.md
#
# NEGATIVE-SPECS (hard):
#   - Do NOT use `wait -n` (bash 4.3+); single-PID `wait` only (bash 4.0 floor).
#   - Sentinel/temp files: mktemp "${TMPDIR:-/tmp}/coordinator-watchdog.XXXXXX"
#     — Xs at the END, no trailing extension suffix (BSD mktemp discipline).
#   - D-state (uninterruptible I/O) processes cannot be SIGKILLed by the OS;
#     cs_timeout guarantees "bail and return control", not "guaranteed terminate".
#   - cs_timeout Branch B sentinel: proves the killer's timer fired, NOT that the
#     target process was successfully terminated. A process exiting at exactly the
#     secs boundary can race the sentinel write → spurious exit 124. Inherent
#     limitation; do NOT claim or rely on the sentinel check being race-free.
#
# Library hygiene:
#   - BASH_VERSINFO < 4 guard with brew-bash remediation (DR-148).
#   - Functions and module-level state variables ONLY at source time; no
#     other top-level executable statements.
#   - Idempotent: safe to source multiple times (guard at bottom).

# ---------------------------------------------------------------------------
# Bash version guard (DR-148) — must be reachable on bash 3.2 (guard syntax
# parses on 3.2 even though the features below require 4.0+).
# ---------------------------------------------------------------------------
if [[ "${BASH_VERSINFO[0]}" -lt 4 ]]; then
  printf 'ERROR: coordinator-watchdog.sh requires bash >= 4 (have %s).\n' "${BASH_VERSION}" >&2
  printf '  Install via: brew install bash  # macOS\n' >&2
  printf '  Or: sudo apt-get install bash   # Debian/Ubuntu\n' >&2
  return 2 2>/dev/null || exit 2
fi

# ---------------------------------------------------------------------------
# Idempotent source guard
# ---------------------------------------------------------------------------
if [[ -n "${_COORDINATOR_WATCHDOG_LOADED:-}" ]]; then
  return 0 2>/dev/null || true
fi
_COORDINATOR_WATCHDOG_LOADED=1

# ---------------------------------------------------------------------------
# cs_timeout <secs> -- <cmd...>
#   Portable single-command wall-clock cap.
#
#   Branch A (tool present): delegates to timeout / gtimeout and returns its
#   exit code verbatim (GNU timeout already returns 124 on timeout).
#
#   Branch B (tool absent, macOS default): runs <cmd...> in the background,
#   starts a parallel killer subshell that writes a sentinel flag-file before
#   sending SIGTERM (then SIGKILL after a grace period). After wait on the
#   command PID, returns 124 if the sentinel exists (killer's timer fired; see
#   NEGATIVE-SPECS for the inherent race-window caveat) or the command's own
#   exit code otherwise. Cleans up sentinel + killer.
#
#   NOTE — D-state guarantee: a process in uninterruptible disk-IO (D-state)
#   cannot be SIGKILLed by the kernel; this function guarantees "bail and return
#   control to the caller", not "the child process is guaranteed to be gone".
# ---------------------------------------------------------------------------
cs_timeout() {
  local secs="${1:?cs_timeout: secs required}"
  shift
  # Consume the optional '--' separator
  if [[ "${1:-}" == "--" ]]; then
    shift
  fi
  if [[ $# -eq 0 ]]; then
    printf 'cs_timeout: no command given after --\n' >&2
    return 1
  fi

  # Branch A: delegate to system timeout / gtimeout
  local _timeout_bin=""
  if command -v timeout &>/dev/null; then
    _timeout_bin="timeout"
  elif command -v gtimeout &>/dev/null; then
    _timeout_bin="gtimeout"
  fi

  if [[ -n "$_timeout_bin" ]]; then
    "$_timeout_bin" "$secs" "$@"
    return $?
  fi

  # Branch B: background-kill fallback (macOS, minimal-coreutils environments)
  local _sentinel _cmd_pid _killer_pid _cmd_rc _grace=2 _monitor_was_set=0

  # BSD mktemp discipline: Xs at the END, no trailing extension suffix
  _sentinel=$(mktemp "${TMPDIR:-/tmp}/coordinator-watchdog.XXXXXX")

  # Remove sentinel immediately so its PRESENCE later is unambiguous (the killer
  # writes it; an absent sentinel means the command finished on its own).
  rm -f "$_sentinel"

  # Run command in background; capture PID
  "$@" &
  _cmd_pid=$!

  # Start killer subshell: writes sentinel BEFORE sending signals. The sentinel
  # proves the killer's timer fired — NOT that kill() succeeded. A process that
  # exits naturally at exactly <secs> can race the sentinel write, yielding a
  # spurious 124. This sub-ms race window is inherent to the background-kill
  # approach and cannot be eliminated in pure bash (see NEGATIVE-SPECS).
  # D-state caveat: SIGKILL may not terminate a process wedged in uninterruptible
  # IO; we still return control to the caller after wait returns (which may take
  # longer than expected in pathological cases).
  #
  # FD-REDIRECT (load-bearing fix for $(...) pipe-orphan stall): redirect all fds
  # to /dev/null so neither the killer subshell nor its `sleep` grandchild can hold
  # the caller's stdout open. When cs_timeout runs inside $(...) the pipe write-end
  # stays open until every inheritor closes it; without this redirect the orphaned
  # `sleep <secs>` grandchild blocks $(...) for the full window even after the
  # wrapped command exits. Sentinel goes to a file; the killer needs no stdio.
  #
  # PROCESS-GROUP (belt-and-braces): set -m (monitor / job-control mode, bash 4+)
  # makes the killer a process-group leader so kill -- -$_killer_pid reaps its
  # `sleep` grandchild too, not just the subshell. Best-effort: set -m may be a
  # no-op in non-interactive contexts; the fd-redirect above is load-bearing and
  # sufficient on its own.
  [[ "$-" == *m* ]] && _monitor_was_set=1
  set -m 2>/dev/null || true
  (
    sleep "$secs"
    # Write sentinel FIRST — before any kill attempt
    # Per-command redirect > "$_sentinel" takes precedence over the subshell-level
    # >/dev/null 2>&1 for this one line — standard bash redirect layering, not a bug.
    printf '1' > "$_sentinel" 2>/dev/null
    kill -TERM "$_cmd_pid" 2>/dev/null
    sleep "$_grace"
    kill -KILL "$_cmd_pid" 2>/dev/null
  ) >/dev/null 2>&1 </dev/null &
  _killer_pid=$!
  # W1 mitigation: disown removes the killer from bash's job table so bash does not
  # print "[N]+ Done/Terminated" to stderr when it exits. The pid is already captured;
  # wait "$_killer_pid" still reaps a disowned direct-child via waitpid(), and both
  # callers below have || true so a disowned-pid wait returning non-zero is harmless.
  disown "$_killer_pid" 2>/dev/null || true
  [[ "$_monitor_was_set" -eq 0 ]] && { set +m 2>/dev/null || true; }

  # Wait on the command's PID only (NOT wait -n — bash 4.0 floor requires single-PID wait)
  wait "$_cmd_pid" 2>/dev/null
  _cmd_rc=$?

  # Check sentinel: if present, killer's timer fired → exit 124 (mirrors GNU timeout; see NEGATIVE-SPECS race note)
  if [[ -f "$_sentinel" ]]; then
    # Clean up: kill process group (reaps sleep grandchild too); fall back to pid kill
    kill -- -"$_killer_pid" 2>/dev/null || kill "$_killer_pid" 2>/dev/null
    wait "$_killer_pid" 2>/dev/null || true
    rm -f "$_sentinel"
    return 124
  fi

  # Normal exit: kill process group (reaps sleep grandchild too); fall back to pid kill
  kill -- -"$_killer_pid" 2>/dev/null || kill "$_killer_pid" 2>/dev/null
  wait "$_killer_pid" 2>/dev/null || true
  rm -f "$_sentinel"
  return "$_cmd_rc"
}

# ---------------------------------------------------------------------------
# Watchdog state — module-level variables (bash 4.0: no declare -A needed;
# simple scalar variables keyed by a fixed prefix are sufficient and more
# portable than associative arrays for a single-instance watchdog).
#
# False-stall tradeoff: if the probe command's granularity is coarser than the
# actual operation's progress (e.g., a line-count probe on a file that grows in
# large bursts), stall detection can fire on a legitimately-progressing loop.
# The caller should tune <stall_count> and <interval_secs> to allow for the
# worst-case burst gap, or use a finer-grained probe.
# ---------------------------------------------------------------------------
_CW_START_EPOCH=0
_CW_LAST_PROBE=""
_CW_STALL_COUNTER=0
_CW_INITIALIZED=0

# _cw_now_epoch: seconds since epoch (portable)
# Review: code-reviewer S1 (F8) — emit warning on date failure; silent 0 disables ceiling invisibly
_cw_now_epoch() {
  local _epoch
  if ! _epoch=$(date +%s 2>/dev/null) || [[ -z "$_epoch" ]]; then
    printf 'cs_watchdog: WARNING — date +%%s failed; elapsed-time ceiling disabled\n' >&2
    echo 0
    return
  fi
  echo "$_epoch"
}

# ---------------------------------------------------------------------------
# cs_watchdog_reset
#   Clear all watchdog state so a fresh cs_watchdog_check cycle can begin.
#   Call between distinct long-running-loop phases.
# ---------------------------------------------------------------------------
cs_watchdog_reset() {
  _CW_START_EPOCH=0
  _CW_LAST_PROBE=""
  _CW_STALL_COUNTER=0
  _CW_INITIALIZED=0
}

# ---------------------------------------------------------------------------
# cs_watchdog_check <ceiling_secs> <stall_count> <interval_secs> <probe_cmd...>
#   Cooperative per-iteration watchdog check. Call at the TOP of each loop body.
#
#   Arguments:
#     ceiling_secs  — maximum total wall-clock seconds for the loop
#     stall_count   — bail after this many consecutive identical probe outputs
#                     following the first (initializing) call; first call sets
#                     the baseline and never increments the stall counter
#     interval_secs — expected caller polling cadence in seconds (advisory-only;
#                     currently not used in stall-detection math — stall detection
#                     uses the consecutive identical-output counter exclusively)
#     probe_cmd...  — command whose stdout is sampled each call; unchanged output
#                     for stall_count consecutive calls signals a stall
#
#   Returns:
#     0  — continue the loop (within ceiling, probe progressing)
#     1  — bail: ceiling exceeded
#     2  — bail: stall detected (probe unchanged for stall_count iterations)
#
#   Probe-failure handling: if <probe_cmd...> exits non-zero, the stall counter
#   is NOT incremented (no signal → can't conclude stall). The wall-clock ceiling
#   check still applies. A one-line warning is emitted to stderr.
#   NEVER silently bails on a probe error — the warning is mandatory.
#
#   False-stall tradeoff (see module-level comment above).
#
#   NO backgrounding — runs entirely in the caller's shell.
# ---------------------------------------------------------------------------
cs_watchdog_check() {
  local ceiling_secs="${1:?cs_watchdog_check: ceiling_secs required}"
  local stall_count="${2:?cs_watchdog_check: stall_count required}"
  local interval_secs="${3:?cs_watchdog_check: interval_secs required}"
  shift 3

  if [[ $# -eq 0 ]]; then
    printf 'cs_watchdog_check: no probe_cmd given\n' >&2
    return 1
  fi

  local now
  now=$(_cw_now_epoch)

  # Initialize on first call
  if [[ "$_CW_INITIALIZED" -eq 0 ]]; then
    _CW_START_EPOCH="$now"
    _CW_LAST_PROBE=""
    _CW_STALL_COUNTER=0
    _CW_INITIALIZED=1
  fi

  # --- Ceiling check ---
  local elapsed=$(( now - _CW_START_EPOCH ))
  if [[ "$elapsed" -ge "$ceiling_secs" ]]; then
    printf 'cs_watchdog_check: ceiling exceeded (%ss elapsed >= %ss limit)\n' \
      "$elapsed" "$ceiling_secs" >&2
    return 1
  fi

  # --- Probe ---
  local probe_out probe_rc
  probe_out=$("$@" 2>/dev/null)
  probe_rc=$?

  if [[ "$probe_rc" -ne 0 ]]; then
    # Probe failure: warn, do NOT increment stall counter, do NOT bail on this alone
    printf 'cs_watchdog_check: probe command exited %d (no signal) — stall counter unchanged\n' \
      "$probe_rc" >&2
    return 0
  fi

  # --- Stall check ---
  if [[ "$probe_out" == "$_CW_LAST_PROBE" && "$_CW_INITIALIZED" -gt 1 ]]; then
    _CW_STALL_COUNTER=$(( _CW_STALL_COUNTER + 1 ))
    if [[ "$_CW_STALL_COUNTER" -ge "$stall_count" ]]; then
      printf 'cs_watchdog_check: stall detected (%d consecutive identical probe outputs)\n' \
        "$_CW_STALL_COUNTER" >&2
      return 2
    fi
  else
    _CW_STALL_COUNTER=0
  fi

  _CW_LAST_PROBE="$probe_out"
  # Use a value > 1 after the first real call so the stall-equality test above
  # can distinguish "first call" (no previous output to compare) from "second call
  # with same output" (genuine stall candidate).
  _CW_INITIALIZED=$(( _CW_INITIALIZED + 1 ))

  return 0
}
