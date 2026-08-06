#!/usr/bin/env python3
"""spawn-hidden.sh — Windows-console-window-suppressing launcher for coordinator scripts.

Spec backlink: docs/plans/2026-05-29-windows-console-flash-elimination.md § Chunk 1
Port backlink: docs/plans/2026-07-22-debash-windows-process-family.md

PURPOSE
-------
On Windows, spawning a native console-subsystem .exe (python.exe, node.exe,
powershell.exe) from a console-less or foreign-console parent causes Windows
to allocate a fresh conhost.exe window for the child, producing a visible
flash.

DE-BASH SIMPLIFICATION — READ THIS BEFORE WIRING NEW CALL SITES
-----------------------------------------------------------------
The prior bash implementation could not set the Win32 CREATE_NO_WINDOW
(dwCreationFlags=0x08000000) bit itself — that bit can only be set at the
CreateProcess() call made by the spawning parent, and bash has no primitive
for it. Its workaround was resolving a SUBSYSTEM:WINDOWS sibling binary
(pythonw.exe) for the python case only, with a documented "no shell-level
suppression" gap for node and powershell, and a hard split between
--stdin-mode=safe (pythonw usable) and --stdin-mode=pipe (pythonw UNSAFE —
a console-less SUBSYSTEM:WINDOWS process can receive an invalid stdin handle).

THIS process — being Python, not bash — IS the spawning parent making the
CreateProcess() call, so it sets CREATE_NO_WINDOW directly via
subprocess.run(creationflags=...). That is genuine suppression at the source,
uniformly for any interpreter (python, node, powershell, anything else), and
it does NOT break stdin: unlike pythonw, CREATE_NO_WINDOW keeps the child a
normal console-subsystem process with normal stdio handles — it only skips
the window allocation. The --stdin-mode flag and the whole pythonw-sibling
resolution dance (D2-36) that motivated it are therefore obsolete and have
been dropped, not re-implemented: --stdin-mode is still accepted for CLI
back-compat but is a no-op under this mechanism.

STDIO INHERITANCE MUST BE EXPLICIT, NOT DEFAULTED — READ BEFORE TOUCHING THE
subprocess.run() CALL BELOW
-----------------------------------------------------------------
CPython's own Popen._get_handles has a fast path: "if stdin is None and
stdout is None and stderr is None: return (-1, -1, -1, -1, -1, -1)" — and
_execute_child computes use_std_handles = (-1 not in (p2cread, c2pwrite,
errwrite)) and bInheritHandles = int(not close_fds). Leaving all three
streams at their default None therefore skips STARTF_USESTDHANDLES entirely
and (since close_fds defaults True) passes bInheritHandles=False to
CreateProcess: the child inherits NO handles at all. Combined with
CREATE_NO_WINDOW suppressing console allocation, the grandchild ends up with
no valid stdin, and a read on it blocks forever (deadlock observed and fixed
2026-07-28 in test_stdin_passes_through — POSIX is unaffected because that
branch uses os.execvp, never CreateProcess). Passing stdin/stdout/stderr
EXPLICITLY forces Popen down the real branch (msvcrt.get_osfhandle +
_make_inheritable), which sets STARTF_USESTDHANDLES and threads the explicit
per-handle handle_list — genuine, targeted inheritance instead of the
accidental no-inheritance fast path. Do not simplify this back to a bare
subprocess.run(cmd, creationflags=_NO_WINDOW) call.

`subprocess.run(stdin=None)` is defined identically to omitting the kwarg
entirely (see subprocess.Popen docs), so passing `sys.stdin` "explicitly"
does NOT actually escape the fast path above when `sys.stdin` (or
`sys.stdout`/`sys.stderr`) IS `None` at the point this runs — precisely the
pythonw / detached-console / console-less-parent case this launcher exists
to run under (Review: code-reviewer — a prior version passed sys.stdin/
sys.stdout/sys.stderr straight through unconditionally, silently regressing
into the exact deadlock this docstring describes fixing whenever the
launcher's own streams were None). The same applies to a stream that IS
non-None but has no usable OS-level fileno() (e.g. an IDE/test-harness
stdio substitute) — subprocess.run raises when it tries to inherit one of
those. `_resolve_stdio_stream()` below guards both cases, substituting
subprocess.DEVNULL whenever a stream is None or fileno()-less, so the
"explicit" call never degenerates back into the implicit all-None fast
path.

USAGE
-----
    lib/spawn-hidden.sh [--stdin-mode=safe|pipe] <interpreter> [args...]

    --stdin-mode is accepted-but-vestigial (kept for call-site back-compat;
    see DE-BASH SIMPLIFICATION above — both values behave identically here).

EXIT CODE
---------
    Propagates the child's exit code exactly. 127 if the interpreter cannot
    be found/launched. 1 on a usage error (no interpreter given).

STDIN / STDOUT / STDERR
------------------------
    Fully inherited from the launcher's own handles — the child gets exactly
    what the launcher got. No buffering, no redirection.

    Non-Windows: os.execvp replaces this process with the interpreter
    (matching the bash oracle's `exec` — no wrapper process survives).
"""
from __future__ import annotations

import os
import subprocess
import sys

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _on_windows() -> bool:
    return os.name == "nt"


def _resolve_stdio_stream(stream: object) -> object:
    """Return `stream` unchanged if it is safely passable to subprocess.run,
    else subprocess.DEVNULL.

    Two cases substitute DEVNULL: `stream is None` (subprocess.run(stdin=None)
    is defined identically to omitting the kwarg — passing None through would
    silently collapse back into CPython's all-None no-inheritance fast path,
    see STDIO INHERITANCE MUST BE EXPLICIT in the module docstring), and a
    stream with no usable OS-level fileno() (subprocess.run raises trying to
    inherit one of those). Both conditions are exactly the pythonw / detached
    / console-less-parent conditions this launcher exists to run under."""
    if stream is None:
        return subprocess.DEVNULL
    fileno = getattr(stream, "fileno", None)
    if fileno is None:
        return subprocess.DEVNULL
    try:
        fd = fileno()
    except Exception:
        return subprocess.DEVNULL
    if fd is None or fd < 0:
        return subprocess.DEVNULL
    return stream


def _parse_args(argv: list[str]) -> tuple[str, list[str]] | None:
    """Consume an optional --stdin-mode=safe|pipe flag and '--' separator.

    Returns (interpreter, args) or None on a usage error (message already
    printed to stderr).
    """
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("--stdin-mode=safe", "--stdin-mode=pipe"):
            i += 1
            continue
        if arg.startswith("--stdin-mode="):
            print(f"spawn-hidden.sh: unknown --stdin-mode value: {arg}", file=sys.stderr)
            return None
        if arg == "--":
            i += 1
            break
        break

    if i >= len(argv):
        print("spawn-hidden.sh: no interpreter specified", file=sys.stderr)
        print(
            "Usage: spawn-hidden.sh [--stdin-mode=safe|pipe] <interpreter> [args...]",
            file=sys.stderr,
        )
        return None

    return argv[i], argv[i + 1 :]


def main(argv: list[str]) -> int:
    parsed = _parse_args(argv)
    if parsed is None:
        return 1
    interpreter, args = parsed
    cmd = [interpreter, *args]

    if not _on_windows():
        # Non-Windows: no console allocation occurs. exec replaces this
        # process outright — transparent pass-through, no wrapper survives.
        try:
            os.execvp(interpreter, cmd)
        except OSError as exc:
            print(f"spawn-hidden.sh: {exc}", file=sys.stderr)
            return 127
        return 127  # unreachable: execvp only returns via exception

    # Windows: this process IS the CreateProcess parent, so CREATE_NO_WINDOW
    # suppresses the console window directly — uniformly for python/node/
    # powershell/anything else, with normal stdio inheritance in both stdin
    # modes (see DE-BASH SIMPLIFICATION in the module docstring). stdin/
    # stdout/stderr are passed EXPLICITLY (not left as the None default) —
    # see STDIO INHERITANCE MUST BE EXPLICIT, NOT DEFAULTED above: leaving
    # all three at None trips a CPython fast path that skips
    # STARTF_USESTDHANDLES and inherits no handles at all, deadlocking a
    # child that reads stdin.
    try:
        result = subprocess.run(
            cmd,
            creationflags=_NO_WINDOW,
            stdin=_resolve_stdio_stream(sys.stdin),
            stdout=_resolve_stdio_stream(sys.stdout),
            stderr=_resolve_stdio_stream(sys.stderr),
        )
        return result.returncode
    except OSError as exc:
        print(f"spawn-hidden.sh: {exc}", file=sys.stderr)
        return 127


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
