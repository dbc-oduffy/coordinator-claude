"""
_win_portability -- stdlib-only console-suppression primitive for hook consumers.

Purpose: `docs/plans/2026-08-07-widen-layer1-spawn-tripwire-to-py-ps1.md` C1. A
subprocess spawned on Windows without console suppression allocates a fresh
``conhost.exe`` window that flashes and steals keyboard focus, with no POSIX
equivalent to omit. This module ships ``no_console_creationflags()``, the same
name and contract as `coordinator/lib/win_portability.py` and the engine
plane's own equivalent module, so all three are recognisably the same
primitive -- but with NO `coordinator_core` import and no dependency on
`coordinator/lib/`.

`_`-prefixed name matches the existing hook-module convention
(`_engine_root.py`, `_guard_runner.py`): the ~59 hook modules already do
`sys.path.insert(0, _HOOKS_DIR)` and import `_`-prefixed siblings from
`hooks/scripts/` directly, rather than reaching into `coordinator/lib/`, which
has no `__init__.py` and is not an importable package. Consumers write:
`from _win_portability import no_console_creationflags` after that existing
`sys.path.insert(0, _HOOKS_DIR)` idiom. A hook raising `ImportError` degrades
every tool call, so this import seam is load-bearing, not cosmetic.

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
      assumptions -- this module must import cleanly via the hooks'
      sys.path-insertion convention alone.
"""

from __future__ import annotations

import os

__all__ = [
    "no_console_creationflags",
    "no_console_spawn_kwargs",
    "noninteractive_git_env",
]


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


def no_console_spawn_kwargs() -> dict:
    """Kwargs to splat as `**no_console_spawn_kwargs()` into a child launch so
    it shows no console window, steals no focus, and does not flip the cursor
    to AppStarting (the busy arrow).

    POSIX: `{}`. Windows: `creationflags` = CREATE_NO_WINDOW plus a
    `startupinfo` with `STARTF_USESHOWWINDOW | STARTF_FORCEOFFFEEDBACK` and
    `wShowWindow = SW_HIDE`. `no_console_creationflags()` stays as the
    creationflags-only primitive; this is the full route.

    Invariant: a NEW `STARTUPINFO` per call -- `Popen` mutates `dwFlags` (adds
    `STARTF_USESTDHANDLES`), so a shared object leaks state between spawns.

    Trap: CREATE_NO_WINDOW leaves a child with no console, so a call that
    wires no stdin/stdout/stderr/capture_output loses its output. Wire the
    streams explicitly, or do not splat this into that call.
    """
    if not _is_windows():
        return {}

    import subprocess

    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 0x1) | 0x80
    startupinfo.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
    return {
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
        "startupinfo": startupinfo,
    }


def noninteractive_git_env(base: dict | None = None) -> dict:
    """Copy of `base` (default `os.environ`) with `GIT_TERMINAL_PROMPT=0` and
    `GCM_INTERACTIVE=never`, so a git child fails fast instead of opening a
    credential prompt window. Applied on every OS; harmless off Windows. Never
    mutates `base`.
    """
    env = dict(os.environ if base is None else base)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "never"
    return env
