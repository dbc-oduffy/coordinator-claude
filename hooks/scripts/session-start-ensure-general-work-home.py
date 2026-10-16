"""SessionStart self-heal: the box's general-work home exists, git-initialised and seeded.

The home is the Group EM's only spawn home, and the installer that ships in the engine never
created it, so a fresh box had no home and `/group-em` rendered NOT ENTERED. This calls
`_gem_home.ensure_home()` on every boot, which makes the home a property of any box that runs
a session, whatever installed it.

Idempotent: a healthy home costs a registry read and three stats; `git init` spawns only when
`.git` is absent, and an existing `CLAUDE.md` is never overwritten.

Silent on success and on a refused home (one inside a checkout is the operator's to move, and
`general-work-home ensure` names it). Fails open everywhere.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HOOKS_DIR = Path(__file__).resolve().parent
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))


def main() -> int:
    try:
        sys.stdin.read()
    except Exception:
        pass
    try:
        import _gem_home

        _gem_home.ensure_home()
    except Exception:
        # HomeRefused, a missing git, an unwritable settings home: none may block a session.
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
