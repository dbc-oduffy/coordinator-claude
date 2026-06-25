#!/usr/bin/env bash
# handoff-transition.bats — plain-bash harness for bin/handoff-transition.js (consume verb)
# and the cs_consume_handoff wrapper in lib/coordinator-archive-stamp.sh.
#
# Purpose: prove the consume lifecycle transition (status→consumed, deployment_state→in_flight,
# +consumed_at/consumed_by) is atomic, idempotent at the full target state, fail-loud on an empty
# session id, and that a Bash-driven helper write bypasses the consumed-handoff freeze hook while a
# manual Edit-tool append to a consumed handoff is STILL denied (the guard the bypass must not weaken).
#
# NOTE: bats-framework is not assumed in the acceptance-oracle environment. Per the oracle's
# `bats:` semantics (= run the file under plain `bash`; see check-acceptance-oracle.sh:808-811) and the
# test_fnm_pin.bats convention, this is a PLAIN-BASH harness — named .bats so the AC grep resolves it.
#
# Spec backlink: docs/plans/2026-06-24-handoff-lifecycle-transition-helper.md § C5 (AC1, AC2, AC3, AC7)
# Run: bash ~/.claude/plugins/coordinator-claude/coordinator/tests/handoff-transition.bats
# Portability (DR-148): bash >= 4 + BSD coreutils; no grep -P / date -d / sed -i.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLI="${SCRIPT_DIR}/../bin/handoff-transition.js"
LIB="${SCRIPT_DIR}/../lib/coordinator-archive-stamp.sh"
HOOK="${SCRIPT_DIR}/../hooks/scripts/block-consumed-handoff-edit.sh"

PASS=0
FAIL=0
FAIL_MSGS=()
pass() { echo "  PASS: $1"; (( PASS++ )) || true; }
fail() { echo "  FAIL: $1"; FAIL_MSGS+=("$1"); (( FAIL++ )) || true; }
run_test() {
    local name="$1" fn="$2"
    echo "--- ${name}"
    if "${fn}"; then pass "${name}"; else fail "${name}"; fi
}

cksum_of() { md5 -q "$1" 2>/dev/null || md5sum "$1" | awk '{print $1}'; }

write_active_handoff() {
    local p="$1"
    {
        printf -- '---\n'
        printf 'title: "Fixture handoff"\n'
        printf 'status: active\n'
        printf 'predecessor: null\n'
        printf 'deployment_state: ready_to_fire\n'
        printf 'pickup_ready: true\n'
        printf -- '---\n'
        printf '\n# Body\nSome work.\n'
    } > "$p"
}

# Fixture: installer-seeded shape — a leading <!-- ... --> provenance comment BEFORE the
# frontmatter (as project_rag_setup / holodeck installers emit). Regression guard for the
# splitFrontmatter line-1 `startsWith('---')` assumption that blocked consume on every
# seeded baton (dogfood finding F6, 2026-06-24).
write_preamble_handoff() {
    local p="$1"
    {
        printf -- '<!-- Seeded into ~/.claude/state/handoffs/ by project_rag_setup.\n'
        printf '     Multi-line provenance comment ahead of the frontmatter.\n'
        printf '     Spec: docs/plans/...-install-spinoff-layer-alignment.md -->\n'
        printf -- '---\n'
        printf 'title: "Seeded fixture"\n'
        printf 'status: active\n'
        printf 'deployment_state: ready_to_fire\n'
        printf 'pickup_ready: true\n'
        printf -- '---\n'
        printf '\n# Body\nSome work.\n'
    } > "$p"
}

# Regression (F6) — consume succeeds on a baton with a leading comment preamble, flips the
# lifecycle keys, AND preserves the provenance comment verbatim (line 1 still the comment).
t_consume_preamble() {
    local d f; d="$(mktemp -d)"; f="$d/h.md"; write_preamble_handoff "$f"
    node "$CLI" consume --handoff "$f" --session-id "sess-pre" --at "2026-06-24T07:00:00Z" >/dev/null 2>&1 || { rm -rf "$d"; return 1; }
    head -1 "$f" | grep -q '^<!-- Seeded into' || { rm -rf "$d"; return 1; }   # preamble preserved
    grep -q '^status: consumed$' "$f"          || { rm -rf "$d"; return 1; }
    grep -q '^deployment_state: in_flight$' "$f" || { rm -rf "$d"; return 1; }
    grep -q '^consumed_by: sess-pre$' "$f"      || { rm -rf "$d"; return 1; }
    [ "$(grep -c '^status:' "$f")" -eq 1 ]      || { rm -rf "$d"; return 1; }   # exactly one status line
    rm -rf "$d"; return 0
}

# AC1 — consume flips all keys atomically; pickup_ready preserved
t_consume_flips() {
    local d f; d="$(mktemp -d)"; f="$d/h.md"; write_active_handoff "$f"
    node "$CLI" consume --handoff "$f" --session-id "sess-1" --at "2026-06-24T07:00:00Z" >/dev/null 2>&1 || { rm -rf "$d"; return 1; }
    grep -q '^status: consumed$' "$f"          || { rm -rf "$d"; return 1; }
    grep -q '^deployment_state: in_flight$' "$f" || { rm -rf "$d"; return 1; }
    grep -q '^consumed_by: sess-1$' "$f"        || { rm -rf "$d"; return 1; }
    grep -q '^consumed_at:' "$f"                || { rm -rf "$d"; return 1; }
    grep -q '^pickup_ready: true$' "$f"         || { rm -rf "$d"; return 1; }
    rm -rf "$d"; return 0
}

# AC7 — exactly one status: line (replaceFmField, not insert)
t_single_status_line() {
    local d f; d="$(mktemp -d)"; f="$d/h.md"; write_active_handoff "$f"
    node "$CLI" consume --handoff "$f" --session-id "sess-1" --at "2026-06-24T07:00:00Z" >/dev/null 2>&1
    local n; n="$(grep -c '^status:' "$f")"
    rm -rf "$d"
    [ "$n" -eq 1 ]
}

# AC1 idempotency — no-op at full target state, no file change
t_idempotent_noop() {
    local d f; d="$(mktemp -d)"; f="$d/h.md"; write_active_handoff "$f"
    node "$CLI" consume --handoff "$f" --session-id "sess-1" --at "2026-06-24T07:00:00Z" >/dev/null 2>&1
    local before after; before="$(cksum_of "$f")"
    # different caller (sess-2/later ts) — must STILL be a no-op; consumed_by/consumed_at must not be clobbered
    node "$CLI" consume --handoff "$f" --session-id "sess-2" --at "2026-06-24T08:00:00Z" >/dev/null 2>&1 || { rm -rf "$d"; return 1; }
    after="$(cksum_of "$f")"; rm -rf "$d"
    [ "$before" = "$after" ]
}

# AC1 partial re-entry — consumed but not in_flight completes; consumed_by preserved
t_partial_reentry() {
    local d f; d="$(mktemp -d)"; f="$d/h.md"
    { printf -- '---\ntitle: "T"\nstatus: consumed\ndeployment_state: ready_to_fire\nconsumed_at: 2026-06-24T06:00:00Z\nconsumed_by: prior-sess\n---\nbody\n'; } > "$f"
    node "$CLI" consume --handoff "$f" --session-id "new-sess" --at "2026-06-24T07:00:00Z" >/dev/null 2>&1 || { rm -rf "$d"; return 1; }
    grep -q '^deployment_state: in_flight$' "$f" || { rm -rf "$d"; return 1; }
    grep -q '^consumed_by: prior-sess$' "$f"     || { rm -rf "$d"; return 1; }   # not clobbered
    rm -rf "$d"; return 0
}

# AC3 — wrapper Bash write succeeds with no override env; consumed_by from CLAUDE_CODE_SESSION_ID
t_wrapper_env_sid() {
    local d f; d="$(mktemp -d)"; f="$d/h.md"; write_active_handoff "$f"
    ( unset COORDINATOR_OVERRIDE_CONSUMED_HANDOFF_EDIT
      export CLAUDE_CODE_SESSION_ID="env-sess-7"
      # shellcheck source=/dev/null
      source "$LIB"
      cs_consume_handoff "$f" >/dev/null 2>&1 ) || { rm -rf "$d"; return 1; }
    grep -q '^status: consumed$' "$f"        || { rm -rf "$d"; return 1; }
    grep -q '^consumed_by: env-sess-7$' "$f" || { rm -rf "$d"; return 1; }
    rm -rf "$d"; return 0
}

# Fail-loud — CLI rejects empty --session-id with non-zero exit and no write
t_cli_empty_sid_no_write() {
    local d f before after; d="$(mktemp -d)"; f="$d/h.md"; write_active_handoff "$f"
    before="$(cksum_of "$f")"
    if node "$CLI" consume --handoff "$f" --session-id "" --at "2026-06-24T07:00:00Z" >/dev/null 2>&1; then
        rm -rf "$d"; return 1   # should have failed
    fi
    after="$(cksum_of "$f")"; rm -rf "$d"
    [ "$before" = "$after" ]
}

# Fail-loud — wrapper fails when no session id is resolvable (non-git cwd, env unset)
# NOTE: relies on 3-env-unset + non-git cwd as a proxy for an empty sid result from _cs_resolve_session_id.
# Update this proxy if _cs_resolve_session_id gains a new resolution tier above the .git sentinel.
t_wrapper_unresolvable_sid() {
    local d f before after; d="$(mktemp -d)"; f="$d/h.md"; write_active_handoff "$f"
    before="$(cksum_of "$f")"
    if ( unset CLAUDE_CODE_SESSION_ID COORDINATOR_SESSION_ID CLAUDE_SESSION_ID
         # shellcheck source=/dev/null
         source "$LIB"
         cd "$d"          # non-git dir → _cs_git_root fails → empty sid
         cs_consume_handoff "$f" >/dev/null 2>&1 ); then
        rm -rf "$d"; return 1   # should have failed
    fi
    after="$(cksum_of "$f")"; rm -rf "$d"
    [ "$before" = "$after" ]
}

# AC2 — freeze hook still DENIES a manual Edit tool_input on a status: consumed handoff
t_hook_denies_consumed() {
    local d f out; d="$(mktemp -d)"; mkdir -p "$d/state/handoffs"; f="$d/state/handoffs/x.md"
    { printf -- '---\nstatus: consumed\ndeployment_state: in_flight\n---\nbody\n'; } > "$f"
    out="$(printf '{"tool_name":"Edit","tool_input":{"file_path":"%s"}}' "$f" | bash "$HOOK" 2>/dev/null)"
    rm -rf "$d"
    [[ "$out" == *'"permissionDecision":"deny"'* ]]
}

# AC2 control — freeze hook ALLOWS an Edit on a status: active handoff
# Allow path exits 0 with no output; capture rc to distinguish silent crash from deliberate allow.
t_hook_allows_active() {
    local d f out rc; d="$(mktemp -d)"; mkdir -p "$d/state/handoffs"; f="$d/state/handoffs/a.md"
    write_active_handoff "$f"
    out="$(printf '{"tool_name":"Edit","tool_input":{"file_path":"%s"}}' "$f" | bash "$HOOK" 2>/dev/null)"; rc=$?
    rm -rf "$d"
    [[ $rc -eq 0 && "$out" != *deny* ]]
}

# End-to-end: cs_consume_handoff → hook DENIES a subsequent manual Edit on the same (now-consumed) file
t_hook_denies_after_consume() {
    local d f out; d="$(mktemp -d)"; mkdir -p "$d/state/handoffs"; f="$d/state/handoffs/e2e.md"
    write_active_handoff "$f"
    # Consume the handoff via the wrapper (env sid, no override)
    ( unset COORDINATOR_OVERRIDE_CONSUMED_HANDOFF_EDIT
      export CLAUDE_CODE_SESSION_ID="e2e-sess-1"
      # shellcheck source=/dev/null
      source "$LIB"
      cs_consume_handoff "$f" >/dev/null 2>&1 ) || { rm -rf "$d"; return 1; }
    # Now pipe an Edit tool_input JSON for the now-consumed file to the hook — must be denied
    out="$(printf '{"tool_name":"Edit","tool_input":{"file_path":"%s"}}' "$f" | bash "$HOOK" 2>/dev/null)"
    rm -rf "$d"
    [[ "$out" == *'"permissionDecision":"deny"'* ]]
}

echo "=== handoff-transition plain-bash harness ==="
run_test "consume flips status/deployment_state + inserts consumed_at/by atomically" t_consume_flips
run_test "consume succeeds on leading-comment baton, preserves preamble (F6 regression)" t_consume_preamble
run_test "consume produces exactly one status: line (replaceFmField)"                t_single_status_line
run_test "idempotent no-op at full target state (no file change)"                    t_idempotent_noop
run_test "partial re-entry completes deployment_state, preserves consumed_by"         t_partial_reentry
run_test "cs_consume_handoff Bash write succeeds with no override env"                t_wrapper_env_sid
run_test "CLI rejects empty --session-id (non-zero, no write)"                        t_cli_empty_sid_no_write
run_test "wrapper fails loud on unresolvable session id (non-zero, no write)"         t_wrapper_unresolvable_sid
run_test "freeze hook DENIES manual Edit on a status: consumed handoff"               t_hook_denies_consumed
run_test "freeze hook ALLOWS Edit on a status: active handoff (control)"              t_hook_allows_active
run_test "end-to-end: cs_consume_handoff then hook DENIES a manual Edit on consumed"  t_hook_denies_after_consume

echo "=== PASS=${PASS} FAIL=${FAIL} ==="
if [ "${FAIL}" -ne 0 ]; then
    printf 'FAILED: %s\n' "${FAIL_MSGS[@]}"
    exit 1
fi
exit 0
