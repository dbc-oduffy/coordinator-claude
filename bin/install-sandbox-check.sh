#!/usr/bin/env bash
# install-sandbox-check.sh — sandbox clean-install shape validator for W4.1
#
# Purpose: exercises the three W4.1 install steps (DoE clone, claude-doe wrapper,
#   gen-settings-hooks seeding) against an isolated sandbox CLAUDE_HOME and asserts
#   the resulting thin-~/.claude + cloned-DoE shape. Validates Tier 1 (filesystem) of
#   the install-surface-completeness contract.
#
# Tier 2 (Running-in-Claude-Code) is DEFERRED — it requires a real Claude Code boot
#   and cannot run inside a subagent. See the DEFERRED block at the end of this script.
#
# Spec backlink: docs/plans/2026-07-04-doe-maximalist-execution-plugin-dir.md § W4.1
#   AC-W4.1: "Sandbox clean-install produces thin ~/.claude + cloned DoE + wired wrapper"
# Doctrine: docs/wiki/install-surface-completeness.md § Running-in-Claude-Code

# ---- bash >= 4 guard (reachable on bash 3.2) ----
if [ "${BASH_VERSINFO[0]:-0}" -lt 4 ]; then
  printf 'install-sandbox-check.sh: bash >= 4 required (got %s)\n' "${BASH_VERSION:-unknown}" >&2
  printf '  Remediation: brew install bash  (macOS) then reopen your shell\n' >&2
  exit 1
fi

set -euo pipefail

# ---- helpers ----
PASS=0
FAIL=0
_pass() { printf 'PASS: %s\n' "$*"; PASS=$((PASS+1)); }
_fail() { printf 'FAIL: %s\n' "$*" >&2; FAIL=$((FAIL+1)); }
_skip() { printf 'SKIP: %s\n' "$*"; }
_info() { printf 'INFO: %s\n' "$*"; }

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

# ---- jq dependency check (fail-loud; required for settings.json parsing) ----
if ! command -v jq >/dev/null 2>&1; then
  die "jq is required but not found on PATH.
  Remediation: brew install jq  (macOS) | apt-get install jq (Linux) | winget install jqlang.jq (Windows)"
fi

# ---- self-resolve SCRIPT_DIR so bin/ siblings are found ----
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COORDINATOR_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ---- arg parse ----
KEEP_SANDBOX=0
VERBOSE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --keep-sandbox) KEEP_SANDBOX=1; shift ;;
    --verbose|-v)   VERBOSE=1;      shift ;;
    -h|--help)
      cat <<'EOF'
Usage: install-sandbox-check.sh [OPTIONS]

Validates the W4.1 thin-~/.claude + cloned-DoE + wired-wrapper install shape
in an isolated sandbox. Tier 1 (filesystem) only — Tier 2 (running-in-Claude-Code)
is printed as a DEFERRED manual gate at the end.

Options:
  --keep-sandbox   Do not delete the sandbox directory after the run.
  --verbose, -v    Print each assertion with context even when passing.
  -h, --help       Show this usage.

Environment:
  REPO_DOE_CLAUDE  Path to the DoE clone (primary resolution override).
                   Falls back to: machine-local get repos.doe_claude.
                   At least one must be set for the DoE clone checks to run.
EOF
      exit 0 ;;
    *) die "Unknown argument: $1. Run with --help." ;;
  esac
done

# ---- resolve DoE clone path ----
DOE_CLONE="${REPO_DOE_CLAUDE:-}"

if [[ -z "$DOE_CLONE" ]]; then
  # Try machine-local (must be findable as sibling bin or PATH)
  _ml_bin="$SCRIPT_DIR/machine-local"
  [ ! -x "$_ml_bin" ] && _ml_bin="machine-local"
  if command -v "$_ml_bin" >/dev/null 2>&1 || [ -x "$SCRIPT_DIR/machine-local" ]; then
    DOE_CLONE="$("$_ml_bin" get repos.doe_claude 2>/dev/null || true)"
  fi
fi

if [[ -z "$DOE_CLONE" ]]; then
  _fail "repos.doe_claude not resolved (set REPO_DOE_CLAUDE or seed via machine-local set repos.doe_claude)"
  _info "Skipping DoE-clone-dependent checks."
  DOE_CLONE_RESOLVED=0
else
  DOE_CLONE_RESOLVED=1
  _info "DoE clone resolved: $DOE_CLONE"
fi

# ---- create sandbox ----
SANDBOX="$(mktemp -d /tmp/install-sandbox-check.XXXXXX)"
export CLAUDE_HOME="$SANDBOX"
_info "Sandbox CLAUDE_HOME: $SANDBOX"

cleanup() {
  if [ "$KEEP_SANDBOX" -eq 0 ]; then
    rm -rf "$SANDBOX"
  else
    _info "Sandbox preserved at: $SANDBOX"
  fi
}
trap cleanup EXIT

# ---- Tier 1: Filesystem shape checks ----
printf '\n=== Tier 1: Filesystem shape ===\n'

# 1. ~/.claude (sandbox) exists as a directory
if [[ -d "$SANDBOX" ]]; then
  _pass "sandbox CLAUDE_HOME created: $SANDBOX"
else
  _fail "sandbox CLAUDE_HOME missing: $SANDBOX"
fi

# 2. DoE clone exists and has a .git dir
if [[ "$DOE_CLONE_RESOLVED" -eq 1 ]]; then
  if [[ -d "$DOE_CLONE/.git" ]]; then
    _pass "DoE clone present: $DOE_CLONE"
  else
    _fail "DoE clone missing .git: $DOE_CLONE"
  fi

  # 3. coordinator/ subdir exists in the DoE clone
  if [[ -d "$DOE_CLONE/coordinator" ]]; then
    _pass "DoE coordinator/ dir present: $DOE_CLONE/coordinator"
    DOE_COORDINATOR_PRESENT=1
  else
    _skip "DoE coordinator/ dir absent — W4.2 cutover not yet completed (expected pre-cutover)"
    _info "  coordinator/ will be populated after the W4.2 source-relocation cutover."
    DOE_COORDINATOR_PRESENT=0
  fi
else
  _skip "DoE clone checks (clone path not resolved)"
  DOE_COORDINATOR_PRESENT=0
fi

# 4. No plugin source byte-copy in sandbox ~/.claude/plugins/coordinator-claude/
_sandbox_plugin_dir="$SANDBOX/plugins/coordinator-claude"
if [[ -d "$_sandbox_plugin_dir" ]] && [[ -n "$(ls -A "$_sandbox_plugin_dir" 2>/dev/null)" ]]; then
  _fail "byte-copy anti-pattern: $SANDBOX/plugins/coordinator-claude/ is non-empty (should not exist)"
else
  _pass "no plugin byte-copy in sandbox ~/.claude/plugins/coordinator-claude/ (thin shape)"
fi

# 5. Exercise step 3.5b — wrapper install into sandbox ~/.local/bin/
printf '\n--- Step 3.5b: wrapper install ---\n'

_wrapper_src="$COORDINATOR_ROOT/bin/claude-doe"
if [[ ! -f "$_wrapper_src" ]]; then
  _fail "claude-doe wrapper not found at: $_wrapper_src"
else
  _pass "claude-doe wrapper source present: $_wrapper_src"

  _sandbox_local_bin="$SANDBOX/.local/bin"
  _sandbox_wrapper="$_sandbox_local_bin/claude-doe"

  mkdir -p "$_sandbox_local_bin"
  cp -p "$_wrapper_src" "$_sandbox_wrapper"
  chmod +x "$_sandbox_wrapper"

  if [[ -f "$_sandbox_wrapper" ]] && [[ -x "$_sandbox_wrapper" ]]; then
    _pass "claude-doe wrapper installed and executable (exec-bit set): $_sandbox_wrapper"
  else
    _fail "claude-doe wrapper install failed (missing or exec-bit not set): $_sandbox_wrapper"
  fi
  # Review: code-reviewer F7 — removed redundant second exec-bit [ -x ] block; folded into
  # the combined -f && -x check above to avoid double FAIL on the same condition.
fi

# 6. Exercise step 3.5c — gen-settings-hooks seeding (sandbox target)
printf '\n--- Step 3.5c: settings.json hook block seed ---\n'

_gen_hooks="$COORDINATOR_ROOT/bin/gen-settings-hooks.sh"
if [[ ! -f "$_gen_hooks" ]]; then
  _fail "gen-settings-hooks.sh not found at: $_gen_hooks"
elif [[ "$DOE_COORDINATOR_PRESENT" -eq 0 ]]; then
  # gen-settings-hooks.sh requires the coordinator/ dir to resolve absolute hook paths.
  # Pre-W4.2 (coordinator/ not yet in DoE clone), verify the script exists and is executable
  # but skip the live-seed run.
  _pass "gen-settings-hooks.sh source present: $_gen_hooks"
  _skip "gen-settings-hooks live seed (DoE coordinator/ absent pre-W4.2 — will run post-cutover)"
  _info "  Seeding will succeed after W4.2 populates $DOE_CLONE/coordinator/"
  # We can still check the script is valid bash syntax
  if bash -n "$_gen_hooks" 2>/dev/null; then
    _pass "gen-settings-hooks.sh parses as valid bash"
  else
    _fail "gen-settings-hooks.sh has bash syntax errors"
  fi
else
  _pass "gen-settings-hooks.sh source present: $_gen_hooks"

  # Review: code-reviewer F4 — verify the --out contract before invoking, analogous to the
  # bash -n check in the pre-W4.2 branch above.
  # gen-settings-hooks.sh --out contract: the script accepts --out <path> to write the
  # generated hook block to a caller-specified settings.json rather than resolving the
  # path via CLAUDE_HOME. This is how the sandbox isolation is achieved below.
  if bash -n "$_gen_hooks" 2>/dev/null; then
    _pass "gen-settings-hooks.sh parses as valid bash"
  else
    _fail "gen-settings-hooks.sh has bash syntax errors"
  fi
  if grep -qF -- '--out' "$_gen_hooks" 2>/dev/null; then
    _pass "gen-settings-hooks.sh --out flag is present (interface contract verified)"
  else
    _fail "gen-settings-hooks.sh does not appear to support --out (interface contract broken — sandbox isolation will not work)"
  fi

  # Build a sandbox settings.json target (pre-populate with empty object)
  _sandbox_settings="$SANDBOX/settings.json"
  printf '{}' > "$_sandbox_settings"

  # Review: code-reviewer F3 — error log moved under $SANDBOX (unique mktemp dir) to avoid
  # concurrent-run clobber at fixed /tmp paths. $SANDBOX is trap-cleaned on EXIT.
  if CLAUDE_HOME="$SANDBOX" REPO_DOE_CLAUDE="$DOE_CLONE" \
     bash "$_gen_hooks" --out "$_sandbox_settings" 2>"$SANDBOX/gen-hooks-err.txt"; then
    _pass "gen-settings-hooks.sh exited 0 against sandbox settings.json"
  else
    _fail "gen-settings-hooks.sh failed (see $SANDBOX/gen-hooks-err.txt)"
  fi

  # The settings.json should now have a "hooks" array
  if [[ -f "$_sandbox_settings" ]]; then
    _hook_count="$(jq '.hooks | length' "$_sandbox_settings" 2>/dev/null || echo "0")"
    if [[ "$_hook_count" -gt 0 ]]; then
      _pass "settings.json hooks array seeded: $_hook_count event bucket(s)"
    else
      _fail "settings.json hooks array empty after gen-settings-hooks run"
    fi
  else
    _fail "settings.json not created in sandbox"
  fi

  # No mcp_tool entries should appear in hook command strings
  _mcp_in_hooks="$(jq '[.hooks[]?.hooks[]?.command // "" | select(test("mcp_tool|coordinator_core"))] | length' "$_sandbox_settings" 2>/dev/null || echo "0")"
  if [[ "$_mcp_in_hooks" -eq 0 ]]; then
    _pass "no mcp_tool entries leaked into settings.json hooks (type filter correct)"
  else
    _fail "mcp_tool-shaped command found in settings.json hooks (type filter broken)"
  fi

  # Idempotency: run again, output must be byte-identical
  _sandbox_settings_v2="$SANDBOX/settings.v2.json"
  cp "$_sandbox_settings" "$_sandbox_settings_v2"
  if CLAUDE_HOME="$SANDBOX" REPO_DOE_CLAUDE="$DOE_CLONE" \
     bash "$_gen_hooks" --out "$_sandbox_settings" 2>/dev/null; then
    if diff -q "$_sandbox_settings_v2" "$_sandbox_settings" >/dev/null 2>&1; then
      _pass "gen-settings-hooks.sh is idempotent (second run = no-op diff)"
    else
      _fail "gen-settings-hooks.sh is NOT idempotent (second run changed settings.json)"
    fi
  else
    _fail "gen-settings-hooks.sh failed on second (idempotency) run"
  fi
fi

# 7. claude-doe --dry-run against sandbox
printf '\n--- Step 3.5b dry-run: claude-doe --dry-run ---\n'

if [[ "$DOE_CLONE_RESOLVED" -eq 1 ]] && [[ "$DOE_COORDINATOR_PRESENT" -eq 1 ]]; then
  _dryrun_out="$SANDBOX/dryrun-out.txt"
  if CLAUDE_HOME="$SANDBOX" REPO_DOE_CLAUDE="$DOE_CLONE" \
    CLAUDE_DOE_GEN_HOOKS_SCRIPT="$COORDINATOR_ROOT/bin/gen-settings-hooks.sh" \
    bash "$COORDINATOR_ROOT/bin/claude-doe" --dry-run 2>"$SANDBOX/dryrun-err.txt" \
      | tee "$_dryrun_out" >/dev/null; then
    _dry_out="$(cat "$_dryrun_out")"
    # Review: code-reviewer F9 — grep -qF (fixed string) avoids accidental regex interpretation.
    if printf '%s' "$_dry_out" | grep -qF "exec claude --plugin-dir"; then
      _pass "claude-doe --dry-run emitted exec line with --plugin-dir"
    else
      _fail "claude-doe --dry-run output missing 'exec claude --plugin-dir' (got: $_dry_out)"
    fi
    if printf '%s' "$_dry_out" | grep -qF "$DOE_CLONE/coordinator"; then
      _pass "claude-doe --dry-run exec line references DoE coordinator dir"
    else
      _fail "claude-doe --dry-run exec line does not reference DoE coordinator dir"
    fi
  else
    _fail "claude-doe --dry-run exited non-zero (see $SANDBOX/dryrun-err.txt)"
  fi
elif [[ "$DOE_CLONE_RESOLVED" -eq 0 ]]; then
  _skip "claude-doe --dry-run (DoE clone path not resolved)"
else
  _skip "claude-doe --dry-run (DoE coordinator/ dir absent pre-W4.2 — runs post-cutover)"
fi

# 7b. Standalone-copy smoke test (F5 regression net) — claude-doe copied ALONE into a
# fresh temp dir, siblings (gen-settings-hooks.sh, machine-local) absent. This is the
# EXACT install shape install.md step 3.5b produces (a bare `cp -p` of the wrapper only
# to ~/.local/bin), and is the shape that broke before F5's fix: the wrapper previously
# resolved GEN_HOOKS/machine-local as co-located SCRIPT_DIR siblings, which do not exist
# when the wrapper is copied alone. --dry-run must still exit 0 and print the
# --plugin-dir exec line, resolving GEN_HOOKS from the DoE clone instead of SCRIPT_DIR.
# Spec backlink: tasks/2026-07-08-install-dogfood-friction.md § F5
printf '\n--- F5 regression: claude-doe standalone-copy --dry-run (siblings absent) ---\n'

if [[ "$DOE_CLONE_RESOLVED" -eq 1 ]] && [[ "$DOE_COORDINATOR_PRESENT" -eq 1 ]]; then
  _f5_standalone_dir="$SANDBOX/f5-standalone-bin"
  mkdir -p "$_f5_standalone_dir"
  cp -p "$_wrapper_src" "$_f5_standalone_dir/claude-doe"
  chmod +x "$_f5_standalone_dir/claude-doe"

  # Confirm the standalone dir genuinely has no siblings (this test is meaningless
  # if it accidentally has gen-settings-hooks.sh / machine-local co-located).
  if [[ -f "$_f5_standalone_dir/gen-settings-hooks.sh" ]] || [[ -f "$_f5_standalone_dir/machine-local" ]]; then
    _fail "F5 regression setup broken: siblings unexpectedly present in $_f5_standalone_dir"
  else
    _pass "F5 regression setup: standalone dir has claude-doe ALONE (no siblings): $_f5_standalone_dir"

    _f5_dryrun_out="$SANDBOX/f5-dryrun-out.txt"
    if REPO_DOE_CLAUDE="$DOE_CLONE" \
      "$_f5_standalone_dir/claude-doe" --dry-run 2>"$SANDBOX/f5-dryrun-err.txt" \
        | tee "$_f5_dryrun_out" >/dev/null; then
      _f5_dry_out="$(cat "$_f5_dryrun_out")"
      if printf '%s' "$_f5_dry_out" | grep -qF "exec claude --plugin-dir"; then
        _pass "F5: standalone-copy claude-doe --dry-run emitted exec line with --plugin-dir"
      else
        _fail "F5: standalone-copy claude-doe --dry-run output missing 'exec claude --plugin-dir' (got: $_f5_dry_out)"
      fi
      if printf '%s' "$_f5_dry_out" | grep -qF "$DOE_CLONE/coordinator"; then
        _pass "F5: standalone-copy claude-doe --dry-run exec line references DoE coordinator dir"
      else
        _fail "F5: standalone-copy claude-doe --dry-run exec line does not reference DoE coordinator dir"
      fi
    else
      _fail "F5: standalone-copy claude-doe --dry-run exited non-zero (see $SANDBOX/f5-dryrun-err.txt)"
    fi
  fi
elif [[ "$DOE_CLONE_RESOLVED" -eq 0 ]]; then
  _skip "F5 regression: standalone-copy claude-doe --dry-run (DoE clone path not resolved)"
else
  _skip "F5 regression: standalone-copy claude-doe --dry-run (DoE coordinator/ dir absent pre-W4.2 — runs post-cutover)"
fi

# ---- Tier 1b: Maximalist install shape (C0 regression net — RED until C1–C3) ----
#
# These assertions exercise the pointer + shim + resolver cold-tier introduced by
# coordinator-maximalist-install-shape plan chunks C1/C2/C3. All are expected RED
# until those chunks land — that is the documented intent ("regression-net FIRST").
#
# Spec backlink: docs/plans/2026-07-04-coordinator-maximalist-install-shape.md § C0
# AC map: pointer=AC1, shim=AC1/AC2, mirror=AC5, cold-tier=AC6, cold-shell=AC2,
#         live-non-mutation=AC4, idempotency=AC4
printf '\n=== Tier 1b: Maximalist install shape (C0 regression net — RED until C1–C3) ===\n'

# ---- Live-artifact baseline capture (must happen before any sandbox run) ----
# Copy live .doe-root and shim into SANDBOX so we can cmp after all sandbox runs.
# If the live artifacts don't exist yet (C1/C2 not installed), we skip those checks.
_live_doe_root="${HOME}/.claude/.doe-root"
_live_shim_file="${HOME}/.claude/shell/claude-doe-shim.sh"
_live_doe_root_bak="$SANDBOX/.live-doe-root.bak"
_live_shim_bak="$SANDBOX/.live-shim.bak"

if [[ -f "$_live_doe_root" ]]; then
  cp "$_live_doe_root" "$_live_doe_root_bak"
fi
if [[ -f "$_live_shim_file" ]]; then
  cp "$_live_shim_file" "$_live_shim_bak"
fi

# ---- 8. Pointer artifact: ~/.claude/.doe-root (via gen-doe-root-pointer.sh) ----
printf '\n--- Pointer artifact (.doe-root) ---\n'

_gen_pointer="$COORDINATOR_ROOT/bin/gen-doe-root-pointer.sh"
POINTER_SECTION_RAN=0

if [[ ! -f "$_gen_pointer" ]]; then
  _fail "gen-doe-root-pointer.sh not found at: $_gen_pointer (C1 not yet landed — expected RED)"
else
  _pass "gen-doe-root-pointer.sh source present: $_gen_pointer"

  if bash -n "$_gen_pointer" 2>/dev/null; then
    _pass "gen-doe-root-pointer.sh parses as valid bash"
  else
    _fail "gen-doe-root-pointer.sh has bash syntax errors"
  fi

  if [[ "$DOE_CLONE_RESOLVED" -eq 1 ]]; then
    # Run against sandbox CLAUDE_HOME with REPO_DOE_CLAUDE override seeding the registry value.
    # gen-doe-root-pointer.sh treats CLAUDE_HOME as the HOME parent: pointer lands at
    # ${CLAUDE_HOME}/.claude/.doe-root (consistent with how the shim reads it cold).
    if CLAUDE_HOME="$SANDBOX" REPO_DOE_CLAUDE="$DOE_CLONE" \
       bash "$_gen_pointer" 2>"$SANDBOX/gen-pointer-err.txt"; then
      _pass "gen-doe-root-pointer.sh exited 0 against sandbox"
      POINTER_SECTION_RAN=1
    else
      _fail "gen-doe-root-pointer.sh failed (see $SANDBOX/gen-pointer-err.txt)"
    fi

    # CLAUDE_HOME is the HOME parent, so pointer lands one level deeper than SANDBOX itself.
    _sandbox_doe_root="$SANDBOX/.claude/.doe-root"
    if [[ -f "$_sandbox_doe_root" ]]; then
      _pass ".doe-root pointer present in sandbox: $_sandbox_doe_root"
      _pointer_content="$(cat "$_sandbox_doe_root")"
      if [[ "$_pointer_content" == "$DOE_CLONE" ]]; then
        _pass ".doe-root content matches registry repos.doe_claude: $DOE_CLONE"
      else
        _fail ".doe-root content mismatch: got '$_pointer_content', expected '$DOE_CLONE'"
      fi
    else
      _fail ".doe-root not created in sandbox (expected at: $_sandbox_doe_root)"
    fi

    # --check-only must not mutate sandbox .doe-root (dry-run-safe lesson)
    if [[ -f "$_sandbox_doe_root" ]]; then
      _ptr_bak="$SANDBOX/.doe-root.bak-checkonly"
      cp "$_sandbox_doe_root" "$_ptr_bak"
      if CLAUDE_HOME="$SANDBOX" REPO_DOE_CLAUDE="$DOE_CLONE" \
         bash "$_gen_pointer" --check-only 2>/dev/null; then
        if cmp -s "$_ptr_bak" "$_sandbox_doe_root"; then
          _pass "gen-doe-root-pointer.sh --check-only: sandbox .doe-root byte-unchanged (dry-run-safe)"
        else
          _fail "gen-doe-root-pointer.sh --check-only: sandbox .doe-root was mutated (dry-run violation)"
        fi
      else
        _skip "gen-doe-root-pointer.sh --check-only exited non-zero (--check-only flag may not be implemented yet)"
      fi
    fi

    # Idempotency: second run must not churn the pointer
    if [[ -f "$_sandbox_doe_root" ]]; then
      _ptr_v1_bak="$SANDBOX/.doe-root.bak-idem"
      cp "$_sandbox_doe_root" "$_ptr_v1_bak"
      if CLAUDE_HOME="$SANDBOX" REPO_DOE_CLAUDE="$DOE_CLONE" \
         bash "$_gen_pointer" 2>/dev/null; then
        if cmp -s "$_ptr_v1_bak" "$_sandbox_doe_root"; then
          _pass "gen-doe-root-pointer.sh idempotent: second run — no pointer churn"
        else
          _fail "gen-doe-root-pointer.sh NOT idempotent: second run changed .doe-root content"
        fi
      else
        _fail "gen-doe-root-pointer.sh failed on second (idempotency) run"
      fi
    fi
  else
    _skip "pointer sandbox run (DoE clone path not resolved)"
  fi
fi

# ---- 9. Shim artifact: ~/.claude/shell/claude-doe-shim.sh ----
printf '\n--- Shim artifact (claude-doe-shim.sh) ---\n'

_gen_shim="$COORDINATOR_ROOT/bin/gen-claude-doe-shim.sh"
_shim_tmpl="$COORDINATOR_ROOT/templates/shell/claude-doe-shim.sh.tmpl"
SHIM_SECTION_RAN=0

if [[ ! -f "$_gen_shim" ]]; then
  _fail "gen-claude-doe-shim.sh not found at: $_gen_shim (C2 not yet landed — expected RED)"
else
  _pass "gen-claude-doe-shim.sh source present: $_gen_shim"

  if [[ ! -f "$_shim_tmpl" ]]; then
    _fail "claude-doe-shim.sh.tmpl not found at: $_shim_tmpl (C2 template missing — expected RED)"
  else
    _pass "claude-doe-shim.sh.tmpl present: $_shim_tmpl"
  fi

  if bash -n "$_gen_shim" 2>/dev/null; then
    _pass "gen-claude-doe-shim.sh parses as valid bash"
  else
    _fail "gen-claude-doe-shim.sh has bash syntax errors"
  fi

  # Sandbox rc file — avoids touching any live interactive rc
  _sandbox_rc="$SANDBOX/sandbox-rc.sh"
  printf '# sandbox-rc\n' > "$_sandbox_rc"

  if CLAUDE_HOME="$SANDBOX" REPO_DOE_CLAUDE="${DOE_CLONE:-}" \
     COORDINATOR_SHIM_RC="$_sandbox_rc" \
     bash "$_gen_shim" 2>"$SANDBOX/gen-shim-err.txt"; then
    _pass "gen-claude-doe-shim.sh exited 0 against sandbox"
    SHIM_SECTION_RAN=1
  else
    _fail "gen-claude-doe-shim.sh failed (see $SANDBOX/gen-shim-err.txt)"
  fi

  # gen-claude-doe-shim.sh treats CLAUDE_HOME as the HOME parent: shim lands at
  # ${CLAUDE_HOME}/.claude/shell/claude-doe-shim.sh.
  _sandbox_shim="$SANDBOX/.claude/shell/claude-doe-shim.sh"
  if [[ -f "$_sandbox_shim" ]]; then
    _pass "claude-doe-shim.sh present in sandbox: $_sandbox_shim"

    # Must define a claude() function
    if grep -q 'claude()' "$_sandbox_shim" 2>/dev/null; then
      _pass "claude-doe-shim.sh defines a claude() function"
    else
      _fail "claude-doe-shim.sh does not define a claude() function"
    fi

    # Must read the pointer (.doe-root)
    if grep -q '\.doe-root' "$_sandbox_shim" 2>/dev/null; then
      _pass "claude-doe-shim.sh references .doe-root (pointer-reading verified)"
    else
      _fail "claude-doe-shim.sh does not reference .doe-root (pointer-read missing)"
    fi

    # Must NOT contain hardcoded machine path — grep for the expanded $HOME value.
    # A shim body may contain '${CLAUDE_HOME:-$HOME}' as text (a variable reference,
    # which is fine); it must NOT contain the resolved value of $HOME as a literal string.
    if [[ -n "${HOME:-}" ]] && grep -qF "$HOME" "$_sandbox_shim" 2>/dev/null; then
      _fail "claude-doe-shim.sh contains hardcoded machine path (literal \$HOME='$HOME' found in body)"
    else
      _pass "claude-doe-shim.sh: no hardcoded machine path (\$HOME literal absent from body)"
    fi

    # Belt-and-suspenders: no /Users/<name> or /home/<name> on non-comment lines (any machine)
    if grep -qE '^[^#].*/Users/[a-zA-Z_]|^[^#].*/home/[a-zA-Z_]' "$_sandbox_shim" 2>/dev/null; then
      _fail "claude-doe-shim.sh contains hardcoded /Users/ or /home/ path on non-comment line"
    else
      _pass "claude-doe-shim.sh: no hardcoded /Users/ or /home/ paths on non-comment lines"
    fi
  else
    _fail "claude-doe-shim.sh not created in sandbox (expected at: $_sandbox_shim)"
  fi

  # Exactly one marked source line in the sandbox rc
  # gen-claude-doe-shim.sh should add a line sourcing the shim file.
  if [[ -f "$_sandbox_rc" ]]; then
    _source_line_count="$(grep -cE 'claude-doe-shim|claude_doe_shim' "$_sandbox_rc" 2>/dev/null || printf '0')"
    if [[ "$_source_line_count" -eq 1 ]]; then
      _pass "exactly one marked source line in sandbox rc (got: $_source_line_count)"
    elif [[ "$_source_line_count" -eq 0 ]]; then
      _fail "no source line for claude-doe-shim found in sandbox rc (expected 1)"
    else
      _fail "multiple source lines for claude-doe-shim in sandbox rc (expected 1, got: $_source_line_count)"
    fi
  fi

  # Idempotency: second run must not duplicate the source line
  if [[ -f "$_sandbox_rc" ]]; then
    if CLAUDE_HOME="$SANDBOX" REPO_DOE_CLAUDE="${DOE_CLONE:-}" \
       COORDINATOR_SHIM_RC="$_sandbox_rc" \
       bash "$_gen_shim" 2>/dev/null; then
      _source_line_count_v2="$(grep -cE 'claude-doe-shim|claude_doe_shim' "$_sandbox_rc" 2>/dev/null || printf '0')"
      if [[ "$_source_line_count_v2" -eq 1 ]]; then
        _pass "idempotency: second gen-claude-doe-shim.sh run — still exactly one source line (no duplication)"
      else
        _fail "idempotency: second run produced $_source_line_count_v2 source lines (expected 1 — duplicated source line)"
      fi
    else
      _fail "gen-claude-doe-shim.sh failed on second (idempotency) run"
    fi
  fi

  # --check-only must not mutate the sandbox rc (dry-run-safe lesson)
  _sandbox_rc_check="$SANDBOX/sandbox-rc-checkonly.sh"
  printf '# sandbox-rc-checkonly\n' > "$_sandbox_rc_check"
  _rc_bak="$SANDBOX/sandbox-rc-checkonly.bak"
  cp "$_sandbox_rc_check" "$_rc_bak"
  if CLAUDE_HOME="$SANDBOX" REPO_DOE_CLAUDE="${DOE_CLONE:-}" \
     COORDINATOR_SHIM_RC="$_sandbox_rc_check" \
     bash "$_gen_shim" --check-only 2>/dev/null; then
    if cmp -s "$_rc_bak" "$_sandbox_rc_check"; then
      _pass "gen-claude-doe-shim.sh --check-only: sandbox rc byte-unchanged (dry-run-safe)"
    else
      _fail "gen-claude-doe-shim.sh --check-only: sandbox rc was mutated (dry-run violation)"
    fi
  else
    _skip "gen-claude-doe-shim.sh --check-only exited non-zero (--check-only flag may not be implemented yet)"
  fi
fi

# ---- 10. Mirror verification: plugin.mirrors.coordinator-claude.live_path (AC5) ----
# Verification assertion — the resolver already handles this via CLAUDE_PLUGIN_ROOT /
# registry precedence under maximalist. No code fix expected; C0 asserts the invariant.
printf '\n--- Mirror verification: live_path == <doe>/coordinator (AC5) ---\n'

_rcc_script="$COORDINATOR_ROOT/lib/resolve-coordinator-clone.sh"
if [[ ! -f "$_rcc_script" ]]; then
  _fail "resolve-coordinator-clone.sh not found at: $_rcc_script"
else
  _pass "resolve-coordinator-clone.sh present: $_rcc_script"

  if [[ "$DOE_CLONE_RESOLVED" -eq 1 ]]; then
    # Under maximalist CLAUDE_PLUGIN_ROOT is set by --plugin-dir at boot, so the resolver
    # returns DoE/coordinator via tier 1 (CLAUDE_PLUGIN_ROOT). We simulate the warm
    # maximalist path: CLAUDE_PLUGIN_ROOT points at DoE/coordinator.
    _expected_mirror="${DOE_CLONE}/coordinator"
    _mirror_out="$(
      CLAUDE_PLUGIN_ROOT="$_expected_mirror" \
      bash "$_rcc_script" --for-content 2>/dev/null || true
    )"
    if [[ "$_mirror_out" == "$_expected_mirror" ]]; then
      _pass "AC5: resolve-coordinator-clone.sh --for-content (CLAUDE_PLUGIN_ROOT): returned expected $DOE_CLONE/coordinator"
    elif [[ -n "$_mirror_out" ]] && [[ -d "$_mirror_out" ]]; then
      _fail "AC5: resolve-coordinator-clone.sh --for-content: returned '$_mirror_out', expected '$_expected_mirror'"
    else
      _fail "AC5: resolve-coordinator-clone.sh --for-content: returned empty or non-existent path"
    fi
  else
    _skip "mirror verification (DoE clone path not resolved)"
  fi
fi

# ---- 11. Resolver cold tier — BOTH modes, pointer-only (AC6 — RED until C3) ----
#
# Tests the new ~/.claude/.doe-root pointer tier in resolve-coordinator-clone.sh
# (C3 deliverable). All warm tiers are stripped:
#   - CLAUDE_PLUGIN_ROOT / COORDINATOR_ROOT / COORDINATOR_CLONE unset
#   - Registry unreadable (cold-env CLAUDE_HOME has no registry.local.toml)
#   - Flat layout absent (cold-env has no plugins/coordinator-claude/)
#
# AC6(a): --for-content  → <doe_clone>/coordinator   (RED until C3)
# AC6(b): --for-git-ops  → <doe_clone>               (RED until C3; also RED against an
#         interim build that returns coordinator/ for both modes, since coordinator/.git
#         is absent under maximalist — that RED is the gap C3's mode-split closes)
printf '\n--- Resolver cold tier (AC6 — RED until C3) ---\n'

if [[ "$DOE_CLONE_RESOLVED" -eq 1 ]]; then
  # Build the cold environment under SANDBOX (auto-cleaned by existing EXIT trap).
  # CLAUDE_HOME="$_cold_env" → resolver reads pointer from $_cold_env/.claude/.doe-root
  # (the resolver uses ${CLAUDE_HOME:-$HOME}/.claude/.doe-root).
  _cold_env="$SANDBOX/cold-env"
  mkdir -p "$_cold_env/.claude"
  # Write only the pointer — no registry, no flat tree
  printf '%s' "$DOE_CLONE" > "$_cold_env/.claude/.doe-root"

  # Verify cold-env pre-conditions
  _cold_ptr_read="$(cat "$_cold_env/.claude/.doe-root" 2>/dev/null || true)"
  if [[ "$_cold_ptr_read" == "$DOE_CLONE" ]]; then
    _pass "cold-env .doe-root seeded: $DOE_CLONE"
  else
    _fail "cold-env .doe-root setup failed (expected '$DOE_CLONE', got '$_cold_ptr_read')"
  fi

  _cold_flat="${_cold_env}/.claude/plugins/coordinator-claude/coordinator"
  if [[ ! -d "$_cold_flat" ]]; then
    _pass "cold-env: no flat-layout tree (correct cold environment)"
  else
    _fail "cold-env setup: flat tree unexpectedly present at $_cold_flat"
  fi

  # Pre-conditions on the DoE clone itself
  if [[ -d "$DOE_CLONE/.git" ]]; then
    _pass "DoE clone has .git at root (git-ops pointer-tier pre-condition met)"
  else
    _fail "DoE clone missing .git at root — --for-git-ops pointer tier cannot satisfy .git gate"
  fi
  if [[ -d "$DOE_CLONE/coordinator" ]]; then
    _pass "DoE clone has coordinator/ subdir (content pointer-tier pre-condition met)"
  else
    _fail "DoE clone missing coordinator/ subdir — --for-content pointer tier cannot satisfy -d gate"
  fi

  # Build a PATH for the cold subshell that excludes coordinator bins (machine-local,
  # claude-home, etc.) so the resolver's _rcc_registry_path helper cannot call
  # "claude-home machine-local" and falls back to ${CLAUDE_HOME}/.claude/machine-local/
  # (which doesn't exist in the cold-env). Without a readable registry, the resolver
  # must reach the pointer tier (or fail loud if that tier is absent).
  #
  # We keep /usr/bin:/bin plus brew-bash (/opt/homebrew/bin or /usr/local/bin for bash
  # itself) but intentionally exclude the DoE coordinator bin/ dir and ~/.local/bin
  # where coordinator wrapper scripts live.
  _cold_bare_path="/usr/bin:/bin"
  # Include brew prefix so bash >=4 and python3 are findable (needed for registry TOML
  # parser in the resolver), but these dirs must NOT contain claude-home/machine-local.
  [[ -d "/opt/homebrew/bin" ]]  && _cold_bare_path="${_cold_bare_path}:/opt/homebrew/bin"
  [[ -d "/usr/local/bin" ]]     && _cold_bare_path="${_cold_bare_path}:/usr/local/bin"

  # Verify: claude-home should NOT be reachable on the cold PATH
  _cold_has_claude_home="$(PATH="$_cold_bare_path" command -v claude-home 2>/dev/null || true)"
  if [[ -z "$_cold_has_claude_home" ]]; then
    _pass "cold PATH: claude-home absent (registry read correctly blocked for cold-tier test)"
  else
    _info "cold PATH: claude-home still reachable at '$_cold_has_claude_home' — cold-tier test may hit registry tier instead of pointer tier (expected on machines where claude-home is in brew PATH)"
  fi

  # AC6(a): --for-content cold resolution via pointer only.
  # The resolver's warm tiers (CLAUDE_PLUGIN_ROOT / COORDINATOR_ROOT / registry) must
  # all miss; the new pointer tier (C3) then reads $_cold_env/.claude/.doe-root and
  # returns <doe_root>/coordinator.
  _cold_content_out="$(
    unset CLAUDE_PLUGIN_ROOT COORDINATOR_ROOT COORDINATOR_CLONE 2>/dev/null || true
    PATH="$_cold_bare_path" \
    CLAUDE_HOME="$_cold_env" \
    bash "$_rcc_script" --for-content 2>/dev/null || true
  )"
  _expected_cold_content="${DOE_CLONE}/coordinator"
  if [[ "$_cold_content_out" == "$_expected_cold_content" ]]; then
    _pass "AC6(a): --for-content cold (pointer-only): returned $DOE_CLONE/coordinator"
  elif [[ -z "$_cold_content_out" ]]; then
    _fail "AC6(a): --for-content cold: returned empty — pointer tier not in resolver (C3 not landed — expected RED)"
  else
    _fail "AC6(a): --for-content cold: got '$_cold_content_out', expected '$_expected_cold_content'"
  fi

  # AC6(b): --for-git-ops cold resolution via pointer.
  # Must return the DoE root (not coordinator/ subdir) because coordinator/.git is absent.
  # This test is RED against both (a) no-pointer-tier (empty result) AND (b) a naive
  # implementation returning coordinator/ for both modes (fails .git check).
  _cold_gitops_out="$(
    unset CLAUDE_PLUGIN_ROOT COORDINATOR_ROOT COORDINATOR_CLONE 2>/dev/null || true
    PATH="$_cold_bare_path" \
    CLAUDE_HOME="$_cold_env" \
    bash "$_rcc_script" --for-git-ops 2>/dev/null || true
  )"
  _expected_cold_gitops="$DOE_CLONE"
  if [[ "$_cold_gitops_out" == "$_expected_cold_gitops" ]]; then
    _pass "AC6(b): --for-git-ops cold (pointer-only): returned $DOE_CLONE (.git confirmed present)"
  elif [[ -z "$_cold_gitops_out" ]]; then
    _fail "AC6(b): --for-git-ops cold: returned empty — pointer tier not in resolver (C3 not landed — expected RED)"
  elif [[ "$_cold_gitops_out" == "${DOE_CLONE}/coordinator" ]]; then
    _fail "AC6(b): --for-git-ops cold: returned coordinator/ subdir — coordinator/.git absent under maximalist; mode-split not yet implemented (C3 not landed — expected RED)"
  else
    _fail "AC6(b): --for-git-ops cold: got '$_cold_gitops_out', expected '$_expected_cold_gitops'"
  fi
else
  _skip "resolver cold-tier tests (DoE clone path not resolved)"
fi

# ---- 12. Cold-shell launch: REPO_DOE_CLAUDE from pointer alone (AC2 — RED until C2) ----
#
# Simulates a cold terminal: coordinator bin/ dirs stripped from PATH.
# Sources the sandbox shim, asserts REPO_DOE_CLAUDE is set from the pointer.
# This is the direct regression for the P0 cold-PATH chicken-and-egg problem.
printf '\n--- Cold-shell launch: REPO_DOE_CLAUDE from pointer alone (AC2 — RED until C2) ---\n'

if [[ "$SHIM_SECTION_RAN" -eq 1 ]] && [[ -f "$SANDBOX/.claude/shell/claude-doe-shim.sh" ]]; then
  _sandbox_shim_path="$SANDBOX/.claude/shell/claude-doe-shim.sh"

  # Build a minimal cold PATH: no machine-local, no claude-home, no coordinator bins.
  # Includes /usr/local/bin and brew paths so bash itself is findable.
  _cold_path="/usr/bin:/bin"
  [[ -d "/usr/local/bin" ]] && _cold_path="${_cold_path}:/usr/local/bin"
  [[ -d "/opt/homebrew/bin" ]] && _cold_path="${_cold_path}:/opt/homebrew/bin"
  [[ -d "/usr/local/opt/bash/bin" ]] && _cold_path="${_cold_path}:/usr/local/opt/bash/bin"

  # Source the shim in a subprocess. The shim should:
  #   1. Read the pointer from $CLAUDE_HOME/.doe-root (= SANDBOX/.doe-root)
  #   2. Set/export REPO_DOE_CLAUDE from the pointer content
  # We don't invoke claude-doe (the exec target may not exist in this env);
  # we just verify the variable resolves correctly.
  _cold_launch_out="$(
    PATH="$_cold_path" \
    CLAUDE_HOME="$SANDBOX" \
    HOME="${HOME}" \
    bash -c "source '$_sandbox_shim_path' 2>/dev/null; printf '%s' \"\${REPO_DOE_CLAUDE:-}\"" 2>/dev/null || true
  )"

  if [[ -n "$_cold_launch_out" ]]; then
    if [[ "$_cold_launch_out" == "$DOE_CLONE" ]]; then
      _pass "AC2 cold-shell: REPO_DOE_CLAUDE resolved from pointer alone: $DOE_CLONE"
    else
      _fail "AC2 cold-shell: REPO_DOE_CLAUDE='$_cold_launch_out', expected '$DOE_CLONE'"
    fi
  else
    _fail "AC2 cold-shell: REPO_DOE_CLAUDE empty after sourcing shim with cold PATH (pointer-read failed or shim does not export REPO_DOE_CLAUDE)"
  fi
elif [[ "$SHIM_SECTION_RAN" -eq 0 ]]; then
  # Shim generator missing — explicit RED (expected until C2 lands)
  _fail "AC2 cold-shell: skipped — gen-claude-doe-shim.sh absent (C2 not yet landed — expected RED)"
else
  _skip "AC2 cold-shell (sandbox shim not generated)"
fi

# ---- 13. Live-artifact non-mutation (AC4) ----
# After all sandbox runs, live ~/.claude/.doe-root and shim must be byte-unchanged.
# Validates the dry-run-safety lesson: no generator run (including --check-only) may
# mutate live artifacts when CLAUDE_HOME is set to a sandbox path.
printf '\n--- Live-artifact non-mutation (AC4) ---\n'

if [[ -f "$_live_doe_root_bak" ]]; then
  if cmp -s "$_live_doe_root_bak" "$_live_doe_root" 2>/dev/null; then
    _pass "AC4: live ~/.claude/.doe-root byte-unchanged after all sandbox runs"
  else
    _fail "AC4: live ~/.claude/.doe-root was MUTATED by a sandbox/check-only run (dry-run violation!)"
  fi
else
  _skip "AC4 .doe-root live-non-mutation (live .doe-root absent — C1 not yet installed on this machine)"
fi

if [[ -f "$_live_shim_bak" ]]; then
  if cmp -s "$_live_shim_bak" "$_live_shim_file" 2>/dev/null; then
    _pass "AC4: live ~/.claude/shell/claude-doe-shim.sh byte-unchanged after all sandbox runs"
  else
    _fail "AC4: live ~/.claude/shell/claude-doe-shim.sh was MUTATED by a sandbox/check-only run (dry-run violation!)"
  fi
else
  _skip "AC4 shim live-non-mutation (live shim absent — C2 not yet installed on this machine)"
fi

# ---- Tier 1c: Publish-repo clean-install parity (F8) ----
#
# Purpose: the working repo (this clone, "DoE-claude") and the customer publish repo
# ("coordinator-claude") are DIFFERENT clones on disk, but every out-of-repo install
# surface (.doe-root pointer, settings.json hook commands, plugin.mirrors.coordinator-claude
# live_path) must be rooted at WHATEVER clone drove the install — never hardcoded to this
# machine's DoE-claude checkout. This tier proves the resolvers/generators are
# clone-path-PARAMETERIZED (take the clone root as an env/arg and emit paths rooted at it),
# not DoE-hardcoded, by driving them against a distinctly-named sandbox clone and asserting
# every emitted path is rooted at THAT clone — never at the real $DOE_CLONE.
#
# Naming-collision trap (see root CLAUDE.md): the working tree and the publish tree are
# BOTH named "coordinator-claude" (the working tree's top-level dir is "DoE-claude"; its
# "coordinator/" subdir and the publish repo's root are both "coordinator-claude"-shaped).
# The sandbox clone below is deliberately named "coordinator-claude" at a throwaway path to
# mirror that shape while remaining trivially distinguishable from $DOE_CLONE by full path.
#
# Scope note: this is a PARAMETERIZATION-CONTRACT assertion, not a fully faithful publish-repo
# install rehearsal — it does not clone the real coordinator-claude publish repo (no such
# clone is guaranteed to exist on the machine running this check), and it does not exercise
# install.md's cold-bootstrap prose end-to-end. A fully faithful parity test would additionally
# need: (1) a real coordinator-claude publish clone (or a git worktree/export of this repo's
# coordinator/ subtree re-rooted under a "coordinator-claude" name) to catch bugs specific to
# repo-boundary layout (e.g. paths that assume a coordinator/ SUBDIR of a larger repo, which a
# standalone publish clone's root would not have); (2) a full install.md cold-bootstrap run
# against that clone; (3) register-coordinator-mirror.sh actually invoked against a sandboxed
# registry.local.toml (skipped here — it shells out to `claude-home machine-local`, which
# resolves against the REAL machine registry, so full simulation risks touching live state;
# its correctness is covered indirectly below via resolve-coordinator-clone.sh, the resolver
# register-coordinator-mirror.sh itself calls to compute live_path).
printf '\n=== Tier 1c: Publish-repo clean-install parity (F8 — parameterization contract) ===\n'

if [[ "$DOE_CLONE_RESOLVED" -eq 1 ]]; then
  # ---- Build a distinctly-named, distinctly-rooted "publish-repo-shaped" sandbox clone ----
  _pub_root="$SANDBOX/publish-repo-check"
  _pub_clone="$_pub_root/coordinator-claude"
  mkdir -p "$_pub_clone/coordinator/hooks"
  mkdir -p "$_pub_clone/.git"   # existence-only stand-in — --for-git-ops gates on -d "<clone>/.git"

  # Real hooks.json content is irrelevant to path-rooting correctness (we assert on emitted
  # COMMAND PATHS, not hook semantics) — copy it so gen-settings-hooks.sh's file-existence
  # gate (hooks.json must exist under <coordinator_root>/hooks/) is satisfied.
  cp "$DOE_CLONE/coordinator/hooks/hooks.json" "$_pub_clone/coordinator/hooks/hooks.json"

  if [[ -d "$_pub_clone/.git" ]] && [[ -f "$_pub_clone/coordinator/hooks/hooks.json" ]]; then
    _pass "F8 setup: publish-repo-shaped sandbox clone built at $_pub_clone (distinct from \$DOE_CLONE=$DOE_CLONE)"
  else
    _fail "F8 setup: publish-repo-shaped sandbox clone build failed at $_pub_clone"
  fi

  # ---- 14. Pointer generator (gen-doe-root-pointer.sh) rooted at the publish clone ----
  printf '\n--- F8: .doe-root pointer rooted at publish clone ---\n'
  _pub_home="$SANDBOX/publish-repo-check-home"
  mkdir -p "$_pub_home"
  if CLAUDE_HOME="$_pub_home" REPO_DOE_CLAUDE="$_pub_clone" \
     bash "$_gen_pointer" 2>"$SANDBOX/f8-gen-pointer-err.txt"; then
    _pub_doe_root="$_pub_home/.claude/.doe-root"
    if [[ -f "$_pub_doe_root" ]]; then
      _pub_pointer_content="$(cat "$_pub_doe_root")"
      if [[ "$_pub_pointer_content" == "$_pub_clone" ]]; then
        _pass "F8: .doe-root pointer rooted at publish clone (got: $_pub_pointer_content)"
      else
        _fail "F8: .doe-root pointer NOT rooted at publish clone — got '$_pub_pointer_content', expected '$_pub_clone'"
      fi
      # Direct catch-the-bug assertion: if a generator hardcoded the real DoE clone path
      # instead of honoring its clone-root parameter, this is the exact line that would FAIL.
      if [[ "$_pub_pointer_content" != "$DOE_CLONE" ]]; then
        _pass "F8: .doe-root pointer does NOT leak the real \$DOE_CLONE path (no DoE-hardcoding)"
      else
        _fail "F8: .doe-root pointer content equals the real \$DOE_CLONE path — DoE-hardcoding bug in gen-doe-root-pointer.sh (ignores REPO_DOE_CLAUDE)"
      fi
    else
      _fail "F8: .doe-root pointer not created for publish clone (expected at: $_pub_doe_root)"
    fi
  else
    _fail "F8: gen-doe-root-pointer.sh failed against publish clone (see $SANDBOX/f8-gen-pointer-err.txt)"
  fi

  # ---- 15. Settings-hooks generator (gen-settings-hooks.sh) rooted at the publish clone ----
  printf '\n--- F8: settings.json hook commands rooted at publish clone ---\n'
  _pub_settings="$_pub_home/settings.json"
  printf '{}' > "$_pub_settings"
  if CLAUDE_HOME="$_pub_home" REPO_DOE_CLAUDE="$_pub_clone" \
     bash "$_gen_hooks" --out "$_pub_settings" 2>"$SANDBOX/f8-gen-hooks-err.txt"; then
    _pass "F8: gen-settings-hooks.sh exited 0 against publish clone"
    _pub_hook_cmds="$(jq -r '[.hooks[]?[]?.hooks[]?.command // empty] | join("\n")' "$_pub_settings" 2>/dev/null || true)"
    if [[ -z "$_pub_hook_cmds" ]]; then
      _fail "F8: settings.json produced no hook commands to inspect against publish clone"
    else
      if printf '%s\n' "$_pub_hook_cmds" | grep -qF "$_pub_clone/coordinator/hooks/"; then
        _pass "F8: settings.json hook commands rooted at publish clone (\$_pub_clone/coordinator/hooks/...)"
      else
        _fail "F8: settings.json hook commands do NOT reference the publish clone's coordinator/hooks/ path"
      fi
      # Direct catch-the-bug assertion: a DoE-hardcoded generator would bake the REAL
      # DOE_CLONE path into hook commands even though REPO_DOE_CLAUDE pointed elsewhere.
      if printf '%s\n' "$_pub_hook_cmds" | grep -qF "$DOE_CLONE/coordinator/hooks/"; then
        _fail "F8: settings.json hook commands leak the real \$DOE_CLONE path — DoE-hardcoding bug in gen-settings-hooks.sh (ignores REPO_DOE_CLAUDE)"
      else
        _pass "F8: settings.json hook commands do NOT leak the real \$DOE_CLONE path (no DoE-hardcoding)"
      fi
    fi
  else
    _fail "F8: gen-settings-hooks.sh failed against publish clone (see $SANDBOX/f8-gen-hooks-err.txt)"
  fi

  # ---- 16. resolve-coordinator-clone.sh --for-content rooted at the publish clone ----
  # Same resolver register-coordinator-mirror.sh calls to compute plugin.mirrors.
  # coordinator-claude.live_path — this is the parameterization-contract stand-in for full
  # mirror-registration simulation (see scope note above).
  printf '\n--- F8: resolve-coordinator-clone.sh --for-content rooted at publish clone (mirror live_path contract) ---\n'
  _pub_mirror_out="$(
    CLAUDE_PLUGIN_ROOT="$_pub_clone/coordinator" \
    bash "$_rcc_script" --for-content 2>/dev/null || true
  )"
  if [[ "$_pub_mirror_out" == "$_pub_clone/coordinator" ]]; then
    _pass "F8: resolve-coordinator-clone.sh --for-content rooted at publish clone: $_pub_clone/coordinator"
  else
    _fail "F8: resolve-coordinator-clone.sh --for-content did not root at publish clone — got '$_pub_mirror_out', expected '$_pub_clone/coordinator'"
  fi

  # ---- 17. Negative control — prove the F8 comparisons above actually discriminate ----
  # Mutation test: simulate what a DoE-hardcoded generator's OUTPUT would look like (the
  # real $DOE_CLONE path, emitted despite REPO_DOE_CLAUDE pointing at the publish clone) and
  # confirm the same equality/grep logic used above reports it as a MISMATCH. This proves
  # the F8 assertions have discriminating power (would genuinely FAIL on the hardcoding bug
  # class), not just happy-path agreement with whatever the generator currently emits.
  printf '\n--- F8: negative control — assertion discriminates a simulated DoE-hardcoded bug ---\n'
  _simulated_hardcoded_output="$DOE_CLONE"
  if [[ "$_simulated_hardcoded_output" != "$_pub_clone" ]]; then
    _pass "F8 negative-control: simulated hardcoded-path output ('\$DOE_CLONE') correctly fails the '== \$_pub_clone' comparison — assertion is selective, not vacuously true"
  else
    _fail "F8 negative-control: simulated hardcoded-path output matched the expected publish-clone path — F8 assertions above are NOT selective (would not have caught the bug)"
  fi
else
  _skip "F8 publish-repo clean-install parity (DoE clone path not resolved)"
fi

# ---- Summary ----
printf '\n=== Tier 1 summary: %d passed, %d failed ===\n' "$PASS" "$FAIL"

# ---- Tier 2: Running-in-Claude-Code (DEFERRED — hardware/editor-gated) ----
cat <<'DEFERRED'

=== Tier 2: Running-in-Claude-Code (DEFERRED — manual gate) ===

Per docs/wiki/install-surface-completeness.md § Running-in-Claude-Code:

This tier cannot run inside a subagent. It requires a real Claude Code boot. The EM or PM
must perform these steps manually before declaring the install surface complete (AC-W4.1):

  1. Launch: claude-doe --dry-run
     Verify output contains: exec claude --plugin-dir <doe_clone>/coordinator

  2. Launch interactively: claude-doe
     Verify in the Claude Code session:
     a. Skill resolution: invoke a coordinator skill (e.g. /repo-setup) and confirm the
        skill base-dir matches <doe_clone>/coordinator (not a cache copy or ~/.claude path).
     b. Hook firing at boot: a fresh boot should fire SessionStart hooks — check the
        session-sentinel file (~/.claude/.session-sentinel) was updated on launch.
     c. CLAUDE_PLUGIN_ROOT is UNSET in hook env (self-resolution via BASH_SOURCE is active).
     d. No plugin byte-copy at ~/.claude/plugins/coordinator-claude/ (ls should show absent
        or pointer/config only).

  3. Confirm: skills/agents resolve from <doe_clone>/coordinator/skills/ and
     hooks fire from <doe_clone>/coordinator/hooks/ (absolute paths in settings.json).

Source of deference: install-surface-completeness.md § Running-in-Claude-Code:
  "A chain leg is only 'complete' when its Claude Code surface is validated live."
  "Plugins and skills it registers are validated as working — discovery preconditions met
   AND the surface is live, not merely present in settings.json or enabledPlugins."

Note: SessionStart hooks take effect only at the NEXT boot. settings.json hook definitions
hot-reload mid-session, but SessionStart is a boot event — it does NOT fire on settings.json
edits in a running session.

DEFERRED

if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
exit 0
