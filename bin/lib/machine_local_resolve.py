"""machine_local_resolve — single canonical `machine-local` executable-path resolver.

Purpose: two call sites (`snippet-registry`, `verify-snippet-sync`) each hand-rolled a
byte-identical `_resolve_machine_local_bin` that returns a path for a THIRD PARTY
(claude-klabauter's `coordinator_core.snippet_sync.registry` / `.verify`) to `subprocess.run`
directly — a different contract from
`cc_invoke.py::_machine_local_get`, which performs the registry READ itself via a
direct `sys.executable` subprocess against `bin/_machine_local.py` and never hands out
an invokable path. Because the caller here needs a bin PATH, not a read result, this
module does not delegate to `_machine_local_get`; it is the minimal correct standalone
resolver for that distinct contract (see `cc_invoke.py` module docstring for the
read-a-key contract this deliberately does NOT reuse).

Windows failure mode this closes (`tasks/2026-07-20-install-dogfood-friction.md` § F7):
the old resolver checked `os.access(script_dir / "machine-local", os.X_OK)` first —
`os.access(..., X_OK)` is not a meaningful executability check on Windows, so it
returned the bare/extension-less bash `machine-local` file as the "resolved" bin. A
`subprocess.run([that, ...])` call then fails with `OSError: [WinError 193] %1 is not
a valid Win32 application` — CreateProcess cannot exec an extension-less shebang
script. The real Windows target is `machine-local.cmd`, installed to `~/.claude/bin`
at setup time, which the old resolver never looked for.

Resolution order:
  Windows (`os.name == "nt"`):
    1. `<script_dir>/machine-local.cmd` (delivered alongside the plugin bin/ tree)
    2. `shutil.which("machine-local")` — PATHEXT-aware, so this DOES find a `.cmd`
       on PATH (unlike a bare-name `subprocess.run` call, which never consults
       PATHEXT — WinError 2 if handed the bare name directly).
  POSIX:
    1. `<script_dir>/machine-local` (extension-less, `os.access(..., X_OK)` is a
       real executability check here)
    2. `shutil.which("machine-local")`

Returns the resolved path string, or None if no rung resolved (a registry miss/absent
sibling repo is a routine, non-fatal outcome for every caller of this module — each
caller degrades gracefully on None). Emits a one-line stderr breadcrumb on total
resolution failure so a silent downstream skip is traceable back to "machine-local not
found" instead of surfacing as an unrelated NOTE/skip further down the call chain.
This breadcrumb is new relative to the two `_resolve_machine_local_bin` copies this
module replaces (`snippet-registry`, `verify-snippet-sync`), which returned `None`
silently on total failure with no diagnostic; it fires on both the Windows and POSIX
resolution branches, deliberately (making a silent skip diagnosable outweighs the minor
POSIX behavior delta — every traced caller already redirects this stderr in tests).
(Review: code-reviewer — Finding 4, 2026-07-22.)

Spec backlink: tasks/2026-07-20-install-dogfood-friction.md § F7 (line 331 sweep item)
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from coordinator_core.win_portability import is_executable


def resolve_machine_local_bin(script_dir: Path) -> "str | None":
    """Resolve an invokable `machine-local` executable path near `script_dir`.

    `script_dir` is the caller's own directory (typically
    `Path(os.path.dirname(os.path.abspath(__file__)))`) — the delivered bin/ tree
    installs `machine-local` (POSIX) / `machine-local.cmd` (Windows) alongside the
    calling script. See module docstring for the full resolution order and the
    WinError 193 failure mode this closes.
    """
    if os.name == "nt":
        candidate_cmd = script_dir / "machine-local.cmd"
        if candidate_cmd.is_file():
            return str(candidate_cmd)
        found = shutil.which("machine-local")
        if found:
            return found
        print(
            f"machine_local_resolve: no machine-local.cmd found at {candidate_cmd} "
            "nor on PATH — machine-local-dependent lookups will degrade/skip",
            file=sys.stderr,
        )
        return None

    candidate = script_dir / "machine-local"
    if is_executable(candidate):
        return str(candidate)
    found = shutil.which("machine-local")
    if found:
        return found
    print(
        f"machine_local_resolve: no machine-local found at {candidate} nor on PATH — "
        "machine-local-dependent lookups will degrade/skip",
        file=sys.stderr,
    )
    return None
