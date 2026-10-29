"""Move a long-lived box memory guard out of the Claude Code session's process tree and job.

Stdlib plus optional psutil (the `box_memory_host` contract); no `coordinator_core` import.
`session_parented` asks whether a Claude Code process is an ancestor, `spawn_detached` starts a
command outside the session's tree and job, `ensure_detached` relaunches a guard through it or
refuses with exit `CANNOT_DETACH_EXIT`.

Windows children get CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB,
never DETACHED_PROCESS (a detached child gets a fresh console the moment it spawns a console
grandchild). POSIX children get start_new_session=True.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

DETACHED_ENV = "COORDINATOR_GUARD_DETACHED"
FAKE_SESSION_ENV = "COORDINATOR_GUARD_FAKE_SESSION"

_NO_CONSOLE_WINDOW = 0x08000000
_CREATE_NEW_PROCESS_GROUP = 0x00000200
_CREATE_BREAKAWAY_FROM_JOB = 0x01000000
_CLAUDE_IMAGES = frozenset({"claude", "claude.exe"})
_NODE_IMAGES = frozenset({"node", "node.exe"})
_MAX_DEPTH = 64


def _sibling(name):
    """A sibling module of this file, loaded by path once."""
    mod = sys.modules.get(name)
    if mod is not None:
        return mod
    path = Path(__file__).resolve().with_name(f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {name} from {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    try:
        spec.loader.exec_module(mod)
    except BaseException:
        sys.modules.pop(spec.name, None)
        raise
    return mod


def _interp():
    return _sibling("python_interp")


def _host():
    return _sibling("box_memory_host")


def _is_claude(image: str, cmdline) -> bool:
    name = Path(image.replace("\\", "/")).name.lower()
    if name in _CLAUDE_IMAGES:
        return True
    return name in _NODE_IMAGES and "claude" in cmdline().lower()


def _win_ancestors_hit(rows, pid: int, cmdline) -> bool:
    by_pid = {r.pid: r for r in rows}
    cur = by_pid.get(pid)
    seen = {pid}
    for _ in range(_MAX_DEPTH):
        if cur is None:
            return False
        parent = by_pid.get(cur.ppid)
        if parent is None or parent.pid in seen or parent.pid <= 4:
            return False
        # A reused pid is a younger process than its supposed child.
        if parent.create_time and cur.create_time and parent.create_time > cur.create_time:
            return False
        if _is_claude(parent.image, lambda p=parent.pid: cmdline(p)):
            return True
        seen.add(parent.pid)
        cur = parent
    return False


def _cmdline_of(pid: int, reader=None) -> str:
    try:
        return (reader or _host().proc_cmdline)(pid)
    except Exception:
        return ""


def session_parented(*, proc_table=None, platform=None, pid=None, cmdline=None) -> bool:
    """True when a Claude Code process (claude, or node running claude) is an ancestor.

    Windows walks the ppid chain over one process-table read; elsewhere psutil parents. Any read
    failure returns False: a guard runs inline rather than refuse on doubt.
    """
    if os.environ.get(FAKE_SESSION_ENV) == "1":
        return True
    plat = sys.platform if platform is None else platform
    me = os.getpid() if pid is None else pid
    try:
        if plat == "win32" or proc_table is not None:
            rows = (proc_table or _host().proc_table)()
            return _win_ancestors_hit(rows, me, lambda p: _cmdline_of(p, cmdline))
        import psutil

        for parent in psutil.Process(me).parents():
            if _is_claude(parent.name(), lambda p=parent: " ".join(p.cmdline())):
                return True
        return False
    except Exception:
        return False


def _swap_pythonw(cmd: list[str]) -> list[str]:
    head = Path(cmd[0])
    if head.name.lower() == "pythonw.exe":
        return [str(head.with_name("python.exe")), *cmd[1:]]
    return cmd


def spawn_detached(cmd, log, *, cwd=None, strict, popen=None, platform=None, env=None):
    """Start `cmd` outside the session's tree and job; return its pid.

    stdin is DEVNULL; stdout and stderr append to `log`. `strict=True` returns None when the
    spawn fails (a child left inside a kill-on-close job dies with the session). `strict=False`
    retries once without breakaway on Windows; a second OSError, or any POSIX one, propagates.
    """
    import subprocess

    plat = sys.platform if platform is None else platform
    popen = subprocess.Popen if popen is None else popen
    cmd = list(cmd)
    kwargs: dict = {}
    if plat == "win32":
        cmd = _swap_pythonw(cmd)
        base_flags = _NO_CONSOLE_WINDOW | _CREATE_NEW_PROCESS_GROUP
        kwargs["creationflags"] = base_flags | _CREATE_BREAKAWAY_FROM_JOB
    else:
        base_flags = 0
        kwargs["start_new_session"] = True
    if cwd:
        kwargs["cwd"] = str(cwd)
    if env is not None:
        kwargs["env"] = env
    log = Path(log)
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        sink = open(log, "ab")
    except OSError:
        if strict:
            return None
        raise
    with sink:

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
            return spawn().pid
        except OSError:
            if strict:
                return None
            if plat != "win32":
                raise
            kwargs["creationflags"] = base_flags
            return spawn().pid


def _remedy(prog: str, plat: str, py: str, script: str, argv) -> str:
    args = " ".join(argv)
    if plat == "win32":
        launch = f"Start-Process -WindowStyle Hidden {py} {script} {args}"
    else:
        launch = f"setsid nohup {py} {script} {args} &"
    return f"{prog}: cannot leave the Claude Code session's job; launch it detached: {launch}".rstrip()


def ensure_detached(
    prog,
    argv,
    log,
    *,
    env=None,
    script=None,
    popen=None,
    platform=None,
    proc_table=None,
    out=None,
    err=None,
):
    """Return None to run inline, 0 after relaunching detached, or CANNOT_DETACH_EXIT.

    Inline when the marker is set or no Claude Code ancestor exists. Otherwise relaunch
    `[sys.executable, script, *argv]` with the marker, print `DETACHED <prog> pid=N log=PATH`,
    and return 0; the caller must exit promptly. A failed strict spawn prints one remedy line.
    """
    env = dict(os.environ if env is None else env)
    if env.get(DETACHED_ENV):
        return None
    plat = sys.platform if platform is None else platform
    if not session_parented(proc_table=proc_table, platform=plat):
        return None
    script = str(Path(sys.argv[0] if script is None else script).resolve())
    argv = list(argv)
    child_env = {**env, DETACHED_ENV: "1"}
    py = _interp().resolve_console_python() or sys.executable
    pid = spawn_detached(
        [py, script, *argv],
        log,
        strict=True,
        popen=popen,
        platform=plat,
        env=child_env,
    )
    if pid is None:
        print(_remedy(prog, plat, py, script, argv), file=err or sys.stderr)
        return _host().CANNOT_DETACH_EXIT
    print(f"DETACHED {prog} pid={pid} log={log}", file=out or sys.stdout)
    return 0
