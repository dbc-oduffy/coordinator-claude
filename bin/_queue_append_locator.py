from __future__ import annotations

import importlib.util
import os
import shutil  # noqa: F401 -- re-export shim keeps this name patchable by callers/tests
import subprocess
import sys


def _ensure_bin_lib_bootstrapped() -> None:
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


def find_cli_cmd(
    caller_dir: str, cli_name: str, *, sibling_only: bool = False
) -> list[str] | None:
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

    `sibling_only` skips both PATH probes and resolves only the sibling in
    `caller_dir`. A caller passes it when it needs the child to run in ITS
    OWN process tree, because the PATH name does not lead to a process at
    all. Every name in `~/.coordinator-claude-settings/bin/` is one shared
    generic DOOR binary — measured 2026-09-20: 444 byte-identical copies,
    sha256 711532ed9123…, 53952 bytes each — which dispatches on its own
    image name to `<engine>/coordinator/bin/<name>.py` inside the RESIDENT
    warm engine. Its JSON-RPC payload is `{"method":"invoke.from_argv",
    "params":{"argv":[…],"cwd":…}}`: argv and cwd, and no env
    (`coordinator_core/op_scopes.py`'s `invoke.from_argv` entry says the same
    — resolution happens from that explicit `cwd`). The served CLI therefore
    runs under the SERVER's environment, not the caller's, so a caller's env
    override never reaches it. `warm/server.py::_scrub_test_harness_env` then
    drops the test-isolation vars outright at boot, deliberately.

    That is the whole mechanism behind an eleven-week leak: harvest tests set
    `LESSON_PROMOTE_OUTBOX_ROOT`, the door dropped it, and the served CLI
    resolved the live `repos.doe_claude` outbox instead of the tmpdir. Going
    sibling-only runs the CLI cold in the caller's own process tree, which is
    the ONLY route where a test-isolation env var applies by design.

    Negative-spec: NOT a general "prefer the source tree" switch, and never
    the default. A live invocation SHOULD reach the door — warm dispatch is
    the contract and the budget. Only a caller already established as under
    test may pin the tree.

    Negative-spec: do NOT grep a door binary for a CLI-specific string. It
    holds none, for any CLI, so a zero hit is the expected answer and carries
    no information about the source. Reading one as if it were that CLI's
    artifact produced exactly one wrong root cause here already.
    """
    if not sibling_only:
        for candidate in (cli_name, cli_name + ".py"):
            try:
                result = subprocess.run(
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
            result = subprocess.run(
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
    return find_cli_cmd(caller_dir, "coordinator-queue-append")
