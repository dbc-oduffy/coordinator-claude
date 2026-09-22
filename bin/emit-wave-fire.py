#!/usr/bin/env python3
"""emit-wave-fire — turn a frozen gate report into fireable plan-blitz wave scripts.

WHY THIS EXISTS. `plan-blitz`'s § Fire the wave used to end at a `Workflow({...})`
example the EM COPIED, filling the `batons` array in by hand from the gate report it
had just read. Every failure mode that example carries is a copying failure:

  - `executionOpen` reached a live wave missing, because the example that taught the
    call omitted it. The wave then dispatched no XS, closed none at the landing, and
    reported them under `routedElsewhere` — the recycling defect, entirely silent.
  - A wave over 8 batons is drained by several fires at the same `waveIndex`. Splitting
    that by hand is arithmetic done in an EM's head, once per fire, and a baton dropped
    between two fires looks exactly like a wave that finished.
  - The args object existed only inside a tool call, so nothing on disk said what was
    fired. A run could not be re-fired, diffed, or archived with its own trail.

This module makes the fire a QUERY over the frozen report rather than an assembly step.
It derives every per-baton field from the engine's own answer, splits the wave into
fires at the documented cap, and emits one standalone `.mjs` per fire — bound through
Claude-klabauter's `workflow.bind_args`, never composed here. The EM's remaining act is one
`Workflow({scriptPath})` per emitted file, with NO args.

WHAT IT DOES NOT DO. It does not read `blocked_by`, derive a wave, decide candidacy, or
re-check a gate — `roadmap.plan_gate` did all of that before the report was frozen, and
a second derivation here would be a second answer to a settled question. It does not
fire: keeping that one call explicit is what makes a runaway chain impossible, the same
boundary `mise-prep-entry.py` holds on the other side of the landing.

THE REPORT COMES IN TWO SHAPES, and both are on disk in live trails. `coordinator-invoke`
prints a JSON-RPC envelope, so the obvious freeze — redirect stdout — writes
`{jsonrpc, id, result: {...}}`, while a caller who unwrapped by hand writes the payload
bare. Reading only the bare shape turns an envelope into `waves == []`, which reports as
"the wave is empty" rather than "this file is wrapped", and the cheap conclusion is the
wrong one. Both are accepted here, as they are in `recycle-check.py`.

Usage:

    python3 emit-wave-fire.py --repo-root <abs> --trail-dir <abs> [--wave-index 0]
                              [--plugin-root <abs>] [--dispositions-cli <abs>]
                              [--spine-check-cli <abs>]
                              [--engine-root <abs>] [--batons-per-fire 8]

Writes `<trail-dir>/fire-<waveIndex>-<n>.mjs` per fire and prints, for each, the exact
`Workflow` invocation to make. Exit 0 on emit, 2 on a refusal that names its reason.

Arrived from DoE-claude coordinator/skills/plan-blitz/emit-wave-fire.py
(docs/plans/2026-09-18-doe-holds-no-scripts.md, chunk W3-C7). Path resolution: the
`recycle-check.py` sibling load (`_slot_order_fn`) is "engine" class (§ Path resolution) and
needed no change — that module lands beside this one in this same chunk, so
`Path(__file__).resolve().parent / "recycle-check.py"` still names it correctly. The
`--plugin-root` fallback IS "doctrine asset" class and did need one: DoE's default read
`Path(__file__).resolve().parents[2]` on the premise that this file's own tree is two levels
under the plugin root (`skills/plan-blitz/<file>`) — exactly the DoE-claude@b644d5a9 lesson, since
this file's tree is now `coordinator/bin/<file>` inside the ENGINE, and that same arithmetic would
resolve to the engine checkout, not DoE's doctrine tree. `_resolve_plugin_root()` below replaces
it, resolving through `coordinator_core.warm.caller_context :: resolve_caller_context` (the same
ladder `mise-prep-entry.py`'s SEAM 2 uses), with `--plugin-root` still honoured as an explicit
override.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

# § Fire the wave: "Batons come from waves[0], at most 8 per fire."
DEFAULT_BATONS_PER_FIRE = 8


def _resolve_plugin_root():
    """The doctrine-plugin content root, for the `--plugin-root` default.

    `workflows/plan-blitz.mjs` and everything under it (`agents/`, the CLI launchers a bare
    `--dispositions-cli`/`--spine-check-cli` guess at) is a doctrine asset (§ Path resolution) that
    stays in DoE, never this module's own tree. Resolved through
    `coordinator_core.warm.caller_context :: resolve_caller_context` — the same ladder
    `mise-prep-entry.py`'s SEAM 2 uses — which itself falls back to
    `coordinator_core.subagent_sandbox.provision_report :: resolve_plugin_root`. Returns None
    rather than guessing when neither resolves; `main()` reports that as a refusal naming
    `--plugin-root`, the same shape as a resolved root that does not carry `plan-blitz.mjs`.
    """
    import lib  # noqa: F401 -- bootstraps coordinator/bin/lib onto sys.path

    from cc_invoke import require_colocated_engine_on_path

    require_colocated_engine_on_path(__file__)
    from coordinator_core.warm.caller_context import resolve_caller_context

    root = resolve_caller_context().plugin_root
    return Path(root) if root else None

EXIT_OK = 0
EXIT_REFUSED = 2


# The planning report states the plan it wrote in its own first lines. It is the per-baton record
# that survives in the slot even when the run's `wave-result.json` was never archived (a fire killed
# before its landing), so it is read as the fallback source of `planPath`.
_PLAN_LINE = re.compile(r"^\*\*Plan:\*\*\s*`([^`]+)`", re.M)

_POINTER_SUFFIX = "-pointer.md"


def _slot_order_fn():
    """`coordinator_core.ops.dispatch_emit.slot_order.slot_order`, imported rather than
    re-derived.

    Both readers order the same slots for the same reason, and the ordering is subtle enough to get
    wrong twice in the same way: `wave-10-…` sorts before `wave-2-…` as text, so a lexical sort
    reports a ten-wave run's oldest records as its newest.

    Both files now import the one
    `coordinator_core` definition directly instead of this file loading `recycle-check.py` by
    file path via `importlib.util`. Engine import happens here, inside a function, never at
    module scope -- keeps this module's body pure so `serve_classifier` still classifies this
    file warm-servable.
    """
    import lib  # noqa: F401 -- bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_colocated_engine_on_path

    require_colocated_engine_on_path(__file__)
    from coordinator_core.ops.dispatch_emit.slot_order import slot_order

    return slot_order


def _latest_wave_slot(trail_dir: Path, baton_id: str) -> Path | None:
    """The wave slot holding this baton's LATEST pointer records, or None if it has none.

    `repair-…` slots are skipped rather than ordered last: a repair re-emits no reviewer, so its
    slot holds an integration report and no pointers. Reading one as the pointer source hands
    `reviews: []` to a baton whose reviews are on disk one directory over, and the workflow then
    refuses a baton that was repairable all along.
    """
    order = _slot_order_fn()
    slots = [
        p
        for p in trail_dir.glob(f"wave-*/{baton_id}.review-*{_POINTER_SUFFIX}")
    ]
    if not slots:
        return None
    return max(slots, key=lambda p: order(trail_dir, p)).parent


def _plan_path_for(slot: Path, baton_id: str) -> str | None:
    """This baton's plan, off the slot's own records. The landing's `wave-result.json` is the
    first source because the verdict row is what the repair re-dispositions; the planning report
    is the fallback for a fire that died before it landed."""
    result = slot / "wave-result.json"
    if result.is_file():
        try:
            data = json.loads(result.read_text(encoding="utf-8"))
        except ValueError:
            data = {}
        for lane in ("pulled", "ready", "replan"):
            for row in data.get(lane) or []:
                if isinstance(row, dict) and row.get("batonId") == baton_id and row.get("planPath"):
                    return row["planPath"]
    report = slot / f"{baton_id}.planning-report.md"
    if report.is_file():
        m = _PLAN_LINE.search(report.read_text(encoding="utf-8"))
        if m:
            return m.group(1)
    return None


def _repair_entry(trail_dir: Path, repo_root: Path, baton_id: str) -> tuple[dict | None, str | None]:
    """Resolve one baton's `repairBatons` entry from the trail, or say why it cannot be.

    Returns (entry, refusal). The refusals mirror the workflow's own, deliberately: the workflow
    refuses the same cases at fire time, and catching them here costs a print instead of a fire.
    """
    slot = _latest_wave_slot(trail_dir, baton_id)
    if slot is None:
        return None, (
            f"{baton_id}: no reviewer pointer records under any wave slot of {trail_dir}. "
            "A trail written before the structured pointer contract carries bare paths, not "
            "records, and is not repairable."
        )
    plan_path = _plan_path_for(slot, baton_id)
    if not plan_path:
        return None, (
            f"{baton_id}: {slot.name} names no plan for it — neither a landed verdict row nor a "
            "planning report. Repair re-dispositions a plan; there is none to read."
        )

    reviews: list[dict] = []
    unresolved: list[dict] = []
    for pointer in sorted(slot.glob(f"{baton_id}.review-*{_POINTER_SUFFIX}")):
        try:
            record = json.loads(pointer.read_text(encoding="utf-8"))
        except ValueError as exc:
            unresolved.append({"pointerPath": str(pointer), "error": f"unreadable: {exc}"})
            continue
        if not isinstance(record, dict) or "verdict" not in record:
            return None, (
                f"{baton_id}: {pointer.name} carries no `verdict` — the pre-contract bare-path "
                "shape. Integrating it would apply findings under a verdict nobody wrote."
            )
        target = Path(record.get("sidecarPath") or "")
        if not target.is_absolute():
            target = repo_root / target
        if record.get("sidecarPath") and target.is_file():
            reviews.append(record)
        else:
            unresolved.append(
                {"pointerPath": str(pointer), "error": f"sidecar missing at {target}"}
            )

    if unresolved:
        return None, (
            f"{baton_id}: {len(unresolved)} pointer(s) name a sidecar that is gone "
            f"({unresolved[0]['error']}). Repair disposition the whole baton or none of it."
        )
    if not reviews:
        return None, f"{baton_id}: {slot.name} holds no resolvable reviewer pointer for it."
    return (
        {
            "batonId": baton_id,
            "planPath": plan_path,
            "reviews": reviews,
            "unresolvedPointers": [],
        },
        None,
    )


def _gate_payload(path: Path) -> dict:
    """The report's payload, whether frozen as the JSON-RPC envelope or as `result`."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "result" in data and "waves" not in data:
        inner = data.get("result")
        if isinstance(inner, dict):
            return inner
    return data if isinstance(data, dict) else {}


def _pack_by_plan(entries: list[dict], per: int) -> list[list[dict]]:
    """Split a wave into fires of at most `per` batons, never across a shared `planPath`.

    Batons linking one plan are one unit: in different fires they are two concurrent waves
    authoring one file, and whichever integrator writes last wins silently. A unit is placed
    whole — over the cap when it alone exceeds it — and wave order is otherwise kept.

    Fires are balanced, not filled greedily: a fire's wall clock is roughly flat in its size, so
    10 batons at a cap of 8 run as 5+5 rather than 8+2 — the same fire count, finishing sooner."""
    units: dict[object, list[dict]] = {}
    for n, entry in enumerate(entries):
        key = entry.get("planPath") or ("__unplanned__", n)
        units.setdefault(key, []).append(entry)
    fire_count = -(-len(entries) // per)
    target = -(-len(entries) // fire_count) if fire_count else per
    fires: list[list[dict]] = []
    for unit in units.values():
        if fires and len(fires[-1]) + len(unit) <= target:
            fires[-1].extend(unit)
        else:
            fires.append(list(unit))
    return fires


def _parse_porcelain(stdout: str) -> set[str]:
    """Paths named by `git status --porcelain` output, forward-slashed; a rename's new path."""
    paths = set()
    for line in stdout.splitlines():
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        paths.add(path.strip('"').replace("\\", "/"))
    return paths


def _live_writer_paths(repo_root: Path, rel_paths: list[str]) -> set[str] | None:
    """Baton records a live writer holds — untracked, or modified in the working tree.

    A baton whose record is uncommitted is being written right now: a minter stamped it
    `pickup_ready` before its commit, or a peer is mid-edit on its gate fields. The gate
    reads the working tree and cannot tell, and by contract spawns no git, so the driver
    holds these the way it holds its own in-flight batons. None when git could not answer.

    Routes through
    `coordinator_core.ops.ceremony.git_native._git` instead of a hand-rolled
    `subprocess.run`. NOT `git_native.dirty_relpaths_from_porcelain`: that helper fails
    CLOSED (treats every candidate as dirty on a git failure), while this caller's own
    contract fails OPEN on purpose -- "none were held" plus a printed warning -- so the
    `None` sentinel below is preserved rather than folded into that helper's opposite
    failure policy.
    """
    if not rel_paths:
        return set()
    import lib  # noqa: F401 -- bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_colocated_engine_on_path

    require_colocated_engine_on_path(__file__)
    from coordinator_core.ops.ceremony.git_native import _git as _git_native

    result = _git_native(
        ["status", "--porcelain", "--untracked-files=all", "--", *rel_paths],
        cwd=repo_root,
        timeout=60,
    )
    return _parse_porcelain(result.stdout) if result.ok else None


def _plans_edited_since(repo_root: Path, report_path: Path, plans: list[str]) -> list[str]:
    """Plans whose file changed after the gate report was frozen.

    THE BETWEEN-WAVES SEAM. The skill forbids intervening DURING a wave and says nothing about the
    gap BETWEEN waves — which is exactly where a pulled baton is settled, and settling one means
    editing its plan. Re-fire that baton and the next wave's planner re-authors the same plan from
    the BATON, seeing neither the previous trail nor the EM's settlement, and the second author
    silently overwrites the first. Measured on project-rag: a settled prime exit criterion was
    rewritten by the next wave's planner, dropping the clause the freshly committed falsifier
    asserts, so the instrument could not go green against its own criterion. Nothing failed loudly.

    This is the cheap half — mechanism, no judgment. It names the collision at emit time; what to
    do about it (fire anyway, re-freeze the gate, or hand the settlement to the planner) stays the
    driver's call, because only the driver knows whether the edit was theirs.
    """
    if not plans:
        return []
    try:
        frozen = report_path.stat().st_mtime
    except OSError:
        return []
    touched = []
    for rel in plans:
        path = repo_root / rel
        try:
            if path.is_file() and path.stat().st_mtime > frozen:
                touched.append(rel)
        except OSError:
            continue
    return touched


def _shared_wave_slots(payload: dict, wave_ids: list) -> list:
    """Wave ids that more than one `batons[]` record answers to, with their paths.

    `waves[]` is keyed by baton id and a baton id is NOT unique: a succession
    chain and a roadmap stub's fan-out both share one deliberately. Binding
    `batons[]` into a dict therefore collapses each such group to whichever
    record happens to be read last, and every consumer walking `waves` reaches
    that one alone -- the rest are unreachable, with nothing raised on any
    surface.

    Computed from `batons[]` directly rather than read off the gate's own
    `shared_wave_slot[]`, which is not carried by every engine this script
    resolves against: an absent field reads as an empty list, so consuming it
    alone would fail OPEN on exactly the engines that cannot report the
    collapse. The gate's field, where present, is corroboration and is unioned
    in below; the local computation is what makes the check load-bearing.

    Negative spec: this NAMES a collapse, it never repairs one. The sharing is
    legitimate, so picking a survivor here would silently resolve a question
    that belongs to the driver.
    """
    wanted = set(wave_ids)
    seen: dict = {}
    for baton in payload.get("batons") or []:
        slot_id = baton.get("id")
        if slot_id in wanted:
            seen.setdefault(slot_id, []).append(baton.get("path") or "<no path>")
    collapsed = {i: paths for i, paths in seen.items() if len(paths) > 1}

    # Review (Kira revision, coordinator-overengineering-reviewer finding 3, applied-modified):
    # the gate's real shape (`coordinator_core/roadmap/plan_gate.py :: assemble_plan_gate`, the
    # `shared_wave_slot_rows` block) is {"id", "wave", "members": [{"path", "title"}, ...]} --
    # the bare-id and "paths" shapes
    # below were guessed and matched nothing the engine emits; reading them as bare strings fed
    # dicts into the final `sorted(paths)` and raised TypeError on a gate-only slot with two or
    # more members. Kept the union (a slot the gate names that the local batons[] scan did not
    # reach is still worth reporting) but read only the shape the engine actually produces.
    for entry in payload.get("shared_wave_slot") or []:
        if not isinstance(entry, dict):
            # Review (code-reviewer, slice D, nit, applied): corroboration-only and
            # engine-controlled, but a malformed entry from a future engine revision
            # should not vanish silently -- name it so drift is visible without
            # blocking the local batons[] scan that remains the load-bearing check.
            print(
                f"  NOTE: shared_wave_slot entry is not a dict ({entry!r}); skipped as "
                "corroboration only, batons[] scan is unaffected",
                file=sys.stderr,
            )
            continue
        slot_id = entry.get("id")
        if slot_id not in wanted:
            continue
        members = [m.get("path") for m in entry.get("members") or [] if isinstance(m, dict) and m.get("path")]
        collapsed.setdefault(slot_id, members or ["<named by the gate; members not carried>"])

    return sorted((i, sorted(paths)) for i, paths in collapsed.items())


def _report_predates_a_landing(trail_dir: Path, wave_number: int, wave_ids: list) -> str:
    """The report is SHAPE-RIGHT and TIME-WRONG: frozen before a landing this run
    has since made, so it proposes batons that landing already advanced.

    Nothing else in this module can see it. A stale report is internally consistent —
    every `batons[]` lookup resolves, every field is present, the manifest reads as a
    healthy wave. The existing checks all ask the report about itself, and it answers
    correctly; what is wrong is WHEN it was frozen, which no self-consistency check
    reaches. Measured on example-market-data-repo 2026-09-11: a 6-candidate wave 2 emitted
    18 batons across 3 fires from wave 0's report, five of them plans the same run had
    approved or certified in the intervening three hours and three open in plan-author
    agents at that moment. Caught by a human read, not by this script.

    The question is asked of what the TRAIL DECLARES, never of file mtimes. A landing
    record names `nextWave.waveIndex` and the exact batons it hands forward, so a report
    frozen after that landing cannot propose a baton the landing did not hand forward.
    An mtime comparison would rest the same refusal on filesystem metadata that a
    checkout or a sync rewrites without anyone writing the thing it stands for —
    claude-klabauter-1e's correction to the first-proposed fix, and the reason this reads
    a declaration instead.

    Returns the refusal text, or "" when nothing is wrong or nothing can be decided.
    Silent when the prior landing is absent (wave 0, or a landing not yet written): an
    absent record is not evidence of staleness.
    """
    if wave_number <= 0:
        return ""
    prior = trail_dir / f"wave-{wave_number - 1}.landing.json"
    if not prior.is_file():
        return ""
    try:
        landing = json.loads(prior.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    nxt = landing.get("nextWave")
    if not isinstance(nxt, dict) or nxt.get("waveIndex") != wave_number:
        return ""
    handed = {
        b.get("id") for b in (nxt.get("batons") or []) if isinstance(b, dict) and b.get("id")
    }
    if not handed:
        return ""
    extra = [i for i in wave_ids if i not in handed]
    if not extra:
        return ""
    # A LIMIT-CAPPED landing hands forward `--limit` batons and says so in the same object:
    # `remaining` is what it did not carry. A fresh gate read then legitimately proposes more,
    # and calling that report time-wrong accuses the EM of a staleness it does not have.
    # Reported by example-game-workbench-repo-b8, who landed at the default 8 with `remaining: 21`,
    # was refused against a correctly-fresh 29-baton report, and read blitz_land source to find
    # out which side was wrong.
    remaining = nxt.get("remaining")
    if isinstance(remaining, int) and remaining > 0:
        return (
            f"this report proposes {len(extra)} baton(s) that {prior.name} did not hand forward, "
            f"and that landing declares `remaining: {remaining}` — it was LIMIT-CAPPED, so it "
            f"handed forward {len(handed)} of a larger set and this report is not thereby stale. "
            "Re-land the same wave-result files at a `--limit` above the remainder if you want "
            "them all in one hand-forward; otherwise emit from a freshly frozen report and take "
            "the extra batons deliberately."
        )
    shown = extra[:8]
    tail = f" (and {len(extra) - len(shown)} more)" if len(extra) > len(shown) else ""
    return (
        f"this report proposes {len(extra)} baton(s) that {prior.name} did not hand "
        f"forward to wave {wave_number}: {shown}{tail}. That landing declares "
        f"{len(handed)} candidate(s), so the report was frozen BEFORE it — it is "
        "shape-right and time-wrong, which is why nothing else here refused it. "
        "Every lookup in a stale report resolves and the manifest reads healthy. "
        f"Re-freeze the gate to {trail_dir.name}/wave-{wave_number}.gate-report.json "
        "and emit from that."
    )


def _baton_arg(record: dict) -> dict:
    """One `batons[]` entry, every field derived — never defaulted, never typed.

    `executionOpen` has no default on purpose. A baton whose report carries no
    `execution_gate` is a report this script will not paper over: the wave's XS lane
    tests it with `=== true`, so a wrong-by-omission `false` dispatches nothing and
    says so nowhere.
    """
    gate = record.get("execution_gate")
    if not isinstance(gate, dict) or "open" not in gate:
        raise ValueError(
            f"baton {record.get('id')!r} carries no `execution_gate.open` in the frozen "
            "report. `executionOpen` is REQUIRED and has no default — omitting it makes "
            "every XS fail the wave's dispatch test silently. Re-freeze the report from "
            "a `roadmap.plan_gate` read that includes it."
        )
    plan = record.get("plan") or {}
    return {
        "id": record["id"],
        "path": record["path"],
        "title": record.get("title") or "",
        "sized": bool(record.get("sized")),
        "planPath": plan.get("path"),
        "executionOpen": bool(gate["open"]),
    }


def _engine_ref(repo_root: Path, script_source: Path) -> dict:
    """What code this fire is a frozen copy of, recorded at emit time.

    Three fields because three different questions get asked of a wave result after the fact: the
    repo `head` says what the tree was at, `workflowSha` identifies the workflow BYTES the fire
    actually carries (the file may be dirty, so HEAD alone is not it), and `dirty` says whether
    those bytes are committed anywhere at all. A fire built from an uncommitted workflow is normal
    on a repair run and misleading without the flag.

    Fails open to nulls with a `reason`. A wave that cannot be emitted because git was unavailable
    would be a worse outcome than one whose provenance is unknown — and an unknown that says so is
    not the silence this field exists to end.
    """
    ref: dict = {
        # WHICH TREE, not only which bytes. A sha and a HEAD from two different checkouts are
        # INCOMPARABLE rather than merely different, and without the path "2 distinct workflows in
        # this trail" reads as version skew when it is tree skew. Not hypothetical where the
        # doctrine plane and the published engine plane are separate checkouts: each holds files
        # the other does not — this workflow lives only in the doctrine tree, while the prep
        # upgrader lives only in the published engine — so a cross-tree difference is the plane
        # boundary working as designed and must never be read as a staleness finding. Reported by
        # example-store-repo-fb.
        "repoRoot": str(repo_root),
        "workflowPath": str(script_source),
        "head": None,
        "workflowSha": None,
        "dirty": None,
        "reason": None,
    }
    try:
        ref["workflowSha"] = hashlib.sha1(script_source.read_bytes()).hexdigest()
    except OSError as exc:
        ref["reason"] = f"workflow bytes unreadable ({exc})"
        return ref
    try:
        # One
        # `git status --porcelain=v2 --branch -- <path>` call returns both the HEAD oid
        # (the `# branch.oid` header line) and this path's dirtiness (any entry line at
        # all), replacing the prior `rev-parse HEAD` + `status --porcelain` pair. Routed
        # through `coordinator_core.ops.ceremony.git_native._git` rather than a
        # hand-rolled `subprocess.run`.
        import lib  # noqa: F401 -- bootstraps coordinator/bin/lib onto sys.path
        from cc_invoke import require_colocated_engine_on_path

        require_colocated_engine_on_path(__file__)
        from coordinator_core.ops.ceremony.git_native import _git as _git_native

        result = _git_native(
            ["status", "--porcelain=v2", "--branch", "--", str(script_source)],
            cwd=repo_root,
            timeout=15,
        )
        if not result.ok:
            ref["reason"] = "git status --porcelain=v2 --branch failed"
            return ref
        head = None
        dirty = False
        for line in result.stdout.splitlines():
            if line.startswith("# branch.oid "):
                head = line[len("# branch.oid ") :].strip()
            elif line and not line.startswith("#"):
                dirty = True
        if head is None or head == "(initial)":
            ref["reason"] = "git status --porcelain=v2 --branch reported no HEAD oid"
            return ref
        ref["head"] = head
        ref["dirty"] = dirty
    except (OSError, subprocess.SubprocessError) as exc:
        ref["reason"] = f"git unavailable ({exc})"
    return ref


def _trail_provenance(trail_dir: Path, fresh_ref: dict) -> list[str]:
    """How many DIFFERENT workflows this trail's fire scripts were built from.

    A trail accumulates fires across a long run, and each is a full standalone COPY of
    `plan-blitz.mjs`, not a wrapper around it — so an emitted-but-unfired fire silently carries
    whatever the workflow said when it was emitted. Measured on this run: fires 15 through 21 sat
    emitted through a day of repairs to the very defects they would have run into.

    WHAT THIS DELIBERATELY DOES NOT DO IS COMPARE A FIRE AGAINST THE CURRENT FILE. On a repair run
    the workflow moves under the reader — example-store-repo-fb watched `plan-blitz.mjs` go from 242712
    to 244313 bytes while measuring it — so "differs from the source" is true of nearly every fire
    nearly always, and a warning that fires every time is one a driver learns to skip. Worse, it
    points the wrong way: fb's `fire-3-1` was emitted 60 seconds BEFORE the commit that is supposed
    to contain its fix and carries the fix anyway, because it was bound from the working tree. A
    HEAD-based or source-diffing check would have told them to throw away a live 40-minute wave to
    acquire code it was already running.

    So the reported fact is about the TRAIL and is stable: how many distinct workflows its fires
    hold, and which fires hold which. Silent when they agree. What a fire CONTAINS is then a grep
    against the fire itself — the one question whose answer does not move.
    """
    groups: dict[tuple, list[str]] = {}
    for path in sorted(trail_dir.glob("fire-*.mjs")):
        text = path.read_text(encoding="utf-8", errors="replace")
        sha = re.search(r'"workflowSha"\s*:\s*"([0-9a-f]{40})"', text)
        # JSON-DECODED, never compared raw. The bound literal is JSON, so a Windows path arrives
        # with its separators escaped and the same tree reads as two — measured by this file's own
        # test, which is the only reason it is not live.
        tree_raw = re.search(r'"workflowPath"\s*:\s*("(?:[^"\\]|\\.)*")', text)
        try:
            tree = json.loads(tree_raw.group(1)) if tree_raw else None
        except ValueError:
            tree = None
        # A fire carrying no `engineRef` predates the field. That says nothing about its bytes, so
        # it is its own group rather than being lumped in with a known one.
        key = (sha.group(1), tree) if sha else (None, None)
        groups.setdefault(key, []).append(path.name)
    fresh = (fresh_ref.get("workflowSha"), fresh_ref.get("workflowPath"))
    if fresh[0] and fresh not in groups:
        groups[fresh] = []
    if len(groups) < 2:
        return []
    # Same bytes from two checkouts is not skew and the line says so, because the reader's next
    # move differs: version skew may warrant a re-emit, tree skew never does.
    trees = {t for _s, t in groups if t}
    lines = []
    for (sha, tree), names in sorted(groups.items(), key=lambda kv: (kv[0][0] is None, kv[0])):
        if sha is None:
            label = "(no engineRef — predates the field)"
        else:
            label = f"{sha[:12]}…"
            if len(trees) > 1 and tree:
                label += f" from {tree}"
        if (sha, tree) == fresh:
            label += "  <-- just bound"
        lines.append(f"    {label}: {', '.join(names) or '(this emit only)'}")
    if len(trees) > 1:
        lines.append(
            "    NOTE: more than one CHECKOUT is represented. Refs from different trees are "
            "incomparable, not merely different — that is a plane boundary, not staleness."
        )
    return lines


def _bind(
    script_path: Path,
    args: dict,
    live_engine_tree: bool = False,
) -> str:
    """Compose the standalone script through claude-klabauter's `workflow.bind_args`, IN-PROCESS.

    Delegated, never reimplemented: the binding rule (where the literal goes, which
    sources are refused) is engine-owned, and a second composer here is how the two
    drift. Through 2026-09-18 the engine was reached through its own `coordinator-invoke`
    subprocess, because this CLI lived in DoE-claude and could not import the engine
    directly. It now lives inside the engine repo itself
    (`docs/plans/2026-09-18-doe-holds-no-scripts.md`) and is served by the warm door, so
    that boundary is gone: `coordinator_core` is importable off this same tree
    (`cc_invoke.require_colocated_engine_on_path`), and DR-344 forbids spawning a cold
    interpreter per fire — of which a wave can carry several — when one in-process
    `coordinator_core.ipc.dispatch_message` call does the same job with the same
    envelope, the same stamp gate, and the same result/error translation, for zero
    spawns. See `coordinator_core/tests/test_no_unbatched_per_item_git_spawn.py`.
    """
    import lib  # noqa: F401 -- bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_colocated_engine_on_path

    require_colocated_engine_on_path(__file__)

    import asyncio

    from coordinator_core.ipc import allow_unstamped_dispatch, dispatch_message

    if live_engine_tree:
        allow_unstamped_dispatch()

    msg = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "workflow.bind_args",
        "params": {"script_path": str(script_path), "args": args},
    }
    reply = asyncio.run(dispatch_message(msg, caller="emit-wave-fire.py"))
    if "error" in reply:
        message = str((reply["error"] or {}).get("message") or reply["error"])
        if "Method not found" in message and "bind_args" in message:
            # The in-process engine ANSWERED and does not carry the op yet — a stale
            # checkout, not a resolution failure (there is no separate mirror to
            # misresolve now that this CLI dispatches against its own tree).
            raise ValueError(
                f"workflow.bind_args refused: {message}. This checkout of "
                "coordinator_core does not carry the op — pull the latest "
                "claude-klabauter."
            )
        raise ValueError(f"workflow.bind_args refused: {message}")
    script = (reply.get("result") or {}).get("script")
    if not isinstance(script, str) or not script:
        # A reply carrying neither `error` nor a usable `script` must REFUSE, not raise.
        # `main()` catches ValueError and names the reason; a KeyError escapes as a
        # traceback, which reads as this module being broken rather than the engine
        # having answered something unexpected.
        raise ValueError(
            "workflow.bind_args returned a reply carrying neither `error` nor a "
            f"`result.script` string. Got keys: {sorted(reply)!r}"
        )
    return script


def _settings_home_bin(name: str) -> str | None:
    """A settings-home launcher path, or None. Rung 2 of the resolution ladder."""
    settings_home = os.environ.get("COORDINATOR_SETTINGS_HOME") or str(
        Path(os.environ.get("CLAUDE_HOME") or Path.home()) / ".coordinator-claude-settings"
    )
    candidate = Path(settings_home) / "bin" / name
    if candidate.is_file():
        return str(candidate)
    return shutil.which(name)


def _engine_env_prefix(engine_root: Path) -> str:
    """`COORDINATOR_ENGINE_ROOT=<engine> `, or empty. Part of the injected literal.

    `append-integrator-dispositions` resolves CLAUDE_KLABAUTER_ROOT before it does anything, and on a
    box with no machine-local registry that resolution fails outright — the CLI exits 3
    with a bootstrap message naming this variable as one of its remedies. The integrator
    then reports the op refused and correctly declines to hand-author around it, so the
    wave runs every review and records not one disposition. Silent by construction: the
    refusal loses only the RECORD. Measured 2026-09-10 on example-cockpit-repo, wave 4 — three
    sidecars, no `## Integrator Dispositions` block on any of them.

    The dispatching side already resolved an engine root to bind the fire with; the agent
    running the CLI cannot. Same rung-3 reasoning as the interpreter and DOE_ROOT.
    """
    if os.environ.get("COORDINATOR_ENGINE_ROOT"):
        return ""
    if os.name != "posix":
        return ""
    return f"COORDINATOR_ENGINE_ROOT={shlex.quote(str(engine_root))} "


#: The two layouts a published/mirrored plugin ships the registry manifest in. The private
#: DoE tree keeps it under `coordinator/`; the OSS publish row ships it flat at plugin root.
#: `coordinator_registry._mp_candidate_manifest_path` probes exactly this pair, so exporting
#: a root that satisfies neither is exporting a value its consumer cannot use.
_MANIFEST_RELPATHS = (
    Path("schemas") / "coordinator-registry.manifest.json",
    Path("coordinator") / "schemas" / "coordinator-registry.manifest.json",
)


def _registry_manifest_prefix(engine_root: Path, plugin_root: Path) -> str:
    """`DOE_ROOT=<a root the manifest actually resolves under> `, or empty.

    Both CLIs load the registry manifest, and an install-less box does not have it in the
    engine tree — the schemas ship with the DOCTRINE repo, not the engine mirror. The
    CLI's own diagnostic names `DOE_ROOT` as the remedy, but it is a remedy nobody reads:
    the failure happens inside a dispatched reviewer, where its stderr becomes "the
    sidecar step did not work".

    VALIDATE THE VALUE YOU EXPORT. An earlier cut checked for the manifest under
    `<plugin_root>/schemas/` and then exported `plugin_root.parent`, which agree only when
    the plugin root's basename is literally `coordinator` — the private layout. Under the
    published layout, where the manifest sits flat at plugin root, that exported a root
    the consumer cannot resolve from, AND `DOE_ROOT` is taken as-is ahead of every other
    rung and is the state-write root. A wrong value there is worse than none: it is the
    plausible-but-wrong invocation this module exists to stop emitting.

    POSIX-shaped, and deliberately not emitted elsewhere: `VAR=x cmd` is not a command on
    a PowerShell host. A Windows box in this state gets no prefix and the CLI's own
    diagnostic, which names the variable — a loud failure rather than a wrong literal.
    """
    if any((engine_root / rel).is_file() for rel in _MANIFEST_RELPATHS):
        return ""
    if os.name != "posix":
        return ""
    for candidate in (plugin_root.parent, plugin_root):
        if any((candidate / rel).is_file() for rel in _MANIFEST_RELPATHS):
            return f"DOE_ROOT={shlex.quote(str(candidate))} "
    return ""


def _engine_bin(
    engine_root: Path | None, name: str, plugin_root: Path | None = None
) -> str | None:
    """The engine checkout's own copy of a CLI, as a runnable invocation, or None.

    Rung N's rung 3. On a box with no settings home — every ephemeral container — the
    launcher rungs above resolve nothing, and the two CLIs this module injects are
    exactly the two whose absence fails SILENTLY downstream. The engine source is on
    disk regardless, but these files carry no shebang and no executable bit, so the path
    alone is not an invocation: the interpreter has to be part of the literal. Building
    it here is the whole of rung 3's "the dispatching side has a filesystem" — leaving it
    to the caller means a human hand-types an interpreter prefix per run, and a
    hand-typed resolution is the thing this module exists to remove.
    """
    if engine_root is None:
        return None
    candidate = engine_root / "coordinator" / "bin" / f"{name}.py"
    if not candidate.is_file():
        return None
    prefix = _engine_env_prefix(engine_root)
    if plugin_root is not None:
        prefix += _registry_manifest_prefix(engine_root, plugin_root)
    return (
        f"{prefix}{shlex.quote(sys.executable)} {shlex.quote(str(candidate))}"
    )


#: Agent definitions every wave dispatches under. The roster the write guards consult is walked
#: from the plugin's own `agents/*.md`, so their presence IS the question `--plugin-agents-available`
#: asks — there is nothing to assume.
_WAVE_AGENT_DEFINITIONS = ("plan-author.md", "blitz-em.md", "review-integrator.md")


def _plugin_agents_available(plugin_root: Path | None, explicit: str) -> tuple[bool, str]:
    """Resolve whether `coordinator:*` agent types resolve here. Returns (value, why).

    `false` is not a safe default and must never be reached by omission. An `agent()` call
    carrying no `agentType` is stamped `workflow-subagent` by the Workflow runtime — a non-empty
    type on no roster — and the write guards confine it on that roster absence. The planner is
    then refused its own plan body by `block_subagent_plan_body_write` and denied
    `plan-spine-check.py` by `block-reviewer-bash-outside-allowlist`, so a wave dispatches, burns
    its full token budget, writes planning research to sidecars, and lands no plan at all.
    Absence of a label is not neutral; it is the most-confined state there is
    (`A-WORKFLOW-DISPATCH-WITHOUT-WITHROLE-IS-CONFINED`).

    Negative-spec: this NEVER probes the harness for whether a type would resolve at dispatch
    time — no such read exists here. It answers the narrower question it can answer honestly,
    "does this plugin root define the agents the wave dispatches", and says which question it
    answered.
    """
    if explicit in ("true", "false"):
        return explicit == "true", f"passed --plugin-agents-available {explicit}"
    if plugin_root is None:
        return False, "no plugin root resolved, so no agents/ directory to read"
    agents_dir = plugin_root / "agents"
    missing = [n for n in _WAVE_AGENT_DEFINITIONS if not (agents_dir / n).is_file()]
    if missing:
        return False, f"{agents_dir} is missing {', '.join(missing)}"
    return True, f"{agents_dir} defines every agent this wave dispatches"


def _default_spine_check_cli(plugin_root: Path | None) -> str | None:
    """`plan-spine-check`, resolved off the PLUGIN root — rung 3's plugin-local case.

    It ships in the coordinator plugin's own `bin/`, never in the repo being planned, so
    the brief's `<repoRoot>/coordinator/bin/plan-spine-check.py` resolves to nothing
    everywhere except the plugin's own source tree. The planner then runs a check the
    brief calls "runnable, not advice", gets "No such file or directory", and returns a
    plan whose spine was never checked — silently, because a missing file reads as a
    tooling hiccup rather than a skipped gate.
    """
    if plugin_root is None:
        return None
    candidate = plugin_root / "bin" / "plan-spine-check.py"
    if not candidate.is_file():
        return None
    return f"{shlex.quote(sys.executable)} {shlex.quote(str(candidate))}"



def _refuse_live_tree_on_a_stamped_engine(engine_root, live_engine_tree: bool) -> str | None:
    """Enforce `--live-engine-tree`'s own stated precondition, or refuse.

    The flag forwards the engine's `--allow-unstamped-dispatch`, whose own help reads
    "For deliberate manual testing of engine changes ONLY". Unconditioned, it applies to
    whichever rung resolved — including a settings-home launcher on a fully installed box
    with a stamped published engine, which is precisely the case it must never touch.

    It also disarms MORE than the stamp gate: the same engine flag decides whether a
    warm-unavailable dispatch may fall through to a cold spawn, so passing it re-enables
    a silent-slow degrade. Both are reasons to require that the caller really is pointed
    at an unstamped tree before it is honoured.
    """
    if not live_engine_tree:
        return None
    if engine_root is None:
        return (
            "--live-engine-tree needs --engine-root: it exists to reach an UNSTAMPED "
            "authoring tree, and without one it would hand the engine's manual-testing "
            "carve-out to whatever rung happens to resolve, installed box included."
        )
    if (engine_root / "coordinator_core" / "_engine_stamp").is_file():
        return (
            f"--live-engine-tree refused: {engine_root} carries a build stamp, so it is a "
            "PUBLISHED engine and needs no carve-out. The flag disarms the stamp gate AND "
            "the cold-fallback refusal; neither is appropriate against a published mirror. "
            "Drop the flag."
        )
    return None


def _archived_fire_identity(path: Path) -> tuple[int | None, frozenset[str]] | None:
    """`(waveIndex, baton ids)` of an already-emitted fire, or None if unreadable.

    The collision guard keys on THIS, not on the bound bytes. Bytes carry emit-time
    ambient facts — `sys.executable`, and whether `COORDINATOR_ENGINE_ROOT` happened to
    be exported, which decides whether `_engine_env_prefix` contributes — so the same
    fire re-emitted from a different shell produces different bytes and a byte guard
    calls it a different fire. What makes two emits the SAME fire is the wave and the
    batons, and nothing else.
    """
    try:
        text = path.read_text(encoding="utf-8")
        marker = text.index("const args = ")
        obj, _ = json.JSONDecoder().raw_decode(text, marker + len("const args = "))
    except (OSError, ValueError):
        return None
    if not isinstance(obj, dict):
        return None
    batons = obj.get("batons")
    if not isinstance(batons, list):
        return None
    ids = frozenset(
        b.get("id") for b in batons if isinstance(b, dict) and b.get("id")
    )
    index = obj.get("waveIndex")
    return (index if isinstance(index, int) else None, ids)


def _default_arming_check_cli(plugin_root: Path | None) -> str | None:
    """`instrument-can-report-red`, resolved off the PLUGIN root. Same rung, worse citation.

    The brief cited it as a BARE RELATIVE path, so it resolved against the planner's cwd —
    the repo being planned — and every wave outside the plugin's own tree got "No such file
    or directory". The arming line then read `N/A`, which is indistinguishable from a plan
    that declared no falsifier at all.
    """
    if plugin_root is None:
        return None
    candidate = plugin_root / "bin" / "instrument-can-report-red.py"
    if not candidate.is_file():
        return None
    return f"{shlex.quote(sys.executable)} {shlex.quote(str(candidate))}"


def _default_sidecar_cli(
    engine_root: Path | None, plugin_root: Path | None = None
) -> str | None:
    """`provision-sidecar`, resolved caller-side for the same reason as the op below.

    A reviewer cannot resolve `<machinery_root>` or `<your session id>` from inside its
    brief — both are facts about this box. An agent handed those placeholders invents
    them, and the invention is silent: the path it picks still carries the
    `subagent-share` segment `append-integrator-dispositions` checks for, so the findings
    are written, accepted, and simply kept somewhere the repo does not track.
    """
    return _settings_home_bin("provision-sidecar") or _engine_bin(
        engine_root, "provision-sidecar", plugin_root
    )


def _default_dispositions_cli(
    engine_root: Path | None, plugin_root: Path | None = None
) -> str | None:
    """`append-integrator-dispositions`, resolved the way rung 3 says the CALLER must.

    The op ships no launcher on a stock install, so a bareword exits 127 and the
    integrator reports the tool ABSENT — a misdiagnosis that gets escalated rather than
    fixed, while the op runs fine from its own bin/. Resolve it here, where there is a
    filesystem, and inject the literal. Returning None is honest: the workflow's brief
    then says the caller omitted it, rather than letting the integrator guess.
    """
    return _settings_home_bin("append-integrator-dispositions") or _engine_bin(
        engine_root, "append-integrator-dispositions", plugin_root
    )


def _emit_repair(args, repo_root: Path, trail_dir: Path, plugin_root: Path, engine_root, refuse) -> int:
    """Emit one repair fire, bound the same way a wave fire is — identity resolution included.

    A repair reaches only the integrator, and a confined integrator cannot run
    `append-integrator-dispositions` at all, so an unresolved identity costs a repair its entire
    point just as silently as it costs a wave its plans.

    Repair existed only as a shape the caller was told to assemble by hand — which is the one act
    § Fire the wave forbids, and for the same reasons: an args object inside a tool call is not on
    disk, so the repair cannot be re-read, re-fired or diffed, and nothing archives with the trail.
    Everything the assembly needed was already mechanical (latest wave slot, the partition rule,
    the refusals), so it is done here.
    """
    script_source = plugin_root / "workflows" / "plan-blitz.mjs"
    if not script_source.is_file():
        return refuse(f"no plan-blitz.mjs at {script_source} — pass --plugin-root")
    if not trail_dir.is_dir():
        return refuse(f"trail dir {trail_dir} does not exist — a repair reads its records")
    plugin_agents, plugin_agents_why = _plugin_agents_available(plugin_root, args.plugin_agents_available)
    print(f"  agent identities: {'declared' if plugin_agents else 'OMITTED'} — {plugin_agents_why}", file=sys.stderr)

    entries, refusals = [], []
    for baton_id in args.repair:
        entry, why = _repair_entry(trail_dir, repo_root, baton_id)
        (refusals if entry is None else entries).append(why if entry is None else entry)

    for why in refusals:
        print(f"  REFUSED {why}", file=sys.stderr)
    if not entries:
        return refuse("no repairable baton among --repair; every one is named above")

    repair_args = {
        "repoRoot": str(repo_root),
        "trailDir": str(trail_dir),
        "mode": "repair",
        "repairBatons": entries,
        # A repair's integrator needs the same two caller-resolved inputs a wave's does, and this
        # path shipped without either. `pluginAgentsAvailable` is the one that bites hardest:
        # `withRole` writes the agent's declared identity ONLY when it is true, so a repair emitted
        # without it dispatches as `workflow-subagent` — a non-empty type on no roster, which the
        # sandbox guard confines, and the confined integrator cannot run
        # `append-integrator-dispositions` at all, "regardless of path spelling". Measured on
        # example-store-repo-fb's repair: the op never executed, so every disposition record silently
        # stayed at whatever an earlier pass wrote. `spineCheckCli`'s absence is quieter and also
        # real — the integrator brief calls a missing one a CALLER defect and correctly refuses to
        # guess a repo-relative substitute, so spine validation simply never ran on a repair while
        # every wave fire got it.
        "pluginAgentsAvailable": plugin_agents,
    }
    dispositions = args.dispositions_cli or _default_dispositions_cli(engine_root, plugin_root)
    if dispositions:
        repair_args["dispositionsCli"] = dispositions
    spine_check_cli = args.spine_check_cli or _default_spine_check_cli(plugin_root)
    if spine_check_cli:
        repair_args["spineCheckCli"] = spine_check_cli
    try:
        text = _bind(script_source, repair_args, args.live_engine_tree)
    except ValueError as exc:
        return refuse(str(exc))

    # Numbered past the archive on the same rule a narrowed wave re-emit uses: a second repair of
    # the same trail is a different fire, and overwriting the first destroys the record of what it
    # re-dispositioned.
    n = 1 + max(
        (int(p.stem.rsplit("-", 1)[-1]) for p in trail_dir.glob("repair-fire-*.mjs")
         if p.stem.rsplit("-", 1)[-1].isdigit()),
        default=0,
    )
    out = trail_dir / f"repair-fire-{n}.mjs"
    out.write_text(text, encoding="utf-8", newline="\n")

    manifest = [{"fire": n, "scriptPath": str(out), "batons": [e["batonId"] for e in entries]}]
    if args.json:
        print(json.dumps({"mode": "repair", "fires": manifest, "refused": refusals}, indent=2))
        return EXIT_OK
    print(f"emit-wave-fire: repair — {len(entries)} baton(s), {len(refusals)} refused.")
    for e in entries:
        print(f"    {e['batonId']}  {len(e['reviews'])} review(s)  {e['planPath']}")
    print(f'\n  Workflow({{ scriptPath: "{out}" }})   # no args — they are bound')
    return EXIT_OK


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="emit-wave-fire",
        description="Emit fireable plan-blitz wave scripts from a frozen gate report.",
    )
    ap.add_argument("--repo-root", required=True, help="ABSOLUTE path to the repo being planned")
    ap.add_argument("--trail-dir", required=True, help="ABSOLUTE trail dir; also where scripts land")
    ap.add_argument(
        "--gate-report",
        help="frozen report for THIS wave (default: <trail-dir>/wave-<N>.gate-report.json, "
        "falling back to <trail-dir>/gate-report.json on wave 0 only). One report per wave, "
        "never one per run: a report frozen for an earlier wave is shape-right and "
        "time-wrong, and every check that asks a report about itself passes on it.",
    )
    ap.add_argument(
        "--wave-index",
        type=int,
        default=0,
        help="which wave OF THE FROZEN REPORT to fire. `roadmap.plan_gate` numbers `waves` "
        "from the READ, so every wave of a run arrives as 0 and this is almost always 0.",
    )
    ap.add_argument(
        "--wave-number",
        type=int,
        help=(
            "this run's own wave count, used for `waveIndex` in the bound args, the fire "
            "filename and the trail slot. Defaults to --wave-index. They are different "
            "questions: --wave-index indexes the frozen report, which renumbers from 0 on "
            "every read, while the trail and the landing want the run's absolute wave. "
            "Without this the run's second wave emits over its first's archived fire, and "
            "the workaround is hand-editing the frozen report — the retype this module "
            "exists to remove."
        ),
    )
    ap.add_argument("--plugin-root", help="resolved CLAUDE_PLUGIN_ROOT (default: this file's plugin root)")
    ap.add_argument("--engine-root", help="claude-klabauter root (default: $COORDINATOR_ENGINE_ROOT)")
    ap.add_argument("--dispositions-cli", help="absolute append-integrator-dispositions invocation")
    ap.add_argument("--provision-sidecar-cli", help="absolute provision-sidecar invocation")
    ap.add_argument(
        "--spine-check-cli",
        help="absolute plan-spine-check invocation (default: derived from --plugin-root). "
        "Plugin-owned tooling, so it is resolved against the PLUGIN root and never the repo "
        "being planned — the two coincide only on DoE-claude.",
    )
    ap.add_argument(
        "--live-engine-tree",
        action="store_true",
        help=(
            "the --engine-root given is claude-klabauter's live authoring tree, which carries "
            "no build stamp. The engine's own live-tree path (the PM's manual "
            "test-and-execute carve-out) is taken for the bind call and NOTHING else — every "
            "other op this run makes still goes through the engine the caller resolved. Its "
            "case is an ephemeral box whose published mirror predates `workflow.bind_args`."
        ),
    )
    ap.add_argument("--batons-per-fire", type=int, default=DEFAULT_BATONS_PER_FIRE)
    ap.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="BATON-ID",
        help=(
            "drop this baton from the emit. Repeatable. For a wave already PART-fired — "
            "another fire at this waveIndex is live over those batons, and emitting them "
            "again would run two waves against one plan. It narrows what is FIRED, never "
            "what the gate computed: the baton stays in the frozen report as a resolved "
            "blocker. An id that matches nothing in the wave is refused, not ignored."
        ),
    )
    ap.add_argument(
        "--plugin-agents-available",
        choices=("true", "false", "auto"),
        default="auto",
        help=(
            "whether coordinator:* agent types resolve on this host. Default `auto`: DETECTED "
            "from the plugin root's own agents/ directory, never assumed. `false` is NOT the "
            "safe direction on a box carrying the write guards — an undeclared agentType is "
            "stamped `workflow-subagent`, which is on no roster, so the guards confine the "
            "planner out of writing any plan at all. Measured: a whole wave of plans refused by "
            "`block_subagent_plan_body_write`, with `plan-spine-check.py` denied alongside it. "
            "A field whose wrong value costs a whole wave silently cannot have a default — the "
            "same rule this module already applies to `executionOpen`."
        ),
    )
    ap.add_argument(
        "--include-dirty",
        action="store_true",
        help="fire batons whose record is uncommitted too (default: hold them — a live writer)",
    )
    ap.add_argument(
        "--repair",
        metavar="BATON-ID",
        action="append",
        default=[],
        help="emit a REPAIR fire for these batons instead of a wave fire: their reviewer "
        "pointer records are resolved from the latest wave slot of --trail-dir and bound as "
        "`repairBatons`. No gate report is read and no reviewer, planner or scout is "
        "dispatched — the one role a repair reaches is the integrator.",
    )
    ap.add_argument("--json", action="store_true", help="emit the fire manifest as JSON")
    args = ap.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    trail_dir = Path(args.trail_dir).resolve()
    plugin_root = Path(args.plugin_root).resolve() if args.plugin_root else _resolve_plugin_root()
    plugin_agents, plugin_agents_why = _plugin_agents_available(plugin_root, args.plugin_agents_available)
    _engine = args.engine_root or os.environ.get("COORDINATOR_ENGINE_ROOT") or ""
    engine_root = Path(_engine).resolve() if _engine.strip() else None

    wave_number = args.wave_number if args.wave_number is not None else args.wave_index

    live_tree_refusal = _refuse_live_tree_on_a_stamped_engine(
        engine_root, args.live_engine_tree
    )

    # PER WAVE, not per run. One report per wave is the truth; one path per run is what
    # the old default and the skill's worked example together produced, and following both
    # literally on wave 2 reads wave 0's report. `gate-report.json` stays the wave-0 name
    # so existing trails resolve, but a later wave with no report of its own REFUSES
    # rather than falling back — silently reading the previous wave's is the whole defect.
    if args.gate_report:
        report_path = Path(args.gate_report)
    else:
        per_wave = trail_dir / f"wave-{wave_number}.gate-report.json"
        legacy = trail_dir / "gate-report.json"
        report_path = per_wave if per_wave.is_file() else legacy
        if report_path is legacy and wave_number > 0:
            # NOT a refusal. A run-wide path RE-FROZEN in place is legitimate and common,
            # and the name alone cannot tell that apart from wave 0's report left sitting
            # there. What can is the previous wave's landing declaration, checked below —
            # so this says what is being assumed and lets the evidence decide.
            print(
                f"  NOTE: no wave-{wave_number}.gate-report.json; reading {legacy.name}, "
                f"which is wave 0's name. This is correct only if you re-froze it AFTER "
                f"wave {wave_number - 1} landed. Freeze per wave and the ambiguity goes away.",
                file=sys.stderr,
            )
    if not report_path.is_absolute():
        report_path = repo_root / report_path

    def refuse(msg: str) -> int:
        print(f"emit-wave-fire: REFUSED — {msg}", file=sys.stderr)
        return EXIT_REFUSED

    if plugin_root is None:
        return refuse(
            "no plugin root resolved (not installed and no --plugin-root given). "
            "Pass --plugin-root with the absolute path."
        )

    if live_tree_refusal:
        return refuse(live_tree_refusal)

    if args.repair:
        return _emit_repair(args, repo_root, trail_dir, plugin_root, engine_root, refuse)

    if not report_path.is_file():
        return refuse(f"no frozen gate report at {report_path}")
    if not trail_dir.is_dir():
        return refuse(
            f"trail dir {trail_dir} does not exist. Scaffold it before emitting — the "
            "workflow has no filesystem primitive, so an unscaffolded directory means "
            "every sidecar write lands nowhere and the readiness gate reads an empty trail."
        )

    script_source = plugin_root / "workflows" / "plan-blitz.mjs"
    if not script_source.is_file():
        return refuse(
            f"no plan-blitz.mjs at {script_source} — the plugin root did not resolve. "
            "Pass --plugin-root with the absolute path."
        )

    payload = _gate_payload(report_path)
    waves = payload.get("waves") or []
    if args.wave_index >= len(waves):
        return refuse(
            f"the report has {len(waves)} wave(s); wave {args.wave_index} is not one of them"
        )
    wave_ids = list(waves[args.wave_index])
    if not wave_ids:
        return refuse(f"wave {args.wave_index} is empty — nothing to fire")

    stale = _report_predates_a_landing(trail_dir, wave_number, wave_ids)
    if stale:
        return refuse(stale)

    if args.exclude:
        unmatched = [i for i in args.exclude if i not in wave_ids]
        if unmatched:
            return refuse(
                f"--exclude names {unmatched}, which wave {args.wave_index} does not "
                "contain. An exclusion that matches nothing is a typo, and silently "
                "honouring it emits a fire the caller did not mean to emit."
            )
        wave_ids = [i for i in wave_ids if i not in set(args.exclude)]
        if not wave_ids:
            return refuse(
                f"every baton in wave {args.wave_index} was excluded — nothing to fire"
            )

    collapsed = _shared_wave_slots(payload, wave_ids)
    if collapsed:
        lines = [
            f"wave {args.wave_index} names {len(collapsed)} id(s) that more than one "
            "baton record answers to, so the wave slot holds several candidates and a "
            "fire would plan exactly one of them:"
        ]
        for slot_id, paths in collapsed:
            lines.append(f"  {slot_id}")
            for path in paths:
                lines.append(f"    {path}")
        lines.append(
            "A baton id is legitimately non-unique -- a succession chain and a roadmap "
            "stub's fan-out both share one by design -- so this is not corrupt data and "
            "there is no survivor for this script to pick. Firing regardless plans a "
            "subset and reports as a completed wave, which is the failure this refusal "
            "exists to stop. Settle the group first: hold the stale member, re-mint a "
            "genuinely separate deliverable, or fire the members by name."
        )
        return refuse("\n".join(lines))

    by_id = {b["id"]: b for b in (payload.get("batons") or [])}
    missing = [i for i in wave_ids if i not in by_id]
    if missing:
        return refuse(
            f"wave {args.wave_index} names {len(missing)} baton(s) the report's own "
            f"`batons[]` does not carry: {missing}. The report is internally inconsistent; "
            "re-freeze it rather than emitting a fire that plans a subset."
        )

    held: list[str] = []
    if not args.include_dirty:
        dirty = _live_writer_paths(repo_root, [by_id[i]["path"] for i in wave_ids])
        if dirty is None:
            print(
                "  WARNING: git could not report which baton records are uncommitted; none "
                "were held. A baton a live writer is still minting may be in these fires.",
                file=sys.stderr,
            )
        else:
            held = [i for i in wave_ids if by_id[i]["path"].replace("\\", "/") in dirty]
        if held:
            print(
                f"  HELD {len(held)} baton(s) whose record is uncommitted — a live writer is "
                f"still on them, and the gate cannot see that: {held}. Commit them and "
                "re-emit, or pass --include-dirty if the uncommitted edit is your own.",
                file=sys.stderr,
            )
            wave_ids = [i for i in wave_ids if i not in set(held)]
            if not wave_ids:
                return refuse("every baton in this wave is held behind an uncommitted record")

    # Reported on EVERY emit, not only when it looks wrong: the omitted-identity failure is
    # invisible at emit time AND at fire time, and surfaces only as a wave that dispatched
    # everything, spent its full budget, and landed no plan.
    if plugin_agents:
        print(f"  agent identities: declared ({plugin_agents_why})", file=sys.stderr)
    else:
        print(
            f"  agent identities: OMITTED ({plugin_agents_why}). Every dispatch is stamped "
            "`workflow-subagent`, a non-empty type on no roster, so the write guards confine it: "
            "the planner cannot write its plan body and cannot run plan-spine-check. On a box "
            "carrying the guards this does not thin a wave, it empties it.",
            file=sys.stderr,
        )

    try:
        entries = [_baton_arg(by_id[i]) for i in wave_ids]
    except ValueError as exc:
        return refuse(str(exc))

    # A PLAN THIS TRAIL ALREADY HOLDS IS BOUND, even when the gate report does not link it.
    # `blitz_land` links a plan to its baton only on `ready`, so a PULLED baton — the one whose
    # plan an EM then settles, and the one a repair re-dispositions — comes back from the gate
    # with no `plan`. Re-firing it hands the planner a baton that looks unplanned, and it authors
    # over the settled plan rather than revising it: the planner's revising branch keys on exactly
    # this field. Reported by example-store-repo-fb, standing between a repaired plan and the only
    # vehicle that can approve it. The trail is authoritative here because it is where THIS run's
    # plan for that baton was written.
    adopted = []
    for entry in entries:
        if entry.get("planPath"):
            continue
        slot = _latest_wave_slot(trail_dir, entry["id"])
        found = _plan_path_for(slot, entry["id"]) if slot is not None else None
        if found:
            entry["planPath"] = found
            adopted.append((entry["id"], found))
    # SILENCE HERE HAS TWO MEANINGS AND A DRIVER CANNOT TELL THEM APART. Nothing to adopt (the
    # gate already links every plan) and the trail lookup finding nothing both print no ADOPTED
    # line, so a driver checking the fix worked has to grep `planPath` out of the generated .mjs
    # — a step this skill asks of nobody. Report the census unconditionally.
    linked = sum(1 for e in entries if e.get("planPath")) - len(adopted)
    print(
        f"  plan links: gate report links {linked} of {len(entries)} baton(s); "
        f"adopted {len(adopted)} from this trail",
        file=sys.stderr,
    )
    if adopted:
        print(
            f"  ADOPTED {len(adopted)} plan(s) from this trail that the gate report does not link "
            "— the planner will REVISE these rather than author over them:",
            file=sys.stderr,
        )
        for bid, rel in adopted:
            print(f"      {bid}  {rel}", file=sys.stderr)

    edited = _plans_edited_since(
        repo_root, report_path, [e["planPath"] for e in entries if e.get("planPath")]
    )
    if edited:
        by_plan = {e["planPath"]: e["id"] for e in entries if e.get("planPath")}
        print(
            f"  WARNING: {len(edited)} plan(s) in this wave changed AFTER the gate report was "
            "frozen — if that was an EM settling a pull, this fire's planner will re-author the "
            "plan from the baton and cannot see the settlement, so the second author silently "
            "overwrites the first:",
            file=sys.stderr,
        )
        for rel in edited:
            print(f"      {by_plan.get(rel, '?')}  {rel}", file=sys.stderr)
        print(
            "    Re-freeze the gate and re-emit if the edit changed what the plan is, or fire "
            "knowing the planner starts from the baton.",
            file=sys.stderr,
        )

    # Multi-OS is P0, and the env-prefix rungs above are POSIX-shaped by necessity —
    # `VAR=x cmd` is not a command on a PowerShell host. A Windows box with no install
    # therefore gets an invocation the CLI will reject for a reason nobody sees, since
    # that stderr surfaces inside a dispatched reviewer. Saying so here is the whole
    # mitigation available: this module cannot write a PowerShell literal into a POSIX
    # brief, but it can refuse to be quiet about the gap.
    if os.name != "posix" and not os.environ.get("COORDINATOR_SETTINGS_HOME"):
        print(
            "  WARNING: non-POSIX host with no settings home. The injected CLI literals "
            "carry no environment prefix (`VAR=x cmd` is not a command here), so "
            "`append-integrator-dispositions` may fail CLAUDE_KLABAUTER_ROOT resolution inside a "
            "dispatched agent, where its diagnostic is not read. Resolve the CLIs "
            "explicitly with --dispositions-cli / --provision-sidecar-cli.",
            file=sys.stderr,
        )

    dispositions = args.dispositions_cli or _default_dispositions_cli(
        engine_root, plugin_root
    )
    sidecar_cli = args.provision_sidecar_cli or _default_sidecar_cli(
        engine_root, plugin_root
    )
    spine_check_cli = args.spine_check_cli or _default_spine_check_cli(plugin_root)
    arming_check_cli = _default_arming_check_cli(plugin_root)

    per = max(1, args.batons_per_fire)
    fires = _pack_by_plan(entries, per)
    for batch in fires:
        if len(batch) > per:
            print(
                f"  WARNING: {len(batch)} batons share {batch[0]['planPath']} and are "
                f"emitted as one fire over the {per}-baton cap — split across concurrent "
                "fires they would be two waves authoring one plan file.",
                file=sys.stderr,
            )

    # A narrowed re-emit (`--exclude`, a wave already part-fired) never reuses a fire number that
    # binds a different baton set: positional numbering would give its first fire `fire-N-1`,
    # which the archived first fire already holds. It numbers past the archive, reusing a number
    # only for a fire that binds exactly the same batons, so re-running the emit is idempotent.
    archived_fires: dict[int, frozenset] = {}
    narrowed = bool(args.exclude or held)
    if narrowed:
        for path in trail_dir.glob(f"fire-{wave_number}-*.mjs"):
            suffix = path.stem.rsplit("-", 1)[-1]
            identity = _archived_fire_identity(path) if suffix.isdigit() else None
            if identity is not None:
                archived_fires[int(suffix)] = identity[1]
    next_n = max(archived_fires, default=0) + 1

    engine_ref = _engine_ref(repo_root, script_source)
    manifest = []
    for n, batch in enumerate(fires, start=1):
        if narrowed:
            ids = frozenset(b["id"] for b in batch)
            n = next((k for k, v in archived_fires.items() if v == ids), None) or next_n
            if n == next_n:
                next_n += 1
        wave_args = {
            "repoRoot": str(repo_root),
            "waveIndex": wave_number,
            "trailDir": str(trail_dir),
            "gateReportPath": str(report_path),
            "pluginAgentsAvailable": plugin_agents,
            # The code this fire will actually run, stamped where it is knowable. A fire is a
            # FROZEN COPY of `plan-blitz.mjs` with its args bound in, so a wave fired an hour ago
            # runs the workflow as it stood an hour ago — and nothing in the result said which.
            # On a run where the workflow is itself being repaired, that makes every reconciliation
            # forensic: a driver comparing two waves' behaviour has to recover the mtimes and the
            # commit times by hand to learn whether they ran the same code. Reported by
            # example-store-repo-fb, who proved it twice on this run — `sizingObjectAbsences` absent from
            # four wave results because it shipped minutes after they fired, and a directory
            # pathspec permitted twice then denied.
            "engineRef": engine_ref,
            "batons": batch,
        }
        if dispositions:
            wave_args["dispositionsCli"] = dispositions
        if sidecar_cli:
            wave_args["provisionSidecarCli"] = sidecar_cli
        if spine_check_cli:
            wave_args["spineCheckCli"] = spine_check_cli
        if arming_check_cli:
            wave_args["armingCheckCli"] = arming_check_cli
        try:
            text = _bind(script_source, wave_args, args.live_engine_tree)
        except ValueError as exc:
            return refuse(str(exc))

        out = trail_dir / f"fire-{wave_number}-{n}.mjs"
        # An emitted script is on disk SO THAT the fire can be re-read, re-fired and
        # diffed, and so it archives with the trail. Silently overwriting one destroys
        # exactly that. The collision is not hypothetical: `roadmap.plan_gate` numbers
        # `waves` from the READ, so every wave of a run comes back as `waves[0]`, and a
        # driver that emits the run's second wave into the same trail clobbers the
        # first's scripts while the trail SLOTS — keyed by baton set — stay correctly
        # separate. Nothing else notices, because the fire that mattered already ran.
        archived = _archived_fire_identity(out) if out.is_file() else None
        if archived is not None:
            archived_index, archived_ids = archived
            fresh_ids = frozenset(b["id"] for b in batch)
            # Two emits are the SAME fire when they cover the same wave and the same
            # batons. A NARROWING re-emit is also legitimate and is the documented
            # `--exclude` flow: a wave already part-fired, re-emitted over the batons
            # still to go. Only a fire covering batons the archived one did not is a
            # genuine collision — that is the one that would destroy a record of work.
            same_wave = archived_index in (None, wave_number)
            if not (same_wave and fresh_ids <= archived_ids):
                return refuse(
                    f"{out.name} already exists in this trail and binds a DIFFERENT fire "
                    f"— it covers {sorted(archived_ids)}, this one covers "
                    f"{sorted(fresh_ids)}. Emitting over it would destroy the archived "
                    "fire, which is the reason these are written to disk at all. "
                    "`roadmap.plan_gate` numbers waves from the read, so a run's second "
                    "wave also arrives as wave 0: pass --wave-number matching this run's "
                    "own wave count, or --trail-dir a fresh directory for this wave."
                )
        # LF on every host: Windows newline translation writes a CR per line, and the harness
        # refuses a Workflow script carrying control characters its approval dialog would hide.
        out.write_text(text, encoding="utf-8", newline="\n")
        manifest.append(
            {"fire": n, "scriptPath": str(out), "batons": [b["id"] for b in batch]}
        )

    if args.json:
        print(json.dumps({"waveIndex": wave_number, "fires": manifest, "held": held}, indent=2))
        return EXIT_OK

    print(
        f"emit-wave-fire: wave {wave_number} — {len(entries)} baton(s) across "
        f"{len(fires)} fire(s), at most {per} per fire."
    )
    if not dispositions:
        print(
            "  WARNING: no append-integrator-dispositions resolved. The integrator brief "
            "will say the caller omitted it; dispositions for this wave go unrecorded.",
            file=sys.stderr,
        )
    if not sidecar_cli:
        print(
            "  WARNING: no provision-sidecar resolved. Every reviewer will place its own "
            "findings sidecar by guessing the machinery root and its session id, and the "
            "guess does not error — the findings land where the repo does not keep them.",
            file=sys.stderr,
        )
    provenance = _trail_provenance(trail_dir, engine_ref)
    if provenance:
        print(
            "  THIS TRAIL'S FIRES WERE BUILT FROM MORE THAN ONE WORKFLOW. A fire is a standalone "
            "COPY of plan-blitz.mjs, so each runs the workflow as it stood when it was emitted:",
            file=sys.stderr,
        )
        for line in provenance:
            print(line, file=sys.stderr)
        print(
            "  Not a refusal and not a re-emit instruction — an older fire is sometimes exactly "
            "right, and the current file moves under you, so it is no baseline either. To learn "
            "what a fire CARRIES, grep the fire.",
            file=sys.stderr,
        )
    for row in manifest:
        print(f"\n  fire {row['fire']}: {', '.join(row['batons'])}")
        print(f'    Workflow({{ scriptPath: "{row["scriptPath"]}" }})   # no args — they are bound')
    print(
        "\nFire every one of them at this waveIndex before landing. `blitz_land` takes ONE "
        "fire's result, so sum the three lanes across all fires before reading the "
        "stop condition."
    )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
