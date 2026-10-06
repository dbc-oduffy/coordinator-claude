"""Subject-repo resolution for scripts that inspect the caller's repo, never their own checkout.

Precedence: explicit argument, then `COORDINATOR_SUBJECT_REPO_ROOT`, then the nearest `.git`
ancestor of the cwd. A script's own `__file__` is never a rung: forwarded in-process it names
the engine checkout.
"""
from __future__ import annotations

import os
from pathlib import Path

SUBJECT_REPO_ENV = "COORDINATOR_SUBJECT_REPO_ROOT"


def subject_repo_root(explicit: "str | os.PathLike | None" = None) -> "Path | None":
    """The caller's repo root; None when no rung resolves."""
    for raw in (explicit, os.environ.get(SUBJECT_REPO_ENV)):
        if raw:
            return Path(raw).resolve()
    origin = Path.cwd().resolve()
    for candidate in (origin, *origin.parents):
        if (candidate / ".git").exists():
            return candidate
    return None
