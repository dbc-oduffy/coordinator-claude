"""box-launch-windowless.py -- start a background job that never opens a console window.

Usage: box-launch-windowless.py [--log PATH] [--cwd DIR] -- CMD...

Prints `LAUNCHED pid=N log=PATH` and exits 0 without waiting. Exit codes: 0 launched,
1 launch failed (one stderr line), 2 usage. Runs on every host.

Windows: the child gets CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB,
never DETACHED_PROCESS (a detached child gets a fresh console the moment it spawns a console
grandchild). Breakaway is best-effort: when the parent's job forbids it Popen raises OSError and
the launch is retried once without breakaway; a second OSError is the exit-1 failure. A
pythonw.exe CMD[0] is swapped for the sibling python.exe for the same reason. Never point
multiprocessing.set_executable at pythonw. POSIX: start_new_session=True.

Stdlib only; no coordinator_core import.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

_NO_CONSOLE_WINDOW = 0x08000000
_CREATE_NEW_PROCESS_GROUP = 0x00000200
_CREATE_BREAKAWAY_FROM_JOB = 0x01000000

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


def _swap_pythonw(cmd: list[str]) -> list[str]:
    head = Path(cmd[0])
    if head.name.lower() == "pythonw.exe":
        sibling = head.with_name("python.exe")
        return [str(sibling), *cmd[1:]]
    return cmd


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
    plat = sys.platform if platform is None else platform
    import subprocess

    if popen is None:
        popen = subprocess.Popen

    cwd = Path(cwd_arg) if cwd_arg else Path.cwd()
    log = Path(log_arg) if log_arg else default_log_path(cmd[0], cwd)
    kwargs: dict = {}
    if plat == "win32":
        cmd = _swap_pythonw(cmd)
        base_flags = _NO_CONSOLE_WINDOW | _CREATE_NEW_PROCESS_GROUP
        kwargs["creationflags"] = base_flags | _CREATE_BREAKAWAY_FROM_JOB
    else:
        base_flags = 0
        kwargs["start_new_session"] = True
    if cwd_arg:
        kwargs["cwd"] = str(cwd)
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, "ab") as sink:
            def spawn():
                return popen(
                    cmd,
                    stdin=subprocess.DEVNULL,
                    stdout=sink,
                    stderr=sink,
                    close_fds=True,
                    **kwargs,
                )

            try:
                proc = spawn()
            except OSError:
                if plat != "win32":
                    raise
                kwargs["creationflags"] = base_flags
                proc = spawn()
    except OSError as exc:
        print(f"box-launch-windowless: launch failed: {exc}", file=sys.stderr)
        return 1
    print(f"LAUNCHED pid={proc.pid} log={log}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
