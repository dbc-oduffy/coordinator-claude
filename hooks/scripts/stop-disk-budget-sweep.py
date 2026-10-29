"""stop-disk-budget-sweep.py -- Stop producer: spawn the capped disk-budget sweep child mid-session.

A PRODUCER folded into `stop-dispatch.py` (no hooks.json entry of its own). It always exits 0 with
empty stdout. Stop fires only inside a running Claude Code session, so a long session is swept on
the same 6 h throttle as SessionStart and nothing runs while Claude Code is not running. When
`sweep_due`, it writes the `last-sweep.json` stamp (the shape the child writes) so concurrent Stops
do not double-spawn, then spawns `session-start-disk-budget.py --child --max-wall-s N` detached;
`sweep_lock` is the backstop. The child never re-arms itself.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_CHILD_SCRIPT = _HERE / "session-start-disk-budget.py"


def main() -> int:
    try:
        sys.stdin.read()
        if str(_HERE) not in sys.path:
            sys.path.insert(0, str(_HERE))
        from _engine_root import resolve_claude_klabauter_root

        engine = resolve_claude_klabauter_root()
        if not engine:
            return 0
        _LIB_DIR = Path(engine) / "coordinator" / "lib"
        if str(_LIB_DIR) not in sys.path:
            sys.path.insert(0, str(_LIB_DIR))
        from disk_budget import CHILD_MAX_WALL_S, Policy, resolve_roots, spawn_detached, sweep_due

        state = resolve_roots().state_dir
        wall = time.time()
        if not sweep_due(state, Policy.from_env(), wall):
            return 0
        state.mkdir(parents=True, exist_ok=True)
        stamp = state / "last-sweep.json"
        tmp = stamp.with_name(stamp.name + ".tmp")
        tmp.write_text(json.dumps({"ts": wall}), encoding="utf-8")
        os.replace(tmp, stamp)
        spawn_detached(
            [sys.executable, str(_CHILD_SCRIPT), "--child", "--max-wall-s", str(CHILD_MAX_WALL_S)]
        )
    except BaseException:  # noqa: BLE001 -- a producer never blocks a Stop
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
