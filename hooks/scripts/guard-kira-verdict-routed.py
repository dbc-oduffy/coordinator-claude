"""Stop-hook guard -- hard-stop a close whose Kira (overengineering-reviewer)
verdict was never routed anywhere.

Spec: docs/plans/2026-09-27-review-inside-execute-plan.md (chunk C5).
Historical spec: docs/plans/2026-08-30-kira-verdict-routing-join-key.md
(chunk C5). Dispatch brief: state/dispatch-briefs/2026-08-30-kira-verdict-
routing-join-key/C5.md

THE PROBLEM. `/workstream-complete` doctrine is emphatic that Kira fires on
every close, that her findings route through `review-integrator`
unconditionally, and that a `rebuild_recommended: true` verdict routes
instead to an executor carrying a refactor remit -- but none of that was
ever mechanical. C1 gave Kira a terminal-stamp contract (`findings_count`
and the `rebuild_recommended`/`rebuild_rationale`/`rebuild_scope` delta,
lifted to top-level frontmatter); C2/C3 gave review-integrator and the
refactor executor route an `integrated_from` stamp naming the Kira
sidecar(s) they answered; C4 typed all of it in
`review-findings.schema.json`. This module is the first thing that
actually READS those stamps and can hard-stop a close that skipped the
routing they encode. See spec for the full stamp shape -- this guard's
own read set is exactly the five facts named below.

WHY `stop-dispatch.py`, NOT `postuse-stop-family-dispatch.py`. The latter is
registered on PostToolUse and gated by `GuardScopeDescriptor` file-path
matching against `tool_input.file_path` -- a session-level predicate like
this one has no file-path key to match, so an entry there registers cleanly
and then fires zero times, forever (see
`docs/research/spike-verdicts/2026-08-29-six-detectors-onto-stop-family-runner.md`,
verdict `not-viable`, for exactly this enrolment shape already having been
tried once). `stop-dispatch.py` is the single Stop entrypoint: its `main()`
returns 2 if any registered `StopGuard` fires, which IS the hard stop this
guard exists to deliver.

TRIGGER SCOPE -- why this must not fire on every Stop. Every peer blocking
guard already registered in `stop-dispatch.py` (`_pre_manufactured_blocker`,
`_pre_em_report_altitude`) begins its precondition with the same two-leg
check this guard's `main()` repeats: `agent_id` present means this Stop
belongs to a SUBAGENT, not the EM -- including Kira's own Stop, before any
integrator could possibly have run yet -- and `stop_hook_active` means this
is a re-entrant Stop the platform is already replaying, where re-blocking
would spin past `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP` rather than deliver a
one-shot-per-turn block. Both legs are the platform contract for any
blocking Stop hook (`claude-code-platform-gotchas.md:790`), not an
implementation detail this module could shortcut.

BOUNDED PICKUP CHAIN. `/coordinator:pickup` continues another session's
review chain, and Kira's sidecar can then sit in the authoring session's
share dir rather than the picking-up session's own -- the picking-up
session's integrator sidecar stamps a correct `integrated_from` naming a
stem `_find_answers` cannot resolve without also looking there, and
condition 1 fires on every close as a false block (memo, confirmed; see
docs/plans/2026-09-09-inbox-blitz-xs-s-bundle-21-fixes.md § C14). The
reach is BOUNDED to exactly the other session-ids named on the ONE
handoff record under `state/handoffs/` whose `consumed_by` or
`claimed_by` contains this Stop's own `session_id` -- resolved from that
record, never from a filesystem scan. No record found, or no other
session-id on it, means the reachable set is empty and this guard behaves
exactly as it does with no chain at all -- the non-pickup case is
byte-identical to prior behaviour. `os.listdir` is still called only on
`<share_root>/subagent-share/<session_id>` paths, one per `(root,
session_id)` pair, now with the session-ids enumerated across the chain
rather than singular; there is no scan of `subagent-share/` itself and no
glob.

CONTRACT_EPOCH -- narrow by construction. The epoch filter applies
identically to every sidecar this guard reaches, whether from the current
session's own share dir or a chain-resolved predecessor's (see BOUNDED
PICKUP CHAIN above): `_postdates_epoch` draws the same line regardless of
which session-id supplied the dir, and still fails toward in-scope on a
missing `spawned_at`. The closing window this epoch exists to retire is
now "a chain whose predecessor session opened before 2026-08-30," not
merely "this session opened before 2026-08-30" -- delete
`_CONTRACT_EPOCH_ISO` and `_postdates_epoch` once no session predating
that date, nor any predecessor reachable through a chain, can still
close.

THE DECISION -- from frontmatter only, review-integrator retired
(docs/plans/2026-09-26-retire-review-integrator.md). Kira now runs inside
every execute-review wave (parallel, findings-only) rather than once at
/workstream-complete; her sidecar lands in the EM session's own share dir,
which `compose-review-wave` provisions. Both conditions below are decided
from column-zero frontmatter keys alone -- no body read of any kind.
  1. No Kira sidecar in the session share dir, but other review activity
     is present -> BLOCK (a close that reviewed something owed Kira a run
     too). A PLAN review never counts as that "something": Kira reviews the
     CODE diff in the execute workflow, never a plan, so a sidecar whose
     `plan:` field points at `docs/plans/*.md`, an `apm` agent_type, or a
     review-integrator-shaped run that answered only such sidecars, is
     excluded from this condition's detection (`_is_plan_review`,
     `_block_condition_1`). Predicate unchanged from the prior spec.
  2. A Kira sidecar carrying `findings_count > 0` with no answer -> BLOCK.
     Reviewers apply their own findings in place ("Apply, Then Ledger, Then
     Verify" -- coordinator/agents/overengineering-reviewer.md); a verified
     `findings_ledger` stamped on the Kira sidecar's OWN frontmatter
     (`_has_verified_ledger`) is therefore an answer by itself -- no sibling
     sidecar is required to name it. The remaining answers, now that
     review-integrator has retired: a sibling sidecar stamping
     `agent_type: coordinator:code-reviewer`, whose `integrated_from` names
     this Kira stem, AND whose frontmatter carries a verified
     `findings_ledger` (the `review-findings-ledger verify` terminal stamp
     -- `verify` writes this key on a passing run only, so its bare
     PRESENCE in this guard's flat, column-zero-only parse is proof enough;
     see `_read_frontmatter`'s nested-block handling); OR a sibling naming
     this stem via `integrated_from` that is NOT itself a retired
     review-integrator (the schema's sole remaining writer of that field
     besides code-reviewer is the rebuild-route executor -- see
     `review-findings.schema.json`'s `integrated_from` description).
     Nothing else answers: a `## Integrator Dispositions` body heading and
     a `review-integrator` `agent_type` both stop being answers -- the
     agent and the heading it wrote are retired together. The owed route
     is named unconditionally in the message (the execute-review
     integration pass, or a rebuild executor if the verdict recommended a
     rebuild) -- an unanswered ordinary verdict and an unanswered rebuild
     verdict are the same failure: an unrouted Kira sidecar.

A third condition -- blocking a rebuild verdict answered by BOTH a
code-reviewer and a refactor executor -- was cut (staff-eng review,
2026-08-30): it could only fire when both answering agents had already
stamped `integrated_from` correctly, which is the exact compliance whose
absence is the problem this guard exists to catch; condition 2 already
covers the unanswered case.

NO WARN TIER, NO ENV ESCAPE, NO `--force`. If the guard seems to need an off
switch the design is wrong -- widen the epoch or the detection instead of
adding one.

Contract:
  stdin   -- Stop JSON (session_id, transcript_path, cwd, stop_hook_active, agent_id...)
  stdout  -- a could-not-evaluate advisory breadcrumb on a fail-open path
             only (stdin unreadable, repo root unresolvable, share dir
             unlistable); silent on every clean-pass or BLOCK outcome
  stderr  -- the BLOCK message, only when the guard fires
  exit 2  -- an unrouted (or over-routed) Kira verdict was found this Stop
  exit 0  -- every other path, including every failure path (fail-open)

Graceful degradation: any failure to read stdin, resolve the repo root, or
list/parse the session share directory falls through to a silent exit 0 --
this guard can only ever block on a POSITIVELY-read fact, never on its own
inability to read one.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_LIB_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir, "lib")
)
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from frontmatter_scan import read_text, scan_frontmatter  # noqa: E402
from _machine_profile import guard_level  # noqa: E402
from _touch_record import _touch_record_jsonl_paths, _touched_txt_paths  # noqa: E402

try:
    from _git_root_walk import git_root_walk  # noqa: E402
except Exception:  # import failure degrades to the "cannot evaluate" path
    def git_root_walk(start=None):  # type: ignore[misc]
        return None


# docstring's CONTRACT_EPOCH section. Delete this constant and
_CONTRACT_EPOCH_ISO = "2026-08-30T00:00:00Z"

_KIRA_AGENT_TYPE = "overengineering-reviewer"

_SHARE_ROOTS = (".coordinator-local", "state")


def _record_fire(repo_root: str, session_id: str, guard: str, reason: str) -> str | None:
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


def _repo_root(payload: dict) -> str | None:
    cwd = payload.get("cwd") or os.getcwd()
    if not isinstance(cwd, str):
        return None
    return git_root_walk(cwd)


def _read_frontmatter(path: str) -> dict:
    """Top-level frontmatter keys via the shared `frontmatter_scan` helper.

    Only COLUMN-ZERO keys are read (an indented key, e.g. one nested under
    `divergence:`, is never surfaced as a top-level fact -- the same
    column-zero discipline C1's terminal-stamp contract itself requires of
    the writer). Returns `{}` on any read/shape failure -- a guard that
    cannot prove a fact must never block on it.
    """
    return scan_frontmatter(read_text(path))


def _handoff_field_values(meta: dict, key: str) -> list[str]:
    val = meta.get(key)
    if isinstance(val, list):
        return [v for v in val if isinstance(v, str) and v.strip()]
    if isinstance(val, str) and val.strip():
        return [val.strip()]
    return []


def _pickup_chain_session_ids(repo_root: str, session_id: str) -> list[str]:
    handoffs_dir = os.path.join(repo_root, "state", "handoffs")
    try:
        names = sorted(os.listdir(handoffs_dir))
    except OSError:
        return []
    for name in names:
        if not name.endswith(".md"):
            continue
        meta = _read_frontmatter(os.path.join(handoffs_dir, name))
        consumed = _handoff_field_values(meta, "consumed_by")
        claimed = _handoff_field_values(meta, "claimed_by")
        if session_id not in consumed and session_id not in claimed:
            continue
        others: list[str] = []
        seen: set[str] = set()
        for sid in consumed + claimed:
            if sid == session_id or sid in seen:
                continue
            seen.add(sid)
            others.append(sid)
        return others
    return []


def _postdates_epoch(meta: dict) -> bool:
    """True unless `spawned_at` is present AND strictly precedes
    `_CONTRACT_EPOCH_ISO` -- see the module docstring's CONTRACT_EPOCH
    section for why a MISSING `spawned_at` fails toward in-scope rather
    than toward a free pass."""
    spawned = meta.get("spawned_at")
    if not isinstance(spawned, str) or not spawned:
        return True
    return spawned >= _CONTRACT_EPOCH_ISO


def _to_int(value) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _kira_stem(filename: str) -> str:
    return filename[:-3] if filename.endswith(".md") else filename


def _normalize_agent_type(agent_type) -> str | None:
    if not isinstance(agent_type, str) or not agent_type:
        return None
    if ":" in agent_type:
        return agent_type.split(":", 1)[1]
    return agent_type


def _is_kira(filename: str, meta: dict) -> bool:
    """Decided ENTIRELY from the stamped `agent_type` frontmatter field --
    no filename fallback. A sidecar with no `agent_type` is a fact this
    guard cannot prove and must not act on (staff-eng finding 2, 2026-08-30:
    the filename leg was the only path that ever fired on real data, and
    only for `.blocks.md` contract scaffolds that carry no frontmatter at
    all -- see the share-dir listing's `.blocks.md` exclusion below)."""
    return _normalize_agent_type(meta.get("agent_type")) == _KIRA_AGENT_TYPE


def _reviewed_a_plan(meta: dict) -> bool:
    """True when this sidecar's `plan:` field -- the sidecar-frontmatter-
    contract's reviewed-artifact-path, stamped by every review persona
    regardless of what it actually reviewed -- names an actual plan
    document under `docs/plans/`, not a code diff, handoff, or other
    artifact wearing the same generic key. Kira's own sidecars stamp
    `plan:` too (a session diff, a handoff -- confirmed on disk,
    `coordinatoroverengineering-reviewer.abfb416965388dd5f.md`), so the
    key's mere PRESENCE proves nothing; the path is what says PLAN."""
    plan = meta.get("plan")
    if isinstance(plan, list):
        plan = plan[0] if plan else None
    if not isinstance(plan, str) or not plan.strip():
        return False
    normalized = plan.strip().strip("'\"").replace("\\", "/")
    return "docs/plans/" in normalized and normalized.endswith(".md")


def _is_plan_review(meta: dict) -> bool:
    return _reviewed_a_plan(meta) or _normalize_agent_type(meta.get("agent_type")) == "apm"


def _integrated_from_list(meta: dict) -> list[str]:
    integrated = meta.get("integrated_from")
    if isinstance(integrated, str):
        return [integrated] if integrated.strip() else []
    if isinstance(integrated, list):
        return [v for v in integrated if isinstance(v, str) and v.strip()]
    return []


def _is_review_activity(filename: str, meta: dict) -> bool:
    if _is_plan_review(meta):
        return False
    if "findings_count" in meta:
        return True
    kind = meta.get("kind")
    if kind in ("review-findings", "staff-eng-review"):
        return True
    agent_type = meta.get("agent_type", "")
    if isinstance(agent_type, str) and "review" in agent_type.lower():
        return True
    return "review" in filename.lower()


def _block_condition_1(in_scope: list[tuple[str, dict]]) -> bool:
    kira_present = any(_is_kira(f, m) for f, m in in_scope)
    if kira_present:
        return False

    plan_review_names: set[str] = set()
    for f, m in in_scope:
        if _is_plan_review(m):
            plan_review_names.add(f)
            plan_review_names.add(_kira_stem(f))

    def _counts_as_review(f: str, m: dict) -> bool:
        if _is_kira(f, m):
            return False
        if not _is_review_activity(f, m):
            return False
        integrated = _integrated_from_list(m)
        if integrated and all(name in plan_review_names for name in integrated):
            return False
        return True

    return any(_counts_as_review(f, m) for f, m in in_scope)


def _find_answers(kira_filename: str, in_scope: list[tuple[str, dict]]) -> list[str]:
    """Filenames of sibling sidecars whose `integrated_from` names this Kira
    stem AND which count as an answer under the retired-review-integrator
    contract (`_counts_as_answer`)."""
    stem = _kira_stem(kira_filename)
    answers: list[str] = []
    for f, m in in_scope:
        if f == kira_filename:
            continue
        integrated = m.get("integrated_from")
        if isinstance(integrated, str):
            integrated = [integrated] if integrated.strip() else []
        if not isinstance(integrated, list):
            continue
        if stem not in integrated and kira_filename not in integrated:
            continue
        if not _counts_as_answer(m):
            continue
        answers.append(f)
    return answers


def _has_verified_ledger(meta: dict) -> bool:
    """True when this sidecar's OWN frontmatter carries a non-empty
    `findings_ledger:` stamp (written by `review_findings_ledger.verify`,
    docs/plans/2026-09-26-retire-review-integrator.md row M4). A verified
    ledger on Kira's own sidecar satisfies routing directly -- it never
    needs a separate sibling sidecar to name it via `integrated_from`."""
    value = meta.get("findings_ledger")
    if isinstance(value, list):
        return bool(value)
    return isinstance(value, str) and bool(value.strip())


_CODE_REVIEWER_AGENT_TYPE = "code-reviewer"
_RETIRED_INTEGRATOR_AGENT_TYPE = "review-integrator"


def _counts_as_answer(meta: dict) -> bool:
    """review-integrator retired (docs/plans/2026-09-26-retire-review-
    integrator.md): its own `integrated_from` stamp, and the `## Integrator
    Dispositions` body heading it used to write, both stop being answers.
    The two remaining answers, per `review-findings.schema.json`'s
    `integrated_from` description: a code-reviewer sidecar whose findings
    were VERIFIED (`findings_ledger` present -- `review-findings-ledger
    verify` writes that key on a passing run only), or the rebuild-route
    executor -- the schema's sole other writer of `integrated_from`."""
    agent_type = _normalize_agent_type(meta.get("agent_type"))
    if agent_type == _RETIRED_INTEGRATOR_AGENT_TYPE:
        return False
    if agent_type == _CODE_REVIEWER_AGENT_TYPE:
        return "findings_ledger" in meta
    return True


_LIVE_JOURNAL_SECONDS = 2 * 60 * 60


def _live_workflow_runs(transcript_path) -> list[str]:
    if not isinstance(transcript_path, str) or not transcript_path.endswith(".jsonl"):
        return []
    base = os.path.join(transcript_path[: -len(".jsonl")], "subagents", "workflows")
    try:
        runs = os.listdir(base)
    except OSError:
        return []
    live = []
    for run in runs:
        journal = os.path.join(base, run, "journal.jsonl")
        try:
            if time.time() - os.path.getmtime(journal) > _LIVE_JOURNAL_SECONDS:
                continue
            started, finished = set(), set()
            with open(journal, encoding="utf-8") as fh:
                for line in fh:
                    try:
                        rec = json.loads(line)
                    except ValueError:
                        continue
                    if rec.get("type") == "started":
                        started.add(rec.get("agentId"))
                    elif rec.get("type") == "result":
                        finished.add(rec.get("agentId"))
        except OSError:
            continue
        if started - finished:
            live.append(run)
    return sorted(live)


_BLOCK_HEADER = (
    "[guard] This close carries an unrouted Kira (overengineering-reviewer) "
    "verdict.\n"
)


def _emit_block(reasons: list[str], repo_root: str, session_id: str) -> int:
    nonce = _record_fire(
        repo_root, session_id, "guard-kira-verdict-routed", "\n".join(reasons)
    )
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
            "[guard] guard-kira-verdict-routed: record_fire write failed, "
            "no nonce minted\n"
        )
    sys.stderr.write(_BLOCK_HEADER + "\n".join(reasons) + "\n" + discharge_note)
    return 2


_GUARD_ID = "guard-kira-verdict-routed"
_SIZING_PATH_RE = re.compile(r"^state/sizings/[^/]+\.ya?ml$")


def _session_route_is_xs_dispatch(repo_root: str, session_id: str) -> bool:
    """True when the newest sizing object this session touched is route
    `dispatch` at t-shirt XS (EM-inline work: no Kira close is owed)."""
    try:
        from _git_common_dir import resolve_git_common_dir

        git_dir = resolve_git_common_dir(repo_root)
        if not git_dir:
            return False
        session_dir = os.path.join(git_dir, "coordinator-sessions", session_id)
        rels = [r for r in _touch_record_jsonl_paths(session_dir) if _SIZING_PATH_RE.match(r)]
        if not rels:
            rels = [r for r in _touched_txt_paths(session_dir) if _SIZING_PATH_RE.match(r)]
        if not rels:
            return False
        text = read_text(os.path.join(repo_root, rels[-1])) or ""
        route = re.search(r"^route:\s*(\S+)", text, re.M)
        tshirt = re.search(r"^\s+tshirt:\s*(\S+)", text, re.M)
        return bool(route and tshirt and route.group(1) == "dispatch" and tshirt.group(1) == "XS")
    except Exception:
        return False


def _emit_could_not_evaluate(reason: str) -> None:
    sys.stdout.write(f"[guard] guard-kira-verdict-routed could not evaluate: {reason}\n")


def main() -> int:
    try:
        raw = sys.stdin.read()
    except Exception:
        _emit_could_not_evaluate("failed to read stdin")
        return 0

    try:
        payload = json.loads(raw) if raw else {}
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        _emit_could_not_evaluate("stdin was not valid JSON")
        return 0

    if payload.get("agent_id"):
        return 0
    if payload.get("stop_hook_active"):
        return 0

    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id.strip():
        _emit_could_not_evaluate("no session_id in the Stop payload")
        return 0

    repo_root = _repo_root(payload)
    if repo_root is None:
        _emit_could_not_evaluate("could not resolve repo root from cwd")
        return 0

    level = guard_level(_GUARD_ID)
    if level == "off":
        return 0
    if _session_route_is_xs_dispatch(repo_root, session_id):
        return 0

    chain_session_ids = _pickup_chain_session_ids(repo_root, session_id)
    share_dirs = [
        os.path.join(repo_root, root, "subagent-share", sid)
        for root in _SHARE_ROOTS
        for sid in (session_id, *chain_session_ids)
    ]
    listed: list[tuple[str, str]] = []
    seen: set[str] = set()
    unreadable: list[str] = []
    for share_dir in share_dirs:
        try:
            names = os.listdir(share_dir)
        except OSError:
            unreadable.append(share_dir)
            continue
        for f in sorted(names):
            if not f.endswith(".md") or f.endswith(".blocks.md"):
                continue
            if f in seen:
                continue
            seen.add(f)
            listed.append((f, os.path.join(share_dir, f)))

    if len(unreadable) == len(share_dirs):
        _emit_could_not_evaluate(
            "could not list any share dir: " + ", ".join(unreadable)
        )
        return 0

    entries: list[tuple[str, dict]] = []
    for fname, fpath in listed:
        entries.append((fname, _read_frontmatter(fpath)))

    if not entries:
        return 0

    # CONTRACT_EPOCH scoping applies uniformly across every condition below
    in_scope = [(f, m) for f, m in entries if _postdates_epoch(m)]
    if not in_scope:
        return 0

    reasons: list[str] = []

    if _block_condition_1(in_scope):
        reasons.append(
            "- Other review activity ran this session, but no Kira "
            "(overengineering-reviewer) sidecar is present. Kira fires on "
            "every close (SKILL.md); dispatch her before closing."
        )

    kira_entries = [(f, m) for f, m in in_scope if _is_kira(f, m)]
    live_runs = _live_workflow_runs(payload.get("transcript_path"))
    if live_runs and kira_entries:
        sys.stdout.write(
            f"[guard] guard-kira-verdict-routed deferred: workflow run(s) {', '.join(live_runs)} "
            "still in flight; their integrators route these verdicts. Evaluated at the first "
            "Stop after they land.\n"
        )
        kira_entries = []
    for kira_file, kira_meta in kira_entries:
        findings_count = _to_int(kira_meta.get("findings_count"))
        if findings_count is not None and findings_count > 0 and _has_verified_ledger(kira_meta):
            continue
        answers = _find_answers(kira_file, in_scope)

        if findings_count is not None and findings_count > 0 and not answers:
            reasons.append(
                f"- {kira_file} stamps findings_count={findings_count} with no "
                f"sibling sidecar's integrated_from naming it. Owed route: the "
                f"execute-review integration pass -- a code-reviewer sidecar "
                f"naming {_kira_stem(kira_file)} in its own `integrated_from` "
                f"and carrying a verified `findings_ledger` (`review-findings-"
                f"ledger verify --sidecar <that sidecar>`) -- or a refactor "
                f"executor if the verdict recommended a rebuild."
            )

    if not reasons:
        return 0

    if level == "warn":
        sys.stdout.write(
            _BLOCK_HEADER.replace("[guard]", f"[guard] Advisory ({_GUARD_ID}, level warn):", 1)
            + "\n".join(reasons)
            + "\nAllowed at guard_level warn. Stricter: `machine-local set "
            "coordinator.guard_level strict`; silence: `machine-local set "
            f"coordinator.guard_level.{_GUARD_ID} off`.\n"
        )
        return 0

    return _emit_block(reasons, repo_root, session_id)


if __name__ == "__main__":
    sys.exit(main())
