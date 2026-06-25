#!/usr/bin/env bash
# coordinator/lib/setup-rag-decision.sh — RAG-index decision resolver for /repo-setup.
#
# Purpose: resolves the RAG-index decision at repo-setup time via an explicit
# three-branch decision tree. Never writes a dead "offer to index" for a repo that
# cannot be indexed.
#
# Decision branches:
#   1. UE repo + project-rag daemon present  → emit "offer to index" text (caller surfaces it).
#   2. Non-UE repo (any daemon state)        → write tripwire block into target CLAUDE.md.
#   3. UE repo + no daemon present           → write tripwire block into target CLAUDE.md.
#
# Non-UE upstream limitation (branch 2): the "offer to index" branch is currently
# UE-only because an upstream `project-rag-ue-addon` .uproject-abstention defect
# blocks indexing of non-UE repos. This is a known upstream limitation in
# project-rag-ue-addon; widen to non-UE only after that defect is resolved.
#
# Detect-then-fail-loud: if UE-vs-non-UE or daemon-presence cannot be determined
# unambiguously, the script exits non-zero with a remediation message rather than
# silently picking a branch.
#
# Idempotent: re-running does NOT duplicate the tripwire block in CLAUDE.md.
#
# Mockable probe: SETUP_RAG_DAEMON_PROBE can be set to a command string that
# returns exit 0 (daemon present) or non-zero (daemon absent). If unset, the
# default probe checks `project-rag status` on PATH.
#
# Spec backlink: docs/plans/2026-06-23-setup-time-substrate-completeness.md § C1c (AC3)
#
# Usage (standalone):
#   setup-rag-decision.sh [--root <path>] [--dry-run] [--help]
#
# Usage (sourced):
#   source setup-rag-decision.sh
#   setup_rag_decision [--root <path>] [--dry-run]
#
# Flags:
#   --root <path>  Target repo root. Defaults to cwd.
#   --dry-run      Print what would happen; write nothing.
#   --help | -h    Show this help and exit.
#
# Exit codes:
#   0  Decision resolved and action taken (or dry-run completed).
#   1  Usage error or unambiguous-detection failure (fail-loud).
#
# Environment overrides (for tests):
#   SETUP_RAG_TARGET_ROOT    — target repo root path (overrides --root and cwd)
#   SETUP_RAG_DAEMON_PROBE   — command to test daemon presence (exit 0 = present)
#   SETUP_RAG_IS_UE_REPO     — "1" to force UE, "0" to force non-UE (test injection)

set -euo pipefail

# ---------------------------------------------------------------------------
# Bash version guard — fail loud on bash < 4. Uses arithmetic guard which
# is reachable on bash 3.2 (no 4-only syntax before this point).
# ---------------------------------------------------------------------------
if [ "${BASH_VERSINFO[0]:-0}" -lt 4 ]; then
    # Review: code-reviewer — POSIX form required; arithmetic guard not reachable on bash 3.2
    printf 'setup-rag-decision: bash 4+ required (running %s). Install via brew (macOS: brew install bash) then re-run.\n' \
        "${BASH_VERSION:-unknown}" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Tripwire block sentinel — must be unique enough to survive idempotency grep.
# ---------------------------------------------------------------------------

_RAG_TRIPWIRE_SENTINEL="coordinator-rag-tripwire: un-indexed"

_RAG_TRIPWIRE_BLOCK="<!-- ${_RAG_TRIPWIRE_SENTINEL} -->
## RAG Index

**Status: un-indexed; use Tier-3 (Read/Grep/Glob)**

This repo is not indexed by project-rag. Use Tier-3 investigation:
Read known paths, Grep specific symbols, Glob patterns.
Do not assume a semantic search index is available.
<!-- end coordinator-rag-tripwire -->"

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# _srd_is_ue_repo <root> — exit 0 if the root contains a .uproject file (UE repo),
# exit 1 otherwise, exit 2 if detection is ambiguous (multiple or nested .uproject).
_srd_is_ue_repo() {
    local root="${1:?root required}"

    # Honour test injection first.
    if [[ -n "${SETUP_RAG_IS_UE_REPO:-}" ]]; then
        case "$SETUP_RAG_IS_UE_REPO" in
            1) return 0 ;;
            0) return 1 ;;
            *)
                printf 'setup-rag-decision: SETUP_RAG_IS_UE_REPO must be "1" or "0", got: %s\n' \
                    "$SETUP_RAG_IS_UE_REPO" >&2
                return 2
                ;;
        esac
    fi

    # Scan for .uproject files at depth 1 (immediate children of root only — the
    # canonical location for a UE project file). Deeper .uproject files are engine
    # samples or sub-projects and do not make the root a first-class UE consumer.
    local uproject_count=0
    local f
    for f in "${root}"/*.uproject; do
        [[ -f "$f" ]] && uproject_count=$((uproject_count + 1))
    done

    if [[ $uproject_count -eq 0 ]]; then
        return 1
    elif [[ $uproject_count -eq 1 ]]; then
        return 0
    else
        # Multiple .uproject files at root depth — ambiguous; fail loud.
        printf 'setup-rag-decision: ambiguous UE detection: %d .uproject files found at %s\n' \
            "$uproject_count" "$root" >&2
        printf '  Remediation: ensure exactly one .uproject file exists at the repo root,\n' >&2
        printf '  or set SETUP_RAG_IS_UE_REPO=1 or SETUP_RAG_IS_UE_REPO=0 to override.\n' >&2
        return 2
    fi
}

# _srd_daemon_present — exit 0 if the project-rag daemon is reachable, non-zero otherwise.
# Uses SETUP_RAG_DAEMON_PROBE if set; falls back to `project-rag status`.
_srd_daemon_present() {
    local probe="${SETUP_RAG_DAEMON_PROBE:-}"
    if [[ -n "$probe" ]]; then
        # Review: code-reviewer — eval on env-supplied string is arbitrary code execution.
        # Direct invocation: supports "true"/"false"/"/path/to/mock" but refuses shell-metacharacter injection.
        $probe >/dev/null 2>&1
        return $?
    fi

    # Default probe: call project-rag status.
    if ! command -v project-rag >/dev/null 2>&1; then
        return 1
    fi
    project-rag status >/dev/null 2>&1
    return $?
}

# _srd_tripwire_present <claude_md_path> — exit 0 if the tripwire sentinel already
# exists in the file (idempotency guard).
_srd_tripwire_present() {
    local path="${1:?path required}"
    [[ ! -f "$path" ]] && return 1
    grep -qF "${_RAG_TRIPWIRE_SENTINEL}" "$path"
}

# _srd_write_tripwire <root> [dry_run] — append the tripwire block to CLAUDE.md
# at <root>/CLAUDE.md if not already present. When dry_run=1, print what would happen.
_srd_write_tripwire() {
    local root="${1:?root required}"
    local dry_run="${2:-0}"
    local claude_md="${root}/CLAUDE.md"

    if _srd_tripwire_present "$claude_md"; then
        if [[ "$dry_run" -eq 1 ]]; then
            printf '[setup-rag-decision dry-run] tripwire already present in %s — skipping (idempotent)\n' \
                "$claude_md"
        fi
        return 0
    fi

    if [[ "$dry_run" -eq 1 ]]; then
        printf '[setup-rag-decision dry-run] would append tripwire block to %s\n' "$claude_md"
        return 0
    fi

    # Append with a leading blank line for readability.
    printf '\n%s\n' "${_RAG_TRIPWIRE_BLOCK}" >> "$claude_md"
    printf 'setup-rag-decision: tripwire block written to %s\n' "$claude_md"
}

# ---------------------------------------------------------------------------
# Public: setup_rag_decision [--root <path>] [--dry-run]
# ---------------------------------------------------------------------------

setup_rag_decision() {
    local root=""
    local dry_run=0

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --help|-h)
                # Extract help from file header.
                grep '^#' "${BASH_SOURCE[0]}" | sed 's/^#[[:space:]]\{0,1\}//' | \
                    sed -n '/^Usage/,/^Exit codes/p'
                return 0
                ;;
            --root)
                if [[ $# -lt 2 ]]; then
                    printf 'setup-rag-decision: --root requires an argument\n' >&2
                    return 1
                fi
                root="$2"
                shift 2
                ;;
            --dry-run)
                dry_run=1
                shift
                ;;
            -*)
                printf 'setup-rag-decision: unknown flag: %s\n' "$1" >&2
                return 1
                ;;
            *)
                printf 'setup-rag-decision: unexpected argument: %s\n' "$1" >&2
                return 1
                ;;
        esac
    done

    # Resolve target root (env override → --root flag → cwd).
    if [[ -n "${SETUP_RAG_TARGET_ROOT:-}" ]]; then
        root="$SETUP_RAG_TARGET_ROOT"
    fi
    if [[ -z "$root" ]]; then
        root="$(pwd)"
    fi

    # Normalise path separators (Git-Bash/MSYS on Windows).
    root="${root//\\//}"

    if [[ ! -d "$root" ]]; then
        printf 'setup-rag-decision: target root does not exist: %s\n' "$root" >&2
        return 1
    fi

    # --- Branch 1: UE detection ---
    local is_ue=0
    local ue_exit=0
    _srd_is_ue_repo "$root" && is_ue=1 || ue_exit=$?

    if [[ $ue_exit -eq 2 ]]; then
        # Ambiguous — fail loud per detect-then-fail-loud contract.
        return 1
    fi

    # --- Branch 2 & 3: daemon detection (only needed if UE) ---
    if [[ $is_ue -eq 1 ]]; then
        local daemon_present=0
        _srd_daemon_present && daemon_present=1 || true

        if [[ $daemon_present -eq 1 ]]; then
            # Branch 1: UE repo + daemon present → offer to index.
            if [[ $dry_run -eq 1 ]]; then
                printf '[setup-rag-decision dry-run] branch 1: UE repo + daemon present → offer to index\n'
            else
                printf 'setup-rag-decision: branch 1 — UE repo with project-rag daemon detected.\n'
                printf '  Offer: run project-rag index to build a semantic index for this repo.\n'
            fi
            return 0
        else
            # Branch 3: UE repo but no daemon → tripwire.
            if [[ $dry_run -eq 1 ]]; then
                printf '[setup-rag-decision dry-run] branch 3: UE repo but no daemon → tripwire\n'
            else
                printf 'setup-rag-decision: branch 3 — UE repo detected but project-rag daemon is absent.\n'
                printf '  Writing un-indexed tripwire to CLAUDE.md.\n'
                printf '  To enable indexing: install and start the project-rag daemon, then re-run /repo-setup.\n'
            fi
            _srd_write_tripwire "$root" "$dry_run"
            return 0
        fi
    else
        # Branch 2: non-UE repo → tripwire (daemon state irrelevant).
        # Upstream limitation: the "offer to index" branch is currently UE-only
        # because project-rag-ue-addon's .uproject-abstention defect blocks indexing
        # of non-UE repos (tracked via cross-repo memo project-rag-ue-addon-em).
        # Widen after that upstream defect is resolved.
        if [[ $dry_run -eq 1 ]]; then
            printf '[setup-rag-decision dry-run] branch 2: non-UE repo → tripwire (upstream .uproject-abstention defect, cross-repo memo project-rag-ue-addon-em)\n'
        else
            printf 'setup-rag-decision: branch 2 — non-UE repo. RAG indexing is not yet supported\n'
            printf '  for non-UE repos: blocked by project-rag-ue-addon .uproject-abstention defect\n'
            printf '  (cross-repo memo project-rag-ue-addon-em). Writing un-indexed tripwire to CLAUDE.md.\n'
        fi
        _srd_write_tripwire "$root" "$dry_run"
        return 0
    fi
}

# ---------------------------------------------------------------------------
# Standalone execution
# ---------------------------------------------------------------------------

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    setup_rag_decision "$@"
fi
