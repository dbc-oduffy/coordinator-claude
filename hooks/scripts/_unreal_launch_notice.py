"""Shared body of the two Unreal-Engine launch notices.

Two audiences, one module: `subagent-start-unreal-training-notice.py` (every agent, SubagentStart)
and `session-start-unreal-em-notice.py` (the EM session, SessionStart). In a repo that
`declares_unreal_engine`, each emits the installed UE addon package's own text for its audience and
nothing coordinator-authored: the addon owns UE messaging. Only when the addon is absent or
unreadable does the bare `UNRELIABLE_LINE` stand in. Every failure is swallowed: a notice that
cannot be built is no notice, never a blocked launch.
"""
from __future__ import annotations

import importlib.resources
import importlib.util
import json
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Optional

_LIB_DIR = Path(__file__).resolve().parents[2] / "lib"

ADDON_PACKAGE = "project_rag_ue_addon"
MESSAGING_DIR = "ue_messaging"
AGENT_SOLUTION_FILE = "ue-solution-agent.txt"
EM_SOLUTION_FILE = "ue-solution-em.txt"

UNRELIABLE_LINE = (
    "UNREAL ENGINE REPO: your training data on Unreal Engine is unreliable -- about 25% of the "
    "time you will confidently hallucinate an API, signature or behaviour."
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


def _lib_module(name: str) -> ModuleType:
    if str(_LIB_DIR) not in sys.path:
        sys.path.insert(0, str(_LIB_DIR))
    return __import__(name)


def solution_text(filename: str) -> str:
    """Verbatim text of `ue_messaging/<filename>` in the installed addon package; "" on any failure."""
    try:
        if importlib.util.find_spec(ADDON_PACKAGE) is None:
            return ""
        text = (importlib.resources.files(ADDON_PACKAGE) / MESSAGING_DIR / filename).read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001 -- absent, broken or unreadable addon: no solution text
        return ""
    return text if text.strip() else ""


def notice(raw_stdin: str, solution_file: str) -> str:
    """The addon text for this audience, else `UNRELIABLE_LINE`; "" when the repo does not declare unreal-engine."""
    root = _repo_root(_payload(raw_stdin).get("cwd") or "")
    if root is None or not _lib_module("ue_review_signal").declares_unreal_engine(root):
        return ""
    return solution_text(solution_file) or UNRELIABLE_LINE


def run(event: str, solution_file: str) -> int:
    """Reads the hook payload from stdin; prints one `additionalContext` envelope or nothing. Always 0."""
    try:
        text = notice(sys.stdin.read(), solution_file)
        if text:
            sys.stdout.write(json.dumps(
                {"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}))
            sys.stdout.write("\n")
    except Exception:  # noqa: BLE001 -- fail open: a launch is never blocked by this notice
        pass
    return 0
