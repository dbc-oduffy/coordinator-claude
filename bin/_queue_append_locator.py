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

import importlib.util
import os
import shutil  # noqa: F401 -- re-export shim keeps this name patchable by callers/tests
import subprocess
import sys


def _ensure_bin_lib_bootstrapped() -> None:
    """Import `coordinator/bin/lib` by location, never by bare name.

    Same by-location bootstrap as `coordinator-doc-new.py`'s
    `_ensure_bin_lib_bootstrapped` -- see that function's docstring for why a
    bare `import lib` is unsafe here (a PEP-420 namespace-package shadow from
    `coordinator/lib` when `coordinator/` precedes `coordinator/bin` on
    `sys.path`). Idempotent; safe to call more than once.
    """
    if "lib" in sys.modules and getattr(sys.modules["lib"], "__file__", None):
        return
    _bin_lib = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
    _spec = importlib.util.spec_from_file_location(
        "lib", os.path.join(_bin_lib, "__init__.py"), submodule_search_locations=[_bin_lib]
    )
    if _spec is None or _spec.loader is None:
        raise ImportError(f"coordinator/bin/lib is not importable at {_bin_lib}")
    _module = importlib.util.module_from_spec(_spec)
    sys.modules["lib"] = _module
    _spec.loader.exec_module(_module)


_ensure_bin_lib_bootstrapped()
from python_interp import (  # noqa: E402
    is_console_python_basename as _is_console_python_basename,
    resolve_console_python as _resolve_python_interpreter,
)


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
