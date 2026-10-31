"""session-start-unreal-em-notice.py -- the EM-session Unreal Engine notice (SessionStart leg).

A StartGuard in `sessionstart-dispatch.py`. In a repo whose `coordinator.local.md` declares
`project_type: unreal-engine`, tells the EM to use the UE specialists, then appends example-game-repo's
`ue-solution-em.txt` verbatim when example-game-repo-control is installed. Body in `_unreal_launch_notice`.
Fail-open; exit 0.
"""
from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import _unreal_launch_notice as _n  # noqa: E402


def main(argv=None) -> int:
    return _n.run("SessionStart", _n.EM_LINE, _n.EM_SOLUTION_FILE)


if __name__ == "__main__":
    sys.exit(main())
