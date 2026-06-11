"""User marker directory resolution — inlined from X:/project-rag/core/marker_dir.py.

Only `resolve_user_marker_dir` is needed by the whoami probe; the broader marker_dir
module (notably `resolve_project_marker_dir`) stays at project-rag, where multiple
other consumers (project_rag_ue_addon, install scripts) depend on it. Inlining a
single function here avoids pulling the whole module and creating a cross-package
dependency. Source-of-origin: X:/project-rag/core/marker_dir.py at SHA bfb57533.

Spec backlink (origin): docs/plans/2026-05-19-first-class-install-redesign.md §W3 — file lives at X:/project-rag (not imported; preserved at source).
Re-anchored backlink (this repo): docs/plans/2026-05-19-whoami-substrate-migration.md § 8 Task 2
"""
from __future__ import annotations

import errno
import logging
import os
import shutil
from enum import Enum
from pathlib import Path

log = logging.getLogger("coordinator_whoami.project_rag._paths")

# Canonical (new) names
USER_MARKER_DIR_NAME = "project-rag"  # under ~/.claude/

# Legacy names — read-only; auto-migrated to canonical names on first resolve.
LEGACY_USER_MARKER_DIR_NAME = "holodeck"  # under ~/.claude/


class MarkerDirState(str, Enum):
    """Observed marker-dir state before any migration is attempted."""

    NEW_ONLY = "new_only"
    LEGACY_ONLY = "legacy_only"
    BOTH = "both"
    NEITHER = "neither"


def resolve_user_marker_dir() -> Path:
    """Return the canonical ``~/.claude/project-rag`` path.

    Auto-migrates ``~/.claude/holodeck`` if present and the canonical dir is
    absent. Same migration semantics as the project-rag-side original.
    """
    base = Path.home() / ".claude"
    return _resolve(
        base / USER_MARKER_DIR_NAME,
        base / LEGACY_USER_MARKER_DIR_NAME,
    )


# ---------------------------------------------------------------------------
# Internals (inlined verbatim from X:/project-rag/core/marker_dir.py bfb57533)
# ---------------------------------------------------------------------------

def _observe(canonical: Path, legacy: Path) -> MarkerDirState:
    new_exists = canonical.exists()
    legacy_exists = legacy.exists()
    if new_exists and legacy_exists:
        return MarkerDirState.BOTH
    if new_exists:
        return MarkerDirState.NEW_ONLY
    if legacy_exists:
        return MarkerDirState.LEGACY_ONLY
    return MarkerDirState.NEITHER


def _resolve(canonical: Path, legacy: Path) -> Path:
    """Resolve canonical path, migrating from legacy on first read.

    Race-tolerant: if a concurrent process wins the rename, this call
    observes the post-rename state and returns the canonical path. On
    cross-device (EXDEV) failure, falls back to copytree + rmtree. On any
    other unrecoverable failure, returns the legacy path so callers can
    still read existing data.
    """
    state = _observe(canonical, legacy)

    if state is MarkerDirState.BOTH:
        log.warning(
            "marker_dir: both %s and %s exist — using canonical, legacy left "
            "untouched. Reconcile manually (see /project-rag:doctor).",
            canonical,
            legacy,
        )
        return canonical

    if state is MarkerDirState.NEW_ONLY or state is MarkerDirState.NEITHER:
        return canonical

    # LEGACY_ONLY: attempt atomic rename. Race-tolerant.
    try:
        os.rename(legacy, canonical)
        log.info("marker_dir: migrated %s -> %s", legacy, canonical)
        return canonical
    except FileExistsError:
        log.debug("marker_dir: rename race lost (target now exists at %s)", canonical)
        return canonical
    except FileNotFoundError:
        log.debug("marker_dir: rename race lost (source already moved at %s)", legacy)
        return canonical
    except OSError as exc:
        if exc.errno == errno.EXDEV:
            return _cross_device_migrate(legacy, canonical)
        log.error(
            "marker_dir: rename %s -> %s failed: %s. Returning legacy path.",
            legacy,
            canonical,
            exc,
        )
        return canonical if canonical.exists() else legacy


def _cross_device_migrate(legacy: Path, canonical: Path) -> Path:
    """Fallback for EXDEV: copytree then rmtree, with race tolerance."""
    try:
        shutil.copytree(legacy, canonical)
    except FileExistsError:
        log.debug("marker_dir: copytree race lost (target exists at %s)", canonical)
        return canonical
    except OSError as exc:
        log.error(
            "marker_dir: cross-device copy %s -> %s failed: %s. Returning legacy path.",
            legacy,
            canonical,
            exc,
        )
        return canonical if canonical.exists() else legacy

    try:
        shutil.rmtree(legacy)
    except OSError as exc:
        log.warning(
            "marker_dir: cross-device migration copied %s -> %s but failed to "
            "remove legacy: %s. Manual cleanup required.",
            legacy,
            canonical,
            exc,
        )

    log.info("marker_dir: migrated (cross-device) %s -> %s", legacy, canonical)
    return canonical
