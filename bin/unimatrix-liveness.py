#!/usr/bin/env python3
"""Spawn-free liveness for the unimatrix autolink supervisors: stdlib only, no subprocess.

Thin CLI wrapper + re-export facade over `_unimatrix.proc` and `_unimatrix.paths`.
"""
import importlib
import os
import sys
from pathlib import Path

_CORE = None
_PATHS = None
_PATH_NAMES = ("settings_home", "state_dir")


def _ensure_pkg():
    bin_dir = os.path.dirname(os.path.abspath(__file__))
    if "_unimatrix" not in sys.modules and bin_dir not in sys.path:
        sys.path.insert(0, bin_dir)


def _proc():
    global _CORE
    if _CORE is None:
        _ensure_pkg()
        _CORE = importlib.import_module("_unimatrix.proc")
    return _CORE


def _paths():
    global _PATHS
    if _PATHS is None:
        _ensure_pkg()
        _PATHS = importlib.import_module("_unimatrix.paths")
    return _PATHS


def __getattr__(name):
    if name in _PATH_NAMES:
        return getattr(_paths(), name)
    return getattr(_proc(), name)


def _get(mod_fn, name):
    return globals()[name] if name in globals() else getattr(mod_fn(), name)


def holder_proven_dead(d) -> bool:
    """The one corpse-row definition (`_unimatrix.proc`), resolved against this module's patchable seams."""
    return _proc().holder_proven_dead(d, _get(_proc, "pid_alive"), _get(_proc, "proc_start"))


def entry_live(d) -> bool:
    return not holder_proven_dead(d)


def codex_holder_live(row):
    """Liveness of the Codex process a peer row recorded as `codexPid`/`codexProcStart`."""
    pid = row.get("codexPid") if isinstance(row, dict) else None
    if not isinstance(pid, int) or isinstance(pid, bool):
        return None
    if entry_live({"pid": pid, "procStart": row.get("codexProcStart")}):
        return True
    target = row.get("target")
    if row.get("vendor") != "codex" or not isinstance(target, str):
        return False
    code_home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    return _get(_proc, "agy_presence_held")(target, presence_dir=code_home / "thread-writer-locks")


def supervisor_live(rec) -> bool:
    """True when the recorded pid is alive and is the same process that was started."""
    pid = rec.get("pid") if isinstance(rec, dict) else None
    if not isinstance(pid, int) or isinstance(pid, bool) or not _get(_proc, "pid_alive")(pid):
        return False
    try:
        return _get(_proc, "proc_start")(pid) == rec.get("procStart")
    except OSError:
        return False


def entry_live(d) -> bool:
    """True when the entry's pid is alive and, if it records a procStart, is still that process."""
    pid = d.get("pid") if isinstance(d, dict) else None
    if not isinstance(pid, int) or isinstance(pid, bool) or not _get(_proc, "pid_alive")(pid):
        return False
    recorded = d.get("procStart")
    if not isinstance(recorded, str) or not recorded:
        return True
    try:
        return _get(_proc, "proc_start")(pid) == recorded
    except OSError:
        return True


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("park", "release"):
        return _park_cmd(args[0], args[1:])
    if not args or args[0] != "codex-probe":
        print(_USAGE, file=sys.stderr)
        return 2
    opts = {"--peers": _get(_paths, "state_dir")() / "peers.json", "--locks-dir": _get(_proc, "codex_locks_dir")()}
    rest = args[1:]
    while rest:
        if rest[0] not in opts or len(rest) < 2:
            print(f"unimatrix-liveness.py codex-probe: bad argument {rest[0]!r}", file=sys.stderr)
            return 2
        opts[rest[0]] = Path(rest[1])
        rest = rest[2:]
    for line in _get(_proc, "codex_probe_lines")(opts["--peers"], opts["--locks-dir"]):
        print(line)
    return 0


_USAGE = ("usage: unimatrix-liveness.py codex-probe [--peers FILE] [--locks-dir DIR]\n"
          "       unimatrix-liveness.py park ALIAS [--reason TEXT]   hold ALIAS out of autolink until released\n"
          "       unimatrix-liveness.py release ALIAS               end the park (backoff record is kept)")


def _park_cmd(verb, rest) -> int:
    reason = None
    if verb == "park" and len(rest) == 3 and rest[1] == "--reason":
        reason = rest[2]
    elif len(rest) != 1:
        print(_USAGE, file=sys.stderr)
        return 2
    alias = rest[0]
    sdir = _get(_paths, "state_dir")()
    if verb == "park":
        _get(_proc, "park")(sdir, alias, reason)
        print(f"parked {alias}: autolink skips it until `release {alias}`")
        return 0
    if _get(_proc, "release")(sdir, alias):
        print(f"released {alias}")
        return 0
    print(f"{alias} is not parked", file=sys.stderr)
    return 1


if __name__ == "__main__":
    if any(_a in ("-h", "--help") for _a in sys.argv[1:]):
        print(_USAGE + "\nunimatrix peer liveness probe")
        raise SystemExit(0)
    sys.exit(main())
