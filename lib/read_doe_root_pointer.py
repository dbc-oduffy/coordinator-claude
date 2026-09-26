# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.

from __future__ import annotations

import os
import sys
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parent


def _resolve_settings_home() -> str:
    try:
        sys.path.insert(0, str(_LIB_DIR))
        import settings_home as _settings_home_mod  # type: ignore

        return _settings_home_mod.settings_home()
    except Exception:
        return ""
    finally:
        try:
            sys.path.remove(str(_LIB_DIR))
        except ValueError:
            pass


def coordinator_read_doe_root_pointer() -> str:
    """Read the DoE repo root from the durable pointer, legacy fallback.

    Read order:
      1. ${settings-home}/machine-local/.doe-root  (durable — DR-072)
      2. ${CLAUDE_HOME:-$HOME}/.claude/.doe-root    (legacy fallback)
    """
    home = os.environ.get("CLAUDE_HOME") or os.environ.get("HOME") or os.environ.get("USERPROFILE") or ""
    if not home:
        return ""

    root = ""
    settings_home = _resolve_settings_home()
    if settings_home:
        try:
            root = (Path(settings_home) / "machine-local" / ".doe-root").read_text(encoding="utf-8").rstrip("\n")
        except OSError:
            root = ""

    if not root:
        try:
            root = (Path(home) / ".claude" / ".doe-root").read_text(encoding="utf-8").rstrip("\n")
        except OSError:
            root = ""

    return root


def _cli(argv: list[str]) -> int:
    if not argv or argv[0] == "--print":
        print(coordinator_read_doe_root_pointer(), end="")
        return 0
    print(f"unknown mode: {argv[0]}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
