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

from pathlib import Path

# Canonical name under ~/.claude/. There is no user-scope legacy name — see module docstring.
USER_MARKER_DIR_NAME = "project-rag"


def resolve_user_marker_dir() -> Path:
    """Return the canonical ``~/.claude/project-rag`` path.

    No legacy migration — the user-scope legacy name was retired 2026-05-21
    (see module docstring). Callers are responsible for ``mkdir`` if needed.
    """
    return Path.home() / ".claude" / USER_MARKER_DIR_NAME
