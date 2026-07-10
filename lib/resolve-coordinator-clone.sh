#!/usr/bin/env bash
# resolve-coordinator-clone.sh — unified coordinator install-root resolver.
#
# Two verbs (select via --clone-root or --content-root; --for-git-ops and
# --for-content are RETAINED LEGACY ALIASES — identical behavior, same
# resolution functions, kept for the live cross-repo contract, see "Public
# contract surface" below). This is the single shared lib absorbing the
# previously-independent rung ladders of coordinator-doe-root.sh, claude-doe,
# and gen-doe-root-pointer.sh (those callers are recast to thin wrappers over
# --clone-root in a companion chunk; the percolate-root resolver
# (coordinator-percolate-runtime-root.sh) is NOT folded — ratified SIBLING,
# zero rung overlap, zero shared guard copies — see
# state/roadmap/v3split/COORDINATOR-RESOLUTIONS.md Resolution 4).
# Spec backlink: docs/plans/2026-07-09-resolver-unification-v3split-01.md § C2
#
#   --clone-root (alias: --for-git-ops)
#                   The .git-backed clone directory. Required for operations
#                   that must address the git history (drift probe, git log,
#                   refresh-plugin-live-install.sh). Fails loud if no clone
#                   with a .git directory can be located.
#
#   --content-root (alias: --for-content)
#                   Highest-precedence readable payload directory. Preferred
#                   for loading libs, agents, snippets, query-records.js, etc.
#                   A contributor's live dev-loop clone wins over any cache so
#                   in-progress edits stay authoritative; the versioned cache is
#                   the fallback for fleet/CI installs.
#
# Precedence:
#
#   NOTE — MODE DIVERGENCE UNDER MAXIMALIST INSTALL:
#   In the maximalist install shape (coordinator source lives in the DoE repo,
#   delivered via `claude --plugin-dir <DoE>/coordinator`), the two resolver
#   modes return DIFFERENT directories from the pointer tier:
#     --content-root → <DoE>/coordinator  (the plugin payload dir)
#     --clone-root   → <DoE>              (the DoE repo root, which holds .git)
#   This divergence is new; in the old flat-clone model both modes returned the
#   same dir. NOTE: the flat marketplace tree is UN-NESTED —
#   ~/.claude/plugins/coordinator-claude IS the plugin root (the manifest lives
#   at coordinator/.claude-plugin/plugin.json, so a flat marketplace install of
#   that plugin lands its contents directly under coordinator-claude/, with no
#   /coordinator subdir). Under maximalist,
#   coordinator/.git is ABSENT — only <DoE>/.git exists — so returning
#   <DoE>/coordinator for --clone-root would fail the .git check and fall through
#   to fail-loud. The pointer tier must return the DoE root for clone-root.
#
#   --clone-root (alias: --for-git-ops):
#     1. COORDINATOR_CLONE env var (non-empty, must have .git/)
#     2. registry — canonical-then-fallback order (plan C6/AC9, registry-namespace
#        collision resolution): repos.doe_claude (canonical, machine-local get)
#        first, then plugin.mirrors.coordinator-claude.live_path (fallback,
#        read-mirrors.sh technique) if repos.doe_claude is unset. Both keys
#        describe the same fact (the DoE-claude clone path); a machine that
#        only set one of the two still resolves. See _rcc_registry_doe_claude
#        and _rcc_registry_live_path below.
#     3. Pointer file ~/.claude/.doe-root → DoE repo root (the dir that holds
#        .git/ under maximalist). Read via cat — zero tool dependency, cold-safe.
#        Gated on -d <root>/.git. Returns <root> itself (NOT <root>/coordinator).
#        Placed below registry so env/registry overrides win; above flat so this
#        tier survives flat-tree removal. REUSES
#        coordinator_read_doe_root_pointer() from read-doe-root-pointer.sh — the
#        shared primitive, not reimplemented per-caller.
#     4. Flat layout: ~/.claude/plugins/coordinator-claude (un-nested) — IF it
#        has a .git/ (i.e. this is a live source_is_live install)
#     5. FAIL-LOUD — no git-backed clone found
#
#   These are the shared OSS-fallback rungs (3-4 above): previously only
#   resolve-coordinator-clone.sh had them; --clone-root is the ONE place they
#   are implemented, so coordinator-doe-root.sh's and claude-doe's callers
#   inherit them by delegating to this verb rather than reimplementing (AC8).
#
#   --content-root (alias: --for-content):
#     1. CLAUDE_PLUGIN_ROOT env var (set by harness/install scripts, wins over
#        all so harness-injected override and test sandboxes work cleanly)
#     2. COORDINATOR_ROOT env var (explicit content-root override)
#     3. registry plugin.mirrors.coordinator-claude.live_path (clone is
#        authoritative — dev-loop edits are live in the clone)
#     4. Versioned cache: newest dir under
#        ~/.claude/plugins/cache/coordinator-claude/coordinator/*/
#        (DR-148-safe: bash semver-compare loop, no sort -rV/realpath/grep -P)
#     5. Pointer file ~/.claude/.doe-root → <root>/coordinator. Read via cat —
#        zero tool dependency, cold-safe. Gated on -d <root>/coordinator.
#        Returns <root>/coordinator (NOT <root>). See mode-divergence note above.
#        Placed below versioned cache so cache installs still win; above flat so
#        this tier survives flat-tree removal.
#     6. Flat layout: ~/.claude/plugins/coordinator-claude (un-nested)
#     7. FAIL-LOUD — no readable content root found
#
#   NOT .git-gated (rung 6 uses the .claude-plugin/plugin.json manifest marker
#   instead) — deliberately different from --clone-root's .git gate on its own
#   flat-layout rung.
#
#   No --percolate-root arm on this lib. coordinator-percolate-runtime-root.sh
#   remains a standalone sibling (the Director of Engineering-ratified SIBLING ruling, Resolution 4,
#   state/roadmap/v3split/COORDINATOR-RESOLUTIONS.md) — zero rung overlap with
#   either verb above, zero shared guard copies; its sole caller keeps sourcing
#   it directly, untouched by this file.
#
# When sourced (no arguments), sets two variables in the CALLER's scope only
# (not exported to child processes — callers that need child inheritance must
# export explicitly; the 13 integration sites all read the caller-scope var):
#   COORDINATOR_CLONE        — the clone-root resolved path (empty if none,
#                              but see NOTE below — sourcing does NOT fail-loud)
#   COORDINATOR_CONTENT_ROOT — the content-root resolved path (empty if none)
#
# When run as a standalone CLI (--clone-root|--content-root, or the legacy
# aliases --for-git-ops|--for-content), prints the resolved path to stdout and
# exits non-zero on resolution failure.
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
# Peer repos (project-rag, ue-addon, example-game-repo) bind here instead of each
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
# Source the settings-home seam (C1) for machine-local dir resolution.
# Non-fatal if absent (cold bootstrap before settings-home.sh is installed).
# Spec backlink: docs/plans/2026-07-06-durable-substrate-to-settings-home.md § C2b
# ---------------------------------------------------------------------------
_RCC_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_RCC_SETTINGS_HOME_LIB="${_RCC_LIB_DIR}/settings-home.sh"
if [[ -f "$_RCC_SETTINGS_HOME_LIB" ]]; then
    # shellcheck source=./settings-home.sh
    source "$_RCC_SETTINGS_HOME_LIB"
fi
unset _RCC_SETTINGS_HOME_LIB _RCC_LIB_DIR

# ---------------------------------------------------------------------------
# Helper: derive the machine-local registry path.
# Rung-1: claude-home machine-local (seam-delegating when available on PATH).
# Rung-2 fallback: settings-home seam (C1) — machine-local has moved out of
# ~/.claude; NEVER hardcode ${…}/.claude/machine-local.
# ---------------------------------------------------------------------------
_rcc_registry_path() {
  local _reg=""
  if command -v claude-home >/dev/null 2>&1; then
    _reg="$(claude-home machine-local 2>/dev/null)/registry.local.toml"
  else
    # Rung-2: resolve via the settings-home seam (C1).
    # machine-local dir is <settings-home>/machine-local — no longer under ~/.claude.
    if declare -f _coordinator_settings_home >/dev/null 2>&1; then
      _reg="$(_coordinator_settings_home)/machine-local/registry.local.toml"
    else
      # Seam unavailable (cold bootstrap before settings-home.sh is installed).
      # Derive from env using the same convention as _coordinator_settings_home().
      local _home="${CLAUDE_HOME:-${HOME:-${USERPROFILE:-}}}"
      if [[ -z "$_home" ]]; then
        return 1
      fi
      _reg="${_home}/.coordinator-claude-settings/machine-local/registry.local.toml"
    fi
  fi
  printf '%s' "$_reg"
}

# ---------------------------------------------------------------------------
# Helper: read repos.doe_claude via `machine-local get` — the CANONICAL
# registry key for the DoE-claude clone path (general [repos] family:
# repos.project_rag, repos.example_orchestration_hub_repo, ...). Returns empty when
# machine-local is unavailable or the key is unset.
#
# Registry-namespace collision resolution (plan C6/AC9,
# docs/plans/2026-07-09-resolver-unification-v3split-01.md § C6): two
# registry keys describe the SAME fact (the DoE-claude clone path) —
# repos.doe_claude (this helper) and plugin.mirrors.coordinator-claude.live_path
# (_rcc_registry_live_path, below). This is a non-destructive READ-ORDER fix,
# not a schema restructure: repos.doe_claude is read FIRST (canonical), and
# plugin.mirrors.coordinator-claude.live_path is the FALLBACK read when
# repos.doe_claude is unset. Both keys keep resolving exactly as before when
# only one is set on a given machine.
# ---------------------------------------------------------------------------
_rcc_registry_doe_claude() {
  command -v machine-local >/dev/null 2>&1 || return 0
  machine-local get repos.doe_claude 2>/dev/null
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
#
# FALLBACK rung in the repos.doe_claude / plugin.mirrors.*.live_path
# registry-namespace collision (plan C6/AC9, see _rcc_registry_doe_claude
# above for the canonical rung and the collision-resolution record).
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
# Helper: read the DoE repo root from the cold-readable pointer file.
#
# Extracted to lib/read-doe-root-pointer.sh (shared substrate, not owned by
# this file) — sourced below as coordinator_read_doe_root_pointer().
# ---------------------------------------------------------------------------
source "${BASH_SOURCE[0]%/*}/read-doe-root-pointer.sh"

# ---------------------------------------------------------------------------
# Helper: find newest versioned cache dir (DR-148-safe, semver-aware).
# Pattern: ~/.claude/plugins/cache/coordinator-claude/coordinator/*/
# Uses a bash loop splitting each basename on '.' and comparing numerically
# — no sort -rV (GNU-only), no realpath, no grep -P. Correctly resolves
# 2.10.0 > 2.9.0 (lex sort would invert this). DR-148 compliant: bash 3.2,
# BSD coreutils.
# Review: the Staff Engineer — lexicographic sort -r inverts 2.9.0/2.10.0; replace with
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
# Rung-0 selector: dev-vs-OSS source-mode decision, shared by both verbs.
#
# Single insertion point for the dev-vs-OSS decision (coordinator/CLAUDE.md
# § Build For Someone Else's Machine: explicit flag → marker auto-discovery →
# hard error). Returns the DECISION only (dev|oss|passthrough) on stdout;
# each verb keeps its own mode-appropriate rung bodies (git-ops gates oss on
# .git, content gates oss on .claude-plugin/plugin.json) — those bodies are
# NOT duplication and must not be collapsed into one shared oss-resolution
# body (mode-divergence invariant, see file header NOTE above).
#
# Args: $1 = verb, "git-ops" or "content".
# Stdout: exactly one of "dev" | "oss" | "passthrough" on success.
# Returns: 0 on success: 1 with a fail-loud message on stderr on failure.
#
# Decision order:
#   1. PASSTHROUGH — existing public env overrides win unconditionally, so
#      the append-only contract 3 peer repos bind to (AC9) is preserved:
#      COORDINATOR_CLONE (git-ops) or CLAUDE_PLUGIN_ROOT (or) COORDINATOR_ROOT
#      (content — either one alone triggers passthrough) pinned →
#      passthrough, regardless of COORDINATOR_SOURCE_MODE.
#      Review: code-reviewer F4 — slash notation read ambiguously as AND;
#      the semantic is OR (either var alone triggers passthrough).
#   2. EXPLICIT COORDINATOR_SOURCE_MODE (only reached if no passthrough pin
#      applied) — dev|oss select directly; any other non-empty value fails
#      loud.
#   3. MARKER AUTO-DISCOVERY (env unset, no passthrough) — dev marker
#      (<candidate-clone>/.coordinator-dev-repo, written by C2) present ⇒
#      dev unconditionally (authoritative dev declaration; a co-existing OSS
#      install is NOT ambiguous). Marker absent + OSS install present on an
#      otherwise-resolvable candidate clone ⇒ fail-loud ambiguity (names both
#      paths + the override). OSS install present (non-ambiguous case) ⇒
#      oss. Marker absent + candidate resolved + NO OSS present ⇒ dev
#      (unmarked-but-sole-candidate; non-ambiguous by construction since
#      there is no OSS to disambiguate against — Review: code-reviewer F1).
#      Neither a candidate nor OSS resolves ⇒ fail-loud no-source.
# Spec backlink: docs/plans/2026-07-09-dev-vs-oss-selector-v3split-06.md § C1
# ---------------------------------------------------------------------------
_rcc_resolve_source_mode() {
  local _verb="$1"

  # 1. PASSTHROUGH tier — existing public env overrides win unconditionally.
  case "$_verb" in
    git-ops)
      if [[ -n "${COORDINATOR_CLONE:-}" ]]; then
        printf 'passthrough'
        return 0
      fi
      ;;
    content)
      if [[ -n "${CLAUDE_PLUGIN_ROOT:-}" ]] || [[ -n "${COORDINATOR_ROOT:-}" ]]; then
        printf 'passthrough'
        return 0
      fi
      ;;
    *)
      # Review: code-reviewer F5 — defense-in-depth default arm. Both current
      # call sites pass a hardcoded literal (unreachable today), but a future
      # typo'd verb must fail loud, not silently skip passthrough and fall
      # to tier 2 (the "detect-then-silently-pick" antipattern this
      # function's docstring explicitly disclaims).
      printf 'resolve-coordinator-clone: internal error — unknown verb "%s"\n' "$_verb" >&2
      return 1
      ;;
  esac

  # 2. Explicit COORDINATOR_SOURCE_MODE override (no passthrough pin applied).
  if [[ -n "${COORDINATOR_SOURCE_MODE:-}" ]]; then
    case "$COORDINATOR_SOURCE_MODE" in
      dev)
        printf 'dev'
        return 0
        ;;
      oss)
        printf 'oss'
        return 0
        ;;
      *)
        printf 'resolve-coordinator-clone: COORDINATOR_SOURCE_MODE is set to "%s" but must be "dev" or "oss"\n' "$COORDINATOR_SOURCE_MODE" >&2
        return 1
        ;;
    esac
  fi

  # 3. Marker auto-discovery.
  # Review: code-reviewer F3 — candidate probe must consult the CANONICAL
  # registry key (_rcc_registry_doe_claude) before the FALLBACK key
  # (_rcc_registry_live_path), matching _rcc_resolve_git_ops's own rung
  # precedence (.doe-root pointer → canonical registry → fallback registry).
  # Without this, a machine that set ONLY repos.doe_claude (no .doe-root
  # pointer, no plugin.mirrors.*.live_path) would wrongly resolve no
  # candidate at rung-0 even though the git-ops ladder below can.
  local _candidate=""
  _candidate="$(coordinator_read_doe_root_pointer)"
  if [[ -z "$_candidate" ]]; then
    _candidate="$(_rcc_registry_doe_claude)"
  fi
  if [[ -z "$_candidate" ]]; then
    _candidate="$(_rcc_registry_live_path)"
  fi
  local _candidate_resolved=0
  if [[ -n "$_candidate" ]] && [[ -d "$_candidate" ]]; then
    _candidate_resolved=1
  fi

  local _dev_marker_present=0
  if [[ "$_candidate_resolved" -eq 1 ]] && [[ -f "${_candidate}/.coordinator-dev-repo" ]]; then
    _dev_marker_present=1
  fi

  local _claude_home
  _claude_home="$(_rcc_claude_home_dir)"
  local _oss_present=0
  if [[ -n "$_claude_home" ]] && [[ -f "${_claude_home}/plugins/coordinator-claude/.claude-plugin/plugin.json" ]]; then
    _oss_present=1
  fi

  if [[ "$_dev_marker_present" -eq 1 ]]; then
    printf 'dev'
    return 0
  fi

  if [[ "$_candidate_resolved" -eq 1 ]] && [[ "$_oss_present" -eq 1 ]]; then
    printf 'resolve-coordinator-clone: ambiguous coordinator source — an unmarked candidate clone was found at "%s" (no .coordinator-dev-repo marker) AND an OSS install was found at "%s".\n' \
      "$_candidate" "${_claude_home}/plugins/coordinator-claude" >&2
    printf '  Set COORDINATOR_SOURCE_MODE=dev or COORDINATOR_SOURCE_MODE=oss to disambiguate.\n' >&2
    return 1
  fi

  if [[ "$_oss_present" -eq 1 ]]; then
    printf 'oss'
    return 0
  fi

  # Review: code-reviewer F1 — unmarked-but-sole-candidate ⇒ dev, not
  # fail-loud. A resolvable candidate clone with no .coordinator-dev-repo
  # marker and no co-present OSS install has nothing to disambiguate against
  # (oss_present is already known 0 here) — the only source that resolves at
  # all IS the candidate clone. Falling through to "no source found" would be
  # actively misleading (a source WAS found, just unmarked) — this is the
  # first-bootstrap shape before .coordinator-dev-repo lands, or any machine
  # where the marker was accidentally not copied.
  if [[ "$_candidate_resolved" -eq 1 ]]; then
    printf 'dev'
    return 0
  fi

  printf 'resolve-coordinator-clone: no coordinator source found (no dev marker, no OSS install); set COORDINATOR_SOURCE_MODE or run coordinator:install.\n' >&2
  return 1
}

# ---------------------------------------------------------------------------
# Resolve clone-root (legacy name: for-git-ops)
# ---------------------------------------------------------------------------
_rcc_resolve_git_ops() {
  local _rcc_mode
  _rcc_mode="$(_rcc_resolve_source_mode git-ops)" || return 1

  if [[ "$_rcc_mode" == "oss" ]]; then
    # OSS mode: the ONLY OSS target for git-ops is the flat marketplace clone
    # IF it has .git. A marketplace byte-copy has no .git, so on a byte-copy
    # consumer git-ops oss legitimately finds nothing and MUST fail loud —
    # do NOT fall through to the dev rungs below.
    local _claude_home
    _claude_home="$(_rcc_claude_home_dir)"
    if [[ -n "$_claude_home" ]]; then
      local _flat="${_claude_home}/plugins/coordinator-claude"
      if [[ -d "${_flat}/.git" ]]; then
        printf '%s' "$_flat"
        return 0
      fi
    fi
    printf 'resolve-coordinator-clone --for-git-ops: OSS mode selected but no git-backed OSS clone found (a marketplace byte-copy install has no .git).\n' >&2
    printf '  Run: coordinator:install OR set COORDINATOR_CLONE to a git-backed clone path.\n' >&2
    return 1
  fi

  # mode is "dev" or "passthrough" — run the existing ladder unchanged.

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

  # 2. Registry — canonical-then-fallback order (plan C6/AC9): repos.doe_claude
  #    first (canonical, general [repos] registry family), then
  #    plugin.mirrors.coordinator-claude.live_path (fallback, coordinator-specific
  #    duplicate). A machine that only set one of the two still resolves.
  local _live
  _live="$(_rcc_registry_doe_claude)"
  if [[ -z "$_live" ]]; then
    _live="$(_rcc_registry_live_path)"
  fi
  if [[ -n "$_live" ]]; then
    if [[ -d "${_live}/.git" ]]; then
      printf '%s' "$_live"
      return 0
    fi
    # Registry entry present but no .git — not a git-backed clone; fall through
  fi

  # 3. Pointer file: ~/.claude/.doe-root → DoE repo root.
  #    Under maximalist install the DoE repo root holds .git (not <root>/coordinator).
  #    Returns <root> itself so callers that need git history address the right dir.
  local _doe_root
  _doe_root="$(coordinator_read_doe_root_pointer)"
  if [[ -n "$_doe_root" ]] && [[ -d "${_doe_root}/.git" ]]; then
    printf '%s' "$_doe_root"
    return 0
  fi

  # 4. Flat layout: ~/.claude/plugins/coordinator-claude with .git (un-nested —
  #    the flat marketplace plugin root has no /coordinator subdir; see header)
  local _claude_home
  _claude_home="$(_rcc_claude_home_dir)"
  if [[ -n "$_claude_home" ]]; then
    local _flat="${_claude_home}/plugins/coordinator-claude"
    if [[ -d "${_flat}/.git" ]]; then
      printf '%s' "$_flat"
      return 0
    fi
  fi

  # 5. Fail-loud
  printf 'resolve-coordinator-clone --for-git-ops: no git-backed coordinator clone found.\n' >&2
  printf '  Tried: COORDINATOR_CLONE env, registry repos.doe_claude (canonical),\n' >&2
  printf '         registry plugin.mirrors.coordinator-claude.live_path (fallback),\n' >&2
  printf '         ~/.claude/.doe-root pointer, flat ~/.claude/plugins/coordinator-claude\n' >&2
  printf '  (no .git in any tried location)\n' >&2
  printf '  Run: coordinator:install OR set COORDINATOR_CLONE to the clone path.\n' >&2
  return 1
}

# ---------------------------------------------------------------------------
# Resolve content-root (legacy name: for-content)
# ---------------------------------------------------------------------------
_rcc_resolve_content() {
  local _rcc_mode
  _rcc_mode="$(_rcc_resolve_source_mode content)" || return 1

  if [[ "$_rcc_mode" == "oss" ]]; then
    # OSS mode: resolve ONLY the versioned-cache rung then the flat manifest
    # rung — fail loud if neither exists. Do NOT fall through to the dev
    # rungs below (registry live_path, .doe-root pointer).
    local _newest
    _newest="$(_rcc_newest_cache)"
    if [[ -n "$_newest" ]]; then
      printf '%s' "$_newest"
      return 0
    fi

    local _claude_home
    _claude_home="$(_rcc_claude_home_dir)"
    if [[ -n "$_claude_home" ]]; then
      local _flat="${_claude_home}/plugins/coordinator-claude"
      if [[ -f "${_flat}/.claude-plugin/plugin.json" ]]; then
        printf '%s' "$_flat"
        return 0
      fi
    fi

    printf 'resolve-coordinator-clone --for-content: OSS mode selected but no readable OSS content root found (tried versioned cache, flat marketplace manifest).\n' >&2
    printf '  Run: coordinator:install OR set COORDINATOR_ROOT to the coordinator directory.\n' >&2
    return 1
  fi

  # mode is "dev" or "passthrough" — run the existing ladder unchanged.

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

  # 5. Pointer file: ~/.claude/.doe-root → <root>/coordinator.
  #    Under maximalist install, coordinator source lives at <DoE>/coordinator
  #    (not at <DoE> itself — mode diverges from --for-git-ops here).
  #    Returns <root>/coordinator, gated on -d <root>/coordinator.
  local _doe_root
  _doe_root="$(coordinator_read_doe_root_pointer)"
  if [[ -n "$_doe_root" ]] && [[ -d "${_doe_root}/coordinator" ]]; then
    printf '%s' "${_doe_root}/coordinator"
    return 0
  fi

  # 6. Flat layout: ~/.claude/plugins/coordinator-claude (un-nested — the flat
  #    marketplace plugin root has no /coordinator subdir; see header)
  #    Gated on the manifest marker AT THE UN-NESTED PATH
  #    (${_flat}/.claude-plugin/plugin.json — no /coordinator segment, since
  #    a marketplace copy lands the DoE repo's coordinator/ CONTENTS directly
  #    under $_flat, not a coordinator/ subdir of it), mirroring the git-ops
  #    rung's -d "${_flat}/.git" gate — a bare -d check on $_flat alone would
  #    false-positive on a stale/partial marketplace dir that isn't actually
  #    a coordinator content root.
  #    Review: code-reviewer — flat rung had no content-validation beyond
  #    directory existence, widening false-positive surface post-un-nesting.
  local _claude_home
  _claude_home="$(_rcc_claude_home_dir)"
  if [[ -n "$_claude_home" ]]; then
    local _flat="${_claude_home}/plugins/coordinator-claude"
    if [[ -f "${_flat}/.claude-plugin/plugin.json" ]]; then
      printf '%s' "$_flat"
      return 0
    fi
  fi

  # 7. Fail-loud
  printf 'resolve-coordinator-clone --for-content: no readable coordinator content root found.\n' >&2
  printf '  Tried: CLAUDE_PLUGIN_ROOT, COORDINATOR_ROOT, registry live_path,\n' >&2
  printf '         versioned cache glob, ~/.claude/.doe-root pointer,\n' >&2
  printf '         flat ~/.claude/plugins/coordinator-claude\n' >&2
  printf '  Run: coordinator:install OR set COORDINATOR_ROOT to the coordinator directory.\n' >&2
  return 1
}

# ---------------------------------------------------------------------------
# Standalone CLI mode: when this script is executed (not sourced), handle
# --clone-root / --content-root flags (plus the legacy --for-git-ops /
# --for-content aliases — same behavior, retained for the live cross-repo
# contract with project-rag / project-rag-ue-addon / example-game-workbench-repo)
# and print the result to stdout.
#
# Detection: if $0 resolves to this script's name (not "bash" or "-bash"),
# we are being run directly. The BASH_SOURCE[0] check is more reliable than
# testing $0 because sourcing always sets BASH_SOURCE[0] to the script path
# while $0 reflects the parent shell.
# ---------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  # Standalone mode — apply fail-loud contract
  if [[ $# -ne 1 ]]; then
    printf 'Usage: resolve-coordinator-clone.sh --clone-root|--content-root (aliases: --for-git-ops|--for-content)\n' >&2
    exit 2
  fi

  case "$1" in
    --clone-root|--for-git-ops)
      _rcc_resolve_git_ops
      exit $?
      ;;
    --content-root|--for-content)
      _rcc_resolve_content
      exit $?
      ;;
    *)
      printf 'resolve-coordinator-clone: unknown flag "%s"\n' "$1" >&2
      printf 'Usage: resolve-coordinator-clone.sh --clone-root|--content-root (aliases: --for-git-ops|--for-content)\n' >&2
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
  # shellcheck source=./coordinator-trusted-root-guard.sh
  source "${BASH_SOURCE[0]%/*}/coordinator-trusted-root-guard.sh"
  coordinator_trusted_root_guard --mode=fail-open --root="$_rcc_incoming_cpr" --site="$0" || _rcc_incoming_cpr=''
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
  # Review: the Staff Engineer F7 — do NOT export COORDINATOR_CONTENT_ROOT. All 13 integration
  # sites source the resolver themselves and read the caller-scope var directly; none
  # rely on a child process inheriting it. Exporting into hot-path hooks (validate-commit,
  # session-init) propagates a resolver-internal location detail into every subprocess
  # those hooks spawn, masking resolution bugs in nested tooling. Set caller-scope only.
fi
