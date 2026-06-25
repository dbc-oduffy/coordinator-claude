#!/usr/bin/env bash
# coordinator-archive-stamp.sh — handoff lifecycle frontmatter-write lib. The single
# authorized-writer family for consumed/shipped handoff frontmatter, so the writes go via
# Bash (invisible to the Edit-only consumed-handoff freeze hook) instead of manual Edits:
#   - stamp_shipped_in()   : inserts `shipped_in:` before git mv (ship/supersede transition).
#   - cs_consume_handoff() : pickup-time consume transition (status→consumed, deployment_state→
#                            in_flight, +consumed_at/consumed_by) via bin/handoff-transition.js.
# Sourced by /workstream-complete Step 2.7, /handoff Step 2.x, /pickup Step 5, and
# session-init.sh orphan-sweep. Spec: docs/plans/2026-06-15-shipped-in-archive-stamping.md § C0;
# docs/plans/2026-06-24-handoff-lifecycle-transition-helper.md § C2.

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
  # The first bare `---` line opens the frontmatter region (so an installer-seeded leading
  # `<!-- ... -->` provenance comment ahead of the frontmatter is ignored); the next bare
  # `---` closes it. The pre-frontmatter comment guard (incmt) makes this comment-aware to
  # match the JS splitFrontmatter parser exactly (the Staff Engineer F6-review Finding 0): a bare `---`
  # line INSIDE a leading comment is skipped, not mistaken for the opener.
  # Exit conditions inside the region: closing `---` OR any subsequent top-level key.
  # Note: a bare --- inside the scope list truncates parsing; malformed YAML is not defended.
  local scope_paths
  scope_paths="$(awk '
    !infm && /<!--/ { incmt=1 }
    incmt { if (/-->/) incmt=0; next }
    !infm && /^---[ \t]*$/ { infm=1; next }
    infm && /^---[ \t]*$/ { exit }
    infm && /^scope:/ { found=1; next }
    infm && found && /^  - / { print substr($0, 5); next }
    infm && found && /^[a-zA-Z_][a-zA-Z0-9_]*:/ { exit }
  ' "$handoff_path")"
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
    node "$_stamp_cli_path" --handoff "$handoff_path" --sha "${sha:0:8}" || echo "stamp_shipped_in: WARNING stamp CLI failed for ${handoff_path}" >&2 # verify-no-console-flash: allow — node has no windowless equivalent (no nodew.exe); shell-level suppression unavailable per spawn-hidden.sh § Node on Windows. Deliberately allow-marked (not routed via spawn-hidden) because node suppression is unavailable and this is a once-per-session-init call, not a hot loop — contrast with coordinator-session.sh § cs_sweep_terminal_plans which routes via spawn-hidden on the happy path.
  fi
  # If sha is empty here, stamping is skipped — caller must decide if this is an error.
  return 0
}

# cs_consume_handoff <handoff_path>
#
# Pickup-time consume transition: atomically flips status: active→consumed,
# deployment_state→in_flight, and inserts consumed_at/consumed_by, via
# bin/handoff-transition.js (a Bash-driven node write — invisible to the Edit-only
# consumed-handoff freeze hook, so /pickup needs no override). Resolves the session id
# via _cs_resolve_session_id (the canonical 4-tier chain) and the timestamp via the
# BSD/GNU-portable `date -u +%Y-%m-%dT%H:%M:%SZ` form (NOT GNU-only --iso-8601).
#
# Exit non-zero on failure (UNLIKE stamp_shipped_in's always-exit-0): a missed
# shipped_in: stamp is advisory, but an un-mutated consume leaves status: active /
# consumed_by empty, defeating the claim-gate idempotency check and the pickup index —
# pickup MUST fail loud rather than proceed on a silent consume failure.
#
# Spec: docs/plans/2026-06-24-handoff-lifecycle-transition-helper.md § C2.
cs_consume_handoff() {
  local handoff_path="$1"
  if [ -z "$handoff_path" ]; then
    echo "cs_consume_handoff: usage: cs_consume_handoff <handoff_path>" >&2
    return 2
  fi
  # Resolve this lib's dir; fall back to the ~/.claude install path when BASH_SOURCE is
  # empty (e.g. invoked from a zsh tool-shell) — same robustness as stamp_shipped_in's
  # CLI resolution, extended to the sibling-source lookup too.
  # Review: code-reviewer A5 — go DIRECTLY to the ~/.claude fallback when BASH_SOURCE[0]
  # is empty; `dirname ""` → `.` (cwd) which is wrong for the coordinator-session.sh lookup.
  local _self_dir="${HOME}/.claude/plugins/coordinator/lib"
  [[ -n "${BASH_SOURCE[0]:-}" ]] && _self_dir="$(dirname "${BASH_SOURCE[0]}")"
  [[ ! -f "${_self_dir}/coordinator-session.sh" ]] && _self_dir="${HOME}/.claude/plugins/coordinator/lib"
  # _cs_resolve_session_id lives in coordinator-session.sh — source lazily if absent.
  if ! command -v _cs_resolve_session_id >/dev/null 2>&1; then
    # shellcheck source=/dev/null
    source "${_self_dir}/coordinator-session.sh"
  fi
  local sid
  sid="$(_cs_resolve_session_id)"
  if [ -z "$sid" ]; then
    echo "cs_consume_handoff: could not resolve a session id (empty consumed_by would corrupt the claim gate) — set CLAUDE_CODE_SESSION_ID or the session sentinel" >&2
    return 1
  fi
  local ts
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  # Resolve the node CLI relative to this lib first, then the ~/.claude fallback
  # (mirrors stamp_shipped_in's stamp-shipped-in.js resolution).
  local _cli_path
  _cli_path="${_self_dir}/../bin/handoff-transition.js"
  [[ ! -f "$_cli_path" ]] && _cli_path="${HOME}/.claude/plugins/coordinator/bin/handoff-transition.js"
  # Review: code-reviewer A6 — guard node presence before invoking; bare exit 127 gives no
  # actionable message (install-surface completeness: docs/wiki/install-surface-completeness.md).
  command -v node >/dev/null 2>&1 || { echo "cs_consume_handoff: node not found on PATH — install Node.js" >&2; return 1; }
  node "$_cli_path" consume --handoff "$handoff_path" --session-id "$sid" --at "$ts" # verify-no-console-flash: allow — node has no windowless equivalent (no nodew.exe); shell-level suppression unavailable per spawn-hidden.sh § Node on Windows. Once-per-pickup call, not a hot loop — same allow-mark rationale as stamp_shipped_in above.
}
