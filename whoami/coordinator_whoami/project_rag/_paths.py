"""User marker directory resolution — inlined from project-rag/core/marker_dir.py.

Only `resolve_user_marker_dir` is needed by the whoami probe; the broader marker_dir
module (notably `resolve_project_marker_dir`) stays at project-rag, where multiple
other consumers (project_rag_ue_addon, install scripts) depend on it. Inlining a
single function here avoids pulling the whole module and creating a cross-package
dependency.

User-scope has NO legacy migration. The legacy ``~/.claude/example-game-repo/`` name was
retired 2026-05-21 at the source (project-rag commit eaa2df4fc) — that path is now
actively owned by the example-game-workbench-repo install pipeline (install-status.json,
install-logs/), so treating it as a project-rag legacy emitted a false-positive
``BOTH`` warning ("marker_dir: both … exist — reconcile manually") on every whoami.
This copy previously lagged that fix — it was inlined at pre-fix SHA bfb57533 and
still carried the retired legacy name — and has been re-synced to the
post-retirement source. See project-rag core/marker_dir.py resolve_user_marker_dir.

Spec backlink (origin): docs/plans/2026-05-19-first-class-install-redesign.md §W3 — file lives at project-rag (not imported; preserved at source).
Re-anchored backlink (this repo): docs/plans/2026-05-19-whoami-substrate-migration.md § 8 Task 2
"""
from __future__ import annotations

import os
from pathlib import Path

# Canonical name under ~/.claude/. There is no user-scope legacy name — see module docstring.
USER_MARKER_DIR_NAME = "project-rag"


def resolve_user_marker_dir() -> Path:
    """Return the canonical ``~/.claude/project-rag`` path.

    No legacy migration — the user-scope legacy name was retired 2026-05-21
    (see module docstring). Callers are responsible for ``mkdir`` if needed.
    """
    return Path.home() / ".claude" / USER_MARKER_DIR_NAME


# ---------------------------------------------------------------------------
# Install-artifact resolver — install-profile.json settings-home data plane
# ---------------------------------------------------------------------------
# DR-072 (docs/decisions/DR-072-durable-machine-local-coordinator-state-lives-in-settings-home-not-claude.md)
# classifies the legacy ~/.claude/project-rag/install-profile.json write as an
# ELECTIVE-DEFECT: durable coordinator/adopter state belongs on the settings-home
# data plane (<settings-home>/project-rag/), not under ~/.claude/. project-rag
# has already repointed its own writers off resolve_user_marker_dir() — that
# function (above) now stays live ONLY as a read-only draining anchor for the
# legacy plane. This block is our own inlined mirror of project-rag's
# core/marker_dir.py::resolve_install_artifact_path /
# read_install_artifact_path, built on an inlined mirror of
# core/machine_local_reader.py's data-home ladder — added alongside
# resolve_user_marker_dir(), never editing it (that function is a byte-faithful
# parity mirror per project-rag's explicit instruction).
#
# Spec backlink: cross-repo/inbox/2026-08-15-project-rag-em-ac5-classification-and-the-persist-writer.md


def _settings_home() -> Path:
    """coordinator-settings-home root, by pure path arithmetic (never a file read).

    Same two-rung ladder every settings-home consumer in this repo carries
    (``COORDINATOR_SETTINGS_HOME`` override — empty/whitespace treated as
    unset — else ``${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings``).
    Inlined here, not imported, for the same standalone-distributable-package
    reason ``coordinator_whoami.host_probes._settings_home`` inlines its own
    copy: this package cannot import across the ``coordinator/hooks`` or
    ``coordinator/templates`` package boundary.
    """
    override = os.environ.get("COORDINATOR_SETTINGS_HOME")
    if override is not None and override.strip():
        return Path(override.strip())
    home = os.environ.get("CLAUDE_HOME") or os.path.expanduser("~")
    return Path(home) / ".coordinator-claude-settings"


def _data_home() -> Path:
    """Resolve the project-rag consumer durable-data root. Never raises.

    Faithful arithmetic mirror of project-rag's
    ``core/machine_local_reader.py::_resolve_data_home()`` four effective
    rungs:
        1. ``PROJECT_RAG_DATA_HOME`` env (``.strip()``-reject-empty,
           ``.resolve()`` with an ``(OSError, ValueError)`` fallback to the
           unresolved ``Path``);
        2. ``_settings_home() / "project-rag"`` if it exists on disk
           (go-forward new default);
        3. legacy top-level ``Path(_claude_home()) / ".project-rag"`` if IT
           exists;
        4. else the rung-2 arithmetic as the go-forward default.

    Never raises, performs no migration side-effect, creates no directory.
    Deliberately NOT memoized — project-rag's ``data_home()`` memoizes because
    it backs a long-lived daemon process where the resolved root is constant
    for process life; this module backs a short-lived CLI/probe invocation, where
    re-resolving per call is correct and keeps tests monkeypatch-safe
    across env-mutation regimes without a ``_reset_for_tests()`` companion.
    """
    override = os.environ.get("PROJECT_RAG_DATA_HOME")
    if override is not None and override.strip():
        try:
            return Path(override.strip()).resolve()
        except (OSError, ValueError):
            return Path(override.strip())
    new_dir = _settings_home() / "project-rag"
    if new_dir.exists():
        return new_dir
    claude_home = os.environ.get("CLAUDE_HOME") or os.path.expanduser("~")
    legacy_dir = Path(claude_home) / ".project-rag"
    if legacy_dir.exists():
        return legacy_dir
    return new_dir


def resolve_install_artifact_path(filename: str) -> Path:
    """Return the settings-home data-plane WRITE target for *filename*.

    Pure arithmetic — ``_data_home() / filename`` — never reads the legacy
    ``~/.claude/project-rag/`` path. Writers (``envelope.py::persist``,
    ``cli.py``'s persist helper) call this directly for the write target;
    readers/merge-reads should use ``read_install_artifact_path()`` below.
    """
    return _data_home() / filename


def read_install_artifact_path(filename: str) -> Path:
    """Resolve *filename* for READS/merge-reads: new data-plane path if it
    exists, else the legacy ``resolve_user_marker_dir() / filename`` path if
    IT exists, else the new path (go-forward default for a fresh install).

    Negative-spec — deliberate divergence from the mirrored project-rag
    source (``core/marker_dir.py::read_install_artifact_path``): project-rag's
    version forward-copies the legacy file onto the new plane on this read
    path. This function does NOT forward-copy. We are a writer, not a
    read-only consumer — our two callers immediately re-write the merged
    content onto the new plane right after this call, which drains the
    legacy copy on its own. A future syncer reconciling this module against
    project-rag's source should NOT "restore" the forward-copy behavior here.
    """
    new_path = resolve_install_artifact_path(filename)
    if new_path.exists():
        return new_path
    legacy_path = resolve_user_marker_dir() / filename
    if not legacy_path.exists():
        return new_path
    return legacy_path
