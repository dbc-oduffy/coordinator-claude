#!/usr/bin/env bash
# claude-doe.test.sh — sandbox tests for the claude-doe launch wrapper.
#
# Tests run entirely in a temp sandbox. The live ~/.claude/settings.json and
# ~/.claude/plugins/ are never touched. All state is created under SANDBOX_DIR
# and cleaned up on exit.
#
# Spec backlink: docs/plans/2026-07-04-doe-maximalist-execution-plugin-dir.md § M2.1 tests
# Coverage:
#   T1                                --dry-run: hook block regenerated (sentinel from stub gen-settings-hooks.sh)
#   T2                                --dry-run: printed exec line carries --plugin-dir <DoE>/coordinator and forwarded arg
#   T3                                absent DoE clone -> fail-loud non-zero, no exec
#   T4                                absent coordinator/ sub-dir -> fail-loud non-zero
#   T5                                CLAUDE_DOE_DRY_RUN=1 env var triggers dry-run (same as --dry-run flag)
#   T6                                absent gen-settings-hooks.sh -> fail-loud non-zero
#   T7                                --dry-run does NOT mutate the generator's default settings.json target (regression)
#   T8                                real exec path: claude called with --plugin-dir; generator called without --out
#   T_ML_NOT_FOUND                    machine-local not found -> fail-loud non-zero, correct error message
#   T_ML_EMPTY                        machine-local returns empty repos.doe_claude -> fail-loud non-zero, correct error
#   T_SILENT_WHEN_PRESENT             hook block already in settings.json -> generator NOT invoked, no "restored" message
#   T_HEALS_WHEN_ABSENT               hook block absent from settings.json -> generator invoked, "restored" line printed
#   T_NONFATAL_GEN_FAILURE_EXISTING   generator exits non-zero, existing settings.json -> warning printed, exec reached (non-fatal)

# ---------------------------------------------------------------------------
# Bash >= 4 guard (mirrors the wrapper's own requirement)
# ---------------------------------------------------------------------------
if [ "${BASH_VERSINFO[0]:-0}" -lt 4 ]; then
  printf 'claude-doe.test: bash >= 4 required (got %s)\n' "${BASH_VERSION:-unknown}" >&2
  exit 1
fi

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WRAPPER="$SCRIPT_DIR/claude-doe"

# ---------------------------------------------------------------------------
# Sandbox setup / teardown
# ---------------------------------------------------------------------------
SANDBOX_DIR=""
setup_sandbox() {
  # Review: code-reviewer F2 — /private/tmp is macOS-only; use TMPDIR for portability.
  SANDBOX_DIR="$(mktemp -d "${TMPDIR:-/tmp}/claude-doe-test.XXXXXX")"
}

teardown_sandbox() {
  if [ -n "${SANDBOX_DIR:-}" ] && [ -d "$SANDBOX_DIR" ]; then
    rm -rf "$SANDBOX_DIR"
  fi
}
trap teardown_sandbox EXIT

# ---------------------------------------------------------------------------
# Helper: create a fake DoE clone with coordinator/ sub-dir
# ---------------------------------------------------------------------------
make_fake_doe() {
  local doe_dir="$SANDBOX_DIR/fake-doe"
  mkdir -p "$doe_dir/coordinator"
  printf '%s' "$doe_dir"
}

# ---------------------------------------------------------------------------
# Helper: create a stub gen-settings-hooks.sh that records it was called
# ---------------------------------------------------------------------------
make_stub_gen_hooks() {
  local sentinel="$SANDBOX_DIR/gen-hooks-ran"
  local stub_path="$SANDBOX_DIR/gen-settings-hooks.sh"
  # The stub writes a sentinel file and exits 0 (success).
  # Review: code-reviewer F3/F8 — real generator defaults to ${HOME}/.claude/settings.json
  # (not CLAUDE_HOME); CLAUDE_HOME branch was dead code. Removed. T7 uses its own inline stub
  # to verify the isolation boundary against the HOME-based default path.
  cat > "$stub_path" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
touch "${CLAUDE_DOE_TEST_SENTINEL:-/dev/null}"
STUB
  chmod +x "$stub_path"
  printf '%s' "$stub_path"
}

# ---------------------------------------------------------------------------
# Test runner helpers
# ---------------------------------------------------------------------------
PASS_COUNT=0
FAIL_COUNT=0

pass() { printf '[PASS] %s\n' "$1"; PASS_COUNT=$((PASS_COUNT + 1)); }
fail() { printf '[FAIL] %s\n' "$1"; FAIL_COUNT=$((FAIL_COUNT + 1)); }

# ---------------------------------------------------------------------------
# T1: --dry-run invokes gen-settings-hooks.sh (sentinel check)
# ---------------------------------------------------------------------------
t1_regen_on_dry_run() {
  setup_sandbox

  local doe_dir; doe_dir="$(make_fake_doe)"
  local stub; stub="$(make_stub_gen_hooks)"
  local sentinel="$SANDBOX_DIR/gen-hooks-ran"

  # Run the wrapper in dry-run mode, pointing at the stub and fake DoE.
  REPO_DOE_CLAUDE="$doe_dir" \
  CLAUDE_DOE_GEN_HOOKS_SCRIPT="$stub" \
  CLAUDE_DOE_TEST_SENTINEL="$sentinel" \
    "$WRAPPER" --dry-run >/dev/null

  if [ -f "$sentinel" ]; then
    pass "T1: gen-settings-hooks.sh was invoked on --dry-run"
  else
    fail "T1: gen-settings-hooks.sh was NOT invoked (sentinel missing at $sentinel)"
  fi

  teardown_sandbox; SANDBOX_DIR=""
}

# ---------------------------------------------------------------------------
# T2: --dry-run output contains --plugin-dir <DoE>/coordinator and forwarded arg
# ---------------------------------------------------------------------------
t2_dry_run_exec_line() {
  setup_sandbox

  local doe_dir; doe_dir="$(make_fake_doe)"
  local stub; stub="$(make_stub_gen_hooks)"

  local output
  output="$(
    REPO_DOE_CLAUDE="$doe_dir" \
    CLAUDE_DOE_GEN_HOOKS_SCRIPT="$stub" \
    CLAUDE_DOE_TEST_SENTINEL="$SANDBOX_DIR/sentinel" \
      "$WRAPPER" --dry-run --some-sample-arg 2>&1
  )"

  local expected_plugin_dir="$doe_dir/coordinator"

  local ok=1
  if printf '%s' "$output" | grep -qF -- "--plugin-dir $expected_plugin_dir"; then
    :
  else
    ok=0
    fail "T2: --plugin-dir not found in output. Got: $output"
  fi

  if printf '%s' "$output" | grep -qF -- "--some-sample-arg"; then
    :
  else
    ok=0
    fail "T2: forwarded arg '--some-sample-arg' not found in output. Got: $output"
  fi

  if [ "$ok" = 1 ]; then
    pass "T2: dry-run output carries --plugin-dir <DoE>/coordinator and forwarded arg"
  fi

  teardown_sandbox; SANDBOX_DIR=""
}

# ---------------------------------------------------------------------------
# T3: absent DoE clone -> fail-loud, non-zero exit, no exec
# ---------------------------------------------------------------------------
t3_absent_clone_fail_loud() {
  setup_sandbox

  local stub; stub="$(make_stub_gen_hooks)"
  local absent_doe="$SANDBOX_DIR/nonexistent-doe"
  # Do NOT create $absent_doe — it must be absent.

  local exit_code=0
  local output
  output="$(
    REPO_DOE_CLAUDE="$absent_doe" \
    CLAUDE_DOE_GEN_HOOKS_SCRIPT="$stub" \
      "$WRAPPER" --dry-run 2>&1
  )" || exit_code=$?

  if [ "$exit_code" -ne 0 ]; then
    pass "T3: absent clone -> non-zero exit ($exit_code)"
  else
    fail "T3: absent clone -> exit 0 (expected non-zero)"
  fi

  # Verify exec did NOT run (no 'exec claude' in output from wrapper printing it)
  # In fail-loud path the wrapper exits before printing the exec line.
  if printf '%s' "$output" | grep -qF 'exec claude'; then
    fail "T3: exec line was printed despite absent clone (should have exited before)"
  else
    pass "T3: exec line not printed (wrapper exited before reaching exec)"
  fi

  teardown_sandbox; SANDBOX_DIR=""
}

# ---------------------------------------------------------------------------
# T4: absent coordinator/ sub-dir -> fail-loud, non-zero exit
# ---------------------------------------------------------------------------
t4_absent_coordinator_dir() {
  setup_sandbox

  # Create DoE clone root but WITHOUT coordinator/ sub-dir
  local doe_dir="$SANDBOX_DIR/doe-no-coordinator"
  mkdir -p "$doe_dir"
  # No $doe_dir/coordinator

  local stub; stub="$(make_stub_gen_hooks)"

  local exit_code=0
  # Review: code-reviewer F7 — local output to avoid leaking into global bash scope.
  local output
  output="$(
    REPO_DOE_CLAUDE="$doe_dir" \
    CLAUDE_DOE_GEN_HOOKS_SCRIPT="$stub" \
      "$WRAPPER" --dry-run 2>&1
  )" || exit_code=$?

  if [ "$exit_code" -ne 0 ]; then
    pass "T4: absent coordinator/ -> non-zero exit ($exit_code)"
  else
    fail "T4: absent coordinator/ -> exit 0 (expected non-zero)"
  fi

  teardown_sandbox; SANDBOX_DIR=""
}

# ---------------------------------------------------------------------------
# T5: CLAUDE_DOE_DRY_RUN=1 triggers dry-run (same behaviour as --dry-run flag)
# ---------------------------------------------------------------------------
t5_env_var_dry_run() {
  setup_sandbox

  local doe_dir; doe_dir="$(make_fake_doe)"
  local stub; stub="$(make_stub_gen_hooks)"
  local sentinel="$SANDBOX_DIR/sentinel"

  local exit_code=0
  local output
  output="$(
    REPO_DOE_CLAUDE="$doe_dir" \
    CLAUDE_DOE_GEN_HOOKS_SCRIPT="$stub" \
    CLAUDE_DOE_DRY_RUN=1 \
    CLAUDE_DOE_TEST_SENTINEL="$sentinel" \
      "$WRAPPER" 2>&1
  )" || exit_code=$?

  if [ "$exit_code" -eq 0 ] && [ -f "$sentinel" ]; then
    pass "T5: CLAUDE_DOE_DRY_RUN=1 triggers dry-run (regen + exit 0)"
  else
    fail "T5: CLAUDE_DOE_DRY_RUN=1 did not trigger dry-run (exit=$exit_code, sentinel_exists=$([ -f "$sentinel" ] && echo yes || echo no))"
  fi

  if printf '%s' "$output" | grep -qF -- "--plugin-dir"; then
    pass "T5: CLAUDE_DOE_DRY_RUN=1 outputs exec line with --plugin-dir"
  else
    fail "T5: CLAUDE_DOE_DRY_RUN=1 output missing --plugin-dir. Got: $output"
  fi

  teardown_sandbox; SANDBOX_DIR=""
}

# ---------------------------------------------------------------------------
# T6: absent gen-settings-hooks.sh -> fail-loud, non-zero exit
# ---------------------------------------------------------------------------
t6_absent_gen_hooks() {
  setup_sandbox

  local doe_dir; doe_dir="$(make_fake_doe)"
  local absent_gen_hooks="$SANDBOX_DIR/no-gen-settings-hooks.sh"
  # Do NOT create $absent_gen_hooks — it must be absent.

  local exit_code=0
  # Review: code-reviewer F7 — local output to avoid leaking into global bash scope.
  local output
  output="$(
    REPO_DOE_CLAUDE="$doe_dir" \
    CLAUDE_DOE_GEN_HOOKS_SCRIPT="$absent_gen_hooks" \
      "$WRAPPER" --dry-run 2>&1
  )" || exit_code=$?

  if [ "$exit_code" -ne 0 ]; then
    pass "T6: absent gen-settings-hooks.sh -> non-zero exit ($exit_code)"
  else
    fail "T6: absent gen-settings-hooks.sh -> exit 0 (expected non-zero)"
  fi

  teardown_sandbox; SANDBOX_DIR=""
}

# ---------------------------------------------------------------------------
# T7: --dry-run does NOT mutate the generator's default settings.json target.
#     Regression test for the footgun where --dry-run ran the generator
#     unconditionally (before the dry-run gate), writing to live settings.json
#     as a side effect. The fix redirects the dry-run generator invocation to
#     a temp file via --out, so the default target is never touched.
# ---------------------------------------------------------------------------
t7_dry_run_no_mutate_settings() {
  setup_sandbox

  local doe_dir; doe_dir="$(make_fake_doe)"

  # Sandbox home: when HOME is redirected here, the generator's default output
  # resolves to $fake_home/.claude/settings.json — safe for the test to mutate.
  local fake_home="$SANDBOX_DIR/fake-home"
  mkdir -p "$fake_home/.claude"
  local sentinel_settings="$fake_home/.claude/settings.json"
  local sentinel_content='{"sentinel":"dry-run-no-mutate","__test":true}'
  printf '%s' "$sentinel_content" > "$sentinel_settings"

  # Stub that mimics the real generator's --out behaviour:
  #   with --out <path>  -> writes to that path (the temp file in the fixed path)
  #   without --out      -> writes to $HOME/.claude/settings.json (the bug path)
  # Using this stub lets the test assert that the sentinel is only mutated when
  # --out is NOT passed — which is what the unfixed wrapper would have done.
  local stub_path="$SANDBOX_DIR/gen-t7.sh"
  cat > "$stub_path" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
OUT="${HOME}/.claude/settings.json"
while [ $# -gt 0 ]; do
  case "$1" in
    --out) OUT="$2"; shift 2 ;;
    *)     shift ;;
  esac
done
mkdir -p "$(dirname "$OUT")"
printf '{"mutated":true}' > "$OUT"
STUB
  chmod +x "$stub_path"

  # Run --dry-run with HOME pointing at our sandbox.  Any write to the generator's
  # default target will land in the sandbox, not in the real ~/.claude/settings.json.
  HOME="$fake_home" \
  REPO_DOE_CLAUDE="$doe_dir" \
  CLAUDE_DOE_GEN_HOOKS_SCRIPT="$stub_path" \
    "$WRAPPER" --dry-run >/dev/null

  # Assert sentinel is byte-identical — --dry-run must NOT have mutated it.
  local after_content
  after_content="$(cat "$sentinel_settings")"
  if [ "$after_content" = "$sentinel_content" ]; then
    pass "T7: --dry-run did NOT mutate the generator's default settings.json target"
  else
    fail "T7: --dry-run MUTATED settings.json (got '$after_content', expected '$sentinel_content')"
  fi

  teardown_sandbox; SANDBOX_DIR=""
}

# ---------------------------------------------------------------------------
# T8: real (non-dry-run) exec path — claude called with --plugin-dir; generator without --out
# Review: code-reviewer F4 — previously no test covered the real dispatch path.
# ---------------------------------------------------------------------------
t8_real_exec_path() {
  setup_sandbox

  local doe_dir; doe_dir="$(make_fake_doe)"

  # Sandbox home with settings.json that does NOT contain the hook block —
  # makes the test hermetic: detect-then-skip determines regeneration is needed
  # regardless of whether the real ~/.claude/settings.json already has DoE hooks.
  local fake_home="$SANDBOX_DIR/fake-home-t8"
  mkdir -p "$fake_home/.claude"
  printf '{"other":"content"}\n' > "$fake_home/.claude/settings.json"

  # Stub claude: records args to a file one-per-line, exits 0.
  # The wrapper exec's into this stub; PATH is prepended so it is found before any real claude.
  local fake_bin_dir="$SANDBOX_DIR/fake-bin"
  mkdir -p "$fake_bin_dir"
  local claude_args_file="$SANDBOX_DIR/claude-args"
  cat > "$fake_bin_dir/claude" <<STUB
#!/usr/bin/env bash
printf '%s\n' "\$@" > "$claude_args_file"
exit 0
STUB
  chmod +x "$fake_bin_dir/claude"

  # Stub gen-settings-hooks.sh: records args to a file, exits 0.
  # In real mode the wrapper calls it with NO arguments (no --out).
  local gen_args_file="$SANDBOX_DIR/gen-args"
  local gen_stub="$SANDBOX_DIR/gen-real-mode.sh"
  cat > "$gen_stub" <<STUB
#!/usr/bin/env bash
printf '%s\n' "\$@" > "$gen_args_file"
exit 0
STUB
  chmod +x "$gen_stub"

  local exit_code=0
  HOME="$fake_home" \
  PATH="$fake_bin_dir:$PATH" \
  REPO_DOE_CLAUDE="$doe_dir" \
  CLAUDE_DOE_GEN_HOOKS_SCRIPT="$gen_stub" \
    "$WRAPPER" 2>/dev/null || exit_code=$?

  local expected_plugin_dir="$doe_dir/coordinator"

  # Assert claude was called with --plugin-dir <doe>/coordinator.
  if [ -f "$claude_args_file" ] && \
     grep -qF -- "--plugin-dir" "$claude_args_file" && \
     grep -qF -- "$expected_plugin_dir" "$claude_args_file"; then
    pass "T8: real exec path calls claude with --plugin-dir $expected_plugin_dir"
  else
    fail "T8: real exec path did not call claude with expected --plugin-dir. args=$(cat "$claude_args_file" 2>/dev/null || echo '(claude not called)')"
  fi

  # Assert generator was called WITHOUT --out (real mode must not redirect to temp file).
  if [ -f "$gen_args_file" ]; then
    if grep -qF -- "--out" "$gen_args_file"; then
      fail "T8: generator called with --out in real mode (must not be — --out is dry-run only)"
    else
      pass "T8: generator called without --out in real mode"
    fi
  else
    # Generator called with no args — empty args file created by printf '%s\n' "$@" with empty $@.
    # File missing means generator was never invoked.
    fail "T8: generator stub was never called in real mode"
  fi

  teardown_sandbox; SANDBOX_DIR=""
}

# ---------------------------------------------------------------------------
# T_ML_NOT_FOUND: machine-local binary absent -> fail-loud with correct error
# Review: code-reviewer F5 — uses CLAUDE_DOE_MACHINE_LOCAL_BIN override to bypass co-located
# machine-local (which always exists in production at $SCRIPT_DIR/machine-local).
# ---------------------------------------------------------------------------
t_ml_not_found() {
  setup_sandbox

  local stub_gen; stub_gen="$(make_stub_gen_hooks)"
  local absent_ml="$SANDBOX_DIR/nonexistent-machine-local"
  # Do NOT create $absent_ml — it must be absent so the not-found path fires.

  local exit_code=0
  local output
  output="$(
    REPO_DOE_CLAUDE="" \
    CLAUDE_DOE_MACHINE_LOCAL_BIN="$absent_ml" \
    CLAUDE_DOE_GEN_HOOKS_SCRIPT="$stub_gen" \
      "$WRAPPER" 2>&1
  )" || exit_code=$?

  if [ "$exit_code" -ne 0 ]; then
    pass "T_ML_NOT_FOUND: absent machine-local -> non-zero exit ($exit_code)"
  else
    fail "T_ML_NOT_FOUND: absent machine-local -> exit 0 (expected non-zero)"
  fi

  if printf '%s' "$output" | grep -qF 'machine-local not found'; then
    pass "T_ML_NOT_FOUND: correct error message emitted"
  else
    fail "T_ML_NOT_FOUND: expected 'machine-local not found' in output. Got: $output"
  fi

  teardown_sandbox; SANDBOX_DIR=""
}

# ---------------------------------------------------------------------------
# T_ML_EMPTY: machine-local returns empty repos.doe_claude -> fail-loud with correct error
# Review: code-reviewer F5 — exercises the "registered but empty" production fail path.
# ---------------------------------------------------------------------------
t_ml_empty() {
  setup_sandbox

  local stub_gen; stub_gen="$(make_stub_gen_hooks)"

  # Mock machine-local: exits 0, prints nothing (repos.doe_claude not registered).
  local mock_ml="$SANDBOX_DIR/mock-machine-local"
  cat > "$mock_ml" <<'STUB'
#!/usr/bin/env bash
# Simulates machine-local with repos.doe_claude unregistered: exits 0, prints nothing.
exit 0
STUB
  chmod +x "$mock_ml"

  local exit_code=0
  local output
  output="$(
    REPO_DOE_CLAUDE="" \
    CLAUDE_DOE_MACHINE_LOCAL_BIN="$mock_ml" \
    CLAUDE_DOE_GEN_HOOKS_SCRIPT="$stub_gen" \
      "$WRAPPER" 2>&1
  )" || exit_code=$?

  if [ "$exit_code" -ne 0 ]; then
    pass "T_ML_EMPTY: empty repos.doe_claude -> non-zero exit ($exit_code)"
  else
    fail "T_ML_EMPTY: empty repos.doe_claude -> exit 0 (expected non-zero)"
  fi

  if printf '%s' "$output" | grep -qF 'repos.doe_claude is empty'; then
    pass "T_ML_EMPTY: correct error message emitted"
  else
    fail "T_ML_EMPTY: expected 'repos.doe_claude is empty' in output. Got: $output"
  fi

  teardown_sandbox; SANDBOX_DIR=""
}

# ---------------------------------------------------------------------------
# Helper: create a fake bin dir with a stub claude that exits 0.
# Used by the detect-then-skip tests to let the wrapper reach exec without
# spawning the real claude binary.
# ---------------------------------------------------------------------------
make_fake_claude_bin() {
  local fake_bin_dir="$SANDBOX_DIR/fake-claude-bin"
  mkdir -p "$fake_bin_dir"
  cat > "$fake_bin_dir/claude" <<'STUB'
#!/usr/bin/env bash
exit 0
STUB
  chmod +x "$fake_bin_dir/claude"
  printf '%s' "$fake_bin_dir"
}

# ---------------------------------------------------------------------------
# T_SILENT_WHEN_PRESENT: settings.json already contains the hook block →
#   generator NOT invoked, no "restored" message printed.
# ---------------------------------------------------------------------------
t_silent_when_present() {
  setup_sandbox

  local doe_dir; doe_dir="$(make_fake_doe)"
  local doe_coordinator="$doe_dir/coordinator"

  # Sandbox home with settings.json that already contains the hook block.
  # The wrapper checks for the literal string "$DOE_COORDINATOR/hooks" in the file.
  local fake_home="$SANDBOX_DIR/fake-home-silent"
  mkdir -p "$fake_home/.claude"
  printf '{"hooks":{"PreToolUse":[{"matcher":"","hooks":[{"type":"command","command":"%s/hooks/somehook.sh"}]}]}}\n' \
    "$doe_coordinator" > "$fake_home/.claude/settings.json"

  # Gen stub records invocation via sentinel.
  local gen_sentinel="$SANDBOX_DIR/gen-sentinel-silent"
  local gen_stub="$SANDBOX_DIR/gen-stub-silent.sh"
  cat > "$gen_stub" <<STUB
#!/usr/bin/env bash
touch "$gen_sentinel"
exit 0
STUB
  chmod +x "$gen_stub"

  local fake_bin_dir; fake_bin_dir="$(make_fake_claude_bin)"

  local exit_code=0
  local output
  output="$(
    HOME="$fake_home" \
    REPO_DOE_CLAUDE="$doe_dir" \
    CLAUDE_DOE_GEN_HOOKS_SCRIPT="$gen_stub" \
    PATH="$fake_bin_dir:$PATH" \
      "$WRAPPER" 2>&1
  )" || exit_code=$?

  if [ ! -f "$gen_sentinel" ]; then
    pass "T_SILENT_WHEN_PRESENT: generator NOT invoked when hook block already present"
  else
    fail "T_SILENT_WHEN_PRESENT: generator WAS invoked even though hook block was present"
  fi

  if printf '%s' "$output" | grep -qF 'restored'; then
    fail "T_SILENT_WHEN_PRESENT: 'restored' message printed (should be silent when intact). Output: $output"
  else
    pass "T_SILENT_WHEN_PRESENT: no 'restored' message (silent as expected)"
  fi

  teardown_sandbox; SANDBOX_DIR=""
}

# ---------------------------------------------------------------------------
# T_HEALS_WHEN_ABSENT: settings.json present but missing hook block →
#   generator invoked, single "restored" stderr line printed.
# ---------------------------------------------------------------------------
t_heals_when_absent() {
  setup_sandbox

  local doe_dir; doe_dir="$(make_fake_doe)"

  # Sandbox home with settings.json that does NOT contain the hook block.
  local fake_home="$SANDBOX_DIR/fake-home-heal"
  mkdir -p "$fake_home/.claude"
  printf '{"other":"content"}\n' > "$fake_home/.claude/settings.json"

  # Gen stub records invocation via sentinel, exits 0.
  local gen_sentinel="$SANDBOX_DIR/gen-sentinel-heal"
  local gen_stub="$SANDBOX_DIR/gen-stub-heal.sh"
  cat > "$gen_stub" <<STUB
#!/usr/bin/env bash
touch "$gen_sentinel"
exit 0
STUB
  chmod +x "$gen_stub"

  local fake_bin_dir; fake_bin_dir="$(make_fake_claude_bin)"

  local exit_code=0
  local output
  output="$(
    HOME="$fake_home" \
    REPO_DOE_CLAUDE="$doe_dir" \
    CLAUDE_DOE_GEN_HOOKS_SCRIPT="$gen_stub" \
    PATH="$fake_bin_dir:$PATH" \
      "$WRAPPER" 2>&1
  )" || exit_code=$?

  if [ -f "$gen_sentinel" ]; then
    pass "T_HEALS_WHEN_ABSENT: generator invoked when hook block was missing"
  else
    fail "T_HEALS_WHEN_ABSENT: generator NOT invoked (sentinel absent)"
  fi

  if printf '%s' "$output" | grep -qF 'restored'; then
    pass "T_HEALS_WHEN_ABSENT: 'restored' message printed on heal"
  else
    fail "T_HEALS_WHEN_ABSENT: 'restored' message NOT printed. Output: $output"
  fi

  teardown_sandbox; SANDBOX_DIR=""
}

# ---------------------------------------------------------------------------
# T_NONFATAL_GEN_FAILURE_EXISTING: generator exits non-zero, existing settings.json
#   present → wrapper prints a warning AND continues to exec (exits 0, non-fatal).
# ---------------------------------------------------------------------------
t_nonfatal_gen_failure_existing() {
  setup_sandbox

  local doe_dir; doe_dir="$(make_fake_doe)"

  # Sandbox home with settings.json that does NOT contain the hook block —
  # detection fails so the generator is attempted, then the stub fails.
  local fake_home="$SANDBOX_DIR/fake-home-nonfatal"
  mkdir -p "$fake_home/.claude"
  printf '{"other":"content"}\n' > "$fake_home/.claude/settings.json"

  # Gen stub that always exits non-zero (simulates a broken generator).
  local gen_stub="$SANDBOX_DIR/gen-stub-fail.sh"
  cat > "$gen_stub" <<'STUB'
#!/usr/bin/env bash
exit 1
STUB
  chmod +x "$gen_stub"

  local fake_bin_dir; fake_bin_dir="$(make_fake_claude_bin)"

  local exit_code=0
  local output
  output="$(
    HOME="$fake_home" \
    REPO_DOE_CLAUDE="$doe_dir" \
    CLAUDE_DOE_GEN_HOOKS_SCRIPT="$gen_stub" \
    PATH="$fake_bin_dir:$PATH" \
      "$WRAPPER" 2>&1
  )" || exit_code=$?

  if [ "$exit_code" -eq 0 ]; then
    pass "T_NONFATAL_GEN_FAILURE_EXISTING: wrapper exits 0 (reached exec — non-fatal)"
  else
    fail "T_NONFATAL_GEN_FAILURE_EXISTING: wrapper exited $exit_code (expected 0 — should be non-fatal with existing settings.json)"
  fi

  if printf '%s' "$output" | grep -qF 'warning'; then
    pass "T_NONFATAL_GEN_FAILURE_EXISTING: warning message printed"
  else
    fail "T_NONFATAL_GEN_FAILURE_EXISTING: warning message NOT printed. Output: $output"
  fi

  teardown_sandbox; SANDBOX_DIR=""
}

# ---------------------------------------------------------------------------
# Pre-flight: wrapper must be executable
# ---------------------------------------------------------------------------
if [ ! -x "$WRAPPER" ]; then
  printf 'ERROR: wrapper not executable at %s\n' "$WRAPPER" >&2
  exit 2
fi

# ---------------------------------------------------------------------------
# Run tests
# ---------------------------------------------------------------------------
printf '=== claude-doe.test.sh ===\n'
printf 'Wrapper: %s\n\n' "$WRAPPER"

t1_regen_on_dry_run
t2_dry_run_exec_line
t3_absent_clone_fail_loud
t4_absent_coordinator_dir
t5_env_var_dry_run
t6_absent_gen_hooks
t7_dry_run_no_mutate_settings
t8_real_exec_path
t_ml_not_found
t_ml_empty
t_silent_when_present
t_heals_when_absent
t_nonfatal_gen_failure_existing

printf '\n--- Results: %d passed, %d failed ---\n' "$PASS_COUNT" "$FAIL_COUNT"

if [ "$FAIL_COUNT" -gt 0 ]; then
  exit 1
fi
exit 0
