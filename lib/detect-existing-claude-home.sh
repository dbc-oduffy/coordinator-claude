#!/usr/bin/env bash
# lib/detect-existing-claude-home.sh — three-state classifier for Claude home directories.
#
# Purpose: tell install logic which of THREE postures a candidate Claude home is in,
# so it can choose the right path and the right message:
#
#   pristine      Claude Code has never run here — no artifacts at all.
#                 Track A. Install from zero, no caveats.
#   used-vanilla  Claude Code HAS run, but nothing opinionated was set up
#                 (no git, no installed plugins, no coordinator infra — just
#                 session history, CC plugin scaffolding, and/or a hand-edited
#                 CLAUDE.md). Track A. Install from effectively zero; acknowledge
#                 prior casual use, but do NOT warn about a setup being overwritten.
#   configured    An opinionated, deliberately-customized home (git-tracked,
#                 installed plugins, or coordinator infrastructure — "a setup
#                 like ours"). Track B. The only tier where the "merge is yours /
#                 your setup may collide" caution is warranted.
#
# WHY THREE, NOT TWO: the old binary Track A/B collapsed "casually used" into
# "existing setup", so a machine that had merely launched Claude Code once (which
# leaves plugins/ scaffolding + session dirs) drew the same "your existing setup
# may be overwritten" warning as a fully git-tracked, plugin-laden home. Those are
# different install postures and deserve different messages.
#
# FILE-LEVEL SAFETY IS TIER-INDEPENDENT. The tier drives posture and messaging
# only. Idempotency guards (never clobber CLAUDE.md, settings.json, registry
# files) MUST hold in every tier — including used-vanilla, where a hand-edited
# CLAUDE.md exists but does not lift the home to "configured".
#
# Spec backlink: chunk C7 — Track A/B detection helper (P8); three-state extension.
#
# Decision tiers (first match wins, most-structural first):
#   configured   — C1 git-tracked | C2 installed plugin | C3 coordinator infra
#   used-vanilla — U1 CLAUDE.md (any size) | U2 session/runtime artifacts | U3 CC scaffolding
#   pristine     — none of the above
#
# Usage:
#   bash detect-existing-claude-home.sh [<target-dir>]
#   CLAUDE_CONFIG_DIR=<dir> bash detect-existing-claude-home.sh
#
# Output (stdout): one line of the form:
#   state=<pristine|used-vanilla|configured> track=<A|B> reason: <human explanation>
# track= is retained for backward-compat with callers that branch on the binary
# fork (configured → B, else → A); new callers should branch on state=.
#
# Exit codes:
#   0 — always (classification result is in stdout, not exit code)
#
# Read-only contract: this script MUST NOT create, modify, or delete anything
# in the target directory.  Idempotent: identical output on repeated runs.

set -euo pipefail

# ---------------------------------------------------------------------------
# Resolve target directory
# ---------------------------------------------------------------------------
# Priority: $1 (explicit arg) > $CLAUDE_CONFIG_DIR > $HOME/.claude
_resolve_target() {
    if [[ -n "${1:-}" ]]; then
        echo "$1"
    elif [[ -n "${CLAUDE_CONFIG_DIR:-}" ]]; then
        echo "$CLAUDE_CONFIG_DIR"
    else
        echo "${HOME}/.claude"
    fi
}

TARGET="$(_resolve_target "${1:-}")"

# ---------------------------------------------------------------------------
# Output helper — every exit goes through here.
# ---------------------------------------------------------------------------
# Format: `state=<tier> track=<A|B> reason: <text>`
#   state= is the load-bearing signal (three tiers, below).
#   track= is a backward-compat binary fork for older callers:
#          configured → B, {used-vanilla, pristine} → A.
emit() { echo "state=$1 track=$2 reason: $3"; exit 0; }

# ===========================================================================
# Helper predicates (shared by the configured / used-vanilla tiers)
# ===========================================================================

# Claude-Code-managed basenames present on a fresh, zero-history install.
# A vanilla Claude home is NOT empty: modern Claude Code bootstraps plugins/
# with its own scaffolding on first run, BEFORE the user installs anything
# (installed_plugins.json, known_marketplaces.json, blocklist.json,
# plugin-catalog-cache.json, config.json, and the cache/ marketplaces/ repos/
# data/ dirs). None of these are user-installed plugins, so they must NOT lift
# a home to the "configured" tier.
_is_cc_managed_entry() {
    case "$1" in
        .*)                     return 0 ;;  # dotfiles: .refresh-log, .last_inuse_sweep, …
        *.bak | *.bak-*)        return 0 ;;  # backup copies (installed_plugins.json.bak-*)
        config.json | installed_plugins.json | known_marketplaces.json) return 0 ;;
        blocklist.json | plugin-catalog-cache.json) return 0 ;;
        repos | marketplaces | cache | data) return 0 ;;
        *)                      return 1 ;;
    esac
}

# Claude Code's own source of truth. A fresh install has "plugins": {} — an
# empty map. Whitespace-stripping makes the check robust to both pretty and
# compact JSON without a jq/python dependency; the case statement reasons by
# PRESENCE (explicit empty-map branch) rather than absence, and avoids a
# `tr | grep` pipeline so the predicate is safe to call bare under `set -e`.
_installed_plugins_json_nonempty() {
    local f="${TARGET}/plugins/installed_plugins.json" stripped
    [[ -f "$f" ]] || return 1
    stripped="$(tr -d '[:space:]' < "$f" 2>/dev/null)" || return 1
    case "$stripped" in
        *'"plugins":{}'*) return 1 ;;  # explicit empty map → no installed plugins
        *'"plugins":{'*)  return 0 ;;  # plugins object carries at least one entry
        *)                return 1 ;;  # no plugins key at all (malformed/foreign file)
    esac
}

# A genuine user-installed plugin under plugins/, distinguished from CC's own
# scaffolding via the deny-list above. Catches non-standard layouts (e.g. a
# live-install checkout that drops plugin dirs directly under plugins/).
_has_installed_plugin() {
    local plugins_dir="${TARGET}/plugins"
    [[ -d "$plugins_dir" ]] || return 1
    local entry base
    while IFS= read -r -d '' entry; do
        base="$(basename "$entry")"
        # `&& continue` guards the return-1 (not-managed) path against `set -e`:
        # the compound's status is `continue`'s, never _is_cc_managed_entry's.
        _is_cc_managed_entry "$base" && continue
        if [[ -f "$entry" ]]; then
            return 0
        elif [[ -d "$entry" ]]; then
            # `ls -A` (BSD + GNU portable, no `-quit` GNU-ism, no head/SIGPIPE)
            # tests whether the subdir has any child.
            if [[ -n "$(ls -A "$entry" 2>/dev/null)" ]]; then
                return 0
            fi
        fi
    done < <(find "$plugins_dir" -maxdepth 1 -mindepth 1 -print0 2>/dev/null)
    return 1
}

# Is plugins/ present with anything at all inside (even if only CC scaffolding)?
# Evidence that Claude Code has run here — a used-vanilla signal, not configured.
# `ls -A` lists all entries except . and .. (dotfiles included) — portable across
# BSD (macOS) and GNU, no `find -quit` dependency.
_plugins_dir_nonempty() {
    local plugins_dir="${TARGET}/plugins"
    [[ -d "$plugins_dir" ]] || return 1
    [[ -n "$(ls -A "$plugins_dir" 2>/dev/null)" ]]
}

# ===========================================================================
# Tier 1 — CONFIGURED (Track B): an opinionated, deliberately-customized home.
# ===========================================================================
# The ONLY tier where the "merge is yours / your setup may collide" caution is
# warranted. Signals are structural intent, not mere prior use.
#
# NOTE — file-level safety is tier-independent. The tier drives posture and
# messaging only. Idempotency guards (never clobber CLAUDE.md, settings.json,
# registry files) MUST hold in every tier, including used-vanilla.

# C1: git-tracked — deliberate version control of ~/.claude. `-e` covers both
# the .git dir (repo root) and .git file (worktree/submodule). TARGET itself,
# not an ancestor, so a ~/.claude under a git-tracked $HOME is not a false hit.
if [[ -e "$TARGET/.git" ]]; then
    emit configured B "${TARGET} is git-tracked (deliberate version control)"
fi

# C2: a real installed plugin (CC's own record, or a non-scaffolding entry).
if _installed_plugins_json_nonempty; then
    emit configured B "${TARGET}/plugins/installed_plugins.json records installed plugin(s)"
fi
if _has_installed_plugin; then
    emit configured B "${TARGET}/plugins/ contains a non-Claude-Code-managed plugin entry"
fi

# C3: coordinator / opinionated infrastructure — the "a setup like ours"
# fingerprint. Claude Code never creates any of these; their presence means a
# human (or the coordinator installer) deliberately structured this home.
# `_c3_marker` is a top-level (global-scope) iteration variable — there is no
# enclosing function to scope it `local`; it is clobbered before each use.
for _c3_marker in state machine-local coordinator.local.md plugins/coordinator-claude; do
    if [[ -e "$TARGET/$_c3_marker" ]]; then
        emit configured B "${TARGET}/${_c3_marker} present (coordinator/opinionated infrastructure)"
    fi
done

# ===========================================================================
# Tier 2 — USED-VANILLA (Track A): Claude Code has run here, but nothing
# opinionated was set up. Install proceeds from effectively zero; the message
# acknowledges prior casual use without a clobber warning.
# ===========================================================================

# U1: a CLAUDE.md of any size. Casual hand-edits live in this tier by design —
# a hand-tuned CLAUDE.md alone does NOT make a home "configured" (per the
# taxonomy: "not git-tracked, only has changes in CLAUDE.md and past sessions").
# Edge case (intentional): a CLAUDE.md carrying the coordinator `@import` line
# but with NO git/plugins/infra still classifies used-vanilla — the import alone
# is not opinionated *structure*. Reaching configured requires a C-tier signal.
if [[ -f "$TARGET/CLAUDE.md" ]]; then
    emit used-vanilla A "${TARGET}/CLAUDE.md present (hand-edited config, no structural setup)"
fi

# U2: session / runtime artifacts a prior Claude Code run leaves behind.
# `_u2_artifact` is a top-level (global-scope) iteration variable (see C3 note).
for _u2_artifact in projects sessions todos shell-snapshots ide file-history statsig history.jsonl settings.json; do
    if [[ -e "$TARGET/$_u2_artifact" ]]; then
        emit used-vanilla A "${TARGET}/${_u2_artifact} present (Claude Code has run here)"
    fi
done

# U3: CC plugin scaffolding present but holding no real plugin (the fresh-run
# case that previously false-positived into Track B).
if _plugins_dir_nonempty; then
    emit used-vanilla A "${TARGET}/plugins/ holds Claude-Code-managed scaffolding only"
fi

# ===========================================================================
# Tier 3 — PRISTINE (Track A): no Claude Code artifacts at all. Never used.
# ===========================================================================
emit pristine A "${TARGET} has no Claude Code artifacts — never used"
