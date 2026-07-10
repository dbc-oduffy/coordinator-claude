#!/usr/bin/env bash
# parse-resolves-trailer.sh — emit the artifact-IDs from a commit's
#                              `Resolves:` git trailers.
#
# Spec backlink: docs/plans/2026-07-08-lifecycle-vocab-c2-durable-links-rollup.md § C4
# Doctrine: coordinator/docs/wiki/resolves-commit-trailer.md
#
# Purpose: thin wrapper that extracts `Resolves: <artifact-id>` trailer
# values from a single commit's message, one artifact-id per stdout line, so
# callers (coordinator/bin/rollup-derive.sh, C5) can derive resolving-commit
# sets without hand-parsing commit bodies.
#
# Portability verdict (pinned 2026-07-08, post-review the Staff Engineer #7): this
# script REQUIRES git >= 2.15 — the release that added the
# `%(trailers:key=...,valueonly)` pretty-format token used as the primary
# extraction path. A `git interpret-trailers --parse` fallback is provided
# for git versions where the pretty-format token is unavailable or behaves
# unexpectedly, but the *primary* path is the pretty-format query.
#
# Do NOT version-probe via `git interpret-trailers --version` — it is not a
# valid flag for that subcommand (confirmed 2026-07-08: `git interpret-
# trailers --version` -> `error: unknown option 'version'`, exit 129). If a
# runtime capability probe is ever needed, probe via a real trailer-parse
# invocation against a throwaway string, never a version flag.
#
# Negative-spec: read-only. Never modifies the repo. Guarded per DR-148
# cross-platform-shell (bash >=4 + BSD coreutils; no GNU-only sed/grep flags).

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: parse-resolves-trailer.sh <commit>

Emits one artifact-id per line, extracted from the `Resolves: <artifact-id>`
git trailers of <commit>. Zero output lines is a valid, non-error result
(the commit carries no Resolves: trailer) -- callers should treat empty
output as a vacuous pass, not a failure. See:
  coordinator/docs/wiki/resolves-commit-trailer.md

Requires git >= 2.15 (for the %(trailers:...) pretty-format token).

Options:
  --help, -h   Show this help
EOF
}

if [[ $# -eq 0 ]]; then
  usage >&2
  exit 1
fi

case "$1" in
  --help|-h) usage; exit 0 ;;
esac

COMMIT="$1"

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "parse-resolves-trailer.sh: not inside a git repository" >&2
  exit 2
fi

if ! git rev-parse --verify --quiet "${COMMIT}^{commit}" >/dev/null; then
  echo "parse-resolves-trailer.sh: not a valid commit: ${COMMIT}" >&2
  exit 2
fi

# Primary path: structured pretty-format trailer extraction (git >= 2.15).
# One trailer value per line already; drop any blank lines the format may
# emit for commits with no Resolves: trailer at all.
primary_output="$(git log -1 --format='%(trailers:key=Resolves,valueonly)' "${COMMIT}" 2>/dev/null || true)"

if [[ -n "${primary_output}" ]]; then
  printf '%s\n' "${primary_output}" | sed '/^[[:space:]]*$/d'
  exit 0
fi

# Fallback path: git interpret-trailers --parse over the raw commit body.
# Used when the pretty-format token yields nothing (older git, or a git
# build where the token is unsupported) -- re-parse the message body
# directly rather than trusting the pretty-format path silently.
body="$(git log -1 --format=%B "${COMMIT}")"

# Review: code-reviewer (F4, nit) — grep -i is DELIBERATE typo-forgiveness
# (e.g. `RESOLVES:`/`resolves:`) beyond the documented exact-case `Resolves:`
# convention, not an oversight; the fallback path is intentionally more
# permissive than the primary pretty-format path.
printf '%s' "${body}" \
  | git interpret-trailers --parse \
  | grep -i '^Resolves:' \
  | sed -E 's/^[Rr][Ee][Ss][Oo][Ll][Vv][Ee][Ss]:[[:space:]]*//' \
  | sed '/^[[:space:]]*$/d' || true

exit 0
