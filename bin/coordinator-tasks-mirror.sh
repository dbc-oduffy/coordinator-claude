#!/usr/bin/env bash
# coordinator-tasks-mirror.sh — Disk mirror for completeness-checklist items.
#
# Purpose: Write and update a per-session YAML mirror of the completeness-checklist
# items created by /pickup Step 5.5. The mirror lives at state/tasks/<sid>/<name>.yaml
# under the repo root — protected `state/` substrate (NOT bare tasks/, which is swept
# aggressively by /distill and /update-docs).
#
# Spec backlink: docs/plans/2026-07-06-ceremony-as-pipeline-2-doe-land-d-slice.md § C1.2
# Negative-spec: This script is ONLY called from within pickup Step 5.5's
# completeness_checklist gate. It is NOT called unconditionally; absent
# completeness_checklist baton field → this helper is never invoked.
#
# Usage:
#   coordinator-tasks-mirror.sh init <name> <item1_title> [<item2_title>...]
#     — Create the mirror file with all items as open.
#       <name>  = sanitized slug for the checklist (used as the yaml filename stem)
#
#   coordinator-tasks-mirror.sh update <name> <item_title> <state>
#     — Update a single item's state in the mirror.
#       <state> = open | done
#
# <sid> resolution: canonical 4-tier chain via cs_resolve_session_id from
# coordinator/lib/coordinator-session.sh (sourced at runtime):
#   Tier 1: $COORDINATOR_SESSION_ID
#   Tier 2: $CLAUDE_SESSION_ID
#   Tier 3: $CLAUDE_CODE_SESSION_ID
#   Tier 4: .git/coordinator-sessions/.current-session-id (ambiguity-aware)
#
# Output path: <repo-root>/state/tasks/<sid>/<slug>.yaml where <slug> is <name> sanitized to [a-zA-Z0-9_-]+
# Review: code-reviewer — F4: was hardcoded to completeness-checklist.yaml; actual filename is <slug>.yaml.
# The file is created if absent; updated atomically if already present.
#
# Exit codes:
#   0  — success
#   1  — usage / resolution error (message on stderr)
#
# Cross-platform: bash ≥ 4 + BSD coreutils. No GNU-isms (no sed -i in-place without
# a temp file, no date -d, no grep -P).

set -uo pipefail

if [[ "${BASH_VERSINFO[0]}" -lt 4 ]]; then
  echo "ERROR: bash >= 4 required. Stock macOS /bin/bash is 3.2 (unsupported)." >&2
  echo "Remediation: brew install bash && ensure /usr/local/bin/bash appears first in PATH." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Locate coordinator root and source the session lib
# ---------------------------------------------------------------------------

_cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
# shellcheck source=../lib/coordinator-trusted-root-guard.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../lib" && pwd)/coordinator-trusted-root-guard.sh"
coordinator_trusted_root_guard --mode=fail-loud --root="$_cc_root" --site="$0"
if [[ ! -d "$_cc_root" ]]; then
  echo "ERROR: coordinator root unresolved — ~/.claude/.doe-root missing/invalid;" \
       "re-run coordinator:install" >&2
  exit 1
fi

_session_lib="${_cc_root}/lib/coordinator-session.sh"
if [[ ! -f "$_session_lib" ]]; then
  echo "ERROR: coordinator-session.sh not found at $_session_lib" >&2
  exit 1
fi
# shellcheck disable=SC1090
source "$_session_lib"

# ---------------------------------------------------------------------------
# Resolve session id via the canonical 4-tier chain
# ---------------------------------------------------------------------------

_sid="$(cs_resolve_session_id)"
if [[ -z "$_sid" ]]; then
  echo "ERROR: could not resolve session id (all 4 tiers empty/ambiguous)." >&2
  echo "Set COORDINATOR_SESSION_ID to an explicit value and retry." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Resolve repo root (cwd must be inside the repo)
# ---------------------------------------------------------------------------

_repo_root="$(git rev-parse --show-toplevel 2>/dev/null)"
if [[ -z "$_repo_root" ]]; then
  echo "ERROR: not inside a git repo; cannot resolve state/ path." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Usage validation
# ---------------------------------------------------------------------------

if [[ $# -lt 2 ]]; then
  echo "Usage: coordinator-tasks-mirror.sh init <name> [<title>...]" >&2
  echo "       coordinator-tasks-mirror.sh update <name> <title> <state>" >&2
  exit 1
fi

_cmd="$1"
_name="$2"

# Sanitize name to a safe filename slug (alphanumeric, dash, underscore only).
_slug="${_name//[^a-zA-Z0-9_-]/-}"
_slug="${_slug#-}"   # strip leading dash
_slug="${_slug%-}"   # strip trailing dash
if [[ -z "$_slug" || "$_slug" == "-" ]]; then
  # Review: code-reviewer — F6: extend guard to catch single-dash result (e.g. "!!!" →
  # "---" → strip leading "-" → "--" → strip trailing "-" → "-").  A file named "-.yaml"
  # is valid on all platforms but degenerate; fall back to the default slug.
  _slug="completeness-checklist"
fi

_mirror_dir="${_repo_root}/state/tasks/${_sid}"
_mirror_file="${_mirror_dir}/${_slug}.yaml"

# ---------------------------------------------------------------------------
# Helper: write the mirror dir + file atomically
# ---------------------------------------------------------------------------

_now_iso() {
  date -u +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date +"%Y-%m-%dT%H:%M:%SZ"
}

_yaml_escape_scalar() {
  # Emit a single-quoted YAML scalar value (safe for arbitrary strings).
  # Replace any single quote in the value with '' (YAML escape for ').
  local v="${1:-}"
  v="${v//\'/\'\'}"
  echo "'${v}'"
}

# ---------------------------------------------------------------------------
# Subcommand: init
# ---------------------------------------------------------------------------

if [[ "$_cmd" == "init" ]]; then
  shift 2   # consume cmd + name; remaining args are item titles
  _titles=("$@")

  mkdir -p "$_mirror_dir"

  {
    printf '# completeness-checklist mirror — managed by coordinator-tasks-mirror.sh\n'
    printf '# Spec: docs/plans/2026-07-06-ceremony-as-pipeline-2-doe-land-d-slice.md § C1.2\n'
    printf '# state/tasks/<sid>/ is protected substrate (never bare tasks/ — DR-173)\n'
    printf '#\n'
    printf 'schema: completeness-checklist-mirror-v1\n'
    printf 'sid: %s\n' "$(_yaml_escape_scalar "$_sid")"
    printf 'created_at: %s\n' "$(_now_iso)"
    printf 'updated_at: %s\n' "$(_now_iso)"
    printf 'items:\n'
    for _t in "${_titles[@]}"; do
      printf '  - title: %s\n' "$(_yaml_escape_scalar "$_t")"
      printf '    state: open\n'
      printf '    updated_at: %s\n' "$(_now_iso)"
    done
  } > "${_mirror_file}.tmp"

  mv "${_mirror_file}.tmp" "$_mirror_file"
  echo "mirror: wrote ${_mirror_file} (${#_titles[@]} items)"
  exit 0
fi

# ---------------------------------------------------------------------------
# Subcommand: update
# ---------------------------------------------------------------------------

if [[ "$_cmd" == "update" ]]; then
  if [[ $# -lt 4 ]]; then
    echo "Usage: coordinator-tasks-mirror.sh update <name> <title> <state>" >&2
    exit 1
  fi
  _update_title="$3"
  _update_state="$4"

  if [[ "$_update_state" != "open" && "$_update_state" != "done" ]]; then
    echo "ERROR: state must be 'open' or 'done', got '${_update_state}'" >&2
    exit 1
  fi

  if [[ ! -f "$_mirror_file" ]]; then
    echo "ERROR: mirror file not found at ${_mirror_file} — call 'init' first." >&2
    exit 1
  fi

  # Rewrite the file: find the item whose title matches and flip its state.
  # We do a line-by-line pass without GNU sed -i (BSD-portable).
  _tmp_out="${_mirror_file}.update.tmp"
  _found=0
  _in_matching_item=0
  _escaped_title="$(_yaml_escape_scalar "$_update_title")"
  _now="$(_now_iso)"

  while IFS= read -r _line || [[ -n "$_line" ]]; do
    # Detect the start of an item block whose title matches.
    if [[ "$_line" == "  - title: ${_escaped_title}" ]]; then
      _in_matching_item=1
      _found=1
      printf '%s\n' "$_line"
      continue
    fi

    # If we're inside the matching item and see the state line, replace it.
    if (( _in_matching_item )) && [[ "$_line" =~ ^[[:space:]]+state: ]]; then
      printf '    state: %s\n' "$_update_state"
      continue
    fi

    # If we're inside the matching item and see the updated_at line, replace it.
    if (( _in_matching_item )) && [[ "$_line" =~ ^[[:space:]]+updated_at: ]]; then
      printf '    updated_at: %s\n' "$_now"
      _in_matching_item=0   # reset after last per-item field we mutate
      continue
    fi

    # Exit the matching-item context when we hit the next item or top-level field.
    if (( _in_matching_item )) && [[ "$_line" =~ ^[[:space:]]*-[[:space:]] || "$_line" =~ ^[^[:space:]] ]]; then
      _in_matching_item=0
    fi

    printf '%s\n' "$_line"
  done < "$_mirror_file" > "$_tmp_out"

  # Also update the top-level updated_at timestamp.
  _tmp2="${_mirror_file}.update2.tmp"
  while IFS= read -r _line || [[ -n "$_line" ]]; do
    if [[ "$_line" =~ ^updated_at: ]]; then
      printf 'updated_at: %s\n' "$_now"
    else
      printf '%s\n' "$_line"
    fi
  done < "$_tmp_out" > "$_tmp2"
  rm -f "$_tmp_out"
  mv "$_tmp2" "$_mirror_file"

  if (( _found == 0 )); then
    echo "WARN: item title not found in mirror — no update applied. Title: ${_update_title}" >&2
    # Review: code-reviewer — F2: exit 1 (not 0) so callers using || or $? can
    # distinguish "update applied" from "title not found"; a silent 0 leaves the
    # disk mirror out of sync with the Task state (item stays 'open' while Task
    # is 'completed'), defeating the cross-session durability guarantee.
    exit 1
  fi

  echo "mirror: updated '${_update_title}' → ${_update_state} in ${_mirror_file}"
  exit 0
fi

# Unknown subcommand
echo "ERROR: unknown subcommand '${_cmd}'. Expected: init | update" >&2
exit 1
