#!/usr/bin/env python3
"""SubagentStop Stage-1 detect+record shim -- zero-tool-use subagent detection.

This doctrine-plane repo owns only this thin PLUMBING shim (DR-047 transport-seam carve-out): parse
the raw SubagentStop payload, gate on agent_type and this-session ownership,
map the payload to the pinned IPC params, and relay to the claude-klabauter engine op
`hooks.subagent_zero_tool_use` (module `coordinator_core.hooks.
subagent_zero_tool_use`, NOT built here). The engine owns the decision LOGIC:
opening `agent_transcript_path`, counting `tool_use` blocks, and resolving
zero-vs-unknown (a missing/unreadable transcript resolves to UNKNOWN, never
zero -- AC1). This script never opens a transcript and never counts anything;
grep of this file for transcript-open/count logic must return nothing (AC7,
DR-047 boundary).

REVIEW-MARK FOLD: this shim ALSO relays `hooks.subagent_review_mark`
(engine module `coordinator_core.hooks.subagent_review_mark`), which derives
a commit-ledger review mark from a finishing reviewer's own `reviewed_range`
findings. Folded here rather than given its own `SubagentStop` registration
in `hooks.json`, and the reason is a cost this file's own registration
comment already prices: a second entry buys a second permanent `python3`
cold start (~642ms on the reference Windows machine) on EVERY subagent stop,
fleet-wide, including every install with no engine present for either op to
resolve against. Folding adds one more op to a call that already pays that
start -- not a second mechanism. Both ops are `common_dir` scoped, so the
single shared `origin_worktree` stamped across the batch keys both correctly.

The mark op is NOT gated shim-side on the finishing agent being a reviewer.
It gates itself, against the closed reviewer vocabulary the engine already
owns (`review_trail_write._DELEGATE_REVIEWERS`). Re-stating that vocabulary
here would fork it across the DR-047 seam and drift silently the first time
the engine edits its own list; the wasted call for a non-reviewer is one
in-process op dispatch, no spawn.

Emits NOTHING on any path (DEC-4): a SubagentStop emission is provably
invisible to the EM -- plain stdout at exit 0 goes to the debug log only, and
even `hookSpecificOutput.additionalContext` on SubagentStop feeds the
SUBAGENT's own context, not the parent's. The engine op response IS the
durable-record write; this shim's product is that disk-append side-effect,
not stdout. Nothing is written to stderr on any path either -- stderr flags a
hook as failed even at exit 0 (AC5a). Stage 2 (a separate script, C8's fold
into `runtime-tripwire-em-check.py`) is what surfaces a written record to the
EM, on a later `UserPromptSubmit` turn.

Contract:
  stdin   -- SubagentStop JSON (session_id, agent_id, agent_type,
             agent_transcript_path, transcript_path, hook_event_name, cwd, ...)
  stdout  -- NOTHING, ever (DEC-4)
  stderr  -- NOTHING, ever, including every failure path (AC5a)
  exit 0  -- always (AC6); an unresolvable engine is silent, not fatal

Ordered gates (order is load-bearing, not stylistic):
  1. agent_type absent/empty -> return 0 silently, BEFORE any other work
     (AC2). No code exemplar in this repo implements this gate --
     `track-dispatched-agents.py` gates on `tool_name == "Agent"`, not
     `agent_type`; `agent-completion-log.py` reads `subagent_type` into
     params but never gates on it. Authored fresh from
     `coordinator/docs/hook-authoring-notes.md` § "SubagentStop fires for
     every subagent -- gate on agent_type first". Two reasons this must be
     first: empty-agent_type events are internal helper agents whose
     transcripts never exist, and an untagged emission in the return channel
     can replace an unrelated subagent's deliverable.
  2. Own-session filter (AC4/DEC-3): this hook fires for PEER sessions'
     subagents too. Read this session's `dispatched-agents.txt` under
     `.git/coordinator-sessions/<session_id>/` and require the arriving
     `agent_id` to be a member; non-member -> return 0. Reuses the sanctioned
     shared TSV oracle (`coordinator-tripwires.md` § RUNTIME-TRIPWIRE;
     `hook-best-practices.md`'s em-session-id.txt -> dispatched-agents.txt
     lookup chain) rather than inventing a new sentinel family.

AC10 -- THE hardest requirement in this file: read `agent_transcript_path`
from the payload and pass ONLY that value as the op's transcript-path param.
The SAME payload also carries `transcript_path` -- the PARENT/calling
session's transcript, never the subagent's own. Reading it (even as an `or`
fallback) is a false-negative generator, not a loud failure: the parent
transcript is a real, valid, tool-call-rich JSONL, so the engine would count
the PARENT's tool calls and silently report health for a subagent that never
ran -- the exact inversion of every other failure mode here, which all err
toward UNKNOWN. See the plan's Pinned contract, Stage 1 section, for the
empirical capture confirming both fields are present simultaneously on every
real payload.

No separate sentinel (integration fix, this pass): the landed engine op
appends every record straight to its own durable store --
`git_common_dir(repo_root)/coordinator-sessions/<session_id>/
subagent-zero-tool-use.jsonl` -- which IS the append-only signal Stage 2
stats before deciding whether to pay for an engine round-trip. This shim
touched a redundant sibling sentinel in an earlier pass; that sentinel and
the store could name-drift (each side of the seam authored in parallel
guessed a different filename, silently), so it was removed rather than
merely renamed -- one artifact, one writer (the engine op), one reader
(Stage 2's own stat call). This is deliberate, not an omission: this shim
now has NO local filesystem write of its own at all.

DELIBERATE DIVERGENCE from the plan's C1 Task body (step 6, which
imperatively required touching a per-session "has unsurfaced" sentinel
file): dropped, not just re-shaped. This is a permitted divergence, not an
undocumented one -- the plan's own Pinned contract names its C8 read as
"the per-session sentinel C1 touches, or the durable-record store directly
if no sentinel convention is pinned yet by the C5 memo," and no sentinel
convention was ever pinned, so C8/Stage 2 falls to the durable-record-store
branch of its own stated fallback. Flagged here (code-reviewer Finding 3)
because the plan's Task-list prose alone, read without this docstring,
would still lead a reader to expect a sentinel file that was never built.

Portability note: `git_root + ".git"` is not the git COMMON dir -- they
coincide in an ordinary clone but diverge in a worktree, where `.git` is a
FILE (a `gitdir:` pointer), not a directory. `_resolve_git_common_dir` below
resolves the real common dir without a subprocess spawn (this hook fires on
every `SubagentStop`, and a `git` subprocess spawn on that cadence is a
correctness/performance defect on the Windows-primary fleet, not a cosmetic
cost). A byte-identical copy of this helper lives in
`runtime-tripwire-em-check.py` -- hooks are standalone scripts and cannot
import each other, so the duplication is the existing idiom here, not an
oversight. Keep the two copies in step: a divergence would mean Stage 1's
own-session filter and Stage 2's store/cursor paths resolve to different
directories under a worktree, silently breaking correlation between them.
"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
from pathlib import Path
from typing import Any


# Path-traversal guard for session_id / agent_id before they are used to
# build filesystem paths -- mirrors runtime-tripwire-em-check.py's
# _ID_CHARSET_RE.
_ID_CHARSET_RE = re.compile(r"^[A-Za-z0-9_@-]+$")


def _read_stdin(timeout: float = 2.0) -> str:
    """Bounded stdin read (Windows hang guard) -- shape copied from
    `track-dispatched-agents.py:107-127` / `runtime-tripwire-stop-watcher.py`.

    A bare `sys.stdin.read()` blocks forever if the harness never closes
    stdin's write end (observed Windows failure mode). Falls back to "" on a
    2s join timeout -- the same fail-open value a JSON-decode failure already
    produces.
    """
    box = {"data": ""}

    def _read() -> None:
        try:
            box["data"] = sys.stdin.read()
        except Exception:
            box["data"] = ""

    t = threading.Thread(target=_read, daemon=True)
    t.start()
    t.join(timeout)
    return box["data"]


_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)
try:
    from _engine_root import resolve_claude_klabauter_root as _resolve_claude_klabauter_root  # noqa: E402
except Exception:
    # Defensive fallback -- a hook script copied/deployed WITHOUT its
    # sibling _engine_root.py (e.g. an isolated test harness, or a partial
    # deploy) must still fail-open rather than crash on import.
    def _resolve_claude_klabauter_root() -> str | None:
        return None
try:
    from _git_common_dir import resolve_git_common_dir as _resolve_git_common_dir  # noqa: E402
except Exception:
    # Defensive fallback -- a deploy missing its sibling _git_common_dir.py
    # must still fail open (empty common dir -> callers skip) rather than
    # crash on import.
    def _resolve_git_common_dir(git_root: str) -> str:
        return ""


def _git_root(start: str) -> str:
    """Resolve the git root by walking up from `start` looking for a `.git`
    entry (dir or file), without spawning a subprocess. Fail-open to "" on
    any error.

    Review: code-reviewer -- Findings 1+2. This replaces a prior
    `git rev-parse --show-toplevel` subprocess spawn, which (a) paid a
    per-`SubagentStop`-fire `git`/`git.exe` fork on the Windows-primary
    fleet, uncredited against this module's own "correctness/performance
    defect" framing for exactly that class of cost (see the module
    docstring's `_resolve_git_common_dir` paragraph), and (b) trusted the
    hook process's ambient OS cwd rather than the payload's own `cwd` field
    -- an assumption this worktree-correctness-focused file otherwise
    refuses to make silently elsewhere. Walking up from `start` (the
    payload's own `cwd`) mirrors `git rev-parse --show-toplevel`'s
    directory-walk algorithm closely enough for this hook's purposes (no
    `GIT_CEILING_DIRECTORIES`/submodule-boundary handling needed here) while
    eliminating both problems: zero subprocess spawns, and `git_root` now
    reflects the SUBAGENT's own worktree (via `payload["cwd"]`), not
    whatever directory the hook process happened to be launched from.

    `start` is preferred when it is a non-empty string, because it names the
    SUBAGENT's own worktree (`payload["cwd"]`) rather than wherever the hook
    process happened to be launched from. But the governing plan
    (`docs/plans/2026-07-25-zero-tool-use-detection.md:562`) itself
    anticipates a `SubagentStop` payload that omits `cwd` -- treating a
    missing `start` as "no git root" would silently drop every such
    detection (fail-open reading as healthy, the exact failure mode this
    feature exists to catch), so an empty/non-string `start` falls back to
    `os.getcwd()` -- the SAME resolution the prior subprocess-based
    implementation used unconditionally. That fallback call is wrapped by
    this function's own outer `try` (an `os.getcwd()` on a deleted cwd can
    raise), so the whole path stays fail-open to "" on any error.
    """
    try:
        base = start if isinstance(start, str) and start else os.getcwd()
        if not base:
            return ""
        cur = os.path.abspath(base)
        while True:
            if os.path.exists(os.path.join(cur, ".git")):
                return cur
            parent = os.path.dirname(cur)
            if parent == cur:
                return ""
            cur = parent
    except Exception:
        return ""


def _is_dispatched_this_session(git_root: str, session_id: str, agent_id: str) -> bool:
    """AC4/DEC-3 own-session filter.

    Reads `.git/coordinator-sessions/<session_id>/dispatched-agents.txt` (the
    sanctioned shared 4-column TSV oracle -- `agentId | model | subagent_type
    | dispatched-at`) and returns True only when `agent_id` appears as the
    first column of some row. Any failure to resolve git_root, read the file,
    or parse a row fails CLOSED here (not a member) -- this filter's whole
    purpose is to exclude peer-session agents, so an unreadable ledger must
    not be treated as "everything belongs to me."
    """
    if not git_root or not session_id or not agent_id:
        return False
    if not _ID_CHARSET_RE.match(session_id):
        return False

    common_dir = _resolve_git_common_dir(git_root)
    if not common_dir:
        return False

    dispatch_file = os.path.join(
        common_dir, "coordinator-sessions", session_id, "dispatched-agents.txt"
    )
    try:
        if not os.path.isfile(dispatch_file):
            return False
        with open(dispatch_file, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                cols = line.rstrip("\n").split("\t")
                if cols and cols[0] == agent_id:
                    return True
    except Exception:
        return False
    return False


def main() -> int:
    raw = _read_stdin()

    try:
        payload: Any = json.loads(raw) if raw else {}
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}

    # --- Gate 1 (AC2): agent_type first, before any other work. ---
    agent_type = payload.get("agent_type")
    if not isinstance(agent_type, str) or not agent_type:
        return 0

    session_id = payload.get("session_id")
    if not isinstance(session_id, str):
        session_id = ""
    agent_id = payload.get("agent_id")
    if not isinstance(agent_id, str):
        agent_id = ""

    cwd = payload.get("cwd")
    if not isinstance(cwd, str):
        cwd = ""

    # --- Gate 2 (AC4/DEC-3): own-session filter. `_git_root` resolves from
    # the payload's own `cwd` (the subagent's worktree), not ambient process
    # cwd -- see `_git_root`'s docstring (Findings 1+2). ---
    git_root = _git_root(cwd)
    if not _is_dispatched_this_session(git_root, session_id, agent_id):
        return 0

    # --- AC10: agent_transcript_path is authoritative; transcript_path is a
    # decoy (the PARENT session's transcript) and must never be read here,
    # not even as a fallback. ---
    agent_transcript_path = payload.get("agent_transcript_path")
    if not isinstance(agent_transcript_path, str):
        agent_transcript_path = ""

    hook_event_name = payload.get("hook_event_name")
    if not isinstance(hook_event_name, str):
        hook_event_name = ""

    # Review: code-reviewer -- Finding 5 (defense-in-depth; the resolved
    # function already guarantees fail-open/never-raise per its own
    # docstring, but this matches the belt-and-braces style the rest of
    # this file uses for `_git_root`/`_is_dispatched_this_session`).
    try:
        root = _resolve_claude_klabauter_root()
    except Exception:
        root = None
    if not root:
        return 0  # fail-open -- claude-klabauter unresolvable on this machine

    if root not in sys.path:
        sys.path.insert(0, root)

    try:
        # Importing coordinator_core.hooks.subagent_zero_tool_use triggers
        # the coordinator_core.hooks package __init__ (registers every
        # advisory + bookkeeping op via register_op side-effects at import
        # time) -- one-time-per-invocation cost, in-process, zero subprocess
        # spawns.
        from coordinator_core.hooks import subagent_zero_tool_use as _op  # noqa: F401
        from coordinator_core.ipc import dispatch_ops_from_hook
    except Exception:
        return 0  # engine unimportable -> fail-open

    ops: list[tuple[str, dict]] = [
        (
            "hooks.subagent_zero_tool_use",
            {
                "session_id": session_id,
                "agent_id": agent_id,
                "agent_type": agent_type,
                "agent_transcript_path": agent_transcript_path,
                "hook_event_name": hook_event_name,
            },
        ),
        (
            "hooks.subagent_review_mark",
            {
                "session_id": session_id,
                "agent_id": agent_id,
                "agent_type": agent_type,
                "cwd": cwd,
            },
        ),
        # RECEIVER-STATE FOLD -- the SubagentStop half of the producer trigger
        # the engine's receiver-state sensor has been waiting on. Its Stop half
        # is `receiver-state-sensor.py`, riding the `stop-dispatch.py` fan-in.
        # Folded here for the same reason the review mark is: a third
        # SubagentStop entry in hooks.json would buy a third permanent
        # interpreter cold start on every subagent stop fleet-wide, where an
        # extra tuple in this list adds no process at all.
        #
        # `agent_transcript_path`, NEVER `transcript_path` -- AC10 above binds
        # this op exactly as it binds the zero-tool-use op, and for the same
        # reason: the decoy is the PARENT session's transcript, valid and
        # tool-call-rich, so reading it would write a confident ladder verdict
        # about the wrong session rather than failing loudly.
        #
        # `pid` is omitted (a stop payload carries none, and this hook's own
        # pid is not the session's) and `delegation_evidence` is passed false
        # rather than derived -- the op declines to derive it and the ask to
        # widen it is out to the engine team. Both dispositions, and why
        # neither is a design, are in `receiver-state-sensor.py`'s docstring;
        # the two legs must stay in step, which is why they are pinned to each
        # other by `test_both_receiver_state_legs_pass_the_same_params`.
        (
            "hooks.receiver_state_sensor",
            {
                "session_id": session_id,
                "transcript_path": agent_transcript_path,
                "delegation_evidence": "false",
            },
        ),
    ]

    # dispatch_ops_from_hook builds the envelope itself and omits
    # _origin_worktree when origin_worktree is None/empty, matching this
    # stub's prior isinstance(cwd, str) and cwd guard unchanged. ONE
    # origin_worktree is stamped onto every op's envelope (a shared kwarg,
    # not a per-op field) -- correct here because both ops are common_dir
    # scoped (coordinator_core/op_scopes.py), so both key off the same
    # resolved common dir.
    try:
        # Per-op errors are RETURNED (HookDispatchError instances), never
        # raised, so neither op can suppress the other: on any install whose
        # published engine mirror lags `hooks.subagent_review_mark`, the mark
        # op resolves to a returned METHOD_NOT_FOUND and the zero-tool-use
        # detection it rides with keeps landing untouched. That isolation is
        # the seam's own contract (`coordinator_core.ipc` ::
        # `dispatch_ops_from_hook`, Returns clause plus negative spec), not a
        # local try/except.
        dispatch_ops_from_hook(
            ops,
            origin_worktree=cwd if isinstance(cwd, str) and cwd else None,
        )
    except Exception:
        # Widened from `except HookDispatchError` as part of this fold: any
        # other exception from the dispatch call would have propagated
        # uncaught and violated this file's own exit-0-always invariant.
        return 0  # any engine failure -> fail-open (never brick a tool call)

    # The op response IS the durable-record write (its disk-append
    # side-effect is this shim's entire product) -- no local write of any
    # kind happens here on success or failure. Stage 2 discovers new records
    # by stating the engine's own durable store directly; see this module's
    # docstring for why a separate sentinel was removed rather than kept in
    # step with it.
    return 0


if __name__ == "__main__":
    sys.exit(main())
