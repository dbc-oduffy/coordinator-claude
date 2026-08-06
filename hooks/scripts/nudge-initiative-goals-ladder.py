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

Candidate-resolution seam: claude-klabauter's `goal.match_candidates` op
(coordinator_core/ops/goals_match.py — already exists, so this port is the "thin
DoE stub" branch of the migration brief, not a from-scratch reimplementation).
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
    from _engine_root import resolve_claude_klabauter_root as _resolve_claude_klabauter_root  # noqa: E402
except Exception:
    # Defensive fallback -- a hook script copied/deployed WITHOUT its
    # sibling _engine_root.py (e.g. an isolated test harness, or a
    # partial deploy) must still fail-open rather than crash on import.
    def _resolve_claude_klabauter_root() -> str | None:
        return None

try:
    import _message_envelope as _envelope  # noqa: E402
except Exception:
    # Defensive fallback -- mirrors the `_resolve_claude_klabauter_root` fallback
    # above: a hook script copied/deployed WITHOUT its `_message_envelope.py`
    # sibling (e.g. `test_family_d_fail_open_coverage.py`'s isolated-copy
    # harness, which copies only this file plus `_engine_root.py`) must
    # still compose and emit its nudge rather than crash on import.
    # Reimplements only the exact shape this hook uses -- not the full
    # envelope surface (no measurement-mode fd-3 hook, no alternative-shape
    # validation) -- since a copied-sibling deploy is never what C1's
    # in-process measurement harness runs against (that harness imports the
    # real hook from its real on-disk location, alongside its real
    # `_message_envelope.py`).
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
            # Review: code-reviewer, Finding 2/6 -- .buffer.write bypasses
            # Python's Windows text-mode newline translation (stderr in
            # text mode would silently turn every LF into CRLF, breaking
            # byte-fidelity with the bash oracle's stderr output). This
            # fallback copy doesn't inherit the real envelope's fix (it
            # exists only for an isolated-copy deploy that lacks
            # `_message_envelope.py`, per the comment above), so it must
            # carry the fix independently.
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


#: See state/relocations/guard-message-cap/nudge-initiative-goals-ladder.py.md
#: for the full explanation this hook's message used to spell out inline
#: (docs/plans/2026-08-02-guard-message-character-cap.md § C6).
_WIKI_ANCHOR = (
    # Review: code-reviewer -- bare fragment produced an unresolvable
    # `render()` citation. Full path matches every other converted hook.
    "coordinator/docs/wiki/guard-message-concision.md"
    "#initiative-goals-nudge-remedies"
)


def _resolve_goal_candidates(repo_root: str, text: str) -> list:
    """In-process call into claude-klabauter's `goal.match_candidates` op.

    Fail-open at every step (unresolvable seam / import error / handler
    exception) -> [] — a nudge with no suggestions is still a valid, safe
    nudge.
    """
    if not text:
        return []

    root = _resolve_claude_klabauter_root()
    if not root:
        return []

    # STOP-FAMILY-RUNNER-CONTRACT clause 8 (sys.path ordering): append,
    # never insert at index 0 -- the hooks dir (inserted at the top of this
    # module) must stay ahead of the sibling engine root on sys.path.
    if root not in sys.path:
        sys.path.append(root)

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

        # A-F2 (P2 C8): bound the goal-match op with its own timeout,
        # independent of the two _git_toplevel calls above -- fail-open to
        # [] on timeout rather than let an unbounded op exhaust the
        # remainder of this hook's 10s hooks.json budget.
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
    """Back-compat shim for `message_measurement_harness.
    _adapt_nudge_initiative_goals_ladder`, which calls this exact name and
    measures its raw string return directly (not via the shared harness's
    `_capture_envelope_messages` context, unlike this wave's other
    conversions) -- so it must keep returning a plain string. Returns
    `_compose_nudge_message(...).prose`: the counted diagnosis only, the
    same value the ceiling/median/p90 legs measure. `main()` itself calls
    `_compose_nudge_message` directly and emits the fuller Message (prose +
    alternative + anchor) via `_message_envelope.emit`."""
    return _compose_nudge_message(initiative_id, candidate_ids, candidate_ids_str).prose


def main() -> int:
    # -- Silence switch for autonomous mode --------------------------------
    if os.environ.get("COORDINATOR_INITIATIVE_GOALS_NUDGE_OFF", "0") == "1":
        return 0

    # -- Safe stdin read ------------------------------------------------------
    try:
        raw = sys.stdin.read()
    except Exception:
        raw = ""

    # -- Parse fields (direct json.loads -- always available in naked Python,
    #    the strongest tier of the bash oracle's jq/python3/sed ladder) --------
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
            # Mirrors `head -60` (first 60 lines of the extracted content).
            content = "\n".join(content_raw.splitlines()[:60])

    # -- Only fire on Write or Edit -------------------------------------------
    if tool_name not in ("Write", "Edit"):
        return 0

    if not file_path:
        return 0

    file_path_norm = file_path.replace("\\", "/")

    # -- Only fire on state/initiatives/*.yaml paths --------------------------
    base = os.path.basename(file_path_norm)
    dirpart = file_path_norm[: -len(base)] if base else file_path_norm
    is_initiative_yaml = base.endswith(".yaml") and (
        dirpart.endswith("/state/initiatives/") or dirpart == "state/initiatives/"
    )
    if not is_initiative_yaml:
        return 0

    # -- First-class suppression: initiative already has goals ----------------
    # Matches: "goals:" followed by a non-empty value on the same line, OR a
    # list item on the next line starting with "  -" (YAML list form). A bare
    # "goals: null", "goals: []", or absent "goals:" is treated as empty --
    # trigger the nudge.
    if content:
        lines = content.split("\n")

        # Inline value form: goals: something-non-empty (not null, not [], not "").
        inline_re = re.compile(r"^goals:[ \t]*[^ \t#\[]")
        goals_line_re = re.compile(r"^goals:")
        for line in lines:
            if inline_re.match(line):
                goals_val = goals_line_re.sub("", line, count=1)
                goals_val = goals_val.lstrip(" \t")
                if goals_val not in ("null", "", "[]", "~"):
                    return 0  # non-empty value -- suppress
                break  # only the first "goals:" line is considered (head -1)

        # List form: goals: followed by a "  - " item on the next line.
        list_item_re = re.compile(r"^[ \t]+-")
        for i, line in enumerate(lines):
            if goals_line_re.match(line):
                if i + 1 < len(lines) and list_item_re.match(lines[i + 1]):
                    return 0
                break  # -A1 semantics: only the (first) matched block matters here

    # -- Resolve repo root for goals/ lookup -----------------------------------
    # Prefer git rev-parse from the file's directory; fall back to PWD.
    repo_root = ""
    dir_of_file = os.path.dirname(file_path_norm)
    if dir_of_file and os.path.isdir(dir_of_file):
        repo_root = _git_toplevel(dir_of_file)
    if not repo_root:
        repo_root = _git_toplevel(os.getcwd())
    if not repo_root:
        # Cannot resolve repo -- fail-open: no nudge (can't check goals/ either).
        return 0

    # -- Suppress if no goals exist under state/goals/ -------------------------
    goals_dir = Path(repo_root) / "state" / "goals"
    if not goals_dir.is_dir():
        return 0
    goal_count = sum(1 for f in goals_dir.glob("*.yaml") if f.is_file())
    if goal_count == 0:
        return 0

    # -- Derive match text from the initiative label/description --------------
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
        # Fall back to filename stem (e.g. "my-initiative" from my-initiative.yaml).
        stem = base
        if stem.endswith(".yaml"):
            stem = stem[: -len(".yaml")]
        match_text = stem

    # -- Resolve candidate goal-ids ---------------------------------------------
    candidates = _resolve_goal_candidates(repo_root, match_text)
    candidate_ids = []
    for c in candidates[:3]:
        if isinstance(c, dict):
            gid = c.get("goal_id")
            if gid:
                candidate_ids.append(gid)
    candidate_ids_str = " or ".join(candidate_ids)

    # -- Build the offer-shaped nudge message ------------------------------------
    initiative_id = base[: -len(".yaml")] if base.endswith(".yaml") else base

    message = _compose_nudge_message(initiative_id, candidate_ids, candidate_ids_str)
    rc = _envelope.emit(message, _envelope.CHANNEL_STOP)
    return rc if rc is not None else 0


if __name__ == "__main__":
    sys.exit(main())
