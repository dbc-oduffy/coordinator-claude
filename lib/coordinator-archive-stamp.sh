#!/usr/bin/env bash
# coordinator-archive-stamp.sh — handoff lifecycle frontmatter-write lib. The single
# authorized-writer family for consumed/shipped handoff frontmatter, so the writes go via
# Bash (invisible to the Edit-only consumed-handoff freeze hook) instead of manual Edits:
#   - stamp_shipped_in()   : inserts `shipped_in:` before git mv (ship/supersede transition).
#   - cs_consume_handoff() : pickup-time consume transition (status→consumed, deployment_state→
#                            in_flight, +consumed_at/consumed_by) via bin/handoff-transition.js.
# Sourced by /workstream-complete Step 2.7, /handoff Step 2.x, /pickup Step 5, and
# session-init.sh orphan-sweep. Spec: archive/completed/2026-06/2026-06-15-shipped-in-archive-stamping-a62b94.md § C0;
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
# Exit codes: 0 on State-1 (legacy path; node CLI failures absorbed) or State-2 (native
#   success); non-zero on State-3 (seam present but engine unreachable) — propagated to
#   caller for AC7 compliance (no silent mask on a live-but-broken engine).
#
# Review: code-reviewer F1 — removed || echo masking of State-3 non-zero; always-exit-0
#   contract revised to propagate hard-fail on native-transport failure (AC7).
#
# _cc_normalize_dotdot <path>
#
# Collapses a single embedded `../` traversal segment (e.g. `lib/../bin/x.js` →
# `bin/x.js`) via pure bash string manipulation — no `realpath`/`readlink -f`
# dependency (both absent on stock macOS; cross-platform-shell-portability.md
# forbids unguarded use). Purely lexical: does NOT resolve symlinks and does NOT
# touch the filesystem, so it's safe to call on paths that may not exist yet.
#
# Why this exists: every `${_self_dir}/../bin/<cli>.js` construction in this file
# feeds the `*"/.."*` trusted-prefix traversal guard below it. Bash's parameter
# expansion doesn't collapse `/../` on its own, so the guard was seeing the raw
# `lib/../bin/...` form and force-rejecting it even when the resolved path sat
# squarely inside a trusted root (`$HOME/.claude/` or `$_cc_doe`). Loop handles
# repeated segments (e.g. `a/b/../../c`) though callers here only ever produce one.
#
# Negative-spec: do NOT swap this for `realpath`/`readlink -f` — both are absent
# on stock macOS bash 3.2/BSD coreutils (see docs/wiki/cross-platform-shell-portability.md
# § Master construct table). A dotdot-prefixed basename (e.g. `..cache`) is NOT
# touched by this loop — it only ever matches a `/../` *segment* boundary, never
# a leading `..` inside a filename, preserving the accepted false-reject edge
# documented at every `*"/.."*` guard site in this file.
#
# Limitation (nit, Review: code-reviewer F1): the pattern `/[^/]+/\.\.(/|$)` requires
# a leading `/` before the segment being collapsed, so a bare leading `../foo` (no
# prior path segment) is NOT normalized — it passes through unchanged. Not reachable
# today: every call site here builds `${_self_dir}/../bin/...` which always has a
# segment before `/../`. A future caller that reuses this helper on a path that
# legitimately starts with `../` would need to pre-check for that shape separately.
#
# Bug fixed: 2026-07-06-cs-action-memo-dotdot-false-reject.md — cs_action_memo
# false-rejected on every DoE-rooted machine because `lib/../bin/memo-transition.js`
# tripped the traversal guard despite the DoE root prefix being trusted.
_cc_normalize_dotdot() {
  local p="$1"
  local prev=""
  while [ "$p" != "$prev" ]; do
    prev="$p"
    p="$(printf '%s' "$p" | sed -E 's#/[^/]+/\.\.(/|$)#\1#')"
  done
  printf '%s' "$p"
}

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
  local sha=""
  local _stamp_rc=0
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
    # Insert into frontmatter via the standalone stamp helper (or native handoff.stamp op).
    # Review: F1 — resolve stamp CLI relative to this lib file before falling back to ~/.claude
    local _stamp_cli_path _doe_root
    _stamp_cli_path="$(_cc_normalize_dotdot "$(dirname "${BASH_SOURCE[0]}")/../bin/stamp-shipped-in.js")"
    if [[ ! -f "$_stamp_cli_path" ]]; then
      _doe_root="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
      if [ -z "$_doe_root" ] || [ ! -d "$_doe_root/coordinator" ]; then echo "ERROR: ~/.claude/.doe-root missing/invalid — re-run coordinator:install" >&2; return 1 2>/dev/null || exit 1; fi
      _stamp_cli_path="${CLAUDE_PLUGIN_ROOT:-$_doe_root/coordinator}/bin/stamp-shipped-in.js"
      # shellcheck source=/dev/null
      source "$(dirname "${BASH_SOURCE[0]}")/coordinator-trusted-root-guard.sh"
      coordinator_trusted_root_guard --mode=fail-loud --root="$_stamp_cli_path" --site="$0"
    fi
    # DR-210 facade router (strang-07 C6): lazy-source the facade helper once per process.
    # Cold-fallback (_stamp_cli_path) resolved via BASH_SOURCE-relative path above — NEVER 'machine-local get'.
    if ! command -v strangle_route >/dev/null 2>&1; then
      local _stamp_sf_dir="${CLAUDE_PLUGIN_ROOT:-${CLAUDE_HOME:-$HOME}/.claude/coordinator}/lib"
      # shellcheck source=/dev/null
      source "$(dirname "${BASH_SOURCE[0]}")/coordinator-trusted-root-guard.sh"
      coordinator_trusted_root_guard --mode=fail-loud --root="$_stamp_sf_dir" --site="$0"
      [[ -n "${BASH_SOURCE[0]:-}" ]] && _stamp_sf_dir="$(dirname "${BASH_SOURCE[0]}")"
      # shellcheck source=./strangler-facade.sh
      source "${_stamp_sf_dir}/strangler-facade.sh"
    fi
    # Review: F2 — emit warning to stderr on node failure; do not silently swallow errors
    # legacy_stamp captures the original node invocation verbatim (State-1 cold-fallback only).
    legacy_stamp() {
      node "$_stamp_cli_path" --handoff "$handoff_path" --sha "${sha:0:8}" || echo "stamp_shipped_in: WARNING stamp CLI failed for ${handoff_path}" >&2 # verify-no-console-flash: allow — node has no windowless equivalent (no nodew.exe); shell-level suppression unavailable per spawn-hidden.sh § Node on Windows. Deliberately allow-marked (not routed via spawn-hidden) because node suppression is unavailable and this is a once-per-session-init call, not a hot loop — contrast with coordinator-session.sh § cs_sweep_terminal_plans which routes via spawn-hidden on the happy path.
    }
    local _stamp_params
    _stamp_params="$(jq -cn --arg handoff_path "$handoff_path" --arg sha "${sha:0:8}" \
      '{handoff_path: $handoff_path, sha: $sha}')"
    # Review: code-reviewer F1 — capture State-3 non-zero; do NOT silently convert to 0.
    # State-1 (legacy path): legacy_stamp absorbs node CLI failures → strangle_route exits 0.
    # State-3 (seam present, engine unreachable): strangle_route exits non-zero → propagate.
    strangle_route_mutation "handoff.stamp" "legacy_stamp" "$_stamp_params" || {
      _stamp_rc=$?
      echo "stamp_shipped_in: WARNING stamp route failed (State-3, exit ${_stamp_rc}) for ${handoff_path}" >&2
    }
  fi
  # If sha is empty here, stamping is skipped (exit 0). On State-3, _stamp_rc carries
  # the non-zero from strangle_route so callers can surface transport failures (AC7).
  return "$_stamp_rc"
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
  local _doe_root
  _doe_root="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
  if [ -z "$_doe_root" ] || [ ! -d "$_doe_root/coordinator" ]; then echo "ERROR: ~/.claude/.doe-root missing/invalid — re-run coordinator:install" >&2; return 1 2>/dev/null || exit 1; fi
  # Review: code-reviewer P1 — trusted BASH_SOURCE candidate resolved and probed FIRST;
  # CLAUDE_PLUGIN_ROOT-derived candidate is only computed (and guarded, once) when the
  # trusted sibling is absent. Previously the untrusted candidate was guarded FIRST with
  # --mode=fail-loud, hard-exiting before the trusted fallback ever ran — a hard DoS on
  # this lifecycle function under any untrusted CLAUDE_PLUGIN_ROOT.
  local _self_dir
  if [[ -n "${BASH_SOURCE[0]:-}" ]] && [[ -f "$(dirname "${BASH_SOURCE[0]}")/coordinator-session.sh" ]]; then
    _self_dir="$(dirname "${BASH_SOURCE[0]}")"
  else
    _self_dir="${CLAUDE_PLUGIN_ROOT:-$_doe_root/coordinator}/lib"
    # shellcheck source=/dev/null
    source "$(dirname "${BASH_SOURCE[0]}")/coordinator-trusted-root-guard.sh"
    coordinator_trusted_root_guard --mode=fail-loud --root="$_self_dir" --site="$0"
  fi
  # _cs_resolve_session_id lives in coordinator-session.sh — source lazily if absent.
  if ! command -v _cs_resolve_session_id >/dev/null 2>&1; then
    # shellcheck source=/dev/null
    source "${_self_dir}/coordinator-session.sh"
  fi
  # DR-210 facade router (strang-07 C6): lazy-source the facade helper once per process.
  # Cold-fallback (_doe_root) resolved via direct file read above — NEVER 'machine-local get'.
  if ! command -v strangle_route >/dev/null 2>&1; then
    # shellcheck source=/dev/null
    source "${_self_dir}/strangler-facade.sh"
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
  _cli_path="$(_cc_normalize_dotdot "${_self_dir}/../bin/handoff-transition.js")"
  if [[ ! -f "$_cli_path" ]]; then
    _cli_path="${CLAUDE_PLUGIN_ROOT:-$_doe_root/coordinator}/bin/handoff-transition.js"
    # shellcheck source=/dev/null
    source "$(dirname "${BASH_SOURCE[0]}")/coordinator-trusted-root-guard.sh"
    coordinator_trusted_root_guard --mode=fail-loud --root="$_cli_path" --site="$0"
  fi
  # Review: code-reviewer A6 — node check moved inside legacy_consume; on native path (State 2/3)
  # node is not required. legacy_consume captures the original node invocation verbatim (State-1 only).
  legacy_consume() {
    command -v node >/dev/null 2>&1 || { echo "cs_consume_handoff: node not found on PATH — install Node.js" >&2; return 1; }
    node "$_cli_path" consume --handoff "$handoff_path" --session-id "$sid" --at "$ts" # verify-no-console-flash: allow — node has no windowless equivalent (no nodew.exe); shell-level suppression unavailable per spawn-hidden.sh § Node on Windows. Once-per-pickup call, not a hot loop — same allow-mark rationale as stamp_shipped_in above.
  }
  local _consume_params
  _consume_params="$(jq -cn \
    --arg verb "consume" \
    --arg handoff_path "$handoff_path" \
    --arg session_id "$sid" \
    --arg at "$ts" \
    '{verb: $verb, handoff_path: $handoff_path, session_id: $session_id, at: $at}')"
  strangle_route_mutation "handoff.transition" "legacy_consume" "$_consume_params" || return $?
  # C2 write-moment: record pickup into session-shape.json (best-effort / non-fatal).
  # cs_session_shape_set is in coordinator-session.sh, lazily sourced above — available in scope.
  # A shape-write failure must not abort the pickup; mirror the advisory guard style in this lib.
  # Spec: docs/plans/2026-07-02-ceremony-as-pipeline-v1-session-state-co.md § C2
  local _hp_esc="${handoff_path//\\/\\\\}"
  _hp_esc="${_hp_esc//\"/\\\"}"
  cs_session_shape_set "$sid" "{\"pickup\":{\"happened\":true,\"handoff\":\"${_hp_esc}\"}}" 2>/dev/null \
    || echo "cs_consume_handoff: WARNING — session-shape pickup record failed (non-fatal)" >&2
}

# cs_claim_memo_stamp <memo_path>
#
# Pickup-time claim stamp: flips a cross-repo memo status: open→in_progress
# and inserts picked_up_at/picked_up_by, via bin/memo-transition.js claim
# (a Bash-driven node write — invisible to the Edit-only hook surface).
# Resolves session id via _cs_resolve_session_id (the canonical 4-tier chain)
# and timestamp via BSD/GNU-portable `date -u +%Y-%m-%dT%H:%M:%SZ`.
#
# NOTE: stamp layer only — this is SEPARATE from the mkdir LOCK in
# cs_claim_memo (coordinator-session.sh); do NOT fold them together; they
# serve different purposes (filesystem lock vs. frontmatter lifecycle write).
#
# Exit non-zero on failure (fail-loud contract): an empty picked_up_by would
# corrupt the claim gate; caller must fail rather than silently proceed.
#
# Spec backlink: docs/plans/2026-06-29-memo-transition-lifecycle-helper.md
cs_claim_memo_stamp() {
  local memo_path="$1"
  if [ -z "$memo_path" ]; then
    echo "cs_claim_memo_stamp: usage: cs_claim_memo_stamp <memo_path>" >&2
    return 2
  fi
  local _doe_root
  _doe_root="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
  if [ -z "$_doe_root" ] || [ ! -d "$_doe_root/coordinator" ]; then echo "ERROR: ~/.claude/.doe-root missing/invalid — re-run coordinator:install" >&2; return 1 2>/dev/null || exit 1; fi
  # Review: code-reviewer P1 — trusted BASH_SOURCE candidate resolved and probed FIRST;
  # CLAUDE_PLUGIN_ROOT-derived candidate is only computed (and guarded, once) when the
  # trusted sibling is absent. Previously the untrusted candidate was guarded FIRST with
  # --mode=fail-loud, hard-exiting before the trusted fallback ever ran — a hard DoS on
  # this lifecycle function under any untrusted CLAUDE_PLUGIN_ROOT.
  local _self_dir
  if [[ -n "${BASH_SOURCE[0]:-}" ]] && [[ -f "$(dirname "${BASH_SOURCE[0]}")/coordinator-session.sh" ]]; then
    _self_dir="$(dirname "${BASH_SOURCE[0]}")"
  else
    _self_dir="${CLAUDE_PLUGIN_ROOT:-$_doe_root/coordinator}/lib"
    # shellcheck source=/dev/null
    source "$(dirname "${BASH_SOURCE[0]}")/coordinator-trusted-root-guard.sh"
    coordinator_trusted_root_guard --mode=fail-loud --root="$_self_dir" --site="$0"
  fi
  if ! command -v _cs_resolve_session_id >/dev/null 2>&1; then
    # shellcheck source=/dev/null
    source "${_self_dir}/coordinator-session.sh"
  fi
  local sid
  sid="$(_cs_resolve_session_id)"
  if [ -z "$sid" ]; then
    echo "cs_claim_memo_stamp: could not resolve a session id (empty picked_up_by would corrupt the claim gate) — set CLAUDE_CODE_SESSION_ID or the session sentinel" >&2
    return 1
  fi
  local ts
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  local _cli_path
  _cli_path="$(_cc_normalize_dotdot "${_self_dir}/../bin/memo-transition.js")"
  if [[ ! -f "$_cli_path" ]]; then
    _cli_path="${CLAUDE_PLUGIN_ROOT:-$_doe_root/coordinator}/bin/memo-transition.js"
    # shellcheck source=/dev/null
    source "$(dirname "${BASH_SOURCE[0]}")/coordinator-trusted-root-guard.sh"
    coordinator_trusted_root_guard --mode=fail-loud --root="$_cli_path" --site="$0"
  fi
  command -v node >/dev/null 2>&1 || { echo "cs_claim_memo_stamp: node not found on PATH — install Node.js" >&2; return 1; }
  node "$_cli_path" claim --memo "$memo_path" --session-id "$sid" --at "$ts" # verify-no-console-flash: allow — node has no windowless equivalent (no nodew.exe); shell-level suppression unavailable per spawn-hidden.sh § Node on Windows. Once-per-pickup call, not a hot loop — same allow-mark rationale as stamp_shipped_in above.
}

# cs_action_memo <memo_path> [disposition-args...]
#
# Action transition: flips a cross-repo memo from in_progress→actioned and
# writes the caller's disposition flags through to bin/memo-transition.js
# action. Preserves picked_up_by/picked_up_at as the claim-of-record for
# the archived memo. Disposition flags are passed through verbatim; see
# bin/memo-transition.js usage block for the full flag surface
# (--decision/--decision-note/--realized-by or --actioned-note).
#
# No session-id or timestamp is required by the node action verb (takes neither); the ownership gate resolves caller_sid internally.
#
# Liveness-gated ownership gate (applied BEFORE the node call):
#   Refuses to close a memo that a DIFFERENT live session holds. Guard order
#   is fail-OPEN at every rung except the last (live-holder conflict):
#     1. Claim dir absent                     → PROCEED (no lock)
#     2. Caller session id unresolvable       → PROCEED (no identity to enforce)
#     3. Holder == caller                     → PROCEED (owner closing own claim)
#     4. cwd git root ≠ memo git root         → PROCEED (cross-repo: liveness
#        verdict from _cs_claim_holder_live untrustworthy — FOREIGN-BATON
#        non-coverage; same fail-open as cs_reap_stale_claims)
#     5. Holder ≠ caller AND holder is LIVE  → FAIL LOUD (return 1) unless
#        COORDINATOR_OVERRIDE_MEMO_ACTION_CLAIM is set (→ WARNING + PROCEED)
#     6. Holder ≠ caller AND holder is DEAD  → WARNING + PROCEED (stale claim)
#
#   Liveness is decided via _cs_claim_holder_live ONLY — never ps -p/kill -0
#   on a stored pid (RAW-PID-LIVENESS tripwire).
#
# Exit non-zero on failure (fail-loud contract).
#
# Spec backlink: docs/plans/2026-06-29-memo-transition-lifecycle-helper.md
cs_action_memo() {
  local memo_path="$1"
  if [ -z "$memo_path" ]; then
    echo "cs_action_memo: usage: cs_action_memo <memo_path> [disposition-args...]" >&2
    return 2
  fi
  shift
  local _doe_root
  _doe_root="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
  if [ -z "$_doe_root" ] || [ ! -d "$_doe_root/coordinator" ]; then echo "ERROR: ~/.claude/.doe-root missing/invalid — re-run coordinator:install" >&2; return 1 2>/dev/null || exit 1; fi
  # Review: code-reviewer P1 — trusted BASH_SOURCE candidate resolved and probed FIRST;
  # CLAUDE_PLUGIN_ROOT-derived candidate is only computed (and guarded, once) when the
  # trusted sibling is absent. Previously the untrusted candidate was guarded FIRST with
  # --mode=fail-loud, hard-exiting before the trusted fallback ever ran — a hard DoS on
  # this lifecycle function under any untrusted CLAUDE_PLUGIN_ROOT.
  local _self_dir
  if [[ -n "${BASH_SOURCE[0]:-}" ]] && [[ -f "$(dirname "${BASH_SOURCE[0]}")/coordinator-session.sh" ]]; then
    _self_dir="$(dirname "${BASH_SOURCE[0]}")"
  else
    _self_dir="${CLAUDE_PLUGIN_ROOT:-$_doe_root/coordinator}/lib"
    # shellcheck source=/dev/null
    source "$(dirname "${BASH_SOURCE[0]}")/coordinator-trusted-root-guard.sh"
    coordinator_trusted_root_guard --mode=fail-loud --root="$_self_dir" --site="$0"
  fi
  local _cli_path
  _cli_path="$(_cc_normalize_dotdot "${_self_dir}/../bin/memo-transition.js")"
  if [[ ! -f "$_cli_path" ]]; then
    _cli_path="${CLAUDE_PLUGIN_ROOT:-$_doe_root/coordinator}/bin/memo-transition.js"
    # shellcheck source=/dev/null
    source "$(dirname "${BASH_SOURCE[0]}")/coordinator-trusted-root-guard.sh"
    coordinator_trusted_root_guard --mode=fail-loud --root="$_cli_path" --site="$0"
  fi
  command -v node >/dev/null 2>&1 || { echo "cs_action_memo: node not found on PATH — install Node.js" >&2; return 1; }

  # ---- liveness-gated ownership gate ----------------------------------------
  local memo_git_root claim_dir
  memo_git_root="$(git -C "$(dirname "$memo_path")" rev-parse --show-toplevel 2>/dev/null)"
  if [[ -n "$memo_git_root" ]]; then
    claim_dir="${memo_git_root}/.git/coordinator-sessions/memo-claims/$(basename "$memo_path")"
    # Guard 1: claim dir absent → PROCEED.
    if [[ -d "$claim_dir" ]]; then
      # Source coordinator-session.sh for _cs_resolve_session_id / _cs_claim_holder_live
      # lazily — avoids sourcing overhead on the common no-active-claim path.
      # Review: F6 — moved inside Guard 1; mirrors sourcing pattern in cs_claim_memo_stamp.
      if ! command -v _cs_resolve_session_id >/dev/null 2>&1; then
        # shellcheck source=/dev/null
        source "${_self_dir}/coordinator-session.sh"
      fi
      local caller_sid
      caller_sid="$(_cs_resolve_session_id)"
      # Guard 2: caller sid unresolvable → PROCEED.
      if [[ -n "$caller_sid" ]]; then
        # Review: F2 — detect legacy pid-only claim dirs (no session_id file) before reading,
        # so Guard 6 can emit a discriminated message instead of "held by dead session ".
        local have_sid_file=0
        [[ -f "${claim_dir}/session_id" ]] && have_sid_file=1
        local holder_sid
        holder_sid="$(cat "${claim_dir}/session_id" 2>/dev/null || echo "")"
        # Guard 3: holder == caller → PROCEED (owner closing own claim).
        if [[ "$holder_sid" != "$caller_sid" ]]; then
          # Guard 4: cwd/memo-root asymmetry → PROCEED (cross-repo liveness
          # verdict is untrustworthy — FOREIGN-BATON non-coverage).
          local cwd_git_root
          cwd_git_root="$(git -C "$PWD" rev-parse --show-toplevel 2>/dev/null)"
          if [[ "$cwd_git_root" == "$memo_git_root" ]]; then
            # Guard 5/6: liveness decision (same-repo only — verdict trustworthy).
            if _cs_claim_holder_live "$claim_dir"; then
              # Holder is LIVE — Guard 5.
              if [[ -n "${COORDINATOR_OVERRIDE_MEMO_ACTION_CLAIM:-}" ]]; then
                echo "cs_action_memo: WARNING — memo held by live session ${holder_sid} (override COORDINATOR_OVERRIDE_MEMO_ACTION_CLAIM set) — proceeding" >&2
              else
                echo "cs_action_memo: REFUSING to action — memo '${memo_path}' is held by a DIFFERENT live session (${holder_sid}); you are (${caller_sid}). Release it, coordinate, or set COORDINATOR_OVERRIDE_MEMO_ACTION_CLAIM=1 to override." >&2
                return 1
              fi
            else
              # Holder is DEAD — Guard 6: stale claim, warn and PROCEED.
              # Review: F1 — message accurately states nothing is removed here; the claim dir
              # persists until cs_sweep_actioned_memos / cs_reap_stale_claims.
              # Review: F2 — discriminate legacy pid-only claim dirs from normal stale claims.
              if [[ "$have_sid_file" -eq 0 ]]; then
                echo "cs_action_memo: WARNING — stale claim on '${memo_path}' (legacy pid-only claim dir, no session_id file); proceeding (claim dir will be reaped by next reaper sweep)" >&2
              else
                echo "cs_action_memo: WARNING — stale claim on '${memo_path}' held by dead session ${holder_sid}; proceeding (claim dir will be reaped by next reaper sweep)" >&2
              fi
            fi
          fi
        fi
      fi
    fi
  fi
  # (non-git memo dir → no claim infrastructure possible → PROCEED)
  # ---- end ownership gate ----------------------------------------------------

  local _am_rc=0
  node "$_cli_path" action --memo "$memo_path" "$@" # verify-no-console-flash: allow — node has no windowless equivalent (no nodew.exe); shell-level suppression unavailable per spawn-hidden.sh § Node on Windows. Once-per-memo-transition, not a hot loop — same allow-mark rationale as stamp_shipped_in above.
  _am_rc=$?
  # C4 write-moment: record actioned memo into session-shape.json (best-effort / non-fatal).
  # Placement: AFTER liveness-gated ownership gate AND confirmed by node action verb exit 0 —
  # FAIL-LOUD / non-owner REFUSE paths have already returned 1 above; PROCEED paths that skip
  # Guard 1 (no claim dir) may not have sourced coordinator-session.sh yet — source lazily.
  # Mirrors C2's guard style (2>/dev/null || echo WARNING >&2) — a shape-write failure must
  # not abort the action; the primary concern (node transition) is already confirmed.
  # Spec: docs/plans/2026-07-02-ceremony-as-pipeline-v1-session-state-co.md § C4
  if [[ "$_am_rc" -eq 0 ]]; then
    # Ensure coordinator-session.sh (cs_session_shape_set + _cs_resolve_session_id) is sourced.
    # It is guaranteed sourced when Guard 1 (claim-dir present) was entered; when the memo had
    # no claim dir, the source above was skipped — ensure it here before calling.
    if ! command -v _cs_resolve_session_id >/dev/null 2>&1; then
      # shellcheck source=/dev/null
      source "${_self_dir}/coordinator-session.sh"
    fi
    local _am_sid
    _am_sid="$(_cs_resolve_session_id 2>/dev/null || true)"
    if [[ -n "$_am_sid" ]]; then
      local _am_basename _am_decision="" _am_prev="" _am_arg
      _am_basename="$(basename "$memo_path")"
      # Extract --decision value from disposition args (absent on --actioned-note paths).
      for _am_arg in "$@"; do
        [[ "$_am_prev" == "--decision" ]] && { _am_decision="$_am_arg"; break; }
        _am_prev="$_am_arg"
      done
      local _am_bn_esc="${_am_basename//\\/\\\\}"
      _am_bn_esc="${_am_bn_esc//\"/\\\"}"
      local _am_dec_esc="${_am_decision//\\/\\\\}"
      _am_dec_esc="${_am_dec_esc//\"/\\\"}"
      cs_session_shape_set "$_am_sid" "{\"actioned_memos\":[{\"basename\":\"${_am_bn_esc}\",\"decision\":\"${_am_dec_esc}\"}]}" 2>/dev/null \
        || echo "cs_action_memo: WARNING — session-shape actioned_memos record failed (non-fatal)" >&2
    fi
  fi
  return "$_am_rc"
}

# cs_release_memo_revert <memo_path>
#
# Release transition: reverts a cross-repo memo from in_progress→open and
# removes picked_up_by/picked_up_at entirely, via bin/memo-transition.js
# release. Use when a claim must be undone (e.g. dispatcher re-routing or
# receiver hand-off to a different session).
#
# No session-id or timestamp is required (the release verb takes neither).
#
# Exit non-zero on failure (fail-loud contract).
#
# Spec backlink: docs/plans/2026-06-29-memo-transition-lifecycle-helper.md
cs_release_memo_revert() {
  local memo_path="$1"
  if [ -z "$memo_path" ]; then
    echo "cs_release_memo_revert: usage: cs_release_memo_revert <memo_path>" >&2
    return 2
  fi
  local _doe_root
  _doe_root="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
  if [ -z "$_doe_root" ] || [ ! -d "$_doe_root/coordinator" ]; then echo "ERROR: ~/.claude/.doe-root missing/invalid — re-run coordinator:install" >&2; return 1 2>/dev/null || exit 1; fi
  # Review: code-reviewer P1 — trusted BASH_SOURCE candidate resolved and probed FIRST;
  # CLAUDE_PLUGIN_ROOT-derived candidate is only computed (and guarded, once) when the
  # trusted sibling is absent. Previously the untrusted candidate was guarded FIRST with
  # --mode=fail-loud, hard-exiting before the trusted fallback ever ran — a hard DoS on
  # this lifecycle function under any untrusted CLAUDE_PLUGIN_ROOT.
  local _self_dir
  if [[ -n "${BASH_SOURCE[0]:-}" ]] && [[ -f "$(dirname "${BASH_SOURCE[0]}")/coordinator-session.sh" ]]; then
    _self_dir="$(dirname "${BASH_SOURCE[0]}")"
  else
    _self_dir="${CLAUDE_PLUGIN_ROOT:-$_doe_root/coordinator}/lib"
    # shellcheck source=/dev/null
    source "$(dirname "${BASH_SOURCE[0]}")/coordinator-trusted-root-guard.sh"
    coordinator_trusted_root_guard --mode=fail-loud --root="$_self_dir" --site="$0"
  fi
  local _cli_path
  _cli_path="$(_cc_normalize_dotdot "${_self_dir}/../bin/memo-transition.js")"
  if [[ ! -f "$_cli_path" ]]; then
    _cli_path="${CLAUDE_PLUGIN_ROOT:-$_doe_root/coordinator}/bin/memo-transition.js"
    # shellcheck source=/dev/null
    source "$(dirname "${BASH_SOURCE[0]}")/coordinator-trusted-root-guard.sh"
    coordinator_trusted_root_guard --mode=fail-loud --root="$_cli_path" --site="$0"
  fi
  command -v node >/dev/null 2>&1 || { echo "cs_release_memo_revert: node not found on PATH — install Node.js" >&2; return 1; }
  node "$_cli_path" release --memo "$memo_path" # verify-no-console-flash: allow — node has no windowless equivalent (no nodew.exe); shell-level suppression unavailable per spawn-hidden.sh § Node on Windows. Once-per-memo-transition, not a hot loop — same allow-mark rationale as stamp_shipped_in above. # Review: code-reviewer slice-B F3 — cs_release_memo_revert can fire N times per session (multiple memos); "pickup" was inaccurate.
}

# cs_supersede_handoff <handoff_path>
#
# Supersede terminal transition: atomically sets status: consumed + deployment_state:
# abandoned on the given handoff, via bin/handoff-transition.js supersede (a Bash-driven
# node write — invisible to the Edit-only consumed-handoff freeze hook, so the freeze hook
# does not block this write while manual Edit appends stay blocked).
#
# Called by coordinator-handoff-archive.sh --supersede AFTER stamp_shipped_in + git mv.
# The handoff is already at its archive path when this function runs. No consumed_at or
# consumed_by are written — supersession does not create a pickup claim; provenance lives
# in the body links per handoff/SKILL.md § Step 1 park-with-links.
#
# Exit non-zero on failure (fail-loud contract): an un-mutated supersede leaves
# status:active in the archive, which misleads query-records and the orphan sweep.
# Callers should surface the non-zero exit as a warning (see coordinator-handoff-archive.sh).
#
# Spec backlink: docs/plans/2026-06-30-session-terminator-mechanism-unification.md § C3b
# Review: code-reviewer A-F3 — moved to after cs_release_memo_revert so each function's
# docstring is adjacent to its body (was previously interleaved between revert docstring and body).
cs_supersede_handoff() {
  local handoff_path="$1"
  if [ -z "$handoff_path" ]; then
    echo "cs_supersede_handoff: usage: cs_supersede_handoff <handoff_path>" >&2
    return 2
  fi
  # Resolve lib dir; fall back to the ~/.claude install path when BASH_SOURCE is empty.
  local _doe_root
  _doe_root="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
  if [ -z "$_doe_root" ] || [ ! -d "$_doe_root/coordinator" ]; then echo "ERROR: ~/.claude/.doe-root missing/invalid — re-run coordinator:install" >&2; return 1 2>/dev/null || exit 1; fi
  # Review: code-reviewer P1 — trusted BASH_SOURCE candidate resolved and probed FIRST;
  # CLAUDE_PLUGIN_ROOT-derived candidate is only computed (and guarded, once) when the
  # trusted sibling is absent. Previously the untrusted candidate was guarded FIRST with
  # --mode=fail-loud, hard-exiting before the trusted fallback ever ran — a hard DoS on
  # this lifecycle function under any untrusted CLAUDE_PLUGIN_ROOT.
  local _self_dir
  if [[ -n "${BASH_SOURCE[0]:-}" ]] && [[ -f "$(dirname "${BASH_SOURCE[0]}")/coordinator-session.sh" ]]; then
    _self_dir="$(dirname "${BASH_SOURCE[0]}")"
  else
    _self_dir="${CLAUDE_PLUGIN_ROOT:-$_doe_root/coordinator}/lib"
    # shellcheck source=/dev/null
    source "$(dirname "${BASH_SOURCE[0]}")/coordinator-trusted-root-guard.sh"
    coordinator_trusted_root_guard --mode=fail-loud --root="$_self_dir" --site="$0"
  fi
  # DR-210 facade router (strang-07 C6): lazy-source the facade helper once per process.
  # Cold-fallback (_doe_root) resolved via direct file read above — NEVER 'machine-local get'.
  if ! command -v strangle_route >/dev/null 2>&1; then
    # shellcheck source=/dev/null
    source "${_self_dir}/strangler-facade.sh"
  fi
  local _cli_path
  _cli_path="$(_cc_normalize_dotdot "${_self_dir}/../bin/handoff-transition.js")"
  if [[ ! -f "$_cli_path" ]]; then
    _cli_path="${CLAUDE_PLUGIN_ROOT:-$_doe_root/coordinator}/bin/handoff-transition.js"
    # shellcheck source=/dev/null
    source "$(dirname "${BASH_SOURCE[0]}")/coordinator-trusted-root-guard.sh"
    coordinator_trusted_root_guard --mode=fail-loud --root="$_cli_path" --site="$0"
  fi
  # node check moved inside legacy_supersede; on native path (State 2/3) node is not required.
  # legacy_supersede captures the original node invocation verbatim (State-1 cold-fallback only).
  legacy_supersede() {
    command -v node >/dev/null 2>&1 || { echo "cs_supersede_handoff: node not found on PATH — install Node.js" >&2; return 1; }
    node "$_cli_path" supersede --handoff "$handoff_path" # verify-no-console-flash: allow — node has no windowless equivalent (no nodew.exe); shell-level suppression unavailable per spawn-hidden.sh § Node on Windows. Once-per-supersede-archival, not a hot loop — same allow-mark rationale as stamp_shipped_in above.
  }
  local _supersede_params
  _supersede_params="$(jq -cn \
    --arg verb "supersede" \
    --arg handoff_path "$handoff_path" \
    '{verb: $verb, handoff_path: $handoff_path}')"
  strangle_route_mutation "handoff.transition" "legacy_supersede" "$_supersede_params"
}

# cs_stamp_plan_implemented <plan_path>
#
# Plan-lifecycle stamp: flips a plan's frontmatter status: to implemented via
# bin/plan-status-transition.js stamp-implemented (a Bash-driven node write —
# same "invisible to Edit-only hook" rationale as the handoff/memo transitions
# above). Resolves the coordinator root the same way cs_consume_handoff does.
#
# SIMPLER than cs_consume_handoff: single-field flip with no session-id
# resolution, no timestamp, and no strangler-facade route — delegates entirely
# to the C1 CLI's own status-matrix guard (draft/reviewed/approved/executing
# flip; implemented/superseded/abandoned/deferred no-op).
#
# Exit codes: surfaces the CLI's own exit code verbatim (0 on flip or
# respected no-op; non-zero on bad args/missing file/missing frontmatter).
#
# Spec backlink: docs/plans referenced by the dispatching chunk (C2).
cs_stamp_plan_implemented() {
  local plan_path="$1"
  if [ -z "$plan_path" ]; then
    echo "cs_stamp_plan_implemented: usage: cs_stamp_plan_implemented <plan_path>" >&2
    return 2
  fi
  local _doe_root
  _doe_root="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
  if [ -z "$_doe_root" ] || [ ! -d "$_doe_root/coordinator" ]; then echo "ERROR: ~/.claude/.doe-root missing/invalid — re-run coordinator:install" >&2; return 1 2>/dev/null || exit 1; fi
  # Review: code-reviewer P1 — trusted BASH_SOURCE candidate resolved and probed FIRST;
  # CLAUDE_PLUGIN_ROOT-derived candidate is only computed (and guarded, once) when the
  # trusted sibling is absent. Previously the untrusted candidate was guarded FIRST with
  # --mode=fail-loud, hard-exiting before the trusted fallback ever ran — a hard DoS on
  # this lifecycle function under any untrusted CLAUDE_PLUGIN_ROOT.
  local _self_dir
  if [[ -n "${BASH_SOURCE[0]:-}" ]] && [[ -f "$(dirname "${BASH_SOURCE[0]}")/coordinator-session.sh" ]]; then
    _self_dir="$(dirname "${BASH_SOURCE[0]}")"
  else
    _self_dir="${CLAUDE_PLUGIN_ROOT:-$_doe_root/coordinator}/lib"
    # shellcheck source=/dev/null
    source "$(dirname "${BASH_SOURCE[0]}")/coordinator-trusted-root-guard.sh"
    coordinator_trusted_root_guard --mode=fail-loud --root="$_self_dir" --site="$0"
  fi
  local _cli_path
  _cli_path="$(_cc_normalize_dotdot "${_self_dir}/../bin/plan-status-transition.js")"
  if [[ ! -f "$_cli_path" ]]; then
    _cli_path="${CLAUDE_PLUGIN_ROOT:-$_doe_root/coordinator}/bin/plan-status-transition.js"
    # shellcheck source=/dev/null
    source "$(dirname "${BASH_SOURCE[0]}")/coordinator-trusted-root-guard.sh"
    coordinator_trusted_root_guard --mode=fail-loud --root="$_cli_path" --site="$0"
  fi
  command -v node >/dev/null 2>&1 || { echo "cs_stamp_plan_implemented: node not found on PATH — install Node.js" >&2; return 1; }
  node "$_cli_path" stamp-implemented --plan "$plan_path" # verify-no-console-flash: allow — node has no windowless equivalent (no nodew.exe); shell-level suppression unavailable per spawn-hidden.sh § Node on Windows. Once-per-plan-completion, not a hot loop — same allow-mark rationale as stamp_shipped_in above.
}
