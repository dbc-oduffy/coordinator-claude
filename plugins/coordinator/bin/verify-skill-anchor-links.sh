#!/usr/bin/env bash
# verify-skill-anchor-links.sh — Check that super-skill SKILL.md citations of
# `CLAUDE.md § <section>` resolve against the project-level coordinator/CLAUDE.md.
#
# A citation is OK when:
#   - the cited section exists as a `## <section>` or `### <section>` heading in
#     coordinator/CLAUDE.md, OR
#   - the citing line explicitly qualifies the link as global by including
#     `~/.claude/CLAUDE.md` or the literal word "global" in the same line.
#
# A citation is DEAD when neither condition holds — marketplace consumers walking
# the super-skill will hit an unresolvable anchor.
#
# Usage:
#   verify-skill-anchor-links.sh           Verify all super-skill anchors. Exit non-zero on any DEAD.
#   verify-skill-anchor-links.sh --list    List the super-skill files scanned.
#
# Authoritative consumer list lives in HARDCODED_CONSUMERS below; extend it when a
# new super-skill ships that anchors into CLAUDE.md.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ]; then
    PLUGIN_ROOT="$CLAUDE_PLUGIN_ROOT"
else
    PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
fi

CLAUDE_MD="$PLUGIN_ROOT/CLAUDE.md"

if [ ! -f "$CLAUDE_MD" ]; then
    echo "ERROR: project-level CLAUDE.md not found at $CLAUDE_MD" >&2
    exit 2
fi

# Super-skills that anchor into CLAUDE.md. Extend as new super-skills ship.
HARDCODED_CONSUMERS=(
    "$PLUGIN_ROOT/skills/plan/SKILL.md"
    "$PLUGIN_ROOT/skills/review/SKILL.md"
    "$PLUGIN_ROOT/skills/review-code/SKILL.md"
)

MODE="${1:-verify}"

if [ "$MODE" = "--list" ]; then
    for f in "${HARDCODED_CONSUMERS[@]}"; do
        printf '%s\n' "$f"
    done
    exit 0
fi

# Build the set of valid section names (## and ### headings) from CLAUDE.md.
# Output one section name per line, trimmed.
VALID_SECTIONS="$(awk '
    /^### / { sub(/^### /, ""); print; next }
    /^## /  { sub(/^## /,  ""); print; next }
' "$CLAUDE_MD")"

EXIT_CODE=0
TOTAL=0
DEAD=0
OK=0
QUALIFIED=0

# Normalize a section name for comparison: trim trailing punctuation/whitespace.
normalize() {
    printf '%s' "$1" | sed -e 's/[[:space:]]*$//' -e 's/[.,;:]*$//'
}

# is_qualified_global LINE — return 0 if the line marks the citation as global.
is_qualified_global() {
    case "$1" in
        *'~/.claude/CLAUDE.md'*) return 0 ;;
        *'global '*'CLAUDE.md'*) return 0 ;;
        *'(global'*) return 0 ;;
    esac
    return 1
}

# resolve_anchors LINE — for each `§ ...` occurrence in LINE, find the longest
# valid heading from VALID_SECTIONS that is a prefix of the post-§ text. Emits
# `MATCH <heading>` per matched anchor and `MISS <citation-snippet>` per
# unmatched. The VALID_SECTIONS list is passed via env.
resolve_anchors() {
    local line="$1"
    # CI/verification tool (run from /workweek-complete and on demand), not the
    # interactive per-prompt/per-commit hot-path; the per-line python spawn never
    # fires during normal EM sessions, so console-flash suppression is unnecessary.
    VALID_SECTIONS_ENV="$VALID_SECTIONS" "${PYTHON_BIN:-python3}" - "$line" <<'PYEOF'  # verify-no-console-flash: allow
import os, re, sys
line = sys.argv[1]
sections = [s for s in os.environ.get("VALID_SECTIONS_ENV", "").splitlines() if s.strip()]
# Sort longest-first so prefix matching prefers the most specific heading.
sections.sort(key=len, reverse=True)

# Find every `§ ` occurrence and inspect the text after it.
for m in re.finditer(r'§\s+', line):
    tail = line[m.end():]
    # Strip leading whitespace (already handled by \s+) and consider up to a hard
    # terminator: underscore (italic close), end of line, or paragraph anchor.
    # The heading itself may contain em-dashes and commas, so we test by prefix
    # rather than pre-truncating.
    hard_end = len(tail)
    for term in ['_', '\n']:
        i = tail.find(term)
        if i != -1 and i < hard_end:
            hard_end = i
    candidate_zone = tail[:hard_end]
    # Find longest section that is a prefix of candidate_zone.
    matched = None
    for sec in sections:
        if candidate_zone.startswith(sec):
            # Require the next char (if any) to NOT be alphanumeric — avoid
            # matching "Core" against "Core Principles" if "Core" were a heading.
            nxt = candidate_zone[len(sec):len(sec)+1]
            if nxt == "" or not nxt.isalnum():
                matched = sec
                break
    if matched:
        print(f"MATCH\t{matched}")
    else:
        snippet = candidate_zone.strip()[:60]
        # Drop trailing punctuation for cleaner reporting.
        snippet = re.sub(r'[.,;:\s]+$', '', snippet)
        print(f"MISS\t{snippet}")
PYEOF
}

PYTHON_BIN="$(command -v python3 || command -v python || true)"
if [ -z "$PYTHON_BIN" ]; then
    echo "ERROR: neither python3 nor python found on PATH" >&2
    exit 2
fi
export PYTHON_BIN

for consumer in "${HARDCODED_CONSUMERS[@]}"; do
    if [ ! -f "$consumer" ]; then
        echo "SKIPPED (not found): $consumer" >&2
        continue
    fi

    # Read each line; for any line containing "CLAUDE.md §", extract anchors.
    line_no=0
    while IFS= read -r line || [ -n "$line" ]; do
        line_no=$((line_no + 1))
        case "$line" in
            *'CLAUDE.md §'*) ;;
            *) continue ;;
        esac

        qualified=0
        if is_qualified_global "$line"; then
            qualified=1
        fi

        while IFS=$'\t' read -r kind value; do
            [ -z "$kind" ] && continue
            TOTAL=$((TOTAL + 1))
            if [ "$qualified" = "1" ]; then
                QUALIFIED=$((QUALIFIED + 1))
                printf 'QUALIFIED  %s:%d  § %s\n' "${consumer#$PLUGIN_ROOT/}" "$line_no" "$value"
            elif [ "$kind" = "MATCH" ]; then
                OK=$((OK + 1))
                printf 'OK         %s:%d  § %s\n' "${consumer#$PLUGIN_ROOT/}" "$line_no" "$value"
            else
                DEAD=$((DEAD + 1))
                EXIT_CODE=1
                printf 'DEAD       %s:%d  § %s\n' "${consumer#$PLUGIN_ROOT/}" "$line_no" "$value"
            fi
        done < <(resolve_anchors "$line")
    done < "$consumer"
done

echo
echo "summary: total=$TOTAL ok=$OK qualified=$QUALIFIED dead=$DEAD"
exit $EXIT_CODE
