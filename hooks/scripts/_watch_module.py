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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


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


def _verdict_constant(attr: str, fallback: str) -> str:
    """One verdict string, from `watch_heartbeat` where it is reachable.

    Callers compare a read verdict against these rather than against literals,
    so the vocabulary keeps one home. Resolution can fail (that is this
    module's whole fail-open posture) and a hook must not crash deciding which
    sentence to print, so the literal stands in.
    """
    module = resolve_watch_module()
    return getattr(module, attr, fallback) if module else fallback


def vacant_verdict() -> str:
    """The `vacant` verdict string, from `watch_heartbeat` where it is reachable.

    Callers compare a read verdict against this rather than a literal, so the
    constant keeps one home. Resolution can fail (that is this module's whole
    fail-open posture), and a hook must not crash deciding which sentence to
    print -- so the literal stands in, matching `watch_heartbeat.VERDICT_VACANT`.
    """
    return _verdict_constant("VERDICT_VACANT", "vacant")


def _age_phrase(last_tick_at: Any) -> Optional[str]:
    """"3 seconds", "41 minutes", "2 hours" from an ISO stamp, or `None`.

    Unparseable is `None`, never "0 seconds": a fabricated age on this line is
    the exact hazard the line exists to end.
    """
    if not isinstance(last_tick_at, str) or not last_tick_at:
        return None
    text = last_tick_at.replace("Z", "+00:00")
    try:
        stamped = datetime.fromisoformat(text)
    except ValueError:
        return None
    if stamped.tzinfo is None:
        stamped = stamped.replace(tzinfo=timezone.utc)
    seconds = (datetime.now(timezone.utc) - stamped).total_seconds()
    if seconds < 0:
        return None
    if seconds < 90:
        return f"{int(seconds)} seconds"
    if seconds < 5400:
        return f"{int(seconds // 60)} minutes"
    return f"{seconds / 3600:.1f} hours"


def render_verdict_line(result: Optional[dict]) -> Optional[str]:
    """Render the human-facing `GROUP EM WATCH:` line from an already-read verdict.

    The verdict word stays first and unchanged -- it is what every emitter and
    test keys on. What follows is the half a person needs and a bare category
    never supplied: how long ago the watch actually checked, and what to do.

    The distinction being carried is that a quiet watch and a dead one are NOT
    the same state, and the four verdicts already tell them apart -- `armed`
    means a tick landed inside its own deadline, not merely that a record
    exists. A reader who cannot see the age reads all four as "some word about
    the watch" and asks the nearest human, which is how a live watch gets
    reported dead.
    """
    if not result:
        return None
    verdict = result.get("verdict")
    if not verdict:
        return None

    age = _age_phrase(result.get("last_tick_at"))
    holder = result.get("holder_name") or result.get("holder_session_id")

    if verdict == _verdict_constant("VERDICT_ARMED", "armed"):
        checked = f"checked {age} ago" if age else "is running"
        held = f", held by {holder}" if holder else ""
        tail = f"{checked}{held}. Quiet between checks is normal, not a fault."
    elif verdict == _verdict_constant("VERDICT_STALE", "stale"):
        checked = f"last checked {age} ago and is" if age else "is"
        tail = f"{checked} past the deadline it set itself. Re-arm it with /group-em."
    elif verdict == vacant_verdict():
        held = f" ({holder})" if holder else ""
        tail = (
            f"the session holding this watch{held} has exited, leaving its record behind. "
            "Nobody is watching. Arm one with /group-em."
        )
    else:
        tail = (
            "no watch has ever reported for this repo. This is NOT an all-clear: nothing has "
            "looked. Arm one with /group-em."
        )
    return f"GROUP EM WATCH: {verdict} — {tail}"


def render_watch_line(repo_root: str) -> Optional[str]:
    """Read `repo_root`'s watch record and render its line, fail-open.

    Returns `None` on any resolution or read failure rather than
    fabricating a verdict -- the single shape all three emitters print.
    """
    module = resolve_watch_module()
    if module is None:
        return None
    try:
        return render_verdict_line(module.read_watch(repo_root))
    except Exception:  # noqa: BLE001
        return None
