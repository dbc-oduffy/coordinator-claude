#!/usr/bin/env bash
# workday-start-cross-repo-memo-surface.sh — Surface inbound cross-repo memos for /workday-start Step 1.45.
#
# Purpose: Glob THIS repo's cross-repo/inbox/ directory (receiver-inbound), parse frontmatter,
# filter to status: open memos (skipping grandfathered pre-cutoff ones), compute staleness,
# emit one line per memo. Emits nothing if zero qualifying memos — callers may skip the
# section heading.
#
# Spec backlink: docs/plans/2026-05-23-cross-repo-single-surface-and-canonical-scaffold.md § Chunk 3
# Prior spec: docs/plans/2026-05-21-cross-repo-memo-discoverability.md § Chunk 3
#
# Single-delivery-copy model: sender writes ONE dirty file into receiver's cross-repo/.
# This script surfaces memos awaiting THIS repo's EM action (status: open).
# Receiver flips status: open → actioned in place via Edit + commit — no move.
#
# Usage:
#   bash workday-start-cross-repo-memo-surface.sh
#   CROSS_REPO_INBOX_DIR=/some/tmpdir bash workday-start-cross-repo-memo-surface.sh
#
# Environment:
#   CROSS_REPO_INBOX_DIR — override inbox directory (default: cross-repo/inbox/ at repo root).
#                          Used by smoke tests. Detect repo root via git if available,
#                          otherwise falls back to cwd.
# Review: F9 — corrected default path from cross-repo/ to cross-repo/inbox/
#
# Exit: always 0. Emits nothing when no qualifying memos exist (silent per spec).

set -euo pipefail

# Resolve THIS repo's cross-repo/inbox/ directory (receiver-inbound inbox).
# Priority: CROSS_REPO_INBOX_DIR env override → git root → cwd.
if [[ -n "${CROSS_REPO_INBOX_DIR:-}" ]]; then
  INBOX_DIR="$CROSS_REPO_INBOX_DIR"
elif git_root=$(git rev-parse --show-toplevel 2>/dev/null); then
  INBOX_DIR="${git_root}/cross-repo/inbox"
else
  INBOX_DIR="$(pwd)/cross-repo/inbox"
fi

# MOCK_TODAY: override for testing (ISO-8601 date string e.g. "2026-06-15").
# When set, all age/staleness computations use this date instead of date.today().
MOCK_TODAY="${MOCK_TODAY:-}"

# Resolve Python binary — mirrors coordinator-doctor-sentinel.sh convention.
if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN=python
else
  # Without Python we cannot parse YAML frontmatter. Stay silent.
  exit 0
fi

# Cutoff: memos created on or before this date are grandfathered (pre-lifecycle).
CUTOFF_DATE="2026-05-21"
# Max entries before truncation line.
MAX_ENTRIES=8

if [[ ! -d "$INBOX_DIR" ]]; then
  exit 0
fi

# Collect qualifying memos via Python YAML parsing.
# Each line: "<band_rank>|<created>|<from>|<title>|<kind>"
# band_rank: 0 = urgent (ask/consult, including absent-kind default), 1 = quiet (fyi)
memo_lines=()

for f in "$INBOX_DIR"/*.md; do
  [[ -f "$f" ]] || continue
  result=$("$PYTHON_BIN" - "$f" <<'PYEOF' # verify-no-console-flash: allow — on-demand cross-repo memo surface, not session-hot-path
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

# code-review F3: replace yaml.safe_load (optional dep, silently exits on missing)
# with regex flat-frontmatter extraction — same approach used elsewhere in this script.
# Handles simple key: value lines only; sufficient for the memo schema fields we care about.
fm = {}
for kv_line in m.group(1).splitlines():
    kv_m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)', kv_line)
    if kv_m:
        k, v = kv_m.group(1), kv_m.group(2).strip()
        # Strip surrounding double-quotes (dispatcher quotes string values).
        if len(v) >= 2 and v.startswith('"') and v.endswith('"'):
            v = v[1:-1].replace('\\"', '"').replace('\\\\', '\\')
        fm[k] = v

if not fm:
    sys.exit(0)

created      = str(fm.get("created", "")).strip()
sender       = str(fm.get("from", "")).strip()
title        = str(fm.get("title", "")).strip()
status       = str(fm.get("status", "")).strip()
picked_up_by = str(fm.get("picked_up_by", "")).strip()

# Must have a status field to be a lifecycle-aware memo.
if not status:
    sys.exit(0)

# Grandfathered: created on or before cutoff.
if created and created <= "2026-05-21":
    sys.exit(0)

# Receiver-inbound: surface memos awaiting action (open) AND in-flight claims
# (in_progress). An in_progress memo is actively claimed by a live session — it is
# NOT free work, but hiding it entirely makes the inbox "look free mid-action" (the
# 2026-06-20 collision). Surface it with a [CLAIMED by ...] tag so the operator sees
# who holds it. Staleness-aware resurfacing is deferred: the dead-PID reaper reverts a
# stale claim back to open, at which point the open path below picks it up for free.
# Spec backlink: docs/plans/2026-06-21-memo-pickup-claim-lock-and-routed-plan-reconcile.md § C4
if status not in ("open", "in_progress"):
    sys.exit(0)

# Parse kind — default to "ask" when absent (safe default: surfaces with urgency,
# never silently downgrades an unlabeled memo to quiet fyi).
# Spec backlink: docs/plans/2026-05-30-pickup-cross-repo-memo-fork.md § Pinned interface
kind = str(fm.get("kind", "ask")).strip() or "ask"

# band_rank: 0 = urgent (ask / consult), 1 = quiet (fyi).
# Sort key composed as "<band_rank>|<created>" so ask/consult sort before fyi,
# and within each band memos are ordered by created date ascending.
band_rank = "1" if kind == "fyi" else "0"

# Review: code-reviewer F4 — sanitize pipe characters in title before emitting the
# |-delimited line; a literal | in a title would corrupt IFS='|' read splits in bash,
# breaking the kind field. Replace with en-dash so titles can never inject extra fields.
title = title.replace("|", "–")
# in_progress memos are attributed, not hidden: append a [CLAIMED by ...] tag so the
# operator sees the memo is actively owned (not free work). Zero coupling — picked_up_by
# is already in frontmatter; no liveness probe needed here.
if status == "in_progress":
    who = picked_up_by.replace("|", "–") if picked_up_by else "unknown"
    title = f"{title} [CLAIMED by {who}]"
print(f"{band_rank}|{created}|{sender}|{title}|{kind}")
PYEOF
  )
  [[ -n "$result" ]] && memo_lines+=("$result")
done

[[ ${#memo_lines[@]} -eq 0 ]] && exit 0

# Sort by (band_rank, created) ascending — urgent band (ask/consult) before quiet (fyi),
# within each band by created date ascending.
sorted=()
while IFS= read -r line; do sorted+=("$line"); done < <(printf '%s\n' "${memo_lines[@]}" | sort)

output_lines=()
for line in "${sorted[@]}"; do
  IFS='|' read -r band_rank created sender title kind <<< "$line"

  # Compute age in days from created date.
  # code-review F15: pass created as a positional arg (sys.argv[1]) to avoid
  # shell-interpolation of an untrusted frontmatter field into Python source.
  if [[ ! "$created" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
    age_days=0
  else
    age_days=$("$PYTHON_BIN" -c " # verify-no-console-flash: allow — on-demand cross-repo memo surface, not session-hot-path
import os, sys
from datetime import date
mock = os.environ.get('MOCK_TODAY', '').strip()
today = date.fromisoformat(mock) if mock else date.today()
try:
    c = date.fromisoformat(sys.argv[1])
    print((today - c).days)
except Exception:
    print(0)
" "$created")
  fi

  stale_flag=""
  # Stale if sitting OPEN for more than 7 days without being actioned. A claimed
  # (in_progress) memo carries a [CLAIMED by ...] marker in its title — it is actively
  # owned, so "awaiting your action" would be wrong; suppress the stale flag for it.
  # (A stale CLAIM is the reaper's concern — it reverts a dead-PID claim back to open,
  # at which point this stale-flag path applies again.)
  if [[ "$age_days" -gt 7 && "$title" != *"[CLAIMED"* ]]; then
    stale_flag=" [STALE — awaiting your action]"
  fi

  # Quiet marker for fyi memos — consistent style with [STALE] flag.
  # Urgent band (ask/consult) gets no marker; the band position conveys urgency.
  # Review: code-reviewer F9 — kind is whitespace-stripped by the Python emitter (.strip());
  # no bash-side strip needed here before the string comparison.
  kind_flag=""
  if [[ "$kind" == "fyi" ]]; then
    kind_flag=" [fyi]"
  fi

  output_lines+=("- ${created} from ${sender}: ${title} (${age_days} days old)${stale_flag}${kind_flag}")
done

total=${#output_lines[@]}
emit_count=$(( total > MAX_ENTRIES ? MAX_ENTRIES : total ))

for (( i=0; i<emit_count; i++ )); do
  echo "${output_lines[$i]}"
done

if [[ "$total" -gt "$MAX_ENTRIES" ]]; then
  remaining=$(( total - MAX_ENTRIES ))
  echo "(${remaining} more — see ${INBOX_DIR} for full list)"
fi
