#!/bin/bash
# Smoke test for block-completion-monolith-write.sh PreToolUse hook.
#
# Concurrency: single-threaded; no shared state outside subshells.
# Idempotency: deterministic given fixed inputs.
# Resume: stateless — re-runs from scratch.

set -uo pipefail

HOOK="$(dirname "$0")/../block-completion-monolith-write.sh"
[[ ! -f "$HOOK" ]] && { echo "FAIL: hook not found at $HOOK"; exit 1; }

PASS=0
FAIL=0

run_case() {
  local name="$1" input="$2" expected_exit="$3" env_prefix="$4"
  local actual_exit
  if [[ -n "$env_prefix" ]]; then
    actual_exit=$(echo "$input" | env $env_prefix bash "$HOOK" >/dev/null 2>&1; echo $?)
  else
    actual_exit=$(echo "$input" | bash "$HOOK" >/dev/null 2>&1; echo $?)
  fi
  if [[ "$actual_exit" == "$expected_exit" ]]; then
    echo "PASS: $name (exit=$actual_exit)"
    PASS=$((PASS+1))
  else
    echo "FAIL: $name — expected exit=$expected_exit, got $actual_exit"
    FAIL=$((FAIL+1))
  fi
}

# Block: write to root monolith path
run_case "blocks root monolith write" \
  '{"tool_name":"Write","tool_input":{"file_path":"/tmp/proj/archive/completed/2026-05.md"}}' \
  1 ""

# Block: write at any nested project path
run_case "blocks monolith at nested project path" \
  '{"tool_name":"Edit","tool_input":{"file_path":"/Users/dev/repos/proj/archive/completed/2026-12.md"}}' \
  1 ""

# Block: NotebookEdit also caught (matcher includes it)
run_case "blocks NotebookEdit monolith write" \
  '{"tool_name":"NotebookEdit","tool_input":{"file_path":"./archive/completed/2025-01.md"}}' \
  1 ""

# Allow: legacy subdir
run_case "allows legacy/ subdir" \
  '{"tool_name":"Write","tool_input":{"file_path":"/tmp/proj/archive/completed/legacy/2026-05.md"}}' \
  0 ""

# Allow: per-entry file under YYYY-MM/
run_case "allows per-entry under YYYY-MM/" \
  '{"tool_name":"Write","tool_input":{"file_path":"/tmp/proj/archive/completed/2026-05/2026-05-19-foo-abc123.md"}}' \
  0 ""

# Allow: unrelated path
run_case "allows unrelated path" \
  '{"tool_name":"Write","tool_input":{"file_path":"/tmp/proj/docs/wiki/some.md"}}' \
  0 ""

# Allow: malformed year-month (3-digit year) does not match pattern
run_case "allows non-YYYY-MM filename" \
  '{"tool_name":"Write","tool_input":{"file_path":"/tmp/proj/archive/completed/2026-5.md"}}' \
  0 ""

# Allow: override env var bypass
run_case "override env var bypasses block" \
  '{"tool_name":"Write","tool_input":{"file_path":"/tmp/proj/archive/completed/2026-05.md"}}' \
  0 "COORDINATOR_OVERRIDE_COMPLETION_MONOLITH=1"

# Allow: empty input (no file_path)
run_case "allows empty input" \
  '{}' \
  0 ""

# Allow: Windows-style backslash path under legacy
run_case "allows Windows-style legacy path" \
  '{"tool_name":"Write","tool_input":{"file_path":"C:\\Users\\dev\\proj\\archive\\completed\\legacy\\2026-05.md"}}' \
  0 ""

# Block: Windows-style backslash root path
run_case "blocks Windows-style root path" \
  '{"tool_name":"Write","tool_input":{"file_path":"C:\\Users\\dev\\proj\\archive\\completed\\2026-05.md"}}' \
  1 ""

echo ""
echo "Results: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]]
