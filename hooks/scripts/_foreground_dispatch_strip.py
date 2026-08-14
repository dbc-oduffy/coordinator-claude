"""_foreground_dispatch_strip.py -- shared library, NOT a registered hook.

Single-emitter fold-in (2026-07-31, re-land of the 2026-07-30-reverted
background-by-default reroute): `nudge-foreground-agent-dispatch.py` used to
be independently registered on the `Agent` PreToolUse matcher, relaying
the engine's `coordinator_core.hooks.nudge_foreground_agent_dispatch`
foreground-dispatch reroute op's REROUTE-gate result (a
`hookSpecificOutput.updatedInput` rewriting a foreground
`run_in_background: false` dispatch to `true`). That reroute was reverted
2026-07-30 on the conclusion that `updatedInput` does not bind
`run_in_background` for the `Agent` tool -- a fresh live probe (harness
2.1.220, single emitter, no competitor) disproved that: the EM regained
control 32.3s before the subagent finished, genuinely backgrounded. The real
root cause was that this shim's own `updatedInput` was racing
`enforce-agent-dispatch-mode.py`'s own `updatedInput` on the SAME `Agent`
matcher -- Claude Code runs same-event PreToolUse hooks in parallel with
undefined completion order, and `updatedInput` is last-writer-wins, so
whichever hook finished second silently clobbered the other's rewrite. This
is the identical clobber class `_worktree_isolation_strip.py` (Concern E) and
`_named_dispatch_strip.py` (Concern F) already closed for the worktree-strip
and named-dispatch-strip pairs; this module closes it for the foreground
reroute too, using those fixes as precedent shape.

Fix shape: the foreground-reroute DECISION (this module) is a pure,
side-effect-limited computation -- no stdout, no sys.exit -- that
`enforce-agent-dispatch-mode.py` folds into its own single merged
`updatedInput` (mode elevation + sidecar + contract-blocks + role-framing +
worktree-strip + named-dispatch-strip + foreground-reroute, all layered onto
ONE `merged` dict, ONE emission site, as "Concern G"). `nudge-foreground-
agent-dispatch.py` is DEREGISTERED from `hooks.json`'s `Agent` matcher
entirely -- Agent was its only matcher, so once its decision is folded into
`enforce-agent-dispatch-mode.py`'s single-emitter path there is no live
matcher left where it is a legitimate standalone emitter (same reasoning
Concern F applied to `guard-named-dispatch-tool-restriction.py`). The script
and the engine's own `coordinator_core.hooks.nudge_foreground_agent_dispatch`
op stay on disk as the reference implementation of this exact algorithm and
keep their own dedicated test suites exercising it via direct
invocation/subprocess -- this module is a BYTE-FAITHFUL PORT of that op's
three-state discrimination + calibration + escape-hatch logic, not a
reinterpretation of it. Deliberate duplication, not an oversight: calling
into the engine in-process (as the old shim did, via
`coordinator_core.ipc.dispatch_message`) would drag the whole
`coordinator_core.hooks` package (~18ms, see `_hook_envelope.py`'s own
measurement) into a hot path this hook already pays a role-framing pass on
for EVERY Agent dispatch (Concern D is unconditional); a subprocess call (as
Concern B's sidecar provisioning uses) would cost a fresh process spawn on
that same every-dispatch path. A pure-Python computation costs neither, at
the price of one duplicate algorithm between two repos on this one seam --
the SAME tradeoff `nudge-foreground-agent-dispatch.py`'s own engine-down
fallback already accepted (it independently re-implements the calibration-
marker read for its OWN fail-closed leg; see that module's `_resolve_git_dir`
/ `_bg_capable_marker_path`).

Three-state run_in_background logic (preserved exactly from the engine's
reference op):
    - present-and-true  -> nothing to do (already backgrounded -- correct
                           shape); the durable calibration marker is still
                           written, because presence of the param -- either
                           value -- is what proves the build exposes it.
    - present-and-false -> reroute (or deny, if no safe rewrite target).
    - absent            -> reroute only if calibrated (this session was
                           previously seen sending the param, proven by the
                           durable `.harness-bg-capable` marker); otherwise
                           nothing to do (brick-proof PASS -- a build with no
                           such param omits it on every dispatch, and acting
                           on that would gate every Agent call on the
                           machine).

Calibration marker: `<git-common-dir>/coordinator-sessions/<session_id>/
.harness-bg-capable`, written (touch, idempotent) whenever the key arrives
PRESENT with either value. Escape hatch: `<git-common-dir>/coordinator-
sessions/<session_id>/.foreground-ok` -- when present, an otherwise-
actionable dispatch passes through unrewritten for the rest of that session.
Both markers are resolved from `git_dir`, itself resolved from `cwd` WITHOUT
spawning a subprocess via `_resolve_git_dir` -> `_resolve_git_common_dir`
(walk up `cwd` and its parents to find the directory holding a `.git` entry,
then resolve that entry to the git COMMON dir, following a worktree's
`gitdir:` pointer AND its `commondir` indirection rather than stopping at the
worktree's own PRIVATE dir) -- the same no-subprocess, common-dir-aware
idiom `offer-exploration-tier-dispatch.py`'s canonical `_resolve_git_common_
dir` establishes; see that function's own docstring for the full list of
sibling copies. Session bookkeeping lives under the COMMON dir specifically
because that is what every hook/session sharing this repo (main clone or any
linked worktree) resolves to the same path -- the private per-worktree dir
would silently fragment one session's markers across worktrees.

NOTICE ON EVERY REROUTE -- load-bearing, not a style choice: the pre-revert
version of this logic (the engine's own commit history, 2026-07-29)
suppressed the reroute advisory after the first one per session (`.foreground-reroute-
noticed`, "bark-once"). That suppression is why the non-binding race went a
whole session undetected: the ONLY feedback channels a broken reroute has are
its own notice and the tool result, and a silenced notice took the one
channel that could have surfaced the mechanism silently failing. This module
carries NO notice-once state and never will -- `compute_foreground_reroute`
returns a fresh notice string on every single reroute it computes, full stop.

Fail-open on every detection-failure leg, mirroring `_worktree_isolation_
strip.compute_strip`: an unresolvable `cwd`/git-dir, an unreadable marker, or
any other I/O failure degrades toward "nothing to do" (`None`) rather than
raising -- except the one case that is DELIBERATELY fail-closed: a
provably-foreground dispatch (present-and-false, or calibrated-absent) that
cannot be safely rewritten (`tool_input` absent, not a dict, or missing the
load-bearing `prompt` key the Agent tool schema requires) returns a "deny"
result rather than silently letting the foreground dispatch through. Never
raises -- this runs inside a PreToolUse gate and must not brick an Agent
dispatch.

Message-text divergence, deliberate: the "BYTE-FAITHFUL PORT" claim above
covers the three-state discrimination + calibration + escape-hatch DECISION
LOGIC only. `_REROUTE_NOTICE`/`_DENY_MESSAGE` are authored fresh for this
module's `additionalContext`/deny channels, not ported verbatim from the
reference op's `_REROUTE_NOTICE`/`_DENY_MSG_TEMPLATE` -- wording drift here is
intentional, not an unflagged regression.

Input-coercion divergence, also deliberate: `compute_foreground_reroute`'s
`bg_true`/`has_bg` checks accept a raw Python `bool` or a mixed-case
`"true"`/`"false"` string, whereas the reference op only ever sees a
stringified `"true"`/`"false"` because its caller flattens every field
through `_payload.field()` first. This module's caller hands it a raw
JSON-decoded dict instead, so it must coerce itself; the wider acceptance is
strictly more permissive in the safe (does-not-miss-a-foreground-dispatch)
direction. It is the *outcome* of the three-state logic, not the input
coercion feeding it, that is preserved exactly from the reference.

Spec backlink: coordinator_core/hooks/nudge_foreground_agent_dispatch.py
(the engine's reference implementation, the algorithm this module ports),
coordinator/hooks/scripts/enforce-agent-dispatch-mode.py (module docstring,
Concern G).
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _message_envelope import resolve_wiki_citation  # noqa: E402

_SESSION_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{4,}$")

_BG_CAPABLE_MARKER_NAME = ".harness-bg-capable"
_FOREGROUND_OK_MARKER_NAME = ".foreground-ok"

#: Repo-relative literal, resolved for the reader by `resolve_wiki_citation()`
#: at render time (below) rather than emitted verbatim -- same mechanism the
#: 16 `_message_envelope`-routed hooks use for their `_WIKI_ANCHOR` sites.
_UNLOCK_DOC_CITATION = "coordinator/docs/wiki/guard-unlock-channel.md"

_REROUTE_NOTICE = (
    "[foreground gate] this Agent dispatch was rewritten to run_in_background: true and "
    "is running now -- expect its result as a task notification, not inline; do not treat "
    "the next tool call as blocked on it. Coordinator default is backgrounded dispatch: a "
    "foreground subagent LOCKS THE EM IN PLACE, unable to issue the rest of its wave, "
    "reconcile plans, or answer the PM until it returns. This notice fires on EVERY "
    "reroute, not just the first, by design -- a silenced notice is how a broken reroute "
    "went undetected for a whole session before (2026-07-30). Rare legitimate foreground "
    "need: see {unlock_doc}."
).format(unlock_doc=resolve_wiki_citation(_UNLOCK_DOC_CITATION))

_DENY_MESSAGE = (
    "[foreground gate] denied: this Agent dispatch chose run_in_background: false (or "
    "omitted it on a session already proven to expose the param) but supplied no safely "
    "rewritable tool_input -- either tool_input was not forwarded, or it is missing the "
    "`prompt` key the Agent tool schema requires. Rewriting without `prompt` would dispatch "
    "a subagent with no instructions, silently -- worse than this deny. Reissue the call "
    "with a complete tool_input and run_in_background: true. Rare legitimate foreground "
    "need: see {unlock_doc}. Doctrine: "
    "coordinator/snippets/em-operating-doctrine.md § How to Dispatch."
).format(unlock_doc=resolve_wiki_citation(_UNLOCK_DOC_CITATION))


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


def _resolve_git_dir(cwd: Any) -> Optional[str]:
    """Best-effort git COMMON-dir resolution from `cwd`, WITHOUT spawning a
    subprocess. Walks `cwd` and its parents to find the directory holding a
    `.git` entry (`_git_root`), then resolves that entry to the git COMMON
    dir (`_resolve_git_common_dir`) -- following a worktree's `gitdir:`
    pointer AND its `commondir` indirection, never stopping at the
    worktree's own PRIVATE dir. Returns `None` on any failure to resolve --
    callers degrade to the fail-open "nothing to do" answer, same as every
    other leg in this module.
    """
    if not isinstance(cwd, str) or not cwd:
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


def _bg_capable_path(git_dir: str, session_id: str) -> Path:
    return Path(git_dir) / "coordinator-sessions" / session_id / _BG_CAPABLE_MARKER_NAME


def _foreground_ok_path(git_dir: str, session_id: str) -> Path:
    return Path(git_dir) / "coordinator-sessions" / session_id / _FOREGROUND_OK_MARKER_NAME


def _mark_bg_capable(git_dir: Optional[str], session_id: str) -> None:
    """Record that this session's harness demonstrably exposes run_in_background.

    Best-effort and silent on failure: a missing marker degrades to the
    brick-proof PASS that predates calibration entirely -- the safe direction
    for the absent-key case.
    """
    if not git_dir or not session_id:
        return
    marker = _bg_capable_path(git_dir, session_id)
    try:
        if marker.exists():
            return
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
    except Exception:
        pass


def _is_bg_capable(git_dir: Optional[str], session_id: str) -> bool:
    if not session_id or not git_dir:
        return False
    try:
        return _bg_capable_path(git_dir, session_id).exists()
    except Exception:
        return False


def compute_foreground_reroute(
    run_in_background: Any,
    session_id: Any,
    tool_input: dict,
    cwd: Any,
) -> Optional[tuple[str, Optional[bool], str]]:
    """Pure computation (plus the calibration-marker touch, same tradeoff
    `_worktree_isolation_strip.compute_strip` makes for its override-sentinel
    read): no stdout, no sys.exit.

    Args:
        run_in_background: the raw `tool_input.run_in_background` value --
            `True`/`False`/`"true"`/`"false"`/`None`/absent all handled;
            "" and `None` are both treated as absent.
        session_id: the raw top-level `session_id` payload value.
        tool_input: the dispatch's `tool_input` dict (the rewrite target).
        cwd: the raw top-level `cwd` payload value, used only for the
            no-subprocess git-dir resolution behind calibration/escape-hatch.

    Returns:
        `None` -- nothing to do (background already set, uncalibrated
            absent, or the `.foreground-ok` escape hatch is active).
        `("reroute", True, notice)` -- rewrite to background; caller sets
            `merged["run_in_background"] = True` and surfaces `notice` via
            `additionalContext`.
        `("deny", None, message)` -- foreground detected but no safe rewrite
            exists; caller must deny the whole dispatch outright, never fold
            this into an "allow".
    """
    sid = session_id if isinstance(session_id, str) else ""
    if sid and not _SESSION_ID_RE.match(sid):
        sid = ""

    has_bg = run_in_background is not None and run_in_background != ""
    bg_true = run_in_background is True or (
        isinstance(run_in_background, str) and run_in_background.strip().lower() == "true"
    )

    git_dir = _resolve_git_dir(cwd)

    # Calibrate first, mirroring the engine's reference op's ordering: presence (either
    # value) proves the build exposes the param, and that fact is only
    # observable here.
    if has_bg and sid:
        _mark_bg_capable(git_dir, sid)

    if bg_true:
        return None

    if not has_bg:
        if not _is_bg_capable(git_dir, sid):
            return None
        # Fall through: calibrated absent = deliberate foreground.

    # Escape hatch -- explicit opt-in to foreground for this session.
    if sid and git_dir:
        try:
            if _foreground_ok_path(git_dir, sid).exists():
                return None
        except Exception:
            pass

    if isinstance(tool_input, dict) and tool_input.get("prompt"):
        return (
            "reroute",
            True,
            _REROUTE_NOTICE,
        )

    return (
        "deny",
        None,
        _DENY_MESSAGE,
    )
