"""SessionStart hook — write-confinement bump's session-start anchor record.

Purpose: the write-confinement speed bump
(docs/plans/2026-08-02-write-confinement-guards.md, chunk C0/C8) needs a
launch-cwd anchor recorded ONCE at SessionStart, keyed on session id, that
survives an ordinary `cd` moving the live payload cwd later in the session
(the Director of Engineering F1). The write/read logic lives on the engine plane, in
`coordinator_core.bash_guards._write_bump_session_start` — that module's own
docstring, "Install-surface note (2026-08-03, C0 dispatch)", names exactly
this file as the missing wiring: chunk C0 correctly refused to invent a
registration list in the engine's own installer (that generator is purely
data-driven off THIS file, `coordinator/hooks/hooks.json` — it has no
per-hook list of its own to edit), so the real fresh-install wiring is a
`hooks.json` SessionStart entry plus this thin doctrine-plane-resident shim.

The doctrine plane owns only this thin PLUMBING shim (DR-047 transport-seam carve-out):
resolve the engine root, extract `session_id`/`cwd` from the raw
SessionStart payload, call `write_session_start_record()` directly, in
process. Deliberately NOT routed through `coordinator_core.hooks` /
`coordinator_core.ipc.dispatch_message` (unlike track-dispatched-agents.py) —
`_write_bump_session_start.py`'s own "Negative-spec" section says not to: that
package eagerly imports 13 hook modules for their `register_op()` side
effects on every call, machinery this plain read/write pair does not need.
Mirrors `preuse-bash-dispatch.py`'s "import the engine module directly, call
its function, never go through the ops/ipc package" shape instead.

Contract:
  stdin   — SessionStart JSON payload (session_id, cwd, source, ...)
  stdout  — NOTHING (this hook has no context to inject; its only product is
            the on-disk anchor-record side effect)
  exit 0  — ALWAYS. FAIL OPEN at every step: a SessionStart hook that errors
            is far worse than one that silently does nothing — it would
            greet every session in the fleet with a stack trace. Every
            failure mode (unparsable stdin, absent session_id, unresolvable
            engine root, an unimportable engine module, a write failure
            inside `write_session_start_record` itself) degrades to a
            silent no-op, never an exception, never non-zero.

Matcher (see hooks.json registration): `startup|resume|clear|compact|fork` —
every SessionStart source the harness emits, not just cold start. Mirrors
`assert-em-role.py`'s reasoning for the same exhaustive matcher: an omitted
source means the anchor simply is never recorded for sessions that begin
there, and `write_session_start_record()` is idempotent by design (a repeat
fire for the same `session_id` overwrites the same file with the same
content, harmless by construction) — so firing on every source is free.

Spec backlink: docs/plans/2026-08-02-write-confinement-guards.md, chunk C8
("Install-surface completeness and marker hygiene", Part 2 — "the install
wiring the plan misplaced").
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path


def _read_stdin(timeout: float = 2.0) -> str:
    """Bounded stdin read (Windows hang guard) — same pattern as the other
    hooks in this directory (e.g. track-dispatched-agents.py._read_stdin)."""
    box = {"data": ""}

    def _read() -> None:
        try:
            box["data"] = sys.stdin.read()
        except Exception:
            box["data"] = ""

    t = threading.Thread(target=_read, daemon=True)
    t.start()
    t.join(timeout)
    return box["data"]


_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)
try:
    from _engine_root import resolve_claude_klabauter_root as _resolve_claude_klabauter_root  # noqa: E402
except Exception:
    # Defensive fallback — a hook script copied/deployed WITHOUT its sibling
    # _engine_root.py (e.g. an isolated test harness, or a partial deploy)
    # must still fail-open rather than crash on import.
    def _resolve_claude_klabauter_root() -> str | None:
        return None


def main() -> int:
    raw = _read_stdin()

    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}

    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return 0  # fail-open — no session id to key the anchor record on

    cwd = payload.get("cwd")
    launch_cwd = cwd if isinstance(cwd, str) and cwd else None

    root = _resolve_claude_klabauter_root()
    if not root:
        return 0  # fail-open — engine root unresolvable on this machine

    if root not in sys.path:
        sys.path.insert(0, root)

    try:
        from coordinator_core.bash_guards._write_bump_session_start import (
            write_session_start_record,
        )
    except Exception:
        return 0  # engine unimportable → fail-open

    try:
        write_session_start_record(session_id, launch_cwd=launch_cwd)
    except Exception:
        # write_session_start_record already fails open internally (returns
        # False rather than raising — see its own docstring's "FAIL OPEN"),
        # but this call site swallows unconditionally too: a SessionStart
        # hook erroring is worse than one that silently no-ops.
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
