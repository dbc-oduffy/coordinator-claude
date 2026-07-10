#!/usr/bin/env bash
# run-fixture-test.sh — Validates the Phase 2.5 undated-pass filter snippet.
#
# The filter is documented as VERBATIM Python inside
# plugins/coordinator/skills/learn-lessons/SKILL.md
# § "Central mode — undated-pass (required after delta routing)".
# This test runs that filter against a synthetic extraction and asserts both
# the happy-path (undated+universal records selected) AND the negative cases
# (non-universal undated NOT selected; dated+universal NOT selected) — locking
# filter polarity beyond the happy path.
#
# Pattern mirrors plugins/coordinator/skills/learn-lessons/tests/fixtures/lesson-triage/run-fixture-test.sh.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SAMPLE="$SCRIPT_DIR/sample-extraction.yaml"
TMP="$(mktemp -t undated-filter-XXXXXX.yaml)"
trap 'rm -f "$TMP"' EXIT

if [ ! -f "$SAMPLE" ]; then
    echo "FAIL: missing fixture input $SAMPLE" >&2
    exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "SKIP: python3 not available; cannot exercise filter snippet" >&2
    exit 0
fi

# Run a structurally-equivalent form of the VERBATIM filter snippet from
# SKILL.md § Phase 2.5. Streamed via stdin to avoid Windows/Git-Bash path
# resolution mismatches between Python's stdlib and msys-translated paths.
python3 -c " # verify-no-console-flash: allow — test fixture, not shipped
import yaml, sys
data = yaml.safe_load(sys.stdin)
records = [r for r in data.get('records', []) if r.get('undated') and r.get('tag_universal')]
data['records'] = records
yaml.safe_dump(data, sys.stdout, sort_keys=False)
" < "$SAMPLE" > "$TMP"

fail=0

# Happy path: both undated+universal records selected.
for expected_id in sample-L1 sample-L2; do
    if grep -q "id: $expected_id$" "$TMP"; then
        echo "OK     $expected_id selected (undated+universal)"
    else
        echo "BAD    $expected_id NOT selected — happy-path failure"
        fail=1
    fi
done

# Negative case (a): undated+project (non-universal) NOT selected.
if grep -q "id: sample-L3$" "$TMP"; then
    echo "BAD    sample-L3 selected — negative case (a) failed (undated+project must NOT pass)"
    fail=1
else
    echo "OK     sample-L3 rejected (undated+project — polarity correct)"
fi

# Negative case (b): dated+universal NOT selected.
if grep -q "id: sample-L4$" "$TMP"; then
    echo "BAD    sample-L4 selected — negative case (b) failed (dated+universal must NOT pass)"
    fail=1
else
    echo "OK     sample-L4 rejected (dated+universal — polarity correct)"
fi

# Negative case (c): dated+project NOT selected (neither-axis sanity).
if grep -q "id: sample-L5$" "$TMP"; then
    echo "BAD    sample-L5 selected — neither-axis case failed"
    fail=1
else
    echo "OK     sample-L5 rejected (dated+project — sanity)"
fi

# Assert selected count is exactly 2.
selected_count="$(grep -c '^[[:space:]]*- id:' "$TMP" 2>/dev/null || echo 0)"
if [ "$selected_count" = "2" ]; then
    echo "OK     selected count = 2 (matches expected)"
else
    echo "BAD    selected count = $selected_count (expected 2)"
    fail=1
fi

echo ""
if [ $fail -eq 0 ]; then
    echo "PASS — Phase 2.5 undated-pass filter snippet polarity validated"
    exit 0
else
    echo "FAIL — see errors above"
    exit 1
fi
