"""_turn_intent -- stdlib-only, zero-spawn contract for the EM turn-intent Stop step.

An EM under Cockpit ends every turn with `<turn-intent>{"needs_pm":bool,"ask":"..."}</turn-intent>`.
The Stop hook parses it and writes `<git-common-dir>/coordinator-sessions/<session_id>/turn-intent.json`
(schema 1) for Cockpit. A missing tail is blocked at most BLOCK_CAP times, counted here and
never via `stop_hook_active`, and only when the caller passes `role_marker` true
(the marker is present AND `_cockpit_session.under_cockpit()` holds); after that the
record is labelled `source: heuristic`. The heuristic record is written either way.

Negative specs: the heuristic only labels, it never blocks. `decide` is pure. Nothing here
spawns a process, and nothing is written for a session_id that is not a real uuid4.
"""

from __future__ import annotations

import json
import os
import re
from typing import Callable, NamedTuple, Optional, Tuple

try:
    from _session_hub import ensure_session_dir
except ImportError:  # pragma: no cover - loaded by path
    import importlib.util as _ilu

    _spec = _ilu.spec_from_file_location(
        "_session_hub", os.path.join(os.path.dirname(os.path.abspath(__file__)), "_session_hub.py")
    )
    _mod = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    ensure_session_dir = _mod.ensure_session_dir

SCHEMA = 1
RECORD_NAME = "turn-intent.json"
COUNTER_NAME = "turn-intent-blocks.json"
ROLE_MARKER_NAME = "em-role-asserted"
BLOCK_CAP = 2
ASK_MAX = 200
BLOCK_REASON = (
    'End your reply with <turn-intent>{"needs_pm":<bool>,"ask":"<the one decision you need, '
    'else empty>"}</turn-intent> as the last line.'
)

_OPEN = "<turn-intent>"
_CLOSE = "</turn-intent>"
_HUB = "coordinator-sessions"


class Marker(NamedTuple):
    needs_pm: Optional[bool]
    ask: str
    source: str


class Decision(NamedTuple):
    block: bool
    record: Optional[Tuple[bool, str, str]]


def _tail_span(text: str) -> Optional[Tuple[int, int]]:
    body = text.rstrip()
    if not body.endswith(_CLOSE):
        return None
    start = body.rfind(_OPEN)
    if start == -1:
        return None
    return start, len(body)


def parse_marker(text: str) -> Optional[Marker]:
    if not isinstance(text, str):
        return None
    span = _tail_span(text)
    if span is None:
        return None
    raw = text.rstrip()[span[0] + len(_OPEN): span[1] - len(_CLOSE)]
    try:
        data = json.loads(raw)
    except ValueError:
        return Marker(None, "", "marker-malformed")
    if not isinstance(data, dict) or not isinstance(data.get("needs_pm"), bool):
        return Marker(None, "", "marker-malformed")
    ask = data.get("ask", "")
    if not isinstance(ask, str):
        return Marker(None, "", "marker-malformed")
    return Marker(data["needs_pm"], ask[:ASK_MAX], "marker")


def strip_marker(text: str) -> str:
    span = _tail_span(text) if isinstance(text, str) else None
    if span is None:
        return text
    return text[: span[0]].rstrip()


def session_dir(git_common_dir: str, session_id: str) -> str:
    return os.path.join(git_common_dir, _HUB, session_id)


def role_marker_present(directory: str) -> bool:
    return os.path.isfile(os.path.join(directory, ROLE_MARKER_NAME))


def _atomic_write(directory: str, name: str, payload: str) -> bool:
    tmp = os.path.join(directory, f".{name}.{os.getpid()}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(payload)
        os.replace(tmp, os.path.join(directory, name))
        return True
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False


def write_role_marker(directory: str, session_id: str) -> bool:
    if not ensure_session_dir(directory, session_id):
        return False
    return _atomic_write(directory, ROLE_MARKER_NAME, session_id)


def read_blocks(directory: str) -> int:
    try:
        with open(os.path.join(directory, COUNTER_NAME), "r", encoding="utf-8") as fh:
            value = json.load(fh).get("blocks", 0)
        return value if isinstance(value, int) and value >= 0 else 0
    except (OSError, ValueError, AttributeError):
        return 0


def bump_blocks(directory: str) -> int:
    count = read_blocks(directory) + 1
    _atomic_write(directory, COUNTER_NAME, json.dumps({"blocks": count}))
    return count


def reset_blocks(directory: str) -> None:
    try:
        os.remove(os.path.join(directory, COUNTER_NAME))
    except OSError:
        pass


def write_record(
    directory: str,
    session_id: str,
    needs_pm: bool,
    ask: str,
    source: str,
    now: float,
) -> bool:
    if not ensure_session_dir(directory, session_id):
        return False
    record = {
        "schema": SCHEMA,
        "session_id": session_id,
        "needs_pm": bool(needs_pm),
        "ask": ask[:ASK_MAX],
        "source": source,
        "turn_ended_at": now,
    }
    if not _atomic_write(directory, RECORD_NAME, json.dumps(record)):
        return False
    reset_blocks(directory)
    return True


def decide(
    text: str,
    blocks_so_far: int,
    role_marker: bool,
    classify: Callable[[str], Tuple[bool, str]],
) -> Decision:
    marker = parse_marker(text)
    if marker is not None and marker.source == "marker":
        return Decision(False, (marker.needs_pm, marker.ask, "marker"))
    stripped = strip_marker(text)
    if marker is not None:
        needs_pm, ask = classify(stripped)
        return Decision(False, (needs_pm, ask, "marker-malformed"))
    if role_marker and blocks_so_far < BLOCK_CAP:
        return Decision(True, None)
    needs_pm, ask = classify(stripped)
    return Decision(False, (needs_pm, ask, "heuristic"))
