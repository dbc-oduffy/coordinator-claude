#!/usr/bin/env bash
# bin/fan-out-integrator.sh — Fan-out integrator compiler: overlap pass + scoped review-integrator prompts.
#
# Purpose: Collapse the parallel-integrator dispatch ceremony into one EM-side call so
# fanning out integrators is the path of least resistance. Given a slice-spec (TSV),
# validates each cited reviewer sidecar exists on disk, runs the file-overlap pass, then
# emits N paste-ready coordinator:review-integrator dispatch prompts — one per slice.
#
# Spec backlink: docs/plans/2026-06-09-partitioned-review-integrator-fan-out.md §Chunk 1
# Problem addressed: ceremony asymmetry (P2/STRUCTURAL) — union-integrator was cheaper to
# author than N parallel integrators; this helper makes parallel integrator fan-out the
# low-ceremony default and makes union-integrator the off-script choice.
#
# Negative-spec: NO --plan / sidecar emission. Integrators are single-pass edit dispatches,
# not flight-recorder workloads. NO fat-chunk NOTE. NO memory-headroom probe.
# N is small (matches slice count, typically 2-4) and integrator dispatches are I/O-bound.
#
# Input format (TSV on stdin or --spec <file>), one row per slice:
#   <slice-id>TAB<reviewer-sidecar-path>TAB<comma-separated-file-paths>
#
# Usage:
#   printf 'slice-A\tstate/review-trail/slice-A.json\tauth.py,auth_test.py\n' | bash bin/fan-out-integrator.sh
#   bash bin/fan-out-integrator.sh --spec slices.tsv
#
# Exit codes:
#   0 — success, N blocks emitted to stdout
#   1 — content validation error (missing sidecar, file overlap, malformed row)
#   2 — invocation error (usage, environment, missing spec file)
#
# Environment: none required. Resolves snippet paths relative to script location.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PEER_SCOPE_SNIPPET="${PLUGIN_ROOT}/snippets/peer-scope-block.md"
TEXT_ONLY_SNIPPET="${PLUGIN_ROOT}/snippets/text-only-recovery-preamble.md"

SPEC_FILE=""

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
_usage() {
    cat >&2 <<'USAGE'
Usage: fan-out-integrator.sh [--spec <file>]
       printf 'slice-id\tsidecar-path\tfile1,file2\n' | fan-out-integrator.sh

Input: TSV on stdin or --spec <file>, one row per slice:
  <slice-id>TAB<reviewer-sidecar-path>TAB<comma-separated-file-paths>

  slice-id              — e.g. slice-A, slice-B
  reviewer-sidecar-path — path to the code-reviewer output on disk (MUST exist)
  comma-separated-file-paths — the slice's review scope (same paths as the source reviewer)

Output: N paste-ready coordinator:review-integrator dispatch prompts to stdout.
        EM reminders (parallel dispatch, commit discipline) to stderr.

Errors on:
  - missing reviewer sidecar (exit 1)
  - file-overlap between slices (exit 1)
  - malformed row / wrong field count (exit 1)
  - non-git-repo cwd (exit 2)
  - empty spec (exit 2)
USAGE
    exit 2
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --help|-h) _usage ;;
        --spec)
            if [[ -z "${2:-}" ]]; then
                echo "fan-out-integrator.sh: --spec requires a file argument" >&2
                exit 2
            fi
            SPEC_FILE="$2"
            shift 2
            ;;
        *)
            echo "fan-out-integrator.sh: unknown argument: $1" >&2
            exit 2
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Git repo check: must be in a git repo; capture branch
# ---------------------------------------------------------------------------
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "fan-out-integrator.sh: ERROR — not inside a git repository." >&2
    echo "  Remediation: run from within your git working tree (e.g., cd /path/to/repo)." >&2
    exit 2
fi

EXPECTED_BRANCH="$(git branch --show-current 2>/dev/null)"
if [[ -z "$EXPECTED_BRANCH" ]]; then
    echo "fan-out-integrator.sh: ERROR — could not determine current branch (detached HEAD?)." >&2
    echo "  Remediation: checkout a named branch before running fan-out-integrator." >&2
    exit 2
fi

# ---------------------------------------------------------------------------
# Read spec input
# ---------------------------------------------------------------------------
SPEC_CONTENT=""
if [[ -n "$SPEC_FILE" ]]; then
    if [[ ! -f "$SPEC_FILE" ]]; then
        echo "fan-out-integrator.sh: spec file not found: ${SPEC_FILE}" >&2
        exit 2
    fi
    SPEC_CONTENT="$(cat -- "$SPEC_FILE")"
else
    SPEC_CONTENT="$(cat)"
fi

if [[ -z "$SPEC_CONTENT" ]]; then
    echo "fan-out-integrator.sh: empty spec — no slices to process" >&2
    exit 2
fi

# ---------------------------------------------------------------------------
# Load snippets
# ---------------------------------------------------------------------------
if [[ ! -f "$PEER_SCOPE_SNIPPET" ]]; then
    echo "fan-out-integrator.sh: ERROR — peer-scope snippet not found: ${PEER_SCOPE_SNIPPET}" >&2
    exit 2
fi
PEER_SCOPE_TEMPLATE="$(cat -- "$PEER_SCOPE_SNIPPET")"

if [[ ! -f "$TEXT_ONLY_SNIPPET" ]]; then
    echo "fan-out-integrator.sh: ERROR — text-only-recovery-preamble snippet not found: ${TEXT_ONLY_SNIPPET}" >&2
    exit 2
fi
TEXT_ONLY_PREAMBLE="$(cat -- "$TEXT_ONLY_SNIPPET")"

# ---------------------------------------------------------------------------
# Parse and validate spec rows
# ---------------------------------------------------------------------------
SLICE_IDS=""
SLICE_SIDECARS=""
SLICE_FILES_RAW=""
SLICE_COUNT=0

ROW_NUM=0
while IFS= read -r line; do
    # Skip blank lines and comment lines (# prefix)
    [[ -z "$line" ]] && continue
    [[ "$line" =~ ^[[:space:]]*# ]] && continue

    ROW_NUM=$((ROW_NUM + 1))

    # Split on TAB — require exactly 3 fields
    # Portable tab-count via pipe chain rather than IFS=$'\t' read -ra: decouples
    # field-count validation (tab counting) from field extraction (cut -f), making
    # each concern independently readable and testable without a temp array.
    tab_count=$(printf '%s' "$line" | tr -cd '\t' | wc -c | tr -d ' ')
    if [[ "$tab_count" -ne 2 ]]; then
        field_count=$((tab_count + 1))
        echo "fan-out-integrator.sh: ERROR — malformed row ${ROW_NUM}: expected exactly 3 tab-separated fields, got ${field_count}." >&2
        echo "  Row content: ${line}" >&2
        echo "  No output emitted." >&2
        exit 1
    fi

    # Extract fields by splitting on tab
    SLICE_ID="$(printf '%s' "$line" | cut -f1)"
    SIDECAR_PATH="$(printf '%s' "$line" | cut -f2)"
    FILES_RAW_FIELD="$(printf '%s' "$line" | cut -f3)"

    # Validate: no empty required fields
    if [[ -z "$SLICE_ID" ]]; then
        echo "fan-out-integrator.sh: ERROR — malformed row ${ROW_NUM}: slice-id field is empty." >&2
        echo "  No output emitted." >&2
        exit 1
    fi
    # Review: code-reviewer — slice-id containing a newline/tab would silently corrupt sed-n indexing
    if [[ "$SLICE_ID" == *$'\n'* ]] || [[ "$SLICE_ID" == *$'\t'* ]]; then
        echo "fan-out-integrator.sh: ERROR — row ${ROW_NUM}: slice-id contains newline or tab character." >&2
        echo "  No output emitted." >&2
        exit 1
    fi
    if [[ -z "$SIDECAR_PATH" ]]; then
        echo "fan-out-integrator.sh: ERROR — malformed row ${ROW_NUM} (slice '${SLICE_ID}'): reviewer-sidecar-path field is empty." >&2
        echo "  No output emitted." >&2
        exit 1
    fi
    if [[ -z "$FILES_RAW_FIELD" ]]; then
        echo "fan-out-integrator.sh: ERROR — malformed row ${ROW_NUM} (slice '${SLICE_ID}'): file-paths field is empty." >&2
        echo "  No output emitted." >&2
        exit 1
    fi

    # NEW precondition (integrator-specific): reviewer sidecar MUST exist on disk
    if [[ ! -f "$SIDECAR_PATH" ]]; then
        echo "fan-out-integrator.sh: ERROR — reviewer sidecar not found on disk: ${SIDECAR_PATH}" >&2
        echo "  Slice '${SLICE_ID}' requires a code-reviewer output file at the cited path." >&2
        echo "  Ensure the reviewer has returned and its sidecar is written before running fan-out-integrator." >&2
        echo "  No output emitted." >&2
        exit 1
    fi

    # Accumulate via newline-delimited strings (bash 3.2 compatible — no declare -A)
    if [[ "$SLICE_COUNT" -eq 0 ]]; then
        SLICE_IDS="${SLICE_ID}"
        SLICE_SIDECARS="${SIDECAR_PATH}"
        SLICE_FILES_RAW="${FILES_RAW_FIELD}"
    else
        SLICE_IDS="${SLICE_IDS}"$'\n'"${SLICE_ID}"
        SLICE_SIDECARS="${SLICE_SIDECARS}"$'\n'"${SIDECAR_PATH}"
        SLICE_FILES_RAW="${SLICE_FILES_RAW}"$'\n'"${FILES_RAW_FIELD}"
    fi
    SLICE_COUNT=$((SLICE_COUNT + 1))

done <<< "$SPEC_CONTENT"

if [[ "$SLICE_COUNT" -eq 0 ]]; then
    echo "fan-out-integrator.sh: no valid slice rows found in spec" >&2
    exit 2
fi

# ---------------------------------------------------------------------------
# Build per-slice file lists (split on comma, trim whitespace)
# Stored as newline-delimited entries in SLICE_FILES_LISTS_<n> pattern (bash 3.2)
# We use indexed variable names stored in an array of names.
# ---------------------------------------------------------------------------
# We'll accumulate parsed file lists as newline-delimited strings in
# PARSED_FILES_0, PARSED_FILES_1, ... via eval (bash 3.2 safe).
# Then we can retrieve them by index.

idx=0
while IFS= read -r raw_field; do
    parsed_list=""
    IFS=',' read -ra paths_arr <<< "$raw_field"
    for p in "${paths_arr[@]}"; do
        # Trim leading/trailing whitespace (bash 3.2 portable)
        p="${p#"${p%%[![:space:]]*}"}"
        p="${p%"${p##*[![:space:]]}"}"
        if [[ -z "$p" ]]; then
            # Retrieve slice id for error context
            sid_for_err="$(printf '%s\n' "$SLICE_IDS" | sed -n "$((idx + 1))p")"
            echo "fan-out-integrator.sh: ERROR — slice '${sid_for_err}': empty path entry in file list after splitting on commas." >&2
            echo "  Raw file field: ${raw_field}" >&2
            echo "  No output emitted." >&2
            exit 1
        fi
        if [[ -n "$parsed_list" ]]; then
            parsed_list="${parsed_list}"$'\n'"${p}"
        else
            parsed_list="${p}"
        fi
    done
    eval "PARSED_FILES_${idx}=\"\${parsed_list}\""
    idx=$((idx + 1))
done <<< "$SLICE_FILES_RAW"

# Review: code-reviewer (F1) — assert idx == SLICE_COUNT to catch any sync divergence
# between SLICE_IDS/SLICE_SIDECARS/SLICE_FILES_RAW and the PARSED_FILES_N variables.
# Silent mismatch would cause sed -n "${n}p" extractors to return wrong content.
if [[ "$idx" -ne "$SLICE_COUNT" ]]; then
    echo "fan-out-integrator.sh: INTERNAL ERROR — parsed file index ($idx) mismatches slice count ($SLICE_COUNT)" >&2
    exit 2
fi

# ---------------------------------------------------------------------------
# File-overlap intersection pass — pairwise, fail-loud on any collision
# ---------------------------------------------------------------------------
OVERLAP_FOUND=0
OVERLAP_REPORT=""

i=0
while [[ "$i" -lt "$SLICE_COUNT" ]]; do
    id_i="$(printf '%s\n' "$SLICE_IDS" | sed -n "$((i + 1))p")"
    eval "files_i_str=\"\${PARSED_FILES_${i}}\""

    j=$((i + 1))
    while [[ "$j" -lt "$SLICE_COUNT" ]]; do
        id_j="$(printf '%s\n' "$SLICE_IDS" | sed -n "$((j + 1))p")"
        eval "files_j_str=\"\${PARSED_FILES_${j}}\""

        while IFS= read -r fi_path; do
            [[ -z "$fi_path" ]] && continue
            while IFS= read -r fj_path; do
                [[ -z "$fj_path" ]] && continue
                if [[ "$fi_path" == "$fj_path" ]]; then
                    OVERLAP_FOUND=1
                    OVERLAP_REPORT="${OVERLAP_REPORT}  File '${fi_path}' claimed by both '${id_i}' and '${id_j}'"$'\n'
                fi
            done <<< "$files_j_str"
        done <<< "$files_i_str"

        j=$((j + 1))
    done
    i=$((i + 1))
done

if [[ "$OVERLAP_FOUND" -ne 0 ]]; then
    echo "fan-out-integrator.sh: ERROR — file overlap detected between slices:" >&2
    printf '%s' "$OVERLAP_REPORT" >&2
    echo "  Action required: merge the overlapping slices into one integrator dispatch OR sequence them" >&2
    echo "  (serial dispatch with EM verification between). Never silently pick." >&2
    echo "  No output emitted." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# EM reminders → stderr
# ---------------------------------------------------------------------------
cat >&2 <<REMINDERS

--- fan-out-integrator.sh: EM REMINDERS (not for integrator prompts) ---
Dispatch ALL ${SLICE_COUNT} integrator blocks in PARALLEL — that is the entire point of this script.
Each integrator handles ONE reviewer slice; dispatching them sequentially defeats the
partition that was applied because one integrator couldn't fit the whole surface.

Commit discipline: YOU (the EM) commit serially after the wave completes using plain
scoped git:  git add -- <file1> <file2> ...  &&  git commit -m "<subject>"
Integrators do NOT commit. EM commits serially after integrators return.

Branch captured: ${EXPECTED_BRANCH}
Slices in this wave: ${SLICE_COUNT}
---

REMINDERS

# ---------------------------------------------------------------------------
# Strip HTML comment header from peer-scope template, leaving the block body
# ---------------------------------------------------------------------------
PEER_SCOPE_BODY=""
in_html_comment=0
leading_blank=1
while IFS= read -r tline; do
    if [[ "$tline" == "<!--"* ]] && [[ "$in_html_comment" -eq 0 ]]; then
        in_html_comment=1
        if [[ "$tline" == *"-->"* ]]; then
            in_html_comment=0
        fi
        continue
    fi
    if [[ "$in_html_comment" -eq 1 ]]; then
        if [[ "$tline" == *"-->"* ]]; then
            in_html_comment=0
        fi
        continue
    fi
    if [[ "$leading_blank" -eq 1 ]] && [[ -z "$tline" ]]; then
        continue
    fi
    leading_blank=0
    if [[ -n "$PEER_SCOPE_BODY" ]]; then
        PEER_SCOPE_BODY="${PEER_SCOPE_BODY}"$'\n'"${tline}"
    else
        PEER_SCOPE_BODY="${tline}"
    fi
done <<< "$PEER_SCOPE_TEMPLATE"

# ---------------------------------------------------------------------------
# Pre-flight: python3 required for {{peer_chunks}} substitution in emit loop
# ---------------------------------------------------------------------------
# Review: code-reviewer — absent python3 fails mid-emission with confusing "command not found"
command -v python3 >/dev/null 2>&1 || {
    echo "fan-out-integrator.sh: ERROR — python3 required but not found on PATH" >&2
    echo "  Remediation: install python3 or ensure it is on your PATH before running this script." >&2
    exit 2
}

# ---------------------------------------------------------------------------
# Emit N paste-ready dispatch blocks
# ---------------------------------------------------------------------------
i=0
while [[ "$i" -lt "$SLICE_COUNT" ]]; do
    slice_id="$(printf '%s\n' "$SLICE_IDS" | sed -n "$((i + 1))p")"
    sidecar_path="$(printf '%s\n' "$SLICE_SIDECARS" | sed -n "$((i + 1))p")"
    eval "own_files_str=\"\${PARSED_FILES_${i}}\""

    # Build peer slices block (other slices' ids + scope — parallel right now)
    peer_lines=""
    j=0
    while [[ "$j" -lt "$SLICE_COUNT" ]]; do
        if [[ "$j" -ne "$i" ]]; then
            peer_id="$(printf '%s\n' "$SLICE_IDS" | sed -n "$((j + 1))p")"
            peer_sidecar="$(printf '%s\n' "$SLICE_SIDECARS" | sed -n "$((j + 1))p")"
            eval "peer_files_str=\"\${PARSED_FILES_${j}}\""

            peer_files_display=""
            while IFS= read -r f; do
                [[ -z "$f" ]] && continue
                if [[ -n "$peer_files_display" ]]; then
                    peer_files_display="${peer_files_display}, ${f}"
                else
                    peer_files_display="${f}"
                fi
            done <<< "$peer_files_str"

            entry="- ${peer_id} (sidecar: ${peer_sidecar}, files: ${peer_files_display}) — peer integrator is running RIGHT NOW in parallel; do NOT wait for it, do NOT collate its findings with yours, your scope is yours alone"
            if [[ -n "$peer_lines" ]]; then
                peer_lines="${peer_lines}"$'\n'"${entry}"
            else
                peer_lines="${entry}"
            fi
        fi
        j=$((j + 1))
    done

    # Fill {{peer_chunks}} placeholder using python3 for literal substitution.
    # bash ${var/pat/repl} corrupts backslashes on Windows paths; python3 str.replace()
    # treats both needle and replacement as plain strings — no backslash or & interpretation.
    peer_scope_filled="$(python3 -c "
import sys
body = sys.argv[1]
repl = sys.argv[2]
print(body.replace('{{peer_chunks}}', repl), end='')
" "$PEER_SCOPE_BODY" "$peer_lines")"

    # Build own file list display
    own_files_display=""
    while IFS= read -r f; do
        [[ -z "$f" ]] && continue
        own_files_display="${own_files_display}- ${f}"$'\n'
    done <<< "$own_files_str"

    # Emit block
    echo ""
    echo "# ===== INTEGRATOR DISPATCH BLOCK: ${slice_id} ====="
    echo '```'
    echo "## Slice: ${slice_id}"
    echo ""
    echo "### Brief"
    echo "Integrate findings from \`${sidecar_path}\` into the codebase. Slice: ${slice_id}."
    echo ""
    echo "### In-scope"
    echo "Files this integrator owns (same scope as the source reviewer for slice ${slice_id}):"
    printf '%s' "$own_files_display"
    echo ""
    echo "### Reviewer sidecar"
    echo "Read findings from: ${sidecar_path}"
    echo "(This file MUST exist on disk — the integrator reads findings from this path, not from inline prompt prose.)"
    echo ""
    echo "${peer_scope_filled}"
    echo ""
    echo "### Parallel-dispatch reminder"
    echo "This integrator is one of ${SLICE_COUNT} running in parallel right now — one per reviewer slice."
    echo "Do NOT wait for peer integrators to complete. Do NOT collate peer findings into your pass."
    echo "Your scope is exactly the files listed above and the findings in your sidecar only."
    echo "The partition was applied because one integrator cannot fit the whole surface; the same"
    echo "constraint that drove the reviewer partition binds the integrator partition."
    echo ""
    echo "### Destructive-action prohibition"
    echo "Do NOT delete, force-push, reset --hard, or run any destructive git operation."
    echo "Do NOT stage, push, or commit any files (exception: doctrine files per review-integrator commit discipline)."
    echo "Do NOT modify any file outside the In-scope list above."
    echo ""
    echo "### Disk-first verification preamble"
    echo "${TEXT_ONLY_PREAMBLE}"
    echo ""
    echo "expected_branch: ${EXPECTED_BRANCH}"
    echo '```'
    echo "# ===== END BLOCK: ${slice_id} ====="
    echo ""

    i=$((i + 1))
done
