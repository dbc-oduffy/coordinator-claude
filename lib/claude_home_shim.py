"""claude_home_shim.py — importable seam onto coordinator/lib/claude-home/_claude_home.py.

`coordinator/lib/claude-home/` is a hyphenated directory name; Python cannot
import it as a package (`import claude-home` is a syntax error, and
`from claude-home import x` fails the same way). Every consumer that wants
the resolver has historically hand-rolled `sys.path.insert` or an
`importlib.util.spec_from_file_location` load to work around this.

This module is that seam, written once: it loads `_claude_home.py` by
explicit file path and re-exports the two names most consumers need —
`resolve_home_base` and `home_dir` — as ordinary importable attributes.
A normal `import claude_home_shim` (or `from claude_home_shim import
resolve_home_base`) is all a caller needs; no `sys.path` or `importlib`
work of their own.

    from claude_home_shim import resolve_home_base, home_dir
    base = resolve_home_base()   # == home_dir(), see _claude_home.py docstring

This is deliberately additive: it does not restructure or rename the
hyphenated `claude-home/` directory, and it does not turn that directory
into a real Python package. It is a sibling file, not a member of it.

Spec backlink: pln-home-resolution-gate-family-ma-e5c146 § C6
"""
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
