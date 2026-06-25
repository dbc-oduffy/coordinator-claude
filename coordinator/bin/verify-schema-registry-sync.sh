#!/usr/bin/env bash
# verify-schema-registry-sync.sh — SSOT drift gate: every schemas/*.yaml with an applies_to:
# must have its glob represented as a value in bin/query-records.js TYPE_TO_GLOB.
#
# Purpose: Prevents the two-registry duplication problem (Substrate Fact #6) from silently
# drifting. Adding a new schema without updating query-records.js TYPE_TO_GLOB causes this
# script to fail loudly, making "add schema, forget query-records" impossible.
#
# Spec backlink: docs/plans/2026-06-23-deliverable-type-schema-taxonomy.md § Decision 3 + C4
#
# Exit codes:
#   0 — all schemas with applies_to: have their glob covered in TYPE_TO_GLOB
#   1 — one or more schemas with applies_to: are NOT covered in TYPE_TO_GLOB
#
# Usage:
#   verify-schema-registry-sync.sh
#   bash plugins/coordinator/bin/verify-schema-registry-sync.sh
#
# Portability (DR-148): bash >= 4 guard only if bash-4 features are used. This script
# uses only POSIX-ish constructs (while read, grep, awk) so no bash-4 guard is needed.
# No sed -i, realpath, grep -P, date -d, or date +%N — all BSD-coreutils compatible.
#
# Negative-spec (hard-won):
#   - Does NOT check type-name equality — only checks that the applies_to glob VALUE
#     appears verbatim in the TYPE_TO_GLOB block of query-records.js.
#   - Deliberate divergences (cross-repo-memo uses a different glob for bracket-class
#     reasons; lesson/completion use different type names) pass because their globs DO
#     appear in TYPE_TO_GLOB (cross-repo-memo glob: cross-repo/inbox/*.md;
#     lesson/completion globs: state/lessons.md / archive/completed/*/*.md).
#   - handoff-ledger is synthetic (no schema file) — not checked here.
#   - debt/bug/improvement use .yaml SSOT, not schema files — not checked here.

set -uo pipefail

# ---------------------------------------------------------------------------
# Resolve script and repo root portably (no realpath — BSD-safe)
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

SCHEMAS_DIR="${PLUGIN_ROOT}/schemas"
QUERY_RECORDS="${PLUGIN_ROOT}/bin/query-records.js"

# ---------------------------------------------------------------------------
# Sanity guards
# ---------------------------------------------------------------------------
if [[ ! -d "$SCHEMAS_DIR" ]]; then
  echo "verify-schema-registry-sync: ERROR — schemas dir not found: $SCHEMAS_DIR" >&2
  exit 1
fi

if [[ ! -f "$QUERY_RECORDS" ]]; then
  echo "verify-schema-registry-sync: ERROR — query-records.js not found: $QUERY_RECORDS" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Extract all single-quoted glob-shaped values from query-records.js that
# contain path separators (to avoid matching type-names like 'handoff').
# ---------------------------------------------------------------------------
# Review: code-reviewer (S2-F2) — deleted dead awk block that was immediately
# overwritten by this grep -o line; kept only the live extractor.
REGISTERED_GLOBS="$(grep -o "'[^']*[/*][^']*'" "$QUERY_RECORDS" | tr -d "'" | sort -u)"

# ---------------------------------------------------------------------------
# Deliberate divergences — schemas whose applies_to: intentionally differs
# from the TYPE_TO_GLOB value (documented in query-records.js inline comments).
# These are checked by schema FILENAME, not by glob value.
#
# cross-repo-memo.yaml: applies_to uses bracket-class [0-9]* which
#   filePatternToRegex in query-records.js escapes as literals (no bracket
#   class support); TYPE_TO_GLOB uses *.md + memo-shape guard instead.
#   Spec: query-records.js inline comment at the cross-repo-memo entry.
#
# handoff-archived.yaml: applies_to is archive/handoffs/*.md (flat) but
#   TYPE_TO_GLOB uses archive/handoffs/**/*.md (recursive) to handle the
#   2026-06-18 month-foldering (archive/handoffs/YYYY-MM/) structure.
#   Spec: query-records.js inline comment at the handoff-archived entry.
# ---------------------------------------------------------------------------
DELIBERATE_DIVERGENCES="cross-repo-memo.yaml handoff-archived.yaml"

# ---------------------------------------------------------------------------
# Scan each schema for applies_to: and check coverage
# ---------------------------------------------------------------------------
FAIL=0
CHECKED=0
MISSING=()

while IFS= read -r schema_file; do
  schema_name="$(basename "$schema_file")"

  # Skip documented deliberate divergences
  skip=0
  for exempt in $DELIBERATE_DIVERGENCES; do
    if [[ "$schema_name" = "$exempt" ]]; then
      skip=1
      break
    fi
  done
  [[ "$skip" -eq 1 ]] && continue

  # Extract applies_to value: strip the key prefix and surrounding quotes/whitespace
  applies_to="$(grep '^applies_to:' "$schema_file" | head -1 | awk -F': ' '{print $2}' | tr -d '"' | tr -d "'" | tr -d '[:space:]')"

  [[ -z "$applies_to" ]] && continue   # schema has no applies_to — skip (no enumeration needed)

  CHECKED=$((CHECKED + 1))

  # Check if this glob value appears in the registered globs set
  if echo "$REGISTERED_GLOBS" | grep -qF "$applies_to"; then
    : # covered
  else
    MISSING+=("${schema_name}: applies_to=${applies_to}")
    FAIL=1
  fi
done < <(find "$SCHEMAS_DIR" -maxdepth 1 -name '*.yaml' | sort)

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
if [[ $FAIL -eq 0 ]]; then
  echo "verify-schema-registry-sync: OK — all ${CHECKED} schema applies_to globs are covered in TYPE_TO_GLOB"
  exit 0
else
  echo "verify-schema-registry-sync: FAIL — ${#MISSING[@]} schema(s) with applies_to: NOT covered in query-records.js TYPE_TO_GLOB:" >&2
  for item in "${MISSING[@]}"; do
    echo "  MISSING: $item" >&2
  done
  echo "" >&2
  echo "Fix: add the missing glob(s) to TYPE_TO_GLOB in bin/query-records.js" >&2
  echo "Spec: docs/plans/2026-06-23-deliverable-type-schema-taxonomy.md § Decision 3" >&2
  exit 1
fi
