#!/usr/bin/env bash
# read-frontmatter-field.sh — Extract a bare scalar value from markdown YAML frontmatter.
#
# Purpose: Reads the first occurrence of a named YAML scalar field from a markdown
# artifact and returns the clean, unquoted value to stdout — no trailing newline.
# Designed for deliverable-spine id/FK fields (deliverable_id, initiative) where
# values are simple strings that never contain '#'. Does NOT attempt full YAML
# parsing; the no-'#'-in-value assumption is a documented scope boundary — callers
# must not use this helper for fields whose values may legitimately contain '#'.
#
# Extracts bare frontmatter scalar values for deliverable-spine arg-pass (handoff/spinoff skills).
#
# Usage:  read-frontmatter-field.sh <file> <field>
#
# Output: bare scalar value printed to stdout (no trailing newline), or empty string when:
#         - the named field is absent in the file
#         - the value is the literal token 'null' (bare or quoted)
#         - the file path is missing, empty, or unreadable
#
# Exit:   always 0 — callers pass optional paths; absence is not an error.
#
# Caution: searches the entire file for the first matching line — not bounded to the YAML
#          frontmatter block. Correct for coordinator artifacts where frontmatter is at
#          file-top; incorrect for files whose body contains matching field patterns above
#          the frontmatter.
# Review: code-reviewer — undocumented scope assumption; grep -m1 is not frontmatter-bounded
#
# Normalization pipeline applied to the matched line:
#   1. Strip the '<field>:' key and leading whitespace.
#   2. Strip a trailing YAML inline comment (' #...' to end of line).
#   3. Trim surrounding whitespace.
#   4. Strip ONE layer of surrounding quotes (double "…" or single '…').
#   5. If the result is the literal string 'null' or empty → emit empty string.

set -euo pipefail

FILE="${1:-}"
FIELD="${2:-}"

# Missing/unreadable file → print nothing, exit 0
if [ -z "$FILE" ] || [ ! -f "$FILE" ] || [ ! -r "$FILE" ]; then
  printf '%s' ""
  exit 0
fi

# Find the first matching frontmatter line
LINE=$(grep -m1 "^${FIELD}:" "$FILE" 2>/dev/null || true)
if [ -z "$LINE" ]; then
  printf '%s' ""
  exit 0
fi

# Step 1: Strip the '<field>:' key and leading whitespace
VALUE=$(printf '%s' "$LINE" | sed "s/^${FIELD}:[[:space:]]*//" )

# Step 2: Strip from ANY '#' to end of line (zero or more preceding spaces).
#         Assumption: target values contain no '#' — not just no ' # comment' — see file-top docstring.
# Review: code-reviewer — comment misstated strip boundary; regex matches zero-width '#', not only space-prefixed
VALUE=$(printf '%s' "$VALUE" | sed 's/[[:space:]]*#.*$//')

# Step 3: Trim surrounding whitespace
VALUE=$(printf '%s' "$VALUE" | sed 's/^[[:space:]]*//' | sed 's/[[:space:]]*$//')

# Step 4: Strip ONE layer of surrounding quotes (double or single)
case "$VALUE" in
  \"*\")
    VALUE="${VALUE#\"}"
    VALUE="${VALUE%\"}"
    ;;
  \'*\')
    VALUE="${VALUE#\'}"
    VALUE="${VALUE%\'}"
    ;;
esac

# Step 5: Literal 'null' or empty → emit empty string
if [ "$VALUE" = "null" ] || [ -z "$VALUE" ]; then
  printf '%s' ""
  exit 0
fi

printf '%s' "$VALUE"
exit 0
