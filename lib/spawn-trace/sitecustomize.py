"""sitecustomize.py — transitive spawn tracer for the POSIX/Windows spawn-economics baton.

Spec backlink: state/handoffs/2026-08-14-windows-spawn-economics.md
(deliverable_id: dlv-spawn-per-call-economics-on-windows-ba9646).

WHAT THIS DOES
    Auto-imported by CPython whenever this file's directory sits on
    PYTHONPATH (the interpreter's own site-init convention, no code here
    triggers it). Installs a `sys.addaudithook` that records every
    subprocess.Popen / os.exec* / os.posix_spawn / os.system event this
    interpreter raises, appending one JSONL row per event to the file named
    by the SPAWN_TRACE_LOG env var. Because PYTHONPATH is inherited by every
    descendant Python process (unless a child scrubs its env), a chain of
    coordinator ops each get their own copy of this hook and all append to
    the SAME log, so the log reconstructs the full transitive spawn tree of
    one top-level invocation, not just its immediate children.

WHAT THIS CANNOT SEE
    A process spawned by a NON-Python parent is invisible to this hook —
    notably the first hop of a Windows `.cmd` launcher (cmd.exe launching
    python.exe): cmd.exe never runs this interpreter, so it never raises a
    Python audit event. That hop must be accounted for analytically (by
    reading the launcher body), not read off this log. Likewise any
    subprocess.Popen call made from C extension code that bypasses the
    audited Python-level APIs, though none of the ops this baton measures do.

SPEC
    Silent by design: never prints, never raises past a `try` (a broken trace
    hook must not break the op it is instrumenting). SPAWN_TRACE_LOG unset ->
    no-op (importable outside a trace run with zero behavior change).
"""
from __future__ import annotations

import json
import os
import sys
import time

_LOG_PATH = os.environ.get("SPAWN_TRACE_LOG")

_TRACKED_EVENTS = frozenset(
    {"subprocess.Popen", "os.exec", "os.posix_spawn", "os.system"}
)


def _argv_from_event(event: str, args: tuple) -> list[str]:
    if event == "subprocess.Popen":
        _executable, popen_args, _cwd, _env = args
        if isinstance(popen_args, (list, tuple)):
            return [str(a) for a in popen_args]
        return [str(popen_args)]
    if event == "os.exec":
        _path, exec_args, _env = args
        return [str(a) for a in exec_args]
    if event == "os.posix_spawn":
        _path, argv, _env = args
        return [str(a) for a in argv]
    if event == "os.system":
        return [str(args[0])]
    return []


def _record(event: str, args: tuple) -> None:
    if _LOG_PATH is None or event not in _TRACKED_EVENTS:
        return
    try:
        argv = _argv_from_event(event, args)
        row = {
            "event": event,
            "pid": os.getpid(),
            "ppid": os.getppid(),
            "argv0": argv[0] if argv else None,
            "argv": argv,
            "monotonic": time.monotonic(),
            "recorder_argv": sys.argv,
        }
        with open(_LOG_PATH, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(row) + "\n")
    except Exception:
        return


if _LOG_PATH is not None:
    sys.addaudithook(_record)
