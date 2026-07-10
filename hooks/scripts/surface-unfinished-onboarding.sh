#!/usr/bin/env bash
# hooks/scripts/surface-unfinished-onboarding.sh — SessionStart (startup) hook.
#
# Purpose: P2 guided post-restart self-onboarding. `/coordinator:install` restarts
# Claude Code partway through the install/onboarding chain; if the operator closes
# the terminal (or simply doesn't continue) before running the guided orientation
# tour, the invitation is lost with no durable nudge on the NEXT session. This hook
# is the post-hoc half of that fix (the in-flow half — the Phase 7 terminal-banner
# gate — is C8). Together they close F13(a)/(d): tasks/2026-07-08-install-dogfood-friction.md.
#
# Detection (the Director of Engineering review, item 1 — re-gated on the orientation receipt, NOT
# install-status.json completeness): `coordinator-setup-state.sh check
# orientation_completed` (non-zero = not yet oriented). install-status.json
# self-extinguishes at install-complete — BEFORE orientation — so gating on it
# reproduces the exact done/oriented decoupling F13 root-cause #2 names. This
# hook MAY additionally consult the install-status.json receipt (schema:
# coordinator-installer-status-schema.md) to distinguish "never installed" from
# "installed, not oriented" for message wording, but that receipt never gates
# the self-extinguish condition.
#
# Mode A (recommended, implemented here): guarded seed. If orientation is not
# recorded, render `continue-onboarding-and-installation.md` into
# `$(coordinator-settings-home)/state/handoffs/` — ONLY IF ABSENT (never clobber
# an already-seeded or already-consumed baton per
# docs/wiki/spinoff-handoffs.md § Install Seed Loop) — then surface ONE line
# pointing at `/pickup <settings-home path>`.
#
# Fail-safe (hard): a receipt-read failure, a resolver miss, a missing template,
# or any other error must NEVER wedge the session. Every exit path below is 0;
# `main` failures are swallowed and the script falls through to a silent `exit 0`.
#
# Registration-order note (the Director of Engineering review, item 5): `hooks.json:105`-area documents
# that `bootstrap-substrate.sh` is async (up to 120s) and array position does NOT
# sequence it. This hook does not depend on bootstrap-substrate output — it reads
# only receipts written by `/coordinator:install` (install-status.json) and
# `coordinator-setup-state.sh` (setup-state.yaml), neither deployed by
# bootstrap-substrate — so no race exists to account for.
#
# Idempotent: re-firing on an already-oriented machine is a silent no-op
# (self-extinguishing). Re-firing while a baton is already seeded and orientation
# is still incomplete re-surfaces the same one-line nudge without re-seeding.
#
# Spec backlink: docs/plans/2026-07-08-install-baton-rendezvous-off-dotclaude.md § C7, AC12, AC13
# Review: code-reviewer — the "every exit path is 0" fail-safe above depends on
# `set -u`: every function-local variable must be declared (bare `local x`) or
# assigned before its first read, or an unset-variable reference will abort the
# script mid-`main()` before reaching the trailing `exit 0`.
set -uo pipefail

main() {
    local hook_dir plugin_root
    hook_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd 2>/dev/null)" || return 0
    plugin_root="$(cd "${hook_dir}/../.." && pwd 2>/dev/null)" || return 0

    local setup_state_bin="${CLAUDE_PLUGIN_ROOT:-$plugin_root}/bin/coordinator-setup-state.sh"
    # CLAUDE_PLUGIN_ROOT-derived resolve-site — guard before the first execution
    # under it. Variant B / fail-open (advisory hook, must never hard-exit).
    # $plugin_root itself is BASH_SOURCE-relative (trusted-by-construction);
    # the risk is an attacker-controlled CLAUDE_PLUGIN_ROOT override.
    # Spec backlink: docs/plans/2026-07-09-resolver-unification-v3split-01.md § C5
    # shellcheck source=/dev/null
    source "$(dirname "${BASH_SOURCE[0]}")/../../lib/coordinator-trusted-root-guard.sh" 2>/dev/null || true
    if command -v coordinator_trusted_root_guard >/dev/null 2>&1; then
        coordinator_trusted_root_guard --mode=fail-open --root="$setup_state_bin" --site="$0" || setup_state_bin=''
    else
        setup_state_bin=''
    fi
    [[ -f "$setup_state_bin" ]] || return 0

    # Self-extinguish: orientation already recorded → silent no-op.
    if bash "$setup_state_bin" check orientation_completed >/dev/null 2>&1; then
        return 0
    fi

    # Not (yet) recorded — installed-but-not-onboarded (or receipt entirely
    # absent, which is the same "not yet oriented" state for this hook's
    # purposes). Resolve settings-home.
    local settings_home
    settings_home="$(_resolve_settings_home "$plugin_root")" || return 0
    [[ -n "$settings_home" ]] || return 0

    local handoff_dir="${settings_home}/state/handoffs"
    mkdir -p "$handoff_dir" 2>/dev/null || return 0
    [[ -d "$handoff_dir" ]] || return 0

    local dest="${handoff_dir}/continue-onboarding-and-installation.md"

    if [[ ! -f "$dest" ]]; then
        # Guarded seed: only-if-absent. A present file — whatever its lifecycle
        # status — is never clobbered (spinoff-handoffs.md § Install Seed Loop).
        _seed_onboarding_baton "$plugin_root" "$dest" 2>/dev/null || true
    fi

    # Surface ONE line whether we just seeded it or a prior session already did.
    [[ -f "$dest" ]] && printf 'Coordinator install detected — onboarding not yet completed. Run: /pickup %s\n' "$dest"
    return 0
}

# _resolve_settings_home <plugin_root> — print the settings-home root.
# Precedence: COORDINATOR_SETTINGS_HOME override → the plugin-bundled
# `coordinator-settings-home` forwarder → inline fallback (mirrors
# lib/settings-home.sh's own precedence so a resolver-binary miss still
# resolves the same root, not a divergent one).
_resolve_settings_home() {
    local plugin_root="$1"
    if [[ -n "${COORDINATOR_SETTINGS_HOME:-}" ]]; then
        printf '%s' "$COORDINATOR_SETTINGS_HOME"
        return 0
    fi
    local forwarder="${CLAUDE_PLUGIN_ROOT:-$plugin_root}/bin/coordinator-settings-home"
    # CLAUDE_PLUGIN_ROOT-derived resolve-site — guard before executing $forwarder.
    # Variant B / fail-open (advisory hook, must never hard-exit).
    # Spec backlink: docs/plans/2026-07-09-resolver-unification-v3split-01.md § C5
    # shellcheck source=/dev/null
    source "$(dirname "${BASH_SOURCE[0]}")/../../lib/coordinator-trusted-root-guard.sh" 2>/dev/null || true
    if command -v coordinator_trusted_root_guard >/dev/null 2>&1; then
        coordinator_trusted_root_guard --mode=fail-open --root="$forwarder" --site="$0" || forwarder=''
    else
        forwarder=''
    fi
    if [[ -n "$forwarder" && -x "$forwarder" ]]; then
        local out
        out="$(bash "$forwarder" 2>/dev/null)" || out=""
        if [[ -n "$out" ]]; then
            printf '%s' "$out"
            return 0
        fi
    fi
    # Resolver miss (forwarder absent/failed) — inline fallback, same precedence.
    printf '%s' "${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings"
}

# _seed_onboarding_baton <plugin_root> <dest> — render the onboarding template
# into <dest>. Prefers render-template.sh (DATE/BRANCH substitution, matches
# the template's own {{DATE}}/{{BRANCH}} contract); falls back to a raw copy
# if the renderer is unavailable so a missing helper never blocks the seed.
_seed_onboarding_baton() {
    local plugin_root="$1" dest="$2"
    local template="${plugin_root}/templates/handoffs/continue-onboarding-and-installation.md"
    [[ -f "$template" ]] || return 1

    local renderer="${plugin_root}/bin/render-template.sh"
    local today branch
    today="$(date +%Y-%m-%d 2>/dev/null)" || today="unknown"
    branch="$(git -C "${CLAUDE_HOME:-$HOME}/.claude" rev-parse --abbrev-ref HEAD 2>/dev/null)" || branch="main"

    if [[ -x "$renderer" ]]; then
        bash "$renderer" "$template" -o "$dest" "DATE=${today}" "BRANCH=${branch}" >/dev/null 2>&1 && return 0
    fi
    cp "$template" "$dest" 2>/dev/null
}

main
exit 0
