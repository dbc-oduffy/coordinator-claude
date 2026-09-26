"""offer-exploration-tier-dispatch.py -- PreToolUse hook, matcher: Agent.

Design-as-offers hook on the dispatch path (Leg D of the boot-envelope
retiering baton): when the EM dispatches a doctrine-carrying agent
(anything other than `Explore`/`Plan`, the two the harness exempts from
the CLAUDE.md corpus -- see `docs/wiki/dispatching-parallel-agents/agent-dispatch-economics.md`) for
work whose prompt reads as read-only-shaped, this hook offers the cheap
alternative -- an UNNAMED `Explore` dispatch -- instead of nagging about
the more expensive one already chosen. Never blocks, never mutates the
call: `additionalContext` only, exactly the shape
`nudge-multiwave-workflow.py` uses, and never the `updatedInput` shape
`enforce-agent-dispatch-mode.py` documents itself as the sole emitter of
on this matcher.

WHY UNNAMED, SPECIFICALLY -- this is the load-bearing correction the offer
text carries. Naming an `Explore` dispatch (`name: "..."` in the Agent
call) does not merely cost more -- a named dispatch discards the harness's
built-in `Explore` definition and rebuilds the child from the main-loop
prompt builder, and the `Edit`/`Write` denial lives in the definition that
gets discarded. A named `Explore` is therefore NOT read-only, and offering
one would be actively wrong advice, not merely a worse deal. This hook
only ever offers the unnamed form and says so explicitly.

DETECTION -- conservative by design. The firing rule requires BOTH:
  1. the dispatch target is doctrine-carrying (subagent_type present and
     not `Explore`/`Plan`, case-insensitive), AND
  2. the prompt is read-only-SHAPED: it contains a find/locate/search/
     survey-class signal AND no write-shaped instruction anywhere (a
     write verb present anywhere in the prompt disqualifies the offer
     outright -- no negation-scrubbing here, unlike a stricter sibling
     hook's predicate, because a false offer on genuinely write-shaped
     work trains the reader to ignore this one; the cost of a missed
     offer is nothing, the cost of a wrong one is credibility).
Both legs are exposed as small pure functions (`_is_doctrine_carrying`,
`_is_read_only_shaped`) so a test can drive the discriminator directly
without going through the process boundary.

Contract:
  stdin   -- PreToolUse JSON (tool_name, tool_input with subagent_type,
             prompt; session_id; cwd; ...)
  stdout  -- one hookSpecificOutput JSON envelope carrying ONLY
             `additionalContext` (never `permissionDecision`, never
             `updatedInput`) on a first-in-session qualifying dispatch;
             NOTHING otherwise (silent pass)
  exit 0  -- always. Advisory-only by construction, not merely by
             convention: this hook has no deny path and no rewrite path.

Fail-open on every leg: unreadable/empty stdin, unparsable JSON, a
non-dict payload or tool_input, an unresolvable git root/marker path, a
missing session_id (no id to dedupe on -> offering unconditionally would
spam rather than nudge, so this degrades to silent, not to firing every
time). No exception anywhere in this module may reach stderr as a
traceback -- a wedged dispatch is worse than a missed offer.

DISPOSITION (C6c, docs/plans/2026-08-06-hook-spawn-fan-in-finish-and-extend.md
§ C6c -- the C1 test applied up front): explicitly no-subprocess by design,
no `coordinator_core` reference. The only read/write beyond the in-process
git-root walk is the once-per-session `exploration-tier-dispatch-offered`
marker file it creates itself under `<git_common_dir>/coordinator-sessions/
<session_id>/` -- generic per-session dedupe bookkeeping, never a read of
this repo's own doctrine working-data (docs/plans, state/*, agents/*.md, etc.). Same
"common_dir" scope shape `coordinator_core.hooks.track_touched_files`
already carries as an engine-repo op, not the "resolves the doctrine repo root
to read doctrine working-data" shape the plan's Anti-scope forbids porting.
Verdict: CANDIDATE for a net-new `common_dir`-scoped engine-repo op,
tracked under C6b's DR-127 gate -- not a doctrine-repo-runner fold (contrast
a hook that reads a genuine doctrine-repo-authored sidecar file and
therefore stays doctrine-repo-resident on `preuse-agent-dispatch.py`'s
runner). Actual porting is out of C6c's scope
per that row's own body ("Porting any of them means writing new engine
logic, not attaching existing logic"); this hook remains un-registered in
`hooks.json` pending that future engine-side work.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

from _message_envelope import CHANNEL_ADDITIONAL_CONTEXT, compose, emit  # noqa: E402
try:
    from _git_common_dir import resolve_git_common_dir as _resolve_git_common_dir  # noqa: E402
except Exception:
    def _resolve_git_common_dir(git_root: str) -> str:
        return ""
try:
    from _session_hub import session_id_is_real, ensure_session_dir  # noqa: E402
except Exception:
    def session_id_is_real(session_id: object) -> bool:
        return bool(session_id)

    def ensure_session_dir(session_dir: "str | os.PathLike[str]", session_id: object) -> bool:
        try:
            os.makedirs(os.fspath(session_dir), exist_ok=True)
        except (OSError, TypeError, ValueError):
            return False
        return True

_EXEMPT_TARGETS = {"explore", "plan"}

_READ_ONLY_RE = re.compile(
    r"\b(find|locate|search|inventory|survey|list|identify)\b"
    r"|which\s+files?"
    r"|where\s+is\b"
    r"|does\b[^.\n]{0,80}\bexist\b",
    re.IGNORECASE,
)

_WRITE_VERB_RE = re.compile(
    r"\b(?:re-?)?(edit|editing|edits|"
    r"writ(?:e|es|ing|ten)|"
    r"creat(?:e|es|ing|ed)|"
    r"fix(?:es|ing|ed)?|"
    r"implement(?:s|ing|ed)?|"
    r"appl(?:y|ies|ying|ied)|"
    r"refactor(?:s|ing|ed)?|"
    r"delet(?:e|es|ing|ed)|"
    r"commit(?:s|ting|ted)?|"
    r"updat(?:e|es|ing|ed)|"
    r"add(?:s|ing|ed)?|"
    r"remov(?:e|es|ing|ed)|"
    r"renam(?:e|es|ing|ed)|"
    r"insert(?:s|ing|ed)?|"
    r"append(?:s|ing|ed)?|"
    r"modif(?:y|ies|ying|ied)|"
    r"mov(?:e|es|ing|ed)|"
    r"bump(?:s|ing|ed)?|"
    r"replac(?:e|es|ing|ed)|"
    r"generat(?:e|es|ing|ed)|"
    r"buil(?:d|ds|ding)|built|"
    r"install(?:s|ing|ed)?|"
    r"configur(?:e|es|ing|ed)|"
    r"patch(?:es|ing|ed)?|"
    r"merg(?:e|es|ing|ed)|"
    r"migrat(?:e|es|ing|ed))\b",
    re.IGNORECASE,
)

_MARKER_NAME = "exploration-tier-dispatch-offered"

_WIKI_ANCHOR = (
    "coordinator/docs/wiki/guards/guard-message-concision.md"
    "#unnamed-explore-dispatch-cost-and-guarantee"
)

_OFFER_PROSE = (
    "Read-only-shaped dispatch: an unnamed Explore is cheaper and stays "
    "read-only. Naming it forfeits both -- skip if this needs Edit/Write."
)


def _compose_offer_message():
    """The pure composer, isolated from stdin/exit-code plumbing -- see
    module docstring for the load-bearing "why unnamed" rule this message
    still states. The token-cost figures and the mechanism explanation
    (main-loop prompt builder rebuild, where the Edit/Write denial lives)
    relocated to `_WIKI_ANCHOR`."""
    return compose(_OFFER_PROSE, anchor=_WIKI_ANCHOR)


def _is_doctrine_carrying(subagent_type: Any) -> bool:
    if not isinstance(subagent_type, str):
        return False
    normalized = subagent_type.strip().lower()
    if not normalized:
        return False
    return normalized not in _EXEMPT_TARGETS


def _is_read_only_shaped(prompt: Any) -> bool:
    if not isinstance(prompt, str) or not prompt.strip():
        return False
    if _WRITE_VERB_RE.search(prompt):
        return False
    return bool(_READ_ONLY_RE.search(prompt))


def _git_root(start: str) -> str:
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


def _claim_offer_marker(cwd: str, session_id: str) -> bool:
    try:
        git_root = _git_root(cwd)
        if not git_root:
            return True
        common_dir = _resolve_git_common_dir(git_root)
        if not common_dir:
            return True
        session_dir = os.path.join(common_dir, "coordinator-sessions", session_id)
        if not session_id_is_real(session_id):
            return True
        ensure_session_dir(session_dir, session_id)
        marker = os.path.join(session_dir, _MARKER_NAME)
        try:
            fd = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return False
        except OSError:
            return True
        else:
            os.close(fd)
            return True
    except Exception:
        return True


def main() -> int:
    try:
        raw = sys.stdin.read()
    except Exception:
        raw = ""
    if not raw:
        return 0

    try:
        data: Any = json.loads(raw)
    except Exception:
        return 0
    if not isinstance(data, dict):
        return 0

    if data.get("tool_name") != "Agent":
        return 0

    tool_input = data.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0

    subagent_type = tool_input.get("subagent_type")
    if not _is_doctrine_carrying(subagent_type):
        return 0

    prompt = tool_input.get("prompt")
    if not _is_read_only_shaped(prompt):
        return 0

    cwd = data.get("cwd")
    if not isinstance(cwd, str):
        cwd = ""
    session_id = data.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return 0

    if not _claim_offer_marker(cwd, session_id):
        return 0

    try:
        emit(_compose_offer_message(), CHANNEL_ADDITIONAL_CONTEXT)
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
