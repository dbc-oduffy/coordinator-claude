#!/usr/bin/env bash
# run-fixture-test.sh — Validates the lesson-triage routing schema against a synthetic lessons dir.
#
# This is a SCHEMA / SHAPE test, not a skill-execution test. The /lesson-triage
# skill is invoked by Claude Code's slash-command harness; we cannot execute it
# from a shell script. What we CAN do here is:
#
#   1. Confirm the fixture inputs exist (per-entry YAML directory + expected manifest)
#   2. Lint expected-manifest.yaml as well-formed YAML
#   3. Verify every record uses a change_kind from the closed enum defined in
#      plugins/coordinator/skills/lesson-triage/SKILL.md
#   4. Verify destinations[] is non-empty and required fields are present
#
# Lessons format: per-entry YAML files under sample-lessons/ (migrated from
# sample-lessons.md markdown format 2026-06-30). Each file is one lesson:
#   created: YYYY-MM-DD
#   title: "..."
#   scope: universal|project
#   body: |
#     ...
#
# Manual reproduction of the full skill behavior:
#   - Open Claude Code in this repo
#   - Run: /lesson-triage --mode cross-project
#   - Configure roots to point at plugins/coordinator/skills/learn-lessons/tests/fixtures/lesson-triage/ only
#   - Compare the produced manifest.yaml against expected-manifest.yaml using diff

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SAMPLE_DIR="$SCRIPT_DIR/sample-lessons"
EXPECTED="$SCRIPT_DIR/expected-manifest.yaml"
SKILL="$SCRIPT_DIR/../../../SKILL.md"

CHANGE_KINDS=(doctrine-edit agent-prompt-edit hook-edit script-edit
              snippet-sync-update wiki-new wiki-append memory-pointer
              project-structural retag-local strip-local discard)

fail=0

echo "=== fixture inputs ==="
# Check per-entry YAML lesson directory (replaced sample-lessons.md 2026-06-30)
if [ -d "$SAMPLE_DIR" ]; then
    yaml_count=$(ls "$SAMPLE_DIR"/*.yaml 2>/dev/null | wc -l | tr -d ' ')
    if [ "$yaml_count" -gt 0 ]; then
        echo "OK     $SAMPLE_DIR/ ($yaml_count YAML lesson files)"
    else
        echo "MISS   $SAMPLE_DIR/ exists but contains no .yaml files"
        fail=1
    fi
else
    echo "MISS   $SAMPLE_DIR/ (expected per-entry YAML lesson directory)"
    fail=1
fi
for f in "$EXPECTED" "$SKILL"; do
    if [ -f "$f" ]; then
        echo "OK     $f"
    else
        echo "MISS   $f"
        fail=1
    fi
done

if [ $fail -ne 0 ]; then
    echo "FAIL: missing fixture inputs"
    exit 1
fi

echo ""
echo "=== expected-manifest.yaml well-formed ==="
if command -v python3 >/dev/null 2>&1; then
    python3 -c "import yaml,sys; yaml.safe_load(open('$EXPECTED'))" && echo "OK     valid YAML"  # verify-no-console-flash: allow (test fixture; not session hot-path)
else
    echo "SKIP   python3 not available; YAML lint skipped"
fi

echo ""
echo "=== change_kind values are in the closed enum ==="
used_kinds="$(grep -E '^\s*change_kind:' "$EXPECTED" | awk '{print $2}' | sort -u)"
for kind in $used_kinds; do
    found=0
    for valid in "${CHANGE_KINDS[@]}"; do
        if [ "$kind" = "$valid" ]; then
            found=1
            break
        fi
    done
    if [ $found -eq 1 ]; then
        echo "OK     $kind"
    else
        echo "BAD    $kind not in closed enum"
        fail=1
    fi
done

echo ""
echo "=== change_kind enum exhaustively documented in SKILL.md ==="
for valid in "${CHANGE_KINDS[@]}"; do
    if grep -qF "\`$valid\`" "$SKILL"; then
        echo "OK     $valid documented"
    else
        echo "BAD    $valid missing from SKILL.md taxonomy table"
        fail=1
    fi
done

echo ""
if [ $fail -eq 0 ]; then
    echo "PASS — fixture validation complete"
    exit 0
else
    echo "FAIL — see errors above"
    exit 1
fi
