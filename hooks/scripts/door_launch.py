"""Native-door launcher: runs the settings-home ``hook-run`` door with stdin mode ``hook``, no shell.

argv: ``[--quiet] [--pass-2] <hook-run args...>``. ``--quiet`` drops the door's stderr; ``--pass-2``
maps its exit 2 to 0 (an advisory door never blocks). A missing door is a loud exit 0 with nothing
on stdout -- fail OPEN, never exit 2, never a deny. Any other exit code propagates.
"""
import os
import subprocess
import sys
from pathlib import Path

_FLAGS = ("--quiet", "--pass-2")


def door_path() -> Path:
    """The door binary under the settings home: ``hook-run.exe`` on Windows, ``hook-run`` elsewhere."""
    home = os.environ.get("COORDINATOR_SETTINGS_HOME") or str(Path.home() / ".coordinator-claude-settings")
    return Path(home) / "bin" / ("hook-run.exe" if os.name == "nt" else "hook-run")


def _fd(stream) -> int:
    """The stream's OS handle, passed explicitly: a CREATE_NO_WINDOW child that is handed no
    std handles gets a fresh console's, not this process's pipes."""
    try:
        return stream.fileno()
    except (AttributeError, OSError, ValueError):
        return subprocess.DEVNULL


def main(argv: list[str]) -> int:
    """Run the door for ``argv``; returns the process exit code (see module docstring)."""
    quiet = pass_2 = False
    rest = list(argv)
    while rest and rest[0] in _FLAGS:
        flag = rest.pop(0)
        quiet = quiet or flag == "--quiet"
        pass_2 = pass_2 or flag == "--pass-2"
    door = door_path()
    if not door.is_file():
        sys.stderr.write("COORDINATOR DOOR: hook-run missing, fails OPEN: %s\n" % door)
        return 0
    try:
        res = subprocess.run(
            [str(door), *rest],
            env=dict(os.environ, COORDINATOR_DOOR_STDIN_MODE="hook"),
            stdin=_fd(sys.stdin),
            stdout=_fd(sys.stdout),
            stderr=subprocess.DEVNULL if quiet else _fd(sys.stderr),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as exc:
        sys.stderr.write("COORDINATOR DOOR: hook-run not runnable, fails OPEN: %s (%s)\n" % (door, exc))
        return 0
    return 0 if pass_2 and res.returncode == 2 else res.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
