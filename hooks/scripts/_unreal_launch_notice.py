"""Shared body of the two Unreal-Engine launch notices.

Two audiences, one module: `subagent-start-unreal-training-notice.py` (every agent, SubagentStart)
and `session-start-unreal-em-notice.py` (the EM session, SessionStart) each emit a
coordinator-authored line here, then append the matching example-game-repo solution text verbatim when the
`example-game-repo-control` plugin is installed. The line fires on `declares_unreal_engine(repo_root)` alone;
the solution files are `<example-game-repo-control root>/hooks/ue-solution-agent.txt` and
`ue-solution-em.txt`, read as plain text. Nothing is imported from example-game-repo. Every failure is
swallowed: a notice that cannot be built is no notice, never a blocked launch.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

_LIB_DIR = Path(__file__).resolve().parents[2] / "lib"

EXAMPLE_GAME_REPO_PLUGIN = "example-game-repo-control"
AGENT_SOLUTION_FILE = "ue-solution-agent.txt"
EM_SOLUTION_FILE = "ue-solution-em.txt"

AGENT_LINE = (
    "UNREAL ENGINE REPO: your training data on Unreal Engine is unreliable -- about 25% of the "
    "time you will confidently hallucinate an API, signature or behaviour. You MUST use "
    "project-rag (engine source, symbols, examples) to ground every UE claim before you write or "
    "assert it."
)
EM_LINE = (
    "UNREAL ENGINE REPO: do not run UE work from your own recall. Use the UE specialists: hand UE "
    "implementation to the ue-* agents, and UE plans and diffs to game-dev:staff-game-dev (the Game Dev Reviewer) "
    "with coordinator:docs-checker."
)


def _payload(raw: str) -> dict:
    try:
        obj = json.loads(raw) if raw else {}
    except ValueError:
        return {}
    return obj if isinstance(obj, dict) else {}


def _repo_root(cwd: str) -> Optional[Path]:
    start = Path(cwd or os.getcwd())
    for d in (start, *start.parents):
        if (d / "coordinator.local.md").is_file():
            return d
    return None


def _lib_module(name: str):
    if str(_LIB_DIR) not in sys.path:
        sys.path.insert(0, str(_LIB_DIR))
    return __import__(name)


def _solution_text(filename: str) -> str:
    """Verbatim text of `hooks/<filename>` under the installed example-game-repo-control root; "" when absent."""
    prs = _lib_module("plugin_review_signals")
    for root in prs.installed_plugin_roots():
        if prs.plugin_name(root) != EXAMPLE_GAME_REPO_PLUGIN:
            continue
        try:
            text = (root / "hooks" / filename).read_text(encoding="utf-8")
        except OSError:
            continue
        if text.strip():
            return text
    return ""


def notice(raw_stdin: str, line: str, solution_file: str) -> str:
    """The notice text for this payload, or "" when the repo does not declare unreal-engine."""
    root = _repo_root(_payload(raw_stdin).get("cwd") or "")
    if root is None or not _lib_module("ue_review_signal").declares_unreal_engine(root):
        return ""
    solution = _solution_text(solution_file)
    return line + ("\n\n" + solution if solution else "")


def run(event: str, line: str, solution_file: str) -> int:
    """Reads the hook payload from stdin; prints one `additionalContext` envelope or nothing. Always 0."""
    try:
        text = notice(sys.stdin.read(), line, solution_file)
        if text:
            sys.stdout.write(json.dumps(
                {"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}))
            sys.stdout.write("\n")
    except Exception:  # noqa: BLE001 -- fail open: a launch is never blocked by this notice
        pass
    return 0
