#!/usr/bin/env bash
# migrate-cross-repo-layout.sh — One-time idempotent migration primitive.
#
# Purpose: Re-homes a repo's cross-repo memo channel from the legacy flat layout to
# the inbox/archive co-located layout.
#   - cross-repo/*.md (non-README) → cross-repo/inbox/
#   - archive/cross-repo/*         → cross-repo/archive/
#   - Removes top-level archive/cross-repo/ if empty after moves.
#
# Spec backlink: docs/plans/2026-05-23-cross-repo-inbox-archive-restructure.md § Chunk F
#
# Idempotency basis:
#   The glob `cross-repo/*.md` is NON-RECURSIVE — it cannot match
#   `cross-repo/inbox/*.md` or `cross-repo/archive/*.md`. After the first run,
#   the only file at `cross-repo/*.md` is README.md (explicit exclusion →
#   zero moves → no-op). No special "skip-if-moved" logic needed; glob geometry
#   is the guard.
#
# Target-collision behaviour (per plan MN4):
#   If a target file already exists in inbox/ or archive/ (e.g. partial prior run),
#   `git mv` FAILS LOUD with the conflicting filename. Do NOT silently overwrite.
#   A same-named file in inbox/ is a real conflict the operator must resolve.
#
# Concurrency: single-shot local op, non-resumable but idempotent.
#
# Usage:
#   cd <repo-root>
#   bash migrate-cross-repo-layout.sh
#
#   Or with explicit repo root:
#   bash migrate-cross-repo-layout.sh --root /path/to/repo
#
# Exit codes:
#   0 — success (N moves or idempotent no-op)
#   1 — usage/environment error or target-collision detected
#   2 — one or more git mv operations failed

set -euo pipefail

# ---------------------------------------------------------------------------
# Root resolution: explicit flag → env var → git auto-discovery → hard error
# ---------------------------------------------------------------------------

REPO_ROOT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --root)
      REPO_ROOT="$2"
      shift 2
      ;;
    --help|-h)
      grep '^#' "$0" | sed 's/^#[[:space:]]\{0,1\}//'
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      echo "Usage: $0 [--root <repo-root>]" >&2
      exit 1
      ;;
  esac
done

if [[ -z "$REPO_ROOT" ]]; then
  if git_root=$(git rev-parse --show-toplevel 2>/dev/null); then
    REPO_ROOT="$git_root"
  else
    echo "ERROR: not inside a git repo and --root not supplied." >&2
    echo "Remediation: run from within a git repo or pass --root <path>." >&2
    exit 1
  fi
fi

if [[ ! -d "$REPO_ROOT" ]]; then
  echo "ERROR: repo root does not exist: $REPO_ROOT" >&2
  exit 1
fi

# Ensure we're actually inside (or at) a git repo.
if ! git -C "$REPO_ROOT" rev-parse --show-toplevel >/dev/null 2>&1; then
  echo "ERROR: $REPO_ROOT is not a git repository." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

CROSS_REPO_DIR="${REPO_ROOT}/cross-repo"
INBOX_DIR="${CROSS_REPO_DIR}/inbox"
ARCHIVE_DIR="${CROSS_REPO_DIR}/archive"
LEGACY_ARCHIVE_DIR="${REPO_ROOT}/archive/cross-repo"

# ---------------------------------------------------------------------------
# Ensure destination subdirs exist
# ---------------------------------------------------------------------------

mkdir -p "$INBOX_DIR" "$ARCHIVE_DIR"

# ---------------------------------------------------------------------------
# Phase 1: move flat cross-repo/*.md (non-README) → cross-repo/inbox/
# ---------------------------------------------------------------------------

inbox_moves=0

for src in "${CROSS_REPO_DIR}"/*.md; do
  # Glob produces the literal pattern string when nothing matches.
  [[ -f "$src" ]] || continue

  filename="$(basename "$src")"

  # Explicit exclusion: skip README.md.
  if [[ "$filename" == "README.md" ]]; then
    continue
  fi

  target="${INBOX_DIR}/${filename}"

  # Fail loud on target-collision — do NOT silently overwrite.
  if [[ -e "$target" ]]; then
    echo "ERROR: target already exists (collision): ${target}" >&2
    echo "  Source: ${src}" >&2
    echo "  Resolve the conflict manually, then re-run." >&2
    exit 1
  fi

  # Use git mv for tracked files; plain mv + git add/rm for untracked.
  # Untracked files exist on disk but have no git history — git mv would fail on them.
  if git -C "$REPO_ROOT" ls-files --error-unmatch "${src#"$REPO_ROOT/"}" >/dev/null 2>&1; then
    # Tracked: git mv stages the rename atomically.
    if ! git -C "$REPO_ROOT" mv "${src#"$REPO_ROOT/"}" "${target#"$REPO_ROOT/"}"; then
      echo "ERROR: git mv failed for: $src → $target" >&2
      exit 2
    fi
  else
    # Untracked: plain mv + git add at destination (no git rm needed — file wasn't tracked).
    if ! mv "$src" "$target"; then
      echo "ERROR: mv failed for: $src → $target" >&2
      exit 2
    fi
    if ! git -C "$REPO_ROOT" add "${target#"$REPO_ROOT/"}"; then
      echo "ERROR: git add failed for: $target" >&2
      exit 2
    fi
  fi

  echo "  inbox: ${filename}"
  (( inbox_moves++ )) || true
done

# ---------------------------------------------------------------------------
# Phase 2: move archive/cross-repo/* → cross-repo/archive/
# ---------------------------------------------------------------------------

archive_moves=0

if [[ -d "$LEGACY_ARCHIVE_DIR" ]]; then
  # Use find -maxdepth 1 to enumerate top-level entries (files and dirs)
  # excluding . and .. — handles dotfiles (e.g. .dogfood-postscript.md).
  while IFS= read -r -d '' src; do
    filename="$(basename "$src")"
    target="${ARCHIVE_DIR}/${filename}"

    # Fail loud on target-collision.
    if [[ -e "$target" ]]; then
      echo "ERROR: target already exists (collision): ${target}" >&2
      echo "  Source: ${src}" >&2
      echo "  Resolve the conflict manually, then re-run." >&2
      exit 1
    fi

    # Use git mv for tracked files; plain mv + git add for untracked.
    if git -C "$REPO_ROOT" ls-files --error-unmatch "${src#"$REPO_ROOT/"}" >/dev/null 2>&1; then
      # Tracked: git mv stages the rename atomically.
      if ! git -C "$REPO_ROOT" mv "${src#"$REPO_ROOT/"}" "${target#"$REPO_ROOT/"}"; then
        echo "ERROR: git mv failed for: $src → $target" >&2
        exit 2
      fi
    else
      # Untracked: plain mv + git add at destination.
      if ! mv "$src" "$target"; then
        echo "ERROR: mv failed for: $src → $target" >&2
        exit 2
      fi
      if ! git -C "$REPO_ROOT" add "${target#"$REPO_ROOT/"}"; then
        echo "ERROR: git add failed for: $target" >&2
        exit 2
      fi
    fi

    echo "  archive: ${filename}"
    (( archive_moves++ )) || true
  done < <(find "$LEGACY_ARCHIVE_DIR" -maxdepth 1 -mindepth 1 -print0)
fi

# ---------------------------------------------------------------------------
# Phase 3: remove the now-empty top-level archive/cross-repo/ directory
# ---------------------------------------------------------------------------

archive_removed=false

if [[ -d "$LEGACY_ARCHIVE_DIR" ]]; then
  # Only remove if empty — guard against partial failure leaving files behind.
  remaining=$(find "$LEGACY_ARCHIVE_DIR" -maxdepth 1 -mindepth 1 | wc -l | tr -d ' ')
  if [[ "$remaining" -eq 0 ]]; then
    rmdir "$LEGACY_ARCHIVE_DIR"
    archive_removed=true
  else
    echo "WARNING: archive/cross-repo/ not empty after moves (${remaining} items remain); leaving in place." >&2
  fi
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo ""
echo "migrate-cross-repo-layout: complete"
echo "  inbox moves:   ${inbox_moves}"
echo "  archive moves: ${archive_moves}"
if [[ "$archive_removed" == true ]]; then
  echo "  archive/cross-repo/ removed (was empty)"
else
  if [[ -d "$LEGACY_ARCHIVE_DIR" ]]; then
    echo "  archive/cross-repo/ skipped (not empty or not present)"
  else
    echo "  archive/cross-repo/ not present (already clean)"
  fi
fi

if [[ "$inbox_moves" -eq 0 && "$archive_moves" -eq 0 ]]; then
  echo "  (no-op: nothing to migrate)"
fi
