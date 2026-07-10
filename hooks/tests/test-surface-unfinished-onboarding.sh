#!/usr/bin/env bash
# Test suite: hooks/scripts/surface-unfinished-onboarding.sh — P2 guided
# post-restart self-onboarding SessionStart(startup) hook.
#
# Spec backlink: docs/plans/2026-07-08-install-baton-rendezvous-off-dotclaude.md § C7, AC12, AC13
#
# Self-contained: builds throwaway fixture dirs for CLAUDE_PLUGIN_ROOT (a fake
# "coordinator/" tree exposing only bin/coordinator-setup-state.sh, so the
# check-orientation gate is scriptable) and COORDINATOR_SETTINGS_HOME (a fake
# settings-home so seeding never touches the real machine's settings home).
# The real template (templates/handoffs/continue-onboarding-and-installation.md)
# and the real render-template.sh ARE used — the hook resolves those from its
# OWN location, not from CLAUDE_PLUGIN_ROOT, so seeding exercises the real
# render path end-to-end.
#
# Pass/fail idiom follows test-repomap-banner.sh (same assertion style):
#   PASS/FAIL counters, "N passed, M failed" summary, exit 1 on any failure.
#
# Exit codes: 0 all passed, 1 one or more failed.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK="$SCRIPT_DIR/../scripts/surface-unfinished-onboarding.sh"

if [[ ! -f "$HOOK" ]]; then
  echo "FATAL: hook not found: $HOOK" >&2
  exit 1
fi

PASS=0
FAIL=0

pass() { PASS=$((PASS+1)); echo "PASS: $1"; }
fail() { FAIL=$((FAIL+1)); echo "FAIL: $1"; }

CLEANUP_DIRS=()
trap 'rm -rf "${CLEANUP_DIRS[@]}"' EXIT

# mk_fixture_plugin_root <check_exit_code|absent> -> prints a fresh fixture
# CLAUDE_PLUGIN_ROOT dir with bin/coordinator-setup-state.sh stubbed to exit
# with the given code on `check orientation_completed`. "absent" omits the
# bin/ dir entirely (simulates a resolver-miss / receipt-unreadable state).
mk_fixture_plugin_root() {
  local check_exit="$1" root
  root="$(mktemp -d)"
  CLEANUP_DIRS+=("$root")
  if [[ "$check_exit" != "absent" ]]; then
    mkdir -p "$root/bin"
    cat > "$root/bin/coordinator-setup-state.sh" <<EOF
#!/usr/bin/env bash
case "\${1:-} \${2:-}" in
  "check orientation_completed") exit ${check_exit} ;;
  *) exit 2 ;;
esac
EOF
    chmod +x "$root/bin/coordinator-setup-state.sh"
  fi
  printf '%s' "$root"
}

# mk_fixture_settings_home -> prints a fresh fixture settings-home dir (empty).
mk_fixture_settings_home() {
  local root
  root="$(mktemp -d)"
  CLEANUP_DIRS+=("$root")
  printf '%s' "$root"
}

# mk_fixture_claude_home -> prints a fresh non-git fixture CLAUDE_HOME (so the
# hook's best-effort `git -C .../. rev-parse` branch lookup fails cleanly and
# falls back to "main", never touching the real machine's ~/.claude).
mk_fixture_claude_home() {
  local root
  root="$(mktemp -d)"
  CLEANUP_DIRS+=("$root")
  printf '%s' "$root"
}

# run_hook <plugin_root> <settings_home> <claude_home> -> stdout (stderr
# discarded). Caller captures via `out="$(run_hook ...)"; RC=$?` — RC must be
# read from $? immediately after the command-substitution assignment (NOT set
# as a global inside this function, which would run in the substitution's own
# subshell and never propagate back to the caller's shell).
run_hook() {
  local plugin_root="$1" settings_home="$2" claude_home="$3"
  CLAUDE_PLUGIN_ROOT="$plugin_root" COORDINATOR_SETTINGS_HOME="$settings_home" CLAUDE_HOME="$claude_home" bash "$HOOK" 2>/dev/null
}

DEST_REL="state/handoffs/continue-onboarding-and-installation.md"

# ---------------------------------------------------------------------------
# Scenario 1: orientation-not-completed → surfaces (mode A: seeds guarded).
# ---------------------------------------------------------------------------
plugin_root="$(mk_fixture_plugin_root 1)"
settings_home="$(mk_fixture_settings_home)"
claude_home="$(mk_fixture_claude_home)"
out="$(run_hook "$plugin_root" "$settings_home" "$claude_home")"
RC=$?
dest="$settings_home/$DEST_REL"

if [[ "$RC" -eq 0 ]]; then
  pass "scenario1: hook exits 0"
else
  fail "scenario1: hook exit code was $RC, expected 0"
fi

if [[ -f "$dest" ]]; then
  pass "scenario1: baton seeded at settings-home rendezvous"
else
  fail "scenario1: baton NOT seeded at $dest"
fi

if printf '%s' "$out" | grep -qF "/pickup $dest"; then
  pass "scenario1: surfaces one /pickup line pointing at the seeded path"
else
  fail "scenario1: no /pickup pointer in stdout (got: $out)"
fi

# ---------------------------------------------------------------------------
# Scenario 2: orientation_completed recorded → silent no-op.
# ---------------------------------------------------------------------------
plugin_root="$(mk_fixture_plugin_root 0)"
settings_home="$(mk_fixture_settings_home)"
claude_home="$(mk_fixture_claude_home)"
out="$(run_hook "$plugin_root" "$settings_home" "$claude_home")"
RC=$?
dest="$settings_home/$DEST_REL"

if [[ "$RC" -eq 0 ]]; then
  pass "scenario2: hook exits 0"
else
  fail "scenario2: hook exit code was $RC, expected 0"
fi

if [[ -z "$out" ]]; then
  pass "scenario2: silent (no stdout) once oriented"
else
  fail "scenario2: expected silence, got: $out"
fi

if [[ ! -f "$dest" ]]; then
  pass "scenario2: no baton seeded once oriented"
else
  fail "scenario2: baton was seeded despite orientation_completed"
fi

# ---------------------------------------------------------------------------
# Scenario 3: orientation-incomplete + baton already present → does NOT
# re-seed/clobber.
# ---------------------------------------------------------------------------
plugin_root="$(mk_fixture_plugin_root 1)"
settings_home="$(mk_fixture_settings_home)"
claude_home="$(mk_fixture_claude_home)"
dest="$settings_home/$DEST_REL"
mkdir -p "$(dirname "$dest")"
printf 'SENTINEL-DO-NOT-OVERWRITE\n' > "$dest"

out="$(run_hook "$plugin_root" "$settings_home" "$claude_home")"
RC=$?

if [[ "$RC" -eq 0 ]]; then
  pass "scenario3: hook exits 0"
else
  fail "scenario3: hook exit code was $RC, expected 0"
fi

if grep -qF 'SENTINEL-DO-NOT-OVERWRITE' "$dest"; then
  pass "scenario3: pre-existing baton was NOT clobbered"
else
  fail "scenario3: pre-existing baton was overwritten"
fi

if printf '%s' "$out" | grep -qF "/pickup $dest"; then
  pass "scenario3: still re-surfaces the pointer to the already-seeded baton"
else
  fail "scenario3: expected a /pickup pointer even without re-seeding (got: $out)"
fi

# ---------------------------------------------------------------------------
# Scenario 4: hook-error path (unreadable receipt / resolver miss) → exits 0
# silently, session not wedged.
# ---------------------------------------------------------------------------
plugin_root="$(mk_fixture_plugin_root absent)"
settings_home="$(mk_fixture_settings_home)"
claude_home="$(mk_fixture_claude_home)"
out="$(run_hook "$plugin_root" "$settings_home" "$claude_home")"
RC=$?
dest="$settings_home/$DEST_REL"

if [[ "$RC" -eq 0 ]]; then
  pass "scenario4: hook exits 0 even with coordinator-setup-state.sh missing"
else
  fail "scenario4: hook exit code was $RC, expected 0"
fi

if [[ -z "$out" ]]; then
  pass "scenario4: silent on resolver miss"
else
  fail "scenario4: expected silence on resolver miss, got: $out"
fi

if [[ ! -f "$dest" ]]; then
  pass "scenario4: no baton seeded on resolver miss (can't confirm orientation state)"
else
  fail "scenario4: baton was seeded despite an unreadable/missing receipt"
fi

# ---------------------------------------------------------------------------
# Scenario 5: second fire after orientation_completed → silent (idempotent
# self-extinguish holds across repeated invocations, not just the first).
# ---------------------------------------------------------------------------
plugin_root="$(mk_fixture_plugin_root 0)"
settings_home="$(mk_fixture_settings_home)"
claude_home="$(mk_fixture_claude_home)"

out1="$(run_hook "$plugin_root" "$settings_home" "$claude_home")"
rc1=$?
out2="$(run_hook "$plugin_root" "$settings_home" "$claude_home")"
rc2=$?
dest="$settings_home/$DEST_REL"

if [[ "$rc1" -eq 0 && "$rc2" -eq 0 && -z "$out1" && -z "$out2" ]]; then
  pass "scenario5: both fires silent, exit 0, once oriented"
else
  fail "scenario5: rc1=$rc1 rc2=$rc2 out1='$out1' out2='$out2'"
fi

if [[ ! -f "$dest" ]]; then
  pass "scenario5: no baton seeded across repeated fires once oriented"
else
  fail "scenario5: baton appeared across repeated fires despite orientation_completed"
fi

# ---------------------------------------------------------------------------
echo ""
echo "$PASS passed, $FAIL failed"
[[ "$FAIL" -eq 0 ]]
