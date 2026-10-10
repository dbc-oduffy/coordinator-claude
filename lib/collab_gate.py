"""collab_gate — the read-only DoE-Python binding of the collaboration verdict file.

The frozen contract is the on-disk shape of `state/collaboration-verdict.json`
(`coordinator/docs/wiki/collaboration-gate-contract.md`); `read_verdict` is one binding of it.

INVARIANTS: `read_verdict` never raises, never spawns, never prompts. This module imports nothing
from `collab_detect` and nothing that imports `subprocess`; the no-spawn guarantee is an
import-graph property pinned by AST in `test_collab_gate_read_shape.py`. Keep module-scope imports
to the standard-library set below.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

VERDICT_RELPATH = "state/collaboration-verdict.json"

MODES = ("solo", "multi")
SOURCES = ("detected", "override", "unresolved", "corrupt")


@dataclass(frozen=True)
class Verdict:
    """The four-field collaboration verdict. `checked_at` is ISO-8601 UTC, or "" when no
    detection has run (`unresolved`) or the cache could not be read (`corrupt`)."""

    mode: str
    source: str
    author_count: int
    checked_at: str


def _fallback(source: str) -> Verdict:
    return Verdict(mode="solo", source=source, author_count=0, checked_at="")


def _parse(raw: object) -> Verdict | None:
    if not isinstance(raw, dict):
        return None
    mode = raw.get("mode")
    source = raw.get("source")
    count = raw.get("author_count")
    checked_at = raw.get("checked_at")
    if mode not in MODES or source not in ("detected", "override"):
        return None
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        return None
    if not isinstance(checked_at, str):
        return None
    return Verdict(mode=mode, source=source, author_count=count, checked_at=checked_at)


def read_verdict(repo_root: str | Path) -> Verdict:
    """Return the cached verdict for `repo_root`.

    Absent file -> solo/unresolved. Present but unreadable, unparseable, or off-schema ->
    solo/corrupt. A cache never carries `unresolved` or `corrupt` as a stored source; those two
    values are read-side states only.
    """
    try:
        path = Path(repo_root) / VERDICT_RELPATH
        if not path.exists():
            return _fallback("unresolved")
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _fallback("corrupt")
    parsed = _parse(raw)
    return parsed if parsed is not None else _fallback("corrupt")
