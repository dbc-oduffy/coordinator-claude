#!/usr/bin/env bash
# owner-emit-example.sh — AC6: verify the owner-namespace env seam emits synthetic
# owners to a throwaway dir and leaves committed schema/ byte-identical.
#
# Run from anywhere; the script cd's to the package root.
# Exits 0 with a PASS line on success; non-zero with a diagnostic on failure.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PACKAGE_DIR"

# --- Temp dir, cleaned on exit -----------------------------------------------
tmp="$(mktemp -d)"
cleanup() { rm -rf "$tmp"; }
trap cleanup EXIT

# --- 1. Snapshot checksum of committed schema BEFORE emit --------------------
committed_schema="schema/cockpit-contract.schema.json"
if [[ ! -f "$committed_schema" ]]; then
  echo "FAIL: committed schema not found at $committed_schema" >&2
  exit 1
fi
before_sum="$(shasum -a 256 "$committed_schema" | awk '{print $1}')"

# --- 2. Run example emit to throwaway temp dir -------------------------------
# Review: code-reviewer — use locally-pinned binary via pnpm exec, not npx (avoids network/version ambiguity)
COCKPIT_OWNER_NAMESPACES='example-org,example-team' \
  COCKPIT_SCHEMA_OUT_DIR="$tmp" \
  pnpm exec tsx scripts/emit-schema.ts

emitted="$tmp/cockpit-contract.schema.json"
if [[ ! -f "$emitted" ]]; then
  echo "FAIL: emitted bundle not found at $emitted" >&2
  exit 1
fi

# --- 3. Assert emitted file contains example orgs and NOT real orgs ----------
if ! grep -q 'example-org' "$emitted"; then
  echo "FAIL: 'example-org' not found in emitted schema" >&2
  exit 1
fi

if ! grep -q 'example-team' "$emitted"; then
  echo "FAIL: 'example-team' not found in emitted schema" >&2
  exit 1
fi

if grep -q 'dbc-oduffy' "$emitted"; then
  echo "FAIL: 'dbc-oduffy' found in emitted schema — real owner leaked into example emit" >&2
  exit 1
fi

if grep -q 'Example-Interactive' "$emitted"; then
  echo "FAIL: 'Example-Interactive' found in emitted schema — real owner leaked into example emit" >&2
  exit 1
fi

# --- 4. Assert committed schema/ is byte-identical (checksum unchanged) ------
after_sum="$(shasum -a 256 "$committed_schema" | awk '{print $1}')"
if [[ "$before_sum" != "$after_sum" ]]; then
  echo "FAIL: committed schema checksum changed — example emit wrote to committed schema/" >&2
  echo "  before: $before_sum" >&2
  echo "  after:  $after_sum" >&2
  exit 1
fi

# --- 5. PASS -----------------------------------------------------------------
echo "PASS: owner-emit-example — synthetic owners emitted to temp dir, committed schema/ unchanged"
