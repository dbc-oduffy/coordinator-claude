"""box-launch-windowless.py -- start a background job that never opens a console window.

Usage: box-launch-windowless.py [--log PATH] [--cwd DIR] -- CMD...

Prints `LAUNCHED pid=N log=PATH` and exits 0 without waiting. Exit codes: 0 launched,
1 launch failed (one stderr line), 2 usage. Runs on every host.

The spawn is lib/session_detach.py spawn_detached(strict=False), the single home of the flag set,
the pythonw swap and the breakaway retry: when the parent's job forbids breakaway the launch is
retried once without it, and a second OSError is the exit-1 failure. Never point
multiprocessing.set_executable at pythonw.

Stdlib only; no coordinator_core import.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import time
from pathlib import Path

_USAGE = "usage: box-launch-windowless.py [--log PATH] [--cwd DIR] -- CMD..."


def _git_toplevel(start: Path) -> Path | None:
    """Nearest ancestor of `start` (inclusive) holding a `.git`; no git spawn."""
    cur = start.resolve()
    for cand in (cur, *cur.parents):
        if (cand / ".git").exists():
            return cand
    return None


def _settings_home() -> Path:
    env = os.environ.get("COORDINATOR_SETTINGS_HOME")
    if env:
        return Path(env)
    base = os.environ.get("CLAUDE_HOME") or str(Path.home())
    return Path(base) / ".coordinator-claude-settings"


def default_log_path(cmd0: str, cwd: Path, now: float | None = None) -> Path:
    """scratch/ of cwd's git toplevel, else of the settings home. Never /tmp or a drive root."""
    top = _git_toplevel(cwd)
    root = top if top is not None else _settings_home()
    stamp = time.strftime("%Y%m%dT%H%M%S", time.localtime(now))
    name = Path(cmd0).stem or "job"
    return root / "scratch" / f"launch-{name}-{stamp}-{os.getpid()}.log"


def _session_detach():
    """lib/session_detach.py, loaded by path once."""
    mod = sys.modules.get("session_detach")
    if mod is not None:
        return mod
    path = Path(__file__).resolve().parent / "lib" / "session_detach.py"
    spec = importlib.util.spec_from_file_location("session_detach", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load session_detach from {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    try:
        spec.loader.exec_module(mod)
    except BaseException:
        sys.modules.pop(spec.name, None)
        raise
    return mod


def _parse(argv: list[str]) -> tuple[str | None, str | None, list[str]] | None:
    if "--" not in argv:
        return None
    sep = argv.index("--")
    opts, cmd = argv[:sep], argv[sep + 1 :]
    if not cmd:
        return None
    log = cwd = None
    i = 0
    while i < len(opts):
        flag = opts[i]
        if flag in ("--log", "--cwd") and i + 1 < len(opts):
            if flag == "--log":
                log = opts[i + 1]
            else:
                cwd = opts[i + 1]
            i += 2
        else:
            return None
    return log, cwd, cmd


def main(argv: list[str] | None = None, *, popen=None, platform: str | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if any(a in ("-h", "--help") for a in argv[: argv.index("--") if "--" in argv else None]):
        print(_USAGE)
        return 0
    parsed = _parse(argv)
    if parsed is None:
        print(_USAGE, file=sys.stderr)
        return 2
    log_arg, cwd_arg, cmd = parsed
    cwd = Path(cwd_arg) if cwd_arg else Path.cwd()
    log = Path(log_arg) if log_arg else default_log_path(cmd[0], cwd)
    try:
        pid = _session_detach().spawn_detached(
            cmd, log, cwd=cwd_arg, strict=False, popen=popen, platform=platform
        )
    except OSError as exc:
        print(f"box-launch-windowless: launch failed: {exc}", file=sys.stderr)
        return 1
    print(f"LAUNCHED pid={pid} log={log}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
