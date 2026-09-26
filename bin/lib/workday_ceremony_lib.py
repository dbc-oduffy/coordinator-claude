from __future__ import annotations

import os
import subprocess
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from cc_invoke import require_engine_on_path  # noqa: E402

_ENGINE_ROOT = require_engine_on_path(__file__)

from coordinator_core.win_portability import no_console_creationflags  # noqa: E402


def plugin_root() -> str:
    _this_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(_this_dir))


def lib_dir(root: str | None = None) -> str:
    return os.path.join(root or plugin_root(), "lib")


def git(
    *args: str,
    cwd: str | None = None,
    env: dict | None = None,
    check: bool = False,
    timeout: int = 300,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        check=check,
        timeout=timeout,
        **no_console_creationflags(),
    )


def git_ok(*args: str, cwd: str | None = None, env: dict | None = None) -> bool:
    return git(*args, cwd=cwd, env=env).returncode == 0


def git_out(*args: str, cwd: str | None = None, env: dict | None = None) -> str:
    proc = git(*args, cwd=cwd, env=env)
    if proc.returncode != 0:
        return ""
    return proc.stdout.rstrip("\n")
