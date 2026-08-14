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
import subprocess
import sys


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
            result = subprocess.run(  # popup-intentional-last-resort
                [candidate, "--help"],
                capture_output=True,
                text=True,
            )
        except OSError:
            continue
        if result.returncode == 0:
            return [candidate]

    for sibling_candidate in (cli_name, cli_name + ".py"):
        sibling = os.path.join(caller_dir, sibling_candidate)
        if not os.path.exists(sibling):
            continue
        try:
            result = subprocess.run(  # popup-intentional-last-resort
                [sys.executable, sibling, "--help"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return [sys.executable, sibling]
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
