"""Shared `watch_heartbeat` resolver + verdict-line renderer for the three
GROUP EM WATCH emitters (`group-em-autofire.py`, `session-start-watch-
presence.py`, `coordinator/bin/group-em-watch-cli.py`).

<!-- Review: overengineering-reviewer -- hoisted from three byte-identical
copies of `_resolve_watch_module()` plus three independent `GROUP EM WATCH:`
format strings. `coordinator/hooks/scripts/` already hosts shared `_`-prefixed
modules (`_next_move_ledger.py` et al., imported by
`watchdog-undischarged-next-move.py` via the same sys.path-insert idiom used
here), so the per-hook-independence posture (DR-047/DR-118) does not cover
this case: it is about hooks not importing EACH OTHER, not about refusing a
shared helper. -->

`coordinator/skills/group-em/` is not an importable package name (the
directory carries a hyphen), so `watch_heartbeat` is resolved by file path,
exactly as every prior copy did. Every caller keeps its own fail-open
behaviour: resolution failure returns `None`/`None`, never raises, never
crashes the calling hook.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional


def resolve_watch_module(*, reraise: bool = False):
    """Import `watch_heartbeat` from its own source position.

    Returns `None` on any resolution failure so the caller can fail open --
    the default, used by the two hook emitters. `reraise=True` (used by the
    diagnostic CLI, which never fails open) instead lets the underlying
    exception propagate so the caller's own error message can chain it,
    rather than the caller getting only a bare "could not resolve" with the
    real cause discarded.
    """
    try:
        skills_dir = Path(__file__).resolve().parents[2] / "skills" / "group-em"
        skills_dir_str = str(skills_dir)
        if skills_dir_str not in sys.path:
            sys.path.insert(0, skills_dir_str)
        import watch_heartbeat  # noqa: F401

        return watch_heartbeat
    except Exception:  # noqa: BLE001
        if reraise:
            raise
        return None


def render_watch_line(repo_root: str) -> Optional[str]:
    """Render `GROUP EM WATCH: <verdict>` for `repo_root`, fail-open.

    Returns `None` on any resolution or read failure rather than
    fabricating a verdict -- the single shape all three emitters print.
    """
    module = resolve_watch_module()
    if module is None:
        return None
    try:
        result = module.read_watch(repo_root)
        return f"GROUP EM WATCH: {result['verdict']}"
    except Exception:  # noqa: BLE001
        return None
