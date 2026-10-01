"""Shared `watch_heartbeat` resolver + verdict-line renderer for the three
GROUP EM WATCH emitters (`group-em-autofire.py`, `session-start-watch-
presence.py`, `coordinator/bin/group-em-watch-cli.py`).

One home for `_resolve_watch_module()` and the `GROUP EM WATCH:` format string.
`coordinator/hooks/scripts/` already hosts shared `_`-prefixed
modules (`_next_move_ledger.py` et al., imported by
`watchdog-undischarged-next-move.py` via the same sys.path-insert idiom used
here), so the per-hook-independence posture (docs/decisions/DR-must-agree-helpers-have-one-home.md) does not cover
this case: it is about hooks not importing EACH OTHER, not about refusing a
shared helper.

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


def age_phrase(last_tick_at: Any) -> Optional[str]:
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
    if not result:
        return None
    verdict = result.get("verdict")
    if not verdict:
        return None

    age = age_phrase(result.get("last_tick_at"))
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
            f"this watch's record{held} has no live holder. "
            "Nobody is watching. Arm one with /group-em."
        )
    else:
        tail = (
            "no watch has ever reported for this repo. NOT an all-clear: nothing has "
            "looked. Arm one with /group-em."
        )
    return f"GROUP EM WATCH: {verdict} — {tail}"


def render_watch_line(repo_root: str) -> Optional[str]:
    module = resolve_watch_module()
    if module is None:
        return None
    try:
        return render_verdict_line(module.read_watch(repo_root))
    except Exception:  # noqa: BLE001
        return None
