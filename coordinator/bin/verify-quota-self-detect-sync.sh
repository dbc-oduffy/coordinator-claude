#!/usr/bin/env bash
# verify-quota-self-detect-sync.sh — Check/fix/list quota-self-detect-preamble sentinel blocks across all owned agent prompts.
#
# Usage:
#   verify-quota-self-detect-sync.sh           Verify all consumers match the canonical snippet. Exit non-zero on drift.
#   verify-quota-self-detect-sync.sh --check   Alias for default mode (explicit).
#   verify-quota-self-detect-sync.sh --fix     Rewrite drifting sentinel blocks with the canonical snippet body.
#   verify-quota-self-detect-sync.sh --list    Print one consumer path per line (used by AC-4).
#
# Sentinel pair (exact strings):
#   <!-- BEGIN quota-self-detect-preamble (synced from snippets/quota-self-detect-preamble.md) -->
#   <!-- END quota-self-detect-preamble -->
#
# Placement (per DR-6): mid-body, adjacent to existing constraint-shape sentinels. When an existing
# BEGIN sentinel (e.g. reviewer-calibration, docs-checker-consumption) is found in the consumer,
# insert immediately after its END line. When no existing sentinel found, append after the
# role-and-rules section body, before any trailing DONE-preamble or examples section.
#
# Spec backlink: docs/plans/2026-06-15-nudge-quota-exhausted-agent.md § Chunk 1

set -uo pipefail
# -e omitted deliberately: awk sentinel checks return non-zero on miss; explicit EXIT_CODE tracks failures.

PYTHON_BIN="$(command -v python3 || command -v python || true)"
if [ -z "$PYTHON_BIN" ]; then
    echo "ERROR: neither python3 nor python found on PATH" >&2
    exit 2
fi

if ! command -v node >/dev/null 2>&1; then
    echo "ERROR: node not found on PATH (required for sentinel-blocks-cli.js)" >&2
    exit 2
fi

BEGIN_SENTINEL='<!-- BEGIN quota-self-detect-preamble (synced from snippets/quota-self-detect-preamble.md) -->'
END_SENTINEL='<!-- END quota-self-detect-preamble -->'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ]; then
    PLUGIN_ROOT="$CLAUDE_PLUGIN_ROOT"
else
    PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
fi

SNIPPET_FILE="$PLUGIN_ROOT/snippets/quota-self-detect-preamble.md"

if [ ! -f "$SNIPPET_FILE" ]; then
    echo "ERROR: canonical snippet not found at $SNIPPET_FILE" >&2
    exit 1
fi

MODE="${1:---check}"
# Review: code-reviewer — removed undocumented 'verify' alias; canonical alias is --check (documented in usage header).
case "${MODE}" in --check|--fix|--list) ;;
  *) echo "ERROR: unknown argument '${MODE}'" >&2; exit 2 ;; esac

# --- CONSUMERS array ---
# Exact output of:
#   find ~/.claude/plugins/coordinator-claude/{coordinator,data-science,web-dev,deep-research}/agents \
#        ~/.claude/plugins/deep-research/notebooklm/agents \
#        ~/.claude/plugins/claude-unreal-holodeck/{holodeck-control,game-dev}/agents \
#        -name "*.md" -type f 2>/dev/null | sort
# Run date: 2026-06-15. Count: 45 (plan estimated 44; the discrepancy is one extra coordinator
# agent — vp-product.md was present at plan-write time, counted as 18 coordinator agents, not 17).
# Paths are relative to HOME to remain location-stable across machines.
# Spec backlink: docs/plans/2026-06-15-nudge-quota-exhausted-agent.md § Chunk 1 — CONSUMERS array
CONSUMERS=(
    "$HOME/.claude/plugins/claude-unreal-holodeck/game-dev/agents/bp-test-evidence-parser.md"
    "$HOME/.claude/plugins/claude-unreal-holodeck/game-dev/agents/perf-trace-classifier.md"
    "$HOME/.claude/plugins/claude-unreal-holodeck/game-dev/agents/schema-migration-auditor.md"
    "$HOME/.claude/plugins/claude-unreal-holodeck/game-dev/agents/staff-game-dev.md"
    "$HOME/.claude/plugins/claude-unreal-holodeck/game-dev/agents/ue-blueprint-assembler.md"
    "$HOME/.claude/plugins/claude-unreal-holodeck/game-dev/agents/ue-blueprint-worker.md"
    "$HOME/.claude/plugins/claude-unreal-holodeck/holodeck-control/agents/ue-asset-author.md"
    "$HOME/.claude/plugins/claude-unreal-holodeck/holodeck-control/agents/ue-cinematic-animator.md"
    "$HOME/.claude/plugins/claude-unreal-holodeck/holodeck-control/agents/ue-gameplay-engineer.md"
    "$HOME/.claude/plugins/claude-unreal-holodeck/holodeck-control/agents/ue-infra-engineer.md"
    "$HOME/.claude/plugins/claude-unreal-holodeck/holodeck-control/agents/ue-project-orchestrator.md"
    "$HOME/.claude/plugins/claude-unreal-holodeck/holodeck-control/agents/ue-python-executor.md"
    "$HOME/.claude/plugins/claude-unreal-holodeck/holodeck-control/agents/ue-virtual-production.md"
    "$HOME/.claude/plugins/claude-unreal-holodeck/holodeck-control/agents/ue-world-builder.md"
    "$HOME/.claude/plugins/coordinator/agents/code-architect.md"
    "$HOME/.claude/plugins/coordinator/agents/code-reviewer-weekly.md"
    "$HOME/.claude/plugins/coordinator/agents/code-reviewer.md"
    "$HOME/.claude/plugins/coordinator/agents/dep-cve-auditor.md"
    "$HOME/.claude/plugins/coordinator/agents/doc-link-checker.md"
    "$HOME/.claude/plugins/coordinator/agents/docs-checker.md"
    "$HOME/.claude/plugins/coordinator/agents/eng-director.md"
    "$HOME/.claude/plugins/coordinator/agents/enricher.md"
    "$HOME/.claude/plugins/coordinator/agents/executor.md"
    "$HOME/.claude/plugins/coordinator/agents/external-pattern-checker.md"
    "$HOME/.claude/plugins/coordinator/agents/parallel-review-synthesizer.md"
    "$HOME/.claude/plugins/coordinator/agents/plan-coverage-checker.md"
    "$HOME/.claude/plugins/coordinator/agents/prior-art-checker.md"
    "$HOME/.claude/plugins/coordinator/agents/review-integrator.md"
    "$HOME/.claude/plugins/coordinator/agents/security-audit-worker.md"
    "$HOME/.claude/plugins/coordinator/agents/staff-eng.md"
    "$HOME/.claude/plugins/coordinator/agents/test-evidence-parser.md"
    "$HOME/.claude/plugins/coordinator/agents/vp-product.md"
    "$HOME/.claude/plugins/data-science/agents/staff-data-sci.md"
    "$HOME/.claude/plugins/deep-research/agents/coverage-auditor.md"
    "$HOME/.claude/plugins/deep-research/agents/repo-scout.md"
    "$HOME/.claude/plugins/deep-research/agents/repo-specialist.md"
    "$HOME/.claude/plugins/deep-research/agents/research-scout.md"
    "$HOME/.claude/plugins/deep-research/agents/research-specialist.md"
    "$HOME/.claude/plugins/deep-research/agents/research-synthesizer.md"
    "$HOME/.claude/plugins/deep-research/agents/structured-synthesizer.md"
    "$HOME/.claude/plugins/deep-research/notebooklm/agents/notebooklm-research-scout.md"
    "$HOME/.claude/plugins/deep-research/notebooklm/agents/research-sweep.md"
    "$HOME/.claude/plugins/deep-research/notebooklm/agents/research-worker.md"
    "$HOME/.claude/plugins/web-dev/agents/senior-front-end.md"
    "$HOME/.claude/plugins/web-dev/agents/staff-ux.md"
)


if [ "$MODE" = "--list" ]; then
    # --list enumerates the canonical CONSUMERS array — the universe of paths
    # where the snippet SHOULD land, regardless of current sentinel presence.
    # Used by AC-4 (`--list | wc -l == 45`).
    for f in "${CONSUMERS[@]}"; do
        printf '%s\n' "$f"
    done
    exit 0
fi

# Extract the snippet body: skip line 1 (comment header) and line 2 (blank).
# The snippet file has NO internal BEGIN sentinel — line 3 IS the ## Quota-Exhausted Self-Detection
# heading, which must be included in the injected body. The final END sentinel line is also excluded.
# The snippet file structure: line 1 = comment, line 2 = blank, line 3 = heading (body starts here),
# lines 3..N-1 = body, line N = END sentinel.
# Review: code-reviewer — NR>3 silently skipped the heading; NR>2 includes it so injected blocks carry the heading.
SNIPPET_BODY="$(awk -v end_sentinel="$END_SENTINEL" 'NR>2 && $0 != end_sentinel' "$SNIPPET_FILE")"

normalize() {
    # TODO: see verify-plan-coverage-sync.sh — same BSD-portability concern with sed :loop; tracked separately.
    printf '%s' "$1" | sed 's/[[:space:]]*$//' | sed -e '/./,$!d' | sed -e :loop -e '/^\n*$/{$d;N;b loop}'
}

SNIPPET_NORM="$(normalize "$SNIPPET_BODY")"

extract_block() {
    local file="$1"
    node "$SCRIPT_DIR/lib/sentinel-blocks-cli.js" extract "$file" "$BEGIN_SENTINEL" "$END_SENTINEL" # verify-no-console-flash: allow — on-demand sync verifier, not session-hot-path
}

# Insert sentinel block into a consumer file that does not yet have it.
# Placement (DR-6): immediately after the END of the first found adjacent sentinel block
# (e.g. reviewer-calibration, docs-checker-consumption). If none found, append before
# any trailing ## examples section or at end of file.
insert_block() {
    local file="$1"
    local body="$2"
    "$PYTHON_BIN" - "$file" "$BEGIN_SENTINEL" "$END_SENTINEL" "$body" <<'PYEOF' # verify-no-console-flash: allow — on-demand sync verifier --fix mode, not session-hot-path
import sys, pathlib, re

fpath   = pathlib.Path(sys.argv[1])
begin   = sys.argv[2]
end     = sys.argv[3]
body    = sys.argv[4]

block = begin + "\n" + (body if body.endswith("\n") else body + "\n") + end + "\n"

lines = fpath.read_text(encoding="utf-8").splitlines(keepends=True)

# Look for an existing adjacent sentinel END line (any <!-- END ... --> pattern, not our own).
# We insert our block immediately after the first such END found, but only if it belongs
# to a different sentinel (not our own BEGIN/END).
insert_after = -1
end_pattern = re.compile(r'^\s*<!--\s*END\s+(?!quota-self-detect-preamble)')
for i, line in enumerate(lines):
    if end_pattern.match(line):
        insert_after = i
        break

if insert_after >= 0:
    # Review: code-reviewer — removed spurious "\n" prefix; block already starts on a new line so one blank line is enough.
    out = lines[:insert_after+1] + [block] + lines[insert_after+1:]
else:
    # Fall back: insert before the first "## Examples" or trailing examples heading,
    # or before a DONE-preamble sentinel, or at end of file.
    examples_pattern = re.compile(r'^\s*##\s+(Examples?|example)', re.IGNORECASE)
    done_pattern = re.compile(r'<!--\s*BEGIN.*done.*preamble', re.IGNORECASE)
    insert_before = len(lines)
    for i, line in enumerate(lines):
        if examples_pattern.match(line) or done_pattern.match(line):
            insert_before = i
            break
    # Review: code-reviewer — sibling sweep of F6 double-newline fix; same pattern as insert_after branch.
    out = lines[:insert_before] + [block] + lines[insert_before:]

fpath.write_text("".join(out), encoding="utf-8")
PYEOF
}

# Rewrite an existing sentinel block body in-place (content between BEGIN and END).
rewrite_block() {
    local file="$1"
    local body="$2"
    "$PYTHON_BIN" - "$file" "$BEGIN_SENTINEL" "$END_SENTINEL" "$body" <<'PYEOF' # verify-no-console-flash: allow — on-demand sync verifier --fix mode, not session-hot-path
import sys, pathlib

fpath = pathlib.Path(sys.argv[1])
begin = sys.argv[2]
end   = sys.argv[3]
body  = sys.argv[4]

lines = fpath.read_text(encoding="utf-8").splitlines(keepends=True)
out = []
in_block = False
for line in lines:
    stripped = line.rstrip("\r\n")
    if stripped == begin:
        out.append(line)
        out.append(body if body.endswith("\n") else body + "\n")
        in_block = True
        continue
    if stripped == end:
        in_block = False
        out.append(line)
        continue
    if not in_block:
        out.append(line)

fpath.write_text("".join(out), encoding="utf-8")
PYEOF
}

EXIT_CODE=0

for consumer in "${CONSUMERS[@]}"; do
    if [ ! -f "$consumer" ]; then
        # Already warned in find_consumers; skip silently in verify/fix pass.
        continue
    fi

    # Check if BEGIN sentinel is present.
    has_begin=0
    if awk -v s="$BEGIN_SENTINEL" '
        { stripped = $0; gsub(/^[[:space:]]+|[[:space:]]+$/, "", stripped); if (index(stripped, s) && stripped == s) { found=1; exit } }
        END { exit !found }
    ' "$consumer" 2>/dev/null; then
        has_begin=1
    fi

    if [ "$has_begin" -eq 0 ]; then
        if [ "$MODE" = "--fix" ]; then
            insert_block "$consumer" "$SNIPPET_BODY"
            echo "INSERTED     $consumer"
        else
            echo "MISSING      $consumer"
            EXIT_CODE=1
        fi
        continue
    fi

    # BEGIN present — check END.
    if ! grep -qF "$END_SENTINEL" "$consumer"; then
        echo "MISSING_END  $consumer"
        EXIT_CODE=1
        continue
    fi

    # Extract and compare block content.
    BLOCK_CONTENT="$(extract_block "$consumer")"
    BLOCK_NORM="$(normalize "$BLOCK_CONTENT")"

    if [ "$BLOCK_NORM" = "$SNIPPET_NORM" ]; then
        echo "OK           $consumer"
    else
        if [ "$MODE" = "--fix" ]; then
            rewrite_block "$consumer" "$SNIPPET_BODY"
            echo "FIXED        $consumer"
        else
            echo "MISMATCH     $consumer"
            EXIT_CODE=1
        fi
    fi
done

exit $EXIT_CODE
