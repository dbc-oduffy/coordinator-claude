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

WHOSE MODULE THIS IS. mise-prep's, not plan-blitz's. It reports what a downstream gate would say,
which is the read half of the read-twin/write-twin pair. *"It reports; it never refuses. Refusal
is yours."*

THE TWO LEGS, and why neither is transcribed here:

  SEAM 1  `coordinator_core.roadmap.plan_gate :: assemble_plan_gate` -> `batons[]`, filtered to
          the FIREABLE set: `plan.status == "approved"` (the M/L exit) OR the baton's
          `execution_authorized` (the S exit, whose plan stays at `draft` by design). Both arms,
          because plan-blitz has two exits — `constituents` reads "approved" nowhere in its own
          count. This module lives inside the engine, so it imports the gate directly — no seam.
  SEAM 2  `coordinator/bin/aggregate-rollup.py :: certification_state` -> the four-state
          attest read over each plan's own bytes, loaded by path from this module's own
          `coordinator/bin` sibling (arrived via docs/plans/2026-09-18-doe-holds-no-scripts.md,
          chunk W3-C7).

THE PREDICATE IS THE RECOMPUTED SHA, NEVER THE PRESENCE OF `mise_prepped_by`. In a chained world
the stamp-to-fire window is wide by construction — planning runs waves ahead of execution — so a
stale stamp is the normal case, not an edge case. STALE and UNSTAMPED route to different repairs
and are named separately here for that reason: a reader told "not certified" re-stamps, a reader
told "the body changed" re-gates, and the wrong repair re-stamps a plan whose defects were never
re-checked.

NO NEW VOCABULARY. Every word this module prints is already in service: `CERTIFIED`/`STALE`/
`UNSTAMPED`/`MALFORMED` are the attest's four consumer states, and `FIRE`/`PARTIAL-FIRE`/
`NO-FIRE` are the aggregate roll-up's three verdicts, with its exit codes.

Negative-spec:
  - Does NOT write, stamp, mint, or mutate anything. The write halves are `plan.stamp_prepped`
    (the attest) and whatever mints an aggregate baton.
  - Does NOT fire, dispatch, or open a gate. It reports what a gate would say.
  - Does NOT spawn a subprocess and does NOT shell out. Both legs are pure reads; the body sha is
    sha1 over bytes, and a process creation costs 25.3ms to compute what sha1 already answers.
  - Does NOT re-run a plan's `census[]` commands. That is the fire-time census leg and it is the
    RUNNER's, ordered strictly after the sha leg.
  - Does NOT run the authoring bar, and does not stamp. Neither verdict is an entry need. The
    repair line names the writer (`plan.stamp_prepped`) and the bar's own resolved launcher name as
    the diagnostic for its refusal, and stops at naming them.
  - Does NOT re-derive the claimed / `in_flight` exclusion. `assemble_plan_gate` applies it.
  - Does NOT decide what to fire. It reports the set; invoking the run is the operator's act.

A LIMIT WORTH NAMING, rather than discovered later. `assemble_plan_gate`'s candidate filter is a
PLANNING filter: a baton at `status: claimed` or `deployment_state: in_flight` is excluded because
handing it to a planning wave races its holder. A certification queue keyed on that filter
inherits an exclusion that was never about certification, so a plan approved and then claimed
drops out of this report silently. Correct immediately after a landing, where the batons are still
`awaiting_gate`; a real gap for a queue re-read days later. Pass `--all-batons` to widen the
report to every baton the engine resolved, at the cost of the race the filter exists to prevent.

Zero subprocess, stdlib plus PyYAML plus two pure readers.

Exit status is a verdict, not a diagnostic: 0 when every fireable plan certifies with nothing
withheld (FIRE), 1 when at least one certifies and something is excluded or withheld
(PARTIAL-FIRE), 2 when nothing certifies (NO-FIRE), 3 on a usage or precondition failure. 1 is not
an error — it is the honest code for a partial hand-over.

Arrived from DoE-claude coordinator/skills/plan-blitz/mise-prep-entry.py (docs/plans/2026-09-18-
doe-holds-no-scripts.md, chunk W2-C9). Lands here as a bin CLI, not a skill-local script; DoE
retargets the skill's citation. AC (reviewer finding 8): `_gate_cmd` prints the bare settings-home
launcher name for `mise-prep-gate`, never the published `<plugin_root>/bin/mise-prep-gate.py`
probed path an operator should not invoke directly through a cold `python3` call
(A-REMEDIATION-LINE-NAMES-A-PROBED-PATH).

Spec backlink: docs/plans/2026-09-18-doe-holds-no-scripts.md, chunk W2-C9.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

#: "engine" class per § Path resolution — this module lives inside the engine checkout.
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent

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
#:
#: TWO OF THE THREE NAME A WRITER, BECAUSE TWO OF THE THREE NEED ONE. The authoring bar
#: (`{gate}`) WRITES NOTHING, so a repair whose only command is the bar promises a stamp no
#: printed command can perform.
#:
#: `plan.stamp_prepped` is the ONE writer of the four-field attest and it re-runs the bar inside
#: its own lock, refusing what the bar fails — so it IS "gate and stamp", in one op, and the bar
#: below it is the DIAGNOSTIC for a refusal rather than a step before it. `{gate}` names the bare
#: settings-home launcher, not a probed file path — see the module docstring's AC note.
_REPAIR = {
    "UNSTAMPED": (
        "stamp it — the `plan.stamp_prepped` op gates and stamps in one call and refuses a plan "
        "the bar fails; on a refusal, the per-class detail is {gate}"
    ),
    "STALE": (
        "body moved after the stamp — re-stamp with `plan.stamp_prepped`, which re-gates the NEW "
        "bytes; on a refusal, the per-class detail is {gate}"
    ),
    "MALFORMED": "hand-written stamp — repair the four mise_prepped_* fields in {target}",
}

#: The authoring bar's bare, installed launcher name — resolvable on PATH / the settings-home
#: `bin/` once installed, the same way `_resolve_upgrade_cli` in `mise-prep-run.py` resolves
#: `mise-prep-upgrade`. Never a probed path: a probed `<plugin_root>/bin/mise-prep-gate.py`
#: literal is not runnable by an operator's cold `python3 <path>` the way the repair text implies,
#: and this module cannot resolve the reader's own shell for them
#: (A-REMEDIATION-LINE-NAMES-A-PROBED-PATH).
_GATE_LAUNCHER_NAME = "mise-prep-gate"


def _gate_cmd(plan: str, repo_root: Optional[Path]) -> str:
    """The bar's invocation for ONE plan, as the bare installed launcher name.

    Carries `--repo-root` because `plan` is repo-relative."""
    root = f"--repo-root {repo_root} " if repo_root else ""
    return f"{_GATE_LAUNCHER_NAME} {root}{plan}"


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


def _ensure_engine_on_path() -> None:
    """Put the engine root on `sys.path`, fail-loud — the same self-location-first bootstrap
    every other `coordinator/bin/*.py` engine-backed CLI uses (see e.g.
    `coordinator/bin/compose-review-wave.py`). Idempotent: `require_colocated_engine_on_path`
    front-inserts onto `sys.path` and a second call is harmless."""
    import lib  # noqa: F401 -- bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_colocated_engine_on_path

    require_colocated_engine_on_path(__file__)


def _load_rollup():
    """SEAM 2's module, loaded by path from this engine's own `coordinator/bin` — never off the
    plugin root, which holds no scripts."""
    rollup_path = Path(__file__).resolve().parent / "aggregate-rollup.py"
    if not rollup_path.is_file():
        raise SeamError(f"aggregate-rollup.py not found at {rollup_path}")

    import importlib.util

    spec = importlib.util.spec_from_file_location("coordinator_aggregate_rollup", rollup_path)
    if spec is None or spec.loader is None:
        raise SeamError(f"unimportable: {rollup_path}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise SeamError(f"unimportable: {rollup_path} ({exc})")
    return module


def _engine_plan_gate():
    """`assemble_plan_gate`, imported directly — this module lives inside the engine, so SEAM 1
    resolves through this module's own tree with no seam at all."""
    _ensure_engine_on_path()
    try:
        from coordinator_core.roadmap.plan_gate import assemble_plan_gate
    except Exception as exc:
        raise SeamError(f"coordinator_core.roadmap.plan_gate unimportable: {exc}")
    return assemble_plan_gate


def approved_plans(repo_root: Path, roadmap_id: Optional[str] = None,
                   all_batons: bool = False) -> list:
    """SEAM 1 — plan-blitz's exit, read off disk.

    Returns `[{"workstream", "baton", "plan"}]`, one entry per baton the last landing left
    fireable. PLAN-BLITZ HAS TWO EXITS, AND THIS READS BOTH: `status: approved` is the M/L lane's,
    and the S lane's `blitz_land` parks the spec on the baton and stamps `execution_authorized`
    while leaving the plan at `draft` BY DESIGN. Deduplicated on `plan`: several batons may cite
    one governing plan, and firing that plan twice is not a composition, it is a double dispatch.
    """
    assemble = _engine_plan_gate()
    try:
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
    rollup = _load_rollup()
    constituents, uncertified, withheld, fires = [], [], [], []
    for row in rows:
        constituents.append({"workstream": row["workstream"], "plan": row["plan"]})
        target = repo_root / row["plan"]
        try:
            text = target.read_text(encoding="utf-8")
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
    headline = (
        f"mise-prep entry: {report['verdict']} — "
        f"{len(report['fires'])} of {len(report['constituents'])} fireable plan(s) certify"
    )
    if report["verdict"] == PARTIAL_FIRE:
        causes = []
        if report["uncertified"]:
            causes.append(f"{len(report['uncertified'])} excluded")
        if report["withheld_rows"]:
            causes.append(
                f"{len(report['withheld_rows'])} certifying plan(s) hold rows behind a gate"
            )
        if causes:
            headline += f"; partial because {', '.join(causes)}"
    lines = [headline]
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
    """The seam-2 payload as the frontmatter block a run's Phase 0a reads."""
    out = ["aggregate_execution:"]
    if report["constituents"]:
        out.append("  constituents:")
        for entry in report["constituents"]:
            out.append(f"    - workstream: {entry['workstream']}")
            out.append(f"      plan: {entry['plan']}")
    else:
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


def main(argv: "list[str] | None" = None) -> int:
    args_in = argv if argv is not None else sys.argv[1:]
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
    args = parser.parse_args(args_in)

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
    sys.exit(main(sys.argv[1:]))
