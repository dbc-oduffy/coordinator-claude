# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""read_doe_root_pointer.py — shared substrate for reading the DoE repo root pointer.

Shared substrate: read the DoE repo root from the durable pointer file under
settings-home (${settings-home}/machine-local/.doe-root), falling back to the
legacy cold-readable pointer (~/.claude/.doe-root) during the transition
window. Neutral helper — NOT owned by resolve-coordinator-clone.py; shared by
any resolver rung that needs the pointer-file read.

DR-072: durable machine-local state belongs in settings-home, not the
resettable/synced ~/.claude tree. The ~/.claude/.doe-root fallback is
load-bearing, not vestigial — it is what keeps every machine working until
the untrack (C5-adjacent follow-on) lands and the legacy pointer is retired.
Do NOT remove the fallback branch without confirming that migration has
completed fleet-wide.

Port backlink: docs/plans/2026-07-19-debash-coordinator-windows.md (de-bash
campaign, chunk E3-e3f-lib). resolve-coordinator-clone.py carries its own
private mirror of this same read — see that file's `_read_doe_root_pointer()`.

Provides:
  coordinator_read_doe_root_pointer() -> str
    Returns the DoE repo root path (a single line, stripped) or "" if
    neither pointer file is present or readable. Does NOT validate whether
    the path exists on disk — callers apply that gate themselves.

CLI (for shell callers that cannot import Python in-process):
  read_doe_root_pointer.py --print
    Prints the resolved DoE root (or nothing) to stdout. Always exits 0.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parent


def _resolve_settings_home() -> str:
    """Resolve the settings-home root via the shared settings_home module.

    Non-fatal if settings_home.py is unreachable or import fails — falls
    through to the legacy-only read (mirrors the bash lib's warm-shape
    degrade-gracefully contract).
    """
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

    # rstrip("\n") mirrors bash command substitution `$(cat ...)`, which
    # strips only trailing newlines — not other whitespace — from the read.
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
