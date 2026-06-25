#!/usr/bin/env bash
# verify-no-console-flash: file-allow — test scaffolding; interpreter spawns run in the CI/local test harness, never the Windows interactive coordinator hot-path
# AC4 — every review-family `kind:` value present on docs/plans/*.md sidecars resolves to the
# review-sidecar schema (NOT plan.yaml), asserted against the LIVE disk census plus a captured
# snapshot of the canonical + legacy vocabulary. This is the oracle-vs-disk test (the Director of Engineering F3): it
# passes ONLY if the real surface is fixed, not a hand-sketched value list.
#
# Portable (DR-148): bash 3.2 + BSD coreutils; no grep -P, sed -i, date -d, mapfile.
set -eo pipefail
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COORD_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"          # .../coordinator
SCHEMAS="$COORD_ROOT/schemas"
SCHEMA_JS="$COORD_ROOT/bin/lib/schema.js"
# Repo root holds docs/plans. Resolve via git (works in the meta-repo AND a published consumer repo,
# regardless of how deep the plugin is nested); fall back to a fixed climb if git is unavailable.
REPO_ROOT="$(git -C "$COORD_ROOT" rev-parse --show-toplevel 2>/dev/null || true)"
[ -n "$REPO_ROOT" ] || REPO_ROOT="$(cd "$COORD_ROOT/../../.." && pwd)"
PLANS="$REPO_ROOT/docs/plans"

fail() { echo "FAIL: $*" >&2; exit 1; }

[ -d "$PLANS" ] || fail "docs/plans not found at $PLANS"
[ -f "$SCHEMA_JS" ] || fail "schema.js not found at $SCHEMA_JS"

resolve_kind() {
  # echo the schemaName matchSchema picks for a given kind value (or 'null')
  node -e "
    const s = require('$SCHEMA_JS');
    const sc = s.loadSchemas('$SCHEMAS');
    const m = s.matchSchema('docs/plans/probe.md', { kind: process.argv[1] }, sc);
    process.stdout.write(m ? m.schemaName : 'null');
  " "$1"
}

# 1) Captured snapshot (2026-06-23) — canonical role-based + legacy review-family values.
#    These MUST resolve to review-sidecar regardless of current disk contents.
SNAPSHOT="staff-eng-review eng-director-review staff-ux-review staff-game-dev-review staff-data-sci-review senior-front-end-review code-review plan-review review review-sidecar patrik-review substrate-adjudication plan-rereview"
for k in $SNAPSHOT; do
  got="$(resolve_kind "$k")"
  [ "$got" = "review-sidecar" ] || fail "snapshot kind '$k' resolved to '$got', expected review-sidecar"
done

# 2) Live disk census — every review-family kind value actually present on disk must resolve too.
#    Review-family = any kind value containing 'review' OR the two known non-'review' review artifacts.
DISK_KINDS="$(grep -hoE '^kind:[[:space:]]*[A-Za-z0-9_-]+' "$PLANS"/*.md 2>/dev/null \
  | awk '{print $2}' | sort -u \
  | grep -E 'review|^substrate-adjudication$|^plan-rereview$' || true)"

# Review: code-reviewer (S3-F3) — guard against a misconfigured PLANS path silently passing
# with 0 results; require at least 3 review-family values on disk.
DISK_KIND_COUNT="$(echo "$DISK_KINDS" | grep -c '[^[:space:]]' || true)"
[ "$DISK_KIND_COUNT" -ge 3 ] || fail "disk census found fewer than 3 review-family kind values (got $DISK_KIND_COUNT) — check PLANS path: $PLANS"

for k in $DISK_KINDS; do
  got="$(resolve_kind "$k")"
  [ "$got" = "review-sidecar" ] || fail "DISK kind '$k' resolved to '$got', expected review-sidecar (oracle drifted from disk — extend review-sidecar.yaml kinds:)"
done

echo "PASS: snapshot ($(echo $SNAPSHOT | wc -w | tr -d ' ') values) + live disk census ($(echo $DISK_KINDS | wc -w | tr -d ' ') values) all resolve to review-sidecar"
exit 0
