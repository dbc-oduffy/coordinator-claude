#!/usr/bin/env bats
# nudge-foreground-agent-dispatch.bats — bats tests for
# hooks/scripts/nudge-foreground-agent-dispatch.sh
#
# Purpose: regression coverage for the PreToolUse foreground-Agent-dispatch deny hook.
#   The load-bearing case (CASE A) is the capability-probe: on harness builds where the
#   Agent tool exposes NO run_in_background parameter, tool_input has no such key, and the
#   hook MUST pass — denying there is unsatisfiable and bricks the session
#   (project-rag-ue-addon-em memo, 2026-06-21). Discrimination is key-PRESENCE, not value:
#   absent → pass; present-and-false → deny; present-and-true → pass.
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
