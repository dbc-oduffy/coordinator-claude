"""Shared repo-root resolver for coordinator-standard tripwire test templates,
independent of each template's own depth in the tree."""

from __future__ import annotations

import os
from pathlib import Path


def resolve_repo_root(start: str | Path) -> Path | None:
    """Resolve a guard template's repo root without a hand-counted parents[N].

    Order: TRIPWIRE_REPO_ROOT env override wins outright; otherwise walk
    upward from `start` for the first ancestor containing a `.git` entry.
    Returns None when neither resolves, so a caller can emit its own skip.
    """
    env_root = os.environ.get("TRIPWIRE_REPO_ROOT", "")
    if env_root:
        return Path(env_root).resolve()

    for ancestor in Path(start).resolve().parents:
        if (ancestor / ".git").exists():
            return ancestor

    return None
