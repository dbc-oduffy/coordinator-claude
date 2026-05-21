#!/usr/bin/env bash
# workday-start-cross-repo-memo-surface.sh — Surface outstanding cross-repo memos for /workday-start Step 1.45.
#
# Purpose: Glob the cross-repo archive, parse frontmatter, filter to open/reviewed memos
# (skipping grandfathered pre-cutoff ones), compute staleness, emit one line per memo.
# Emits nothing if zero qualifying memos — callers may skip the section heading.
#
# Spec backlink: docs/plans/2026-05-21-cross-repo-memo-discoverability.md §Chunk 3
#
# Usage:
#   bash workday-start-cross-repo-memo-surface.sh
#   CROSS_REPO_ARCHIVE_DIR=/some/tmpdir bash workday-start-cross-repo-memo-surface.sh
#
# Environment:
#   CROSS_REPO_ARCHIVE_DIR — override archive directory (used by smoke tests)
#
# Exit: always 0. Emits nothing when no qualifying memos exist (silent per spec).

set -euo pipefail

ARCHIVE_DIR="${CROSS_REPO_ARCHIVE_DIR:-${HOME}/.claude/archive/cross-repo}"
# MOCK_TODAY: override for testing (ISO-8601 date string e.g. "2026-06-15").
# When set, all age/staleness computations use this date instead of date.today().
MOCK_TODAY="${MOCK_TODAY:-}"

# Resolve Python binary — mirrors coordinator-doctor-sentinel.sh convention.
if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  # Without Python we cannot parse YAML frontmatter. Stay silent.
  exit 0
fi

# Cutoff: memos created on or before this date are grandfathered (pre-lifecycle).
CUTOFF_DATE="2026-05-21"
# Max entries before truncation line.
MAX_ENTRIES=8

if [[ ! -d "$ARCHIVE_DIR" ]]; then
  exit 0
fi

# Collect qualifying memos via Python YAML parsing.
# Each line: "<created>|<to>|<title>|<status>|<reviewed_at>"
memo_lines=()

for f in "$ARCHIVE_DIR"/*.md; do
  [[ -f "$f" ]] || continue
  result=$("$PY" - "$f" <<'PYEOF'
import sys, re

path = sys.argv[1]
try:
    with open(path, encoding="utf-8") as fh:
        content = fh.read()
except Exception:
    sys.exit(0)

# Extract YAML frontmatter between first pair of --- lines.
m = re.match(r'^---\r?\n(.*?)\r?\n---', content, re.DOTALL)
if not m:
    sys.exit(0)

try:
    import yaml
    fm = yaml.safe_load(m.group(1))
except Exception:
    sys.exit(0)

if not isinstance(fm, dict):
    sys.exit(0)

created     = str(fm.get("created", "")).strip()
to          = str(fm.get("to", "")).strip()
title       = str(fm.get("title", "")).strip()
status      = str(fm.get("status", "")).strip()
reviewed_at = str(fm.get("reviewed_at", "")).strip()

# Must have a status field to be a lifecycle-aware memo.
if not status:
    sys.exit(0)

# Grandfathered: created on or before cutoff.
if created and created <= "2026-05-21":
    sys.exit(0)

# Only surface open or reviewed.
if status not in ("open", "reviewed"):
    sys.exit(0)

print(f"{created}|{to}|{title}|{status}|{reviewed_at}")
PYEOF
  )
  [[ -n "$result" ]] && memo_lines+=("$result")
done

[[ ${#memo_lines[@]} -eq 0 ]] && exit 0

# Sort by created date ascending.
IFS=$'\n' sorted=($(printf '%s\n' "${memo_lines[@]}" | sort))
unset IFS

output_lines=()
for line in "${sorted[@]}"; do
  IFS='|' read -r created to title status reviewed_at <<< "$line"

  # Compute age in days from created date.
  age_days=$("$PY" -c "
import os
from datetime import date
mock = os.environ.get('MOCK_TODAY', '').strip()
today = date.fromisoformat(mock) if mock else date.today()
try:
    c = date.fromisoformat('${created}')
    print((today - c).days)
except Exception:
    print(0)
")

  stale_flag=""
  if [[ "$status" == "open" ]] && [[ "$age_days" -gt 7 ]]; then
    stale_flag=" [STALE — receiver hasn't read]"
  elif [[ "$status" == "reviewed" ]]; then
    # F5 (code-reviewer P2): if reviewed_at is absent, fall back to created so
    # staleness degrades gracefully instead of silently masking a stale memo.
    reviewed_age=$("$PY" -c "
import os
from datetime import date
mock = os.environ.get('MOCK_TODAY', '').strip()
today = date.fromisoformat(mock) if mock else date.today()
anchor = '${reviewed_at}' or '${created}'
try:
    r = date.fromisoformat(anchor)
    print((today - r).days)
except Exception:
    print(0)
")
    if [[ "$reviewed_age" -gt 14 ]]; then
      stale_flag=" [STALE — action pending]"
    fi
  fi

  output_lines+=("- ${created} → ${to}: ${title} — ${status} (${age_days} days)${stale_flag}")
done

total=${#output_lines[@]}
emit_count=$(( total > MAX_ENTRIES ? MAX_ENTRIES : total ))

for (( i=0; i<emit_count; i++ )); do
  echo "${output_lines[$i]}"
done

if [[ "$total" -gt "$MAX_ENTRIES" ]]; then
  remaining=$(( total - MAX_ENTRIES ))
  echo "(${remaining} more — see ${ARCHIVE_DIR} for full list)"
fi
