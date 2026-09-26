from __future__ import annotations

import os
import shutil
import sys


def is_console_python_basename(path: str) -> bool:
    stem = os.path.splitext(os.path.basename(path))[0].lower()
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
    interpreter = resolve_console_python()
    if interpreter is None:
        return None
    return [interpreter, script, *args]
