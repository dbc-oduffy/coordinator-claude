#!/usr/bin/env bash
# check-no-monolith-completion-append.sh — static-grep tripwire: detects unauthorized
# writes to the legacy monolith path archive/completed/YYYY-MM.md on the coordinator
# surface (skills/, commands/, agents/, pipelines/, hooks/).
#
# Purpose: enforces the monolithic-completion-log-write-check tripwire registered in
# docs/wiki/coordinator-tripwires.md. The new per-entry completion-log format writes to
# archive/completed/YYYY-MM/<slug>.md; any new write path targeting the root monolith
# shape is a regression to the old format and must be caught before it ships.
#
# Spec backlink: docs/plans/2026-05-19-completion-log-phase1-foundational-loop.md § Chunk 10
#
# Concurrency: read-only; safe to run in parallel.
# Idempotency: full — pure grep, no writes.
# Resume: not applicable (single-pass grep).
#
# Exit codes:
#   0  No unauthorized hits found (clean).
#   1  One or more unauthorized hits found; offending file:line written to stdout.
#   2  Script invocation error (bad args).
#
# Allowed exceptions (excluded from firing):
#   1. Paths under archive/completed/legacy/ — post-migration canonical home.
#   2. bin/migrate-completion-log-legacy.sh — the migration helper itself uses git mv
#      with the path as its source argument; that is intentional and authorized.
#   3. docs/wiki/ files — instructional mentions of the literal path in docstrings and
#      reference docs are not write instructions.
#   4. Lines containing COORDINATOR_OVERRIDE_LEGACY_MONOLITH — the session-end
#      AUTO-MIGRATE block documents the override path; those lines are not write calls.
#   5. Lines that are HTML/Markdown comment tripwire markers (<!-- TRIPWIRE: ...) — the
#      self-describing prohibition comment in session-end/SKILL.md is not a write call.
#
# Call shapes detected (all six enumerated in the tripwire registry):
#   1. String literal in markdown body:       archive/completed/YYYY-MM.md
#   2. Shell redirect (>> or >):              >> archive/completed/YYYY-MM.md
#   3. Here-doc body:                         cat >> archive/completed/YYYY-MM.md <<'EOF'
#   4. tee invocation:                        tee -a archive/completed/YYYY-MM.md
#   5. Python/Node open(...)/writeFileSync:   open('archive/completed/YYYY-MM.md', ...)
#   6. git mv source argument:                git mv archive/completed/YYYY-MM.md
#      (exception: migrate-completion-log-legacy.sh itself is excluded)
#
# Usage:
#   bash check-no-monolith-completion-append.sh [--root <path>]
#
#   --root  Path to the coordinator plugin root (default: script's own two levels up,
#           i.e. the coordinator/ directory). Override for testing.

set -uo pipefail

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

COORDINATOR_ROOT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --root)
      [[ -z "${2:-}" ]] && { echo "Error: --root requires a path argument" >&2; exit 2; }
      COORDINATOR_ROOT="$2"
      shift 2
      ;;
    --help|-h)
      sed -n '2,/^set /p' "$0" | grep '^#' | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    -*)
      echo "Unknown option: $1" >&2
      exit 2
      ;;
    *)
      echo "Unexpected argument: $1" >&2
      exit 2
      ;;
  esac
done

# Resolve coordinator root: explicit --root > marker-based auto-discovery.
if [[ -z "$COORDINATOR_ROOT" ]]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  COORDINATOR_ROOT="$(dirname "$SCRIPT_DIR")"
fi

if [[ ! -d "$COORDINATOR_ROOT" ]]; then
  echo "Error: coordinator root not found at: $COORDINATOR_ROOT" >&2
  exit 2
fi

# ---------------------------------------------------------------------------
# Grep surface — coordinator skill/command/agent/pipeline/hook files only.
# ---------------------------------------------------------------------------

SEARCH_DIRS=()
for d in skills commands agents pipelines hooks; do
  candidate="${COORDINATOR_ROOT}/${d}"
  [[ -d "$candidate" ]] && SEARCH_DIRS+=("$candidate")
done

if [[ ${#SEARCH_DIRS[@]} -eq 0 ]]; then
  echo "Error: no search directories found under: $COORDINATOR_ROOT" >&2
  exit 2
fi

# The literal pattern we're guarding against: root-level monolith path.
# Matches all six call shapes because every shape includes this substring.
PATTERN='archive/completed/[0-9][0-9][0-9][0-9]-[0-9][0-9]\.md'

# ---------------------------------------------------------------------------
# Run grep, then filter allowed exceptions line-by-line.
# ---------------------------------------------------------------------------

HITS=()

while IFS= read -r line; do
  # Exception 1: path inside legacy/ — post-migration canonical writes are fine.
  echo "$line" | grep -qF "archive/completed/legacy/" && continue

  # Exception 2: the migration helper itself — its git mv source is authorized.
  echo "$line" | grep -qF "migrate-completion-log-legacy.sh" && continue

  # Exception 3: docs/wiki/ files — reference documentation, not write calls.
  echo "$line" | grep -qF "/docs/wiki/" && continue

  # Exception 4: COORDINATOR_OVERRIDE_LEGACY_MONOLITH lines — override documentation.
  echo "$line" | grep -qF "COORDINATOR_OVERRIDE_LEGACY_MONOLITH" && continue

  # Exception 5: HTML/Markdown comment tripwire markers.
  echo "$line" | grep -qE '<!--[[:space:]]*TRIPWIRE:|#[[:space:]]*TRIPWIRE:' && continue

  HITS+=("$line")
done < <(
  grep -rn --include="*.md" --include="*.sh" --include="*.js" --include="*.py" \
       -E "$PATTERN" "${SEARCH_DIRS[@]}" 2>/dev/null
)

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

if [[ ${#HITS[@]} -eq 0 ]]; then
  echo "check-no-monolith-completion-append: CLEAN — no unauthorized monolith writes found."
  exit 0
fi

echo "check-no-monolith-completion-append: UNAUTHORIZED MONOLITH WRITE DETECTED" >&2
echo "" >&2
echo "The following file:line references contain a write path targeting" >&2
echo "archive/completed/YYYY-MM.md outside the allowed exceptions." >&2
echo "New completion-log writes must use archive/completed/YYYY-MM/<slug>.md." >&2
echo "" >&2
for hit in "${HITS[@]}"; do
  echo "  $hit" >&2
done
echo "" >&2
echo "Allowed exceptions: archive/completed/legacy/, migrate-completion-log-legacy.sh," >&2
echo "docs/wiki/ reference docs, COORDINATOR_OVERRIDE_LEGACY_MONOLITH lines," >&2
echo "and <!-- TRIPWIRE: comment markers." >&2

exit 1
