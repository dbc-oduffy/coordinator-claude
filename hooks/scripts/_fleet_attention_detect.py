"""Read-only fleet attention detector: modal-blocked vs finished-clean.

Reads one harness roster record (``~/.claude/sessions/<pid>.json``, harness-owned,
schema changes without notice) and returns an ``AttentionVerdict``. Never writes
the roster.

Verdict contract
-----------------
- ``blocked_on_modal`` / ``finished`` / ``running``: only on a positive,
  discriminating input (a roster ``status`` in the named value sets, or an engine
  discriminant supplied through ``engine_discriminant``).
- ``cannot_discriminate``: every other case, with ``missing_input`` naming what
  was absent. A roster ``status`` of ``idle`` is NOT evidence of anything: the
  harness reports ``idle`` for sessions driving live workflows and for sessions
  parked behind a modal, so ``idle`` never yields ``finished`` or ``running`` and
  never yields an "idle" verdict.

Engine seam: ``engine_discriminant`` is an optional callable
``(session_id) -> Optional[str]`` returning one of ``ENGINE_VALUES`` or None
("the engine did not say"). Its shape is deliberately unfixed beyond that until
the ledger contract lands; a None result falls through to the roster path.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

BLOCKED_ON_MODAL = "blocked_on_modal"
FINISHED = "finished"
RUNNING = "running"
CANNOT_DISCRIMINATE = "cannot_discriminate"

VERDICTS = (BLOCKED_ON_MODAL, FINISHED, RUNNING, CANNOT_DISCRIMINATE)

# Roster `status` values that carry a positive meaning. `idle` is absent on purpose.
_ROSTER_BLOCKED = frozenset({"requires_action", "blocked", "waiting_for_input", "awaiting_input"})
_ROSTER_FINISHED = frozenset({"finished", "completed", "done"})
_ROSTER_RUNNING = frozenset({"running", "busy"})

ENGINE_VALUES = frozenset({BLOCKED_ON_MODAL, FINISHED, RUNNING})


@dataclass(frozen=True)
class AttentionVerdict:
    verdict: str
    source: str
    missing_input: Optional[str] = None
    detail: str = ""


def _cannot(missing: str, detail: str = "") -> AttentionVerdict:
    return AttentionVerdict(CANNOT_DISCRIMINATE, "none", missing, detail)


def classify(
    record: Optional[Mapping[str, Any]],
    engine_discriminant: Optional[Callable[[str], Optional[str]]] = None,
) -> AttentionVerdict:
    """Classify one roster record. Tolerates a missing/malformed record or `status`."""
    if not isinstance(record, Mapping):
        return _cannot("roster record", "record absent or not an object")

    session_id = record.get("sessionId")
    if engine_discriminant is not None and isinstance(session_id, str):
        try:
            engine = engine_discriminant(session_id)
        except Exception as exc:  # the seam is foreign code; degrade, never raise
            engine = None
            engine_note = f"engine discriminant raised {type(exc).__name__}"
        else:
            engine_note = ""
        if engine in ENGINE_VALUES:
            return AttentionVerdict(engine, "engine")
    else:
        engine_note = ""

    status = record.get("status")
    if not isinstance(status, str) or not status:
        return _cannot("roster status field", engine_note or "roster record carries no `status`")

    s = status.strip().lower()
    if s in _ROSTER_BLOCKED:
        return AttentionVerdict(BLOCKED_ON_MODAL, "roster", detail=f"status={s}")
    if s in _ROSTER_FINISHED:
        return AttentionVerdict(FINISHED, "roster", detail=f"status={s}")
    if s in _ROSTER_RUNNING:
        return AttentionVerdict(RUNNING, "roster", detail=f"status={s}")
    if s == "idle":
        return _cannot(
            "blocked-vs-idle discriminator",
            "roster `idle` does not separate modal-blocked from finished or running",
        )
    return _cannot("recognised roster status value", f"unrecognised status={s!r}")


def read_record(path: Path) -> Optional[dict]:
    """Read one roster file defensively; None on any read/parse failure."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def classify_path(
    path: Path,
    engine_discriminant: Optional[Callable[[str], Optional[str]]] = None,
) -> AttentionVerdict:
    return classify(read_record(path), engine_discriminant)


def roster_dir() -> Path:
    return Path(os.environ.get("CLAUDE_HOME") or Path.home() / ".claude") / "sessions"
