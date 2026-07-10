#!/usr/bin/env bash
# render-posture-overlay.sh — idempotent managed-section merge of a chosen
# Posture overlay block into a target CLAUDE.md, never clobbering the rest
# of the file.
#
# Purpose: reads coordinator/templates/postures/<anchor>.md (authored by a
# sibling chunk — this script assumes the file exists at that path) and
# merges its content into <target-claude-md> as a MARKER-DELIMITED managed
# section:
#
#   <!-- coordinator:posture:start -->
#   ...anchor template content (its own `## Posture` heading lives INSIDE
#   the markers as content — the markers are the anchor, not the heading)...
#   <!-- coordinator:posture:end -->
#
# Behavior:
#   - No managed block present  -> INSERT (append to end of file). The rest
#     of the file is never rewritten (install.md's never-clobber invariant).
#   - Managed block present     -> SWAP (replace between markers) so a
#     re-run / posture change hot-swaps in place; never appends a duplicate.
#   - anchor == default injects default.md like any other anchor — there is
#     no special "default removes the block" branch; all three anchors are
#     treated uniformly.
#   - --check-only computes the intended action, prints it, and leaves the
#     target file byte-unchanged (no write of any kind).
#
# Size guard: the check-claude-md-size.py PreToolUse hook only fires on the
# Write/Edit/MultiEdit tool path and never sees this script's Bash-mediated
# write, so the post-merge byte size is self-gated here against the SAME
# HARD threshold the hook enforces (read from that file at runtime — not a
# second hardcoded copy that can drift out of sync).
#
# Collision detection: a target file that already carries a MARKERLESS
# `## Posture` or `## Working Style` heading (the shape the pre-installer
# "How to tune posture" doctrine told users to hand-author) OUTSIDE the
# managed marker span is a collision with an unmanaged, hand-authored
# section — checked on BOTH the insert path (no managed block yet) and the
# swap path (managed block already present alongside a separate stray
# heading). This script FAILS LOUD on that collision rather than silently
# appending a second `## Posture` heading or silently swap-merging past it.
#
# Marker-rewrite technique (DR-148): the between-markers rewrite is an awk
# pass to a mktemp file, then an atomic `mv` — never `sed -i` in any form
# (BSD `sed -i ''` and GNU `sed -i` are both excluded; DR-148 portability).
#
# Spec backlink: archive/specs/2026-07/2026-07-09-coordinator-end-user-modes.md § C4
# Negative-spec: do NOT use `sed -i` (see MARKER-REWRITE TECHNIQUE above).
# Negative-spec: do NOT special-case anchor==default to skip injection —
#   AC6 requires the default block to be materialized just like the others.
# Negative-spec: do NOT let a posture template body contain a line
#   byte-identical to $MARKER_START/$MARKER_END — guarded by an assert
#   near script start (fail loud), since the awk swap pass matches marker
#   lines by exact string equality against the whole file.

set -uo pipefail

# ---------------------------------------------------------------------------
# Bash >=4 guard — must be above all bash-4 syntax; parses safely on bash 3.2.
# ---------------------------------------------------------------------------
if [ "${BASH_VERSINFO[0]:-0}" -lt 4 ]; then
  {
    printf 'render-posture-overlay.sh: requires bash >=4 (found %s).\n' "${BASH_VERSION:-unknown}"
    printf '  macOS: brew install bash  (restart terminal; /opt/homebrew/bin/bash is bash 5)\n'
    printf '  Reference: coordinator/docs/wiki/cross-platform-shell-portability.md\n'
  } >&2
  exit 1
fi

MARKER_START='<!-- coordinator:posture:start -->'
MARKER_END='<!-- coordinator:posture:end -->'

die() {
  printf 'render-posture-overlay.sh: ERROR: %s\n' "$*" >&2
  exit 1
}

usage() {
  cat >&2 <<'EOF'
Usage: render-posture-overlay.sh <anchor> <target-claude-md> [--check-only]

  <anchor>            One of: precision | default | substrate-free
  <target-claude-md>  Path to the CLAUDE.md to merge the posture block into
  --check-only        Compute and print the intended action; write nothing.

Reads: <coordinator-root>/templates/postures/<anchor>.md
EOF
}

# ---- arg parse ----
if [[ $# -lt 2 ]]; then
  usage
  exit 1
fi

ANCHOR="$1"
TARGET="$2"
shift 2

CHECK_ONLY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --check-only) CHECK_ONLY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown argument: $1 (run with --help for usage)" ;;
  esac
done

case "$ANCHOR" in
  precision|default|substrate-free) ;;
  *) die "Unknown anchor '$ANCHOR' — must be one of: precision, default, substrate-free" ;;
esac

# ---- resolve coordinator root relative to this script (never hardcoded) ----
_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)"
COORDINATOR_ROOT="$(cd "${_SCRIPT_DIR}/.." 2>/dev/null && pwd)"
[[ -n "$COORDINATOR_ROOT" ]] || die "Could not resolve coordinator root from ${_SCRIPT_DIR}"

TEMPLATE_PATH="${COORDINATOR_ROOT}/templates/postures/${ANCHOR}.md"
[[ -f "$TEMPLATE_PATH" ]] || die "Template not found: ${TEMPLATE_PATH}"

[[ -f "$TARGET" ]] || die "Target CLAUDE.md not found: ${TARGET}"

# ---- resolve HARD size-guard threshold from the SSOT (never a second copy) ----
SIZE_GUARD_SRC="${COORDINATOR_ROOT}/hooks/scripts/check-claude-md-size.py"
[[ -f "$SIZE_GUARD_SRC" ]] || die "Size-guard SSOT not found: ${SIZE_GUARD_SRC}"

HARD_LIMIT="$(grep -E '^HARD = [0-9]+' "$SIZE_GUARD_SRC" | head -1 | sed -E 's/^HARD = ([0-9]+).*/\1/')"
[[ -n "$HARD_LIMIT" ]] || die "Could not parse HARD threshold from ${SIZE_GUARD_SRC}"
case "$HARD_LIMIT" in
  ''|*[!0-9]*) die "Parsed HARD threshold is not numeric: '${HARD_LIMIT}' (from ${SIZE_GUARD_SRC})" ;;
esac

# ---- read template content ----
TEMPLATE_CONTENT="$(cat "$TEMPLATE_PATH")"

# Review: code-reviewer — precondition assert: a posture template body that
# itself contains a line byte-identical to a marker string would corrupt the
# awk swap pass's exact-line-match boundary detection on any future re-run.
# Latent today (no template trips it) but cheap to guard against a future
# template that quotes the marker syntax as illustrative prose.
if printf '%s\n' "$TEMPLATE_CONTENT" | grep -qFx "$MARKER_START"; then
  die "Template ${TEMPLATE_PATH} contains a line byte-identical to the start marker (${MARKER_START}) — this would corrupt marker-boundary detection on merge. Rephrase the template to avoid an exact-line match against the marker string."
fi
if printf '%s\n' "$TEMPLATE_CONTENT" | grep -qFx "$MARKER_END"; then
  die "Template ${TEMPLATE_PATH} contains a line byte-identical to the end marker (${MARKER_END}) — this would corrupt marker-boundary detection on merge. Rephrase the template to avoid an exact-line match against the marker string."
fi

# ---- collision detection: markerless '## Posture' / '## Working Style' heading ----
# Review: code-reviewer — broadened to run on BOTH the insert path (no
# managed block yet) and the swap path (managed block already present but a
# SEPARATE markerless legacy heading also exists outside the marker span).
# Previously this only fired pre-insert, so an operator with both a managed
# block AND a stray hand-authored heading (e.g. re-edited the file by hand
# after an earlier install) got a silent swap that never touched — or
# flagged — the stray heading. Now: strip the managed span itself before
# scanning for a markerless heading, so a heading INSIDE the markers (which
# is expected content, e.g. the template's own `## Posture` heading) never
# false-positives, only a heading OUTSIDE the span does.
HAS_START_MARKER=0
grep -qF "$MARKER_START" "$TARGET" && HAS_START_MARKER=1

if [[ "$HAS_START_MARKER" -eq 0 ]]; then
  SCAN_TARGET="$TARGET"
else
  SCAN_TARGET="$(mktemp "${TARGET}.collision-scan.XXXXXX")" || die "mktemp failed for collision scan"
  awk -v start="$MARKER_START" -v end="$MARKER_END" '
    $0 == start { in_block = 1; next }
    $0 == end   { in_block = 0; next }
    in_block    { next }
    { print }
  ' "$TARGET" > "$SCAN_TARGET"
fi

if grep -qE '^## (Posture|Working Style)[[:space:]]*$' "$SCAN_TARGET"; then
  COLLISION_LINE="$(grep -nE '^## (Posture|Working Style)[[:space:]]*$' "$SCAN_TARGET" | head -1)"
  [[ "$HAS_START_MARKER" -eq 1 ]] && rm -f "$SCAN_TARGET"
  die "Collision: target already has a markerless '## Posture' or '## Working Style' heading outside the managed marker span (${COLLISION_LINE}). This is a hand-authored section from before managed-section merging existed (or added after an earlier install). Resolve by hand: either delete/rename that section, or wrap it manually in ${MARKER_START} / ${MARKER_END} markers, then re-run."
fi
[[ "$HAS_START_MARKER" -eq 1 ]] && rm -f "$SCAN_TARGET"

# ---- compute intended action + post-merge content ----
if [[ "$HAS_START_MARKER" -eq 1 ]]; then
  grep -qF "$MARKER_END" "$TARGET" || die "Target has a start marker but no matching end marker (${MARKER_END}) — malformed managed block. Resolve by hand."
  ACTION="swap"
else
  ACTION="insert"
fi

MANAGED_BLOCK="${MARKER_START}
${TEMPLATE_CONTENT}
${MARKER_END}"

if [[ "$ACTION" == "swap" ]]; then
  # ---- awk pass: replace everything between (and including) the markers ----
  # Written to temp files, never edited in place with sed -i (DR-148). The
  # replacement block is passed via a temp FILE (not a -v string) because
  # BSD/onetrueawk (the macOS default) rejects multi-line strings in -v
  # assignments ("newline in string") — gawk tolerates it but the script
  # must stay portable across both.
  AWK_TMP="$(mktemp "${TARGET}.tmp.XXXXXX")" || die "mktemp failed for ${TARGET}"
  BLOCK_TMP="$(mktemp "${TARGET}.block.XXXXXX")" || { rm -f "$AWK_TMP"; die "mktemp failed for ${TARGET}"; }
  printf '%s\n' "$MANAGED_BLOCK" > "$BLOCK_TMP"
  # shellcheck disable=SC2064
  trap "rm -f '${AWK_TMP}' '${BLOCK_TMP}'" EXIT

  awk -v start="$MARKER_START" -v end="$MARKER_END" -v blockfile="$BLOCK_TMP" '
    BEGIN { in_block = 0; printed_block = 0 }
    $0 == start {
      if (!printed_block) {
        while ((getline line < blockfile) > 0) { print line }
        close(blockfile)
        printed_block = 1
      }
      in_block = 1
      next
    }
    $0 == end {
      in_block = 0
      next
    }
    in_block { next }
    { print }
  ' "$TARGET" > "$AWK_TMP" || die "awk swap pass failed"

  NEW_CONTENT="$(cat "$AWK_TMP")"
else
  # insert: append the managed block to the end of the file, separated by a
  # blank line if the file does not already end with one.
  ORIGINAL_CONTENT="$(cat "$TARGET")"
  if [[ -z "$ORIGINAL_CONTENT" ]]; then
    NEW_CONTENT="$MANAGED_BLOCK"
  else
    NEW_CONTENT="${ORIGINAL_CONTENT}

${MANAGED_BLOCK}"
  fi
fi

# ---- size guard: compute post-merge byte size, compare against HARD ----
# Review: code-reviewer — measure the exact bytes that will land on disk
# (printf '%s\n', matching the write below), not the pre-newline string; the
# prior '%s'-only measurement under-counted by one byte against HARD_LIMIT.
NEW_SIZE="$(printf '%s\n' "$NEW_CONTENT" | wc -c | tr -d '[:space:]')"

if [[ "$NEW_SIZE" -gt "$HARD_LIMIT" ]]; then
  die "Merge would push ${TARGET} to ${NEW_SIZE} bytes (hard limit ${HARD_LIMIT}). Refusing to write. Trim the anchor template or other content in ${TARGET}, then re-run."
fi

# ---- --check-only: print intended action, write nothing, leave file byte-unchanged ----
if [[ "$CHECK_ONLY" -eq 1 ]]; then
  printf 'render-posture-overlay.sh: --check-only: would %s managed posture block (anchor=%s) into %s (post-merge size %s bytes, limit %s bytes)\n' \
    "$ACTION" "$ANCHOR" "$TARGET" "$NEW_SIZE" "$HARD_LIMIT"
  exit 0
fi

# ---- write: atomic mktemp + mv (never sed -i) ----
WRITE_TMP="$(mktemp "${TARGET}.tmp.XXXXXX")" || die "mktemp failed for ${TARGET}"
printf '%s\n' "$NEW_CONTENT" > "$WRITE_TMP" || { rm -f "$WRITE_TMP"; die "write to temp file failed"; }
mv "$WRITE_TMP" "$TARGET" || die "atomic mv failed for ${TARGET}"

printf 'render-posture-overlay.sh: %s managed posture block (anchor=%s) into %s (%s bytes)\n' \
  "$ACTION" "$ANCHOR" "$TARGET" "$NEW_SIZE" >&2
