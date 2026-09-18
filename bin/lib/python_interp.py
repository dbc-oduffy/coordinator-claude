"""
Shared console-CPython interpreter resolver.

Single source of truth for "is this path a real console CPython, not a
pythonw-style GUI-subsystem build or a non-python forwarder exe" and for the
`sys.executable` / `sys._base_executable` / `shutil.which` ladder that
resolves one. Extracted verbatim from
`coordinator/bin/_queue_append_locator.py` (`_is_console_python_basename` /
`_resolve_python_interpreter`) so every swept caller shares one ladder
instead of re-deriving it -- see
docs/plans/2026-08-31-the-sys-executable-class-one-shared-inte.md.

Stdlib-only, `subprocess`-free by design: the absence of a `subprocess`
import is itself the "zero spawns" enforcement for this module, checkable
by `ast` rather than by timing.

Not a CLI entry point -- no shebang, no sh/python polyglot trampoline.
Import only; never invoked directly.
"""
from __future__ import annotations

import os
import shutil
import sys


def is_console_python_basename(path: str) -> bool:
    """True if `path`'s basename names a console CPython interpreter.

    Negative spec: `pythonw`/`pythonw3` (any extension) are excluded even
    though they start with "python". `pythonw.exe` is the GUI-subsystem
    build with no usable stdout by default -- a caller whose whole contract
    depends on reading a child's stdout would reproduce the exact
    silent-loss class this predicate exists to close, just one level down: a
    plausible exit code with nothing on stdout. Console-flash avoidance
    (`coordinator_core/win_portability.py`, `verify-no-console-flash.py`) is
    an active pattern in this repo, so a launcher chosen specifically to
    avoid a console flash is exactly the context where `sys.executable`
    would be `pythonw.exe` -- do not "simplify" this back to a bare
    `startswith("python")`.
    # Review: code-reviewer P2 — pythonw.exe/pythonw3.exe silently accepted.
    """
    stem = os.path.splitext(os.path.basename(path))[0].lower()
    # Review: code-reviewer — nit: `startswith("python")` would also accept a
    # hypothetical non-python `pythonstub.exe` on PATH with no further
    # validation here. Defended in depth by each caller's own liveness probe
    # (e.g. a `--help` subprocess check gating the value before it is ever
    # handed back as the final argv) -- this is not a live hole there.
    return stem.startswith("python") and not stem.startswith("pythonw")


def resolve_console_python() -> str | None:
    """Resolve a real CPython interpreter, never a non-python launcher exe.

    Negative spec: `sys.executable` is NOT trustworthy as-is here. A
    forwarder-shaped launcher (e.g. an installed `.exe` forwarder) reports
    that forwarder's own embedded interpreter as `sys.executable`. Handing
    that exe a script path re-enters the FORWARDER's own argv parsing with
    the script as an unknown positional -- the child never runs the
    intended script, while the forwarder still exits 0, so the failure is
    silent.

    A `pythonw`-named `sys.executable` is rejected on the same theory (see
    `is_console_python_basename`) but does NOT return None immediately --
    it falls through to `sys._base_executable` and then `shutil.which`,
    either of which may resolve a console interpreter. Returning None early
    on a `pythonw` `sys.executable` would turn a recoverable case into a
    refusal.
    """
    exe = sys.executable or ""
    if is_console_python_basename(exe):
        return exe
    base = getattr(sys, "_base_executable", None)
    if base and is_console_python_basename(base):
        return base
    for name in ("python3", "python"):
        found = shutil.which(name)
        if found:
            return found
    return None


def python_argv(script: str, *args: str) -> list[str] | None:
    """Build `[interpreter, script, *args]` over `resolve_console_python()`.

    Returns None when nothing resolves so callers keep their existing
    degrade-gracefully contracts (skip/fallback) rather than inheriting a
    raise from this helper.
    """
    interpreter = resolve_console_python()
    if interpreter is None:
        return None
    return [interpreter, script, *args]
