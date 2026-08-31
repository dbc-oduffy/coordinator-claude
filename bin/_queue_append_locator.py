"""
Shared locator for sibling extensionless-Python CLIs in this directory
(`coordinator-queue-append`, `coordinator-lesson-promote`, ...). Single
source of truth for the PATH-probe + sibling-path fallback so the probe
logic and its subprocess-cmd-list construction are not re-derived per
caller (was triplicated pre-consolidation: DoE
docs/plans/2026-07-15-bash-to-naked-python-engine-migration.md leaf
already-python-cleanup).

Originally named for its first (and, pre-generalization, only) consumer,
`coordinator-queue-append`; `find_cli_cmd()` is the general entry point and
`find_queue_append_cmd()` is now a thin back-compat wrapper over it kept for
the four existing `migrate-*.py` callers.

Not a CLI entry point — no shebang, no sh/python polyglot trampoline.
Import only; never invoked directly.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys


def _is_console_python_basename(path: str) -> bool:
    """True if `path`'s basename names a console CPython interpreter.

    Negative spec: `pythonw`/`pythonw3` (any extension) are excluded even
    though they start with "python". `pythonw.exe` is the GUI-subsystem
    build with no usable stdout by default -- this locator's whole contract
    is that `coordinator-queue-append` PRINTS the path it wrote, so handing
    a `pythonw`-resolved interpreter back here would reproduce the exact
    silent-loss class this module exists to close, just one level down: a
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
    # validation here. Defended in depth: the sibling `--help` probe in
    # `find_cli_cmd` (`returncode == 0` check) gates the value before it is
    # ever handed back as the final argv, so this is not a live hole.
    return stem.startswith("python") and not stem.startswith("pythonw")


def _resolve_python_interpreter() -> str | None:
    """Resolve a real CPython interpreter, never a non-python launcher exe.

    Negative spec: `sys.executable` is NOT trustworthy as-is here. A sibling
    CLI reached through an installed `.exe` forwarder (e.g.
    `coordinator-lesson-add.exe`) reports that forwarder's own embedded
    interpreter as `sys.executable`. Handing that exe a script path re-enters
    the FORWARDER's own argv parsing with the script as an unknown
    positional -- the child never runs the intended script, while the
    forwarder still exits 0, so the failure is silent.

    A `pythonw`-named `sys.executable` is rejected on the same theory (see
    `_is_console_python_basename`) but does NOT return None immediately --
    it falls through to `sys._base_executable` and then `shutil.which`,
    either of which may resolve a console interpreter. Returning None early
    on a `pythonw` `sys.executable` would turn a recoverable case into a
    refusal.
    """
    exe = sys.executable or ""
    if _is_console_python_basename(exe):
        return exe
    base = getattr(sys, "_base_executable", None)
    if base and _is_console_python_basename(base):
        return base
    for name in ("python3", "python"):
        found = shutil.which(name)
        if found:
            return found
    return None


def find_cli_cmd(caller_dir: str, cli_name: str) -> list[str] | None:
    """
    Return the ready-to-use subprocess argv PREFIX for invoking the
    extensionless sibling CLI `cli_name` (caller appends its own flags
    after it), or None if not locatable.

    Probe order: bare `cli_name` on PATH, then `cli_name + ".py"` on PATH,
    then a sibling-path fallback in `caller_dir` (the directory of the
    CALLING script, passed explicitly rather than derived from this
    module's own __file__ — all current callers happen to be siblings of
    this module, but a library contract should not assume that), invoked
    via sys.executable. Covers Windows Python, which uses Windows PATH
    rather than bash PATH, so a bin/-installed sibling may be
    locatable-by-path but not on Windows PATH — and covers the harder
    Windows case where the sibling is an extensionless script at all:
    CreateProcess cannot launch it directly (WinError 193), so the
    sys.executable-prefixed fallback is the only branch that works there.

    Deliberate isolation boundary — do not convert to an in-process
    import. This is a distinct-target probe: a `--help` liveness check
    on a candidate sibling CLI before committing to it, so the probe
    must observe that CLI's own process exit rather than the caller's.
    Reason recorded in
    state/audits/2026-08-06-self-spawn-isolation-boundary-classification.md.
    """
    for candidate in (cli_name, cli_name + ".py"):
        try:
            # Review: code-reviewer — pre-existing hazard, untouched by this
            # diff: this bare-PATH probe validates only `returncode == 0` on
            # a name found via PATH lookup, so a forwarder that answers
            # `--help` with exit 0 for an unrelated reason would still pass.
            # Seen and left deliberately: the probe order (PATH bare name →
            # PATH .py → interpreter+sibling) is load-bearing and currently
            # correct -- the bare-name probe resolving queue-append's own
            # forwarder is the right door. Do not change the probe order.
            result = subprocess.run(  # popup-intentional-last-resort
                [candidate, "--help"],
                capture_output=True,
                text=True,
            )
        except OSError:
            continue
        if result.returncode == 0:
            return [candidate]

    interpreter = _resolve_python_interpreter()
    if interpreter is None:
        return None

    for sibling_candidate in (cli_name, cli_name + ".py"):
        sibling = os.path.join(caller_dir, sibling_candidate)
        if not os.path.exists(sibling):
            continue
        try:
            result = subprocess.run(  # popup-intentional-last-resort
                [interpreter, sibling, "--help"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return [interpreter, sibling]
        except OSError:
            pass

    return None


def find_queue_append_cmd(caller_dir: str) -> list[str] | None:
    """
    Return the ready-to-use subprocess argv PREFIX for invoking
    coordinator-queue-append (caller appends --schema/... after it), or
    None if not locatable.

    Back-compat wrapper over `find_cli_cmd` — kept for the existing
    migrate-*.py callers; signature and return contract unchanged.
    """
    return find_cli_cmd(caller_dir, "coordinator-queue-append")
