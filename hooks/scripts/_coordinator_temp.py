"""Single Temp root for fleet tooling: <gettempdir()>/coordinator/<repo-slug>/.

Stdlib only; hooks import this before engine resolution.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

from _win_portability import no_console_spawn_kwargs, noninteractive_git_env  # noqa: E402

_ROOT_NAME = "coordinator"


def _default_slug() -> str:
    """Directory name of the git toplevel, else of the cwd."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=10,
            env=noninteractive_git_env(),
            **no_console_spawn_kwargs(),
        )
        top = out.stdout.strip()
        if out.returncode == 0 and top:
            return Path(top).name
    except (OSError, subprocess.SubprocessError):
        pass
    return Path.cwd().name


def coordinator_temp_root(repo_slug: str | None = None) -> Path:
    """Return (creating it) <gettempdir()>/coordinator/<slug>; slug defaults to the git toplevel name."""
    slug = repo_slug or _default_slug()
    if not slug or slug in (".", "..") or "/" in slug or "\\" in slug:
        raise ValueError(f"invalid coordinator temp slug: {slug!r}")
    root = Path(tempfile.gettempdir()) / _ROOT_NAME / slug
    root.mkdir(parents=True, exist_ok=True)
    return root
