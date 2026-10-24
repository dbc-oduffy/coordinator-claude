"""mise-prep-run — gate and stamp a set of plans, and name each one's state.

WHY THIS EXISTS. mise-prep's two halves both shipped and neither drives the ceremony.
`plan.prep_gate` reports the authoring bar for ONE plan; `plan.stamp_prepped` writes the
attest for ONE plan and refuses unless the gate passes over the bytes it is about to
stamp. Between them, nothing — so certifying a landed wave means an EM reading the entry
query, picking plan paths out of it, and typing two op calls per plan. That is the same
retype `mise-prep-entry.py` removed at the plan-blitz seam, still standing one step later.

This is the driver: one call over a set, gate then stamp each, and one report that names
every plan's state with the repair that state routes to.

THE FOUR STATES ROUTE FOUR WAYS, which is why "not certified" is the wrong noun for three
of them and this module never prints it:

  CERTIFIED    the recomputed body sha matches the stamp. Nothing to do.
  STALE        stamped, but the body moved since — re-GATE, then re-stamp. A wave's
               reviewer rewrites plan bodies applying its own findings, so STALE is
               the ORDINARY state after a landing, not an anomaly.
  UNSTAMPED    never certified. Gate and stamp.
  MALFORMED    a hand-written stamp. Repair the frontmatter; do not stamp over it.

CLIENT-SIDE DRIVER. This file is a client: it sends the engine ONE `plan.mise_prep_probe` call over
the whole set (gate and upgrade derivation per plan), so the op count does not grow with the set;
an engine that predates the set form falls back to one probe per plan. Each op travels the warm
client transport
(`cc_invoke.cc_invoke`) under its own budget. The set-level ops (`plan.seam_fix`, the seam check,
residue bind/validate) are one call each.

CENSUS. No census re-runs at prep (the revalidation leg was deleted under DR-344). Each PREPPED
row's `census` is the NOT-RUN outcome, and the JSON summary carries `census: "NOT-RUN"`. Stamping
proceeds on the gate and seam verdicts alone.

WHAT IT DOES NOT DO. It does not decide what to fire, does not refresh a plan's recorded
`result:` values, and does not author anything into a plan beyond the `depends_on_plan`
edges `plan.seam_fix` writes. A plan that fails the bar is REPORTED with its failing
classes and the upgrade command that writes the declarations derivable from the plan's own text —
`mise-prep-upgrade` never invents one, and neither does this. `--upgrade` has the probe derive them
(`upgrade_plan`, check-only); without `--dry-run` a derivable plan then gets `plan.mise_upgrade_apply`
and a re-probe. Without the flag nothing under `docs/plans/` is written except an attest the gate
has just passed.

Usage:

    python3 mise-prep-run.py --repo-root <abs> [--upgrade] [--dry-run] [plan ...]
    python3 mise-prep-run.py --repo-root <abs> --apply-rulings <payload.json|->

`--apply-rulings` skips the gate/stamp pass: it sends the payload `{run_id, rulings}` as ONE
`plan.record_residue_rulings` call (`on` = today's UTC date), prints the reply as JSON, and exits 0
when its `refused` is empty, 1 otherwise, 2 for a malformed payload.

With no plan arguments the set is every APPROVED plan the engine's plan gate reports —
mise-prep's own entry set, taken from the same seam `mise-prep-entry.py` reads, never
re-derived from plan frontmatter.

Before any plan is probed, `plan.seam_fix` runs once over the set, minting the `depends_on_plan`
edges that order in-set writes collisions. It is the one op here that edits plan bodies, and it runs
first so every stamp is computed over the edged body. Pairs it cannot order without a cycle come
back as `skippedCycles` on the report. Under `--dry-run` it does NOT run: it is MUTATING even with
`dry_run: true`, and a dry run issues only COMPUTE_ONLY ops, so a timeout on one is never an
indeterminate mutation. `seamFix` then reads "not run (dry run)".

After every plan is probed, one seam check runs over the whole set (`plan.seam_record` at
`phase: prep`; `plan.seam_check` under `--dry-run`, which writes no sidecar). A plan the check
implicates is not stamped and reads SEAM-REFUSED with one `seam:` line per finding, each ending in
its route. A seam or stamp op error is a refusal (exit 2), never a pass.

RESIDUE WORKFLOW. After the report rows and the seam-fix reply exist (dry run or not),
`mise_residue.residue_args` sorts what stayed short: plans to author go to Sonnet
`coordinator:residue-author` agents, up to 8 plans per agent; a NOT-PREPPED row whose failing
bar classes are spine-repair classes (`mise_residue.spine_repairs`) prints each repair line with
`route: coordinator:residue-author`; unscreenable census entries and
`skippedCycles` go to one `coordinator:apm` agent. When either list is non-empty the run binds
`workflows/mise-prep-residue.mjs` with those args (`workflow.bind_args`), validates it
(`workflow.validate`) and writes `state/mise-workflows/<runId>.residue.mjs` plus its receipt, then
prints a `Workflow({scriptPath})` line for the EM to fire (`--dry-run` still writes the script
and receipt: it withholds stamps, not files). A script over the Workflow byte cap is split into
`<runId>-pN.residue.mjs` parts, each a complete args object, one printed line each, `apmItems` in
part 1 only. The per-plan writes-collision findings files the args reference by `seamRef` sit in
`state/mise-workflows/<runId>.seam/`, written under `--dry-run` too. Nothing is fired from here;
`--json` carries `residueWorkflow` (repo-relative path of part 1, or null),
`residueWorkflowParts` (every part) and `residueFindings` (findings-file count). A bind or validate refusal is exit 2, taken
only AFTER the full report prints (`--json`: `residueWorkflow: null` plus `residueError`), because
the stamps are already written and the report is the record of which plans they covered.

Exit 0 when every plan in the set ends CERTIFIED, 1 when at least one does not (the
report names which and why), 2 on a set-level refusal that stopped the run or a `plan.stamp_prepped`
error. One plan's `plan.mise_prep_probe` error is that row's PROBE-FAILED outcome (exit 1): the plan
is never stamped, never residue, and stays in the seam set.

Landed here (`coordinator/bin/mise-prep-run.py`, claude-klabauter) from coordinator-content-repo
`coordinator/bin/mise-prep-run.py`, docs/plans/2026-09-18-doe-holds-no-scripts.md chunk W2-C9.
`_invoke` never spawns `sys.executable coordinator-invoke.py` per op. It reaches the warm engine
through `cc_invoke.cc_invoke`, the library form of the client transport, so the driver itself spawns
no process per plan and no op carries the whole set
(docs/plans/2026-10-21-mise-prep-run-full-set-fits-its-op-budget.md). `_ENTRY` points at the sibling
`coordinator/bin/mise-prep-entry.py`, not a DoE `skills/plan-blitz/` path.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

EXIT_OK = 0
EXIT_NOT_ALL_CERTIFIED = 1
EXIT_REFUSED = 2

_HERE = Path(__file__).resolve().parent
#: mise-prep's entry query, now a sibling bin CLI (this chunk lands both). Imported rather than
#: re-implemented: re-deriving the approved set from plan frontmatter would be a second answer to
#: a question the engine's gate settles.
_ENTRY = _HERE / "mise-prep-entry.py"


def _load_entry():
    spec = importlib.util.spec_from_file_location("mise_prep_entry", _ENTRY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


#: `_invoke` calls this run has made, failures included; `main` resets it and the JSON report
#: carries it as `opCalls`.
_OP_CALLS = 0


def _invoke(repo_root: Path, op: str, params: dict) -> dict:
    """One op call over the warm client transport — a bounded op under its own budget, never a
    `coordinator-invoke.py` subprocess and never an in-process dispatch.

    `cc_invoke.cc_invoke` is the library form of `coordinator_core.invoke`'s warm preamble: it
    reaches the warm engine, and only on a miss falls to its own stamped in-process rung. Raises
    `ValueError` on any failure — unresolvable transport, an error envelope, or a malformed
    reply — so callers keep treating a refusal as a reply, never a crash.
    """
    global _OP_CALLS
    _OP_CALLS += 1
    try:
        import lib  # noqa: F401 -- bootstraps coordinator/bin/lib onto sys.path
        import cc_invoke
    except Exception as exc:
        raise ValueError(
            f"{op}: client transport unresolvable: {exc} — set COORDINATOR_ENGINE_ROOT to the "
            "engine checkout or run the settings-home `mise-prep-run` launcher"
        )
    try:
        result = cc_invoke.cc_invoke(op, params, str(repo_root))
    except Exception as exc:
        raise ValueError(f"{op} refused: {exc}") from exc
    if not isinstance(result, dict):
        raise ValueError(f"{op} returned a non-dict result: {result!r}")
    return result


#: The op's bare verdicts collide with this command's own exit-2 `REFUSED`, so every caller-facing
#: surface spells them with the `SEAM-` prefix; the bare values live only in the op reply.
_SEAM_SPELLING = {"REFUSED": "SEAM-REFUSED", "DRIFT": "SEAM-DRIFT"}
_SEAM_OPS = {False: "plan.seam_record", True: "plan.seam_check"}
#: Each refusal carries its own route: the engine and the command text publish separately.
_ROUTE_AUTHOR = "route: coordinator:residue-author, declare capabilities"
_ROUTE_RESIDUE = "route: coordinator:residue-author"
_ROUTE_APM = "route: coordinator:apm, scope"
_FINDING_FIELDS = ("capability", "missing_consumer", "counterpart_plan", "path", "row", "detail")


def _seam_call(repo_root: Path, plans: list[str], phase: str, named_set: bool, read_only: bool) -> dict:
    """One `plan.seam_record` (`plan.seam_check` when `read_only`) call over the whole set.

    A named set is checked with `universe` on: its gaps against open plans outside the set come
    back as non-blocking `missing-seam` findings rather than blocking `unpromised-export`, so an
    out-of-set dependency never refuses the stamp. The default set is every approved plan, so it
    has no outside worth the extra parse.

    Raises `ValueError` on an op error or a reply without `verdict`/`per_plan`: a seam check that
    did not answer is never a pass.
    """
    op = _SEAM_OPS[read_only]
    reply = _invoke(
        repo_root, op, {"plans": list(plans), "phase": phase, "named_set": named_set, "universe": named_set}
    )
    if not isinstance(reply.get("verdict"), str) or not isinstance(reply.get("per_plan"), dict):
        raise ValueError(f"{op} returned a reply without `verdict` and `per_plan`")
    return reply


_SEAM_FIX_NOT_RUN = "not run (dry run)"


def _seam_fix(repo_root: Path, plans: list[str], dry_run: bool) -> dict:
    """One `plan.seam_fix` call over the set, normalized to the report's `seamFix` shape.

    Runs before any probe so every stamp is computed over the edged body. The reply is returned
    once for the report and the downstream APM stage; callers never re-call the op. Raises
    `ValueError` on an op error.

    `plan.seam_fix` is MUTATING even with `dry_run: true`, and a dry run issues COMPUTE_ONLY ops
    only, so under `dry_run` no op is called: the shape comes back empty with `notRun` set and
    `converged` False. `plan.seam_check` carries no edges to read in its place.
    """
    if dry_run:
        return {
            "edgesAdded": [], "skippedCycles": [], "converged": False, "files": [],
            "notRun": _SEAM_FIX_NOT_RUN,
        }
    reply = _invoke(repo_root, "plan.seam_fix", {"plans": list(plans), "dry_run": False})
    return {
        "edgesAdded": list(reply.get("edges_added") or []),
        "skippedCycles": list(reply.get("skipped_cycles") or []),
        "converged": bool(reply.get("converged")),
        "files": list(reply.get("files") or []),
    }


_RESIDUE_SOURCE_NAME = "mise-prep-residue.mjs"
_RESIDUE_DIR = ("state", "mise-workflows")


def _bound_size(script: str) -> int:
    return len(script.encode("utf-8"))


#: Equal to `coordinator_core.roadmap.census.NOT_RUN`; this client imports no engine module.
_NOT_RUN = "NOT-RUN"


def _not_run_census() -> dict:
    """The census outcome of a row: no census re-ran at prep (DR-344 kill of the revalidation leg)."""
    return {
        "state": _NOT_RUN,
        "entries": [],
        "detail": "no census re-ran at prep: the revalidation leg was deleted under DR-344",
    }


def _probe_failed_row(plan: str, error: str, upgraded: str | None = None) -> dict:
    """The row for a plan whose probe op raised: reported, never stamped, never residue."""
    return {
        "plan": plan,
        "verdict": "PROBE-FAILED",
        "failing": [],
        "detail": [error],
        "withheld_rows": [],
        "upgraded": upgraded,
        "stamp_state": None,
        "census": None,
        "processMs": None,
        "outcome": "PROBE-FAILED",
    }


def _emit_residue(repo_root: Path, rows: list[dict], seam_fix: dict) -> tuple[list[Path], int]:
    """`_write_residue` with every file it writes declared to the session scope-touch."""
    try:
        import lib  # noqa: F401 -- bootstraps coordinator/bin/lib onto sys.path
        import cc_invoke

        cc_invoke.require_engine_on_path(__file__)
        from coordinator_core.cli_entry import recording_declared_writes
    except Exception as exc:
        raise ValueError(f"residue workflow: coordinator_core unresolvable: {exc}")
    with recording_declared_writes(cwd=str(repo_root)):
        return _write_residue(repo_root, rows, seam_fix)


def _write_residue(repo_root: Path, rows: list[dict], seam_fix: dict) -> tuple[list[Path], int]:
    """Build, bind, validate and write the residue workflow for this round: `([], 0)` when no
    plan needs authoring and no census or seam-fix item needs a ruling.

    Contract: returns `(part paths, findings-file count)`. Writes the per-plan findings files
    under `state/mise-workflows/<runId>.seam/`, then `<runId>.residue.mjs` (one part) or
    `<runId>-pN.residue.mjs` (each at most `emit._WORKFLOW_SCRIPT_BYTE_CAP` bytes, `apmItems` in
    part 1 only), each with its emission receipt; fires nothing, spawns nothing of its own.
    Raises `ValueError` on a bind or validate refusal or a single over-cap batch, after removing
    every file it wrote, so the caller exits 2 rather than printing a path to a script that
    would not run.
    """
    try:
        import lib  # noqa: F401 -- bootstraps coordinator/bin/lib onto sys.path
        import cc_invoke

        cc_invoke.require_engine_on_path(__file__)
        from coordinator_core.ops.dispatch_emit import emit
        from coordinator_core.ops.dispatch_emit.emission_receipt import _write_emission_receipt
        from coordinator_core.session.declared_writes import declare_write
        from coordinator_core.roadmap import mise_residue
    except Exception as exc:
        raise ValueError(f"residue workflow: coordinator_core unresolvable: {exc}")

    run_id = (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(4)
    )
    args = mise_residue.residue_args(
        rows,
        {"skipped_cycles": seam_fix["skippedCycles"]},
        repo_root=repo_root,
        run_id=run_id,
        gate_command=f"mise-prep-gate --repo-root {repo_root.as_posix()}",
        residue_agent_type=mise_residue.RESIDUE_AGENT_TYPE,
        residue_model=emit.resolve_agent_model(mise_residue.RESIDUE_AGENT_TYPE),
        apm_model=emit.resolve_agent_model(mise_residue.APM_AGENT_TYPE),
    )
    if not mise_residue.has_work(args):
        return [], 0

    cap = emit._WORKFLOW_SCRIPT_BYTE_CAP
    source = Path(mise_residue.__file__).resolve().parent / "workflows" / _RESIDUE_SOURCE_NAME
    out_dir = repo_root.joinpath(*_RESIDUE_DIR)
    written: list[Path] = []

    def cleanup() -> None:
        for f in written:
            f.unlink(missing_ok=True)
            f.with_name(f.name + ".emitted.json").unlink(missing_ok=True)
        for d in {f.parent for f in written if f.parent != out_dir}:
            try:
                d.rmdir()
            except OSError:
                pass

    def bind(part_args: dict) -> str:
        script = _invoke(
            repo_root, "workflow.bind_args", {"script_path": str(source), "args": part_args}
        ).get("script")
        if not isinstance(script, str) or not script:
            raise ValueError("workflow.bind_args returned no script text")
        return script

    parts: list[Path] = []
    try:
        findings = mise_residue.seam_ref_texts(rows, run_id)
        for rel, text in findings.items():
            target = repo_root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8", newline="\n")
            declare_write(target)
            written.append(target)

        batches = args["batches"]
        scripts: list[tuple[dict, str]] = []
        start = 0
        while start < len(batches) or (not scripts and not batches):
            part_apm = args["apmItems"] if not scripts else []
            rest = len(batches) - start

            def part_args(k: int) -> dict:
                return {**args, "batches": batches[start:start + k], "apmItems": part_apm}

            best = None
            if rest:
                script = bind(part_args(rest))
                if _bound_size(script) <= cap:
                    best = (rest, script)
                else:
                    lo, hi = 1, rest - 1
                    while lo <= hi:
                        mid = (lo + hi) // 2
                        script = bind(part_args(mid))
                        if _bound_size(script) <= cap:
                            best, lo = (mid, script), mid + 1
                        else:
                            hi = mid - 1
            else:
                script = bind(part_args(0))
                if _bound_size(script) <= cap:
                    best = (0, script)
            if best is None:
                named = ", ".join(p["plan"] for p in batches[start]["plans"]) if rest else "apmItems"
                raise ValueError(
                    f"residue workflow: {'batch ' + batches[start]['id'] if rest else 'part 1'} "
                    f"({named}) alone exceeds the {cap}-byte Workflow script cap"
                )
            k, script = best
            scripts.append((part_args(k), script))
            start += k
            if not rest:
                break

        out_dir.mkdir(parents=True, exist_ok=True)
        for n, (part, script) in enumerate(scripts, 1):
            name = f"{run_id}.residue.mjs" if len(scripts) == 1 else f"{run_id}-p{n}.residue.mjs"
            path = out_dir / name
            path.write_text(script, encoding="utf-8", newline="\n")
            declare_write(path)
            written.append(path)
            verdict = _invoke(repo_root, "workflow.validate", {"script_path": str(path)})
            if not verdict.get("ok"):
                messages = "; ".join(str(f.get("message")) for f in verdict.get("findings") or [])
                raise ValueError(f"workflow.validate refused {path.name}: {messages}")
            _write_emission_receipt(
                path, None, {},
                extras={"batches": len(part["batches"]), "apmItems": len(part["apmItems"])},
            )
            parts.append(path)
    except BaseException:
        cleanup()
        raise
    return parts, len(findings)


def _seam_spell(verdict: str | None) -> str | None:
    return _SEAM_SPELLING.get(verdict, verdict)


def _seam_implicated(reply: dict, plan: str) -> bool:
    per_plan = reply.get("per_plan") or {}
    verdict = per_plan.get(plan, per_plan.get(Path(plan).as_posix()))
    return verdict in _SEAM_SPELLING


def _seam_findings_for(reply: dict, plan: str) -> list[dict]:
    """The findings that name `plan`. A finding carrying no `plan` key is attributed to every
    implicated plan, since the pinned reply names `counterpart_plan` but not the owner."""
    out = []
    for f in reply.get("findings") or []:
        if not isinstance(f, dict):
            continue
        owner = f.get("plan")
        if owner is None:
            if _seam_implicated(reply, plan) or not f.get("blocking"):
                out.append(f)
        elif plan in (owner, f.get("counterpart_plan")):
            out.append(f)
    return out


def _seam_findings_index(reply: dict, plans: list[str]) -> dict[str, list[dict]]:
    """`{p: _seam_findings_for(reply, p)}` for every plan in `plans`, from one pass over the
    findings instead of one pass per plan. Order within a plan is the reply's order."""
    index: dict[str, list[dict]] = {p: [] for p in plans}
    implicated = {p for p in index if _seam_implicated(reply, p)}
    for f in reply.get("findings") or []:
        if not isinstance(f, dict):
            continue
        owner = f.get("plan")
        if owner is None:
            if f.get("blocking"):
                for p in index:
                    if p in implicated:
                        index[p].append(f)
            else:
                for p in index:
                    index[p].append(f)
        else:
            for p in {owner, f.get("counterpart_plan")}:
                if p in index:
                    index[p].append(f)
    return index


_MISSING_SEAM = "missing-seam"
_MISSING_SEAM_SHOWN = 10


def _is_missing_seam(finding: dict) -> bool:
    return finding.get("class") == _MISSING_SEAM and not finding.get("blocking")


def _missing_seam_section(rows: list[dict]) -> list[str]:
    """One bounded block of the non-blocking `missing-seam` findings, deduplicated across rows,
    kept apart from the per-plan verdict lines."""
    seen: dict[str, None] = {}
    for r in rows:
        for f in r.get("seam") or []:
            if _is_missing_seam(f):
                seen.setdefault(_seam_line(f), None)
    lines = list(seen)
    if not lines:
        return []
    out = [f"missing-seam: {len(lines)} non-blocking finding(s)"]
    out += [f"  {line}" for line in lines[:_MISSING_SEAM_SHOWN]]
    if len(lines) > _MISSING_SEAM_SHOWN:
        out.append(f"  … {len(lines) - _MISSING_SEAM_SHOWN} further finding(s) omitted")
    return out


def _seam_route(finding: dict) -> str:
    return _ROUTE_AUTHOR if finding.get("class") == "capabilities-undeclared" else _ROUTE_APM


def _seam_line(finding: dict) -> str:
    parts = [str(finding.get("class"))]
    parts += [f"{k}={finding[k]}" for k in _FINDING_FIELDS if finding.get(k) not in (None, "")]
    if not finding.get("blocking"):
        parts.append("(not blocking)")
    return "seam: " + " ".join(parts) + f" — {_seam_route(finding)}"


def _failing_classes(gate: dict) -> list[str]:
    return [
        f"{name}/{body.get('kind') or body.get('status')}"
        for name, body in (gate.get("classes") or {}).items()
        if body.get("status") != "PASS"
    ]


# WHAT THE CLASS ACTUALLY SAID. The repair line tells the reader to correct "the named field", and
# until this existed nothing named it: `_failing_classes` kept the class name and threw the body
# away, `--json` carried only the class string, and the one tool that would have printed detail is
# the gate — which, on the very plans that fail here, says PREPPED. So the operator was pointed at
# a class body reachable from nowhere, and example-store-repo-fb was reduced to diffing a failing plan
# against a passing one to guess at the field. A repair instruction that names an artifact the tool
# does not emit is `A-DIAGNOSTIC-THAT-NAMES-A-CAUSE-IT-DID-NOT-OBSERVE` wearing its other face.
#
# The body's shape belongs to the engine and will grow keys this does not know, so this renders
# whatever detail it carries rather than a fixed field list: preferred keys first, then any
# remaining non-bookkeeping key, so a new one surfaces instead of being silently dropped.
_DETAIL_KEYS = ("message", "reason", "detail", "details", "field", "fields", "errors", "offenders")
_CLASS_BOOKKEEPING = {"status", "kind"}


def _failing_details(gate: dict) -> list[str]:
    out = []
    for name, body in (gate.get("classes") or {}).items():
        if not isinstance(body, dict) or body.get("status") == "PASS":
            continue
        seen, parts = set(), []
        for key in _DETAIL_KEYS:
            if body.get(key) not in (None, "", [], {}):
                seen.add(key)
                parts.append(f"{key}={body[key]!r}")
        for key, value in body.items():
            if key in seen or key in _CLASS_BOOKKEEPING:
                continue
            if value not in (None, "", [], {}):
                parts.append(f"{key}={value!r}")
        if parts:
            out.append(f"{name}: {'; '.join(parts)}")
    return out


# `mise-prep-upgrade` writes DECLARATIONS DERIVABLE FROM A PLAN'S OWN TEXT. A schema class rejects
# a value the plan already states, so `--upgrade` has nothing to derive and writes nothing — the
# blanket "repair: mise-prep-upgrade <plan>" is then a no-op that sends the reader in a circle,
# reported by project-rag-4a after running it across a whole set for zero writes.
#
# This line names only what the runner OBSERVED: which class refused, and that the upgrade path
# cannot reach it. It deliberately names no cause.
_NOT_UPGRADEABLE = ("schema",)


def _sizing_object_citation(plan: str) -> str:
    """This plan's own top-level `sizing_object:`, when it resolves on disk.

    project-rag-ue-addon measured 21 SCHEMA refusals on one corpus, every one a
    `prime_exit_criterion.derived_from` carrying narrative where the schema wants an openable
    link — and in 17 of 17 repaired by hand, the correct pointer was this same field, sitting in
    the same frontmatter. Naming it costs a line-scan; not naming it cost them four dispatched
    agents. Returns "" on any read failure: a repair line may name only what was read.
    """
    try:
        with open(plan, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return ""
    if not lines or lines[0].strip() != "---":
        return ""
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if not line.startswith("sizing_object:"):
            continue
        value = line.split(":", 1)[1].strip().strip("'\"")
        return value if value and os.path.exists(value) else ""
    return ""


def _repair_line(failing: list[str], plan: str) -> str:
    """The repair for THIS row's failing classes, never one constant string."""
    blocked = sorted({
        cls.split("/", 1)[0] for cls in failing
        if cls.split("/", 1)[0].lower().startswith(_NOT_UPGRADEABLE)
    })
    if blocked:
        candidate = _sizing_object_citation(plan)
        derived = (
            f" This plan's own `sizing_object: {candidate}` resolves on disk; where the refused "
            f"field is `prime_exit_criterion.derived_from`, that is usually the value it wants. "
            f"Relocate the prose it currently holds into the plan body rather than dropping it, "
            f"and re-run — a body edit invalidates `mise_prepped_sha`."
            if candidate
            else ""
        )
        return (
            f"repair: NOT `--upgrade` — it writes declarations derivable from the plan's own "
            f"text, and {', '.join(blocked)} refuses a value the plan already states, so the "
            f"upgrade path does not write it. Read that class's own body for the named field and "
            f"correct it BY HAND in {plan} — unless the field is engine-written (`mise_prepped*`, "
            f"`execution_authorized_*`), which has a producer and must be repaired there instead."
            f"{derived}"
        )
    return f"repair: mise-prep-upgrade {plan}  (or --upgrade), then re-run"


def _probe(repo_root: Path, plan: str, *, upgrade: bool) -> dict:
    """One `plan.mise_prep_probe` call: this plan's gate and upgrade derivation, no census.

    Raises `ValueError` on an op error or a reply without a `gate` object, so a probe that did
    not answer is never read as a verdict.
    """
    reply = _invoke(repo_root, "plan.mise_prep_probe", {"plan": plan, "upgrade": upgrade})
    if not isinstance(reply.get("gate"), dict):
        raise ValueError("plan.mise_prep_probe returned a reply without a `gate` object")
    return reply


def _probe_set(repo_root: Path, plans: list[str], *, upgrade: bool) -> dict[str, dict]:
    """ONE `plan.mise_prep_probe` call over `plans`: `{plan: probe reply | {"error": text}}`.

    A failed call, or a reply with no `probes` object (an engine that predates the set form
    rejects `plans`), falls back to the per-plan `_probe` loop. A plan the reply omits, or answers
    without a `gate` object, reads `{"error"}`, never a verdict.
    """
    ordered = list(dict.fromkeys(plans))
    try:
        reply = _invoke(repo_root, "plan.mise_prep_probe", {"plans": ordered, "upgrade": upgrade})
        probes = reply.get("probes")
        if not isinstance(probes, dict):
            raise ValueError("plan.mise_prep_probe returned a reply without a `probes` object")
    except Exception as exc:  # noqa: BLE001 - any set-call failure degrades to the per-plan loop
        if isinstance(exc, TimeoutError) or "timed out" in str(exc).lower():
            return {plan: {"error": str(exc)} for plan in ordered}
        print(f"mise-prep-run: set probe unavailable ({exc}); probing per plan", file=sys.stderr)
        out: dict[str, dict] = {}
        for plan in ordered:
            try:
                out[plan] = _probe(repo_root, plan, upgrade=upgrade)
            except ValueError as perr:
                out[plan] = {"error": str(perr)}
        return out
    out = {}
    for plan in ordered:
        entry = probes.get(plan)
        if not isinstance(entry, dict):
            out[plan] = {"error": "set probe returned no reply for this plan"}
        elif isinstance(entry.get("gate"), dict):
            out[plan] = entry
        else:
            out[plan] = {
                "error": str(entry.get("error"))
                if entry.get("error")
                else "plan.mise_prep_probe returned a reply without a `gate` object"
            }
    return out


def _derivable(derivation) -> bool:
    """True when a probe's `upgrade` dict says `upgrade_plan` would change the plan."""
    return isinstance(derivation, dict) and not derivation.get("error") and bool(derivation.get("changed"))


def _upgrade_note(derivation) -> str | None:
    """The row's `upgraded` text from an `upgrade_plan` dict (a probe's `upgrade` or an apply reply).

    `None` for no derivation or `{"skipped": ...}`: the plan fails only a class the upgrade cannot
    reach, and `_repair_line` says so more precisely than a note would. Otherwise `wrote <fields>;
    AUTHOR: ...` when the tool changed (or under check-only would change) the plan, and
    `declined: ...` for an error, pure residue, or nothing to derive.

    Delegated, never reimplemented: what is derivable from a plan's own text is
    `mise-prep-upgrade`'s judgment, and a second deriver here would author declarations it never
    agreed to.
    """
    if not isinstance(derivation, dict) or "skipped" in derivation:
        return None
    if derivation.get("error"):
        return f"declined: {derivation['error']}"
    residue = list(derivation.get("residue") or [])
    if derivation.get("changed"):
        derived = ", ".join(derivation.get("derived") or [])
        note = f"wrote {derived}" if derived else "wrote"
        if residue:
            note += "; AUTHOR: " + "; ".join(residue)
        return note
    if residue:
        return "declined: AUTHOR: " + "; AUTHOR: ".join(residue)
    return "declined: nothing to derive"


def _apply_rulings(repo_root: Path, source: str, refuse) -> int:
    """`--apply-rulings`: one `RULINGS_OP` call over the payload `{run_id, rulings}`, receipt on
    stdout. Exit 0 when the reply's `refused` is empty, else 1; an unreadable or malformed payload
    is exit 2 before any op call."""
    try:
        text = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
        payload = json.loads(text)
    except (OSError, ValueError) as exc:
        return refuse(f"rulings payload unreadable: {exc}")
    if not isinstance(payload, dict) or not isinstance(payload.get("rulings"), list):
        return refuse("rulings payload must be a JSON object with a `rulings` list")
    try:
        import lib  # noqa: F401 -- bootstraps coordinator/bin/lib onto sys.path
        import cc_invoke

        cc_invoke.require_engine_on_path(__file__)
        from coordinator_core.roadmap import mise_residue
    except Exception as exc:  # noqa: BLE001
        return refuse(f"coordinator_core unresolvable: {exc}")
    params = {
        "run_id": payload.get("run_id", ""),
        "on": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "rulings": payload["rulings"],
    }
    try:
        reply = _invoke(repo_root, mise_residue.RULINGS_OP, params)
    except ValueError as exc:
        return refuse(str(exc))
    print(json.dumps(reply, indent=2, sort_keys=True))
    return EXIT_OK if not reply.get("refused") else EXIT_NOT_ALL_CERTIFIED


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="mise-prep-run",
        description="Gate and stamp a set of plans; name each one's certification state.",
    )
    ap.add_argument("plans", nargs="*", help="plan paths; default: every approved plan")
    ap.add_argument("--repo-root", required=True, help="ABSOLUTE repo root")
    ap.add_argument("--engine-root", help="engine checkout (default: $COORDINATOR_ENGINE_ROOT)")
    ap.add_argument("--roadmap-id", help="narrow the default set to one roadmap")
    ap.add_argument(
        "--upgrade",
        action="store_true",
        help="derive what mise-prep-upgrade would write for a plan that fails the bar and, "
        "outside --dry-run, write it and re-probe. Writes "
        "only the declarations derivable from the plan's own text; it invents none, so a "
        "plan needing real authoring still comes back NOT-PREPPED with its classes named.",
    )
    ap.add_argument("--dry-run", action="store_true", help="gate and report; stamp nothing")
    ap.add_argument("--json", action="store_true")
    ap.add_argument(
        "--apply-rulings", metavar="PATH",
        help="write the APM rulings in this JSON payload file ('-' = stdin) into their plans' "
        "pm_ruling: lists with one plan.record_residue_rulings call; skips the gate/stamp pass",
    )
    args = ap.parse_args(argv)

    global _OP_CALLS
    _OP_CALLS = 0
    repo_root = Path(args.repo_root).resolve()
    if args.engine_root:
        os.environ["COORDINATOR_ENGINE_ROOT"] = str(Path(args.engine_root).resolve())

    def refuse(msg: str) -> int:
        print(f"mise-prep-run: REFUSED — {msg}", file=sys.stderr)
        return EXIT_REFUSED

    if args.apply_rulings is not None:
        return _apply_rulings(repo_root, args.apply_rulings, refuse)

    plans = list(args.plans)
    skipped: list[str] = []
    if not plans:
        try:
            entry = _load_entry()
            rows = entry.approved_plans(repo_root, args.roadmap_id, False)
        except Exception as exc:  # noqa: BLE001 - the entry query owns its own errors
            return refuse(f"could not read the approved-plan set: {exc}")
        plans = [r["plan"] for r in rows]
        # `plan.seam_fix` writes docs/plans/ plans only and raises on anything else, which would
        # take the whole run down; an out-of-tree plan (an archived spec) is reported, not fired.
        skipped = [p for p in plans if not p.replace("\\", "/").startswith("docs/plans/")]
        plans = [p for p in plans if p not in skipped]
        for p in skipped:
            print(
                f"mise-prep-run: SKIPPED-OUT-OF-TREE {p} — outside docs/plans/, not certifiable",
                file=sys.stderr,
            )
        if not plans:
            print("mise-prep-run: no approved plans — nothing to certify")
            return EXIT_OK
        # SAY WHAT THE SET IS MADE OF. The selection reads BOTH plan-blitz exits — `status:
        # approved` and the S lane's execution-ready park, whose plan stays `draft` by design — so
        # a count that moves with no approval in sight is ordinary.
        drafts = [
            p for p in plans
            if "status: approved" not in (repo_root / p).read_text(
                encoding="utf-8", errors="replace")[:4000]
        ] if all((repo_root / p).is_file() for p in plans) else []
        print(
            f"mise-prep-run: certification set — {len(plans)} plan(s)"
            + (f", {len(drafts)} entering from the execution-ready lane (plan still draft by "
               f"design): {', '.join(drafts[:5])}"
               f"{' …' if len(drafts) > 5 else ''}" if drafts else ""),
            # --json owns stdout: a prose line ahead of the document makes it unparseable.
            file=sys.stderr if args.json else sys.stdout,
        )

    try:
        seam_fix = _seam_fix(repo_root, plans, args.dry_run)
    except ValueError as exc:
        return refuse(f"seam fix: {exc}")

    gates: dict[str, dict] = {}
    slots: list[dict | None] = [None] * len(plans)
    regate: dict[int, str | None] = {}

    def make_row(plan: str, probe: dict, upgraded: str | None) -> dict:
        # The gate already carries the attest's own four-state read (`plan.prep_gate`
        # returns `read_stamp`'s answer). Carrying it here is what makes a dry run
        # answer the question a dry run is asked: not "would these pass the bar" but
        # "how many of them does this run actually write". Without it every plan in the
        # set reads `would-stamp`, CERTIFIED ones included, and a set with nothing to do
        # is indistinguishable from a set where all of it is pending.
        gate = probe["gate"]
        gates[plan] = gate
        return {
            "plan": plan,
            "verdict": gate.get("verdict"),
            "failing": _failing_classes(gate),
            "detail": _failing_details(gate),
            "withheld_rows": gate.get("withheld_rows") or [],
            "upgraded": upgraded,
            "stamp_state": (gate.get("stamp") or {}).get("state"),
            "census": _not_run_census() if gate.get("verdict") == "PREPPED" else None,
            "processMs": probe.get("process_ms"),
            "outcome": None,
        }

    probes = _probe_set(repo_root, plans, upgrade=args.upgrade)
    for index, plan in enumerate(plans, 1):
        probe = probes[plan]
        if not isinstance(probe.get("gate"), dict):
            gates[plan] = {}
            slots[index - 1] = _probe_failed_row(plan, str(probe.get("error")))
            print(f"mise-prep-run: [{index}/{len(plans)}] {plan} PROBE-FAILED", file=sys.stderr)
            continue
        gate = probe["gate"]
        # One line per plan, printed after the set probe returned: a record of the verdicts, not
        # a progress signal.
        print(
            f"mise-prep-run: [{index}/{len(plans)}] {plan} {gate.get('verdict')} "
            f"{probe.get('process_ms')}ms",
            file=sys.stderr,
        )

        derivation = probe.get("upgrade")
        upgraded = _upgrade_note(derivation)
        # Apply only a derivable plan, and only outside `--dry-run`: the probe's derivation is
        # check-only, so a dry run never issues the MUTATING apply op. A written plan is
        # re-gated after the loop in one set call: the ordinary outcome is a write alongside
        # residue. The re-gate skips the derivation (the apply reply is the new note).
        if args.upgrade and not args.dry_run and _derivable(derivation):
            try:
                applied = _invoke(repo_root, "plan.mise_upgrade_apply", {"plan": plan})
            except ValueError as exc:
                upgraded = f"declined: {exc}"
            else:
                regate[index - 1] = _upgrade_note(applied)
                continue
        slots[index - 1] = make_row(plan, probe, upgraded)

    if regate:
        regated = _probe_set(
            repo_root, [plans[i] for i in regate], upgrade=False
        )
        for i, upgraded in regate.items():
            plan, probe = plans[i], regated[plans[i]]
            if not isinstance(probe.get("gate"), dict):
                gates[plan] = {}
                slots[i] = _probe_failed_row(
                    plan, f"re-gate after upgrade: {probe.get('error')}", upgraded=upgraded
                )
            else:
                slots[i] = make_row(plan, probe, upgraded)
    rows = [r for r in slots if r is not None]

    named_set = bool(args.plans or args.roadmap_id)
    try:
        seam = _seam_call(repo_root, plans, "prep", named_set, read_only=args.dry_run)
    except ValueError as exc:
        return refuse(f"seam check: {exc}")

    seam_index = _seam_findings_index(seam, [r["plan"] for r in rows])
    for row in rows:
        plan = row["plan"]
        row["seam"] = seam_index[plan]
        if row["outcome"] == "PROBE-FAILED":
            continue
        if _seam_implicated(seam, plan):
            row["outcome"] = "SEAM-REFUSED"

    for row in rows:
        plan, gate = row["plan"], gates[row["plan"]]
        # TRAP: a PROBE-FAILED row's `gates[plan]` is {} so it can never read PREPPED below; the
        # `continue` keeps that true even if the gate dict ever carries a verdict.
        if row["outcome"] in ("SEAM-REFUSED", "PROBE-FAILED"):
            continue
        if gate.get("verdict") == "PREPPED" and not args.dry_run:
            try:
                stamp = _invoke(repo_root, "plan.stamp_prepped", {"plan": plan})
            except ValueError as exc:
                # The one MUTATING op in the loop: an error is an indeterminate mutation (a stamp
                # may have landed), so the set is refused, not reported as if it had not.
                return refuse(f"{plan}: {exc}")
            # A refusal is a REPLY here, not an exception — the per-class breakdown is
            # what tells an author where the fix lands, so it is carried, not raised.
            row["outcome"] = stamp.get("outcome")
            row["mise_prepped_findings"] = stamp.get("mise_prepped_findings") or []
            if stamp.get("outcome") == "refused":
                row["verdict"] = stamp.get("verdict") or row["verdict"]
                row["failing"] = _failing_classes(stamp) or row["failing"]
                row["detail"] = _failing_details(stamp) or row["detail"]
        elif gate.get("verdict") == "PREPPED":
            row["outcome"] = (
                "already-certified"
                if row["stamp_state"] == "CERTIFIED"
                else "would-stamp"
            )

    # In a dry run `would-stamp` IS the pass — the gate returned PREPPED and only the
    # write was withheld. Counting it as short would report a clean set as a failing one
    # and send an author to fix plans that need nothing, which is the wrong half of the
    # report to get wrong: a dry run exists to be believed before anything is written.
    passing = {"stamped", "already-certified"} | ({"would-stamp"} if args.dry_run else set())
    certified = [r for r in rows if r["outcome"] in passing]
    short = [r for r in rows if r not in certified]

    residue_parts, residue_findings, residue_error = [], 0, None
    try:
        residue_parts, residue_findings = _emit_residue(
            repo_root, [r for r in rows if r["outcome"] != "PROBE-FAILED"], seam_fix
        )
    except (ValueError, OSError) as exc:
        residue_error = str(exc)

    if args.json:
        print(
            json.dumps(
                {
                    "plans": rows,
                    "certified": len(certified),
                    "dryRun": args.dry_run,
                    "opCalls": _OP_CALLS,
                    "census": _NOT_RUN,
                    "skipped": [{"plan": p, "outcome": "SKIPPED-OUT-OF-TREE"} for p in skipped],
                    "seam": _seam_spell(seam["verdict"]),
                    "seamFix": seam_fix,
                    "residueWorkflow": (
                        residue_parts[0].relative_to(repo_root).as_posix() if residue_parts else None
                    ),
                    "residueWorkflowParts": [
                        p.relative_to(repo_root).as_posix() for p in residue_parts
                    ],
                    "residueFindings": residue_findings,
                    **({"residueError": residue_error} if residue_error else {}),
                },
                indent=2,
            )
        )
    else:
        verb = "would certify" if args.dry_run else "certified"
        mode = " (dry run — nothing stamped)" if args.dry_run else ""
        pending = sum(1 for r in rows if r["outcome"] == "would-stamp")
        work = f" — {pending} would be written" if args.dry_run else ""
        print(f"mise-prep-run: {len(certified)} of {len(rows)} plan(s) {verb}{mode}{work}")
        print(f"census: {_NOT_RUN}")
        if seam_fix.get("notRun"):
            print(f"seam-fix: {seam_fix['notRun']}")
        else:
            print(
                f"seam-fix: {len(seam_fix['edgesAdded'])} edge(s) added; "
                f"converged={seam_fix['converged']}"
            )
        for c in seam_fix["skippedCycles"]:
            print(f"seam-fix: skipped cycle {c.get('plans')} path={c.get('path')} — {c.get('detail')}")
        for r in rows:
            if r in certified:
                held = r.get("mise_prepped_findings") or []
                tail = f"  [{len(held)} row(s) withheld: {', '.join(held)}]" if held else ""
                print(f"  {r['outcome']:<18} {r['plan']}{tail}")
                for f in r.get("seam") or []:
                    if not _is_missing_seam(f):
                        print(f"                     {_seam_line(f)}")
            elif r["outcome"] == "PROBE-FAILED":
                print(f"  PROBE-FAILED  {r['plan']} — {r['detail'][0]}")
                if r["upgraded"]:
                    print(f"                     upgrade: {r['upgraded']}")
                print(
                    f"                     re-run mise-prep-run --repo-root {repo_root.as_posix()} "
                    f"{r['plan']} once the op answers"
                )
            else:
                print(f"  {(r['outcome'] or r['verdict'] or 'NOT-PREPPED'):<18} {r['plan']}")
                if r["failing"]:
                    print(f"                     bar: {', '.join(r['failing'])}")
                for line in r.get("detail") or []:
                    print(f"                     said: {line}")
                if r["upgraded"]:
                    print(f"                     upgrade: {r['upgraded']}")
                elif r["verdict"] != "PREPPED":
                    from coordinator_core.roadmap import mise_residue as _mr

                    spine = _mr.spine_repairs(r["failing"])
                    for line in spine:
                        print(f"                     {line}")
                    if spine:
                        print(f"                     {_ROUTE_RESIDUE}")
                    rest = [c for c in r["failing"] if c not in _mr.SPINE_REPAIR_CLASSES]
                    if rest or not spine or "CENSUS/census-unscreenable" in r["failing"]:
                        print(f"                     {_repair_line(rest, r['plan'])}")
                for f in r.get("seam") or []:
                    if not _is_missing_seam(f):
                        print(f"                     {_seam_line(f)}")

    if not args.json:
        for line in _missing_seam_section(rows):
            print(line)

    if residue_parts:
        sys.stdout.flush()
        for part in residue_parts:
            print(
                f"\nmise-prep-run: residue workflow written — "
                f"{part.relative_to(repo_root).as_posix()}\n"
                f'Workflow({{scriptPath: "{part.as_posix()}"}})',
                file=sys.stderr if args.json else sys.stdout,
            )

    if residue_error:
        sys.stdout.flush()
        return refuse(f"residue workflow: {residue_error}")

    if short:
        refused = [r for r in short if r["outcome"] == "SEAM-REFUSED"]
        failed = [r for r in short if r["outcome"] == "PROBE-FAILED"]
        unprepped = len(short) - len(refused) - len(failed)
        lines = []
        if failed:
            lines.append(
                f"\nmise-prep-run: {len(failed)} plan(s) are PROBE-FAILED. The op errored for "
                "each; none was stamped or sent to residue. Re-run those plans."
            )
        if unprepped:
            lines.append(
                f"\nmise-prep-run: {unprepped} plan(s) are not certified. A plan that fails the "
                "bar needs authoring, not a stamp — the classes above name where. "
                + (
                    "Fire the residue workflow printed above, then re-run."
                    if residue_parts
                    else "Author it via /mise-prep, then re-run."
                )
            )
        if refused:
            lines.append(
                f"\nmise-prep-run: {len(refused)} plan(s) are SEAM-REFUSED. Follow each "
                "finding's own `route:` line above; re-authoring does not clear them."
            )
        # stdout is block-buffered on a pipe while stderr is line-buffered, so without this the
        # summary overtakes the report on a shared stream.
        sys.stdout.flush()
        print("\n".join(lines), file=sys.stderr)
        return EXIT_NOT_ALL_CERTIFIED
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
