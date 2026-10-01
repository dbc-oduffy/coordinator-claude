"""Undischarged-next-move watchdog -- ledger emission/discharge + one-shot Stop read.

Spec backlink: docs/plans/2026-08-10-posture-scaled-autonomous-disposition.md
(chunk C3, "THE HEADLINE CHUNK").

THE PROBLEM (see the plan's own Problem section for the fuller account): an
EM ends its turn having NARRATED a machine-resolved next move instead of
taking it -- "next, a named Opus reviewer", "shall I dispatch?" -- and the
session halts for no reason a human needed to supply. This module is the
generalisation of `nudge-unrouted-sizing.py` (one seam, engine-resident) to
three doctrine-plane-resident seams behind a session-scoped ledger
(`_next_move_ledger.py`).

WHY THIS IS NOT THE STOOD-DOWN WATCHER. `runtime-tripwire-stop-watcher.py`
inferred a STATE ("is this session stalled?") from timing and transcript
shape, fired 681 times in 26 days at ~99.4% wrong, and was stood down by PM
ruling. This module infers NOTHING -- it reads a ledger of obligations that
were themselves opened only by a concrete PostToolUse observation of a
seam-opening call, and closed only by a concrete PostToolUse observation of
the matching terminal call. No timing, idle-duration, or session-age
predicate exists anywhere in this module (grep-asserted by the test suite,
per A5).

TWO EVENTS, ONE SCRIPT. Registered on BOTH `PostToolUse` (matcher
`Skill|Agent`) and `Stop` (matcher ""); `main()` branches on the payload
shape (`tool_name` a string -> PostToolUse; else `transcript_path` present
-> Stop) since the two events carry different stdin shapes and neither
wire format currently sends a distinguishing `hook_event_name` field to
naked-Python hooks. The PostToolUse branch takes precedence: a payload
carrying a non-string `tool_name` (e.g. `null`) alongside `transcript_path`
still routes to Stop, matching what `_handle_post_tool_use` itself
requires of `tool_name`. This mirrors the existing single-script,
dual-matcher pattern used by `guard-manufactured-blocker.py`'s Stop-only
sibling registrations elsewhere in `hooks.json`.

EMISSION -- a STATIC seam table (`_SEAM_TABLE` below), never an inference.
Five obligations:
  sizing-routed    opens on Skill(coordinator:sizing); the resolved next
                   action is read off the JUST-WRITTEN sizing object's
                   `route` (via the session's git `touch-record.jsonl`, same
                   technique `guard-manufactured-blocker.py` uses to find
                   "the session's routed sizing object" -- read
                   here through `lib/frontmatter_scan.py`).
  plan->review     opens on Skill(coordinator:plan) ONLY when that same
                   sizing object's route is exactly "plan" (the FULL
                   terminal). A route of "spec-dispatch" does NOT open this
                   obligation -- its terminal is an executor dispatch, not
                   review, and that obligation is already covered by
                   sizing-routed opened at sizing time.
  execute->wave    opens on Skill(coordinator:execute-plan); discharged by
                   the next Agent dispatch. Needs no sizing object: this
                   skill's terminal is fixed by the skill itself ("no
                   per-chunk reviewer gate ... ship Phase N green, dispatch
                   Phase N+1 immediately, no checkpoint offer"), so a turn
                   that enters plan execution and ends without dispatching
                   anything is the undischarged case by construction, with
                   no route lookup needed to know it.
  review-a1-a2     opens on Skill(coordinator:review); discharged by the
                   next Agent dispatch (the reviewer persona named at A.2
                   varies per review -- the Staff Engineer/the Game Dev Reviewer/the Data Science Reviewer/the Front-End Reviewer/the UX Reviewer/the Director of Engineering --
                   and none of those names is a fixed `subagent_type` this
                   module can match against, so discharge is a deliberately
                   broad "any Agent call after Skill(coordinator:review)"
                   rather than a narrower, unverifiable persona match).
  pickup->next-move
                   opens on Skill(coordinator:pickup), unconditionally --
                   pickup is mutually exclusive with sizing, so there is
                   no sizing object to read a route off, and the whole
                   lane was invisible while emission required one. Its
                   terminal is heterogeneous (apply a handoff, dispatch an
                   executor, mint a successor), so it discharges on ANY
                   subsequent Skill OR Agent call -- the `Skill|Agent`
                   wildcard kind, the same "no verifiable identity" logic
                   as review-a1-a2 widened one step.

ROUTE TERMINALS -- only routes with a machine-resolved next call get an
obligation opened at all (`_ROUTE_TERMINAL` below): `dispatch`/
`spec-dispatch` -> an executor dispatch (Agent tool); `plan`/`shape`/
`roadmap` -> Skill(coordinator:plan) (the route mints a plan next).
`pm-decision` and `goal-setting` are deliberately ABSENT from the table --
their whole point is that the next move is a PM call, not a machine-
resolved one, and `pm-decision` with `xl_exit: null` is additionally
covered by the exemption predicate below regardless of table membership.

EXEMPTIONS -- copied from `nudge-unrouted-sizing.py`'s own discipline (and
reimplemented, self-contained, the same way `guard-manufactured-blocker.py`
reimplements it): an unresolved appetite/post-size fork, or a
`route: pm-decision` sizing object carrying `xl_exit: null`, is a
legitimate PM-pending state and must NOT open an obligation.

ONE FIRE PER OBLIGATION (A6) -- `_next_move_ledger.mark_fired` is the latch;
a second Stop with the same obligation open finds it already fired and
stays silent. A guard that repeats is the nag the PM has already rejected.

MESSAGE SHAPE (A7) -- the fired message carries the obligation's literal
`next_action` string (e.g. "Skill(coordinator:review)"), never an
exhortation to keep going.

SEVERITY BY POSTURE -- `precision`: advisory via stdout, exit 0 (byte-
identical to today, per A8). `default`/`substrate-free`: stderr, exit 2
(the Stop-family blocking shape `nudge-unrouted-sizing.py` and
`nudge-harness-directive-dispatch.py` already use), so the turn does not
end and the EM continues in-turn with the command in hand.

Contract:
  PostToolUse stdin  -- tool_name, tool_input, session_id, cwd, agent_id...
  PostToolUse stdout -- nothing, ever (this leg is silent bookkeeping)
  Stop stdin         -- session_id, transcript_path, cwd, stop_hook_active,
                        agent_id...
  Stop stdout        -- the correction text, at posture `precision` only
  Stop stderr        -- the correction text, at posture `default`/
                        `substrate-free` only
  exit 2             -- Stop leg fires at a blocking posture
  exit 0             -- every other path, including every failure path
                        (fail-open, both legs, unconditionally)

Graceful degradation: any failure to read stdin, parse JSON, resolve the
repo root, or read the ledger falls through to a silent no-op / exit 0.
"""

from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _posture import resolve_posture  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "lib"))
from frontmatter_scan import read_text, scan_mapping  # noqa: E402
import _next_move_ledger as _ledger  # noqa: E402
from _touch_record import _touch_lines, _touch_record_jsonl_paths, _touched_txt_paths  # noqa: E402

try:
    from _git_root_walk import git_root_walk  # noqa: E402
    from _git_common_dir import resolve_git_common_dir  # noqa: E402
except Exception:  # import failure degrades to the "cannot evaluate" path
    def git_root_walk(start=None):  # type: ignore[misc]
        return None

    def resolve_git_common_dir(git_root):  # type: ignore[misc]
        return ""



_SEAM_SIZING_ROUTED = "sizing-routed"
_SEAM_PLAN_REVIEW = "plan->review"
_SEAM_REVIEW_A1_A2 = "review-a1-a2"
_SEAM_EXECUTE_WAVE = "execute->wave"
_SEAM_PICKUP_NEXT_MOVE = "pickup->next-move"

# route -> the literal next_action a routed sizing object machine-resolves.
# `pm-decision` and `goal-setting` are deliberately absent -- see module
# docstring "ROUTE TERMINALS".
_ROUTE_TERMINAL = {
    "dispatch": "Agent(coordinator:executor)",
    "spec-dispatch": "Agent(coordinator:executor)",
    "plan": "Skill(coordinator:plan)",
    "shape": "Skill(coordinator:plan)",
    "roadmap": "Skill(coordinator:plan)",
}

_REVIEW_NEXT_ACTION = "Agent(<named Opus reviewer>)"
# execute->wave discharges on the Workflow vehicle as well as a direct Agent dispatch, and
# the Workflow leg is the DEFAULT path, not the exotic one: /execute-plan emits a script and
# fires it via Workflow, so the executor dispatches happen INSIDE the fired run, in a
# separate process this hook's PostToolUse leg never sees. Keyed on Agent alone, the
# obligation could not be discharged by the very call that discharges it in practice. The
# seam is "did this turn hand the work to an executor", and firing the emitted script is
# exactly that.
_EXECUTE_NEXT_ACTION = "Agent|Workflow(coordinator:executor or the emitted plan script)"
_REVIEW_TERMINAL = "Skill(coordinator:review)"

# The pickup lane's terminal is heterogeneous by construction (apply a handoff, dispatch an
# executor, mint a successor), so its obligation carries the wildcard call kind below rather
# than one fixed identity -- the same "no verifiable identity to match against" reasoning
# that makes the review terminal discharge on any Agent call, widened one step to cover
# Skill as well.
_ANY_CALL_KIND = "Skill|Agent"
_PICKUP_NEXT_ACTION = "Skill|Agent(the narrated next move)"

_SIZING_PATH_RE = re.compile(r"^state/sizings/[^/]+\.ya?ml$")
_APPETITE_DIVERGENCE_DETENT = "appetite_exceeded"
_POST_SIZE_PROMPT_DETENT = "post_size_prompt_pending"


# Self-contained sizing-object resolution -- reads the session's git touched.txt to find
# "the sizing object THIS session routed", since this module has no sibling engine op to
# delegate to.
def _record_fire(repo_root: str, session_id: str, guard: str, reason: str) -> str | None:
    """Mint a block-discharge nonce through the engine's ledger writer
    (coordinator_core.block_discharge.record_fire). None when the engine is unresolvable or
    the write fails; the caller reports that as an unrecorded fire, never as a clean check.
    """
    try:
        from _engine_root import place_engine_root_on_path, resolve_claude_klabauter_root

        root = resolve_claude_klabauter_root()
        if not root:
            return None
        place_engine_root_on_path(root)
        from coordinator_core.block_discharge import record_fire
    except Exception:
        return None
    return record_fire(repo_root, session_id, guard, reason)


def _repo_root(payload: dict):
    cwd = payload.get("cwd") or os.getcwd()
    if not isinstance(cwd, str):
        return None
    return git_root_walk(cwd)


def _is_null_scalar(value):
    return value is None or value in ("null", "~", "None", "")


def _newest_touched_sizing_path(repo_root: str, session_id: str):
    """Return the most-recently-touched state/sizings/*.yaml path this session wrote, or
    None.

    Source-then-recency, NOT the touch-lines' concatenated list order: a partially-migrated
    session can carry a state/sizings/ match in BOTH the new journal and the legacy touched
    file. Every new-file row postdates every legacy-file row for a given session -- the
    legacy writer stopped before the new writer started, never interleaved -- so the correct
    newest match is the LAST matching row in the new file if it has any match at all,
    falling back to the legacy file's last matching row only when the new file has none.
    Taking the last match of the naive new+legacy concatenation instead lets a legacy row
    that merely sorts later in the list mask a genuinely newer new-file row.
    """
    git_dir = resolve_git_common_dir(repo_root) or None
    if not git_dir:
        return None
    session_dir = os.path.join(git_dir, "coordinator-sessions", session_id)

    candidate = None
    for rel in _touch_record_jsonl_paths(session_dir):
        if _SIZING_PATH_RE.match(rel):
            candidate = rel
    if candidate is not None:
        return candidate

    for rel in _touched_txt_paths(session_dir):
        if _SIZING_PATH_RE.match(rel):
            candidate = rel
    return candidate


def _sizing_route_and_exemption(repo_root: str, rel_path: str):
    """Return (route, exempt) for the sizing object at rel_path. Any read failure returns
    (None, True) -- "cannot prove the exemption doesn't apply" fails toward silence."""
    text = read_text(os.path.join(repo_root, rel_path))
    if text is None:
        return None, True

    m = scan_mapping(text)
    route = m.get("route")
    fork = m.get("fork")
    xl_exit = m.get("xl_exit")
    detents = m.get("detents")
    if not isinstance(detents, list):
        detents = []

    fork_open = (
        _APPETITE_DIVERGENCE_DETENT in detents or _POST_SIZE_PROMPT_DETENT in detents
    ) and _is_null_scalar(fork)
    xl_open = route == "pm-decision" and _is_null_scalar(xl_exit)
    return route, (fork_open or xl_open)


def _split_call(next_action: str):
    """"Skill(coordinator:review)" -> ("Skill", "coordinator:review")."""
    if not next_action or "(" not in next_action or not next_action.endswith(")"):
        return None, None
    kind, _, rest = next_action.partition("(")
    return kind, rest[:-1]


def _matches_next_action(next_action: str, tool_name, tool_input) -> bool:
    kind, ident = _split_call(next_action)
    if kind is None:
        return False
    if "|" in kind:
        # A pipe-joined kind is a set of accepted tool names, not one name: both members
        # discharge on ANY match. Matching the set rather than special-casing one literal
        # keeps a third vehicle from needing another branch here.
        return tool_name in tuple(part for part in kind.split("|") if part)
    if kind == "Skill":
        if tool_name != "Skill" or not isinstance(tool_input, dict):
            return False
        skill = tool_input.get("skill")
        if not isinstance(skill, str):
            skill = tool_input.get("command")
        return skill == ident
    if kind == "Agent":
        # The reviewer/executor persona is not a fixed subagent_type this module can verify
        # -- any Agent dispatch discharges an "Agent(...)" obligation.
        return tool_name == "Agent"
    return False


def _discharge_matching(session_id: str, tool_name, tool_input) -> None:
    # kind "Agent" matches on tool name alone (no persona/identity is verifiable), so two
    # open Agent-terminal obligations can both match one Agent call. Cap discharge at the
    # single OLDEST matching open record per call -- read_records returns oldest first --
    # rather than closing every matching obligation, so one ambiguous terminal call never
    # silently discharges an obligation it didn't actually satisfy.
    for record in _ledger.read_records(session_id):
        if record.get("discharged_at") is not None:
            continue
        next_action = record.get("next_action")
        obligation_id = record.get("obligation_id")
        if not isinstance(next_action, str) or not isinstance(obligation_id, str):
            continue
        if _matches_next_action(next_action, tool_name, tool_input):
            _ledger.discharge_obligation(session_id, obligation_id)
            return


def _handle_post_tool_use(payload: dict) -> None:
    if payload.get("agent_id"):
        return  # a subagent's own tool call, not the EM's

    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return

    tool_name = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}

    # Discharge first -- this same call may close an obligation opened by an earlier turn,
    # independent of anything it opens below.
    _discharge_matching(session_id, tool_name, tool_input)

    if tool_name != "Skill":
        return

    skill = tool_input.get("skill")
    if not isinstance(skill, str):
        skill = tool_input.get("command")
    if not isinstance(skill, str):
        return

    if skill == "coordinator:review":
        _ledger.open_obligation(
            session_id, _SEAM_REVIEW_A1_A2, _SEAM_REVIEW_A1_A2, _REVIEW_NEXT_ACTION
        )
        return

    if skill == "coordinator:pickup":
        _ledger.open_obligation(
            session_id, _SEAM_PICKUP_NEXT_MOVE, _SEAM_PICKUP_NEXT_MOVE, _PICKUP_NEXT_ACTION
        )
        return

    if skill == "coordinator:execute-plan":
        _ledger.open_obligation(
            session_id, _SEAM_EXECUTE_WAVE, _SEAM_EXECUTE_WAVE, _EXECUTE_NEXT_ACTION
        )
        return

    if skill not in ("coordinator:sizing", "coordinator:plan"):
        return

    repo_root = _repo_root(payload)
    if repo_root is None:
        return
    rel_path = _newest_touched_sizing_path(repo_root, session_id)
    if rel_path is None:
        return
    route, exempt = _sizing_route_and_exemption(repo_root, rel_path)
    if exempt or route is None:
        return

    if skill == "coordinator:sizing":
        next_action = _ROUTE_TERMINAL.get(route)
        if next_action is not None:
            _ledger.open_obligation(
                session_id, _SEAM_SIZING_ROUTED, _SEAM_SIZING_ROUTED, next_action
            )
        return

    # route == "plan" -- only the FULL "plan" terminal opens this obligation; "spec-dispatch"
    # (or any other route) does not.
    if route == "plan":
        _ledger.open_obligation(
            session_id, _SEAM_PLAN_REVIEW, _SEAM_PLAN_REVIEW, _REVIEW_TERMINAL
        )


def _handle_stop(payload: dict) -> int:
    if payload.get("agent_id"):
        return 0
    if payload.get("stop_hook_active"):
        return 0  # avoid re-entering on our own already-fired Stop

    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return 0

    # Fold the engine plane's obligations-inbound rows BEFORE the read. The intake exists so
    # that only one plane ever rewrites this ledger; folding here is what makes an
    # engine-resolved obligation reachable by this Stop read at all. It never raises and a
    # deferred drain simply leaves the rows for the next one.
    try:
        _ledger.drain_intake(session_id)
    except Exception:  # noqa: BLE001
        pass

    record = _ledger.find_undischarged_unfired(session_id)
    if record is None:
        return 0

    next_action = record.get("next_action")
    obligation_id = record.get("obligation_id")
    if not isinstance(next_action, str) or not next_action or not isinstance(obligation_id, str):
        return 0

    text = (
        "[watchdog] An earlier turn resolved a next move that was never "
        f"invoked ({record.get('seam', 'unknown-seam')}). Invoke it now: "
        f"{next_action}\n"
    )

    # A failed latch write must degrade to a silent miss, never a repeat fire; a repeat is
    # worse than a miss.
    if not _ledger.mark_fired(session_id, obligation_id):
        return 0

    try:
        posture = resolve_posture()
    except Exception:
        posture = "precision"

    if posture in ("default", "substrate-free"):
        repo_root = _repo_root(payload)
        if repo_root is not None:
            nonce = _record_fire(
                repo_root, session_id, "watchdog-undischarged-next-move", text
            )
        else:
            nonce = None
        if nonce is not None:
            discharge_note = (
                f"Recorded as {nonce}. When you have acted on this, run:\n"
                f'  block-discharge record --nonce {nonce} '
                f'--action "<what you did>" --repo-root "{repo_root}"\n'
            )
        else:
            discharge_note = (
                f"Could not record this fire (engine unresolvable or write failed) at "
                f"state/block-discharge/{session_id}.jsonl.\n"
                "No nonce to discharge -- this failure is visible in stderr, not "
                "laundered into a clean check.\n"
            )
            sys.stderr.write(
                "[watchdog] watchdog-undischarged-next-move: record_fire write "
                "failed, no nonce minted\n"
            )
        sys.stderr.write(text + discharge_note)
        return 2

    sys.stdout.write(text)
    return 0


def main() -> int:
    try:
        raw = sys.stdin.read()
    except Exception:
        return 0

    try:
        payload = json.loads(raw) if raw else {}
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}

    try:
        if isinstance(payload.get("tool_name"), str):
            _handle_post_tool_use(payload)
            return 0
        if "transcript_path" in payload:
            return _handle_stop(payload)
    except Exception:
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
