#!/usr/bin/env bash
# bin/fan-out-dispatch.sh — Fan-out wave compiler: overlap pass + scoped executor prompts.
#
# Purpose: Collapse the entire fan-out ceremony into one EM-side call so fanning out is
# the path of least resistance. Given a chunk-spec (TSV), runs the file-overlap
# intersection pass, then emits N paste-ready scoped dispatch prompts — one per chunk.
#
# Spec backlink: docs/plans/2026-05-27-fan-out-default-doctrine.md §Chunk 1
# Problem addressed: ceremony asymmetry (problem B) — the monolith path was cheaper to
# author than a fan-out; this helper makes fan-out the low-ceremony default.
#
# Input format (TSV, one row per chunk):
#   <chunk-id>TAB<brief-one-liner-or-@filepath>TAB<comma-separated-file-paths>
#
# Usage:
#   printf 'chunk-A\tFix the auth module\tauth.py,auth_test.py\n' | bash bin/fan-out-dispatch.sh
#   bash bin/fan-out-dispatch.sh --spec wave.tsv
#
# Exit codes:
#   0 — success, N blocks emitted to stdout
#   1 — spec/overlap error (with explanatory message on stderr, no partial output)
#   2 — usage or environment error
#
# Environment: none required. Resolves snippet paths relative to script location.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PEER_SCOPE_SNIPPET="${PLUGIN_ROOT}/snippets/peer-scope-block.md"
TEXT_ONLY_SNIPPET="${PLUGIN_ROOT}/snippets/text-only-recovery-preamble.md"

SPEC_FILE=""
PLAN_PATH=""

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
_usage() {
    cat >&2 <<'USAGE'
Usage: fan-out-dispatch.sh [--spec <file>] [--plan <path>]
       printf 'id\tbrief\tfile1,file2\n' | fan-out-dispatch.sh [--plan <path>]

Input: TSV on stdin or --spec <file>, one row per chunk:
  <chunk-id>TAB<brief-one-liner-or-@filepath>TAB<comma-separated-file-paths>

Options:
  --plan <path>   Path to the plan document driving this wave. When provided,
                  fan-out-dispatch.sh creates a per-chunk flight-recorder sidecar
                  at tasks/<plan-slug>/flight/<chunk-id>.md and emits
                  sidecar_path: in each executor brief.
                  # Plan filename should follow YYYY-MM-DD-<slug>.md convention; the date prefix is auto-stripped. Non-dated filenames are accepted verbatim as the slug.

Output: N paste-ready executor dispatch prompts to stdout.
        EM reminders (concurrency cap, commit discipline) to stderr.

Errors on: file-overlap between chunks, malformed rows, non-git-repo cwd.
USAGE
    exit 2
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --help|-h) _usage ;;
        --spec)
            if [[ -z "${2:-}" ]]; then
                echo "fan-out-dispatch.sh: --spec requires a file argument" >&2
                exit 2
            fi
            SPEC_FILE="$2"
            shift 2
            ;;
        --plan)
            if [[ -z "${2:-}" ]]; then
                echo "fan-out-dispatch.sh: --plan requires a file argument" >&2
                exit 2
            fi
            PLAN_PATH="$2"
            shift 2
            ;;
        *)
            echo "fan-out-dispatch.sh: unknown argument: $1" >&2
            exit 2
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Git repo check (AC8): must be in a git repo; capture branch
# ---------------------------------------------------------------------------
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "fan-out-dispatch.sh: ERROR — not inside a git repository." >&2
    echo "  Remediation: run from within your git working tree (e.g., cd /path/to/repo)." >&2
    exit 2
fi

EXPECTED_BRANCH="$(git branch --show-current 2>/dev/null)"
if [[ -z "$EXPECTED_BRANCH" ]]; then
    echo "fan-out-dispatch.sh: ERROR — could not determine current branch (detached HEAD?)." >&2
    echo "  Remediation: checkout a named branch before running fan-out-dispatch." >&2
    exit 2
fi

# ---------------------------------------------------------------------------
# Read spec input
# ---------------------------------------------------------------------------
SPEC_CONTENT=""
if [[ -n "$SPEC_FILE" ]]; then
    if [[ ! -f "$SPEC_FILE" ]]; then
        echo "fan-out-dispatch.sh: spec file not found: ${SPEC_FILE}" >&2
        exit 2
    fi
    SPEC_CONTENT="$(cat -- "$SPEC_FILE")"
else
    SPEC_CONTENT="$(cat)"
fi

if [[ -z "$SPEC_CONTENT" ]]; then
    echo "fan-out-dispatch.sh: empty spec — no chunks to process" >&2
    exit 2
fi

# ---------------------------------------------------------------------------
# Load snippets
# ---------------------------------------------------------------------------
if [[ ! -f "$PEER_SCOPE_SNIPPET" ]]; then
    echo "fan-out-dispatch.sh: ERROR — peer-scope snippet not found: ${PEER_SCOPE_SNIPPET}" >&2
    exit 2
fi
PEER_SCOPE_TEMPLATE="$(cat -- "$PEER_SCOPE_SNIPPET")"

if [[ ! -f "$TEXT_ONLY_SNIPPET" ]]; then
    echo "fan-out-dispatch.sh: ERROR — text-only-recovery-preamble snippet not found: ${TEXT_ONLY_SNIPPET}" >&2
    exit 2
fi
TEXT_ONLY_PREAMBLE="$(cat -- "$TEXT_ONLY_SNIPPET")"

# ---------------------------------------------------------------------------
# Parse and validate spec rows (AC1)
# ---------------------------------------------------------------------------
declare -a CHUNK_IDS=()
declare -a CHUNK_BRIEFS=()
declare -a CHUNK_FILES_RAW=()

ROW_NUM=0
while IFS= read -r line; do
    # Skip blank lines and comment lines (# prefix)
    [[ -z "$line" ]] && continue
    [[ "$line" =~ ^[[:space:]]*# ]] && continue

    ROW_NUM=$((ROW_NUM + 1))

    # Split on TAB — require exactly 3 fields
    IFS=$'\t' read -ra FIELDS <<< "$line"

    if [[ ${#FIELDS[@]} -ne 3 ]]; then
        echo "fan-out-dispatch.sh: ERROR — malformed row ${ROW_NUM}: expected exactly 3 tab-separated fields, got ${#FIELDS[@]}." >&2
        echo "  Row content: ${line}" >&2
        echo "  No output emitted." >&2
        exit 1
    fi

    CHUNK_ID="${FIELDS[0]}"
    BRIEF_RAW="${FIELDS[1]}"
    FILES_RAW="${FIELDS[2]}"

    # Validate: no empty required fields
    if [[ -z "$CHUNK_ID" ]]; then
        echo "fan-out-dispatch.sh: ERROR — malformed row ${ROW_NUM}: chunk-id field is empty." >&2
        echo "  No output emitted." >&2
        exit 1
    fi
    if [[ -z "$BRIEF_RAW" ]]; then
        echo "fan-out-dispatch.sh: ERROR — malformed row ${ROW_NUM} (chunk '${CHUNK_ID}'): brief field is empty." >&2
        echo "  No output emitted." >&2
        exit 1
    fi
    if [[ -z "$FILES_RAW" ]]; then
        echo "fan-out-dispatch.sh: ERROR — malformed row ${ROW_NUM} (chunk '${CHUNK_ID}'): file-paths field is empty." >&2
        echo "  No output emitted." >&2
        exit 1
    fi

    # Resolve @file brief form
    BRIEF="$BRIEF_RAW"
    if [[ "$BRIEF_RAW" == @* ]]; then
        BRIEF_FILE="${BRIEF_RAW:1}"
        if [[ ! -f "$BRIEF_FILE" ]]; then
            echo "fan-out-dispatch.sh: ERROR — row ${ROW_NUM} (chunk '${CHUNK_ID}'): @file brief references non-existent file: ${BRIEF_FILE}" >&2
            echo "  No output emitted." >&2
            exit 1
        fi
        BRIEF="$(cat -- "$BRIEF_FILE")"
        if [[ -z "$BRIEF" ]]; then
            echo "fan-out-dispatch.sh: ERROR — row ${ROW_NUM} (chunk '${CHUNK_ID}'): @file brief file is empty: ${BRIEF_FILE}" >&2
            echo "  No output emitted." >&2
            exit 1
        fi
    fi

    CHUNK_IDS+=("$CHUNK_ID")
    CHUNK_BRIEFS+=("$BRIEF")
    CHUNK_FILES_RAW+=("$FILES_RAW")

done <<< "$SPEC_CONTENT"

CHUNK_COUNT="${#CHUNK_IDS[@]}"

if [[ "$CHUNK_COUNT" -eq 0 ]]; then
    echo "fan-out-dispatch.sh: no valid chunk rows found in spec" >&2
    exit 2
fi

# ---------------------------------------------------------------------------
# Build per-chunk file lists (split on comma, trim whitespace)
# ---------------------------------------------------------------------------
# Each entry in CHUNK_FILES_LISTS is newline-delimited file paths for chunk i
declare -a CHUNK_FILES_LISTS=()

for i in "${!CHUNK_IDS[@]}"; do
    chunk_id="${CHUNK_IDS[$i]}"
    raw="${CHUNK_FILES_RAW[$i]}"

    # NOTE — format limitation: comma is the field-3 delimiter, so a path containing a
    # literal comma is indistinguishable from two separate paths. Paths with commas are
    # unsupported — analogous to tabs being unrepresentable in a TSV field. Detection is
    # impossible at this layer; the behaviour is: a comma-bearing path silently becomes two
    # path entries (see test B6 for the documented known-behaviour assertion).
    IFS=',' read -ra paths_arr <<< "$raw"

    joined=""
    for p in "${paths_arr[@]}"; do
        # Trim leading/trailing whitespace
        p="${p#"${p%%[![:space:]]*}"}"
        p="${p%"${p##*[![:space:]]}"}"
        if [[ -z "$p" ]]; then
            echo "fan-out-dispatch.sh: ERROR — chunk '${chunk_id}': empty path entry in file list after splitting on commas." >&2
            echo "  Raw file field: ${raw}" >&2
            echo "  No output emitted." >&2
            exit 1
        fi
        if [[ -n "$joined" ]]; then
            joined="${joined}"$'\n'"${p}"
        else
            joined="${p}"
        fi
    done
    CHUNK_FILES_LISTS+=("$joined")
done

# ---------------------------------------------------------------------------
# File-overlap intersection pass (AC1) — pairwise, fail-loud on any collision
# ---------------------------------------------------------------------------
OVERLAP_FOUND=0
OVERLAP_REPORT=""

# Review: code-reviewer — declare -a hoisted out of nested loop; re-declare inside a loop is legal bash but redundant and can mask scoping intent; plain reassignment inside loop body is cleaner.
declare -a files_i=()
declare -a files_j=()

for i in "${!CHUNK_IDS[@]}"; do
    id_i="${CHUNK_IDS[$i]}"
    files_i=()
    while IFS= read -r f; do
        [[ -n "$f" ]] && files_i+=("$f")
    done <<< "${CHUNK_FILES_LISTS[$i]}"

    for j in "${!CHUNK_IDS[@]}"; do
        [[ "$j" -le "$i" ]] && continue

        id_j="${CHUNK_IDS[$j]}"
        files_j=()
        while IFS= read -r f; do
            [[ -n "$f" ]] && files_j+=("$f")
        done <<< "${CHUNK_FILES_LISTS[$j]}"

        for fi_path in "${files_i[@]}"; do
            for fj_path in "${files_j[@]}"; do
                if [[ "$fi_path" == "$fj_path" ]]; then
                    OVERLAP_FOUND=1
                    OVERLAP_REPORT="${OVERLAP_REPORT}  File '${fi_path}' claimed by both '${id_i}' and '${id_j}'"$'\n'
                fi
            done
        done

        unset files_j
    done
    unset files_i
done

if [[ "$OVERLAP_FOUND" -ne 0 ]]; then
    echo "fan-out-dispatch.sh: ERROR — file overlap detected between chunks:" >&2
    printf '%s' "$OVERLAP_REPORT" >&2
    echo "  Action required: merge the overlapping chunks into one executor OR sequence them" >&2
    echo "  (serial dispatch with EM verification between). Never silently pick." >&2
    echo "  No output emitted." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Derive plan-slug + create per-chunk flight-recorder sidecars (when --plan provided)
# Spec backlink: docs/plans/2026-06-09-executor-sidecar-flight-recorder.md §Sidecar shape
# Plan-slug: strip YYYY-MM-DD- prefix and .md suffix from the plan filename.
# Sidecar path: tasks/<plan-slug>/flight/<chunk-id>.md (relative to repo root).
# ---------------------------------------------------------------------------
PLAN_SLUG=""
if [[ -n "$PLAN_PATH" ]]; then
    plan_basename="$(basename -- "$PLAN_PATH")"
    # Strip leading YYYY-MM-DD- prefix (8 digits + dash)
    plan_slug_tmp="${plan_basename#[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]-}"
    # Strip trailing .md suffix
    PLAN_SLUG="${plan_slug_tmp%.md}"
    if [[ -z "$PLAN_SLUG" ]]; then
        echo "fan-out-dispatch.sh: ERROR — could not derive plan-slug from: ${PLAN_PATH}" >&2
        exit 2
    fi

    # date -u +%Y-%m-%dT%H:%M:%SZ is BSD-portable (distinct from date -d and date +%s%N which are not — see plugins/coordinator/docs/wiki/cross-platform-shell-portability.md).
    DISPATCH_TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    DISPATCH_BY="${CLAUDE_CODE_SESSION_ID:-em-unknown}"

    for i in "${!CHUNK_IDS[@]}"; do
        cid="${CHUNK_IDS[$i]}"
        sidecar_dir="tasks/${PLAN_SLUG}/flight"
        sidecar_path="${sidecar_dir}/${cid}.md"
        mkdir -p "${sidecar_dir}"
        # Idempotent: skip if sidecar already exists (executor-updated mid-flight, or prior run). Caller is responsible for clearing stale sidecars before re-running on a renamed chunk set — silent skip is by design.
        if [[ ! -f "$sidecar_path" ]]; then
            printf -- '---\nplan: %s\nchunk: %s\ndispatched_at: %s\ndispatched_by: %s\nstatus: dispatched\ncommits: []\nsidecar_schema: v1\n---\n' \
                "$PLAN_PATH" "$cid" "$DISPATCH_TS" "$DISPATCH_BY" > "$sidecar_path"
        fi
    done
fi

# ---------------------------------------------------------------------------
# Large-wave ramp reminder (soft NOTE — offer-shaped, not a HARD STOP):
# Resolve threshold: LARGE_WAVE_THRESHOLD env var → machine-local registry →
# fallback 16. The env var is a script-level convenience override (per-invocation
# operator control of a soft nudge), intentionally ranked above the registry value.
# Spec backlink: docs/plans/2026-05-30-organic-ramp-concurrency-doctrine.md §C2
# ---------------------------------------------------------------------------
LARGE_WAVE_THRESHOLD="${LARGE_WAVE_THRESHOLD:-}"
if [[ -z "$LARGE_WAVE_THRESHOLD" ]]; then
    LARGE_WAVE_THRESHOLD="$(machine-local get fan_out.large_wave_threshold 2>/dev/null)" || true
fi
if [[ -z "$LARGE_WAVE_THRESHOLD" ]] || ! [[ "$LARGE_WAVE_THRESHOLD" =~ ^[0-9]+$ ]]; then
    LARGE_WAVE_THRESHOLD=16
fi

# ---------------------------------------------------------------------------
# Memory-headroom probe (best-effort) — the memory-commit-aware successor to the
# core-count proxy. The genuinely load-bearing resource is RAM/VRAM, not cores, so
# this reads live headroom and emits TWO distinct, complementary signals:
#   • "large wave" NOTE  — fires on the cores proxy (CHUNK_COUNT ≥ threshold), now
#     augmented with the live headroom readout when the probe succeeds.
#   • "headroom tight" NOTE — fires independently when free RAM/VRAM is below a floor,
#     i.e. the machine is ALREADY loaded — regardless of wave size. This is the higher-
#     value signal: it watches what actually degrades the machine, not a proxy.
# The two phrasings are deliberately disjoint ("large wave" never appears on the memory
# signal) so the cores-proxy regression assertions stay valid on a tight CI runner.
# Floors: FAN_OUT_MIN_{RAM,VRAM}_HEADROOM_MB env → machine-local → defaults (4096/2048 MB).
# (No coordinator:install capture for the floors — unlike large_wave_threshold they are absolute
# safety margins, correct as universal defaults; see wiki § Headroom-tight NOTE for rationale.)
# Probe failure (unsupported platform, no probe script) degrades silently to cores-only.
# ---------------------------------------------------------------------------
PROBE_OUT=""
if [[ -f "${SCRIPT_DIR}/probe-memory-headroom.sh" ]]; then
    # Outer wall-clock cap (defense-in-depth atop the probe's per-tool bounds) so a stuck
    # external tool can never stall dispatch; degrades to cores-only if `timeout` is absent.
    if command -v timeout >/dev/null 2>&1; then
        PROBE_OUT="$(timeout 10 bash "${SCRIPT_DIR}/probe-memory-headroom.sh" 2>/dev/null)" || PROBE_OUT=""
    else
        PROBE_OUT="$(bash "${SCRIPT_DIR}/probe-memory-headroom.sh" 2>/dev/null)" || PROBE_OUT=""
    fi
fi
# substr-after-first-`=` (not `$2`) so a value that ever contains `=` is not truncated — the
# probe emits integer/`unknown` today, but this keeps the key=value contract forward-compatible.
_probe_field() { printf '%s\n' "$PROBE_OUT" | awk -F= -v k="$1" '$1==k {print substr($0, index($0,"=")+1); exit}'; }
# Compact magnitude: GB at ≥1 GB, MB below — a headroom-tight machine must not read "≈0 GB".
# Intentionally copied from probe-memory-headroom.sh::_fmt_mb (not sourced — sourcing the probe
# would run its probe legs as a side effect); keep the two in sync if the format changes.
_fmt_headroom_mb() { if [[ "$1" -ge 1024 ]]; then echo "≈$(( $1 / 1024 )) GB"; else echo "≈${1} MB"; fi; }
RAM_AVAIL_MB="$(_probe_field ram_available_mb)"
VRAM_FREE_MB="$(_probe_field vram_free_mb)"

RAM_FLOOR_MB="${FAN_OUT_MIN_RAM_HEADROOM_MB:-}"
if [[ -z "$RAM_FLOOR_MB" ]]; then
    RAM_FLOOR_MB="$(machine-local get fan_out.min_ram_headroom_mb 2>/dev/null)" || true
fi
[[ "$RAM_FLOOR_MB" =~ ^[0-9]+$ ]] || RAM_FLOOR_MB=4096

VRAM_FLOOR_MB="${FAN_OUT_MIN_VRAM_HEADROOM_MB:-}"
if [[ -z "$VRAM_FLOOR_MB" ]]; then
    VRAM_FLOOR_MB="$(machine-local get fan_out.min_vram_headroom_mb 2>/dev/null)" || true
fi
[[ "$VRAM_FLOOR_MB" =~ ^[0-9]+$ ]] || VRAM_FLOOR_MB=2048

# Build the live-headroom readout fragment (empty if probe gave no numbers).
HEADROOM_READOUT=""
if [[ "$RAM_AVAIL_MB" =~ ^[0-9]+$ ]]; then
    HEADROOM_READOUT="RAM free $(_fmt_headroom_mb "$RAM_AVAIL_MB")"
fi
if [[ "$VRAM_FREE_MB" =~ ^[0-9]+$ ]]; then
    if [[ -n "$HEADROOM_READOUT" ]]; then HEADROOM_READOUT="${HEADROOM_READOUT}, "; fi
    HEADROOM_READOUT="${HEADROOM_READOUT}VRAM free $(_fmt_headroom_mb "$VRAM_FREE_MB")"
fi

# Cores-proxy signal — keeps the "large wave" phrase the regression net asserts on.
if [[ "$CHUNK_COUNT" -ge "$LARGE_WAVE_THRESHOLD" ]]; then
    cores_note="NOTE: ${CHUNK_COUNT} concurrent agents is a large wave (≈3× cores) — a speed advisory, NOT a cap: past here CPU scheduling contention may start tapering throughput, but CPU/GPU parallelize fine, so ramp pilot→expand and watch RAM/VRAM commit more than CPU. If any chunk is an orchestrator, count its fanout. Your call, not a PM gate. See § Concurrency Budget."
    if [[ -n "$HEADROOM_READOUT" ]]; then
        cores_note="${cores_note} Live headroom now: ${HEADROOM_READOUT}."
    fi
    echo "$cores_note"
fi

# Memory-pressure signal — the higher-value successor; fires whenever the machine is
# already tight, independent of wave size. Distinct phrasing (no "large wave").
ram_tight=0
vram_tight=0
if [[ "$RAM_AVAIL_MB" =~ ^[0-9]+$ ]] && [[ "$RAM_AVAIL_MB" -lt "$RAM_FLOOR_MB" ]]; then ram_tight=1; fi
if [[ "$VRAM_FREE_MB" =~ ^[0-9]+$ ]] && [[ "$VRAM_FREE_MB" -lt "$VRAM_FLOOR_MB" ]]; then vram_tight=1; fi
if [[ "$ram_tight" -eq 1 || "$vram_tight" -eq 1 ]]; then
    echo "NOTE: memory headroom is tight (${HEADROOM_READOUT:-unknown}) — memory commit, not core count, is what actually degrades this machine. Before launching ${CHUNK_COUNT} agents, ramp pilot→expand and watch the headroom drop per agent; a GPU/CUDA-heavy chunk can commit far more than its share. Floor: RAM ${RAM_FLOOR_MB} MB / VRAM ${VRAM_FLOOR_MB} MB (override via FAN_OUT_MIN_{RAM,VRAM}_HEADROOM_MB). Your call, not a PM gate. See § Concurrency Budget."
fi

# ---------------------------------------------------------------------------
# Fat-chunk NOTE (per-chunk, AC: fan-out-suitability-gate 2026-05-29):
# A single chunk owning many files MAY be a hidden fan-out — N disjoint
# deliverables yeeted at one executor. This is a SOFT, offer-shaped note (the
# design-as-offers ethos: lead with the better alternative, do not block): the
# EM confirms the chunk is one coherent surface or re-chunks it per the Fan-Out
# Suitability Gate (docs/wiki/dispatching-parallel-agents.md § Executing a
# Fan-Out Wave → Step 0.5). Deliberately uses the
# "NOTE:" prefix, NEVER "WARNING:", to keep the phrasing clearly advisory/soft per the
# design-as-offers ethos — there is no blocking gate on this path. Read-overlap and a
# pinned import interface are NOT reasons to keep many files in one chunk — only
# WRITE-overlap is; the NOTE surfaces the question, the EM makes the judgment.
# ---------------------------------------------------------------------------
# Threshold is env-overridable for projects whose coherent surfaces are legitimately wider.
FAT_CHUNK_THRESHOLD="${FAT_CHUNK_THRESHOLD:-4}"
for i in "${!CHUNK_IDS[@]}"; do
    fc_count=0
    while IFS= read -r fc_line; do
        [[ -n "$fc_line" ]] && fc_count=$((fc_count + 1))
    done <<< "${CHUNK_FILES_LISTS[$i]}"
    if [[ "$fc_count" -ge "$FAT_CHUNK_THRESHOLD" ]]; then
        echo "NOTE: chunk '${CHUNK_IDS[$i]}' owns ${fc_count} files — confirm this is ONE coherent surface. If these are independent deliverables with disjoint write targets, split into separate chunks (read-overlap and a pinned import interface are NOT reasons to keep them in one executor). See docs/wiki/dispatching-parallel-agents.md, Step 0.5 of the fan-out methodology."
    fi
    unset fc_count fc_line
done

# ---------------------------------------------------------------------------
# EM reminders → stderr (AC3)
# ---------------------------------------------------------------------------
cat >&2 <<REMINDERS

--- fan-out-dispatch.sh: EM REMINDERS (not for executor prompts) ---
Concurrency: ramp pilot→expand — launch a pilot, observe this session's
responsiveness, expand. Maximize hardware utilization; the cores-scaled NOTE
(≈3× cores) is a speed-taper advisory, NOT a cap — a CPU time-slices far more
than (cores) tasks, so past the threshold you pay scheduling contention, you do
not stop. CPU/GPU parallelize, so the dimension to watch is memory commit
(RAM/VRAM), not core count — for a live readout run bin/probe-memory-headroom.sh
(--human), the memory-commit-aware signal behind the headroom NOTEs above.
If any chunk is an orchestrator (spawning sub-agents),
count its fanout toward your wave size; leaf workers (executors, reviewers, simple
file-scoped scouts) spawn nothing. Note: the platform's min(16, cores-2) cap
applies ONLY inside Workflow scripts, NOT on this manual fan-out path — organic
ramp is the guard here, by design.

Commit discipline: YOU (the EM) commit serially after the wave completes using plain
scoped git:  git add -- <file1> <file2> ...  &&  git commit -m "<subject>"
Executors do NOT commit. No commit step appears in the emitted executor prompts.

Branch captured: ${EXPECTED_BRANCH}
Chunks in this wave: ${CHUNK_COUNT}
---

REMINDERS

# ---------------------------------------------------------------------------
# Strip HTML comment header from peer-scope template, leaving the block body
# ---------------------------------------------------------------------------
PEER_SCOPE_BODY=""
in_html_comment=0
leading_blank=1
while IFS= read -r tline; do
    # Detect opening of HTML comment block
    if [[ "$tline" == "<!--"* ]] && [[ "$in_html_comment" -eq 0 ]]; then
        in_html_comment=1
        # Check if comment closes on same line
        if [[ "$tline" == *"-->"* ]]; then
            in_html_comment=0
        fi
        continue
    fi
    # Inside multi-line HTML comment
    if [[ "$in_html_comment" -eq 1 ]]; then
        if [[ "$tline" == *"-->"* ]]; then
            in_html_comment=0
        fi
        continue
    fi
    # Skip leading blank lines
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
# Emit N paste-ready dispatch blocks (AC2)
# ---------------------------------------------------------------------------
for i in "${!CHUNK_IDS[@]}"; do
    chunk_id="${CHUNK_IDS[$i]}"
    brief="${CHUNK_BRIEFS[$i]}"

    # Build own file list
    declare -a own_files=()
    while IFS= read -r f; do
        [[ -n "$f" ]] && own_files+=("$f")
    done <<< "${CHUNK_FILES_LISTS[$i]}"

    # Build peer chunks block
    peer_lines=""
    for j in "${!CHUNK_IDS[@]}"; do
        [[ "$j" -eq "$i" ]] && continue
        peer_id="${CHUNK_IDS[$j]}"
        peer_files_display=""
        while IFS= read -r f; do
            if [[ -n "$f" ]]; then
                if [[ -n "$peer_files_display" ]]; then
                    peer_files_display="${peer_files_display}, ${f}"
                else
                    peer_files_display="${f}"
                fi
            fi
        done <<< "${CHUNK_FILES_LISTS[$j]}"
        entry="- ${peer_id} (files: ${peer_files_display}) — concurrent executor handles this"
        if [[ -n "$peer_lines" ]]; then
            peer_lines="${peer_lines}"$'\n'"${entry}"
        else
            peer_lines="${entry}"
        fi
    done

    # Fill {{peer_chunks}} placeholder in template body.
    # Use python3 for a fully literal substitution: bash ${var/pat/repl} corrupts when
    # $peer_lines contains backslashes (e.g. Windows-native paths like X:\Users\...).
    # awk gsub() has the same problem (\\ and & are special in the replacement string).
    # python3 str.replace() treats both needle and replacement as plain strings — no
    # backslash or & interpretation whatsoever.
    peer_scope_filled="$(python3 -c "
import sys
body = sys.argv[1]
repl = sys.argv[2]
print(body.replace('{{peer_chunks}}', repl), end='')
" "$PEER_SCOPE_BODY" "$peer_lines")"

    # Emit block
    echo ""
    echo "# ===== EXECUTOR DISPATCH BLOCK: ${chunk_id} ====="
    echo '```'
    echo "## Chunk: ${chunk_id}"
    echo ""
    echo "### Brief"
    echo "${brief}"
    echo ""
    echo "### In-scope"
    echo "Files this executor owns:"
    for f in "${own_files[@]}"; do
        echo "- ${f}"
    done
    echo ""
    echo "${peer_scope_filled}"
    echo ""
    echo "### Destructive-action prohibition"
    echo "Do NOT delete, force-push, reset --hard, or run any destructive git operation."
    echo "Do NOT stage, push, or commit any files. The EM commits serially after the wave with plain scoped git."
    echo "Do NOT modify any file outside the In-scope list above."
    echo ""
    echo "### Disk-first verification preamble"
    echo "${TEXT_ONLY_PREAMBLE}"
    echo ""
    echo "expected_branch: ${EXPECTED_BRANCH}"
    if [[ -n "$PLAN_SLUG" ]]; then
        echo "sidecar_path: tasks/${PLAN_SLUG}/flight/${chunk_id}.md"
    fi
    echo '```'
    echo "# ===== END BLOCK: ${chunk_id} ====="
    echo ""

    unset own_files
done
