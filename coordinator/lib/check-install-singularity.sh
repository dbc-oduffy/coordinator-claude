#!/usr/bin/env bash
# check-install-singularity.sh — detect accidental coordinator install splits.
#
# PURPOSE: Enforce the canonical-install-locus invariant: the coordinator
# setup lives at ~/.claude, period. Detects accidental splits where >1
# coordinator tree, divergent settings files, a doubled venv pin, or a
# .claude-suffixed CLAUDE_HOME breaks the invariant.
#
# Exits:
#   0  — install singularity confirmed, or consented dev-loop override active
#   1  — accidental split detected (prints remediation to stderr)
#   2  — usage / internal error
#
# Spec backlink:
#   docs/plans/2026-06-26-coordinator-install-update-friction-fix-slate.md § C-R1b
#   tasks/install-friction-triage/cluster-B-path-venv-registration.md § ISSUE #4
#
# Design seam discriminator (PM-ruled 2026-06-26):
#   EXEMPT (exit 0, INFO): exactly ONE of COORDINATOR_CLONE / COORDINATOR_ROOT
#   is explicitly set AND points at a .git-backed clone. The exemption applies
#   only to the tree-count check — CLAUDE_HOME/venv/settings checks always run.
#   CLAUDE_PLUGIN_ROOT is harness-injected, NOT an operator consent signal, and
#   is NOT in the exemption set.
#
#   FAIL: accidental split — >1 distinct canonical coordinator tree (after
#   dedupe), OR two PRESENT settings files naming different coordinator-claude
#   marketplace paths, OR doubled .claude/.claude venv pin, OR .claude-suffixed
#   CLAUDE_HOME.
#
# False-FAIL guards:
#   (a) Every enumerated tree is canonicalized via "cd <dir> && pwd -P" (NOT
#       realpath — DR-148) and deduped before the >1 test. The registry
#       live_path and flat ~/.claude/plugins/coordinator-claude commonly resolve
#       to the same canonical path on a normal install (both normalize to the
#       plugin-root level after stripping a trailing /coordinator component).
#   (b) source_is_live: flat path has .git AND dedup leaves ≤1 distinct tree →
#       this is the canonical meta-repo machine; exit 0 via the count check.
#   (c) Tri-file cross-check: absent settings.local.json is concordant (not a
#       disagreement); FAIL only when two PRESENT files name different paths.
#
# Cross-platform (DR-148): no realpath, no grep -P, no sort -rV. Bash >= 4
# required for declare -A; guard is reachable on bash 3.2 (syntax parses).

# ---------------------------------------------------------------------------
# Bash version guard — declare -A requires bash >= 4.
# ---------------------------------------------------------------------------
if [[ "${BASH_VERSINFO[0]}" -lt 4 ]]; then
  printf 'ERROR: check-install-singularity.sh requires bash >= 4 (have %s).\n' "${BASH_VERSION}" >&2
  printf '  Install via: brew install bash  # macOS\n' >&2
  printf '  Or: sudo apt-get install bash   # Debian/Ubuntu\n' >&2
  exit 2
fi

# Do NOT use set -e — this script accumulates all failures before exiting so the
# operator sees every issue at once (a diagnostic tool that exits on first error
# is less useful than one that reports everything).
set -uo pipefail

# ---------------------------------------------------------------------------
# Failure accumulator
# ---------------------------------------------------------------------------
_FAIL_COUNT=0

_emit_fail() {
  local _msg="$1" _remedy="$2"
  printf 'ERROR [singularity]: %s\n' "$_msg" >&2
  printf '  Remediation: %s\n' "$_remedy" >&2
  _FAIL_COUNT=$((_FAIL_COUNT + 1))
}

_emit_info() {
  printf 'INFO [singularity]: %s\n' "$1"
}

# ---------------------------------------------------------------------------
# Helper: canonicalize a directory path via cd && pwd -P (DR-148: no realpath).
# Returns empty string if the path does not exist or is not a directory.
# ---------------------------------------------------------------------------
_canonical_dir() {
  local _d="$1"
  if [[ -d "$_d" ]]; then
    (cd "$_d" && pwd -P) 2>/dev/null || true
  fi
}

# ---------------------------------------------------------------------------
# Helper: strip a trailing /coordinator component to normalize content-root
# paths to plugin-root level. Only strips when the last path component is
# literally "coordinator" (not "coordinator-claude" or other names).
# ---------------------------------------------------------------------------
_to_plugin_root() {
  local _p="${1%/}"  # strip trailing slash
  if [[ "${_p##*/}" == "coordinator" ]]; then
    printf '%s' "${_p%/coordinator}"
  else
    printf '%s' "$_p"
  fi
}

# ---------------------------------------------------------------------------
# Helper: derive the ~/.claude base directory.
# Follows Convention A: CLAUDE_HOME is a $HOME substitute; .claude is appended.
# (The form ${CLAUDE_HOME:-$HOME/.claude} is wrong — see wiki.)
# ---------------------------------------------------------------------------
_claude_base_dir() {
  local _home="${CLAUDE_HOME:-${HOME:-${USERPROFILE:-}}}"
  if [[ -z "$_home" ]]; then
    printf '' ; return 1
  fi
  printf '%s' "${_home}/.claude"
}

# ---------------------------------------------------------------------------
# Helper: read plugin.mirrors.coordinator-claude.live_path from registry TOML.
# Returns empty string on any failure (no Python, no registry, parse error).
# ---------------------------------------------------------------------------
_registry_live_path() {
  local _reg_dir
  _reg_dir="$(_claude_base_dir 2>/dev/null)" || return 0
  local _reg="${_reg_dir}/machine-local/registry.local.toml"
  [[ -f "$_reg" ]] || return 0

  local _py=""
  for _cand in python3 python py; do
    if command -v "$_cand" >/dev/null 2>&1; then _py="$_cand"; break; fi
  done
  [[ -z "$_py" ]] && return 0

  "$_py" - "$_reg" <<'PYEOF' 2>/dev/null
import sys
from pathlib import Path

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        sys.exit(0)

reg_path = Path(sys.argv[1])
if not reg_path.exists():
    sys.exit(0)

try:
    data = tomllib.loads(reg_path.read_text(encoding="utf-8"))
except Exception:
    sys.exit(0)

# Nested-table form: [plugin.mirrors.coordinator-claude] live_path = "..."
nested = data.get("plugin", {}).get("mirrors", {}).get("coordinator-claude", {})
if isinstance(nested, dict):
    live = nested.get("live_path", "")
    if live:
        print(live)
        sys.exit(0)

# Flat dotted-key form: "plugin.mirrors.coordinator-claude.live_path" = "..."
val = data.get("plugin.mirrors.coordinator-claude.live_path", "")
if val:
    print(val)
PYEOF
}

# ---------------------------------------------------------------------------
# Helper: read coordinator.python venv pin from registry TOML.
# Returns empty string on any failure.
# ---------------------------------------------------------------------------
_registry_venv_pin() {
  local _reg_dir
  _reg_dir="$(_claude_base_dir 2>/dev/null)" || return 0
  local _reg="${_reg_dir}/machine-local/registry.local.toml"
  [[ -f "$_reg" ]] || return 0

  local _py=""
  for _cand in python3 python py; do
    if command -v "$_cand" >/dev/null 2>&1; then _py="$_cand"; break; fi
  done
  [[ -z "$_py" ]] && return 0

  "$_py" - "$_reg" <<'PYEOF' 2>/dev/null
import sys
from pathlib import Path

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        sys.exit(0)

reg_path = Path(sys.argv[1])
if not reg_path.exists():
    sys.exit(0)

try:
    data = tomllib.loads(reg_path.read_text(encoding="utf-8"))
except Exception:
    sys.exit(0)

# Nested form: [coordinator] python = "..."
coord = data.get("coordinator", {})
if isinstance(coord, dict):
    pin = coord.get("python", "")
    if pin:
        print(pin)
        sys.exit(0)

# Flat dotted-key form: "coordinator.python" = "..."
val = data.get("coordinator.python", "")
if val:
    print(val)
PYEOF
}

# ---------------------------------------------------------------------------
# Helper: read coordinator-claude marketplace path from a settings JSON file
# (settings.json or settings.local.json). Returns empty string on any failure.
# Path is at: extraKnownMarketplaces["coordinator-claude"]["source"]["path"].
# ---------------------------------------------------------------------------
_settings_coordinator_path() {
  local _file="$1"
  [[ -f "$_file" ]] || return 0

  local _py=""
  for _cand in python3 python py; do
    if command -v "$_cand" >/dev/null 2>&1; then _py="$_cand"; break; fi
  done
  [[ -z "$_py" ]] && return 0

  "$_py" - "$_file" <<'PYEOF' 2>/dev/null
import sys, json
from pathlib import Path

p = Path(sys.argv[1])
try:
    data = json.loads(p.read_text(encoding="utf-8"))
except Exception:
    sys.exit(0)

mkts = data.get("extraKnownMarketplaces", {})
entry = mkts.get("coordinator-claude", {})
if not isinstance(entry, dict):
    sys.exit(0)
src = entry.get("source", {})
if not isinstance(src, dict):
    sys.exit(0)
path = src.get("path", "")
if path:
    print(path)
PYEOF
}

# ---------------------------------------------------------------------------
# Helper: read coordinator-claude marketplace path from known_marketplaces.json.
# Path is at: ["coordinator-claude"]["source"]["path"].
# Returns empty string on any failure.
# ---------------------------------------------------------------------------
_known_marketplaces_coordinator_path() {
  local _file="$1"
  [[ -f "$_file" ]] || return 0

  local _py=""
  for _cand in python3 python py; do
    if command -v "$_cand" >/dev/null 2>&1; then _py="$_cand"; break; fi
  done
  [[ -z "$_py" ]] && return 0

  "$_py" - "$_file" <<'PYEOF' 2>/dev/null
import sys, json
from pathlib import Path

p = Path(sys.argv[1])
try:
    data = json.loads(p.read_text(encoding="utf-8"))
except Exception:
    sys.exit(0)

# known_marketplaces.json top-level keys are marketplace names.
entry = data.get("coordinator-claude", {})
if not isinstance(entry, dict):
    sys.exit(0)
src = entry.get("source", {})
if not isinstance(src, dict):
    sys.exit(0)
path = src.get("path", "")
if path:
    print(path)
PYEOF
}

# ===========================================================================
# MAIN CHECKS
# ===========================================================================

_claude_base="$(_claude_base_dir 2>/dev/null)" || _claude_base=""

# ---------------------------------------------------------------------------
# CHECK 1 — CLAUDE_HOME suffix guard
# A .claude-suffixed CLAUDE_HOME means the operator has set CLAUDE_HOME to the
# .claude dir itself (Convention B). Convention A requires CLAUDE_HOME to be
# the *parent* (a $HOME substitute). The doubled-venv bug (issue #3) is a
# direct consequence of this mismatch.
# ---------------------------------------------------------------------------
if [[ -n "${CLAUDE_HOME:-}" ]]; then
  case "$CLAUDE_HOME" in
    */.claude|*/.claude/)
      _emit_fail \
        "CLAUDE_HOME is set to a .claude-suffixed path: ${CLAUDE_HOME}" \
        "CLAUDE_HOME must be a \$HOME substitute (the parent directory), not the .claude dir. Unset CLAUDE_HOME, or set it to its parent (e.g. export CLAUDE_HOME=\$HOME)."
      ;;
  esac
fi

# ---------------------------------------------------------------------------
# CHECK 2 — Venv pin doubled-path guard
# coordinator.python in the registry should never contain /.claude/.claude/
# which is the symptom of a Convention-B CLAUDE_HOME in effect when the venv
# was built.
# ---------------------------------------------------------------------------
_venv_pin=""
if [[ -n "$_claude_base" ]]; then
  _venv_pin="$(_registry_venv_pin 2>/dev/null)" || _venv_pin=""
fi
if [[ -n "$_venv_pin" ]]; then
  case "$_venv_pin" in
    */.claude/.claude/*)
      _emit_fail \
        "Venv pin contains doubled .claude path: ${_venv_pin}" \
        "Fix CLAUDE_HOME (must be the parent dir, e.g. \$HOME), then re-run ensure-coordinator-venv.sh to reset the coordinator.python registry pin."
      ;;
  esac
fi

# ---------------------------------------------------------------------------
# CHECK 3 — Exemption check (consented dev-loop override)
# Exactly ONE of COORDINATOR_CLONE / COORDINATOR_ROOT explicitly set AND
# pointing at a .git-backed clone → consented contributor override; emit INFO
# and skip the tree-count check (only that check). All other checks still run.
# CLAUDE_PLUGIN_ROOT is harness-injected and is NOT in the exemption set.
#
# "Explicitly set" means the variable is non-empty in the current environment.
# Both COORDINATOR_CLONE and COORDINATOR_ROOT being set simultaneously (or
# neither) is NOT exempt — the operator may have an accidental environment.
# ---------------------------------------------------------------------------
_exempt_tree_check=0
_exempt_reason=""

_clone_set=0; _root_set=0
[[ -n "${COORDINATOR_CLONE:-}" ]] && _clone_set=1
[[ -n "${COORDINATOR_ROOT:-}" ]] && _root_set=1

if [[ $((_clone_set + _root_set)) -eq 1 ]]; then
  if [[ "$_clone_set" -eq 1 ]]; then
    # COORDINATOR_CLONE must have a .git directory directly (it IS the repo root)
    if [[ -d "${COORDINATOR_CLONE}/.git" ]]; then
      _exempt_tree_check=1
      _exempt_reason="COORDINATOR_CLONE dev-loop override active -> ${COORDINATOR_CLONE} (consented)"
    fi
  else
    # COORDINATOR_ROOT is a content root; its plugin root (parent if basename=coordinator)
    # must have a .git directory for the exemption to apply.
    _cr_plugin_root="$(_to_plugin_root "${COORDINATOR_ROOT}")"
    if [[ -d "${_cr_plugin_root}/.git" ]]; then
      _exempt_tree_check=1
      _exempt_reason="COORDINATOR_ROOT dev-loop override active -> ${COORDINATOR_ROOT} (consented)"
    fi
  fi
fi

# ---------------------------------------------------------------------------
# CHECK 4 — Coordinator tree enumeration + canonical dedupe
# Enumerate all paths where the resolver could find a coordinator plugin.
# Normalize each to plugin-root level (strip trailing /coordinator component),
# canonicalize via cd && pwd -P, then dedupe. If >1 distinct canonical path
# remains after dedupe, the install is split.
#
# Paths enumerated:
#   - Flat installed path: ~/.claude/plugins/coordinator-claude
#   - Registry live_path (strip /coordinator to get plugin root)
#   - COORDINATOR_CLONE (already at plugin-root level — has the .git)
#   - COORDINATOR_ROOT (strip /coordinator if content-subdir shape)
#   - CLAUDE_PLUGIN_ROOT (harness-injected; strip /coordinator; NOT exempt)
# ---------------------------------------------------------------------------
declare -A _seen_trees=()
_tree_count=0

_add_tree() {
  local _raw="$1"
  [[ -z "$_raw" ]] && return 0
  local _norm
  _norm="$(_to_plugin_root "$_raw")"
  [[ -z "$_norm" ]] && return 0
  [[ -d "$_norm" ]] || return 0
  local _canon
  _canon="$(_canonical_dir "$_norm")" || return 0
  [[ -z "$_canon" ]] && return 0
  if [[ -z "${_seen_trees["$_canon"]+x}" ]]; then
    _seen_trees["$_canon"]=1
    _tree_count=$((_tree_count + 1))
  fi
}

# Flat installed path
if [[ -n "$_claude_base" ]]; then
  _add_tree "${_claude_base}/plugins/coordinator-claude"
fi

# Registry live_path (content root; strip /coordinator to get plugin root)
_live_path=""
if [[ -n "$_claude_base" ]]; then
  _live_path="$(_registry_live_path 2>/dev/null)" || _live_path=""
fi
if [[ -n "$_live_path" ]]; then
  _add_tree "$_live_path"
fi

# COORDINATOR_CLONE (git repo root = plugin root level)
if [[ -n "${COORDINATOR_CLONE:-}" ]]; then
  _add_tree "${COORDINATOR_CLONE}"
fi

# COORDINATOR_ROOT (content root; strip /coordinator if applicable)
if [[ -n "${COORDINATOR_ROOT:-}" ]]; then
  _add_tree "${COORDINATOR_ROOT}"
fi

# CLAUDE_PLUGIN_ROOT (harness-injected content root; NOT exempt from count)
if [[ -n "${CLAUDE_PLUGIN_ROOT:-}" ]]; then
  _add_tree "${CLAUDE_PLUGIN_ROOT}"
fi

# Apply the >1 test (skip only if consented override is active)
if [[ "$_exempt_tree_check" -eq 1 ]]; then
  _emit_info "$_exempt_reason"
elif [[ "$_tree_count" -gt 1 ]]; then
  _emit_fail \
    "Multiple coordinator trees detected (${_tree_count} distinct canonical paths)." \
    "Consolidate to a single coordinator install at \${CLAUDE_HOME:-\$HOME}/.claude/plugins/coordinator-claude. Unset COORDINATOR_CLONE/COORDINATOR_ROOT/CLAUDE_PLUGIN_ROOT, and remove or unregister extra clones."
  printf '  Trees found:\n' >&2
  for _tp in "${!_seen_trees[@]}"; do
    printf '    %s\n' "$_tp" >&2
  done
fi

# ---------------------------------------------------------------------------
# CHECK 5 — Settings tri-file cross-check
# Compare the coordinator-claude marketplace path across three settings files.
# Absent settings.local.json → concordant (not a disagreement).
# FAIL only when two PRESENT files name different coordinator-claude paths
# (after canonical dedupe when the directories exist on disk).
# ---------------------------------------------------------------------------
if [[ -n "$_claude_base" ]]; then
  _settings_json="${_claude_base}/settings.json"
  _settings_local="${_claude_base}/settings.local.json"
  _known_mkts="${_claude_base}/plugins/known_marketplaces.json"

  _p_settings=""
  _p_local=""
  _p_known=""

  [[ -f "$_settings_json" ]] && _p_settings="$(_settings_coordinator_path "$_settings_json" 2>/dev/null)" || true
  # Guard: only read settings.local.json if it exists (absent → concordant per false-FAIL guard c)
  [[ -f "$_settings_local" ]] && _p_local="$(_settings_coordinator_path "$_settings_local" 2>/dev/null)" || true
  [[ -f "$_known_mkts" ]] && _p_known="$(_known_marketplaces_coordinator_path "$_known_mkts" 2>/dev/null)" || true

  # Collect non-empty paths and dedupe (canonicalize when dir exists)
  declare -A _mkt_seen=()
  _mkt_count=0

  _add_mkt_path() {
    local _raw="$1"
    [[ -z "$_raw" ]] && return 0
    local _canon
    if [[ -d "$_raw" ]]; then
      _canon="$(_canonical_dir "$_raw")" || _canon="$_raw"
    else
      _canon="$_raw"
    fi
    [[ -z "$_canon" ]] && return 0
    if [[ -z "${_mkt_seen["$_canon"]+x}" ]]; then
      _mkt_seen["$_canon"]=1
      _mkt_count=$((_mkt_count + 1))
    fi
  }

  _add_mkt_path "$_p_settings"
  _add_mkt_path "$_p_local"
  _add_mkt_path "$_p_known"

  if [[ "$_mkt_count" -gt 1 ]]; then
    _emit_fail \
      "Settings files disagree on the coordinator-claude marketplace path (${_mkt_count} distinct paths found)." \
      "Re-run platform-localize.sh (fires on SessionStart) so all present settings files agree on \${CLAUDE_HOME:-\$HOME}/.claude/plugins/coordinator-claude."
    [[ -n "$_p_settings" ]] && printf '  settings.json:            %s\n' "$_p_settings" >&2
    [[ -n "$_p_local" ]]    && printf '  settings.local.json:      %s\n' "$_p_local" >&2
    [[ -n "$_p_known" ]]    && printf '  known_marketplaces.json:  %s\n' "$_p_known" >&2
  fi
fi

# ---------------------------------------------------------------------------
# Final verdict
# ---------------------------------------------------------------------------
if [[ "$_FAIL_COUNT" -eq 0 ]]; then
  _emit_info "coordinator install singularity OK — single canonical location confirmed."
  exit 0
else
  exit 1
fi
