#!/usr/bin/env python3
"""PreToolUse(Agent) naked-Python REROUTE-gate dispatcher.

Replaces the former bash nudge-foreground-agent-dispatch.sh PreToolUse
registration (background-by-default enforcement for Agent tool dispatches)
with ONE python3 hook entry -- zero Git-Bash cold-start per Agent dispatch
on Windows (each bash.exe spawn costs 200-500ms; this is the whole point).

The doctrine plane owns only this thin PLUMBING shim (DR-047 transport-seam carve-out): resolve
the claude-klabauter engine, hand it the mapped params, relay its stdout. Claude-klabauter owns the
REROUTE-gate LOGIC (coordinator_core.hooks.nudge_foreground_agent_dispatch,
registered under the JSON-RPC method hooks.nudge_foreground_agent_dispatch).
The engine is imported and run IN-PROCESS via coordinator_core.ipc.dispatch_message
-- no bash, no python3 -m subprocess re-spawn -- so a whole PreToolUse fire pays
exactly one Python interpreter start.

Contract (mirrors the bash hook it replaces -- nudge-foreground-agent-dispatch.sh):
  stdin   -- PreToolUse JSON (tool_name, tool_input with run_in_background,
             session_id, cwd, ...)
  stdout  -- one hookSpecificOutput JSON envelope on a foreground Agent
             dispatch (normally updatedInput, rewriting the call to
             run_in_background:true; permissionDecision:deny only on the
             engine's no-rewrite-possible fallback); NOTHING otherwise
             (silent pass)
  exit 0  -- always (ALLOW/DENY/REWRITE conveyed via stdout, never exit code).
             Unchanged by the fail-closed narrowing below: a blocked dispatch
             is still a deny ENVELOPE on stdout, never a non-zero exit. A
             PreToolUse hook that exits non-zero on a transport hiccup breaks
             the session rather than the one dispatch.

stdin -> params mapping (op scope common_dir -- REQUIRES _origin_worktree;
see coordinator_core/ipc.py _OP_KEY_SCOPE for hooks.nudge_foreground_agent_dispatch
== common_dir. This is the ONE place this stub diverges from the W2 reference
stub's none-scope assumption -- W2-stub-contract.md sec 3 flags exactly this risk
for the analogous common_dir-scoped bookkeeping ops; nudge_foreground_agent_dispatch
is scoped the same way, so the divergence is confirmed against ipc.py directly,
not assumed from the reference).

The handler (coordinator_core/hooks/nudge_foreground_agent_dispatch.py) reads,
via _payload.field(params, key):
    tool_name          <- flattened stdin top-level tool_name
    run_in_background   <- flattened stdin tool_input.run_in_background
    session_id          <- flattened stdin top-level session_id

and, read RAW (not via field(), which stringifies):
    tool_input          <- stdin tool_input, forwarded whole and unflattened

The raw tool_input is what the engine rewrites: it answers a foreground
dispatch with hookSpecificOutput.updatedInput, and updatedInput REPLACES the
tool's argument object rather than merging into it, so a partial forward would
drop prompt/subagent_type. It is passed IN ADDITION to the flattened scalars
above, not instead of them -- the flattened run_in_background is still the
field the gate branches on.

Flattened mirrors the retired bash sibling's advisory_flatten_params
contract: output = (payload minus tool_input) plus
(payload.tool_input or empty) -- tool_input keys are merged UP to top level
(and win over any same-named top-level key), because run_in_background lives
inside tool_input in the raw hook payload but the op handler reads it as a
flat top-level params key via field(). Missing/absent keys map to empty string --
_payload.field() already treats empty string (and None) as ABSENT.

_origin_worktree is populated from the stdin cwd field, falling back to this
process's own os.getcwd() when the payload omits it -- the same fact from another
source, still plumbing. That fallback exists because the silent no-op W2-stub-
contract.md sec 3 warns about for common_dir-scoped ops was REAL here and was a
foreground leak: a cwd-less payload used to produce no _origin_worktree ->
INVALID_PARAMS -> result None -> a relay that treated that identically to a clean
no-advisory pass. The gate simply switched itself off, invisibly, on any payload
without cwd. Two changes closed it (2026-07-29): the cwd fallback above, so the
ENGINE still adjudicates (reroute + escape hatch honoured) rather than degrading
at all; and, underneath it, `result is None` is no longer conflated with `{}` --
`{}` is the engine deliberately answering PASS, None means it never adjudicated,
and only the latter drops to the fail-closed/fail-open split below.
Raising still isn't the answer -- that would brick the hook on a cwd-less payload
-- but neither is passing silently.

Graceful degradation -- NARROWED 2026-07-29 (PM ruling), was unconditionally
fail-open. Any failure to resolve/import/run the claude-klabauter engine still degrades
without bricking the session, but the degraded answer now depends on whether
this shim can tell, from the payload alone (plus a best-effort, no-subprocess
read of the durable calibration marker -- see below), that it is looking at a
deliberately-foreground Agent dispatch (`_is_deliberate_foreground`):

  - CAN tell (tool_name == "Agent" AND run_in_background present-and-false)
    -> emit a local deny envelope. Fail CLOSED.
  - CAN also tell (tool_name == "Agent" AND run_in_background absent AND
    the session's durable `.harness-bg-capable` marker exists) -> the
    calibrated-absent case: same fail CLOSED. This is the ONE hole review
    Finding 1 (2026-07-29) named -- the engine-down leg could not previously
    see calibration state at all, so a session already proven to expose
    run_in_background silently PASSed foreground the moment the engine went
    down, exactly the case claude-klabauter's own D7b durable marker was written to
    close on the engine-up path. Closing it here needs no engine: the shim
    already knows cwd/session_id at parse time, so it can resolve the git dir
    itself (no subprocess -- see `_resolve_git_dir`) and stat the same marker
    file claude-klabauter's `_bg_capable_path` writes/reads.
  - CANNOT tell (any other tool, absent run_in_background with NO calibration
    marker found or resolvable, unparseable stdin, non-Agent payload) -> exit
    0, no stdout. Fail OPEN, as before -- this is still the brick-proof rule:
    on a build with no such param every dispatch omits it, and denying on
    absence alone would gate every Agent call on the machine.

The PM ruling this encodes: "I don't want to let foreground agents get through,
I'd rather block than let that happen." The cost of the old blanket fail-open is
not a slower dispatch -- a foreground subagent LOCKS THE EM IN PLACE. With one
outstanding, the EM cannot issue the rest of its wave, reconcile plans, or answer
the PM until the agent returns or the PM manually backgrounds it (ctrl+b). A gate
that silently disables itself on a transport hiccup hands back exactly the state
it exists to prevent, invisibly.

The fail-open half is preserved precisely where blocking would be reckless: a
shim that denies what it cannot identify denies everything. So the fail-closed
branch is gated on the ONE payload shape that needs no engine to classify.
Note this diverges from preuse-write-dispatch.py._resolve_claude_klabauter_root, which
stays unconditionally fail-open -- the lockstep is now deliberate-partial, not
total: that hook gates writes (blocking a write on a missing engine is pure
obstruction), this one gates a dispatch mode whose failure state is a wedged EM.

NOTE (2026-07-31, single-emitter fold-in): this script is DEREGISTERED from
hooks.json's Agent PreToolUse matcher -- its own reroute (updatedInput) used
to race enforce-agent-dispatch-mode.py's updatedInput on that SAME matcher,
the last-writer-wins clobber a 2026-07-30 revert misdiagnosed as
"updatedInput does not bind run_in_background". The reroute decision this
shim relays now lives as a byte-faithful pure-Python port in
_foreground_dispatch_strip.py, called directly by enforce-agent-dispatch-
mode.py (Concern G) as the matcher's sole live updatedInput emitter. This
file and the engine op it calls stay on disk as the algorithm's reference
implementation, each still exercised by its own dedicated test suite via
direct invocation/subprocess -- neither is wired into any live hooks.json
matcher any more.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path


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


_TRANSPORT_DENY_MSG = (
    "FOREGROUND AGENT DISPATCH BLOCKED — retry with `run_in_background: true`. "
    "Coordinator default is backgrounded dispatch: a foreground subagent locks the EM "
    "in place until it returns. That is not merely slower — with one foreground dispatch "
    "outstanding the EM cannot issue the REST of its wave, reconcile plans, or answer the "
    "PM until the agent finishes or the PM manually backgrounds it (ctrl+b). "
    "NOTE: the claude-klabauter engine was unreachable for this call, so this gate could not consult "
    "the session escape hatch (.foreground-ok) and could not auto-reroute you to background "
    "as it normally would. Reissue with `run_in_background: true`. If you need the hatch, "
    "the engine has to be repaired first — check that claude-klabauter resolves on this machine."
)


def _git_root(start: str) -> str:
    """No-subprocess walk-up from `start` looking for a directory holding a
    `.git` entry (directory or file) -- same idiom as `offer-exploration-
    tier-dispatch.py`'s helper of the same name. Fails open to "" on any
    error."""
    try:
        if not isinstance(start, str) or not start:
            return ""
        cur = os.path.abspath(start)
        while True:
            if os.path.exists(os.path.join(cur, ".git")):
                return cur
            parent = os.path.dirname(cur)
            if parent == cur:
                return ""
            cur = parent
    except Exception:
        return ""


def _resolve_git_common_dir(git_root: str) -> str:
    """Resolve the git COMMON dir for `git_root` without spawning a
    subprocess. Fails open to "" on any error, including the plain-clone
    case where `.git` is simply a directory.

    THIS IS A VERBATIM COPY of the canonical helper in
    `offer-exploration-tier-dispatch.py` (hooks are standalone scripts and
    cannot import each other). See that copy's docstring for the full list
    of sibling duplicates and the rationale for keeping every copy in step
    -- a divergence would mean different hooks resolve the same session's
    bookkeeping directory to different locations under a worktree, silently
    breaking correlation between them."""
    try:
        dot_git = os.path.join(git_root, ".git")
        if os.path.isdir(dot_git):
            return dot_git
        if os.path.isfile(dot_git):
            with open(dot_git, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read().strip()
            if not text.startswith("gitdir:"):
                return ""
            gitdir_value = text[len("gitdir:"):].strip()
            git_dir = (
                gitdir_value
                if os.path.isabs(gitdir_value)
                else os.path.normpath(os.path.join(git_root, gitdir_value))
            )
            if not os.path.isdir(git_dir):
                return ""
            commondir_file = os.path.join(git_dir, "commondir")
            if os.path.isfile(commondir_file):
                with open(commondir_file, "r", encoding="utf-8", errors="replace") as fh:
                    common_value = fh.read().strip()
                if not common_value:
                    return git_dir
                return (
                    common_value
                    if os.path.isabs(common_value)
                    else os.path.normpath(os.path.join(git_dir, common_value))
                )
            return git_dir
        return ""
    except Exception:
        return ""


def _resolve_git_dir(cwd: str) -> str | None:
    """Best-effort git COMMON-dir resolution from `cwd`, WITHOUT spawning a
    subprocess.

    Walks `cwd` and its parents to find the directory holding a `.git` entry
    (`_git_root`), then resolves that entry to the git COMMON dir
    (`_resolve_git_common_dir`) -- following a worktree's `gitdir: <path>`
    pointer AND its `commondir` indirection, never stopping at the
    worktree's own PRIVATE dir. Returns None on any failure to resolve (no
    `.git` found, unreadable pointer/commondir file, permission error) so
    callers degrade to the same fail-open answer as an unreachable engine --
    this is a best-effort read, not a replacement for git itself.
    """
    if not cwd:
        return None
    try:
        start = Path(cwd).resolve()
    except Exception:
        return None
    git_root = _git_root(str(start))
    if not git_root:
        return None
    common_dir = _resolve_git_common_dir(git_root)
    return common_dir or None


def _bg_capable_marker_path(git_dir: str, session_id: str) -> Path:
    """Same durable calibration marker claude-klabauter's `_bg_capable_path` writes/reads.

    Kept as a named helper (not a bare string) precisely so a rename on either side has a
    findable second site -- see coordinator_core/hooks/nudge_foreground_agent_dispatch.py
    `_bg_capable_path`, the other half of this agreement.
    """
    return Path(git_dir) / "coordinator-sessions" / session_id / ".harness-bg-capable"


def _is_deliberate_foreground(flat: dict, cwd: str | None = None) -> bool:
    """True iff this payload is UNAMBIGUOUSLY a deliberately-foreground Agent dispatch.

    `run_in_background` present and false on an Agent call is the one case that needs no
    engine and no filesystem read to classify -- always fail closed on it.

    An absent key is the engine's calibration question by default: an uncalibrated absent
    key is NOT deliberate foreground (that is the brick-proof rule -- a build with no such
    param omits it on every dispatch, and denying on absence alone would gate every Agent
    call on the machine). But a session already CALIBRATED -- proven, by an earlier
    present-key dispatch, to expose run_in_background -- reading absent now IS a deliberate
    foreground choice, and that fact is readable without the engine: it is exactly the
    durable `.harness-bg-capable` marker claude-klabauter's D7b write leaves behind (Finding 1,
    2026-07-29). `cwd` is used only for this best-effort, no-subprocess marker lookup; an
    unparseable payload, a missing cwd/session_id, or an unresolvable git dir all fall
    through to the same fail-open False a build-without-the-param would get.
    """
    if flat.get("tool_name") != "Agent":
        return False
    rib = flat.get("run_in_background")
    if rib is False or (isinstance(rib, str) and rib.strip().lower() == "false"):
        return True
    if rib is not None and rib != "":
        return False  # present-and-true (or unrecognized truthy value) -- never foreground
    session_id = flat.get("session_id")
    if not (isinstance(session_id, str) and session_id and cwd):
        return False
    git_dir = _resolve_git_dir(cwd)
    if not git_dir:
        return False
    try:
        return _bg_capable_marker_path(git_dir, session_id).exists()
    except Exception:
        return False


def _deny_envelope() -> str:
    return json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": _TRANSPORT_DENY_MSG,
        }
    })


def main() -> int:
    raw = sys.stdin.read()

    # Parse BEFORE the engine-resolution legs: every fail-closed branch below needs to know
    # whether this is a deliberate foreground dispatch, and that answer lives in the payload.
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}

    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}
    flat = {k: v for k, v in payload.items() if k != "tool_input"}
    flat.update(tool_input)

    # Resolved up-front (not just for the engine leg's _origin_worktree below): the
    # calibrated-absent leg of _is_deliberate_foreground needs it too, to do its own
    # no-subprocess git-dir/marker lookup when the engine turns out to be unreachable.
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        try:
            cwd = os.getcwd()
        except Exception:
            cwd = ""

    foreground = _is_deliberate_foreground(flat, cwd)

    def _fail() -> int:
        """Engine unreachable: deny a known foreground dispatch, pass anything else."""
        if foreground:
            sys.stdout.write(_deny_envelope())
            sys.stdout.write("\n")
        return 0

    root = _resolve_claude_klabauter_root()
    if not root:
        return _fail()  # claude-klabauter unresolvable on this machine

    if root not in sys.path:
        sys.path.insert(0, root)

    try:
        from coordinator_core.hooks import nudge_foreground_agent_dispatch as _op  # noqa: F401
        from coordinator_core.ipc import dispatch_message
    except Exception:
        return _fail()  # engine unimportable

    params = {
        "tool_name": flat.get("tool_name", ""),
        "run_in_background": flat.get("run_in_background", ""),
        "session_id": flat.get("session_id", ""),
        # Forwarded UNFLATTENED and complete: the engine answers a foreground dispatch by
        # rewriting it (hookSpecificOutput.updatedInput), and updatedInput REPLACES the
        # tool's argument object rather than merging into it -- so the engine needs every
        # original key, not the three flattened scalars above. Withholding it is not a
        # silent no-op: the engine falls back to its legacy deny envelope.
        "tool_input": tool_input,
    }

    # _origin_worktree: the op is common_dir-scoped, so an unresolvable worktree means the
    # engine never runs its business logic at all. `cwd` was already resolved above (with
    # the same os.getcwd() fallback) so the ENGINE decides (reroute + escape-hatch honoured)
    # from the identical fact this shim's own fail-closed leg would fall back to.
    msg = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "hooks.nudge_foreground_agent_dispatch",
        "params": params,
        "_origin_worktree": cwd,
    }

    try:
        response = asyncio.run(dispatch_message(msg))
    except Exception:
        return _fail()  # any engine failure

    result = response.get("result") if isinstance(response, dict) else None
    if result is None:
        # No result object at all == the engine did not adjudicate (INVALID_PARAMS,
        # unregistered op, malformed response). NOT the same as {}, which is the engine
        # deliberately saying PASS -- conflating the two is what let a foreground dispatch
        # through unremarked.
        return _fail()
    if result:
        sys.stdout.write(json.dumps(result))
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
