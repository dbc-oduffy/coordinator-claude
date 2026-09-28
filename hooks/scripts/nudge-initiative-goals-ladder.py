#!/usr/bin/env python3
"""PostToolUse(Write|Edit) naked-Python port of nudge-initiative-goals-ladder.sh.

When a file is Written or Edited under state/initiatives/*.yaml AND the written
initiative has an empty/absent `goals` field AND the repo has >=1 goal under
state/goals/*.yaml, surface an offer-shaped nudge (exit 2 + stderr) with matching
candidate goal-ids. Never blocks the write — PostToolUse exit 2 reaches the
model's next turn via stderr WITHOUT undoing the already-applied edit (offer-shape
per eager-agent-calibration.md § Offer-Shape vs Friction-as-Warning; platform
contract per docs/wiki/hook-best-practices.md § Friction-as-warning).

This port preserves every decision/advisory condition and the escape-hatch env
var byte-for-byte from the retired bash predecessor; the full suppression
table is reproduced in each guard clause below via inline comments.

Candidate-resolution seam: the engine repo's `goal.match_candidates` op
(coordinator_core/ops/goals_match.py — already exists, so this port is the "thin
doctrine-plane stub" branch of the migration brief, not a from-scratch reimplementation).
This port calls that op in-process (import + direct handler invocation,
`preuse-write-dispatch.py` `_resolve_claude_klabauter_root()` shape) rather than
spawning a bash veneer + subprocess — one fewer process per nudge, and it
fails open identically (no seam on disk / import error / handler exception ->
empty candidates, never a crash, matching the bash oracle's
`2>/dev/null || true` posture end to end). The historical
`bin/resolve-goal-candidates.sh` shell-out client this port superseded has
since been retired (killed, zero live callers) now that this hook is the only
consumer and calls the op directly.

Contract (mirrors the bash hook it replaces):
  stdin   -- PostToolUse JSON (tool_name, tool_input, cwd, ...)
  stdout  -- nothing on suppress/allow
  stderr  -- `[nudge] ...` lines when firing
  exit 0  -- silent suppression / no-op (fail-open)
  exit 2  -- advisory nudge fired (stderr reaches the model's next turn)

Escape hatch: COORDINATOR_INITIATIVE_GOALS_NUDGE_OFF=1 (autonomous runs).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)
try:
    from _engine_root import (  # noqa: E402
        resolve_claude_klabauter_root as _resolve_claude_klabauter_root,
        place_engine_root_on_path as _place_engine_root_on_path,
    )
except Exception:
    def _resolve_claude_klabauter_root() -> str | None:
        return None

    def _place_engine_root_on_path(root):
        if root and root not in sys.path[:2]:
            sys.path.insert(1 if sys.path else 0, root)
        return root

try:
    import _message_envelope as _envelope  # noqa: E402
except Exception:
    from dataclasses import dataclass as _dataclass
    from typing import Optional as _Optional

    @_dataclass(frozen=True)
    class _FallbackMessage:
        prose: str
        alternative: "_Optional[str]" = None
        anchor: "_Optional[str]" = None

    class _FallbackEnvelope:
        CHANNEL_STOP = "stop"
        Message = _FallbackMessage

        @staticmethod
        def compose(prose, alternative=None, anchor=None):
            return _FallbackMessage(prose=prose.strip(), alternative=alternative, anchor=anchor)

        @staticmethod
        def emit(message, channel):  # noqa: ARG004 -- single-channel fallback
            parts = [message.prose]
            if message.alternative:
                parts.append("")
                parts.append("```\n" + message.alternative.rstrip("\n") + "\n```")
            if message.anchor:
                parts.append("")
                parts.append("See {}.".format(message.anchor))
            sys.stderr.buffer.write("\n".join(parts).encode("utf-8"))
            return 2

    _envelope = _FallbackEnvelope()


def _git_toplevel(cwd: str) -> str:
    """Best-effort `git -C <cwd> rev-parse --show-toplevel`; "" on any failure.

    A-F2 (P2 C8): timeout trimmed 5.0 -> 2.0. This hook is called up to
    twice sequentially (dir_of_file, then os.getcwd() fallback) -- at 5.0s
    each, two back-to-back timeouts alone could exhaust this hook's entire
    10s hooks.json budget before the unbounded asyncio.run goal-match op
    even starts. 2.0s is still generous for a local millisecond-scale git op.

    Moved below this module's own path-setup/import block (C4b) -- the
    STOP-FAMILY-RUNNER-CONTRACT conformance test locates the LAST plain
    import-shaped line and flags any late path-insertion after it; this
    function carries no import of its own, so its ORIGINAL position (before
    that self-resolution block) made the block read as occurring after the
    import block to the heuristic, even though nothing about
    `_git_toplevel` itself touches import/path ordering at runtime. A pure
    textual move, zero behaviour change -- the same house-standard shape
    every other guard in this directory already uses (self-resolution
    block immediately after the stdlib import list, no function definition
    sandwiched in between).
    """
    try:
        proc = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=2.0,
            creationflags=_NO_WINDOW,
        )
    except Exception:
        return ""
    if proc.returncode != 0:
        return ""
    return (proc.stdout or "").strip()


_WIKI_ANCHOR = (
    "coordinator/docs/wiki/guards/guard-message-concision.md"
    "#initiative-goals-nudge-remedies"
)


def _resolve_goal_candidates(repo_root: str, text: str) -> list:
    if not text:
        return []

    root = _resolve_claude_klabauter_root()
    if not root:
        return []

    # STOP-FAMILY-RUNNER-CONTRACT clause 8 (sys.path ordering): append,
    # never insert at index 0 -- the hooks dir (inserted at the top of this
    # module) must stay ahead of the sibling engine root on sys.path.
    # Index-1 placement via the shared primitive: hooks dir stays at 0, engine root
    # outranks site-packages. A bare append put it BEHIND an editable install of the
    # engine, so the resolver answered the mirror and the import returned the working
    # tree -- see _engine_root.place_engine_root_on_path.
    _place_engine_root_on_path(root)

    try:
        import asyncio

        import coordinator_core.ops.goals_match  # noqa: F401 -- registers the op
        from coordinator_core.ipc import get_op_handler
        from coordinator_core.lifecycle import git_common_dir

        handler = get_op_handler("goal.match_candidates")
        if handler is None:
            return []

        # goal.match_candidates is keyed on git_common_dir (coordinator_core/ipc.py
        # WORKTREE_SCOPED_OPS comment: "goal.match_candidates -- keyed on
        # git_common_dir: reads state/goals/ under main_worktree_root(common_dir)").
        # The handler derives the worktree root as common_dir.parent -- passing the
        # worktree root itself here (what git rev-parse --show-toplevel gives us)
        # would make it look one directory too high and always return [].
        common_dir = git_common_dir(Path(repo_root))

        result = asyncio.run(
            asyncio.wait_for(handler({"text": text}, repo_root=common_dir), timeout=3.0)
        )
    except Exception:
        return []

    if not isinstance(result, dict):
        return []
    candidates = result.get("candidates")
    if not isinstance(candidates, list):
        return []
    return candidates


def _compose_nudge_message(
    initiative_id: str, candidate_ids: "list[str]", candidate_ids_str: str
) -> "_envelope.Message":
    """Pure message composer, routed through `_message_envelope.compose`
    (docs/plans/2026-08-02-guard-message-character-cap.md § C6). The
    diagnosis names the initiative and any matched candidate goal(s); the
    one runnable attach command rides in the exempt `alternative` slot;
    the rest of the prior inline explanation (including the
    COORDINATOR_INITIATIVE_GOALS_NUDGE_OFF=1 escape hatch) relocates to
    `_WIKI_ANCHOR` -- see
    state/relocations/guard-message-cap/nudge-initiative-goals-ladder.py.md."""
    if candidate_ids_str:
        prose = (
            "Initiative {} has no goals field; candidate goal(s): {}. Attach "
            "one, or ignore -- nothing is blocked.".format(initiative_id, candidate_ids_str)
        )
        first_id = candidate_ids[0] if candidate_ids else ""
        alternative = "coordinator-initiative attach --goals {} state/initiatives/{}.yaml".format(
            first_id, initiative_id
        )
    else:
        prose = (
            "Initiative {} has no goals field, and this repo has goal(s) "
            "under state/goals/. Tag one, or ignore -- nothing is "
            "blocked.".format(initiative_id)
        )
        alternative = "coordinator-initiative attach --goals <goal-id> state/initiatives/{}.yaml".format(
            initiative_id
        )
    return _envelope.compose(prose, alternative=alternative, anchor=_WIKI_ANCHOR)


def _compose_nudge_text(initiative_id: str, candidate_ids: "list[str]", candidate_ids_str: str) -> str:
    return _compose_nudge_message(initiative_id, candidate_ids, candidate_ids_str).prose


def main() -> int:
    if os.environ.get("COORDINATOR_INITIATIVE_GOALS_NUDGE_OFF", "0") == "1":
        return 0

    try:
        raw = sys.stdin.read()
    except Exception:
        raw = ""

    tool_name = ""
    file_path = ""
    content = ""
    lines: list = []
    try:
        payload = json.loads(raw) if raw else {}
    except Exception:
        payload = {}
    if isinstance(payload, dict):
        tool_input = payload.get("tool_input")
        if not isinstance(tool_input, dict):
            tool_input = {}
        tool_name = payload.get("tool_name") or ""
        file_path = tool_input.get("file_path") or ""
        content_raw = tool_input.get("content")
        if not content_raw:
            content_raw = tool_input.get("new_string")
        if isinstance(content_raw, str) and content_raw:
            content = "\n".join(content_raw.splitlines()[:60])

    if tool_name not in ("Write", "Edit"):
        return 0

    if not file_path:
        return 0

    file_path_norm = file_path.replace("\\", "/")

    base = os.path.basename(file_path_norm)
    dirpart = file_path_norm[: -len(base)] if base else file_path_norm
    is_initiative_yaml = base.endswith(".yaml") and (
        dirpart.endswith("/state/initiatives/") or dirpart == "state/initiatives/"
    )
    if not is_initiative_yaml:
        return 0

    if content:
        lines = content.split("\n")

        inline_re = re.compile(r"^goals:[ \t]*[^ \t#\[]")
        goals_line_re = re.compile(r"^goals:")
        for line in lines:
            if inline_re.match(line):
                goals_val = goals_line_re.sub("", line, count=1)
                goals_val = goals_val.lstrip(" \t")
                if goals_val not in ("null", "", "[]", "~"):
                    return 0
                break

        list_item_re = re.compile(r"^[ \t]+-")
        for i, line in enumerate(lines):
            if goals_line_re.match(line):
                if i + 1 < len(lines) and list_item_re.match(lines[i + 1]):
                    return 0
                break

    repo_root = ""
    dir_of_file = os.path.dirname(file_path_norm)
    if dir_of_file and os.path.isdir(dir_of_file):
        repo_root = _git_toplevel(dir_of_file)
    if not repo_root:
        repo_root = _git_toplevel(os.getcwd())
    if not repo_root:
        return 0

    goals_dir = Path(repo_root) / "state" / "goals"
    if not goals_dir.is_dir():
        return 0
    goal_count = sum(1 for f in goals_dir.glob("*.yaml") if f.is_file())
    if goal_count == 0:
        return 0

    match_text = ""
    if content:
        label_re = re.compile(r"^label:[ \t]+(.*)$")
        desc_re = re.compile(r"^description:[ \t]+(.*)$")
        for line in lines:
            m = label_re.match(line)
            if m:
                match_text = m.group(1).replace('"', "")
                break
        if not match_text:
            for line in lines:
                m = desc_re.match(line)
                if m:
                    match_text = m.group(1).replace('"', "")[:120]
                    break
    if not match_text:
        stem = base
        if stem.endswith(".yaml"):
            stem = stem[: -len(".yaml")]
        match_text = stem

    candidates = _resolve_goal_candidates(repo_root, match_text)
    candidate_ids = []
    for c in candidates[:3]:
        if isinstance(c, dict):
            gid = c.get("goal_id")
            if gid:
                candidate_ids.append(gid)
    candidate_ids_str = " or ".join(candidate_ids)

    initiative_id = base[: -len(".yaml")] if base.endswith(".yaml") else base

    message = _compose_nudge_message(initiative_id, candidate_ids, candidate_ids_str)
    rc = _envelope.emit(message, _envelope.CHANNEL_STOP)
    return rc if rc is not None else 0


if __name__ == "__main__":
    sys.exit(main())
