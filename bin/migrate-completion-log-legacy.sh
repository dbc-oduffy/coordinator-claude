#!/usr/bin/env bash
# migrate-completion-log-legacy.sh — Idempotent migration helper: moves legacy
# monthly monolith files (archive/completed/YYYY-MM.md) under archive/completed/legacy/
# so the completion-log query tooling (query-completions.sh) can ignore them without
# needing special-case glob exclusions.
#
# Invocation contexts:
#   PM-invoked one-shot: run manually when first adopting the per-entry layout.
#   Per-close-out wrap:  invoked automatically by coordinator-complete-entry.sh
#     (step 2.6.2) at each workstream close-out when a root monolith is detected.
#     Full idempotency (re-entrant, safe to call repeatedly) makes this safe.
#
# Spec backlink: docs/plans/2026-05-19-completion-log-phase1-foundational-loop.md § Chunk 7
#
# Background: The original completion-log format used one append-only monolith per
# month (archive/completed/YYYY-MM.md). The new format uses per-entry files under
# archive/completed/YYYY-MM/<slug>.md. query-completions glob targets the per-entry
# shape and intentionally excludes legacy/ from result sets (absence-as-signal
# doctrine — historical monolith entries are not backfilled as per-entry files).
#
# Concurrency: reentrant; called per-close-out (automatic) or PM one-shot. Full idempotency makes concurrent or repeated invocations safe.
# Review: code-reviewer — Concurrency field was stale; contradicted the new Per-close-out invocation context added at lines 7–11.
# Idempotency: full. Running twice on an already-migrated repo is a no-op (the root
# scan finds no YYYY-MM.md files; legacy/ subdirectory may already exist — that's fine).
# Resume: `git mv` is atomic per file; a partial run (e.g. Ctrl-C after 2 of 3 files)
# leaves moved files committed. Re-running picks up remaining files and skips already-moved
# ones (they no longer exist at the root).
#
# Usage:
#   cd <repo-root>
#   bash ~/.claude/plugins/coordinator/bin/migrate-completion-log-legacy.sh
#
# Or, with an explicit repo root:
#   REPO_ROOT=/path/to/repo bash migrate-completion-log-legacy.sh
#
# Exit codes:
#   0 — success (0 or more files moved, or no-op)
#   1 — usage or environment error (not in a repo with archive/completed/)
#   2 — one or more git mv operations failed

set -euo pipefail

# ---------------------------------------------------------------------------
# Root resolution: explicit flag → env var → marker auto-discovery → hard error
# ---------------------------------------------------------------------------

REPO_ROOT=""

# Pass --root <path> to override auto-discovery (useful for tests/CI).
if [[ "${1:-}" == "--root" && -n "${2:-}" ]]; then
  REPO_ROOT="$2"
  shift 2
elif [[ "${1:-}" == --root=* ]]; then
  REPO_ROOT="${1#--root=}"
  shift 1
fi

# Env var override (MIGRATION_REPO_ROOT takes precedence over git discovery).
if [[ -z "$REPO_ROOT" && -n "${MIGRATION_REPO_ROOT:-}" ]]; then
  REPO_ROOT="$MIGRATION_REPO_ROOT"
fi

# Auto-discovery: walk up from cwd to git toplevel.
if [[ -z "$REPO_ROOT" ]]; then
  REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || {
    echo "ERROR: not inside a git repository." >&2
    echo "  Remediation: run from a git repo root, or set MIGRATION_REPO_ROOT=<path>." >&2
    exit 1
  }
fi

# Verify archive/completed/ exists — this is the per-repo scope guard.
COMPLETED_DIR="$REPO_ROOT/archive/completed"
if [[ ! -d "$COMPLETED_DIR" ]]; then
  echo "ERROR: archive/completed/ not found under: $REPO_ROOT" >&2
  echo "  Remediation: run from a repo that uses the completion-log layout, or set" >&2
  echo "  MIGRATION_REPO_ROOT to the correct repo root." >&2
  exit 1
fi

LEGACY_DIR="$COMPLETED_DIR/legacy"

echo "=== migrate-completion-log-legacy.sh ==="
echo "Repo: $REPO_ROOT"
echo "Source dir: $COMPLETED_DIR"
echo "Target dir: $LEGACY_DIR"
echo ""

# ---------------------------------------------------------------------------
# Detect monolith files: YYYY-MM.md at the root of archive/completed/ only.
# Glob is restricted to that directory; files under subdirs are not touched.
# ---------------------------------------------------------------------------

MONOLITHS=()
while IFS= read -r line; do MONOLITHS+=("$line"); done < <(
  find "$COMPLETED_DIR" -maxdepth 1 -name '[0-9][0-9][0-9][0-9]-[0-9][0-9].md' -type f \
  | sort
)

if [[ ${#MONOLITHS[@]} -eq 0 ]]; then
  echo "No legacy monolith files found at the root of archive/completed/."
  echo "Nothing to migrate — this repo is already in the per-entry layout, or was"
  echo "already migrated. Exiting (no-op)."
  exit 0
fi

echo "Found ${#MONOLITHS[@]} legacy monolith file(s):"
for f in "${MONOLITHS[@]}"; do
  echo "  $f"
done
echo ""

# Create legacy/ directory if absent (git mv won't create it automatically).
if [[ ! -d "$LEGACY_DIR" ]]; then
  mkdir -p "$LEGACY_DIR"
  echo "Created: $LEGACY_DIR"
fi

# ---------------------------------------------------------------------------
# Move each monolith: git mv so git tracks the rename.
# ---------------------------------------------------------------------------

MOVED=0
FAILED=0
FAILED_FILES=()

for src in "${MONOLITHS[@]}"; do
  filename=$(basename "$src")
  dst="$LEGACY_DIR/$filename"

  # Idempotency guard: if destination already exists, the file was moved in a
  # previous (partial) run. Skip without error.
  if [[ -e "$dst" ]]; then
    echo "SKIP (already at destination): $filename"
    continue
  fi

  echo "MOVE: archive/completed/$filename  →  archive/completed/legacy/$filename"
  if git -C "$REPO_ROOT" mv "$src" "$dst"; then
    MOVED=$((MOVED + 1))
  else
    echo "  FAIL: git mv returned non-zero for $filename" >&2
    FAILED=$((FAILED + 1))
    FAILED_FILES+=("$filename")
  fi
done

echo ""
echo "=== Summary ==="
echo "  Moved:  $MOVED"
echo "  Failed: $FAILED"
echo ""

if [[ $MOVED -gt 0 ]]; then
  echo "Next step: commit the staged renames."
  echo "  git commit -m 'migrate: move legacy completion monoliths under archive/completed/legacy/'"
  echo ""
fi

echo "Note: legacy/ entries are excluded from query-completions results."
echo "  query-completions.sh targets archive/completed/*/*.md (per-entry files)."
echo "  Files under archive/completed/legacy/ are in that glob's scope as one of"
echo "  the '*' segments, BUT query-records.js excludes the legacy/ bucket from"
echo "  result sets (absence-as-signal doctrine — monolith content is not backfilled)."
echo "  See: docs/plans/2026-05-19-completion-log-phase1-foundational-loop.md § Chunk 2"
echo ""

if [[ $FAILED -gt 0 ]]; then
  echo "ERROR: the following files failed to move:" >&2
  for f in "${FAILED_FILES[@]}"; do
    echo "  $f" >&2
  done
  exit 2
fi

exit 0
