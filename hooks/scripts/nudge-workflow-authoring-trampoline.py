"""PreToolUse(Skill, Workflow) trampoline nudge, two fire points, one hook.

Problem this closes (docs/wiki/coordinator-tripwires/
a-hand-authored-workflow-costs-4x-the-plan-execution.md): the native
`workflow-authoring` skill teaches an EM to hand-author a `Workflow({script:
"..."})` call with no pointer back at `emit-dispatch-workflow.py`, the
emitter that would derive the same wave shape from a ratified plan spine for
roughly a quarter of the token cost. `Workflow({script: "..."})` (the inline
form) is a deliberate fail-open in `block-workflow-foreign-emission.py`
(byte-provenance remit only, silent about cost) -- every inline `script:` is
by construction hand-authored, since the emitter always writes to disk and
is fired by `scriptPath`. This hook is the missing pointer, fired at
whichever of two moments comes first: opening the `workflow-authoring`
skill, or authoring an inline `Workflow({script: "..."})` call directly.

Offer-shape (never blocks): this hook ALWAYS exits 0. It emits
{"hookSpecificOutput":{"hookEventName":"PreToolUse",
"additionalContext":"<message>"}} on the nudge path -- an advisory
surfaced to the EM, never a deny. It never sets "decision":"block" and never
returns a non-zero exit code.

Fires when:
  - tool_name == "Skill" and tool_input carries a skill identifier
    ("skill", falling back to "command" -- same two-key probe as
    watchdog-undischarged-next-move.py's `_matches_next_action` Skill leg)
    equal to "workflow-authoring" (case-insensitive; a bare or
    `coordinator:`-prefixed spelling both match, mirroring the same
    tolerance the executor-roster substring check in
    nudge-multiwave-workflow.py extends to subagent_type spellings); OR
  - tool_name == "Workflow" and tool_input carries a `script` key
    (non-empty string) and does NOT carry a `scriptPath` key -- the
    by-construction hand-authored form (a deliberate fail-open in
    `block-workflow-foreign-emission.py`: "No `scriptPath` (an inline
    `script:` carries its own bytes in the call -- there is no disk read
    for a peer to race)")
  - and, either way, the once-per-session sentinel is absent

Registered under BOTH matchers in hooks.json, one script. The `Workflow`
entry sits AFTER the Workflow deny-hooks (block-workflow-foreign-emission.py,
block-dispatch-suite-invocation.py, block-workflow-unmodeled-agent.py,
strip-worktree-isolation.py) so a real deny still wins the remediation text
(hook-best-practices.md § Multi-hook deny aggregation) -- this hook never
denies.

ONE sentinel name shared across both fire points: whichever tool_name fires
first this session suppresses the other for the rest of the session. Two
distinct sentinel names would let the same message fire twice a session to
the one EM the message is meant for (open the skill, then also author the
inline call) -- the sentinel exists to prevent exactly that repeat.

Negative spec (Workflow leg): does NOT fire on a `scriptPath` launch,
whatever its provenance -- that is the emitted-and-fired path this
trampoline exists to recommend, not a case to warn about. Does NOT inspect
the `script` bytes for content (e.g. to detect a script that merely wraps
`emit-dispatch-workflow.py` output) -- the presence of an inline `script:`
with no `scriptPath` is itself the by-construction signal; no false
positive is possible on that axis.

Graceful degradation -- REQUIRED: any failure to parse stdin, resolve the
git root, or read/write the session-scoped sentinel falls through to a
silent pass (exit 0, no stdout). A filesystem hiccup must never brick a
Skill or Workflow invocation. The emit itself is wrapped defensively too:
the sentinel is touched only AFTER a successful emit, so a failed emit
degrades to a harmless repeat next fire rather than a silent, permanent
loss of the advisory for the session.

Spec backlink: docs/wiki/coordinator-tripwires/
a-hand-authored-workflow-costs-4x-the-plan-execution.md

Contract:
  stdin   -- PreToolUse JSON (tool_name, tool_input, session_id, ...)
  stdout  -- one hookSpecificOutput JSON envelope (additionalContext) on a
             qualifying first-fire-this-session Skill(workflow-authoring) or
             inline Workflow({script}) invocation; NOTHING otherwise
             (silent pass)
  exit 0  -- always (advisory only; never blocks/denies)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)
import _message_envelope as _envelope  # noqa: E402

from _win_portability import no_console_creationflags  # noqa: E402
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
try:
    from _git_root_walk import git_root_walk as _git_root_walk  # noqa: E402
except Exception:
    def _git_root_walk() -> str | None:
        return None

_WIKI_ANCHOR = (
    "coordinator/docs/wiki/coordinator-tripwires/"
    "a-hand-authored-workflow-costs-4x-the-plan-execution.md"
)

# Mirrors nudge-multiwave-workflow.py's own session_id format guard.
_SESSION_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{4,}$")

_SENTINEL_NAME = "workflow-authoring-trampoline-nudged"

_TARGET_SKILL_NAMES = {"workflow-authoring", "coordinator:workflow-authoring"}


def _git_root() -> str | None:
    """Repo root, fail-open to None. In-process parent walk first, subprocess
    fallback -- see nudge-multiwave-workflow.py's own `_git_root` for the
    full rationale; this is a byte-for-byte copy of that function."""
    walked = _git_root_walk()
    if walked:
        return walked
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=1,
            **no_console_creationflags(),
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    root = result.stdout.strip()
    return root or None


def _compose_skill_offer() -> "_envelope.Message":
    """Pure message composer, routed through `_message_envelope.compose`
    (docs/plans/2026-08-02-guard-message-character-cap.md § C6)."""
    prose = (
        "[workflow-authoring trampoline] if this is plan dispatch, the script "
        "already exists -- run `emit-dispatch-workflow.py --plan <plan>` and "
        "fire the emitted path via `coordinator:execute-plan` instead of "
        "hand-authoring one here. If this is a fan-out the emitter cannot "
        "produce (review, research), carry on and author it."
    )
    return _envelope.compose(prose, anchor=_WIKI_ANCHOR)


def _compose_inline_offer() -> "_envelope.Message":
    """Pure message composer, routed through `_message_envelope.compose`
    (docs/plans/2026-08-02-guard-message-character-cap.md § C6)."""
    prose = (
        "[workflow-authoring trampoline] this inline `script:` is by "
        "construction hand-authored -- if this is plan dispatch, run "
        "`emit-dispatch-workflow.py --plan <plan>` and fire the emitted path "
        "via `coordinator:execute-plan` (`Workflow({scriptPath})`) instead, "
        "for roughly a quarter of the token cost. If this is a fan-out the "
        "emitter cannot produce (review, research), carry on."
    )
    return _envelope.compose(prose, anchor=_WIKI_ANCHOR)


def _extract_skill_name(tool_input: object) -> str | None:
    if not isinstance(tool_input, dict):
        return None
    skill = tool_input.get("skill")
    if not isinstance(skill, str):
        skill = tool_input.get("command")
    if not isinstance(skill, str):
        return None
    return skill


def _is_inline_script_launch(tool_input: object) -> bool:
    if not isinstance(tool_input, dict):
        return False
    script = tool_input.get("script")
    if not isinstance(script, str) or not script.strip():
        return False
    script_path = tool_input.get("scriptPath")
    if isinstance(script_path, str) and script_path.strip():
        return False
    return True


def main() -> int:
    raw = sys.stdin.read()
    if not raw:
        return 0

    try:
        payload = json.loads(raw)
    except Exception:
        return 0
    if not isinstance(payload, dict):
        return 0

    tool_name = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    if tool_name == "Skill":
        skill_name = _extract_skill_name(tool_input)
        if not skill_name or skill_name.strip().lower() not in _TARGET_SKILL_NAMES:
            return 0
        compose = _compose_skill_offer
    elif tool_name == "Workflow":
        if not _is_inline_script_launch(tool_input):
            return 0
        compose = _compose_inline_offer
    else:
        return 0

    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return 0
    if not _SESSION_ID_RE.match(session_id):
        return 0
    if not session_id_is_real(session_id):
        return 0

    git_root = _git_root()
    if not git_root:
        return 0

    # Rooted at the git COMMON dir, never `<git_root>/.git` -- see
    # nudge-multiwave-workflow.py's own `main()` for why a worktree's `.git`
    # FILE would silently never persist this session's sentinel.
    common_dir = _resolve_git_common_dir(git_root)
    if not common_dir:
        return 0

    session_dir = Path(common_dir) / "coordinator-sessions" / session_id
    nudged_sentinel = session_dir / _SENTINEL_NAME
    if nudged_sentinel.is_file():
        return 0

    message = compose()
    try:
        _envelope.emit(message, _envelope.CHANNEL_ADDITIONAL_CONTEXT)
    except Exception:
        pass

    try:
        ensure_session_dir(session_dir, session_id)
        nudged_sentinel.touch()
    except Exception:
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
