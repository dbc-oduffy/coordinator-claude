#!/usr/bin/env bash
# coordinator-archive-stamp.sh — stamp_shipped_in() lib: inserts `shipped_in:` into a handoff's
# frontmatter before git mv; sourced by /workstream-complete Step 2.7, /handoff Step 2.x, and
# session-init.sh orphan-sweep. Spec: docs/plans/2026-06-15-shipped-in-archive-stamping.md § C0.

# stamp_shipped_in <handoff_path> [--allow-branch-tip-fallback]
#
# Resolves the most recent git SHA touching the handoff's scope: paths, then invokes
# stamp-shipped-in.js to splice `shipped_in: <SHA8>` into the frontmatter.
#
# --allow-branch-tip-fallback: when no scope-path commit is found, fall back to the
#   branch-tip SHA. ONLY correct for ceremony-complete call sites (/workstream-complete,
#   /handoff supersession) where the branch tip plausibly belongs to this workstream.
#   DO NOT pass this flag from session-init.sh orphan-sweep — the branch tip there is
#   overwhelmingly a sibling workstream's commit; misattribution is worse than no stamp.
#
# Note: scope: paths must be space-free. The unquoted git log expansion below is
#   intentional for multi-path query; paths with spaces will be incorrectly split.
#
# Exit codes: always 0 — stamping failures are emitted to stderr but do not fail the caller.
#
# Review: the Staff Engineer F1 — fallback off by default; C2b (orphan sweep) must NOT set the flag.
# Review: the Staff Engineer F2 — tightened awk exit conditions catch closing `---` and any subsequent
#   top-level YAML key regardless of case.
stamp_shipped_in() {
  local handoff_path="$1"
  local allow_branch_tip_fallback=0
  if [ "${2:-}" = "--allow-branch-tip-fallback" ]; then
    allow_branch_tip_fallback=1
  fi
  local repo_root
  repo_root="$(git rev-parse --show-toplevel)"
  # Read scope: paths from frontmatter (YAML list under `scope:`).
  # Exit conditions: closing `---` delimiter OR any subsequent top-level key (any case/underscore).
  # Note: a bare --- inside the scope list truncates parsing; malformed YAML is not defended.
  local scope_paths
  scope_paths="$(awk 'NR==1 && /^---/{next} /^scope:/{found=1; next} found && /^  - /{print substr($0, 5)} /^---/{exit} found && /^[a-zA-Z_][a-zA-Z0-9_]*:/{exit}' "$handoff_path")"
  local sha
  if [ -n "$scope_paths" ]; then
    # shellcheck disable=SC2086 — intentional word splitting for multi-path log query
    sha="$(git -C "$repo_root" log --format=%H -n1 -- $scope_paths 2>/dev/null)"
  fi
  # Fallback: most recent commit on this branch — only when explicitly permitted.
  # C2b (orphan sweep) must NOT set this flag: the branch tip is likely a sibling
  # workstream's commit; misattribution is worse than leaving shipped_in: absent.
  if [ -z "$sha" ] && [ "$allow_branch_tip_fallback" -eq 1 ]; then
    sha="$(git -C "$repo_root" log --format=%H -n1 2>/dev/null)"
  fi
  if [ -n "$sha" ]; then
    # Insert into frontmatter via the standalone stamp helper
    # Review: F1 — resolve stamp CLI relative to this lib file before falling back to ~/.claude
    local _stamp_cli_path
    _stamp_cli_path="$(dirname "${BASH_SOURCE[0]}")/../bin/stamp-shipped-in.js"
    [[ ! -f "$_stamp_cli_path" ]] && _stamp_cli_path="${HOME}/.claude/plugins/coordinator/bin/stamp-shipped-in.js"
    # Review: F2 — emit warning to stderr on node failure; do not silently swallow errors
    node "$_stamp_cli_path" --handoff "$handoff_path" --sha "${sha:0:8}" \
      || echo "stamp_shipped_in: WARNING stamp CLI failed for ${handoff_path}" >&2
  fi
  # If sha is empty here, stamping is skipped — caller must decide if this is an error.
  return 0
}
