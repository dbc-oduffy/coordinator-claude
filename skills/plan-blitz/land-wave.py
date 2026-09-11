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
  - a result carrying a non-empty `dispatched` with no `--shipped-in`. The op would refuse
    those batons one at a time and the wave would read as landed-with-refusals; refusing
    up front names the actual missing input, which is a commit that has not been made.
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


def _invoke(repo_root: Path, engine_root: Path | None, op: str, params: dict,
            live_engine_tree: bool = False) -> dict:
    settings_home = os.environ.get("COORDINATOR_SETTINGS_HOME") or str(
        Path(os.environ.get("CLAUDE_HOME") or Path.home()) / ".coordinator-claude-settings"
    )
    launcher = Path(settings_home) / "bin" / "coordinator-invoke"
    if launcher.is_file():
        cmd = [str(launcher)]
    elif engine_root is not None:
        cmd = [sys.executable, str(engine_root / "coordinator" / "bin" / "coordinator-invoke.py")]
    else:
        raise ValueError(
            f"no coordinator-invoke launcher at {launcher}, and no --engine-root or "
            "$COORDINATOR_ENGINE_ROOT to fall back to."
        )

    env = dict(os.environ)
    if engine_root is not None:
        env.setdefault("COORDINATOR_ENGINE_ROOT", str(engine_root))
    proc = subprocess.run(
        cmd + [op, json.dumps(params)]
        + (["--allow-unstamped-dispatch"] if live_engine_tree else []),
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
    dispatching = [
        str(p)
        for p, r in fires
        if any(e.get("completed") for e in (r.get("dispatched") or []) if isinstance(e, dict))
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
    landings, all_refused, all_surfaced = [], [], []
    next_wave = None

    for path, result in fires:
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
        counted = {lane: len(reply.get(lane) or []) for lane in _LANES}
        for lane, n in counted.items():
            totals[lane] += n

        all_refused.extend(reply.get("refused") or [])
        all_surfaced.extend(reply.get("surfaced_to_pm") or [])
        # Each landing recomputes `next_wave` from a FRESH gate read taken after its
        # own writes, so the last fire's is the only current one — an earlier fire's
        # was computed before the later fires had landed anything.
        next_wave = reply.get("next_wave") or next_wave
        landings.append({"fire": path.name, "counted": counted, "reply": reply})

    advanced = sum(totals.values())

    if args.json:
        print(
            json.dumps(
                {
                    "waveIndex": wave_index,
                    "totals": totals,
                    "advanced": advanced,
                    "refused": all_refused,
                    "surfacedToPm": all_surfaced,
                    "nextWave": next_wave,
                    "landings": [
                        {"fire": l["fire"], "counted": l["counted"]} for l in landings
                    ],
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
        if next_wave:
            print(f"  next     wave {next_wave.get('waveIndex')}: "
                  f"{len(next_wave.get('batons') or [])} baton(s)")

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
