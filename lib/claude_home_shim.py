from __future__ import annotations

import importlib.util
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parent / "claude-home" / "_claude_home.py"

_spec = importlib.util.spec_from_file_location("_claude_home", _MODULE_PATH)
if _spec is None or _spec.loader is None:
    raise ImportError(f"could not build a module spec for {_MODULE_PATH}")
_claude_home = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_claude_home)

resolve_home_base = _claude_home.resolve_home_base
home_dir = _claude_home.home_dir

__all__ = ["resolve_home_base", "home_dir"]
