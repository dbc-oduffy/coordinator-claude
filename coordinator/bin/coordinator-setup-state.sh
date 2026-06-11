#!/usr/bin/env bash
# bin/coordinator-setup-state.sh — single writer/reader primitive for the coordinator
# setup/orientation milestone receipt at ~/.claude/coordinator-setup-state.yaml.
#
# Purpose: durable, per-machine evidence that coordinator setup concluded and (optionally)
# that the operator started/completed the guided orientation. This is a RECEIPT in the
# sense of docs/wiki/plugin-identity-and-health-sentinels.md — written by the actor whose
# action it witnesses, stale = signal not lie. It is the cross-repo chaining contract:
# sibling (branch/leaf) repos read it to confirm coordinator is bootstrapped before
# chaining their own setup/orientation after it.
#
# Idempotent and enduring: each milestone timestamp is set ONCE (first occurrence wins)
# and never overwritten on re-run, so re-running /setup or re-taking the tour does not
# rewrite history.
#
# Spec backlink: docs/wiki/coordinator-setup-state-receipt.md
#
# Usage:
#   coordinator-setup-state.sh record <milestone>   # set <milestone>_at if unset (atomic)
#   coordinator-setup-state.sh check  <milestone>    # exit 0 if recorded, 1 if not
#   coordinator-setup-state.sh status                # print the receipt (or note absence)
#   coordinator-setup-state.sh auto-record-if-source-is-live
#                                                    # silent self-heal: on machines where
#                                                    # coordinator-claude is registered as
#                                                    # propagation_mode="source_is_live"
#                                                    # (the install IS the source — the
#                                                    # operator is the author, never ran
#                                                    # /coordinator:install), record
#                                                    # setup_concluded implicitly. No-op
#                                                    # otherwise and on every subsequent
#                                                    # call (record is first-write-wins).
#                                                    # Always exits 0; emits nothing.
#
#   milestone ∈ { setup_concluded | orientation_started | orientation_completed }
#
# Environment: CLAUDE_HOME (defaults to $HOME/.claude) selects the install root.

set -uo pipefail

is_milestone() {
    case "$1" in
        setup_concluded|orientation_started|orientation_completed) return 0 ;;
        *) return 1 ;;
    esac
}

usage() {
    cat >&2 <<'EOF'
Usage:
  coordinator-setup-state.sh record <milestone>
  coordinator-setup-state.sh check  <milestone>
  coordinator-setup-state.sh status

  milestone ∈ { setup_concluded | orientation_started | orientation_completed }
EOF
    exit 2
}

CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude}"
STATE_FILE="$CLAUDE_HOME/coordinator-setup-state.yaml"

CMD="${1:-}"
[[ -n "$CMD" ]] || usage

# A value is "recorded" when the key exists with a non-empty, non-comment value.
# `key` is interpolated into a regex; refuse anything but a fixed identifier so a
# future caller passing an unvalidated key can't inject regex metacharacters.
key_recorded() {
    local key="$1"
    [[ "$key" =~ ^[a-z_]+$ ]] || return 1
    [[ -f "$STATE_FILE" ]] || return 1
    grep -qE "^${key}:[[:space:]]+[^[:space:]#]" "$STATE_FILE"
}

seed_file_if_absent() {
    [[ -f "$STATE_FILE" ]] && return 0
    local tmp
    tmp="$(mktemp "${STATE_FILE}.XXXXXX")" || { echo "coordinator-setup-state: mktemp failed (seed)" >&2; exit 1; }
    cat > "$tmp" <<'EOF'
# ~/.claude/coordinator-setup-state.yaml — coordinator setup/orientation receipt.
# Operator-local, per-machine, gitignored, NEVER a publish target.
#
# Cross-repo contract: sibling (branch/leaf) repos read this file to confirm coordinator
# setup concluded before chaining their own setup/orientation after it. The presence of
# a non-empty `setup_concluded_at` is the chaining gate.
#
# Schema + reader idiom: docs/wiki/coordinator-setup-state-receipt.md
# Each *_at timestamp is set once (first occurrence wins) and never overwritten.
version: 1
EOF
    mv "$tmp" "$STATE_FILE"
}

case "$CMD" in
    record)
        MILESTONE="${2:-}"
        is_milestone "$MILESTONE" || usage
        KEY="${MILESTONE}_at"
        seed_file_if_absent

        # Portable advisory lock so first-occurrence-wins holds under concurrent
        # writers (two /setup runs, or /setup + orientation racing). mkdir is
        # atomic on POSIX and Git-Bash; flock is not available on stock Git-Bash
        # or macOS. Best-effort: if we can't acquire within ~5s, proceed anyway —
        # the worst case is the benign pre-lock race (a valid, slightly-later
        # timestamp). The EXIT trap releases on every exit path below.
        lockdir="${STATE_FILE}.lock"
        for _ in {1..25}; do
            if mkdir "$lockdir" 2>/dev/null; then
                trap 'rmdir "$lockdir" 2>/dev/null || true' EXIT
                break
            fi
            sleep 0.2
        done

        if key_recorded "$KEY"; then
            echo "${KEY} already recorded; leaving unchanged."
            exit 0
        fi
        NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        tmp="$(mktemp "${STATE_FILE}.XXXXXX")" || { echo "coordinator-setup-state: mktemp failed (record)" >&2; exit 1; }
        if grep -qE "^${KEY}:" "$STATE_FILE"; then
            # Key present but empty — fill it in place.
            sed "s|^${KEY}:.*|${KEY}: ${NOW}|" "$STATE_FILE" > "$tmp"
        else
            cat "$STATE_FILE" > "$tmp"
            printf '%s: %s\n' "$KEY" "$NOW" >> "$tmp"
        fi
        mv "$tmp" "$STATE_FILE"
        echo "Recorded ${KEY}: ${NOW} in ${STATE_FILE}"
        ;;
    check)
        MILESTONE="${2:-}"
        is_milestone "$MILESTONE" || usage
        if key_recorded "${MILESTONE}_at"; then
            exit 0
        fi
        exit 1
        ;;
    status)
        if [[ -f "$STATE_FILE" ]]; then
            cat "$STATE_FILE"
            # Header-only file (seeded but no milestone recorded — e.g. a crash
            # between seed and write) is semantically "not concluded": exit
            # non-zero so a gating reader does not mistake existence for conclusion.
            grep -qE "^[a-z_]+_at:[[:space:]]+[^[:space:]#]" "$STATE_FILE" || exit 1
        else
            echo "No coordinator setup-state receipt at ${STATE_FILE} (setup not concluded on this machine)."
            exit 1
        fi
        ;;
    auto-record-if-source-is-live)
        # Silent self-heal for source_is_live machines (coordinator-claude
        # installed over ~/.claude/ — operator is the author, never runs
        # /coordinator:install, so the receipt never gets written by the normal
        # path). Detect via registry, record setup_concluded, exit 0 silently.
        # No-op if receipt already present (record is first-write-wins).
        registry="${CLAUDE_HOME}/machine-local/registry.local.toml"
        [[ -f "$registry" ]] || exit 0
        # Look for [plugin.mirrors.coordinator-claude] table followed within a
        # short window by propagation_mode = "source_is_live". awk so we don't
        # cross-match a different plugin's prop_mode.
        awk '
            /^\[plugin\.mirrors\.coordinator-claude\]/ { in_block=1; next }
            /^\[/ { in_block=0 }
            in_block && /^propagation_mode[[:space:]]*=[[:space:]]*"source_is_live"/ { found=1; exit }
            END { exit (found ? 0 : 1) }
        ' "$registry" || exit 0
        # Fire the same record path used by /coordinator:install. Suppress
        # stdout/stderr — this is a silent self-heal.
        "$0" record setup_concluded >/dev/null 2>&1 || true
        exit 0
        ;;
    --help|-h)
        usage
        ;;
    *)
        usage
        ;;
esac
