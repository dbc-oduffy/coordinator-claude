"""coordinator-settings-home.py — door-resolvable engine entrypoint for `coordinator-settings-home`.

Prints the coordinator settings-home root; `check` runs only the machine-local
divergence check. Exit codes: 0 ok, 1 divergent homes (remediation on stderr),
2 usage error.

The divergence check lives here and never inside `_settings_home.settings_home()`,
which stays a pure, zero-call read. Bootstrap-safe: stdlib plus
`coordinator_core._settings_home` only; the engine root is put on `sys.path`
because the `.cmd` twin starts a bare interpreter.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_ENGINE_ROOT = Path(__file__).resolve().parents[2]
if str(_ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ENGINE_ROOT))

from coordinator_core import _settings_home  # noqa: E402

_USAGE = "Usage: coordinator-settings-home [check]"

DIVERGENCE_MSG = (
    "coordinator-settings-home: DIVERGENT MACHINE-LOCAL HOMES — cannot safely resolve.\n"
    "\n"
    "Both ~/.claude/machine-local and <settings-home>/machine-local exist and point\n"  # abs-path-ok: operator-facing message text, not a read
    "at different content homes. Reading from either risks using stale or incomplete\n"
    "registry data.\n"
    "\n"
    "Remediation — re-run /coordinator:install (the substrate→settings-home\n"
    "migration is now performed natively by the coordinator install step).\n"
    "\n"
    "Or set COORDINATOR_SETTINGS_HOME to the intended settings home and remove/\n"
    "symlink the other directory to resolve the ambiguity.\n"
)


def _is_absent_or_empty_husk(path) -> bool:
    """True when `path` carries no machine-local state: absent, empty, or unreadable."""
    try:
        if not os.path.exists(path):
            return True
        return not os.listdir(path)
    except OSError:
        return True


def _check_divergence(settings_home: Path) -> bool:
    """False only when both machine-local homes hold content at different realpaths."""
    legacy = os.path.join(str(_settings_home.home_dir()), ".claude", "machine-local")
    new = os.path.join(str(settings_home), "machine-local")

    if _is_absent_or_empty_husk(legacy) or _is_absent_or_empty_husk(new):
        return True

    rp_legacy = os.path.realpath(legacy)
    rp_new = os.path.realpath(new)
    if rp_legacy != rp_new:
        sys.stderr.write(DIVERGENCE_MSG)
        sys.stderr.write("  Legacy realpath : %s\n" % rp_legacy)
        sys.stderr.write("  New    realpath : %s\n" % rp_new)
        return False
    return True


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    cmd = args[0] if args else ""

    if cmd in ("--help", "-h"):
        sys.stdout.write(_USAGE + "\n")
        return 0
    if cmd not in ("", "check"):
        sys.stderr.write("coordinator-settings-home: unknown subcommand: %s\n" % cmd)
        sys.stderr.write(_USAGE + "\n")
        return 2

    try:
        settings_home = _settings_home.settings_home()
    except ValueError as exc:
        sys.stderr.write("coordinator-settings-home: %s\n" % exc)
        return 1

    if not _check_divergence(settings_home):
        return 1
    if cmd == "":
        sys.stdout.write(str(settings_home) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
