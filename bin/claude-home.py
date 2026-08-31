"""claude-home.py — door-eligible engine entrypoint for `claude-home`.

Spec backlink: docs/plans/2026-08-30-twenty-one-bin-names-reach-the-door-or-
are-thoroughly-dead.md C5 (engine entrypoint only; cutover not shipped).

Purpose: the door (`_resolve_entrypoint_script`, `door.c :: fall_through`,
`door_posix.c`) resolves exactly `{engine_root}/coordinator/bin/<name>.py`,
falling back to the extensionless `{engine_root}/coordinator/bin/<name>`.
Neither existed for `claude-home` before this file, which is why the name
could never reach the door (see the plan body's "Established facts"). This
file is that missing entrypoint — a thin trampoline, carrying no logic of
its own, into the real implementation at
`coordinator/lib/claude-home/_claude_home.py`.

ELIGIBILITY IS NOT CUTOVER. Creating this file makes `claude-home`
door-eligible; no cutover has shipped on either platform, and
`_AGENT_HELPER_RESERVED_NAMES` (`substrate.py`) keeps the name reserved on
every platform, Windows included — see DR-365's 2026-08-30 note for the
current state and why.

Usage: identical to the co-located POSIX `claude-home` launcher and the
`_claude_home.py` implementation's own `_main(argv)` dispatch — see
`coordinator/lib/claude-home/_claude_home.py`'s module docstring for the
full subcommand list.
"""
from __future__ import annotations

import sys
from pathlib import Path

_IMPL_DIR = Path(__file__).resolve().parents[1] / "lib" / "claude-home"

if str(_IMPL_DIR) not in sys.path:
    sys.path.insert(0, str(_IMPL_DIR))

from _claude_home import _main  # noqa: E402

if __name__ == "__main__":
    sys.exit(_main(sys.argv))
