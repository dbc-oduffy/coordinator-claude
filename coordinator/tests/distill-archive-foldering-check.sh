#!/usr/bin/env bash
# distill-archive-foldering-check.sh — regression check for the archive month-
# foldering migration (docs/plans/2026-06-18-distill-plan-priority-...), covering
# BOTH archive/specs/ and archive/handoffs/.
#
# Asserts:
#   AC7 — no flat *.md remain directly under archive/specs/ (all month-foldered).
#   AC8 — no stale LINK-context reference (markdown link target or spec_backlink:)
#         points at a flat archive/specs/YYYY-MM-DD-*.md that the migration MOVED
#         (i.e. the month-foldered version now exists on disk and the ref should
#          have been healed). Provenance/log/cache/pre-dangling refs are carved out.
#   AH7 — no DATED flat *.md remain directly under archive/handoffs/. Unlike the
#         specs check, no-date batons (the install-*.md class) legitimately stay
#         flat and are carved out — only date-prefixed handoffs must be foldered.
#   AH8 — every dated archive/handoffs/YYYY-MM/<file> sits in the folder whose name
#         equals ${basename:0:7}. Pure on-disk conformance — the assert that catches
#         a month<->folder misfile. No link-heal dimension: handoffs are not
#         spec_backlink targets (zero inbound link refs observed in practice).
#
# Exit 0 = green. Repo-root-relative; resolves repo root from this script's location.
#
# Portability: requires bash ≥ 3.2 (coordinator:install provisions brew bash; the
# `${BASH_SOURCE[0]}` array ref and `<<<` here-strings are 3.2-safe). Uses GNU-or-BSD
# grep via the $GREP resolver below. Capture-then-process (never `grep | head` under
# `set -o pipefail`) avoids the SIGPIPE-errexit false-green trap — see
# state/lessons.md "pipefail + early-exit-consumer SIGPIPE race".
set -euo pipefail

# Prefer GNU grep (ggrep) when present; stock BSD grep on macOS also supports the
# -rnE + --include combination used below, but ggrep is the safer default.
GREP="$(command -v ggrep 2>/dev/null || command -v grep)"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
cd "$repo_root"

fail=0

# --- AC7: no flat specs directly under archive/specs/ ---
flat="$(find archive/specs -maxdepth 1 -name '*.md' 2>/dev/null | wc -l | tr -d ' ')"
if [ "$flat" != "0" ]; then
  echo "AC7 FAIL: $flat flat *.md remain directly under archive/specs/ (expected month-foldered)"
  find archive/specs -maxdepth 1 -name '*.md'
  fail=1
else
  echo "AC7 ok: 0 flat specs under archive/specs/"
fi

# --- AC8: stale link-context refs to MOVED files only ---
# A ref is stale ONLY IF it is a link context (markdown link target or spec_backlink:)
# pointing at a flat archive/specs/YYYY-MM-DD-<name>.md AND the foldered version
# (archive/specs/YYYY-MM/<name>.md) now exists on disk.
# Excluded (not heal targets):
#   - this plan's own prose (cites example paths, not real link targets)
#   - state/distillation-log.md (provenance rows, not links)
#   - plugins/cache/** (frozen snapshots of published plugin versions)
#   - refs whose foldered target does NOT exist (pre-dangling historical refs to
#     files that never existed at archive/specs/ — not migration-induced)
#
# Capture the full grep result first (|| true: no-match is exit 1, NOT an error
# here), then iterate. Never pipe grep into an early-exit consumer under pipefail.
ac8_fail=0
hits="$("$GREP" -rnE '(\]\(|spec_backlink:[[:space:]]*)archive/specs/[0-9]{4}-[0-9]{2}-[0-9]{2}-' . \
  --include='*.md' 2>/dev/null \
  | "$GREP" -v 'docs/plans/2026-06-18-distill-plan-priority-atlas-gate-archive-foldering.md' \
  | "$GREP" -v 'state/distillation-log.md' \
  | "$GREP" -v 'plugins/cache/' || true)"

while IFS= read -r line; do
  [ -n "$line" ] || continue
  # First flat archive/specs path on the line. Capture fully (|| true guards
  # no-match under set -e), then take the first match via pure-bash expansion
  # (no `| head` — that is the SIGPIPE trap).
  matches="$("$GREP" -oE 'archive/specs/[0-9]{4}-[0-9]{2}-[0-9]{2}-[^ )`]+\.md' <<<"$line" || true)"
  flatpath="${matches%%$'\n'*}"
  [ -n "$flatpath" ] || continue
  bn="$(basename "$flatpath")"
  ym="$("$GREP" -oE '^[0-9]{4}-[0-9]{2}' <<<"$bn" || true)"
  [ -n "$ym" ] || { echo "AC8 WARN: cannot derive YYYY-MM from '$bn' — skipping line"; continue; }
  foldered="archive/specs/$ym/$bn"
  if [ -e "$foldered" ]; then
    echo "AC8 FAIL (moved file, unhealed ref): $line"
    ac8_fail=1
  fi
done <<EOF
$hits
EOF

if [ "$ac8_fail" = "0" ]; then
  echo "AC8 ok: 0 stale link-context refs to moved archive/specs files"
else
  fail=1
fi

# --- AH7: no DATED flat *.md directly under archive/handoffs/ ---
# Carve-out: no-date batons (e.g. install-*.md) legitimately stay flat; only files
# whose basename carries a YYYY-MM-DD date prefix should have been month-foldered.
# Capture find output into a heredoc (not a pipe) so the `fail` mutation below is
# not lost to a subshell — same discipline as AC8.
ah7_fail=0
while IFS= read -r f; do
  [ -n "$f" ] || continue
  bn="$(basename "$f")"
  if "$GREP" -qE '^[0-9]{4}-[0-9]{2}-[0-9]{2}' <<<"$bn"; then
    echo "AH7 FAIL: dated handoff '$bn' sits flat under archive/handoffs/ (expected month-foldered)"
    ah7_fail=1
  fi
done <<EOF
$(find archive/handoffs -maxdepth 1 -name '*.md' 2>/dev/null)
EOF

if [ "$ah7_fail" = "0" ]; then
  echo "AH7 ok: no dated flat handoffs under archive/handoffs/ (no-date batons carved out)"
else
  fail=1
fi

# --- AH8: every dated archive/handoffs/YYYY-MM/<file> sits in its matching folder ---
# Pure on-disk conformance: derive YYYY-MM from the basename's first 7 chars and
# assert it equals the parent folder name. Catches a misfile (e.g. a 2026-05 handoff
# under 2026-06/). Non-date basenames are defensively skipped — they cannot misfile.
ah8_fail=0
while IFS= read -r f; do
  [ -n "$f" ] || continue
  bn="$(basename "$f")"
  "$GREP" -qE '^[0-9]{4}-[0-9]{2}-[0-9]{2}' <<<"$bn" || continue
  folder="$(basename "$(dirname "$f")")"
  ym="${bn:0:7}"
  if [ "$folder" != "$ym" ]; then
    echo "AH8 FAIL (misfiled): $f — basename month $ym != folder $folder"
    ah8_fail=1
  fi
done <<EOF
$(find archive/handoffs -mindepth 2 -maxdepth 2 -name '*.md' 2>/dev/null)
EOF

if [ "$ah8_fail" = "0" ]; then
  echo "AH8 ok: 0 misfiled handoffs under archive/handoffs/YYYY-MM/"
else
  fail=1
fi

exit "$fail"
