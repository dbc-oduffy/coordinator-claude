"""
_copy_leg_capability_index -- capability-index leg of the Copies line.

One question: is `state/capabilities/fleet-index.json` in the live engine clone
still inside its own declared `ttl`, measured from its own `generated_at`.
Single axis (currency). Spawn-free; re-derived against `now` on every boot and
never served from the git-keyed cache.

Invariants:
    - An absent file, unparseable `generated_at` or `ttl`, or no engine clone is
      could-not-check; an unparseable ttl is never assumed fresh.
    - The engine clone comes from the live-tree registry rung, never the resolved
      engine root (which has no `state/`).
    - The remedy launcher is resolved by file existence only; none resolving
      yields the `no local remedy` verdict naming the engine repo.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _copy_currency as cc  # noqa: E402

COPY = "capability-index"
INDEX_RELPATH = "state/capabilities/fleet-index.json"
OP_KEY = "fleet.aggregate_capability_index"

#: Settings-home launcher names that expose `fleet.aggregate_capability_index`.
REMEDY_LAUNCHER_CANDIDATES = ("coordinator-fleet-aggregate-capability-index",)

_NO_CLONE = "no claude-klabauter clone registered"

_DURATION_RE = re.compile(
    r"^P(?!$)(?:(\d+)Y)?(?:(\d+)M)?(?:(\d+)W)?(?:(\d+)D)?"
    r"(?:T(?=\d)(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$"
)


def parse_duration(raw: object) -> timedelta | None:
    """ISO-8601 duration subset (Y/M/W/D/H/M/S) to a timedelta; None if unparseable."""
    if not isinstance(raw, str):
        return None
    m = _DURATION_RE.match(raw.strip())
    if not m:
        return None
    y, mo, w, d, h, mi, s = (int(g) if g else 0 for g in m.groups())
    return timedelta(days=y * 365 + mo * 30 + w * 7 + d, hours=h, minutes=mi, seconds=s)


def parse_timestamp(raw: object) -> datetime | None:
    """ISO-8601 instant to an aware UTC datetime; naive values are taken as UTC."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _default_claude_klabauter_root() -> str | None:
    import _engine_root

    return _engine_root._resolve_live_working_tree()[0]


def resolve_remedy(
    settings_home: Path | None = None,
    candidates: tuple[str, ...] = REMEDY_LAUNCHER_CANDIDATES,
) -> str:
    """Name the launcher invocation for the index op, or the no-local-remedy literal.

    Existence checks only; never executes or probes a launcher.
    """
    try:
        if settings_home is None:
            import _engine_root

            settings_home = _engine_root._settings_home()
        bin_dir = Path(settings_home) / "bin"
        suffix = ".exe" if os.name == "nt" else ""
        for name in candidates:
            launcher = bin_dir / (name + suffix)
            if launcher.is_file():
                return str(launcher)
    except Exception:  # noqa: BLE001 -- an unresolvable remedy is the literal, not an error
        pass
    return cc.no_local_remedy("claude-klabauter")


def _humanize_overdue(delta: timedelta) -> str:
    days = delta.days
    if days >= 1:
        return f"{days}d"
    return f"{int(delta.total_seconds() // 3600)}h"


def check_capability_index(
    claude_klabauter_root: Callable[[], str | None] | str | Path | None = None,
    now: datetime | None = None,
    remedy: Callable[[], str] = resolve_remedy,
) -> cc.CopyVerdict:
    """Verdict for the capability-index copy. `claude_klabauter_root` may be a path or provider."""
    root = claude_klabauter_root() if callable(claude_klabauter_root) else claude_klabauter_root
    if claude_klabauter_root is None:
        root = _default_claude_klabauter_root()
    if not root:
        return cc.could_not_check(COPY, cc.CURRENCY, _NO_CLONE)
    path = Path(root) / INDEX_RELPATH
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return cc.could_not_check(COPY, cc.CURRENCY, f"{INDEX_RELPATH} absent")
    except (OSError, ValueError) as exc:
        return cc.could_not_check(
            COPY, cc.CURRENCY, f"{INDEX_RELPATH} unreadable ({type(exc).__name__})"
        )
    if not isinstance(data, dict):
        return cc.could_not_check(COPY, cc.CURRENCY, f"{INDEX_RELPATH} is not a JSON object")
    generated_raw, ttl_raw = data.get("generated_at"), data.get("ttl")
    generated = parse_timestamp(generated_raw)
    if generated is None:
        return cc.could_not_check(
            COPY, cc.CURRENCY, f"unparseable generated_at {generated_raw!r}"
        )
    ttl = parse_duration(ttl_raw)
    if ttl is None:
        return cc.could_not_check(COPY, cc.CURRENCY, f"unparseable ttl {ttl_raw!r}")
    current_time = now or datetime.now(timezone.utc)
    expiry = generated + ttl
    if expiry < current_time:
        return cc.CopyVerdict(
            COPY,
            cc.CURRENCY,
            cc.DRIFT,
            detail=f"expired {_humanize_overdue(current_time - expiry)} past {ttl_raw}",
            remedy=remedy(),
        )
    return cc.CopyVerdict(
        COPY,
        cc.CURRENCY,
        cc.CURRENT,
        evidence=f"generated_at {generated_raw} within ttl {ttl_raw}",
    )


def leg(
    claude_klabauter_root: Callable[[], str | None] | str | Path | None = None,
    now: datetime | None = None,
    remedy: Callable[[], str] = resolve_remedy,
) -> cc.CopyVerdict:
    """The leg as the banner calls it: wrapped so it can never raise or render current unrun."""
    return cc.run_leg(
        COPY, cc.CURRENCY, lambda: check_capability_index(claude_klabauter_root, now, remedy)
    )
