"""_protected_act -- the closed enum of acts a hook deny may protect, and the advise-and-record seam.

A hook may deny only an act in PROTECTED_ACTS. Every other would-be deny is recorded to the
friction log and injects nothing into context. The roster
(`tests/baselines/hook-registration-roster.json`) maps each deny-capable guard id or script
name to its enum value under `protected_acts`.

Stdlib-only; every I/O failure fails open (a hook must never break on its own bookkeeping).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _git_root_walk import git_root_walk  # noqa: E402

#: box-degrading: filling the disk, runaway processes, a true whole-filesystem scan, destroying
#: data or git history. irreversible-external: push or PR to a non-owned remote, p4 submit,
#: mail, release, publish into a mirror.
PROTECTED_ACTS = frozenset({"box-degrading", "irreversible-external"})

FRICTION_LOG_RELPATH = Path(".coordinator-local") / "hook-friction.jsonl"

_ROSTER = Path(__file__).resolve().parents[2] / "tests" / "baselines" / "hook-registration-roster.json"


def _load_roster(roster_path: Path | None = None) -> dict:
    # TRAP: fails toward advise -- a missing or unreadable roster (e.g. a mirror that does not ship
    # tests/) leaves every guard without a protected act, so even irreversible-act denies are
    # recorded and dropped. Re-read on every call; callers on a per-guard loop pay one parse each.
    try:
        return json.loads((roster_path or _ROSTER).read_text(encoding="utf-8"))
    except Exception:
        return {}


def protected_act_for(guard_id: str, roster_path: Path | None = None) -> str | None:
    """The enum value the roster declares for `guard_id` (or its `.py` script name), else None.
    A value outside PROTECTED_ACTS is treated as undeclared."""
    acts = _load_roster(roster_path).get("protected_acts") or {}
    stem = guard_id[:-3] if guard_id.endswith(".py") else guard_id
    for key in (guard_id, stem, stem + ".py"):
        value = acts.get(key)
        if value in PROTECTED_ACTS:
            return value
    return None


def advise_and_record(guard_id: str, deny_text: str, event: str, repo: Path | None = None) -> None:
    """Append one JSON line {ts, guard_id, event, deny_text, cwd} to
    `<repo>/.coordinator-local/hook-friction.jsonl`. Returns None so the caller emits nothing
    into context. Fails open on any error."""
    try:
        cwd = os.getcwd()
        root = Path(repo) if repo else Path(git_root_walk(cwd) or cwd)
        path = root / FRICTION_LOG_RELPATH
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "guard_id": guard_id,
            "event": event,
            "deny_text": deny_text,
            "cwd": cwd,
        }
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        return None
    return None
