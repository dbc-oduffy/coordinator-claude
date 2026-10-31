"""subagent-start-unreal-training-notice.py -- the every-agent Unreal Engine notice (SubagentStart).

In a repo whose `coordinator.local.md` declares `project_type: unreal-engine`, tells each launched
agent its UE training data is unreliable and it MUST use project-rag, then appends example-game-repo's
`ue-solution-agent.txt` verbatim when example-game-repo-control is installed. Body in `_unreal_launch_notice`.
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
    return _n.run("SubagentStart", _n.AGENT_LINE, _n.AGENT_SOLUTION_FILE)


if __name__ == "__main__":
    sys.exit(main())
