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


def group_em_identity(repo_root: str) -> Optional[dict]:
    """The engine's one decision on who the Group EM is (`nomination.identify`), or None.

    Any failure, including an engine that predates `identify`, is None -- never a locally
    composed guess at the holder."""
    try:
        import _engine_root

        root = _engine_root.resolve_claude_klabauter_root()
        if not root:
            return None
        _engine_root.place_engine_root_on_path(root)
        from coordinator_core.group_em import nomination

        identify = getattr(nomination, "identify", None)
        identity = identify(repo_root) if identify else None
        return identity if isinstance(identity, dict) else None
    except Exception as exc:  # noqa: BLE001
        print(f"watch-presence: group-em identify failed ({type(exc).__name__}); presence line omitted", file=sys.stderr)
        return None


def session_is_group_em(identity: Optional[dict], session_id: Any) -> bool:
    """True when the engine identity names this session as a live or pending Group EM holder."""
    if not identity or not isinstance(session_id, str) or not session_id:
        return False
    holder = identity.get("holder") or {}
    return identity.get("state") in ("live", "pending") and holder.get("session_id") == session_id


def identity_holder_name(identity: Optional[dict]) -> Optional[str]:
    holder = (identity or {}).get("holder") or {}
    return holder.get("name") or None


def render_verdict_line(result: Optional[dict], holder_fallback: Optional[str] = None) -> Optional[str]:
    """The one `GROUP EM WATCH:` line; `holder_fallback` names the holder when the watch read does not."""
    if not result:
        return None
    verdict = result.get("verdict")
    if not verdict:
        return None

    age = age_phrase(result.get("last_tick_at"))
    holder = result.get("holder_name") or result.get("holder_session_id") or holder_fallback

    if verdict == _verdict_constant("VERDICT_ARMED", "armed"):
        checked = f"checked {age} ago" if age else "is running"
        held = f", held by {holder}" if holder else ""
        tail = f"{checked}{held}."
    elif verdict == _verdict_constant("VERDICT_STALE", "stale"):
        checked = f"last checked {age} ago," if age else ""
        tail = f"{checked} past its deadline. Re-arm: /group-em.".strip()
    elif verdict == vacant_verdict():
        held = f" ({holder})" if holder else ""
        tail = f"no live holder{held}. Arm: /group-em."
    else:
        tail = "never reported. NOT an all-clear: nothing has looked. Arm: /group-em."
    return f"GROUP EM WATCH: {verdict} — {tail}"


def render_watch_line(repo_root: str) -> Optional[str]:
    module = resolve_watch_module()
    if module is None:
        return None
    try:
        return render_verdict_line(module.read_watch(repo_root))
    except Exception:  # noqa: BLE001
        return None
