#!/usr/bin/env python3
"""mise-prep-entry — mise-prep's entry query over plan-blitz's exit. Writes nothing.

WHY THIS EXISTS. `plan-blitz` lands a wave and stops at *ready to execute*. Its exit is complete
and correct: `roadmap.blitz_land` has stamped each ready plan `approved` and linked it to its
baton. mise-prep's entry is complete and correct too: `plan.prep_gate` takes one plan path and
returns a verdict. Between them, nothing — and so an EM reads the landing report, picks the plan
paths out of it, and types them one at a time into the next ceremony. Both halves shipped; the
JOIN is a retype. This module is the join: ONE read that answers what the landing left and what
each of those plans' certification state is, so the next ceremony's entry is a query rather than
an EM assembly step. Tripwire: `A-HANDOFF-AN-EM-RETYPES-IS-NOT-A-SEAM`.

Measured against this repo's real corpus (process time, not wall clock — `resource.getrusage`
user+sys; re-measured 2026-09-08, Review: code-reviewer, 2026-09-08-hoexec-close/mise-prep-entry
Finding 4 — the prior 7-baton/0.28s figures had drifted): `assemble_plan_gate` reports **9** batons
whose linked plan is at `status: approved`, in 0.07s process time; the four-state attest read over
those 9 costs a further 0.02s; and `aggregate_execution` — the payload the run's Phase 0a consumes,
schema-valid and required-keys since it shipped — exists **zero** times on disk. A shape no surface
produces is never populated, which is what an unwelded seam looks like from the outside. The
unwelded seam is one of two reasons and was never the whole of it: until handoff.schema.json
10.2.0 the block's kind-gate admitted `roadmap-baton` alone, and this module's entry set is
cluster-less by construction — `--roadmap-id` is an OPTIONAL narrowing, so constituents are drawn
across clusters and mostly from batons carrying no `roadmap_id` at all. An aggregate over that set
now mints as `kind: spinoff` (DR-198(a));
`coordinator/docs/wiki/aggregate-execution-baton.md` § Minting one is the table.

WHOSE MODULE THIS IS. mise-prep's, not plan-blitz's. It is sited beside the exit it reads because
that is where the exit's shape is owned — the same siting `roadmap.plan_gate`'s own spec backlink
takes, pointing at `plan-blitz/SKILL.md § The two gates`. It opens nothing: it reports what a
downstream gate would say, which is the read half of the read-twin/write-twin pair and is exactly
what `plan-blitz`'s anti-scope permits. *"It reports; it never refuses. Refusal is yours."*

THE TWO LEGS, and why neither is transcribed here:

  SEAM 1  `coordinator_core.roadmap.plan_gate :: assemble_plan_gate` -> `batons[]`, filtered to
          `plan.status == "approved"`. The engine already computes this gate; re-deriving approval
          from plan frontmatter would be a second answer to a settled question, which is the
          defect `plan-blitz`'s own "never hand-derive either" rule names.
  SEAM 2  `coordinator/skills/pickup/aggregate-rollup.py :: certification_state` -> the four-state
          attest read over each plan's own bytes. Imported, never re-transcribed: the recomputed
          body sha already exists twice (there, and in the engine), and a third copy is how one of
          them drifts.

THE PREDICATE IS THE RECOMPUTED SHA, NEVER THE PRESENCE OF `mise_prepped_by`. In a chained world
the stamp-to-fire window is wide by construction — planning runs waves ahead of execution — so a
stale stamp is the normal case, not an edge case. STALE and UNSTAMPED route to different repairs
and are named separately here for that reason: a reader told "not certified" re-stamps, a reader
told "the body changed" re-gates, and the wrong repair re-stamps a plan whose defects were never
re-checked.

NO NEW VOCABULARY. Every word this module prints is already in service: `CERTIFIED`/`STALE`/
`UNSTAMPED`/`MALFORMED` are the attest's four consumer states, and `FIRE`/`PARTIAL-FIRE`/
`NO-FIRE` are the aggregate roll-up's three verdicts, with its exit codes. A fourth vocabulary at
a seam is roadmap anti-scope.

Negative-spec:
  - Does NOT write, stamp, mint, or mutate anything — not a plan, not a baton, not a record. The
    write halves are `plan.stamp_prepped` (the attest) and whatever mints an aggregate baton; both
    belong to the plane that owns the record, and a read twin that started writing would be a
    second record-minting authority nobody ratified.
  - Does NOT fire, dispatch, or open a gate. It reports what a gate would say. `plan-blitz`'s
    anti-scope is preserved, not amended.
  - Does NOT spawn a subprocess and does NOT shell out. Both legs are pure reads; the body sha is
    sha1 over bytes, and a process creation costs 25.3ms to compute what sha1 already answers.
  - Does NOT re-run a plan's `census[]` commands. That is the fire-time census leg and it is the
    RUNNER's, ordered strictly after the sha leg — which is the whole reason the command is
    recorded rather than the answer alone.
  - Does NOT run the authoring bar. The bar is the step BEFORE stamping and its verdict is not an
    entry need; the repair line names the bar's own resolved path and stops there.
  - Does NOT re-derive the claimed / `in_flight` exclusion. `assemble_plan_gate` applies it; a
    second exclusion vocabulary here would be a second answer to a settled question. Note that the
    exclusion is inherited and NOT tuned for certification — see § A LIMIT WORTH NAMING.
  - Does NOT decide what to fire. It reports the set; invoking the run is the operator's act, and
    keeping that one call explicit is what makes a runaway chain impossible.

A LIMIT WORTH NAMING, rather than discovered later. `assemble_plan_gate`'s candidate filter is a
PLANNING filter: a baton at `status: claimed` or `deployment_state: in_flight` is excluded because
handing it to a planning wave races its holder. A certification queue keyed on that filter
inherits an exclusion that was never about certification, so a plan approved and then claimed
drops out of this report silently. Correct immediately after a landing, where the batons are still
`awaiting_gate`; a real gap for a queue re-read days later. Pass `--all-batons` to widen the
report to every baton the engine resolved, at the cost of the race the filter exists to prevent.

Zero subprocess, stdlib plus PyYAML plus two pure readers already in the tree.

Exit status is a verdict, not a diagnostic, because the caller of this read is a gate, and because
the partial case must be impossible to mistake for the complete one: 0 when every approved plan
certifies with nothing withheld (FIRE), 1 when at least one certifies and something is excluded or
withheld (PARTIAL-FIRE), 2 when nothing certifies (NO-FIRE), 3 on a usage or precondition failure.
1 is not an error — it is the honest code for a partial hand-over, and a caller treating 0 as
"ready" therefore cannot read a partial one as complete.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Optional

_SCRIPT_DIR = Path(__file__).resolve().parent
_PLUGIN_ROOT = _SCRIPT_DIR.parent.parent
_REPO_ROOT = _PLUGIN_ROOT.parent
_HOOKS_SCRIPTS_DIR = _PLUGIN_ROOT / "hooks" / "scripts"
_ROLLUP_PATH = _PLUGIN_ROOT / "skills" / "pickup" / "aggregate-rollup.py"

FIRE = "FIRE"
PARTIAL_FIRE = "PARTIAL-FIRE"
NO_FIRE = "NO-FIRE"

EXIT_FIRE = 0
EXIT_PARTIAL_FIRE = 1
EXIT_NO_FIRE = 2
EXIT_USAGE = 3

#: The plan status that IS plan-blitz's exit. `blitz_land :: approve_ready` writes it, and it is
#: what opens the next wave's planning gates — never an execution gate.
APPROVED = "approved"

#: One repair per non-certified state, keyed by the state's own name. The four repairs differ, and
#: a report that said "not certified" for all four would send three of the four authors to the
#: wrong one.
_REPAIR = {
    "UNSTAMPED": "gate and stamp: {gate}",
    "STALE": "body moved after the stamp — re-gate, then re-stamp: {gate}",
    "MALFORMED": "hand-written stamp — repair the four mise_prepped_* fields in {target}",
}

#: The authoring bar every repair above routes to. A PLUGIN-LOCAL sibling, so it self-resolves off
#: the plugin root — rung 3 of `snippets/resolve-coordinator-bin.md` — rather than through the
#: engine seam the bar itself uses for ITS forward reference. Absolute by construction, because
#: this read's whole purpose is running over a CONSUMER repo (`--repo-root`), and the DoE-relative
#: literal `coordinator/bin/mise-prep-gate.py` these repairs used to print resolves nowhere there.
#: Measured on project-rag-ue-addon: 4 of 4 excluded plans routed to a path absent both in that
#: repo and in the `~/.claude` plugin mirror. Same defect, same repair, one surface over from
#: `mise-prep-gate.py :: _mise_prep_upgrade_fix_line` — which is why the pin below is the
#: generalising one, not another dead-literal assertion.
_GATE_PATH = _PLUGIN_ROOT / "bin" / "mise-prep-gate.py"


def _gate_cmd(plan: str, repo_root: Optional[Path]) -> str:
    """The bar's invocation for ONE plan, runnable from any cwd.

    Carries `--repo-root` because `plan` is repo-relative: without it the printed line runs only
    from inside the very repo the reader may not be standing in, which is the same unresolvable
    remediation one argument along. Fail-open, and never a silent guess — an absent bar is
    reported as unnamed rather than papered over with a path that is not there."""
    if not _GATE_PATH.is_file():
        return ("[cannot name the authoring bar — mise-prep-gate.py is not present beside this "
                "read; reinstall coordinator-claude, then rerun]")
    root = f"--repo-root {repo_root} " if repo_root else ""
    return f"python {_GATE_PATH} {root}{plan}"


def _repair_line(state: str, plan: str, repo_root: Optional[Path]) -> Optional[str]:
    """The repair for one non-certified state, or None where the state carries none."""
    template = _REPAIR.get(state)
    if template is None:
        return None
    target = str(repo_root / plan) if repo_root else plan
    return template.format(gate=_gate_cmd(plan, repo_root), target=target)


class SeamError(RuntimeError):
    """A fail-loud precondition. `main()` prints `str(exc)` and exits `EXIT_USAGE` — this read
    never returns an empty fire set it could not actually compute. An empty set and an unanswerable
    question look identical downstream, and the second one must never read as the first."""


def _load_module(path: Path, name: str):
    """Import a hyphenated sibling by path. `aggregate-rollup.py` is not an importable module
    name, and copying its ten-line sha recipe here instead would make a third home for one fact."""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SeamError(f"unimportable: {path}")
    module = importlib.util.module_from_spec(spec)
    try:
        # Review: code-reviewer (2026-09-08-hoexec-close/mise-prep-entry, Finding 1 site 3) —
        # exec_module was unguarded: `spec_from_file_location` returns a non-None spec/loader
        # even for a path that does not exist, so a missing/renamed sibling (e.g.
        # aggregate-rollup.py) raised a bare FileNotFoundError here, escaping main()'s
        # `except SeamError` and exiting 1 via Python's default handler — indistinguishable
        # from a legitimate PARTIAL-FIRE.
        spec.loader.exec_module(module)
    except Exception as exc:
        raise SeamError(f"unimportable: {path} ({exc})")
    return module


def _engine_plan_gate():
    """`assemble_plan_gate`, through the shared `_engine_root` seam.

    The SAME seam `mise-prep-gate.py` and `emit-dispatch-workflow.py` resolve through,
    deliberately: a second resolution order would let this read and the bar disagree about which
    engine answered, and a seam whose reply depends on that is not a seam."""
    if str(_HOOKS_SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(_HOOKS_SCRIPTS_DIR))
    try:
        from _engine_root import resolve_claude_klabauter_root
    except Exception as exc:  # pragma: no cover - import-shape guard
        raise SeamError(f"coordinator_core unreachable: _engine_root unimportable ({exc})")
    root = resolve_claude_klabauter_root()
    if not root:
        raise SeamError(
            "coordinator_core unreachable: could not resolve the engine root "
            "(set REPO_CLAUDE_KLABAUTER, or COORDINATOR_ENGINE_ROOT, or register "
            "repos.claude_klabauter in machine-local)"
        )
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        from coordinator_core.roadmap.plan_gate import assemble_plan_gate
    except Exception as exc:
        raise SeamError(f"coordinator_core.roadmap.plan_gate unimportable from {root}: {exc}")
    return assemble_plan_gate


def approved_plans(repo_root: Path, roadmap_id: Optional[str] = None,
                   all_batons: bool = False) -> list:
    """SEAM 1 — plan-blitz's exit, read off disk.

    Returns `[{"workstream", "baton", "plan"}]`, one entry per baton the last landing left
    fireable. `workstream` is the baton's `stub_id` where it has one and its resolved id
    otherwise, because the aggregate payload's own `workstream` field is a name a reader
    recognises, not an internal id.

    PLAN-BLITZ HAS TWO EXITS, AND THIS READS BOTH. `status: approved` is the M/L lane's. The S
    lane exits differently and deliberately: `blitz_land` parks the spec on the baton and stamps
    it execution-ready (`handoff_phase: execution` plus the four `execution_authorized_*`
    fields), leaving the plan at `draft` BY DESIGN — the skill's own reasoning being that "if
    calling something S condemned it to the queue, the honest S got inflated to M", so sizing
    that bends toward its downstream route is corrupted sizing.

    Reading `approved` alone therefore dropped every S-lane plan from the certification set —
    silently, and disproportionately, because the S lane is the work most likely to be
    straight-dispatchable. Measured on project-rag after a 40-baton sweep: 8 plans reported
    against 25 actually fireable. The engine already computes the second arm as
    `execution_authorized`; not reading it was this seam's own version of the defect it exists
    to close.

    Deduplicated on `plan`: several batons may cite one governing plan, and firing that plan twice
    is not a composition, it is a double dispatch."""
    assemble = _engine_plan_gate()
    try:
        # Review: code-reviewer (2026-09-08-hoexec-close/mise-prep-entry, Finding 1 site 2) —
        # only `_engine_plan_gate()`'s two IMPORT-time failures were wrapped in `SeamError`; a
        # runtime exception raised while `assemble_plan_gate` walks a malformed corpus record
        # was not, and escaped uncaught to exit 1 (== EXIT_PARTIAL_FIRE). Wrapped for
        # consistency with `_engine_plan_gate()`'s own two guarded failure points.
        report = assemble(repo_root, roadmap_id=roadmap_id)
    except SeamError:
        raise
    except Exception as exc:
        raise SeamError(f"coordinator_core.roadmap.plan_gate.assemble_plan_gate failed: {exc}")
    rows, seen = [], set()
    for baton in report["batons"]:
        if not all_batons and not baton.get("candidate", True):
            continue
        plan = baton.get("plan")
        if not plan:
            continue
        approved = str(plan.get("status") or "").strip().lower() == APPROVED
        if not (approved or baton.get("execution_authorized")):
            continue
        if plan["path"] in seen:
            continue
        seen.add(plan["path"])
        rows.append({
            "workstream": baton.get("stub_id") or baton["id"],
            "baton": baton["path"],
            "plan": plan["path"],
        })
    return sorted(rows, key=lambda r: r["plan"])


def certify(repo_root: Path, rows: list) -> dict:
    """SEAM 2 — the mise-prep attest, read per plan.

    The predicate is the recomputed body sha, never the presence of `mise_prepped_by`. Returns the
    seam-2 payload verbatim: `constituents`, `uncertified`, `withheld_rows` — the three REQUIRED
    keys of `handoff.schema.json :: aggregate_execution`, plus the verdict and the fire set.

    A plan named by the gate but missing from disk is reported UNSTAMPED rather than raising: the
    seam's job is to name every excluded plan and why, and a traceback names one and drops six."""
    rollup = _load_module(_ROLLUP_PATH, "coordinator_aggregate_rollup")
    constituents, uncertified, withheld, fires = [], [], [], []
    for row in rows:
        constituents.append({"workstream": row["workstream"], "plan": row["plan"]})
        target = repo_root / row["plan"]
        try:
            text = target.read_text(encoding="utf-8")
        # Review: code-reviewer (2026-09-08-hoexec-close/mise-prep-entry, Finding 1 site 1) —
        # a non-UTF-8 plan body raises `UnicodeDecodeError`, a `ValueError` subclass, not an
        # `OSError`; it escaped this guard uncaught even though the docstring above promises
        # "reported UNSTAMPED rather than raising" for exactly this case. Widened to match the
        # promise, not converted to `SeamError`: a corrupted plan body is the same class of
        # per-plan exclusion as a missing one, not a precondition failure of the whole read.
        except (OSError, UnicodeDecodeError):
            uncertified.append({"plan": row["plan"], "state": rollup.UNSTAMPED})
            continue
        state, rows_held = rollup.certification_state(text)
        if state != rollup.CERTIFIED:
            uncertified.append({"plan": row["plan"], "state": state})
            continue
        fires.append(row)
        if rows_held:
            withheld.append({"plan": row["plan"], "rows": rows_held})
    # Review: overengineering-reviewer — the FIRE/PARTIAL-FIRE/NO-FIRE derivation is
    # aggregate-rollup's, imported rather than restated (its own docstring: "a third copy is how
    # one of them drifts").
    verdict = rollup.fire_verdict(fires, uncertified, withheld)
    return {
        "verdict": verdict,
        "fires": fires,
        "constituents": constituents,
        "uncertified": uncertified,
        "withheld_rows": withheld,
    }


def report_message(report: dict, repo_root: Optional[Path] = None) -> str:
    """The register: one fact per line, the terse alternative, no override key.

    Every non-certified plan carries its OWN repair, because the four states route four different
    ways and a single "not certified" line is the wrong noun for three of them."""
    lines = [
        f"mise-prep entry: {report['verdict']} — "
        f"{len(report['fires'])} of {len(report['constituents'])} approved plan(s) certify"
    ]
    if report["fires"]:
        for row in report["fires"]:
            lines.append(f"  fires    {row['plan']}  ({row['workstream']})")
    else:
        lines.append("  fires    nothing")
    for entry in report["uncertified"]:
        lines.append(f"  excluded {entry['plan']}  {entry['state']}")
        repair = _repair_line(entry["state"], entry["plan"], repo_root)
        if repair:
            lines.append(f"           {repair}")
    for entry in report["withheld_rows"]:
        lines.append(f"  withheld {entry['plan']}  rows {', '.join(entry['rows'])}")
    if report["verdict"] == NO_FIRE:
        lines.append("  next     nothing to hand on; the run is not invoked")
    else:
        lines.append("  next     the run fires what is listed above it; the rest rides a successor")
    return "\n".join(lines)


def emit_block(report: dict) -> str:
    """The seam-2 payload as the frontmatter block a run's Phase 0a reads.

    Emitted rather than described. A block a reader has to assemble from a description is the
    retype this module exists to delete — and `aggregate_execution` has been schema-valid, with
    three required keys, since it shipped, and exists zero times on disk.

    `[]` is written explicitly for an empty `uncertified`/`withheld_rows` — and, per the same rule,
    for an empty `constituents` (zero approved plans is a reachable state, e.g. no baton anywhere
    is at `plan.status == approved`). A declared-empty asserts that nothing was excluded; an absent
    key asserts nothing at all, and an optional exclusion list is how a quiet drop happens."""
    out = ["aggregate_execution:"]
    if report["constituents"]:
        out.append("  constituents:")
        for entry in report["constituents"]:
            out.append(f"    - workstream: {entry['workstream']}")
            out.append(f"      plan: {entry['plan']}")
    else:
        # Review: code-reviewer (2026-09-08-hoexec-close/mise-prep-entry, Finding 2) — a bare
        # `constituents:` key with no items followed was YAML `null` when parsed back, not `[]`;
        # `type: array` (the schema's own requirement) failed outright, before `minItems: 1` was
        # even reached. Declared `[]` explicitly, matching `uncertified`/`withheld_rows` below.
        # `minItems: 1` still (correctly) rejects a zero-constituent aggregate — the schema's own
        # comment: "an aggregate of nothing would validate as an execute-me baton with nothing to
        # execute" — this fix only makes the TYPE honest, never makes that case validate.
        out.append("  constituents: []")
    if report["uncertified"]:
        out.append("  uncertified:")
        for entry in report["uncertified"]:
            out.append(f"    - plan: {entry['plan']}")
            out.append(f"      state: {entry['state']}")
    else:
        out.append("  uncertified: []")
    if report["withheld_rows"]:
        out.append("  withheld_rows:")
        for entry in report["withheld_rows"]:
            rows = ", ".join(entry["rows"])
            out.append(f"    - plan: {entry['plan']}")
            out.append(f"      rows: [{rows}]")
    else:
        out.append("  withheld_rows: []")
    return "\n".join(out)


def walk(repo_root: Path, roadmap_id: Optional[str] = None, all_batons: bool = False) -> dict:
    """Both seams, one read. The composition IS the deliverable — either leg alone leaves the
    join to a reader."""
    return certify(repo_root, approved_plans(repo_root, roadmap_id, all_batons))


def _default_repo_root() -> Path:
    return _REPO_ROOT


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(
        prog="mise-prep-entry",
        description="mise-prep's entry query over plan-blitz's exit. Writes nothing.",
    )
    parser.add_argument("--roadmap-id", default=None,
                        help="narrow the candidate set to one roadmap")
    parser.add_argument("--all-batons", action="store_true",
                        help="include claimed/in_flight batons (see the module's LIMIT note)")
    parser.add_argument("--json", action="store_true", help="emit the full report as JSON")
    parser.add_argument("--emit-block", action="store_true",
                        help="emit the aggregate_execution frontmatter block")
    parser.add_argument("--repo-root", default=None, help="repo root (default: this plugin's)")
    args = parser.parse_args(argv[1:])

    repo_root = Path(args.repo_root).resolve() if args.repo_root else _default_repo_root()
    try:
        report = walk(repo_root, args.roadmap_id, args.all_batons)
    except SeamError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.emit_block:
        print(emit_block(report))
    else:
        print(report_message(report, repo_root))

    if report["verdict"] == FIRE:
        return EXIT_FIRE
    if report["verdict"] == PARTIAL_FIRE:
        return EXIT_PARTIAL_FIRE
    return EXIT_NO_FIRE


if __name__ == "__main__":
    sys.exit(main(sys.argv))
