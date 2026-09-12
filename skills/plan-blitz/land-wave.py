#!/usr/bin/env python3
"""land-wave — land every fire of one plan-blitz wave, and read the stop condition once.

WHY THIS EXISTS. `roadmap.blitz_land` takes ONE fire's result. A wave over the per-fire
cap is drained by several fires sharing one `waveIndex`, so the landing an EM is holding
is a FRACTION of the wave — and the skill's stop condition ("a wave that lands zero
approved AND zero execution_ready AND zero closed") is a WAVE-level test. Reading it off
one fire is how a healthy blitz gets reported as a stall: measured on this repo, one fire
of five landed nothing at all while the wave around it had opened nine.

The arithmetic that separates those two readings is a sum across fires. Doing it by hand,
once per wave, after reading N landing replies, is the step this module removes. It lands
each fire in order, accumulates the three lanes, and states the stop condition from the
SUM — never from the last reply it happened to read.

It also removes the second retype at this seam. The wave result is the workflow's own
returned object, and passing it to the op means copying a large JSON literal out of a
tool result. This reads it from disk instead — either the raw result or the harness's
task-output envelope, whichever the caller points at.

WHAT IT DOES NOT DECIDE. Nothing. The verdicts were the EM's, made at the readiness gate;
the op executes them. This module orders the calls and sums the lanes. It does not fire
the next wave — that stays one explicit call away, which is what keeps a runaway loop
impossible — and it does not re-queue anything the wave surfaced to the PM.

REFUSALS, all before any landing is attempted:

  - a wave whose fires disagree about `waveIndex`. Two fires at different indices are two
    waves, and summing their lanes answers a question about neither.
  - a result carrying a completed `dispatched` entry with no `--shipped-in`, unless every
    such entry reports the `priorShippedIn` its work already shipped in (a confirm-and-close).
    The op would refuse those batons one at a time and the wave would read as
    landed-with-refusals; refusing up front names the actual missing input, which is a
    commit that has not been made. The op validates each prior itself.
  - a file that is neither a wave result nor a task-output envelope carrying one.

Usage:

    python3 land-wave.py --repo-root <abs> [--shipped-in <sha>] [--branch <name>]
                         <fire-result.json> [<fire-result.json> ...]

Exit 0 when every fire landed and the wave advanced, 1 when the wave advanced nothing
(the stop condition — report and stop), 2 on a refusal, 3 when any landing returned a
non-empty `refused[]`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_WAVE_OPENED_NOTHING = 1
EXIT_REFUSED = 2
EXIT_LANDING_REFUSALS = 3

#: The three lanes whose SUM decides whether the wave advanced. `approved` alone is not
#: the test: an all-S wave approves nothing by construction and still advances, because
#: `blitz_land` parks each S execution-ready and `needs_plan` keys off that stamp.
_LANES = ("approved", "execution_ready", "closed")


def _wave_result(path: Path) -> dict:
    """The workflow's returned object, from either shape a caller has on disk.

    A Workflow's return value reaches the caller two ways: inside the harness's
    task-output envelope (`{summary, agentCount, result, workflowProgress}`), and as the
    bare object once someone has pulled it out. Accepting only the bare one makes the
    common case — pointing at the task output file the notification named — fail as
    "not a wave result", which reads as a broken run rather than a wrapped file.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: not a JSON object")
    if "waveIndex" not in data and isinstance(data.get("result"), dict):
        data = data["result"]
    if "waveIndex" not in data:
        raise ValueError(
            f"{path}: carries no `waveIndex`, so it is neither a plan-blitz wave result "
            "nor a task-output envelope wrapping one."
        )
    return data


def _rejected_prior_lines(reply: dict) -> list[str]:
    """Closed batons whose own prior SHA did not verify and were stamped with the landing's.

    `close_dispatched` takes `prior or shipped_in or ""`, so a prior that verifies correctly wins.
    One that does NOT verify falls back to the landing's SHA whenever `--shipped-in` was passed —
    stamping the baton with a commit its work did not ship in. That is the wrong-SHA outcome the
    caller-side restore exists to prevent, arriving by the one path the restore cannot reach, and
    the engine records it only as a key on the closed row where no printed summary shows it.
    """
    return [
        f"  PRIOR SHA REJECTED  {row.get('baton') or row.get('batonId')}: "
        f"{row['prior_shipped_in_rejected']} — this baton is stamped with the LANDING's SHA, "
        "not the commit its work shipped in."
        for row in (reply.get("closed") or [])
        if isinstance(row, dict) and row.get("prior_shipped_in_rejected")
    ]


def _fallback_lines(reply: dict) -> list[str]:
    """Approved rows the engine landed by the plan route because the S lane refused the kind.

    The row is a real approval and counts as one, but the gate said "execute straight off the
    spec" and the landing delivered "approved, go through /execute-plan". The engine names that
    on the row; a count cannot, so a kind the resolved engine does not yet admit — a mirror
    lagging its source, not a kind refused by design — would otherwise read as ordinary approval.
    """
    return [
        f"{row.get('baton') or row.get('batonId') or '(unnamed)'}: fell back from "
        f"{row['fell_back_from']} — {row.get('fallback_reason') or 'no reason given'}"
        for row in (reply.get("approved") or [])
        if isinstance(row, dict) and row.get("fell_back_from")
    ]


def _stamped_nothing(lane: str, row) -> bool:
    """The approved lane reports its write as `stamped`; the other two carry the lane's own name.

    Reading only the lane-named flag counted every `approved` row as a write, so a re-landed wave
    whose plans were all `already at status: approved` reported the same totals as a fresh one.
    """
    return isinstance(row, dict) and (row.get(lane) is False or row.get("stamped") is False)


def _lane_refusals(reply: dict) -> list[str]:
    """Rows a lane RETURNED while its own per-row flag says nothing was stamped.

    `blitz_land` catches the stamp's `MutateAbort` and converts it to a return value
    (`{execution_ready: False, note: ...}`), then appends the row to the lane list
    unconditionally — so the lane's length counts a refusal as a success and `refused[]`
    stays empty. Measured by example-game-workbench-repo-b8 on its wave 1 (landing `2014cd58f`,
    reported `execution_ready: 2`, neither baton stamped), then on this repo's own
    20260911T145644Z landing: 18 of 22, every one a `kind: spinoff` baton, which
    `_EXECUTION_PHASE_KINDS` does not admit.

    A baton that reads as parked and is not comes back as a planning candidate, and the
    next wave re-plans work that already has an approved spec. So these rows join
    `refused[]`, where the skill's standing "read `refused[]` on every landing" rule
    already looks.
    """
    lines = []
    for lane in _LANES:
        for row in reply.get(lane) or []:
            if not _stamped_nothing(lane, row):
                continue
            baton = row.get("baton") or row.get("batonId") or "(unnamed)"
            note = row.get("note") or "the op stamped nothing and said no more"
            lines.append(f"{baton}: {lane} returned FALSE — {note}")
            lines.extend(_executor_prestamp_diagnosis(lane, baton, note))
    return lines


def _executor_prestamp_diagnosis(lane: str, baton: str, note: str) -> list[str]:
    """Name the one cause a terminal-state refusal on the XS lane almost always has.

    The dispatch lane closes a baton the wave's own XS executor just worked on, so the only
    party that can have made it terminal first is that executor — and the brief forbidding it
    (`workflows/plan-blitz.mjs` § Never stamp the baton's lifecycle frontmatter) has been read
    past in a live run, with the wave's own readiness note observing the write and passing it
    as schema-legal. The refusal that follows reads as a conflict to adjudicate, when what it
    actually reports is a DIFFERENT terminal than the one the close was going to write:
    `closed` + a `closed_reason` against `shipped` + the wave's `shipped_in` SHA. The executor's
    terminal keeps no link to the commit carrying the work, which is the whole content of the
    stamp it pre-empted — so "it ended up where it was going anyway" is the reading to refuse.
    """
    if lane != "closed" or "terminal" not in note.lower():
        return []
    return [
        f"  ^ {baton}: the XS executor almost certainly stamped lifecycle frontmatter itself "
        "(deployment_state/closed_reason), which the landing owns. Read the baton: if it is "
        "closed rather than shipped, it carries no shipped_in and nothing links it to the "
        "commit holding its work.",
    ]


def _restore_prior_shipped_in(result: dict) -> list[str]:
    """Put `priorShippedIn` back on a ready row that a wave built without it.

    `blitz_land` reads the field off the READY row. The wave has two paths to such a row for a
    dispatched XS — a synthetic one for the batons its gate did not judge, which carries the
    field, and the gate's own verdict for the ones it did, which did not. So a confirm-and-close
    whose work shipped months ago was refused for want of a SHA it was carrying two keys away, in
    the same result.

    Measured on fire-0-14 of this run: three batons, three distinct prior commits, all three
    refused. The workflow is fixed, but every fire already emitted is a FROZEN COPY of the old one
    and cannot be, so the repair belongs here too — and here it is also strictly better, because
    the alternative a driver reaches for is `--shipped-in` with one SHA, which stamps three batons
    that shipped in three different commits with a single wrong one.

    Copies, never invents: the value comes from this same result's own `dispatched` entry, and
    only where that entry completed. It is the transform the wave now performs, applied to a
    result written before it did.
    """
    by_id = {
        d["batonId"]: d
        for d in (result.get("dispatched") or [])
        if isinstance(d, dict) and d.get("batonId")
    }
    restored = []
    for row in result.get("ready") or []:
        if not isinstance(row, dict) or row.get("priorShippedIn"):
            continue
        entry = by_id.get(row.get("batonId"))
        if entry and entry.get("completed") and entry.get("priorShippedIn"):
            row["priorShippedIn"] = entry["priorShippedIn"]
            restored.append(f"{row['batonId']} -> {entry['priorShippedIn'][:9]}")
    if not restored:
        return []
    return [
        "land-wave: restored priorShippedIn from the result's own dispatched rows for: "
        + ", ".join(restored),
        "  These came from this result, not from an assumption. Without them the landing refuses "
        "each baton for want of a SHA it was already carrying.",
    ]


def _missing_integration_records(result: dict) -> list[str]:
    """Ready plan-route batons whose integration left no record in the trail slot.

    THE WAVE CANNOT CHECK THIS AND THIS SCRIPT CAN. A workflow script has no filesystem
    primitive, so the integrator's `reportPath` reaches the wave as a CLAIM; the wave's own
    `ready`-to-`pulled` reconciliation therefore keys on whether the integrator RETURNED, which is
    the only integration fact it can observe. That correctly leaves one case uncovered: the pass
    ran, returned, edited the plan — and its sidecar never landed.

    Measured 2026-09-11 on this run's fire-0-14. `hnd-single-surface-hook-cutover-th-a7d688`
    gated READY with no `*.review-integration.md` anywhere in the trail, while the plan itself
    carries the integrator's `<!-- Review: ... -->` annotations at the lines the gate cited. So the
    work happened and the record did not, and an earlier fire of the same run PULLED on an absence
    that looked identical. What is lost is not the edit but the account of it: which findings were
    applied, which declined, and on what reasoning — the thing a later reader has no other source
    for.

    WARNS, never refuses. The plan is on disk and landing it is right; a refusal here would hold
    good work over a missing file that re-running nothing can restore.
    """
    slot = result.get("trailSlotDir")
    if not slot:
        return []
    slot_path = Path(str(slot))
    if not slot_path.is_dir():
        return []
    # MATCHED ON A NORMALISED STEM, never on an exact path. A baton id is `hnd-` + a slug
    # truncated to a fixed width + `-` + a hash, so a slug truncated ON a hyphen yields a DOUBLED
    # dash — and the sidecar writer collapses it while the id keeps it. Reported by
    # example-store-repo-fb on this check's first real use: `hnd-corpus-knowledge-delivery-raw--b8256d`
    # warned as missing while `hnd-corpus-knowledge-delivery-raw-b8256d.review-integration.md` sat
    # in the directory the check had just read. Not rare and not random — it is a property of the
    # title, so it recurs forever on the same batons.
    #
    # This check exists to say a record is absent. A lookup that reports its own path arithmetic as
    # an absence is the exact defect it was written to catch, one layer up:
    # `A-DIAGNOSTIC-THAT-NAMES-A-CAUSE-IT-DID-NOT-OBSERVE`.
    def _stem(name: str) -> str:
        return re.sub(r"-+", "-", name).strip("-").lower()

    present = {
        _stem(p.name[: -len(".review-integration.md")]): p.name
        for p in slot_path.glob("*.review-integration.md")
    }
    missing = [
        str(v["batonId"])
        for v in (result.get("ready") or [])
        if isinstance(v, dict)
        and v.get("route") in ("plan", "spec-dispatch")
        and v.get("batonId")
        and _stem(str(v["batonId"])) not in present
    ]
    if not missing:
        return []
    return [
        "land-wave: NO INTEGRATION RECORD in the trail slot for: " + ", ".join(missing),
        "  The plans are landing anyway and that is correct — the integrator's edits are in the "
        "plan bodies. What is missing is the ACCOUNT: which findings it applied, which it "
        "declined, and why. The integrator's return value still holds it: the fire's "
        "journal.jsonl (the completion notification names it) carries one `result` line per "
        "`integrate:<baton>` agent. Write the record from that, marked as reconstructed, before "
        "the session that fired the wave ends — the journal does not outlive it.",
        f"  Slot: {slot_path}",
        # The evidence, not just the conclusion. fb caught this check's own false positive ONLY
        # because it printed the slot and the listing was one command away; naming what WAS found
        # makes the near-miss visible without that second step.
        "  Records found there: " + (", ".join(sorted(present.values())) or "(none)"),
    ]


def _archive_result(result: dict) -> Path | None:
    """Persist a fire's own returned object into that fire's trail slot.

    WHY. The trail archives what was FIRED — the emitted `.mjs` carries its bound
    args — and, until this, nothing archived what a fire RETURNED. A wave's
    verdicts therefore existed only inside a tool call, and that is not a
    cosmetic gap: `roadmap.blitz_land` takes the wave result verbatim, so a
    landing cannot be re-run once the session holding it ends. Measured on
    claude-klabauter, run 20260910T000000Z: two XS batons finished, their landing
    never stamped them, `recycle-check.py` correctly named them RECYCLED — and
    the documented repair ("re-run the landing with the SHA") was unreachable,
    because the trail held hand-written baton arrays and no fire result. The
    verdicts had to be reconstructed from the execution records instead.

    Written to `trailSlotDir` rather than `trailDir`: the slot is this fire's own
    leaf, so several fires of one wave cannot overwrite each other's result —
    the same keying the wave-scoped sidecars already use. Best-effort by
    design: this is a durability improvement to the trail, and a landing that
    otherwise succeeds must not be refused because the trail was unwritable.
    """
    slot = result.get("trailSlotDir") or result.get("trailDir")
    if not slot:
        return None
    target = Path(slot)
    try:
        target.mkdir(parents=True, exist_ok=True)
        out = target / "wave-result.json"
        out.write_text(json.dumps(result, indent=1), encoding="utf-8")
        return out
    except OSError as exc:
        print(f"land-wave: could not archive the fire result under {target}: {exc}",
              file=sys.stderr)
        return None


def _invoke_argv(engine_root: Path | None, live_engine_tree: bool) -> tuple[list[str], list[str], dict]:
    """The command, trailing flags and environment that dispatch an op — and against WHICH code.

    Under `--live-engine-tree` the answer is the named tree's own trampoline, run COLD. The
    engine's `--allow-unstamped-dispatch` alone still takes the warm path, and a warm server
    booted from an unstamped tree never retires on a code change — it cannot trip the superseded
    check, so it serves whatever it loaded at boot until it idles out. This flag exists to reach
    an engine fix that is not published yet, and on a state-mutating op the warm path can serve
    the tree from before that fix with nothing saying so. Measured on a re-land: it refused a
    baton the authoring tree's HEAD lands, because the serving code predated the fix by one
    commit. `COORDINATOR_WARM=0` is the engine's own per-invocation escape hatch, and the flag is
    its sanctioned CLI opt-out — so neither is a new way past the stamp gate.
    """
    env = dict(os.environ)
    if live_engine_tree and engine_root is not None:
        env["COORDINATOR_ENGINE_ROOT"] = str(engine_root)
        env["COORDINATOR_WARM"] = "0"
        return (
            [sys.executable, str(engine_root / "coordinator" / "bin" / "coordinator-invoke.py")],
            ["--allow-unstamped-dispatch"],
            env,
        )
    settings_home = os.environ.get("COORDINATOR_SETTINGS_HOME") or str(
        Path(os.environ.get("CLAUDE_HOME") or Path.home()) / ".coordinator-claude-settings"
    )
    bin_dir = Path(settings_home) / "bin"
    # The Windows launcher is `coordinator-invoke.exe`; the bare name beside it is a POSIX script.
    launcher = next(
        (bin_dir / n for n in ("coordinator-invoke.exe", "coordinator-invoke") if (bin_dir / n).is_file()),
        bin_dir / "coordinator-invoke",
    )
    if launcher.is_file():
        cmd = [str(launcher)]
    elif engine_root is not None:
        cmd = [sys.executable, str(engine_root / "coordinator" / "bin" / "coordinator-invoke.py")]
    else:
        raise ValueError(
            f"no coordinator-invoke launcher at {launcher}, and no --engine-root or "
            "$COORDINATOR_ENGINE_ROOT to fall back to."
        )
    if engine_root is not None:
        env.setdefault("COORDINATOR_ENGINE_ROOT", str(engine_root))
    return cmd, [], env


def _invoke(repo_root: Path, engine_root: Path | None, op: str, params: dict,
            live_engine_tree: bool = False) -> dict:
    cmd, tail, env = _invoke_argv(engine_root, live_engine_tree)
    proc = subprocess.run(
        cmd + [op, json.dumps(params)] + tail,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(repo_root),
        timeout=600,
    )
    # A JSON-RPC refusal still exits non-zero, and the engine writes its `[warm-settings]`
    # line to stderr. Preferring stderr on a non-zero exit therefore reports the chatter as
    # the failure and DISCARDS the refusal — and `roadmap.blitz_land`'s refusals are the
    # ones that must never be routed around. Parse stdout first.
    # `A-PUBLISHED-MIRROR-OLDER-THAN-AN-OP-REFUSES-AS-A-MISSING-ENGINE`.
    try:
        reply = json.loads(proc.stdout)
    except json.JSONDecodeError:
        reply = None
    if not isinstance(reply, dict):
        raise ValueError(
            f"{op} failed (exit {proc.returncode}): {(proc.stderr or proc.stdout).strip()[:800]}"
        )
    if "error" in reply:
        err = reply["error"]
        message = str((err or {}).get("message") or err) if isinstance(err, dict) else str(err)
        raise ValueError(f"{op} refused: {message}")
    # Stdout-first does NOT mean exit-code-blind. A well-formed reply carrying no `error`
    # alongside a non-zero exit is the engine failing in a way its envelope did not
    # describe, and returning `result` there reports that failure as success — the exact
    # inversion of the defect this parse order was introduced to fix.
    if proc.returncode != 0:
        raise ValueError(
            f"{op} exited {proc.returncode} while returning a result envelope with no "
            f"`error`. Treating that as success would report a failure as a landing. "
            f"stderr: {(proc.stderr or '').strip()[:800]}"
        )
    if "result" not in reply:
        raise ValueError(f"{op} returned a reply carrying neither `result` nor `error`")
    return reply["result"]



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


_LANDING_ROOTS = ("state/handoffs/", "archive/handoffs/", "state/roadmap/", "docs/plans/")


def _repo_relative(value: str, repo_root: Path) -> str | None:
    """`value` as a forward-slash repo-relative path, or None when it names nothing here.

    Trail records have been measured writing `planPath` in two shapes — absolute on some entries,
    repo-relative on others — so both are normalised rather than trusting either.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    p = Path(value.strip())
    if p.is_absolute():
        try:
            p = p.resolve().relative_to(repo_root)
        except ValueError:
            return None
    return p.as_posix()


#: Reply keys that describe the NEXT wave, not this one. A next-wave baton's plan or handoff can be
#: dirty for any reason — a peer's edit, an earlier run's uncommitted body — and none of it is a
#: record this wave wrote.
_NOT_THIS_WAVE = frozenset({"next_wave"})


def _strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for k, v in node.items():
            if k not in _NOT_THIS_WAVE:
                yield from _strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from _strings(v)


def _landing_pathspec(fires: list, replies: list, repo_root: Path) -> list[str]:
    """Every path this wave's OWN records name that is now uncommitted.

    `roadmap.blitz_land` does not commit, by its own negative spec, and this helper used to say
    nothing about what the caller then owes. Measured 2026-09-11, twice on one run: one fire's
    landing stamps and another's integrated plan rewrites were never committed, because the
    landing commit named what the landing stamped and missed what the FIRE wrote. The next emit
    then HELD three batons as "uncommitted record — a live writer is still on them", against the
    driver's own work.

    Candidates come only from this wave's records — each fire's trail slot, every `planPath` its
    lanes cite, and every handoff/roadmap/plan path in the landing replies — and are then
    intersected with `git status`. Never a directory sweep: a shared tree carries peer sessions,
    and a pathspec that sweeps `state/handoffs/` commits their work under this wave's name.
    """
    return _dirty_among(_landing_candidates(fires, replies, repo_root), repo_root)


def _landing_candidates(fires: list, replies: list, repo_root: Path) -> set[str]:
    """The paths this wave's own records name, dirty or not. Pure: reads the trail root's
    listing and nothing else, so it is tested without a repository."""
    candidates: set[str] = set()
    for _, result in fires:
        slot = _repo_relative(result.get("trailSlotDir") or "", repo_root)
        if slot:
            candidates.add(slot)
        # The trail ROOT's own files too — the fire script, the frozen gate report, the landing
        # declaration this helper writes. Files only, never the root's other slots: a sibling fire
        # of this run may still be airborne, and committing its partial records would clear the
        # dirty-record HOLD that keeps the next emit off its batons.
        trail = _repo_relative(result.get("trailDir") or "", repo_root)
        if trail and (repo_root / trail).is_dir():
            candidates.update(
                f"{trail}/{child.name}" for child in (repo_root / trail).iterdir() if child.is_file()
            )
        for lane in ("ready", "pulled", "replan"):
            for entry in result.get(lane) or []:
                if isinstance(entry, dict):
                    rel = _repo_relative(entry.get("planPath") or "", repo_root)
                    if rel:
                        candidates.add(rel)
    for reply in replies:
        for s in _strings(reply):
            rel = _repo_relative(s, repo_root)
            if rel and rel.startswith(_LANDING_ROOTS) and rel.endswith((".md", ".yaml")):
                candidates.add(rel)
    return candidates


def _dirty_among(candidates: set[str], repo_root: Path, run=subprocess.run) -> list[str]:
    """`candidates` intersected with `git status`, renames resolved to their destination. `run`
    is injectable so the porcelain parse is tested without spawning git."""
    if not candidates:
        return []
    try:
        out = run(
            ["git", "status", "--porcelain", "--untracked-files=all", "--", *sorted(candidates)],
            cwd=str(repo_root), capture_output=True, text=True, encoding="utf-8", check=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return []
    dirty = []
    for line in out.splitlines():
        path = line[3:].strip().strip('"')
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if path:
            dirty.append(path)
    return sorted(set(dirty))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="land-wave",
        description="Land every fire of one plan-blitz wave and read the stop condition once.",
    )
    ap.add_argument("results", nargs="+", help="one wave-result (or task-output) JSON per fire")
    ap.add_argument("--repo-root", required=True, help="ABSOLUTE repo root")
    ap.add_argument("--engine-root", help="engine checkout (default: $COORDINATOR_ENGINE_ROOT)")
    ap.add_argument(
        "--shipped-in",
        help="SHA of the commit carrying this wave's XS work. Required when any fire "
        "dispatched — closing a dispatched baton stamps `shipped` against it, and the "
        "landing op does not commit.",
    )
    ap.add_argument(
        "--live-engine-tree",
        action="store_true",
        help=(
            "the --engine-root given is claude-klabauter's live authoring tree, which "
            "carries no build stamp. Takes the engine's own live-tree path (the PM's "
            "manual test-and-execute carve-out) for this landing's ops. Its case is a "
            "box whose published mirror predates a fix the landing depends on — the "
            "same rung `emit-wave-fire --live-engine-tree` takes for the bind call."
        ),
    )
    ap.add_argument("--branch", default="main", help="branch recorded on any minted replan baton")
    ap.add_argument("--limit", type=int, default=8, help="max batons in the emitted next wave")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    def refuse(msg: str) -> int:
        print(f"land-wave: REFUSED — {msg}", file=sys.stderr)
        return EXIT_REFUSED

    repo_root = Path(args.repo_root).resolve()
    _er = args.engine_root or os.environ.get("COORDINATOR_ENGINE_ROOT") or ""
    engine_root = Path(_er).resolve() if _er.strip() else None

    live_tree_refusal = _refuse_live_tree_on_a_stamped_engine(
        engine_root, args.live_engine_tree
    )
    if live_tree_refusal:
        print(f"land-wave: REFUSED — {live_tree_refusal}", file=sys.stderr)
        return EXIT_REFUSED
    if args.live_engine_tree:
        # `roadmap.blitz_land` MUTATES state — it links plans, stamps `approved` and
        # `shipped`, mints replan batons. The engine's own help for the flag this
        # forwards says live ops must never pass it, so the one honest mitigation is to
        # say out loud what was disarmed and against which tree.
        print(
            f"land-wave: --live-engine-tree — landing through UNSTAMPED {engine_root}. "
            "This disarms the build-stamp gate AND the cold-fallback refusal, for a "
            "state-mutating op. Use it only to reach an engine fix that is not published "
            "yet.",
            file=sys.stderr,
        )

    fires = []
    for raw in args.results:
        p = Path(raw)
        if not p.is_absolute():
            p = repo_root / p
        if not p.is_file():
            return refuse(f"no wave result at {p}")
        try:
            fires.append((p, _wave_result(p)))
        except ValueError as exc:
            return refuse(str(exc))

    indices = {r.get("waveIndex") for _, r in fires}
    if len(indices) != 1:
        return refuse(
            f"the fires name {sorted(indices, key=str)} as their waveIndex. Two fires at "
            "different indices are two waves, and summing their lanes answers a question "
            "about neither. Land each wave separately."
        )
    wave_index = indices.pop()

    # `completed: true` is the discriminator, not the presence of a `dispatched` entry.
    # A wave records every XS it dispatched, including the ones that declined: a baton
    # whose wait-gate was still shut reports `completed: false`, touches no file, and is
    # routed to `pulled` rather than closed — there is no commit for it to cite, and
    # demanding one refuses a wave that has nothing to ship. Measured wave 0 here: one
    # dispatched baton, zero files changed, correctly declined.
    # A confirm-and-close whose work shipped long ago reports that commit as `priorShippedIn`,
    # and `blitz_land` stamps it in place of the landing's SHA. Only a completed entry WITHOUT
    # one needs a landing commit to cite.
    dispatching = [
        str(p)
        for p, r in fires
        if any(
            e.get("completed") and not e.get("priorShippedIn")
            for e in (r.get("dispatched") or [])
            if isinstance(e, dict)
        )
    ]
    if dispatching and not args.shipped_in:
        return refuse(
            "these fires dispatched XS work and no --shipped-in was given: "
            + ", ".join(dispatching)
            + ". Commit the wave's XS work first and pass that SHA. Without it the XS lane "
            "refuses and those batons stay open, which is the recycling defect, not a "
            "cosmetic gap."
        )

    totals = {lane: 0 for lane in _LANES}
    landings, all_refused, all_surfaced, all_fell_back = [], [], [], []
    next_wave = None

    for path, result in fires:
        for line in _restore_prior_shipped_in(result):
            print(line, file=sys.stderr)
        for line in _missing_integration_records(result):
            print(line, file=sys.stderr)
        archived = _archive_result(result)
        if archived:
            # stderr, not stdout: `--json` promises a parseable stdout, and a real wave
            # result always carries `trailSlotDir`, so a stdout notice here would prefix
            # every `--json` run with a non-JSON line.
            print(f"land-wave: archived {path.name} -> {archived}", file=sys.stderr)
        params = {"wave_result": result, "branch": args.branch, "limit": args.limit}
        if args.shipped_in:
            params["shipped_in"] = args.shipped_in
        try:
            reply = _invoke(
                repo_root, engine_root, "roadmap.blitz_land", params,
                args.live_engine_tree,
            )
        except ValueError as exc:
            return refuse(f"{path.name}: {exc}")

        # `approved`, `execution_ready` and `closed` are the op's own reply keys, one
        # per lane of the skill's landing table. They are read separately and never
        # collapsed: an approval opens a dependent's PLANNING gate, an execution stamp
        # hands the baton to /execute-plan, and a terminal stamp opens the EXECUTION
        # gate too. Collapsing them is what makes an all-S wave read as a stall.
        # A row whose own per-lane flag is False stamped nothing (see `_lane_refusals`), so it
        # is not counted as one — a total that includes it reports a wave as advancing on
        # batons that will return as candidates.
        counted = {
            lane: sum(
                1
                for row in (reply.get(lane) or [])
                if not _stamped_nothing(lane, row)
            )
            for lane in _LANES
        }
        for lane, n in counted.items():
            totals[lane] += n

        # A REJECTED prior is stamped with the landing's SHA and reported only as a key on the
        # closed row. `close_dispatched` takes `prior or shipped_in or ""`, so where the prior
        # verifies it correctly wins — but where it does NOT verify, and the landing happens to
        # carry a `--shipped-in`, the baton is silently stamped with the landing commit instead.
        # That is the wrong-SHA outcome the caller-side restore exists to avoid, arriving by the
        # one path the restore cannot prevent, and nothing in the printed summary says so.
        for line in _rejected_prior_lines(reply):
            print(line, file=sys.stderr)
        all_refused.extend(reply.get("refused") or [])
        all_refused.extend(_lane_refusals(reply))
        all_surfaced.extend(reply.get("surfaced_to_pm") or [])
        all_fell_back.extend(_fallback_lines(reply))
        # Each landing recomputes `next_wave` from a FRESH gate read taken after its
        # own writes, so the last fire's is the only current one — an earlier fire's
        # was computed before the later fires had landed anything.
        next_wave = reply.get("next_wave") or next_wave
        landings.append(
            {"fire": path.name, "counted": counted, "reply": reply,
             "trailDir": result.get("trailDir") or ""}
        )

    advanced = sum(totals.values())
    uncommitted = _landing_pathspec(fires, [l["reply"] for l in landings], repo_root)
    # The declaration written just below is dirty by construction, and the scan above ran before
    # it existed — so it is named here rather than left for the next landing to find.
    for trail in {Path(l["trailDir"]) for l in landings if l["trailDir"]}:
        rel = _repo_relative(str(trail / f"wave-{wave_index}.landing.json"), repo_root)
        if rel and trail.is_dir() and rel not in uncommitted:
            uncommitted = sorted([*uncommitted, rel])

    # The landing's own record, in the trail, BEFORE anything is printed. Without it the only
    # account of what a wave landed is stdout — which the next session does not have — and the
    # driver that must subtract pulled and surfaced batons from a fresh gate read has to
    # reconstruct them from prose across several trail dirs. Measured on project-rag: four trails
    # carrying no landing result at all. Written per wave, so several fires landed in one call
    # produce one file, and a second landing of the same wave supersedes it by design.
    summary = {
        "waveIndex": wave_index,
        "totals": totals,
        "advanced": advanced,
        "refused": all_refused,
        "surfacedToPm": all_surfaced,
        "fellBack": all_fell_back,
        "nextWave": next_wave,
        "landings": [{"fire": l["fire"], "counted": l["counted"]} for l in landings],
        "uncommitted": uncommitted,
    }
    for trail in {Path(l["trailDir"]) for l in landings if l["trailDir"]}:
        if trail.is_dir():
            try:
                (trail / f"wave-{wave_index}.landing.json").write_text(
                    json.dumps(summary, indent=2), encoding="utf-8", newline="\n"
                )
            except OSError as exc:
                # Never fatal: the landing already wrote to disk through the engine, and losing
                # the summary must not read as a landing that failed.
                print(f"land-wave: could not write the landing summary under {trail}: {exc}",
                      file=sys.stderr)

    if args.json:
        print(
            json.dumps(
                {
                    "waveIndex": wave_index,
                    "totals": totals,
                    "advanced": advanced,
                    "refused": all_refused,
                    "surfacedToPm": all_surfaced,
                    "fellBack": all_fell_back,
                    "nextWave": next_wave,
                    "landings": [
                        {"fire": l["fire"], "counted": l["counted"]} for l in landings
                    ],
                    "uncommitted": uncommitted,
                },
                indent=2,
            )
        )
    else:
        print(f"land-wave: wave {wave_index} — {len(fires)} fire(s) landed")
        for l in landings:
            c = l["counted"]
            print(
                f"  fire {l['fire']}: approved {c['approved']}, "
                f"execution_ready {c['execution_ready']}, closed {c['closed']}"
            )
        print(
            f"  WAVE TOTAL: approved {totals['approved']}, "
            f"execution_ready {totals['execution_ready']}, closed {totals['closed']}"
        )
        for entry in all_refused:
            print(f"  refused  {entry}")
        for entry in all_surfaced:
            print(f"  pm       {entry}")
        for entry in all_fell_back:
            print(f"  fellback {entry}")
        if next_wave:
            print(f"  next     wave {next_wave.get('waveIndex')}: "
                  f"{len(next_wave.get('batons') or [])} baton(s)")

    if uncommitted and not args.json:
        # Printed before either STOP: a refused or opened-nothing landing can still have
        # written records, and what the fire wrote is uncommitted either way.
        print(
            f"\nland-wave: {len(uncommitted)} path(s) this wave's own records name are "
            "uncommitted. Commit them BY NAME \u2014 the landing does not, and the next emit "
            "HOLDS a baton whose record is dirty as if a live writer were still on it:"
        )
        for path in uncommitted:
            print(f"    {path}")

    if all_refused:
        print(
            "\nland-wave: STOP — a landing returned refusals. A refusal is the op declining "
            "to write something misleading; it is never a thing to route around.",
            file=sys.stderr,
        )
        return EXIT_LANDING_REFUSALS

    if advanced == 0:
        print(
            f"\nland-wave: STOP — wave {wave_index} opened nothing across all "
            f"{len(fires)} fire(s) (approved 0, execution_ready 0, closed 0). The next "
            "wave is this wave again; report rather than spinning.",
            file=sys.stderr,
        )
        return EXIT_WAVE_OPENED_NOTHING

    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
