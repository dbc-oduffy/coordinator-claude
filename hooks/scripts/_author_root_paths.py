"""
_author_root_paths -- the single list of `.content-root` pointer locations, in the
order the no-launcher fences read them.

Trap: adding or reordering a pointer location anywhere else re-creates the
drift between the hooks that read and write the pointer. Pure path
construction: no reads, no mkdir.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)
try:
    from _engine_root import _settings_home_registry_dir  # noqa: E402
except Exception:
    # Partial deploy without the sibling: no settings-home leg, never a crash.
    def _settings_home_registry_dir():  # type: ignore[no-redef]
        return None


_CONTENT_ROOT_POINTER_BASENAME = ".coordinator-content-root"
_CONTENT_ROOT_POINTER_BASENAME = ".content-root"  # compat-fallback: legacy pointer name


def _content_root_pointer_paths() -> "list[Path]":
    """Every pointer file to keep current: the content-root name first, then
    the legacy name, each at the two locations the fences try in order."""
    paths: "list[Path]" = []
    for basename in (_CONTENT_ROOT_POINTER_BASENAME, _CONTENT_ROOT_POINTER_BASENAME):
        try:
            reg_dir = _settings_home_registry_dir()
            if reg_dir is not None:
                paths.append(Path(reg_dir) / basename)
        except Exception:
            pass
        try:
            claude_home = os.environ.get("CLAUDE_HOME") or str(Path.home())
            paths.append(Path(claude_home) / ".claude" / basename)
        except Exception:
            pass
    return paths
