#!/usr/bin/env bash
# AC5 — the frontmatter hook discriminates by `kind:` not directory. A `kind: review-sidecar` file
# carrying only `plan:` under docs/plans/ validates SILENT (no plan-schema nag — fight-the-hook fixed);
# a kindless plan still validates against plan.yaml (back-compat). Self-contained E2E so it does NOT
# inherit the hook test file's pre-existing baseline failures.
# Portable (DR-148): bash 3.2 + BSD coreutils.
set -eo pipefail
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COORD_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
HOOK="$COORD_ROOT/hooks/scripts/validate-frontmatter-schema.js"
REPO_ROOT="$(git -C "$COORD_ROOT" rev-parse --show-toplevel 2>/dev/null || true)"
[ -n "$REPO_ROOT" ] || REPO_ROOT="$(cd "$COORD_ROOT/../../.." && pwd)"

fail() { echo "FAIL: $*" >&2; exit 1; }
[ -f "$HOOK" ] || fail "hook not found at $HOOK"

# 1) review-sidecar with ONLY plan: → SILENT (the exact fight-the-hook case this workstream fixes).
payload1="{\"tool_name\":\"Write\",\"cwd\":\"$REPO_ROOT\",\"tool_input\":{\"file_path\":\"$REPO_ROOT/docs/plans/__probe__.zoli-review.md\",\"content\":\"---\\nkind: review-sidecar\\nplan: docs/plans/x.md\\n---\\n\\nbody\"}}"
out1="$(printf '%s' "$payload1" | node "$HOOK" 2>&1)"
[ -z "$out1" ] || fail "review-sidecar (kind:review-sidecar, only plan:) produced output, expected SILENT: $out1"

# 2) kindless plan with only title: → still routes to plan.yaml (warns missing created/author/status).
payload2="{\"tool_name\":\"Write\",\"cwd\":\"$REPO_ROOT\",\"tool_input\":{\"file_path\":\"$REPO_ROOT/docs/plans/__probe_plain__.md\",\"content\":\"---\\ntitle: x\\n---\\n\\nbody\"}}"
out2="$(printf '%s' "$payload2" | node "$HOOK" 2>&1)"
# Review: code-reviewer (S3-F2) — assert non-empty hook output (plan.yaml fired) rather than
# coupling to the specific message text "created" which may change.
[ -n "$out2" ] || fail "kindless plan did NOT validate vs plan.yaml (back-compat broken): hook output was empty"

echo "PASS: hook discriminates by kind (review-sidecar → silent; kindless plan → plan.yaml back-compat)"
exit 0
