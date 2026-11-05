"""idle-compact-watcher — type /compact into idle, allowlisted EM sessions that fired engine asks.

Default invocation detaches itself from the Claude Code session (outside its process tree and job)
and loops every 30 s, appending to `--log` (default `<settings home>/state/idle-compact/watcher.log`).
`--once` runs one tick in the foreground and prints one line per logged decision. Never run it under
a `Monitor`. Decisions land in the injection log (`injections.jsonl`) under this process's run id.

NEGATIVE SPEC: never denies or blocks; never shells out; injects only into sessions that fired an
engine ask, are idle 300 s, read over 18 % context, and are allowlisted and not opted out or held.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Optional


def _place_engine_on_path() -> Optional[str]:
    lib = str(Path(__file__).resolve().parent / "lib")
    if lib not in sys.path:
        sys.path.insert(0, lib)
    import cc_invoke  # type: ignore

    root = cc_invoke.ensure_engine_on_path(__file__)
    if root:
        # The Windows injector child runs `python -m coordinator_core...` and inherits this.
        os.environ["PYTHONPATH"] = os.pathsep.join(
            [str(root), *([os.environ["PYTHONPATH"]] if os.environ.get("PYTHONPATH") else [])]
        )
    return root


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n", 1)[0])
    ap.add_argument("--once", action="store_true", help="run one tick in the foreground and exit")
    ap.add_argument("--log", type=Path, default=None, help="log the detached watcher appends to")
    args = ap.parse_args(argv)
    if _place_engine_on_path() is None:
        print("idle-compact-watcher: engine root unresolvable", file=sys.stderr)
        return 2
    from coordinator_core.idle_compact import watcher

    if args.once:
        for rec in watcher.run_once():
            print(f"{rec.action} sid={rec.session_id} pid={rec.pid} reason={rec.reason} run_id={rec.run_id}")
        return 0

    import session_detach  # type: ignore

    log = args.log or watcher.default_watcher_log()
    child_argv = list(sys.argv[1:] if argv is None else argv)
    if "--log" not in child_argv:
        child_argv += ["--log", str(log)]
    rc = session_detach.ensure_detached("idle-compact-watcher", child_argv, log)
    if rc is not None:
        return rc
    log.parent.mkdir(parents=True, exist_ok=True)
    sys.stdout = sys.stderr = open(log, "a", encoding="utf-8", buffering=1)
    watcher.loop(watcher.new_run_id(), watcher.make_injector())
    return 0


if __name__ == "__main__":
    sys.exit(main())
