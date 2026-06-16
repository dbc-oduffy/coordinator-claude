#!/usr/bin/env bash
# test_probe_cwd_project_rag_relevance.sh — Tests for probe-cwd-project-rag-relevance.sh
#
# Purpose: verifies the AC-9 visibility matrix for each combination of binding, MCP health,
# and UE detection. All tests mock the environment via COORDINATOR_TEST_HOME and temp dirs —
# no writes to the real home directory, no live MCP queries.
#
# Spec backlink: docs/plans/2026-05-20-portable-code-substrate.md § Chunk 3
#
# Run: bash ~/.claude/plugins/coordinator/tests/test_probe_cwd_project_rag_relevance.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SUBJECT="${SCRIPT_DIR}/../bin/probe-cwd-project-rag-relevance.sh"

# ---------------------------------------------------------------------------
# Minimal test framework
# ---------------------------------------------------------------------------
PASS=0
FAIL=0
FAIL_MSGS=()

pass() { echo "  PASS: $1"; (( PASS++ )) || true; }
fail() {
  echo "  FAIL: $1"
  FAIL_MSGS+=("$1")
  (( FAIL++ )) || true
}

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------
TMP_ROOTS=()

make_test_home() {
  local tmpdir
  tmpdir=$(mktemp -d)
  TMP_ROOTS+=("$tmpdir")
  # Standard directory structure for a mocked HOME
  mkdir -p "$tmpdir/.claude/machine-local"
  mkdir -p "$tmpdir/.claude/plugins/coordinator-claude/data"
  mkdir -p "$tmpdir/.claude/plugins/project-rag-ue-addon/data"
  echo "$tmpdir"
}

cleanup() {
  for d in "${TMP_ROOTS[@]}"; do
    rm -rf "$d"
  done
}
trap cleanup EXIT

# Write a minimal ~/.claude.json with project-rag in mcpServers
write_claude_json_with_rag() {
  local home="$1"
  cat > "$home/.claude.json" <<'JSON'
{
  "mcpServers": {
    "project-rag": {
      "command": "python3",
      "args": ["/fake/cli.py", "/fake/project"]
    }
  }
}
JSON
}

# Write a minimal ~/.claude.json WITHOUT project-rag
write_claude_json_no_rag() {
  local home="$1"
  cat > "$home/.claude.json" <<'JSON'
{
  "mcpServers": {
    "other-server": {}
  }
}
JSON
}

# Write registry.toml with project_rag set
write_registry_with_rag() {
  local home="$1"
  local val="${2:-/fake/project-rag}"
  cat > "$home/.claude/machine-local/registry.toml" <<EOF
[repos]
project_rag = "$val"
EOF
}

# Write mcp-registration-last-check.json indicating broken
write_mcp_sentinel_broken() {
  local home="$1"
  cat > "$home/.claude/plugins/coordinator-claude/data/mcp-registration-last-check.json" <<'JSON'
{
  "red_servers": ["project-rag"]
}
JSON
}

# Write mcp-registration-last-check.json indicating healthy (project-rag NOT in red_servers)
write_mcp_sentinel_healthy() {
  local home="$1"
  cat > "$home/.claude/plugins/coordinator-claude/data/mcp-registration-last-check.json" <<'JSON'
{
  "red_servers": []
}
JSON
}

# Write UE addon sentinel indicating engine corpus PRESENT (GREEN, no engine-corpus red probes)
write_ue_addon_sentinel_present() {
  local home="$1"
  cat > "$home/.claude/plugins/project-rag-ue-addon/data/doctor-last-run.json" <<'JSON'
{
  "ran_at": "2026-05-21T10:00:00Z",
  "verdict": "GREEN",
  "red_probes": [],
  "hint": ""
}
JSON
}

# Write UE addon sentinel indicating engine corpus MISSING (RED with engine-corpus probe)
write_ue_addon_sentinel_missing() {
  local home="$1"
  cat > "$home/.claude/plugins/project-rag-ue-addon/data/doctor-last-run.json" <<'JSON'
{
  "ran_at": "2026-05-21T10:00:00Z",
  "verdict": "RED",
  "red_probes": ["engine-corpus"],
  "hint": "run /project-rag-ue-addon:doctor to bootstrap"
}
JSON
}

# Run the probe with a given COORDINATOR_TEST_HOME and a fake PWD.
# COORDINATOR_TEST_PWD bypasses git top-level detection so .uproject scanning uses the temp dir.
# Returns output in variable OUTPUT and exit code in EXIT_CODE
run_probe() {
  local test_home="$1"
  local fake_pwd="$2"
  OUTPUT=$(COORDINATOR_TEST_HOME="$test_home" COORDINATOR_TEST_PWD="$fake_pwd" bash "$SUBJECT" 2>&1)
  EXIT_CODE=$?
}

# ---------------------------------------------------------------------------
# Test 1: no project-rag binding → silent
# ---------------------------------------------------------------------------
echo "--- Test 1: no project-rag binding → silent output"

T1=$(make_test_home)
write_claude_json_no_rag "$T1"
# No registry.toml with project_rag either (empty machine-local)

FAKE_PWD1=$(mktemp -d)
TMP_ROOTS+=("$FAKE_PWD1")

run_probe "$T1" "$FAKE_PWD1"

if [[ "$EXIT_CODE" -eq 0 ]]; then
  pass "Test 1: exits 0"
else
  fail "Test 1: expected exit 0, got $EXIT_CODE"
fi

if [[ -z "$OUTPUT" ]]; then
  pass "Test 1: no output (silent)"
else
  fail "Test 1: expected empty output, got: $OUTPUT"
fi

# ---------------------------------------------------------------------------
# Test 2: non-UE, project-RAG bound (registry), MCP healthy → healthy: line
# ---------------------------------------------------------------------------
echo "--- Test 2: non-UE, project-RAG bound via registry, MCP healthy → healthy:"

T2=$(make_test_home)
# Use registry.toml binding (not .claude.json) to test that path
write_registry_with_rag "$T2"
write_mcp_sentinel_healthy "$T2"
# No .claude.json mcpServers entry — binding via registry only

FAKE_PWD2=$(mktemp -d)
TMP_ROOTS+=("$FAKE_PWD2")
# No .uproject files in FAKE_PWD2

run_probe "$T2" "$FAKE_PWD2"

if [[ "$EXIT_CODE" -eq 0 ]]; then
  pass "Test 2: exits 0"
else
  fail "Test 2: expected exit 0, got $EXIT_CODE"
fi

if echo "$OUTPUT" | grep -q '\[project-rag-relevance\] healthy:'; then
  pass "Test 2: healthy: line emitted"
else
  fail "Test 2: expected healthy: line, got: $OUTPUT"
fi

if echo "$OUTPUT" | grep -q 'broken:'; then
  fail "Test 2: unexpected broken: line in output"
else
  pass "Test 2: no broken: line"
fi

# ---------------------------------------------------------------------------
# Test 3: non-UE, project-RAG bound, MCP broken → broken: line
# ---------------------------------------------------------------------------
echo "--- Test 3: non-UE, project-RAG bound, MCP broken → broken:"

T3=$(make_test_home)
write_claude_json_with_rag "$T3"
write_mcp_sentinel_broken "$T3"

FAKE_PWD3=$(mktemp -d)
TMP_ROOTS+=("$FAKE_PWD3")

run_probe "$T3" "$FAKE_PWD3"

if [[ "$EXIT_CODE" -eq 0 ]]; then
  pass "Test 3: exits 0"
else
  fail "Test 3: expected exit 0, got $EXIT_CODE"
fi

if echo "$OUTPUT" | grep -q '\[project-rag-relevance\] broken:'; then
  pass "Test 3: broken: line emitted"
else
  fail "Test 3: expected broken: line, got: $OUTPUT"
fi

if echo "$OUTPUT" | grep -q 'healthy:'; then
  fail "Test 3: unexpected healthy: line in output"
else
  pass "Test 3: no healthy: line"
fi

# ---------------------------------------------------------------------------
# Test 4: UE (.uproject present), project-RAG bound, MCP healthy, engine corpus PRESENT
#         → healthy-ue: lines, no suggest-engine-corpus
# ---------------------------------------------------------------------------
echo "--- Test 4: UE + bound + healthy + engine corpus PRESENT → healthy-ue: only"

T4=$(make_test_home)
write_claude_json_with_rag "$T4"
write_mcp_sentinel_healthy "$T4"
write_ue_addon_sentinel_present "$T4"

FAKE_PWD4=$(mktemp -d)
TMP_ROOTS+=("$FAKE_PWD4")
touch "$FAKE_PWD4/MyGame.uproject"

run_probe "$T4" "$FAKE_PWD4"

if [[ "$EXIT_CODE" -eq 0 ]]; then
  pass "Test 4: exits 0"
else
  fail "Test 4: expected exit 0, got $EXIT_CODE"
fi

if echo "$OUTPUT" | grep -q '\[project-rag-relevance\] healthy-ue:'; then
  pass "Test 4: healthy-ue: line emitted"
else
  fail "Test 4: expected healthy-ue: line, got: $OUTPUT"
fi

if echo "$OUTPUT" | grep -q 'suggest-engine-corpus:'; then
  fail "Test 4: unexpected suggest-engine-corpus: line (corpus is PRESENT)"
else
  pass "Test 4: no suggest-engine-corpus: line"
fi

if echo "$OUTPUT" | grep -q 'p0-broken-ue:'; then
  fail "Test 4: unexpected p0-broken-ue: line"
else
  pass "Test 4: no p0-broken-ue: line"
fi

# ---------------------------------------------------------------------------
# Test 5: UE (.uproject present), project-RAG bound, MCP healthy, engine corpus MISSING
#         → both healthy-ue: AND suggest-engine-corpus:
# ---------------------------------------------------------------------------
echo "--- Test 5: UE + bound + healthy + engine corpus MISSING → healthy-ue: + suggest-engine-corpus:"

T5=$(make_test_home)
write_claude_json_with_rag "$T5"
write_mcp_sentinel_healthy "$T5"
# No UE addon sentinel → MISSING

FAKE_PWD5=$(mktemp -d)
TMP_ROOTS+=("$FAKE_PWD5")
touch "$FAKE_PWD5/MyGame.uproject"

run_probe "$T5" "$FAKE_PWD5"

if [[ "$EXIT_CODE" -eq 0 ]]; then
  pass "Test 5: exits 0"
else
  fail "Test 5: expected exit 0, got $EXIT_CODE"
fi

if echo "$OUTPUT" | grep -q '\[project-rag-relevance\] healthy-ue:'; then
  pass "Test 5: healthy-ue: line emitted"
else
  fail "Test 5: expected healthy-ue: line, got: $OUTPUT"
fi

if echo "$OUTPUT" | grep -q 'suggest-engine-corpus:'; then
  pass "Test 5: suggest-engine-corpus: line emitted"
else
  fail "Test 5: expected suggest-engine-corpus: line, got: $OUTPUT"
fi

# ---------------------------------------------------------------------------
# Test 6: UE (.uproject present), project-RAG bound, MCP broken → p0-broken-ue: output
# ---------------------------------------------------------------------------
echo "--- Test 6: UE + bound + MCP broken → p0-broken-ue:"

T6=$(make_test_home)
write_claude_json_with_rag "$T6"
write_mcp_sentinel_broken "$T6"

FAKE_PWD6=$(mktemp -d)
TMP_ROOTS+=("$FAKE_PWD6")
touch "$FAKE_PWD6/MyGame.uproject"

run_probe "$T6" "$FAKE_PWD6"

if [[ "$EXIT_CODE" -eq 0 ]]; then
  pass "Test 6: exits 0"
else
  fail "Test 6: expected exit 0, got $EXIT_CODE"
fi

if echo "$OUTPUT" | grep -q '\[project-rag-relevance\] p0-broken-ue:'; then
  pass "Test 6: p0-broken-ue: line emitted"
else
  fail "Test 6: expected p0-broken-ue: line, got: $OUTPUT"
fi

if echo "$OUTPUT" | grep -q 'healthy'; then
  fail "Test 6: unexpected healthy line in broken UE output"
else
  pass "Test 6: no healthy line"
fi

# ---------------------------------------------------------------------------
# Test 7: .uproject absent, whoami says ue → UE enrichment emitted
# ---------------------------------------------------------------------------
echo "--- Test 7: no .uproject, whoami project_kind=ue → UE enrichment emitted"

# This test can only fully work if coordinator_whoami is installed. We mock the whoami
# path by overriding COORDINATOR_PYTHON to point to a wrapper that injects the ue response.
# If the package is not installed, the probe falls back to non-UE (whoami returns empty).
# We test both: if package unavailable, we verify probe at least exits 0 and doesn't crash.
# For machines with coordinator_whoami, we'd need full mock injection. Since coordinator_whoami
# is itself complex to mock portably, we verify the probe handles this path gracefully.

T7=$(make_test_home)
write_claude_json_with_rag "$T7"
write_mcp_sentinel_healthy "$T7"
write_ue_addon_sentinel_missing "$T7"

FAKE_PWD7=$(mktemp -d)
TMP_ROOTS+=("$FAKE_PWD7")
# Intentionally NO .uproject file here

# Write a mock python that pretends coordinator_whoami is installed and returns ue
MOCK_PY_DIR=$(mktemp -d)
TMP_ROOTS+=("$MOCK_PY_DIR")

cat > "$MOCK_PY_DIR/mock_py.sh" <<'MOCKPY'
#!/usr/bin/env bash
# Mock python that intercepts coordinator_whoami calls to inject project_kind=ue,
# but otherwise delegates to real python.
ARGS=("$@")
if [[ "${ARGS[*]}" == *"coordinator_whoami"* && "${ARGS[*]}" == *"get_whoami_json"* ]]; then
  echo '{"project_kind": "ue", "binding": {"kind": "bound", "target": "/fake/project"}}'
  exit 0
fi
# For any other -c invocation, delegate to the real interpreter
if command -v python3 >/dev/null 2>&1; then
  exec python3 "${ARGS[@]}" # verify-no-console-flash: allow
elif command -v python >/dev/null 2>&1; then
  exec python "${ARGS[@]}" # verify-no-console-flash: allow
fi
exit 1
MOCKPY
chmod +x "$MOCK_PY_DIR/mock_py.sh"

OUTPUT7=$(COORDINATOR_TEST_HOME="$T7" COORDINATOR_TEST_PWD="$FAKE_PWD7" COORDINATOR_PYTHON="$MOCK_PY_DIR/mock_py.sh" bash "$SUBJECT" 2>/dev/null)
EXIT7=$?

if [[ "$EXIT7" -eq 0 ]]; then
  pass "Test 7: exits 0"
else
  fail "Test 7: expected exit 0, got $EXIT7"
fi

# The mock python injects project_kind=ue — we require UE-enrichment output.
# The mock intercepts all python -c "...coordinator_whoami...get_whoami_json..." calls
# and returns {"project_kind": "ue", ...}. If the mock fails to intercept, the probe
# falls back to non-UE and emits healthy: — which means the mock broke, not the probe.
# TODO: if this assertion becomes flaky on a platform where the mock can't intercept
# reliably (e.g. Windows cmd.exe without bash on PATH), downgrade to a smoke test and
# mark it explicitly with DEGRADED-MODE-SMOKE-TEST in the test name.
if echo "$OUTPUT7" | grep -qE '(healthy-ue:|p0-broken-ue:|suggest-engine-corpus:)'; then
  pass "Test 7: UE enrichment emitted (whoami mock triggered)"
else
  fail "Test 7: expected UE enrichment (healthy-ue:/p0-broken-ue:/suggest-engine-corpus:) — mock may not have intercepted correctly; got: $OUTPUT7"
fi

# ---------------------------------------------------------------------------
# Test 8: always-on — invoke healthy UE case twice → healthy-ue: emitted both times
#         (not throttled / idempotent)
# ---------------------------------------------------------------------------
echo "--- Test 8: healthy UE case invoked twice → healthy-ue: emitted both times (not throttled)"

T8=$(make_test_home)
write_claude_json_with_rag "$T8"
write_mcp_sentinel_healthy "$T8"
write_ue_addon_sentinel_present "$T8"

FAKE_PWD8=$(mktemp -d)
TMP_ROOTS+=("$FAKE_PWD8")
touch "$FAKE_PWD8/MyGame.uproject"

OUTPUT8A=$(COORDINATOR_TEST_HOME="$T8" COORDINATOR_TEST_PWD="$FAKE_PWD8" bash "$SUBJECT" 2>/dev/null)
EXIT8A=$?
OUTPUT8B=$(COORDINATOR_TEST_HOME="$T8" COORDINATOR_TEST_PWD="$FAKE_PWD8" bash "$SUBJECT" 2>/dev/null)
EXIT8B=$?

if [[ "$EXIT8A" -eq 0 && "$EXIT8B" -eq 0 ]]; then
  pass "Test 8: both invocations exit 0"
else
  fail "Test 8: expected both to exit 0, got $EXIT8A and $EXIT8B"
fi

if echo "$OUTPUT8A" | grep -q '\[project-rag-relevance\] healthy-ue:'; then
  pass "Test 8: first invocation emits healthy-ue:"
else
  fail "Test 8: first invocation expected healthy-ue:, got: $OUTPUT8A"
fi

if echo "$OUTPUT8B" | grep -q '\[project-rag-relevance\] healthy-ue:'; then
  pass "Test 8: second invocation also emits healthy-ue: (not throttled)"
else
  fail "Test 8: second invocation expected healthy-ue:, got: $OUTPUT8B"
fi

if [[ "$OUTPUT8A" == "$OUTPUT8B" ]]; then
  pass "Test 8: both invocations produce identical output"
else
  fail "Test 8: invocations produced different output — first: $OUTPUT8A | second: $OUTPUT8B"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"

if [[ "$FAIL" -gt 0 ]]; then
  echo ""
  echo "Failures:"
  for msg in "${FAIL_MSGS[@]}"; do
    echo "  - $msg"
  done
  exit 1
fi

exit 0
