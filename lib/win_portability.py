"""
win_portability -- stdlib-only console-suppression primitive for lib/bin/CLI consumers.

Purpose: `docs/plans/2026-08-07-widen-layer1-spawn-tripwire-to-py-ps1.md` C1. A
subprocess spawned on Windows without console suppression allocates a fresh
``conhost.exe`` window that flashes and steals keyboard focus, with no POSIX
equivalent to omit. This module ships ``no_console_creationflags()``, the same
name and contract as the engine plane's own `win_portability.py`, so the two
are recognisably the same primitive -- but with NO `coordinator_core` import:
`coordinator/lib/` has no `__init__.py` and is not an importable package, so
this file is reached by explicit path insertion, not a package import, and
must not assume either project's package layout is present.

This pair is deliberately UNPARITIED against the engine plane's copy for now
(see C1's plan body) -- do not add a SHA-parity test here without a fresh
chunk to size it.

Negative-spec:
    - Off-Windows returns `{}` -- an EMPTY dict, never `{"creationflags": 0}`.
      The helper must spread nothing off-Windows; callers rely on
      `**no_console_creationflags()` being a true no-op there, not on POSIX
      `Popen` merely tolerating an extra key.
    - Uses `getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)`, never a
      bare `subprocess.CREATE_NO_WINDOW` attribute access -- that constant
      only exists on `subprocess` when the real host is Windows, and this
      module's own platform check is a patchable seam a test can flip on a
      POSIX host. The fallback is `0x08000000` -- `CREATE_NO_WINDOW`'s real
      value -- not `0`: a `0` fallback is falsy and silently degrades the
      Windows branch to a no-op `creationflags=0`, spawning the very console
      window this primitive exists to suppress.
    - Stdlib only. No `coordinator_core`, no relative imports, no package
      assumptions -- this module must import cleanly by explicit path
      insertion alone.
"""

from __future__ import annotations

import os

__all__ = ["no_console_creationflags"]


def _is_windows() -> bool:
    return os.name == "nt"


def no_console_creationflags() -> dict:
    """Kwargs mapping to splat into `subprocess.run` / `subprocess.Popen` as
    `**no_console_creationflags()` to suppress the `conhost.exe` popup window
    a Windows child process otherwise allocates.

    POSIX: returns `{}` -- there is no console-popup defect to suppress
    there, and an empty mapping splats to no-op kwargs, leaving stdout/stderr
    capture semantics on every existing call site completely unchanged.

    Windows: returns `{"creationflags": <CREATE_NO_WINDOW>}`.

    `import subprocess` is function-local, not module-scope, so this module
    stays importable before a venv exists or PATH is populated -- a
    module-scope import here would add a load-bearing dependency this
    primitive does not need on the common (non-Windows) path.
    """
    if not _is_windows():
        return {}

    import subprocess

    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)}
