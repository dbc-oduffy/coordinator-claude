#!/usr/bin/env bash
# Purpose: Extract the scope: path list from a handoff frontmatter block, one path per line.
#          Strips the leading "  - " prefix from each entry and fails loud when the block
#          is absent or empty so callers get a clear diagnostic rather than silent empty output.
#
# Usage: extract-scope-paths.sh <handoff-file>
#   Prints matching scope paths to stdout, one per line.
#   Exit 0 on success; exit 1 when scope block is missing or empty.
#
# Spec: docs/plans/2026-06-30-session-terminator-mechanism-unification.md C4

set -euo pipefail

if [[ "${BASH_VERSINFO[0]}" -lt 4 ]]; then
  echo "extract-scope-paths: requires bash >= 4 (found ${BASH_VERSION})" >&2
  echo "  install: brew install bash (macOS) or use system bash on Linux" >&2
  exit 2
fi

if [[ $# -lt 1 ]]; then
  echo "usage: extract-scope-paths.sh <handoff-file>" >&2
  exit 2
fi

HANDOFF="$1"

if [[ ! -f "$HANDOFF" ]]; then
  echo "extract-scope-paths: file not found: $HANDOFF" >&2
  exit 2
fi

# Extract scope paths from YAML frontmatter (  - <path> lines between scope: and next key).
# Byte-identical to the inline idiom in skills/handoff/SKILL.md Step 3 and skills/pickup/SKILL.md Step 1.
# Review: code-reviewer A-F1 — added found && /^---/{exit} before /^[a-z]/ guard so
# extraction terminates at the closing --- when scope: is the last frontmatter field.
SCOPE=$(awk '/^scope:/{found=1; next} found && /^  - /{print substr($0, 5)} found && /^---/{exit} found && /^[a-z]/{exit}' "$HANDOFF")

if [[ -z "$SCOPE" ]]; then
  echo "extract-scope-paths: scope: block missing or empty in $HANDOFF" >&2
  exit 1
fi

printf '%s\n' "$SCOPE"
