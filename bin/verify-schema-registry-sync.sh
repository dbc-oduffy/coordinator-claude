#!/usr/bin/env bash
# verify-schema-registry-sync.sh — SSOT drift gate: every schemas/*.yaml with an applies_to:
# must have a corresponding query --type recognised by bin/query-records.js at runtime.
#
# Purpose: Prevents the two-registry duplication problem (Substrate Fact #6) from silently
# drifting. Adding a new schema without wiring it into query-records.js TYPE_TO_GLOB (via
# _buildTypeToGlob schema derivation or an explicit supplement) causes this script to fail
# loudly, making "add schema, forget query-records" impossible.
#
# How the check works (updated 2026-06-26):
#   For each schemas/*.yaml that carries an applies_to: field, derive the expected
#   query --type name (schema filename sans .yaml, with two explicit renames for legacy
#   reasons: completion-entry→completion, lesson-entry→lesson). Then invoke:
#     node bin/query-records.js --type <type> --format json --limit 1
#   A type that exists in TYPE_TO_GLOB exits 0 (returns [] if no records on disk).
#   An unrecognised type exits 1 ("Unknown type: ..."). The exit code is the coverage signal.
#
#   This approach is robust to refactors because it asks query-records.js itself what it
#   supports, rather than grepping its source for hardcoded string literals. TYPE_TO_GLOB is
#   now built dynamically from loadSchemas() (_buildTypeToGlob in query-records.js:173), so
#   there are no string literals to grep — the prior grep -o approach produced 12 false-positive
#   MISSING reports for all dynamically-derived schema types.
#
# Spec backlink: docs/plans/2026-06-23-deliverable-type-schema-taxonomy.md § Decision 3 + C4
#
# Exit codes:
#   0 — all schemas with applies_to: have a recognised --type in query-records.js
#   1 — one or more schemas with applies_to: are NOT recognised by query-records.js
#
# Usage:
#   verify-schema-registry-sync.sh
#   bash plugins/coordinator/bin/verify-schema-registry-sync.sh
#
# Portability (DR-148): bash >= 4 guard only if bash-4 features are used. This script
# uses only POSIX-ish constructs (while read, grep, case) so no bash-4 guard is needed.
# No sed -i, realpath, grep -P, date -d, or date +%N — all BSD-coreutils compatible.
#
# Negative-spec (hard-won):
#   - Does NOT compare applies_to glob values — only checks that a --type for the schema
#     is registered in TYPE_TO_GLOB (i.e. query-records.js --type <name> exits 0).
#   - Deliberate divergences (cross-repo-memo and handoff-archived) are exempted because
#     their applies_to: globs intentionally differ from the TYPE_TO_GLOB override values
#     (documented inline below and in query-records.js). Their query types DO exist and
#     would pass the runtime check; the exemption is kept for documentation consistency.
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
# Schema filename → query --type name mapping.
#
# Most schemas: type name = schema filename without .yaml extension.
# Two exceptions (legacy type-name mismatches documented in query-records.js ~L100):
#   completion-entry → completion  (legacy --type name predates the schema rename)
#   lesson-entry     → lesson      (same reason; lesson is handled as a supplement type)
# ---------------------------------------------------------------------------
_schema_to_query_type() {
  local schema_name="$1"   # e.g. "completion-entry.yaml"
  local base="${schema_name%.yaml}"
  case "$base" in
    completion-entry) echo "completion" ;;
    lesson-entry)     echo "lesson"     ;;
    *)                echo "$base"      ;;
  esac
}

# ---------------------------------------------------------------------------
# Deliberate divergences — schemas whose applies_to: intentionally differs
# from the TYPE_TO_GLOB override value (documented in query-records.js inline
# comments). These types DO exist in TYPE_TO_GLOB and would pass the runtime
# check; they are exempted here to document the intentional glob mismatch and
# avoid confusion between "type not wired" and "glob intentionally different".
#
# cross-repo-memo.yaml: applies_to uses bracket-class [0-9]* which
#   filePatternToRegex in query-records.js escapes as literals; TYPE_TO_GLOB
#   uses *.md + memo-shape guard instead.
#
# handoff-archived.yaml: applies_to is archive/handoffs/*.md (flat) but
#   TYPE_TO_GLOB uses archive/handoffs/**/*.md (recursive) to handle the
#   2026-06-18 month-foldering (archive/handoffs/YYYY-MM/) structure.
# ---------------------------------------------------------------------------
DELIBERATE_DIVERGENCES="cross-repo-memo.yaml handoff-archived.yaml"

# ---------------------------------------------------------------------------
# Scan each schema for applies_to: and check coverage via query-records.js
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

  # Only process schemas that declare applies_to:
  applies_to="$(grep '^applies_to:' "$schema_file" | head -1 | awk -F': ' '{print $2}' | tr -d '"' | tr -d "'" | tr -d '[:space:]')"
  [[ -z "$applies_to" ]] && continue   # schema has no applies_to — skip

  CHECKED=$((CHECKED + 1))

  # Derive the query --type name from the schema filename
  query_type="$(_schema_to_query_type "$schema_name")"

  # Ask query-records.js itself whether this type is registered in TYPE_TO_GLOB.
  # Exit 0 = type known (returns [] if no records on disk, which is fine).
  # Exit 1 = "Unknown type: ..." — the type is missing from TYPE_TO_GLOB.
  if node "$QUERY_RECORDS" --type "$query_type" --format json --limit 1 > /dev/null 2>&1; then # verify-no-console-flash: allow — schema sync check only, not on session hot-path; node.exe does not produce a console flash
    : # covered
  else
    MISSING+=("${schema_name}: type='${query_type}' not recognised by query-records.js (applies_to=${applies_to})")
    FAIL=1
  fi
done < <(find "$SCHEMAS_DIR" -maxdepth 1 -name '*.yaml' | sort)

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
if [[ $FAIL -eq 0 ]]; then
  echo "verify-schema-registry-sync: OK — all ${CHECKED} schema applies_to types are recognised by query-records.js"
  exit 0
else
  # Review: code-reviewer F4 — updated message to reflect the runtime-dispatch approach
  # (node query-records.js --type <name>) rather than the old TYPE_TO_GLOB literal grep.
  echo "verify-schema-registry-sync: FAIL — ${#MISSING[@]} schema(s) with applies_to: NOT recognised by query-records.js runtime:" >&2
  for item in "${MISSING[@]}"; do
    echo "  MISSING: $item" >&2
  done
  echo "" >&2
  echo "Fix: ensure the schema type is registered in _buildTypeToGlob() or its supplements in bin/query-records.js" >&2
  echo "Spec: docs/plans/2026-06-23-deliverable-type-schema-taxonomy.md § Decision 3" >&2
  exit 1
fi
