"""guard-review-integrator-sidecar-intake.py -- PreToolUse hook, matcher: Agent.

Mechanical enforcement of `coordinator/agents/review-integrator.md`'s
"Intake precondition -- hard stop": review-integrator's inputs are files on
disk (a reviewer findings sidecar + the artifact path(s)), never findings
inline in the dispatch prompt. That precondition is stated in prose only,
and prose lost 5/5 in the field -- a sibling EM sent five consecutive
inline-findings dispatches to review-integrator, and all five walked
straight through the prose hard stop and did the work anyway, flagging the
mismatch only as a closing concern. One instance rationalized past the stop
explicitly: it found an UNRELATED pre-existing sidecar on disk and treated
the dispatch as "a correction order against that pre-existing sidecar." A
sufficiently confident, concretely-specified brief -- real file paths,
verified measurements, unambiguous instructions -- walks straight through a
prose-only stop; the fix has to live at the dispatch seam, not in stronger
prose review-integrator itself might rationalize past again.

Fires only for a dispatched `subagent_type` that resolves to
review-integrator (`coordinator:review-integrator` or the bare
`review-integrator`, matched via the same "segment after the last `:`"
normalization `pickup-autofire.py::_normalize_command_name` already uses for
the analogous namespaced/bare command-name split -- both a plugin-namespaced
identity and a bare one must resolve to the same check, not two).

A dispatch is satisfying iff its prompt text NAMES a
`state/subagent-share/<session>/<key>.md`-shaped path (see
`review-integrator.md`'s "Intake precondition" paragraph for the canonical
provisioned shape) AND that exact path exists on disk. Anything else --
inline findings with no sidecar path at all, a path that is named but not on
disk (stale/never-provisioned), or (the closed rationalization hole,
documented below) a real sidecar that exists on disk but was never named in
THIS dispatch's prompt -- denies.

NEGATIVE SPEC -- the closed rationalization hole: this guard deliberately
checks "named in this dispatch's prompt AND present on disk", never "present
on disk" alone. A "some sidecar exists somewhere under
state/subagent-share/<session>/" fallback would silently re-open the exact
failure this guard exists to close (the observed "I treated this as a
correction order against that pre-existing sidecar" rationalization) --
resist adding one even as a convenience for a genuinely-provisioned-but-
unnamed sidecar; the EM's remedy in that case is to name the path in the
prompt, not for this guard to go find it.

Deny-message shape follows this repo's design-as-offers doctrine (global
CLAUDE.md § Implementation Standards): leads with the correct route before
stating what was missing.

Fail-open, silently, on: tool_name != "Agent"; subagent_id present (a
subagent's own nested Agent call, not the dispatching EM's); no
subagent_type; subagent_type normalizes to something other than
review-integrator; no `prompt` text extractable; malformed input JSON. A
broken guard must never brick every review-integrator dispatch in the
fleet -- the only fail-CLOSED leg is the confirmed "no on-disk, in-prompt
sidecar path found for a genuine review-integrator dispatch" case.

Spec backlink: coordinator/agents/review-integrator.md § Intake precondition -- hard stop
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Optional

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from _message_envelope import ALTERNATIVE_MAX_LINES, compose, render  # noqa: E402

#: Wiki section carrying the relocated three-branch remedy explanation and
#: the closed-rationalization-hole rationale -- see
#: docs/plans/2026-08-02-guard-message-character-cap.md § C6 and this
#: hook's own relocation fragment.
_WIKI_ANCHOR = (
    "coordinator/docs/wiki/guard-message-concision.md"
    "#review-integrator-sidecar-intake"
)


# Repo-relative shape only, per review-integrator.md's canonical provisioned
# path (`state/subagent-share/<session>/<key>.md`) -- mirrors
# enforce-agent-dispatch-mode.py's `_PLAN_PATH_RE` widening rationale: the
# leading char-class includes "/" so an absolute brief citation (e.g.
# ".../DoE-claude/state/subagent-share/<session>/<key>.md") still matches,
# because the capture group only ever starts at the literal
# "state/subagent-share/" prefix -- an absolute prefix before that point is
# excluded from the match by construction.
_SIDECAR_PATH_RE = re.compile(
    r"(?:^|[\s(\[\"'`/])(state/subagent-share/[^\s()\[\]\"'`,;:]+\.md)"
)


def _extract_candidate_paths(prompt: str) -> "list[str]":
    if not prompt:
        return []
    return [m.group(1) for m in _SIDECAR_PATH_RE.finditer(prompt)]


def _normalize_subagent_type(raw: Optional[str]) -> str:
    """Same "segment after the last `:`" normalization
    `pickup-autofire.py::_normalize_command_name` uses -- a namespaced
    `coordinator:review-integrator` and a bare `review-integrator` both
    resolve to the same bare identity before the membership test."""
    if not isinstance(raw, str):
        return ""
    return raw.rsplit(":", 1)[-1]


def _git_root(start: str) -> Optional[str]:
    """Best-effort repo-root walk from `start`, mirroring
    block-dispatch-suite-invocation.py's `_git_root` (no shell-out, this
    guard stays zero-spawn on the hot path). Any failure returns None."""
    try:
        cur = Path(start)
        for _ in range(8):
            if (cur / ".git").exists():
                return str(cur)
            if cur.parent == cur:
                break
            cur = cur.parent
    except Exception:
        return None
    return None


def _compose_no_candidates_message():
    """Pure composer for the "no sidecar path named at all" deny message --
    separated from `main()` so C1's in-process measurement harness can call
    it directly (no stdin, no process) per the plan's Measurement mechanism
    section. Keeps both remedies the original prose carried (fulfil the
    contract, or use the right agent); the three-branch "why" explanation
    relocated to `_WIKI_ANCHOR` -- see this hook's relocation fragment."""
    return compose(
        "no sidecar named -- name or provision one, or dispatch "
        "coordinator:enricher instead for plan-body work.",
        anchor=_WIKI_ANCHOR,
    )


def _compose_stale_candidates_message(candidates: "list[str]"):
    """Pure composer for the "named but not on disk" deny message -- same
    separation rationale as `_compose_no_candidates_message`. The named,
    stale candidate path(s) ride in `alternative` (structurally exempt from
    the char cap, per `_message_envelope`) rather than the counted prose."""
    alternative = "\n".join(candidates[:ALTERNATIVE_MAX_LINES])
    return compose(
        "named sidecar not on disk -- provision it, or dispatch "
        "coordinator:enricher instead for plan-body work.",
        alternative=alternative,
        anchor=_WIKI_ANCHOR,
    )


def main() -> int:
    try:
        raw = sys.stdin.read()
    except Exception:
        raw = ""
    if not raw:
        return 0

    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}

    if payload.get("tool_name", "") != "Agent":
        return 0

    # Only the dispatching EM's own Agent call is guarded, never a
    # subagent's own nested dispatch -- mirrors the sibling Agent-matcher
    # guards' `agent_id` exclusion.
    if "agent_id" in payload:
        return 0

    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0

    child_subagent_type = _normalize_subagent_type(tool_input.get("subagent_type"))
    if child_subagent_type != "review-integrator":
        return 0

    prompt = tool_input.get("prompt", "")
    prompt = prompt if isinstance(prompt, str) else ""

    candidates = _extract_candidate_paths(prompt)
    if not candidates:
        out = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": render(_compose_no_candidates_message()),
            }
        }
        sys.stdout.write(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
        sys.stdout.write("\n")
        return 0

    cwd = payload.get("cwd")
    start = cwd if isinstance(cwd, str) and cwd else os.getcwd()
    root = _git_root(start) or start

    for candidate in candidates:
        full = Path(root) / candidate
        try:
            if full.is_file():
                return 0
        except Exception:
            continue

    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": render(
                _compose_stale_candidates_message(candidates)
            ),
        }
    }
    sys.stdout.write(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
