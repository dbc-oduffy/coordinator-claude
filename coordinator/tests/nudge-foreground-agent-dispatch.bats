#!/usr/bin/env bats
# nudge-foreground-agent-dispatch.bats — bats tests for
# hooks/scripts/nudge-foreground-agent-dispatch.sh
#
# Purpose: regression coverage for the PreToolUse foreground-Agent-dispatch deny hook.
#   Two load-bearing invariants:
#     (1) Brick-proof (CASE A/A2/A4): on a param-less build, or a fresh session that
#         has not yet proven the build exposes run_in_background, an absent key MUST
#         pass — denying there is unsatisfiable and bricks the session
#         (project-rag-ue-addon-em memo, 2026-06-21).
#     (2) Hole-closed (CASE A3): once any dispatch this session carries the key
#         (proving the param exists, e.g. Claude Code 2.1.178 which re-exposed it),
#         a later absent key is a deliberate foreground omission → DENY.
#   So: present-and-true → pass + calibrate; present-and-false → deny; absent → deny
#   only if the session is calibrated, else pass. Capability is LEARNED per session
#   via a session-scoped sentinel, never key-presence of a single call alone.
#
# Spec backlink: cross-repo/inbox/2026-06-21-agent-tool-missing-run-in-background-param.md
#
# Run: npx bats plugins/coordinator-claude/coordinator/tests/nudge-foreground-agent-dispatch.bats
#      from the ~/.claude repo root.
#      (Override subject: FG_HOOK=/abs/path npx bats <file>)
#
# Portability (DR-148): bash >= 4 + BSD coreutils; no grep -P / date -d / sed -i.

SCRIPT_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")" && pwd)"
SUBJECT="${FG_HOOK:-${SCRIPT_DIR}/../hooks/scripts/nudge-foreground-agent-dispatch.sh}"

# File-global temp repo path used by CASE A3/A4 and cleaned up by teardown.
# Review: code-reviewer — teardown safety net so a failing assertion never leaks
# a temp git repo; the variable is populated per-test and reset to "" after cleanup.
repo=""

teardown() {
  [ -n "${repo:-}" ] && rm -rf "$repo"
  repo=""
}

# ---------------------------------------------------------------------------
# CASE A — param ABSENT (this-harness reproduction): tool_input carries no
# run_in_background key. Hook MUST pass silently (exit 0, no deny). This is the
# bug the memo reported: the old `// false` default denied here and bricked the
# session. Mirrors the real Agent param set on Claude Code 2.1.176.
# ---------------------------------------------------------------------------

@test "CASE A: param absent (no run_in_background key) → silent pass" {
  local payload='{"tool_name":"Agent","tool_input":{"description":"x","subagent_type":"Explore","prompt":"go"}}'
  run bash "$SUBJECT" <<< "$payload"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

# ---------------------------------------------------------------------------
# CASE A2 — tool_input ITSELF absent (not just the key within it). All three
# extraction paths must treat this as param-absent → pass. The hook's history
# is one missing-key assumption causing an outage, so cover the empty-input
# shape explicitly rather than rely on it falling out of CASE A.
# ---------------------------------------------------------------------------

@test "CASE A2: tool_input entirely absent → silent pass" {
  local payload='{"tool_name":"Agent"}'
  run bash "$SUBJECT" <<< "$payload"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

# ---------------------------------------------------------------------------
# CASE A3 — calibrated deny: once any dispatch this session carries the key
# (proving the build exposes the param, e.g. Claude Code 2.1.178), a LATER
# absent-key dispatch in the same session is a deliberate foreground omission
# and MUST deny. This is the hole the key-presence-only rule left open on 2.1.178.
# Requires session_id + a git root so the session-scoped sentinel can be written.
# ---------------------------------------------------------------------------

@test "CASE A3: present-key calibrates session, later absent-key → deny" {
  # Review: code-reviewer — cleanup moved after assertions so a failing assertion
  # preserves the temp repo + sentinel for debugging; teardown() is the safety net.
  local sid
  repo="$(mktemp -d)"
  ( cd "$repo" && git init -q )
  sid="calsession$$"
  cd "$repo"
  # Backgrounded dispatch calibrates (writes sentinel) and passes silently.
  local cal='{"session_id":"'"$sid"'","tool_name":"Agent","tool_input":{"prompt":"go","run_in_background":true}}'
  run bash "$SUBJECT" <<< "$cal"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
  [ -f "$repo/.git/coordinator-sessions/$sid/.harness-bg-capable" ]
  # Now an absent-key (foreground-by-omission) dispatch in the SAME session denies.
  local fg='{"session_id":"'"$sid"'","tool_name":"Agent","tool_input":{"prompt":"go"}}'
  run bash "$SUBJECT" <<< "$fg"
  [ "$status" -eq 0 ]
  [[ "$output" == *'"deny"'* ]]
  [[ "$output" == *'FOREGROUND AGENT DISPATCH BLOCKED'* ]]
  # teardown() handles rm -rf "$repo"
}

# ---------------------------------------------------------------------------
# CASE A4 — uncalibrated pass (brick-proof fresh session): absent key with a
# resolvable session scope but NO prior present-key dispatch must still pass.
# A fresh session on a param-less build never proves capability, so this is the
# invariant that keeps deny-ALL from bricking the session (memo 2026-06-21).
# ---------------------------------------------------------------------------

@test "CASE A4: absent-key in an uncalibrated session → silent pass" {
  # Review: code-reviewer — cleanup moved after assertions so a failing assertion
  # preserves the temp repo for debugging; teardown() is the safety net.
  local sid
  repo="$(mktemp -d)"
  ( cd "$repo" && git init -q )
  sid="freshsession$$"
  cd "$repo"
  local fg='{"session_id":"'"$sid"'","tool_name":"Agent","tool_input":{"prompt":"go"}}'
  run bash "$SUBJECT" <<< "$fg"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
  # teardown() handles rm -rf "$repo"
}

# ---------------------------------------------------------------------------
# CASE B — param present-and-true: legitimately backgrounded → silent pass.
# ---------------------------------------------------------------------------

@test "CASE B: run_in_background:true → silent pass" {
  local payload='{"tool_name":"Agent","tool_input":{"prompt":"go","run_in_background":true}}'
  run bash "$SUBJECT" <<< "$payload"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

# ---------------------------------------------------------------------------
# CASE C — param present-and-false: foreground deliberately chosen on a build
# that DOES expose the param → hard deny (the hook's reason for existing).
# ---------------------------------------------------------------------------

@test "CASE C: run_in_background:false → deny (with valid-JSON assertion on jq path)" {
  local payload='{"tool_name":"Agent","tool_input":{"prompt":"go","run_in_background":false}}'
  run bash "$SUBJECT" <<< "$payload"
  [ "$status" -eq 0 ]
  [[ "$output" == *'"permissionDecision"'* ]]
  [[ "$output" == *'"deny"'* ]]
  [[ "$output" == *'FOREGROUND AGENT DISPATCH BLOCKED'* ]]
  # Deny output must be valid JSON or the harness silently ignores it and the
  # dispatch passes — defeating the gate. (Was standalone CASE E; folded here.)
  printf '%s' "$output" | python3 -c 'import json,sys; json.load(sys.stdin)'
}

# ---------------------------------------------------------------------------
# CASE D — escape hatch: COORDINATOR_AGENT_FOREGROUND_OK set → pass even when
# the param is present-and-false.
# ---------------------------------------------------------------------------

@test "CASE D: COORDINATOR_AGENT_FOREGROUND_OK=1 overrides present-and-false → silent pass" {
  local payload='{"tool_name":"Agent","tool_input":{"prompt":"go","run_in_background":false}}'
  run env -i HOME="$HOME" PATH="$PATH" COORDINATOR_AGENT_FOREGROUND_OK=1 \
      bash "$SUBJECT" <<< "$payload"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

# ---------------------------------------------------------------------------
# CASE F — fallback parity: with jq AND python masked, the sed substring
# last-resort must still pass on param-absent (CASE A invariant holds with no
# JSON parser available). Stub PATH carries only the coreutils the hook needs
# (bash/cat/sed/timeout), deliberately omitting jq/python/python3 so the
# substring branch is exercised hermetically.
# ---------------------------------------------------------------------------

# Build a PATH dir with symlinks to the essential coreutils but NOT jq/python.
_make_coreutils_only_path() {
  local d="$1" tool p
  for tool in bash cat sed timeout; do
    p="$(command -v "$tool" 2>/dev/null)" && ln -s "$p" "$d/$tool" 2>/dev/null || true
  done
}

@test "CASE F: param absent passes even with no jq/python (sed last-resort)" {
  local payload='{"tool_name":"Agent","tool_input":{"description":"x","prompt":"go"}}'
  local stub_dir
  stub_dir="$(mktemp -d)"
  _make_coreutils_only_path "$stub_dir"
  run env -i HOME="$HOME" PATH="$stub_dir" bash "$SUBJECT" <<< "$payload"
  rm -rf "$stub_dir"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "CASE F2: present-and-false denies even with no jq/python (sed last-resort)" {
  local payload='{"tool_name":"Agent","tool_input":{"prompt":"go","run_in_background":false}}'
  local stub_dir
  stub_dir="$(mktemp -d)"
  _make_coreutils_only_path "$stub_dir"
  run env -i HOME="$HOME" PATH="$stub_dir" bash "$SUBJECT" <<< "$payload"
  rm -rf "$stub_dir"
  [ "$status" -eq 0 ]
  [[ "$output" == *'"deny"'* ]]
  # The no-jq path emits via the heredoc fallback (MSG_ESC + cat <<JSONEOF).
  # A backtick or stray quote in MSG would break the heredoc and the harness
  # would silently ignore the malformed deny → dispatch passes. Validate JSON
  # here too, not just on the jq path (CASE C). python3 is on the bats runner's
  # PATH; only the hook ran under the stub PATH.
  printf '%s' "$output" | python3 -c 'import json,sys; json.load(sys.stdin)'
}

# ---------------------------------------------------------------------------
# CASE F3 — sed fallback calibration: with no jq/python, a present-key dispatch
# (present-and-true) calibrates the session via the sed substring branch, then a
# later absent-key dispatch in the same session denies.
# Review: code-reviewer — exercises the sed last-resort parser's calibration path
# end-to-end; mirrors CASE A3's two-dispatch structure under the stub PATH.
# ---------------------------------------------------------------------------

@test "CASE F3: sed fallback calibrates session (present-true), later absent-key → deny" {
  local stub_dir sid
  stub_dir="$(mktemp -d)"
  _make_coreutils_only_path "$stub_dir"
  # Symlink git + mkdir into the stub dir so the hook can write the capability sentinel
  # (git for rev-parse; mkdir for the sentinel dir creation — not a shell builtin here).
  local git_bin mkdir_bin
  git_bin="$(command -v git 2>/dev/null)"
  [ -n "$git_bin" ] && ln -s "$git_bin" "$stub_dir/git" 2>/dev/null || true
  mkdir_bin="$(command -v mkdir 2>/dev/null)"
  [ -n "$mkdir_bin" ] && ln -s "$mkdir_bin" "$stub_dir/mkdir" 2>/dev/null || true
  # Create a temp git repo and cd into it so git rev-parse succeeds.
  repo="$(mktemp -d)"
  ( cd "$repo" && git init -q )
  sid="sedsession$$"
  cd "$repo"
  # First dispatch: present-and-true under stub PATH — sed branch sets HAS_BG=true,
  # calibration writes sentinel, hook passes silently.
  local cal='{"session_id":"'"$sid"'","tool_name":"Agent","tool_input":{"prompt":"go","run_in_background":true}}'
  run env -i HOME="$HOME" PATH="$stub_dir" bash "$SUBJECT" <<< "$cal"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
  [ -f "$repo/.git/coordinator-sessions/$sid/.harness-bg-capable" ]
  # Second dispatch: absent key in the now-calibrated session — must deny.
  local fg='{"session_id":"'"$sid"'","tool_name":"Agent","tool_input":{"prompt":"go"}}'
  run env -i HOME="$HOME" PATH="$stub_dir" bash "$SUBJECT" <<< "$fg"
  [ "$status" -eq 0 ]
  [[ "$output" == *'"deny"'* ]]
  [[ "$output" == *'FOREGROUND AGENT DISPATCH BLOCKED'* ]]
  rm -rf "$stub_dir"
  # teardown() handles rm -rf "$repo"
}

# ---------------------------------------------------------------------------
# CASE F4 — Python fallback, present-and-false: with jq masked (stub PATH has
# bash/cat/sed/timeout/python3 but NOT jq), a present-and-false dispatch must deny.
# This exercises the Python branch's value extraction for the false case.
# Review: code-reviewer — masks only jq (prepends stub with a broken jq) while
# keeping the real PATH appended to reach python3 reliably.
# ---------------------------------------------------------------------------

@test "CASE F4: Python fallback, present-and-false → deny (jq masked)" {
  local stub_dir
  stub_dir="$(mktemp -d)"
  # Place a non-executable stub named jq in the stub dir so `command -v jq` resolves
  # to it but the hook's jq invocation fails, falling through to python.
  touch "$stub_dir/jq"
  # Do NOT chmod +x — it is intentionally non-executable so jq invocations exit non-zero.
  local payload='{"tool_name":"Agent","tool_input":{"prompt":"go","run_in_background":false}}'
  # Prepend stub_dir so the broken jq shadows the real one; real PATH follows for python3.
  run env -i HOME="$HOME" PATH="$stub_dir:$PATH" bash "$SUBJECT" <<< "$payload"
  rm -rf "$stub_dir"
  [ "$status" -eq 0 ]
  [[ "$output" == *'"deny"'* ]]
  [[ "$output" == *'FOREGROUND AGENT DISPATCH BLOCKED'* ]]
}
