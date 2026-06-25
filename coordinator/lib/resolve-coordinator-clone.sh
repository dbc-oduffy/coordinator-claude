#!/usr/bin/env bash
# resolve-coordinator-clone.sh — coordinator install-root resolver.
#
# Two outputs (select via --for-git-ops or --for-content):
#
#   --for-git-ops   The .git-backed clone directory. Required for operations
#                   that must address the git history (drift probe, git log,
#                   refresh-plugin-live-install.sh). Fails loud if no clone
#                   with a .git directory can be located.
#
#   --for-content   Highest-precedence readable payload directory. Preferred
#                   for loading libs, agents, snippets, query-records.js, etc.
#                   A contributor's live dev-loop clone wins over any cache so
#                   in-progress edits stay authoritative; the versioned cache is
#                   the fallback for fleet/CI installs.
#
# Precedence:
#
#   --for-git-ops:
#     1. COORDINATOR_CLONE env var (non-empty, must have .git/)
#     2. registry plugin.mirrors.coordinator-claude.live_path (read-mirrors.sh)
#     3. Flat layout: ~/.claude/plugins/coordinator-claude/coordinator — IF it
#        has a .git/ (i.e. this is a live source_is_live install)
#     4. FAIL-LOUD — no git-backed clone found
#
#   --for-content:
#     1. CLAUDE_PLUGIN_ROOT env var (set by harness/install scripts, wins over
#        all so harness-injected override and test sandboxes work cleanly)
#     2. COORDINATOR_ROOT env var (explicit content-root override)
#     3. registry plugin.mirrors.coordinator-claude.live_path (clone is
#        authoritative — dev-loop edits are live in the clone)
#     4. Versioned cache: newest dir under
#        ~/.claude/plugins/cache/coordinator-claude/coordinator/*/
#        (DR-148-safe: bash semver-compare loop, no sort -rV/realpath/grep -P)
#     5. Flat layout: ~/.claude/plugins/coordinator-claude/coordinator
#     6. FAIL-LOUD — no readable content root found
#
# When sourced (no arguments), sets two variables in the CALLER's scope only
# (not exported to child processes — callers that need child inheritance must
# export explicitly; the 13 integration sites all read the caller-scope var):
#   COORDINATOR_CLONE        — the for-git-ops resolved path (empty if none,
#                              but see NOTE below — sourcing does NOT fail-loud)
#   COORDINATOR_CONTENT_ROOT — the for-content resolved path (empty if none)
#
# When run as a standalone CLI (--for-git-ops|--for-content), prints the
# resolved path to stdout and exits non-zero on resolution failure.
#
# NOTE on sourced mode: When sourced, this lib sets both variables but does NOT
# exit on failure — it is the caller's responsibility to check for empty values
# when they matter. The fail-loud contract applies to CLI (standalone) mode only.
# This mirrors resolve-python.sh's convention: PYTHON_BIN="" (not exit 1) on
# source, to allow graceful degradation in callers that test [[ -z "$VAR" ]].
#
# Idempotent re-source: variables are overwritten on each source.
# Callers must not declare COORDINATOR_CLONE or COORDINATOR_CONTENT_ROOT as
# readonly — re-source idempotency requires overwriting both.
#
# Public contract surface: CLI entrypoint and env-var overrides are stable.
# Peer repos (project-rag, ue-addon, holodeck) bind here instead of each
# vendoring a cache-glob fallback.
# Spec backlink: docs/plans/2026-06-23-coordinator-install-surface-dogfood-hardening.md § C2a
#
# Cross-platform shell:
#   - Parses and runs under bash 3.2 (no declare -A, mapfile, ${v^^}).
#   - DR-148: semver-compare bash loop for glob; no sort -rV (GNU-only).
#   - No realpath, no grep -P.
#   - No GNU-isms: tests use [[ ]] not (( )) for non-arithmetic, no sed -i.

# ---------------------------------------------------------------------------
# Guard against bash 3.2 syntax traps — none used here, but document intent.
# Any bash-4 idiom added in future needs a BASH_VERSINFO guard.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Helper: derive the machine-local registry path.
# Falls back to ~/.claude/machine-local/registry.local.toml when claude-home
# is not available (e.g. during initial install before PATH is seeded).
# ---------------------------------------------------------------------------
_rcc_registry_path() {
  local _reg=""
  if command -v claude-home >/dev/null 2>&1; then
    _reg="$(claude-home machine-local 2>/dev/null)/registry.local.toml"
  else
    # Derive $HOME from env — same chain as _claude_home.py
    local _home="${CLAUDE_HOME:-${HOME:-${USERPROFILE:-}}}"
    if [[ -z "$_home" ]]; then
      return 1
    fi
    _reg="${_home}/.claude/machine-local/registry.local.toml"
  fi
  printf '%s' "$_reg"
}

# ---------------------------------------------------------------------------
# Helper: read plugin.mirrors.coordinator-claude.live_path from the registry.
#
# Uses Python inline script (same technique as read-mirrors.sh) to parse the
# TOML that register-coordinator-mirror.sh writes. Returns empty string when
# the registry is absent, the plugin is not registered, or no Python available.
#
# Reads both nested-table form ([plugin.mirrors.coordinator-claude]) and flat
# dotted-key form ("plugin.mirrors.coordinator-claude.live_path" = "...") to
# match what register-coordinator-mirror.sh actually writes.
# ---------------------------------------------------------------------------
_rcc_registry_live_path() {
  local _reg
  _reg="$(_rcc_registry_path)" || return 0
  [[ -f "$_reg" ]] || return 0

  # Resolve Python — same multi-name probe used by register-coordinator-mirror.sh
  local _py=""
  for _cand in python3 python py; do
    if command -v "$_cand" >/dev/null 2>&1; then
      _py="$_cand"
      break
    fi
  done
  [[ -z "$_py" ]] && return 0

  "$_py" - "$_reg" <<'PYEOF' 2>/dev/null
import sys
from pathlib import Path

reg_path = Path(sys.argv[1])
if not reg_path.exists():
    sys.exit(0)

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        # tomllib unavailable; fall through silently
        sys.exit(0)

try:
    data = tomllib.loads(reg_path.read_text(encoding="utf-8"))
except Exception:
    sys.exit(0)

# Source 1: nested table form [plugin.mirrors.coordinator-claude]
nested = data.get("plugin", {}).get("mirrors", {}).get("coordinator-claude", {})
if isinstance(nested, dict):
    live = nested.get("live_path", "")
    if live:
        print(live)
        sys.exit(0)

# Source 2: flat dotted-key form written by `machine-local set`
key = "plugin.mirrors.coordinator-claude.live_path"
val = data.get(key, "")
if val:
    print(val)
    sys.exit(0)

sys.exit(0)
PYEOF
}

# ---------------------------------------------------------------------------
# Helper: derive ~/.claude/ base from env (same chain as _claude_home.py).
# ---------------------------------------------------------------------------
_rcc_claude_home_dir() {
  local _home="${CLAUDE_HOME:-${HOME:-${USERPROFILE:-}}}"
  if [[ -z "$_home" ]]; then
    # Last resort: ask Python if available
    if command -v python3 >/dev/null 2>&1; then
      _home="$(python3 -c 'from pathlib import Path; print(Path.home())' 2>/dev/null)" # verify-no-console-flash: allow — last-resort one-shot path discovery only when CLAUDE_HOME/HOME/USERPROFILE are all empty; dead path on any normal system
    fi
  fi
  [[ -n "$_home" ]] && printf '%s' "${_home}/.claude"
}

# ---------------------------------------------------------------------------
# Helper: find newest versioned cache dir (DR-148-safe, semver-aware).
# Pattern: ~/.claude/plugins/cache/coordinator-claude/coordinator/*/
# Uses a bash loop splitting each basename on '.' and comparing numerically
# — no sort -rV (GNU-only), no realpath, no grep -P. Correctly resolves
# 2.10.0 > 2.9.0 (lex sort would invert this). DR-148 compliant: bash 3.2,
# BSD coreutils.
# Review: patrik — lexicographic sort -r inverts 2.9.0/2.10.0; replace with
# numeric-compare loop so newest-version-wins holds across minor version bumps.
# Returns empty if no versioned cache dirs exist.
# ---------------------------------------------------------------------------
_rcc_newest_cache() {
  local _claude_home
  _claude_home="$(_rcc_claude_home_dir)" || return 0
  local _cache_parent="${_claude_home}/plugins/cache/coordinator-claude/coordinator"
  [[ -d "$_cache_parent" ]] || return 0

  local _newest="" _newest_a=0 _newest_b=0 _newest_c=0
  local _d _base _a _b _c _rest
  for _d in "${_cache_parent}"/*/; do
    # Strip trailing slash; skip if glob unexpanded (no dirs present)
    _base="${_d%/}"
    [[ -d "$_base" ]] || continue
    _base="${_base##*/}"
    # Split basename on '.' into major.minor.patch (non-numeric parts map to 0
    # via arithmetic context; extra components are ignored).
    _a="${_base%%.*}"; _rest="${_base#*.}"
    _b="${_rest%%.*}"; _c="${_rest#*.}"
    # Strip any non-numeric suffix (e.g. pre-release labels) for comparison.
    _a="${_a%%[!0-9]*}"; _b="${_b%%[!0-9]*}"; _c="${_c%%[!0-9]*}"
    _a="${_a:-0}"; _b="${_b:-0}"; _c="${_c:-0}"
    if [[ "$_a" -gt "$_newest_a" ]] || \
       { [[ "$_a" -eq "$_newest_a" ]] && [[ "$_b" -gt "$_newest_b" ]]; } || \
       { [[ "$_a" -eq "$_newest_a" ]] && [[ "$_b" -eq "$_newest_b" ]] && [[ "$_c" -gt "$_newest_c" ]]; }; then
      _newest="${_d%/}"
      _newest_a="$_a"; _newest_b="$_b"; _newest_c="$_c"
    fi
  done

  [[ -d "$_newest" ]] && printf '%s' "$_newest"
}

# ---------------------------------------------------------------------------
# Resolve for-git-ops
# ---------------------------------------------------------------------------
_rcc_resolve_git_ops() {
  # 1. COORDINATOR_CLONE env var
  if [[ -n "${COORDINATOR_CLONE:-}" ]]; then
    if [[ -d "${COORDINATOR_CLONE}/.git" ]]; then
      printf '%s' "$COORDINATOR_CLONE"
      return 0
    else
      printf 'resolve-coordinator-clone: COORDINATOR_CLONE is set to "%s" but it has no .git directory\n' "$COORDINATOR_CLONE" >&2
      return 1
    fi
  fi

  # 2. Registry live_path
  local _live
  _live="$(_rcc_registry_live_path)"
  if [[ -n "$_live" ]]; then
    if [[ -d "${_live}/.git" ]]; then
      printf '%s' "$_live"
      return 0
    fi
    # Registry entry present but no .git — not a git-backed clone; fall through
  fi

  # 3. Flat layout: ~/.claude/plugins/coordinator-claude/coordinator with .git
  local _claude_home
  _claude_home="$(_rcc_claude_home_dir)"
  if [[ -n "$_claude_home" ]]; then
    local _flat="${_claude_home}/plugins/coordinator-claude/coordinator"
    if [[ -d "${_flat}/.git" ]]; then
      printf '%s' "$_flat"
      return 0
    fi
  fi

  # 4. Fail-loud
  printf 'resolve-coordinator-clone --for-git-ops: no git-backed coordinator clone found.\n' >&2
  printf '  Tried: COORDINATOR_CLONE env, registry plugin.mirrors.coordinator-claude.live_path,\n' >&2
  printf '         flat ~/.claude/plugins/coordinator-claude/coordinator (no .git in any)\n' >&2
  printf '  Run: coordinator:install OR set COORDINATOR_CLONE to the clone path.\n' >&2
  return 1
}

# ---------------------------------------------------------------------------
# Resolve for-content
# ---------------------------------------------------------------------------
_rcc_resolve_content() {
  # 1. CLAUDE_PLUGIN_ROOT (harness / test sandbox injection)
  if [[ -n "${CLAUDE_PLUGIN_ROOT:-}" ]]; then
    if [[ -d "$CLAUDE_PLUGIN_ROOT" ]]; then
      printf '%s' "$CLAUDE_PLUGIN_ROOT"
      return 0
    else
      printf 'resolve-coordinator-clone: CLAUDE_PLUGIN_ROOT is set to "%s" but it does not exist\n' "$CLAUDE_PLUGIN_ROOT" >&2
      return 1
    fi
  fi

  # 2. COORDINATOR_ROOT env var (explicit content-root override)
  if [[ -n "${COORDINATOR_ROOT:-}" ]]; then
    if [[ -d "$COORDINATOR_ROOT" ]]; then
      printf '%s' "$COORDINATOR_ROOT"
      return 0
    else
      printf 'resolve-coordinator-clone: COORDINATOR_ROOT is set to "%s" but it does not exist\n' "$COORDINATOR_ROOT" >&2
      return 1
    fi
  fi

  # 3. Registry live_path (contributor's dev-loop clone wins over cache — edits
  #    in the clone are authoritative when both a clone and a cache exist)
  local _live
  _live="$(_rcc_registry_live_path)"
  if [[ -n "$_live" ]] && [[ -d "$_live" ]]; then
    printf '%s' "$_live"
    return 0
  fi

  # 4. Versioned cache glob — newest version (fleet/CI installs)
  local _newest
  _newest="$(_rcc_newest_cache)"
  if [[ -n "$_newest" ]]; then
    printf '%s' "$_newest"
    return 0
  fi

  # 5. Flat layout: ~/.claude/plugins/coordinator-claude/coordinator
  local _claude_home
  _claude_home="$(_rcc_claude_home_dir)"
  if [[ -n "$_claude_home" ]]; then
    local _flat="${_claude_home}/plugins/coordinator-claude/coordinator"
    if [[ -d "$_flat" ]]; then
      printf '%s' "$_flat"
      return 0
    fi
  fi

  # 6. Fail-loud
  printf 'resolve-coordinator-clone --for-content: no readable coordinator content root found.\n' >&2
  printf '  Tried: CLAUDE_PLUGIN_ROOT, COORDINATOR_ROOT, registry live_path,\n' >&2
  printf '         versioned cache glob, flat ~/.claude/plugins/coordinator-claude/coordinator\n' >&2
  printf '  Run: coordinator:install OR set COORDINATOR_ROOT to the coordinator directory.\n' >&2
  return 1
}

# ---------------------------------------------------------------------------
# Standalone CLI mode: when this script is executed (not sourced), handle
# --for-git-ops / --for-content flags and print the result to stdout.
#
# Detection: if $0 resolves to this script's name (not "bash" or "-bash"),
# we are being run directly. The BASH_SOURCE[0] check is more reliable than
# testing $0 because sourcing always sets BASH_SOURCE[0] to the script path
# while $0 reflects the parent shell.
# ---------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  # Standalone mode — apply fail-loud contract
  if [[ $# -ne 1 ]]; then
    printf 'Usage: resolve-coordinator-clone.sh --for-git-ops|--for-content\n' >&2
    exit 2
  fi

  case "$1" in
    --for-git-ops)
      _rcc_resolve_git_ops
      exit $?
      ;;
    --for-content)
      _rcc_resolve_content
      exit $?
      ;;
    *)
      printf 'resolve-coordinator-clone: unknown flag "%s"\n' "$1" >&2
      printf 'Usage: resolve-coordinator-clone.sh --for-git-ops|--for-content\n' >&2
      exit 2
      ;;
  esac
else
  # Sourced mode — snapshot incoming env overrides before reset, then resolve.
  # The caller may have pre-set COORDINATOR_CLONE or COORDINATOR_ROOT as overrides
  # (mirrors how COORDINATOR_PYTHON pre-set before sourcing resolve-python.sh acts
  # as a pin). We read them here, reset both output vars, then resolve with the
  # snapshots visible inside the resolution functions via the local env.
  _rcc_incoming_clone="${COORDINATOR_CLONE:-}"
  _rcc_incoming_root="${COORDINATOR_ROOT:-}"
  _rcc_incoming_cpr="${CLAUDE_PLUGIN_ROOT:-}"
  # Reset outputs (idempotent re-source in caller scope).
  COORDINATOR_CLONE=""
  COORDINATOR_CONTENT_ROOT=""
  # Restore env overrides so the resolution functions pick them up correctly.
  # COORDINATOR_CLONE override: used by _rcc_resolve_git_ops step 1.
  if [[ -n "$_rcc_incoming_clone" ]]; then
    COORDINATOR_CLONE="$_rcc_incoming_clone"
  fi
  if [[ -n "$_rcc_incoming_root" ]]; then
    COORDINATOR_ROOT="$_rcc_incoming_root"
  fi
  if [[ -n "$_rcc_incoming_cpr" ]]; then
    CLAUDE_PLUGIN_ROOT="$_rcc_incoming_cpr"
  fi
  unset _rcc_incoming_clone _rcc_incoming_root _rcc_incoming_cpr
  # Resolve and write to the output vars.
  COORDINATOR_CLONE="$(_rcc_resolve_git_ops 2>/dev/null || true)"
  COORDINATOR_CONTENT_ROOT="$(_rcc_resolve_content 2>/dev/null || true)"
  # Review: patrik F7 — do NOT export COORDINATOR_CONTENT_ROOT. All 13 integration
  # sites source the resolver themselves and read the caller-scope var directly; none
  # rely on a child process inheriting it. Exporting into hot-path hooks (validate-commit,
  # session-init) propagates a resolver-internal location detail into every subprocess
  # those hooks spawn, masking resolution bugs in nested tooling. Set caller-scope only.
fi
