#!/usr/bin/env python3
"""Launch agy with coordinator EM defaults, leaving bare `agy` unchanged.

`coordinator-agy` and `agy-coordinator` strip a leading/embedded `--coordinator`
flag, default to `--dangerously-skip-permissions` (unless `--mode` or `--sandbox`
is given) plus the EM model and effort from `coordinator_core.agent_pipe.model_tiers`,
and `os.execvp` straight into `agy` on POSIX so TTY/child-process invariants hold.
Native Unimatrix hooks (`unimatrix-agy-hook-sessionstart.py` + `agy-legs`) handle
live peer delivery without a lingering parent process.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def agy_binary() -> str:
    found = shutil.which("agy")
    if not found:
        raise SystemExit("agy-coordinator: agy is not on PATH")
    return found


def strip_coordinator(argv: list[str]) -> list[str]:
    """Drop `--coordinator`. The real agy binary does not know that flag."""
    return [arg for arg in argv if arg != "--coordinator"]


def _plan_flags(extra: list[str]) -> list[str]:
    """Plan-role model and effort, unless the caller already set them."""
    try:
        lib = str(Path(__file__).resolve().parent / "lib")
        if lib not in sys.path:
            sys.path.insert(0, lib)
        import cc_invoke

        cc_invoke.ensure_engine_on_path(__file__)
        from coordinator_core.agent_pipe.model_tiers import AGY_EM_EFFORT, model_for_role
    except Exception:
        return []
    flags: list[str] = []
    if not any(a in ("--model", "-m") or a.startswith("--model=") for a in extra):
        flags += ["--model", model_for_role("agy", "em")]
    if not any(a == "--effort" or a.startswith("--effort=") for a in extra):
        flags += ["--effort", AGY_EM_EFFORT]
    return flags


def _permission_flags(extra: list[str]) -> list[str]:
    """Default to auto-approve unless caller passed an explicit permission/mode/sandbox flag."""
    if any(
        a in ("--dangerously-skip-permissions", "--mode", "--sandbox") or a.startswith("--mode=")
        for a in extra
    ):
        return []
    return ["--dangerously-skip-permissions"]


def interactive_argv(binary: str, extra: list[str]) -> list[str]:
    """Interactive launch. Extra args are the caller's."""
    return [binary, *_permission_flags(extra), *_plan_flags(extra), *extra]


def headless_argv(binary: str, text: str, extra: list[str] | None = None) -> list[str]:
    """One headless turn (`-p TEXT`)."""
    rest = list(extra or ())
    fmt_flags = (
        []
        if any(a == "--output-format" or a.startswith("--output-format=") for a in rest)
        else ["--output-format", "json"]
    )
    return [binary, *_permission_flags(rest), *_plan_flags(rest), "-p", text, *fmt_flags, *rest]


def exec_agy(argv: list[str]) -> int:
    """Replace this process with agy on POSIX; run synchronously on Windows."""
    if os.name != "nt":
        os.execvp(argv[0], argv)
    return subprocess.run(argv).returncode


def main(argv: list[str] | None = None) -> int:
    args = strip_coordinator(list(sys.argv[1:] if argv is None else argv))
    for i, arg in enumerate(args):
        if arg in ("-p", "--print"):
            if i + 1 >= len(args):
                raise SystemExit("agy-coordinator: -p needs the prompt text")
            prompt = args[i + 1]
            rest = args[:i] + args[i + 2 :]
            return exec_agy(headless_argv(agy_binary(), prompt, rest))
        if arg.startswith("--print="):
            prompt = arg[len("--print=") :]
            rest = args[:i] + args[i + 1 :]
            return exec_agy(headless_argv(agy_binary(), prompt, rest))
    return exec_agy(interactive_argv(agy_binary(), args))


if __name__ == "__main__":
    raise SystemExit(main())
