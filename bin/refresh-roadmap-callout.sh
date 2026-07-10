#!/usr/bin/env bash
# refresh-roadmap-callout.sh — Scoped refresh of a single roadmap's STUB-INDEX query callout.
#
# Usage: refresh-roadmap-callout.sh <roadmap_id> [--root <repo>]
#
# Resolves state/roadmap/<roadmap_id>/STUB-INDEX.md and, when it exists and carries a
# `<!-- BEGIN query:` callout, delegates rendering to refresh-queries.js --files (single
# source of truth — this wrapper never re-implements callout rendering). Clean no-op
# (exit 0 + one-line note) when the roadmap dir or callout is absent — a roadmap_id with
# no index is not an error.
#
# Spec: docs/plans/2026-07-09-roadmap-callout-refresh-at-pickup-and-wsc.md § C1
set -euo pipefail

ROADMAP_ID=""
ROOT_ARG=""

while [ $# -gt 0 ]; do
  case "$1" in
    --root)
      ROOT_ARG="${2:-}"
      shift 2
      ;;
    -h|--help)
      echo "Usage: refresh-roadmap-callout.sh <roadmap_id> [--root <repo>]"
      exit 0
      ;;
    *)
      if [ -z "$ROADMAP_ID" ]; then
        ROADMAP_ID="$1"
      fi
      shift
      ;;
  esac
done

if [ -z "$ROADMAP_ID" ]; then
  echo "ERROR: refresh-roadmap-callout.sh requires <roadmap_id>" >&2
  exit 1
fi

# Defensive quote-strip: handoff frontmatter stores roadmap_id quoted (roadmap_id: "v3split"),
# and not every caller (e.g. the wsc break-glass extraction, the future example-orchestration-hub op) strips the
# surrounding quotes. Strip a single layer of matching double- or single-quotes so a quoted id
# resolves to the right path instead of silently no-op'ing on state/roadmap/"v3split"/.
ROADMAP_ID="${ROADMAP_ID%\"}"; ROADMAP_ID="${ROADMAP_ID#\"}"
ROADMAP_ID="${ROADMAP_ID%\'}"; ROADMAP_ID="${ROADMAP_ID#\'}"

# Path-injection guard (Review: code-reviewer Finding 1 — roadmap_id is extracted from
# handoff frontmatter, attacker-influenceable on a shared work/* branch, and is interpolated
# raw into a filesystem path below and into a git-add pathspec at the two SKILL.md call sites;
# the quote-strip above is a content-shape fix, not a security control). Fail loud (non-zero
# exit) on anything outside the allowlist ^[A-Za-z0-9][A-Za-z0-9._-]*$, and explicitly reject
# any embedded ".." traversal segment even though the character class already excludes "/".
case "$ROADMAP_ID" in
  "" | [!A-Za-z0-9]* | *[!A-Za-z0-9._-]* | *..* )
    echo "ERROR: invalid roadmap_id '${ROADMAP_ID}' — must match ^[A-Za-z0-9][A-Za-z0-9._-]*\$ with no '..' traversal" >&2
    exit 1
    ;;
esac

# Resolve repo root: --root flag -> git-toplevel marker auto-discovery -> cwd fallback.
# (Review: code-reviewer Finding 6.) No env-var tier — this wrapper is always invoked with
# an explicit --root from its two call sites (pickup/SKILL.md, workstream-complete/SKILL.md);
# cwd fallback exists only for manual/test invocation.
if [ -n "$ROOT_ARG" ]; then
  ROOT="$ROOT_ARG"
elif ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"; then
  :
else
  ROOT="$(pwd)"
fi

STUB_INDEX="${ROOT}/state/roadmap/${ROADMAP_ID}/STUB-INDEX.md"

if [ ! -f "$STUB_INDEX" ]; then
  echo "refresh-roadmap-callout: no STUB-INDEX.md for roadmap '${ROADMAP_ID}' at ${STUB_INDEX} — no-op"
  exit 0
fi

if ! grep -q '<!-- BEGIN query:' "$STUB_INDEX" 2>/dev/null; then
  echo "refresh-roadmap-callout: ${STUB_INDEX} has no query callout — no-op"
  exit 0
fi

# Coordinator-root + trust-prefix guard (promoted to the shared
# coordinator_trusted_root_guard function — Variant A / fail-loud, since this
# script must refuse to proceed with an untrusted root. See
# coordinator/lib/coordinator-trusted-root-guard.sh for the trust-core.
# Spec backlink: docs/plans/2026-07-09-resolver-unification-v3split-01.md § C5
_cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
# shellcheck source=../lib/coordinator-trusted-root-guard.sh
source "$(dirname "${BASH_SOURCE[0]}")/../lib/coordinator-trusted-root-guard.sh"
coordinator_trusted_root_guard --mode=fail-loud --root="$_cc_root" --site="$0"
[ -d "$_cc_root" ] || { echo "ERROR: coordinator root unresolved — ~/.claude/.doe-root missing/invalid; re-run coordinator:install" >&2; exit 1; }

node "${_cc_root}/bin/refresh-queries.js" --files "$STUB_INDEX" --root "$ROOT"
