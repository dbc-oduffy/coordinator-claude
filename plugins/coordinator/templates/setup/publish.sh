#!/usr/bin/env bash
# publish.sh — Sync (a.k.a. percolate / push-to-publish-repo) plugin files from canonical source to downstream release repos
#
# Source directories are per-target, configured in the machine-local registry
# (publish.targets key) or in the legacy publish-targets.sh fallback. See
# .percolate-identity.example and registry.toml.example for configuration shapes.
# Each target repo receives either a full mirror or a manifest-driven subset.
#
# (a.k.a. percolate / push-to-publish-repo)
#
# Usage:
#   bash ~/.claude/setup/publish.sh                    # publish to all targets
#   bash ~/.claude/setup/publish.sh coordinator-claude  # publish to one target
#   bash ~/.claude/setup/publish.sh --dry-run           # preview changes
#   bash ~/.claude/setup/publish.sh --dry-run holodeck   # preview one target
#
# Requires: publish-targets.sh (copy from publish-targets.example.sh)

set -euo pipefail

# bash 4.0+ guard — this script uses associative arrays (declare -A). macOS ships
# bash 3.2 as /bin/bash, which lacks them, so publishing from a Mac under system
# bash would crash mid-run with "declare: -A: invalid option". Fail fast instead.
if (( BASH_VERSINFO[0] < 4 )); then
  echo "ERROR: publish.sh requires bash 4.0 or later (it uses associative arrays)." >&2
  echo "       Detected: bash ${BASH_VERSION:-unknown}" >&2
  echo "  macOS ships bash 3.2 as /bin/bash. Install a current bash and re-run with it:" >&2
  echo "      brew install bash" >&2
  echo '      "$(brew --prefix)/bin/bash" ~/.claude/setup/publish.sh' >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------------------
# Personal identity tokens — sourced from .percolate-identity (gitignored,
# per-operator). Defaults to empty arrays so a fresh install with no identity
# file works correctly (generic patterns below still cover the common cases).
# See .percolate-identity.example for the file format.
# ---------------------------------------------------------------------------
PERSONAL_EXPECTED_PATTERNS=()
PERSONAL_REVIEW_PATTERNS=()
PERSONAL_ALLOW_TOKENS=()
if [[ -f "$SCRIPT_DIR/.percolate-identity" ]]; then
  # Trust boundary: .percolate-identity is machine-local config (gitignored).
  # It is sourced as shell code — only place this file on trusted machines.
  # shellcheck source=/dev/null
  source "$SCRIPT_DIR/.percolate-identity"
fi

# Portable Python 3 invocation — `python3` on Linux/macOS; `py -3` on Windows
# Git Bash where the launcher is the canonical entry; `python` as last-resort
# fallback (relies on it being Py3 — Py2 is decade-EOL but bare-`python` lingers
# on older Windows installs). Audit ref: install-scripts.md OOS-1 (2026-05-20).
if command -v python3 >/dev/null 2>&1; then
  PY=(python3)
elif command -v py >/dev/null 2>&1; then
  PY=(py -3)
elif command -v python >/dev/null 2>&1; then
  PY=(python)
else
  echo "publish.sh: no Python 3 interpreter found (tried python3, py -3, python). Install Python 3." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
DRY_RUN=false
TARGET_FILTER=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=true; shift ;;
    *)
      # Review: the Staff Engineer — guard against silent target override when two positional args are given
      if [[ -n "$TARGET_FILTER" ]]; then
        echo "Error: multiple targets specified ('$TARGET_FILTER' and '$1'). Use one target or none." >&2
        exit 1
      fi
      TARGET_FILTER="$1"; shift ;;
  esac
done

# ---------------------------------------------------------------------------
# Load target registry
# ---------------------------------------------------------------------------
# _load_targets — populate the TARGETS bash array from the best available source.
#
# Priority order:
#   1. machine-local registry (publish.targets key) — primary path
#   2. publish-targets.sh — deprecation fallback; emits a nudge once per invocation
#   3. Neither set — loud error with remediation hint
#
# Spec backlink: docs/plans/2026-05-19-machine-local-registry.md §5 Task 5
# Defensive: future refactors might call _load_targets in a loop; this prevents nudge spam.
# Review: code-reviewer (F3) — guard kept intentionally; see comment above.
_DEPRECATION_NUDGE_FIRED=false

_load_targets() {
  local targets_file="$SCRIPT_DIR/publish-targets.sh"
  # Review: code-reviewer (F4) — derive bin path from setup/'s sibling bin/ directory
  # rather than hardcoding $HOME/.claude/bin; MACHINE_LOCAL_BIN env var is the escape
  # hatch for tests or non-standard installs.
  local machine_local_bin="${MACHINE_LOCAL_BIN:-$(dirname "$SCRIPT_DIR")/bin/machine-local}"

  # Primary path: machine-local registry
  # Review: code-reviewer (F8) — empty array treated as "not configured"; fall
  # through to deprecation fallback so `"publish.targets" = []` in an operator's
  # registry doesn't silently publish nothing.
  if [[ -x "$machine_local_bin" ]] && bash "$machine_local_bin" has publish.targets 2>/dev/null; then
    # machine-local get returns TOML array elements joined by newlines (one row per line).
    local raw
    raw="$(bash "$machine_local_bin" get publish.targets)"
    TARGETS=()
    while IFS= read -r row; do
      [[ -n "$row" ]] && TARGETS+=("$row")
    done <<< "$raw"
    # Empty array: treat as not configured; fall through to deprecation path.
    if [[ ${#TARGETS[@]} -gt 0 ]]; then
      return 0
    fi
  fi

  # Deprecation fallback: publish-targets.sh
  if [[ -f "$targets_file" ]]; then
    if [[ "$_DEPRECATION_NUDGE_FIRED" == false ]]; then
      echo "[publish.sh] DEPRECATED: publish-targets.sh — migrate to machine-local registry (publish.targets key). See ~/.claude/machine-local/README.md" >&2
      _DEPRECATION_NUDGE_FIRED=true
    fi
    # Trust boundary: publish-targets.sh is machine-local config (gitignored).
    # It is sourced as shell code — only place this file on trusted machines.
    # shellcheck source=/dev/null
    source "$targets_file"
    return 0
  fi

  # Neither source available
  echo "Error: no publish targets found." >&2
  echo "Either:" >&2
  echo "  (a) Add publish.targets to ~/.claude/machine-local/registry.toml" >&2
  echo "      See ~/.claude/machine-local/README.md for the key format." >&2
  echo "  (b) Copy publish-targets.example.sh (legacy fallback):" >&2
  echo "      cp $SCRIPT_DIR/publish-targets.example.sh $targets_file" >&2
  exit 1
}

_load_targets

if [[ ${#TARGETS[@]} -eq 0 ]]; then
  echo "Error: TARGETS array is empty — check your publish.targets registry key or publish-targets.sh" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
total_synced=0
total_deleted=0
total_warnings=0

warn() {
  echo "  WARNING: $1"
  (( total_warnings += 1 )) || true
}

# ---------------------------------------------------------------------------
# Personal data audit patterns
# ---------------------------------------------------------------------------
#
# Two layers compose the final pattern arrays the audit loop uses:
#
#   1. Generic defaults derived at runtime from $HOME and $SCRIPT_DIR's drive
#      letter (where applicable). These catch the most common machine-local
#      leakage shapes (your home directory in paths, the drive your install
#      lives on) without requiring identity-file configuration.
#
#   2. Operator-specific tokens from .percolate-identity (loaded above into
#      PERSONAL_EXPECTED_PATTERNS / PERSONAL_REVIEW_PATTERNS /
#      PERSONAL_ALLOW_TOKENS). These add operator name, org slug, working-
#      branch prefix, machine codename, etc.
#
# Patterns that are expected and need no action. (Currently informational —
# not consumed by the audit loop; retained as documentation of which tokens
# the operator deems intentional.)
EXPECTED_PATTERNS=("${PERSONAL_EXPECTED_PATTERNS[@]+"${PERSONAL_EXPECTED_PATTERNS[@]}"}")

# Derive generic REVIEW_PATTERNS from runtime context.
#   * $HOME path leakage: catch raw $HOME ("/c/Users/yourname" → "C:\\Users\\yourname")
#     and JSON-encoded variants ("C:\\\\Users\\\\yourname"). On POSIX, $HOME ships
#     as-is (no backslash transform needed).
#   * Drive-letter leakage: derive from $SCRIPT_DIR (e.g. "/x/..." → "X:\\\\"
#     and "X:\\") so installs on non-C: drives don't leak the drive letter
#     into config files.
_review_pat_generic=()
_home_posix="${HOME:-}"
if [[ -n "$_home_posix" ]]; then
  # MSYS/Git-Bash style path: /c/Users/foo → C:\Users\foo (raw) and C:\\Users\\foo (JSON)
  if [[ "$_home_posix" =~ ^/([a-zA-Z])/(.+)$ ]]; then
    _drive_upper="$(printf '%s' "${BASH_REMATCH[1]}" | tr '[:lower:]' '[:upper:]')"
    _home_rest="${BASH_REMATCH[2]//\//\\}"
    _review_pat_generic+=("${_drive_upper}:\\\\\\\\${_home_rest//\\/\\\\\\\\}")
    _review_pat_generic+=("${_drive_upper}:\\\\${_home_rest//\\/\\\\}")
  else
    # POSIX: use $HOME as-is
    _review_pat_generic+=("$_home_posix")
  fi
fi
# Drive letter from SCRIPT_DIR (e.g. /x/foo → X:\\\\, X:\\). Captures secondary
# drives without requiring identity-file config; only triggers when SCRIPT_DIR
# is not on the same drive as $HOME (avoiding duplicate patterns).
if [[ "$SCRIPT_DIR" =~ ^/([a-zA-Z])/ ]]; then
  _sd_drive="$(printf '%s' "${BASH_REMATCH[1]}" | tr '[:lower:]' '[:upper:]')"
  _home_drive=""
  if [[ "$_home_posix" =~ ^/([a-zA-Z])/ ]]; then
    _home_drive="$(printf '%s' "${BASH_REMATCH[1]}" | tr '[:lower:]' '[:upper:]')"
  fi
  if [[ "$_sd_drive" != "$_home_drive" ]]; then
    _review_pat_generic+=("${_sd_drive}:\\\\\\\\")
    _review_pat_generic+=("${_sd_drive}:\\\\")
  fi
fi

# Final REVIEW_PATTERNS = generic + personal.
REVIEW_PATTERNS=(
  "${_review_pat_generic[@]+"${_review_pat_generic[@]}"}"
  "${PERSONAL_REVIEW_PATTERNS[@]+"${PERSONAL_REVIEW_PATTERNS[@]}"}"
)

# Per-target marketplace-slug allowlists (Bucket 2 metadata).
# A target whose `native_slugs` field lists a marketplace slug treats that slug
# as expected content — the audit will skip it instead of flagging a bare-name
# REVIEW hit. Populated from the 5th tuple field by the main loop.
declare -A TARGET_NATIVE_SLUGS=()

# Pattern matching helpers — $1 is a PCRE regex (not a literal string).
# Safe with hardcoded REVIEW_PATTERNS; do NOT pass unvalidated user input.
# Uses perl for regex so \b word-boundaries work on macOS/BSD/Linux without
# requiring GNU grep. LC_ALL=C on grep was needed for MSYS2; perl handles
# encoding cleanly on its own.
# Portability fix: replaced grep -P (GNU/PCRE-only) with perl -ne (universally available).
perl_match() { perl -ne '$f=1 if /'"$1"'/; END{exit !$f}' "$2"; }
perl_any()   { perl -ne 'print if /'"$1"'/' "$2"; }

# Global array for per-target file tracking (populated by sync_mirror/sync_manifest)
AUDIT_FILES=()
CURRENT_PLUGIN_HEADER=""

# ---------------------------------------------------------------------------
# .percolate-ignore — source-side publish-content policy
# ---------------------------------------------------------------------------
# A file at $SOURCE_DIR/.percolate-ignore (gitignore-shaped, simplified subset)
# specifies paths that mirror mode should NOT copy and NOT delete from the
# destination. Patterns are matched against rel_path (per-sub-plugin).
#
# Supported pattern forms (NOT full gitignore — '**/' is not supported):
#   dir/        prefix-anchored directory match  (matches dir/anything)
#   *.ext       basename glob                    (matches whatever.ext at any depth)
#   path/file   exact path                       (matches that exact rel_path)
#
# Lines starting with # are comments. Blank lines ignored.
IGNORE_PATTERNS=()

load_percolate_ignore() {
  local source_dir="$1"
  local ignore_file="$source_dir/.percolate-ignore"
  IGNORE_PATTERNS=()

  if [[ ! -f "$ignore_file" ]]; then
    if $DRY_RUN; then
      echo "  Note: No .percolate-ignore found at $source_dir — defaulting to publish-everything."
      echo "        Run /setup-percolate to scaffold one."
    fi
    return 0
  fi

  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"  # Strip Windows \r
    # Skip comments and blank lines
    [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
    # Trim trailing whitespace
    line="${line%"${line##*[![:space:]]}"}"
    [[ -z "$line" ]] && continue
    IGNORE_PATTERNS+=("$line")
  done < "$ignore_file"

  if $DRY_RUN; then
    echo "  Loaded .percolate-ignore: ${#IGNORE_PATTERNS[@]} pattern(s)"
  fi
}

# is_ignored — returns 0 (true) if rel_path matches any IGNORE_PATTERN.
# Match semantics:
#   pattern ending in '/'   → directory match: rel_path begins with pattern
#                              (e.g. scratch/ matches scratch/foo and a/scratch/foo)
#   pattern with leading *  → basename glob: basename of rel_path matches pattern
#                              (e.g. *.bak matches a/b/c.bak)
#   anything else           → exact rel_path match
is_ignored() {
  local rel_path="$1"
  local pattern
  for pattern in "${IGNORE_PATTERNS[@]}"; do
    if [[ "$pattern" == */ ]]; then
      # Directory pattern: match prefix or any-depth occurrence
      local dir="${pattern%/}"
      [[ "$rel_path" == "$dir"/* ]] && return 0
      [[ "$rel_path" == */"$dir"/* ]] && return 0
    elif [[ "$pattern" == \** ]]; then
      # Basename glob (e.g. *.bak) — bash builtin (no basename fork)
      local base="${rel_path##*/}"
      # shellcheck disable=SC2053  # intentional glob match
      [[ "$base" == $pattern ]] && return 0
    else
      # Exact path match
      [[ "$rel_path" == "$pattern" ]] && return 0
    fi
  done
  return 1
}

# ---------------------------------------------------------------------------
# Copy-gate primitives — files_differ + bytes_differ
# ---------------------------------------------------------------------------
# Sourced from setup/lib/percolate-gate.sh so the regression test
# (setup/tests/test_needs_copy_content_aware.sh) and production share one
# definition. Replaces the prior 4-line inline replica + grep guardrail
# pattern that risked silent test/production drift (the Staff Engineer 2026-06-08).
# Doctrine: docstrings + caller contracts live in the lib file.
# shellcheck source=lib/percolate-gate.sh
source "$SCRIPT_DIR/lib/percolate-gate.sh"

# ---------------------------------------------------------------------------
# Hook registry — convention-based discovery of pre/post-rsync hooks
# ---------------------------------------------------------------------------
# Per-target hooks live at $SCRIPT_DIR/percolate-hooks/<target>/<hook-point>/*.sh.
# Hook scripts run in lexical order (numeric prefixes 10-, 20- order execution).
# Each script is invoked via `bash "$hook"` regardless of executable bit; the
# .sh file extension is the contract. *.sh.bak and *~ are excluded by the glob.
#
# Failure semantics: non-zero exit aborts the publish (set -euo pipefail).
# Pre-rsync abort = no destination mutation. Post-rsync abort = destination
# already mutated; recovery is to fix the hook and re-run /percolate (sync is
# idempotent; post-rsync hooks must be re-runnable — depersonalize already is).

# run_hooks <hook-point> <target-name> <target-dir>
# stdin (post-rsync only): newline-delimited list of synced files
# Echoes count to global HOOKS_RAN_COUNT.
HOOKS_RAN_COUNT=0
run_hooks() {
  local hook_point="$1"
  local target_name="$2"
  local target_dir="$3"

  HOOKS_RAN_COUNT=0
  local hooks_dir="$SCRIPT_DIR/percolate-hooks/$target_name/$hook_point"

  # Runtime guard: hooks_dir must NOT be inside SOURCE_DIR — if a future EM
  # widens SOURCE_DIR to encompass setup/, the hook tree would silently start
  # percolating. Loud-fail before any hook executes.
  if [[ -n "${SOURCE_DIR:-}" ]] && [[ "$hooks_dir" == "$SOURCE_DIR"/* ]]; then
    echo "FATAL: hooks dir $hooks_dir is inside SOURCE_DIR $SOURCE_DIR — this would percolate hook scripts. Aborting." >&2
    exit 1
  fi

  if [[ ! -d "$hooks_dir" ]]; then
    echo "  $hook_point hooks: (none — directory not present)"
    return 0
  fi

  # Collect hooks via array; nullglob in subshell so we don't leak the option.
  local hooks=()
  while IFS= read -r -d '' h; do hooks+=("$h"); done < <(
    cd "$hooks_dir" 2>/dev/null && \
      shopt -s nullglob && \
      for f in *.sh; do printf '%s\0' "$f"; done
  )

  if [[ ${#hooks[@]} -eq 0 ]]; then
    echo "  $hook_point hooks: (none)"
    return 0
  fi

  # Sort lexically (already lexical from glob expansion, but be explicit)
  local sorted_hooks=()
  while IFS= read -r h; do sorted_hooks+=("$h"); done < <(printf '%s\n' "${hooks[@]}" | sort)

  echo "  $hook_point hooks: $(printf '%s, ' "${sorted_hooks[@]}" | sed 's/, $//')"

  if $DRY_RUN; then
    echo "  (dry-run — hooks not invoked)"
    HOOKS_RAN_COUNT=${#sorted_hooks[@]}
    return 0
  fi

  # Invoke each hook. Pass synced files via stdin for post-rsync (always —
  # even when AUDIT_FILES is empty — so `while read` in the hook returns EOF
  # immediately rather than inheriting the parent's terminal stdin and blocking).
  #
  # Hook failure propagation: each invocation is wrapped in `if ! ...; then exit 1`
  # so that a non-zero hook exit aborts the publish loudly. Without this wrap,
  # subtle errexit-suppression in pipelines (`printf | bash`) and downstream
  # callers can swallow hook failures silently — empirically observed when the
  # post-percolate verification gate in 10-depersonalize.sh exited 1 but the
  # publish.sh wrapper reported exit 0. The explicit `if !` is robust regardless
  # of which errexit gotcha was masking it.
  local hook
  for hook in "${sorted_hooks[@]}"; do
    [[ -e "$hooks_dir/$hook" ]] || continue
    echo "  → $hook_point/$hook"
    if [[ "$hook_point" == "post-rsync" ]]; then
      # Empty-array-safe under set -u: the ${AUDIT_FILES[@]+...} form expands
      # to the array elements only when set, otherwise to nothing.
      if ! printf '%s\n' ${AUDIT_FILES[@]+"${AUDIT_FILES[@]}"} | bash "$hooks_dir/$hook" "$target_dir"; then
        echo "  → $hook_point/$hook FAILED (exit non-zero) — aborting publish" >&2
        exit 1
      fi
    else
      if ! bash "$hooks_dir/$hook" "$target_dir" </dev/null; then
        echo "  → $hook_point/$hook FAILED (exit non-zero) — aborting publish" >&2
        exit 1
      fi
    fi
    (( HOOKS_RAN_COUNT += 1 )) || true
  done
}

# ---------------------------------------------------------------------------
# Mirror mode: copy + delete per plugin dir
# ---------------------------------------------------------------------------
# Implementation note: the per-file work runs in setup/publish_sync.py — one
# Python process for the whole sync. The previous bash-only loop forked per
# file (cp, mkdir, diff -q, basename), which on Cygwin/MSYS exhausted
# cygwin1.dll heap at ~150 files (`fork: retry: Resource temporarily
# unavailable`, 2026-05-20 incident). Bash still owns hooks, audit patterns,
# and totals.
sync_mirror() {
  local target_dir="$1"
  local synced=0
  local removed=0

  echo "  Mode: mirror (copy + delete per plugin)"
  echo ""

  # Load .percolate-ignore from $SOURCE_DIR (or emit missing-nudge in dry-run)
  load_percolate_ignore "$SOURCE_DIR"

  local ignore_arg=()
  if [[ -f "$SOURCE_DIR/.percolate-ignore" ]]; then
    ignore_arg=(--ignore "$SOURCE_DIR/.percolate-ignore")
  fi
  local dry_arg=()
  $DRY_RUN && dry_arg=(--dry-run)

  # Run Python sync; capture stdout to a temp so we can both echo and parse.
  local sync_log
  sync_log="$(mktemp)"
  if ! "${PY[@]}" "$SCRIPT_DIR/publish_sync.py" mirror "$SOURCE_DIR" "$target_dir" \
       "${ignore_arg[@]}" "${dry_arg[@]}" > "$sync_log" 2>&1; then
    cat "$sync_log" >&2
    rm -f "$sync_log"
    echo "  ERROR: publish_sync.py failed" >&2
    return 1
  fi

  # Stream output to stdout AND collect AUDIT_FILES from NEW:/UPDATE: lines
  # (real-run only — dry-run paths are not on disk).
  local line rel_path action
  while IFS= read -r line; do
    line="${line%$'\r'}"  # strip CR from python output on Windows
    echo "$line"
    if ! $DRY_RUN; then
      if [[ "$line" =~ ^[[:space:]]+(NEW|UPDATE):[[:space:]]+(.+)$ ]]; then
        action="${BASH_REMATCH[1]}"
        rel_path="${BASH_REMATCH[2]}"
        # rel_path is relative to plugin dir; need to find which plugin we're in
        # by tracking the most recent "--- <plugin> ---" header.
        AUDIT_FILES+=("$target_dir/$CURRENT_PLUGIN_HEADER/$rel_path")
      fi
    fi
    if [[ "$line" =~ ^[[:space:]]+---[[:space:]]+(.+)[[:space:]]+---$ ]]; then
      CURRENT_PLUGIN_HEADER="${BASH_REMATCH[1]}"
    fi
    if [[ "$line" =~ ^SUMMARY[[:space:]]+synced=([0-9]+)[[:space:]]+removed=([0-9]+)$ ]]; then
      synced="${BASH_REMATCH[1]}"
      removed="${BASH_REMATCH[2]}"
    fi
  done < "$sync_log"
  rm -f "$sync_log"

  (( total_synced += synced )) || true
  (( total_deleted += removed )) || true
  echo ""
  echo "  Synced: $synced file(s), Removed: $removed file(s)"
}

# ---------------------------------------------------------------------------
# Flat-mirror mode: copy + delete for a flat .md directory (no subdirs)
# ---------------------------------------------------------------------------
# Handles source trees where all .md files live at the top level with no
# subdirectories — the coordinator-claude-toplevel-wiki target is the canonical
# example. sync_mirror() iterates over plugin subdirs and silently no-ops
# against a flat directory; this sibling mode handles the flat case cleanly
# without perturbing sync_mirror()'s subdir-iterating contract.
#
# Spec backlink: docs/plans/2026-05-18-publish-repo-toplevel-wiki-sync.md § F9
sync_flat_mirror() {
  local target_dir="$1"
  local synced=0
  local removed=0

  echo "  Mode: flat-mirror (copy + delete at top level)"
  echo ""

  load_percolate_ignore "$SOURCE_DIR"

  local ignore_arg=()
  if [[ -f "$SOURCE_DIR/.percolate-ignore" ]]; then
    ignore_arg=(--ignore "$SOURCE_DIR/.percolate-ignore")
  fi
  local dry_arg=()
  $DRY_RUN && dry_arg=(--dry-run)

  local sync_log
  sync_log="$(mktemp)"
  if ! "${PY[@]}" "$SCRIPT_DIR/publish_sync.py" flat-mirror "$SOURCE_DIR" "$target_dir" \
       "${ignore_arg[@]}" "${dry_arg[@]}" > "$sync_log" 2>&1; then
    cat "$sync_log" >&2
    rm -f "$sync_log"
    echo "  ERROR: publish_sync.py failed" >&2
    return 1
  fi

  local line rel_path
  while IFS= read -r line; do
    line="${line%$'\r'}"  # strip CR from python output on Windows
    echo "$line"
    if ! $DRY_RUN; then
      if [[ "$line" =~ ^[[:space:]]+(NEW|UPDATE):[[:space:]]+(.+)$ ]]; then
        rel_path="${BASH_REMATCH[2]}"
        AUDIT_FILES+=("$target_dir/$rel_path")
      fi
    fi
    if [[ "$line" =~ ^SUMMARY[[:space:]]+synced=([0-9]+)[[:space:]]+removed=([0-9]+)$ ]]; then
      synced="${BASH_REMATCH[1]}"
      removed="${BASH_REMATCH[2]}"
    fi
  done < "$sync_log"
  rm -f "$sync_log"

  (( total_synced += synced )) || true
  (( total_deleted += removed )) || true
  echo ""
  echo "  Synced: $synced file(s), Removed: $removed file(s)"
}

# ---------------------------------------------------------------------------
# Manifest mode: selective file copy driven by publish-manifest.txt
# ---------------------------------------------------------------------------
sync_manifest() {
  local target_dir="$1"
  local manifest="$target_dir/publish-manifest.txt"
  local synced=0
  local deleted=0

  if [[ ! -f "$manifest" ]]; then
    echo "  Error: manifest not found at $manifest" >&2
    return 1
  fi

  echo "  Mode: manifest ($manifest)"
  echo ""

  # Collect plugin dirs for staleness scan (only SCAN: declared plugins)
  declare -A scan_plugins=()
  declare -A manifest_files=()

  # Pass 1: DELETE and SCAN lines
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"  # Strip Windows \r
    # Skip comments and blank lines
    [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue

    if [[ "$line" =~ ^SCAN:[[:space:]]*(.*) ]]; then
      scan_plugins["${BASH_REMATCH[1]}"]=1
      continue
    fi

    if [[ "$line" =~ ^DELETE:[[:space:]]*(.*) ]]; then
      local del_path="${BASH_REMATCH[1]}"
      local del_target="$target_dir/$del_path"

      if [[ -f "$del_target" ]]; then
        if $DRY_RUN; then
          echo "  DELETE: $del_path (would remove)"
        else
          rm "$del_target"
          echo "  DELETE: $del_path"
        fi
        (( deleted += 1 )) || true
      else
        echo "  DELETE: $del_path (already absent)"
      fi
    fi
  done < "$manifest"

  # Pass 2: COPY lines
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"  # Strip Windows \r
    # Skip comments, blank lines, DELETE lines, and SCAN directives
    [[ -z "$line" || "$line" =~ ^[[:space:]]*# || "$line" =~ ^DELETE: || "$line" =~ ^SCAN: ]] && continue

    local src_path="$line"
    local dst_path="$line"

    local src_file="$SOURCE_DIR/$src_path"
    local dst_file="$target_dir/$dst_path"

    # Track for staleness scan
    manifest_files["$src_path"]=1

    if [[ ! -f "$src_file" ]]; then
      warn "Source file missing: $src_path"
      continue
    fi

    # Skip if dst is at least as new as src (bash builtin; no fork)
    files_differ "$src_file" "$dst_file" || continue

    # Create parent dir if needed (bash parameter expansion; no dirname fork)
    local dst_parent="${dst_file%/*}"
    if [[ ! -d "$dst_parent" ]]; then
      if ! $DRY_RUN; then
        mkdir -p "$dst_parent"
      fi
    fi

    # Byte-divergence warning (PM 2026-05-28): warn iff an existing destination
    # is about to be overwritten with DIFFERENT bytes. MUST be computed before
    # the cp (after cp, src==dst). Identical-bytes-but-newer-mtime overwrites are
    # silent (no digression to flag).
    local content_replace=false
    if [[ -f "$dst_file" ]] && bytes_differ "$src_file" "$dst_file"; then
      content_replace=true
    fi
    if $DRY_RUN; then
      if [[ ! -f "$dst_file" ]]; then
        echo "  NEW:    $dst_path"
      elif $content_replace; then
        warn "REPLACE (content differs) — would overwrite: $dst_path"
      else
        echo "  UPDATE: $dst_path"
      fi
    else
      # Review: the Staff Engineer — check existence before cp; after cp the file always exists so NEW is never reached
      local is_new=true
      [[ -f "$dst_file" ]] && is_new=false
      cp "$src_file" "$dst_file"
      AUDIT_FILES+=("$dst_file")
      if $is_new; then
        echo "  NEW:    $dst_path"
      elif $content_replace; then
        warn "REPLACE (content differs) — overwrote: $dst_path"
      else
        echo "  UPDATE: $dst_path"
      fi
    fi
    (( synced += 1 )) || true
  done < "$manifest"

  # Staleness scan: only check SCAN:-declared plugins (not stripped subsets)
  echo ""
  echo "  --- staleness scan ---"
  local stale_count=0
  if [[ ${#scan_plugins[@]} -eq 0 ]]; then
    echo "    (no SCAN: directives — skipping)"
  fi
  for plugin_dir in "${!scan_plugins[@]}"; do
    local src_plugin="$SOURCE_DIR/$plugin_dir"
    [[ -d "$src_plugin" ]] || continue

    while IFS= read -r -d '' src_file; do
      local rel_path="${src_file#"$SOURCE_DIR"/}"

      # Skip plugin.json (never synced in manifest mode)
      [[ "$rel_path" == *"plugin.json"* ]] && continue
      # Skip _archived
      [[ "$rel_path" == *"_archived"* ]] && continue

      if [[ -z "${manifest_files[$rel_path]+_}" ]]; then
        warn "Not in manifest: $rel_path"
        (( stale_count += 1 )) || true
      fi
    done < <(find "$src_plugin" -type f -print0)
  done

  if [[ $stale_count -eq 0 ]]; then
    echo "    (all source files covered)"
  fi

  (( total_synced += synced )) || true
  (( total_deleted += deleted )) || true
  echo ""
  echo "  Synced: $synced file(s), Deleted: $deleted file(s)"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
echo "publish: plugin sources → downstream repos"
if $DRY_RUN; then
  echo "(dry-run mode — no files will be modified)"
fi
echo ""

processed=0
for target_entry in "${TARGETS[@]}"; do
  # Tuple shape: legacy 4-field "name|mode|source|path" OR 5-field
  # "name|mode|source|path|native_slugs" (comma-separated marketplace slugs).
  # Read the optional 5th field with default-empty so 4-field rows parse
  # unchanged.
  native_slugs=""
  IFS='|' read -r name mode SOURCE_DIR path native_slugs <<< "$target_entry"

  # Filter to specific target if requested
  if [[ -n "$TARGET_FILTER" && "$name" != "$TARGET_FILTER" ]]; then
    continue
  fi

  # Per-target native-slug allowlist (Bucket 2). The 5th tuple field is a
  # comma-separated list of marketplace slugs that are EXPECTED in this
  # target's content. Empty = no per-target allowlist (same behavior as a
  # legacy 4-field tuple).
  TARGET_NATIVE_SLUGS["$name"]="${native_slugs:-}"

  # Reset per-target file tracking for audit
  AUDIT_FILES=()

  echo "=== $name ($mode) ==="
  echo "  Source: $SOURCE_DIR"
  echo "  Target: $path"

  # Validate source path exists
  if [[ ! -d "$SOURCE_DIR" ]]; then
    echo "  Error: source path does not exist: $SOURCE_DIR" >&2
    echo "  Skipping $name."
    echo ""
    continue
  fi

  # Dirty-tree guard: publish copies the WORKING TREE of $SOURCE_DIR, so
  # uncommitted (or stash-resurrected — see 2026-05-31) edits would ship to the
  # publish target. Refuse when the source subtree is dirty, unless
  # COORDINATOR_OVERRIDE_DIRTY_TREE=1. Skipped when SOURCE_DIR is not inside a git
  # work tree (can't assess). Dry-run warns but never aborts.
  if git -C "$SOURCE_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    dirty="$(git -C "$SOURCE_DIR" status --porcelain -- . 2>/dev/null)"
    if [[ -n "$dirty" ]]; then
      if $DRY_RUN; then
        echo "  WARNING: $SOURCE_DIR has uncommitted changes — these would publish from the working tree:" >&2
        printf '%s\n' "$dirty" | sed 's/^/    /' >&2
      elif [[ "${COORDINATOR_OVERRIDE_DIRTY_TREE:-0}" == "1" ]]; then
        echo "  WARNING: $SOURCE_DIR is dirty; COORDINATOR_OVERRIDE_DIRTY_TREE=1 set — publishing working-tree state anyway." >&2
      else
        echo "  Error: $SOURCE_DIR has uncommitted changes; refusing to publish working-tree state." >&2
        echo "         Commit first, or set COORDINATOR_OVERRIDE_DIRTY_TREE=1 to override." >&2
        printf '%s\n' "$dirty" | sed 's/^/    /' >&2
        echo "  Skipping $name."
        echo ""
        continue
      fi
    fi
  fi

  # Validate target path exists
  if [[ ! -d "$path" ]]; then
    echo "  Error: target path does not exist: $path" >&2
    echo "  Skipping $name."
    echo ""
    continue
  fi

  # Pre-rsync hooks (run before sync; pre-rsync abort = no destination mutation)
  echo ""
  run_hooks "pre-rsync" "$name" "$path"

  case "$mode" in
    mirror)       sync_mirror "$path" ;;
    flat-mirror)  sync_flat_mirror "$path" ;;
    manifest)     sync_manifest "$path" ;;
    *)
      echo "  Error: unknown mode '$mode'" >&2
      continue
      ;;
  esac

  # Post-rsync hooks (run after sync, before Phase 4 audit)
  # Depersonalization for non-holodeck targets is registered as
  # setup/percolate-hooks/<target>/post-rsync/10-depersonalize.sh.
  echo ""
  run_hooks "post-rsync" "$name" "$path"

  # Phase 3.5: write publish-side install-provenance sentinel.
  # version.txt = source meta-repo HEAD at publish time. Useful for OSS-clone
  # consumers (source_is_live-by-git-pull case). Install-side sentinel
  # semantics (downstream copy_install scripts writing their own version.txt
  # at install time) is canonical per live-install-drift-audit.md § copy_install
  # Mode — that path is NOT covered by this hook; see
  # docs/wiki/agentic-install-integrity.md § Writer location. Skipped on
  # dry-run; non-fatal on failure (publish succeeded, sentinel is advisory).
  if ! $DRY_RUN; then
    sentinel_writer="${COORDINATOR_BIN:-$SCRIPT_DIR/../plugins/coordinator/bin}/install-sentinel-write"
    if [[ ! -f "$sentinel_writer" ]]; then
      warn "install-sentinel-write not found at $sentinel_writer — version.txt will not be written; set COORDINATOR_BIN if your meta-repo layout differs"
    elif ! "${PY[@]}" "$sentinel_writer" --path "$path" --source "$SOURCE_DIR"; then
      warn "install-sentinel-write failed for $name — publish succeeded but version.txt absent"
    fi
  fi

  # Phase 4: Personal data audit
  if [[ ${#AUDIT_FILES[@]} -gt 0 ]]; then
    echo ""
    echo "  --- personal data audit ---"

    local_review_found=false

    for f in "${AUDIT_FILES[@]}"; do
      for pat in "${REVIEW_PATTERNS[@]}"; do
        if perl_match "$pat" "$f"; then
          echo "  REVIEW  [$pat]  $f"
          local_review_found=true
        fi
      done
      # Bare-identifier check: if any PERSONAL_ALLOW_TOKENS are configured,
      # flag occurrences of the bare identifier (alphabetic prefix of the
      # first allow-token) that do NOT match any allow-token or per-target
      # native-slug entry. This generalizes the legacy hardcoded `\boduffy\b`
      # check — the operator declares which identifier is theirs via
      # PERSONAL_ALLOW_TOKENS in .percolate-identity.
      if [[ ${#PERSONAL_ALLOW_TOKENS[@]} -gt 0 ]]; then
        # Use the first allow-token's leading alphabetic run as the bare
        # identifier to scan for. (E.g. PERSONAL_ALLOW_TOKENS=('foo-delphi'
        # 'Foo Bar') → scan for `\bfoo\b`.)
        _first_token="${PERSONAL_ALLOW_TOKENS[0]}"
        _bare_ident=""
        if [[ "$_first_token" =~ ^([a-zA-Z]+) ]]; then
          _bare_ident="$(printf '%s' "${BASH_REMATCH[1]}" | tr '[:upper:]' '[:lower:]')"
        fi
        if [[ -n "$_bare_ident" ]] && perl_match "\\b${_bare_ident}\\b" "$f"; then
          # Build allow_re from PERSONAL_ALLOW_TOKENS, joined by '|'. Add
          # per-target native_slugs (comma-separated → '|'-separated) if set.
          # CONTRACT: allow_re tokens are interpolated verbatim into a Perl inline
          # regex — tokens must not contain Perl metacharacters (., *, +, (, ), [, ],
          # ^, $, ?, {, }, \, |). Current live tokens (e.g. "foo-delphi", "O'Duffy")
          # are safe. If you add a token with a metacharacter, escape it first or
          # pre-process with quotemeta.
          allow_re="$(IFS='|'; echo "${PERSONAL_ALLOW_TOKENS[*]}")"
          _slugs="${TARGET_NATIVE_SLUGS[$name]:-}"
          if [[ -n "$_slugs" ]]; then
            allow_re="${allow_re}|${_slugs//,/|}"
          fi
          # Collect grep output before piping to perl — avoids SIGPIPE false-negative
          # under set -o pipefail when perl exits early after finding a disallowed match.
          _matches="$(perl_any "\\b${_bare_ident}\\b" "$f" || true)"
          if printf '%s\n' "$_matches" | perl -ne "\$f=1 if !/$allow_re/; END{exit !\$f}"; then
            echo "  REVIEW  [bare ${_bare_ident}]  $f"
            local_review_found=true
          fi
        fi
      fi
    done

    if $local_review_found; then
      echo ""
      echo "  WARNING: REVIEW items found — inspect files above before publishing."
      (( total_warnings += 1 )) || true
    else
      echo "  ✓ Clean — no personal data patterns found."
    fi
  fi

  # Phase 5: write last-sync marker (real run only; inverse-drift anchor for /percolate)
  # SEMANTICS: records the DESTINATION repo HEAD at the time of publish — this is the
  # pre-publish HEAD (before the operator commits the synced files). The marker therefore
  # represents "what was in the destination just before this publish run", not the
  # post-commit state. /percolate uses it to detect inverse-drift (dest changes since
  # last sync); its anchor being pre-commit is intentional and expected.
  if ! $DRY_RUN; then
    if [[ -d "$path/.git" ]] || git -C "$path" rev-parse --git-dir &>/dev/null; then
      dest_head="$(git -C "$path" rev-parse HEAD 2>/dev/null || true)"
      if [[ -n "$dest_head" ]]; then
        marker_dir="$SCRIPT_DIR/percolate-state"
        mkdir -p "$marker_dir"
        printf '%s\n' "$dest_head" > "$marker_dir/$name.lastsync"
      fi
    fi
  fi

  echo ""
  (( processed += 1 )) || true
done

# Summary
echo "==============================="
echo "Done. $processed target(s) processed."
echo "  Files synced:   $total_synced"
echo "  Files deleted:  $total_deleted"
echo "  Warnings:       $total_warnings"
if $DRY_RUN; then
  echo "  (dry-run — no changes were made)"
fi
