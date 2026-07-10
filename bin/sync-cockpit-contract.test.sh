#!/usr/bin/env bash
# bin/sync-cockpit-contract.test.sh — Tests for sync-cockpit-contract.sh
#
# Purpose: verifies the vendor-sync staleness check exits 0 on matching versions,
# exits non-zero with a DRIFT message on mismatched versions, and handles error
# conditions (missing vendored file, missing jq, missing canonical) loudly.
#
# Spec backlink: state/handoffs/2026-06-22_230001_roadmap-cockpit-contract-ext-2026-06-22-tc-1.md
# § AC — vendor-sync staleness-check script authored, tested, fails loud on a planted stale-stamp fixture.
#
# Intentionally `set -uo pipefail` WITHOUT `-e`: each case captures `$?` manually so the
# harness continues on failure to run all assertions.
set -uo pipefail

# Require bash >= 4 (coordinator baseline — DR-148).
if (( BASH_VERSINFO[0] < 4 )); then
  echo "ERROR: bash >= 4 required (found ${BASH_VERSION}). On macOS: brew install bash" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="${SCRIPT_DIR}/sync-cockpit-contract.sh"
CANONICAL="${SCRIPT_DIR}/../cockpit-contract/schema/cockpit-contract.schema.json"

PASS=0
FAIL=0

_ok()  { echo "  PASS: $1"; PASS=$(( PASS + 1 )); }
_bad() { echo "  FAIL: $1 — $2"; FAIL=$(( FAIL + 1 )); }

TMPROOT="$(mktemp -d)"
trap 'rm -rf "$TMPROOT"' EXIT

# Read the canonical version from the real schema (source of truth).
CANONICAL_VERSION="$(jq -r '.version // empty' "$CANONICAL")"

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

# Write a fake schema JSON with the given version stamp to a temp path.
_fixture() {
    local version="$1"
    local path="${TMPROOT}/fixture-${version//[^0-9a-zA-Z._-]/_}.json"
    printf '{"$schema":"https://json-schema.org/draft/2020-12/schema","version":"%s","title":"fixture"}\n' "$version" > "$path"
    echo "$path"
}

# ---------------------------------------------------------------------------
# Test A: matching version → exit 0, "in sync" message
# ---------------------------------------------------------------------------
echo "=== Test A: matching version → exit 0 ==="
MATCH_FIXTURE="$(_fixture "${CANONICAL_VERSION}")"
OUT="$(bash "$SCRIPT" --vendored "$MATCH_FIXTURE" 2>&1)"; RC=$?
[[ "$RC" -eq 0 ]] && _ok "A0: exit 0 on matching version" || _bad "A0: exit 0" "rc=$RC, out=$OUT"
[[ "$OUT" == *"in sync"* ]] && _ok "A1: output contains 'in sync'" || _bad "A1: in sync message" "out=$OUT"
[[ "$OUT" == *"v${CANONICAL_VERSION}"* ]] && _ok "A2: output contains canonical version v${CANONICAL_VERSION}" || _bad "A2: version in message" "out=$OUT"

# ---------------------------------------------------------------------------
# Test B: stale vendored stamp (older version) → exit 1, DRIFT message
# ---------------------------------------------------------------------------
echo "=== Test B: stale vendored stamp → exit 1 + DRIFT message ==="
STALE_FIXTURE="$(_fixture "0.0.1")"
OUT="$(bash "$SCRIPT" --vendored "$STALE_FIXTURE" 2>&1)"; RC=$?
[[ "$RC" -eq 1 ]] && _ok "B0: exit 1 on stale version" || _bad "B0: exit 1" "rc=$RC, out=$OUT"
[[ "$OUT" == *"DRIFT"* ]] && _ok "B1: output contains 'DRIFT'" || _bad "B1: DRIFT keyword" "out=$OUT"
[[ "$OUT" == *"canonical v${CANONICAL_VERSION}"* ]] && _ok "B2: DRIFT message names canonical version" || _bad "B2: canonical version in DRIFT" "out=$OUT"
[[ "$OUT" == *"vendored v0.0.1"* ]] && _ok "B3: DRIFT message names vendored version" || _bad "B3: vendored version in DRIFT" "out=$OUT"
[[ "$OUT" == *"re-vendor"* ]] && _ok "B4: DRIFT message contains actionable 're-vendor' instruction" || _bad "B4: re-vendor instruction" "out=$OUT"

# ---------------------------------------------------------------------------
# Test C: future version stamp (newer than canonical) → exit 1, DRIFT message
# ---------------------------------------------------------------------------
echo "=== Test C: future vendored stamp → exit 1 + DRIFT message ==="
FUTURE_FIXTURE="$(_fixture "99.99.99")"
OUT="$(bash "$SCRIPT" --vendored "$FUTURE_FIXTURE" 2>&1)"; RC=$?
[[ "$RC" -eq 1 ]] && _ok "C0: exit 1 on future/mismatched version" || _bad "C0: exit 1" "rc=$RC, out=$OUT"
[[ "$OUT" == *"DRIFT"* ]] && _ok "C1: DRIFT message emitted for future stamp" || _bad "C1: DRIFT keyword" "out=$OUT"

# ---------------------------------------------------------------------------
# Test D: vendored file missing → exit 1, DRIFT message naming the path
# ---------------------------------------------------------------------------
echo "=== Test D: vendored file missing → exit 1 + DRIFT ==="
MISSING_PATH="${TMPROOT}/does-not-exist.json"
OUT="$(bash "$SCRIPT" --vendored "$MISSING_PATH" 2>&1)"; RC=$?
[[ "$RC" -eq 1 ]] && _ok "D0: exit 1 on missing vendored file" || _bad "D0: exit 1" "rc=$RC, out=$OUT"
[[ "$OUT" == *"DRIFT"* ]] && _ok "D1: DRIFT message on missing file" || _bad "D1: DRIFT on missing file" "out=$OUT"
[[ "$OUT" == *"$MISSING_PATH"* ]] && _ok "D2: missing path named in message" || _bad "D2: path in message" "out=$OUT"

# ---------------------------------------------------------------------------
# Test E: --vendored omitted → exit 2 + usage hint
# ---------------------------------------------------------------------------
echo "=== Test E: --vendored omitted → exit 2 ==="
OUT="$(bash "$SCRIPT" 2>&1)"; RC=$?
[[ "$RC" -eq 2 ]] && _ok "E0: exit 2 when --vendored omitted" || _bad "E0: exit 2" "rc=$RC, out=$OUT"
[[ "$OUT" == *"--vendored"* ]] && _ok "E1: error message names --vendored flag" || _bad "E1: flag hint" "out=$OUT"

# ---------------------------------------------------------------------------
# Test F: canonical overridden via --canonical flag
# ---------------------------------------------------------------------------
echo "=== Test F: --canonical flag overrides default ==="
CUSTOM_CANONICAL="$(_fixture "2.0.0")"
MATCH_TO_CUSTOM="$(_fixture "2.0.0")"
OUT="$(bash "$SCRIPT" --canonical "$CUSTOM_CANONICAL" --vendored "$MATCH_TO_CUSTOM" 2>&1)"; RC=$?
[[ "$RC" -eq 0 ]] && _ok "F0: exit 0 when --canonical override matches vendored" || _bad "F0: exit 0" "rc=$RC, out=$OUT"
[[ "$OUT" == *"in sync (v2.0.0)"* ]] && _ok "F1: 'in sync' message with overridden version" || _bad "F1: in sync v2.0.0" "out=$OUT"

# ---------------------------------------------------------------------------
# Test G: COCKPIT_VENDORED env var (no flag needed)
# ---------------------------------------------------------------------------
echo "=== Test G: COCKPIT_VENDORED env var ==="
STALE_ENV_FIXTURE="$(_fixture "0.0.2")"
OUT="$(COCKPIT_VENDORED="$STALE_ENV_FIXTURE" bash "$SCRIPT" 2>&1)"; RC=$?
[[ "$RC" -eq 1 ]] && _ok "G0: exit 1 via env-var path" || _bad "G0: exit 1" "rc=$RC, out=$OUT"
[[ "$OUT" == *"DRIFT"* ]] && _ok "G1: DRIFT emitted via env-var path" || _bad "G1: DRIFT via env" "out=$OUT"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "========================================"
echo "Results: ${PASS} passed, ${FAIL} failed"
echo "========================================"
[[ "$FAIL" -eq 0 ]]
