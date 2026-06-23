#!/usr/bin/env bash
# normalize-snippet.sh — shared normalize() helper for verify-*-sync.sh scripts.
#
# Defines normalize(), which strips leading blank lines, trailing blank lines,
# and per-line trailing whitespace from a snippet string — used by snippet-sync
# verifiers to canonicalize both the on-disk snippet body and the extracted
# sentinel block before diffing them.
#
# Sourced by: all verify-*-sync.sh scripts in bin/.
# Source path idiom: "$SCRIPT_DIR/../lib/normalize-snippet.sh" where SCRIPT_DIR
#   is the bin/ directory containing the verify script.
#
# Spec backlink: code-reviewer P2 finding — normalize() was copy-pasted verbatim
#   in 8 verify-*-sync.sh scripts; this lib is the single source of truth.

# normalize <string>
#
# Pipeline:
#   1. printf '%s' "$1"          — emit the string without a trailing newline
#   2. sed 's/[[:space:]]*$//'   — strip trailing whitespace from EACH LINE,
#                                  collapsing whitespace-only lines to "".
#                                  IMPORTANT: this sed pre-pass is what keeps the
#                                  awk NF (trailing-blank guard) and a[s]==""
#                                  (leading-blank guard) tests consistent. Without
#                                  it, a line containing only spaces would NOT be
#                                  empty ("" in awk), so NF would be non-zero and
#                                  the leading/trailing blank detection would miss
#                                  whitespace-only lines. Do NOT remove or reorder
#                                  the sed pre-pass relative to the awk pass.
#   3. awk 'NF{last=NR} ...'     — track last non-blank line (trailing-blank trim);
#                                  find first non-blank line s (leading-blank trim);
#                                  emit lines s..last only.
normalize() {
    printf '%s' "$1" | sed 's/[[:space:]]*$//' | awk 'NF{last=NR} {a[NR]=$0} END{s=1; while(s<=NR && a[s]==""){s++} for(i=s;i<=last;i++){print a[i]}}'
}
