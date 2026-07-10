#!/usr/bin/env bash
# assert-no-dangling-plan-backlinks.sh — AC9 gate for programmatic terminal-plan archival.
#
# After the C4 backfill moved terminal plans docs/plans/<name>.md →
# archive/specs/YYYY-MM/<name>.md, every spec_backlink that still cites the old
# docs/plans/ path dangles. This gate asserts ZERO such dangling backlinks in
# active doctrine surfaces, and --fix repoints them to the archive location.
#
# Scope (both detect and --fix):
#   • spec_backlink CONVENTION lines only — a line matching /spec.?backlink/i.
#     Incidental prose mentions ("Phase 2d reverses docs/plans/X") are NOT
#     rewritten; only the citation convention is healed.
#   • A cited plan counts as "moved" iff it exists under archive/specs/ AND no
#     longer exists at docs/plans/<name>.md.
#   • Excluded trees: archive/ (terminal paper trail), dist/ (generated publish
#     artifacts), tasks/ + state/ (ephemera swept by /distill), and plan review
#     sidecars (<plan-stem>.<tag>.md).
#
# Spec backlink: docs/plans/2026-06-23-programmatic-terminal-plan-archival.md § AC9 / C6.
#
# Usage:   assert-no-dangling-plan-backlinks.sh [--root <dir>] [--fix]
# Exit:    0 = no dangling backlinks; 1 = ≥1 dangling (run with --fix to heal).

set -uo pipefail

# Bash 4+ required (declare -A). Stock macOS /bin/bash is 3.2; coordinator:install
# provisions brew bash. Fail loud with remediation rather than abort mid-run on a
# cryptic `declare: -A: invalid option`. Exit 0 (can't-verify ≠ gate-fail), matching
# this script's other degradation guards (missing node/perl) — a wrong-shell run
# must not register as a false dangling-backlink FAIL.
if (( BASH_VERSINFO[0] < 4 )); then
  echo "assert-no-dangling-plan-backlinks: requires bash 4+ (declare -A); install via 'brew install bash' (coordinator:install provisions it). Skipping." >&2
  exit 0
fi

ROOT=""; FIX=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --root) ROOT="$2"; shift 2 ;;
    --fix)  FIX=1; shift ;;
    *) shift ;;
  esac
done

if [[ -z "$ROOT" ]]; then
  command -v git >/dev/null 2>&1 && ROOT=$(git rev-parse --show-toplevel 2>/dev/null || true)
fi
[[ -z "$ROOT" ]] && exit 0
[[ -d "$ROOT/archive/specs" ]] || { echo "OK: no archive/specs/ — nothing to heal"; exit 0; }

cd "$ROOT" || exit 0

# Map: moved-plan basename → archive/specs/YYYY-MM/<basename> path.
declare -A MVPATH
while IFS= read -r f; do
  b=$(basename "$f"); stem="${b%.md}"
  [[ "$stem" == *.* ]] && continue                 # sidecar, not a plan
  [[ -e "docs/plans/$b" ]] && continue             # still live → not moved
  MVPATH["$b"]="${f#./}"
done < <(find archive/specs -name '*.md' 2>/dev/null)

[[ "${#MVPATH[@]}" -eq 0 ]] && { echo "OK: no moved plans"; exit 0; }

# Candidate files: spec_backlink convention lines citing docs/plans/, minus
# excluded trees and sidecars.
# DANGLING / FIXED count UNIQUE (file, plan) pairs — a plan cited on several
# spec_backlink lines in one file is one fix, not N.
DANGLING=0; FIXED=0
declare -A SEEN_FILES SEEN_PAIRS
while IFS= read -r hit; do
  file="${hit%%:*}"; file="${file#./}"
  case "/$file" in */archive/*|*/dist/*) continue;; esac
  case "$file" in tasks/*|state/*) continue;; esac
  bn=$(basename "$file"); st="${bn%.md}"; [[ "$st" == *.* ]] && continue   # skip sidecar files
  line="${hit#*:}"; line="${line#*:}"
  # Collect each moved plan cited on this convention line.
  while IFS= read -r fn; do
    [[ -z "$fn" ]] && continue
    base=$(basename "$fn")
    dest="${MVPATH[$base]:-}"
    [[ -z "$dest" ]] && continue                   # cited plan not moved
    [[ -n "${SEEN_PAIRS["$file:$base"]:-}" ]] && continue   # already counted/healed
    SEEN_PAIRS["$file:$base"]=1
    DANGLING=$((DANGLING+1))
    if [[ "$FIX" -eq 1 ]]; then
      # Literal replace docs/plans/<base> → <dest>, ONLY on spec_backlink
      # convention lines (perl quotemeta) — leaves tripwire greps / prose intact.
      if command -v perl >/dev/null 2>&1; then
        SRC="docs/plans/$base" DST="$dest" perl -i -pe 's/\Q$ENV{SRC}\E/$ENV{DST}/g if /spec.?backlink/i' "$file" && FIXED=$((FIXED+1))
      else
        echo "ERROR: --fix needs perl; not found" >&2; exit 2
      fi
    else
      [[ -n "${SEEN_FILES[$file]:-}" ]] || echo "DANGLING in: $file" >&2
      SEEN_FILES[$file]=1
      echo "  $fn → ${dest}" >&2
    fi
  done < <(printf '%s\n' "$line" | grep -oE 'docs/plans/[0-9]{4}-[0-9]{2}-[0-9]{2}-[a-z0-9.-]+\.md')
done < <(grep -rEni 'spec.?backlink' --include='*.md' . 2>/dev/null | grep -E 'docs/plans/')

if [[ "$FIX" -eq 1 ]]; then
  echo "healed $FIXED dangling backlink citation(s)"
  exit 0
fi

if [[ "$DANGLING" -gt 0 ]]; then
  echo "FAIL: $DANGLING dangling plan backlink(s) to moved docs/plans/ paths — run with --fix" >&2
  exit 1
fi
echo "OK: no dangling plan backlinks to moved docs/plans/ paths"
exit 0
