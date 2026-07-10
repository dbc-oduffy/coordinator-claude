#!/usr/bin/env bash
# Unit tests for hooks/scripts/validate-commit.sh.
#
# Tests:
#   AC1  source-inert — sourcing defines check_validate_commit, no logic/output
#   AC2  standalone-deny via main-guard (oversized CLAUDE.md)
#   AC8  override export-then-allow for each of the 3 env-gated deny paths
#        machine-path-leak (#4) has NO override — assert still denies with all
#        other overrides set
#
# Each deny fixture is an isolated real git repo built in a temp dir.
#
# Spec backlink: docs/plans/2026-06-30-pretooluse-bash-hook-dispatcher.md

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK="$SCRIPT_DIR/../scripts/validate-commit.sh"
PASS=0
FAIL=0

export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null

# ---------------------------------------------------------------------------
# Cleanup — accumulated as repos are created
# ---------------------------------------------------------------------------
CLEANUP_DIRS=()
_vc_cleanup() {
  [[ ${#CLEANUP_DIRS[@]} -gt 0 ]] && rm -rf "${CLEANUP_DIRS[@]}" 2>/dev/null
  true
}
trap _vc_cleanup EXIT

# ---------------------------------------------------------------------------
# emit <cmd> [<sid>]: build PreToolUse JSON for a Bash tool call
# ---------------------------------------------------------------------------
emit() {
  local cmd="$1" sid="${2:-vc-test-default}"
  if command -v jq &>/dev/null; then
    jq -nc --arg c "$cmd" --arg s "$sid" \
      '{tool_name:"Bash",tool_input:{command:$c},session_id:$s}'
  else
    local ec="${cmd//\\/\\\\}"; ec="${ec//\"/\\\"}"; ec="${ec//$'\n'/\\n}"
    printf '{"tool_name":"Bash","tool_input":{"command":"%s"},"session_id":"%s"}\n' \
      "$ec" "$sid"
  fi
}

# ---------------------------------------------------------------------------
# assert_hook <desc> <expected:allow|deny> <json> [<cwd>] [<env-prefix>]
# Runs validate-commit.sh as a standalone process; checks permissionDecision.
# ---------------------------------------------------------------------------
assert_hook() {
  local desc="$1" expected="$2" json="$3" cwd="${4:-$PWD}" envvars="${5:-}"
  local out got
  if [[ -n "$envvars" ]]; then
    # shellcheck disable=SC2086  # word-split intentional for env VAR=val pairs
    out=$(cd "$cwd" && printf '%s' "$json" | env $envvars bash "$HOOK" 2>/dev/null || true)
  else
    out=$(cd "$cwd" && printf '%s' "$json" | bash "$HOOK" 2>/dev/null || true)
  fi
  got="allow"
  printf '%s' "$out" | grep -q '"permissionDecision":"deny"' && got="deny"
  if [[ "$got" == "$expected" ]]; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1))
    printf 'FAIL: %s (expected %s, got %s)\n' "$desc" "$expected" "$got"
    [[ -n "$out" ]] && printf '      out: %s\n' "$(printf '%s' "$out" | head -c 200)"
  fi
}

# ============================================================================
# AC1: source-inert — sourcing defines check_validate_commit, no logic/output
# ============================================================================

# Sub-test 1a: check_validate_commit is defined after sourcing
_src_func=$(bash -c "source '$HOOK' </dev/null 2>/dev/null; \
  declare -f check_validate_commit >/dev/null 2>&1 && echo DEFINED" 2>/dev/null || true)
if [[ "$_src_func" == "DEFINED" ]]; then
  PASS=$((PASS + 1))
else
  FAIL=$((FAIL + 1))
  printf 'FAIL: AC1a source-inert — check_validate_commit not defined after sourcing\n'
fi

# Sub-test 1b: sourcing emits no spurious output (only our echo reaches stdout)
_src_noise=$(bash -c "source '$HOOK' </dev/null 2>/dev/null; echo SOURCE_OK" 2>/dev/null || true)
if [[ "$_src_noise" == "SOURCE_OK" ]]; then
  PASS=$((PASS + 1))
else
  FAIL=$((FAIL + 1))
  printf 'FAIL: AC1b source-inert — unexpected stdout during source\n'
  printf '      got: %s\n' "$_src_noise"
fi

# ============================================================================
# Build fixture repos
# ============================================================================

# ---- Fixture 1: oversized CLAUDE.md staged (> 40000 chars) ----
VC_CLAUDE_REPO=$(mktemp -d)
CLEANUP_DIRS+=("$VC_CLAUDE_REPO")
(
  cd "$VC_CLAUDE_REPO"
  git init -q -b main
  git config user.email t@t.t && git config user.name T && git config commit.gpgsign false
  printf 'x\n' > init.txt && git add init.txt && git commit -q -m "init"
  # Generate > 40000 chars via awk (popup-safe, not a console-subsystem process)
  awk 'BEGIN{for(i=0;i<41001;i++) printf "A"; print ""}' > CLAUDE.md
  git add CLAUDE.md
)

# ---- Fixture 2: SCOPE_STRICT foreign file staged ----
# Session dir created with far-future started_at (2050) so foreign.txt's mtime
# (~now, 2026) is below started_at_epoch — cs_compute_scope mtime-fallback
# does NOT pull foreign.txt into MY_SCOPE, keeping it foreign.
VC_SCOPE_REPO=$(mktemp -d)
VC_SCOPE_SID="vc-scope-$$"
CLEANUP_DIRS+=("$VC_SCOPE_REPO")
(
  cd "$VC_SCOPE_REPO"
  git init -q -b main
  git config user.email t@t.t && git config user.name T && git config commit.gpgsign false
  printf 'x\n' > init.txt && git add init.txt && git commit -q -m "init"
  printf 'foreign content\n' > foreign.txt && git add foreign.txt
  mkdir -p ".git/coordinator-sessions/${VC_SCOPE_SID}"
  printf '2050-01-01T00:00:00Z\n' > ".git/coordinator-sessions/${VC_SCOPE_SID}/started_at"
  # touched.txt lists only "other.txt" — not "foreign.txt"
  printf 'other.txt\n' > ".git/coordinator-sessions/${VC_SCOPE_SID}/touched.txt"
)

# ---- Fixture 3: FRONTMATTER_STRICT staged docs/plans file ----
# docs/plans/x.md has a `status:` line in its staged diff; commit subject
# "initial" contains no frontmatter key or lifecycle verb → deny fires.
VC_FM_REPO=$(mktemp -d)
CLEANUP_DIRS+=("$VC_FM_REPO")
(
  cd "$VC_FM_REPO"
  git init -q -b main
  git config user.email t@t.t && git config user.name T && git config commit.gpgsign false
  printf 'x\n' > init.txt && git add init.txt && git commit -q -m "init"
  mkdir -p docs/plans
  printf -- '---\nstatus: active\n---\n# Plan\n' > docs/plans/x.md
  git add docs/plans/x.md
)

# ---- Fixture 4: machine-path-leak staged settings.json ----
# settings.json contains a C:\Users\ path; check-machine-path-leak.sh exits 1
# → validate-commit hard-blocks with no override path.
VC_LEAK_REPO=$(mktemp -d)
CLEANUP_DIRS+=("$VC_LEAK_REPO")
(
  cd "$VC_LEAK_REPO"
  git init -q -b main
  git config user.email t@t.t && git config user.name T && git config commit.gpgsign false
  printf 'x\n' > init.txt && git add init.txt && git commit -q -m "init"
  # jq: C:\\Users\\foo in a jq string literal = the string C:\Users\foo
  # jq output JSON: "C:\\Users\\foo" (valid — double backslash represents one backslash)
  if command -v jq &>/dev/null; then
    jq -n '{"path": "C:\\Users\\foo\\something"}' > settings.json
  else
    # printf %s passes the arg verbatim; single-quoted \\ = two backslashes in file
    printf '%s\n' '{"path": "C:\\Users\\foo\\something"}' > settings.json
  fi
  git add settings.json
)

# ============================================================================
# AC2: standalone-deny via main-guard — oversized CLAUDE.md
# ============================================================================
assert_hook \
  "AC2: standalone deny — CLAUDEMD > 40K chars staged" \
  "deny" \
  "$(emit 'git commit -m x')" \
  "$VC_CLAUDE_REPO"

# ============================================================================
# Fixture verifications: confirm each deny fires before testing its override
# ============================================================================
assert_hook \
  "fixture-verify: SCOPE_STRICT deny (no override)" \
  "deny" \
  "$(emit 'git commit -m x' "$VC_SCOPE_SID")" \
  "$VC_SCOPE_REPO" \
  "COORDINATOR_SCOPE_STRICT=1"

assert_hook \
  "fixture-verify: FRONTMATTER_STRICT deny (no override)" \
  "deny" \
  "$(emit 'git commit -m initial')" \
  "$VC_FM_REPO" \
  "COORDINATOR_FRONTMATTER_STRICT=1"

assert_hook \
  "fixture-verify: machine-path-leak deny (hard block, no override env)" \
  "deny" \
  "$(emit 'git commit -m x')" \
  "$VC_LEAK_REPO"

# ============================================================================
# AC8: override export-then-allow (3 env-gated deny points)
# ============================================================================

# AC8a: COORDINATOR_OVERRIDE_CLAUDEMD_BUDGET=1 → allow despite oversized CLAUDE.md
assert_hook \
  "AC8a: override-allow — CLAUDEMD budget (COORDINATOR_OVERRIDE_CLAUDEMD_BUDGET=1)" \
  "allow" \
  "$(emit 'git commit -m x')" \
  "$VC_CLAUDE_REPO" \
  "COORDINATOR_OVERRIDE_CLAUDEMD_BUDGET=1"

# AC8b: COORDINATOR_SCOPE_STRICT=1 + COORDINATOR_OVERRIDE_SCOPE=1 → allow despite foreign file
assert_hook \
  "AC8b: override-allow — scope strict (COORDINATOR_SCOPE_STRICT=1 COORDINATOR_OVERRIDE_SCOPE=1)" \
  "allow" \
  "$(emit 'git commit -m x' "$VC_SCOPE_SID")" \
  "$VC_SCOPE_REPO" \
  "COORDINATOR_SCOPE_STRICT=1 COORDINATOR_OVERRIDE_SCOPE=1"

# AC8c: COORDINATOR_FRONTMATTER_STRICT=1 + COORDINATOR_OVERRIDE_FRONTMATTER=1 → allow
assert_hook \
  "AC8c: override-allow — frontmatter strict (COORDINATOR_FRONTMATTER_STRICT=1 COORDINATOR_OVERRIDE_FRONTMATTER=1)" \
  "allow" \
  "$(emit 'git commit -m initial')" \
  "$VC_FM_REPO" \
  "COORDINATOR_FRONTMATTER_STRICT=1 COORDINATOR_OVERRIDE_FRONTMATTER=1"

# ============================================================================
# Deny #4 (machine-path-leak) has NO override env — hard block regardless.
# Assert: even with ALL other override envs set, machine-path-leak still denies.
# ============================================================================
assert_hook \
  "machine-path-leak still denies with all other override envs set (no override for leak)" \
  "deny" \
  "$(emit 'git commit -m x')" \
  "$VC_LEAK_REPO" \
  "COORDINATOR_OVERRIDE_CLAUDEMD_BUDGET=1 COORDINATOR_OVERRIDE_SCOPE=1 COORDINATOR_OVERRIDE_FRONTMATTER=1"

# ============================================================================
echo "----------------------------------------"
printf 'test-validate-commit: %d passed, %d failed\n' "$PASS" "$FAIL"
[[ "$FAIL" -eq 0 ]] || exit 1
exit 0
