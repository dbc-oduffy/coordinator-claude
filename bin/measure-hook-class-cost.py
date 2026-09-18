"""
coordinator.bin.measure-hook-class-cost -- per-class structural + round-trip cost harness for
the hook-routing decision.

Ported from DoE-claude `coordinator/bin/measure-hook-class-cost.py` (W3-C1,
`docs/plans/2026-09-18-doe-holds-no-scripts.md`) -- mechanical move, no behavioural change.
`_REPO_ROOT` and `_PROBE_PATH` were already "engine" class (§ Path resolution): both resolve
from this module's own `__file__`, unchanged by the move -- `Path(__file__).parents[2]` was
already the engine root in DoE (a sibling of `coordinator/bin`) and stays the engine root here.
The module docstring's reference to `coordinator/hooks/scripts/_engine_root.py` below still
names a DoE-claude file (that hook lands with Wave 4, not this chunk) -- kept as prose evidence
for the zero-spawn scoping claim, not a runtime import.

Purpose: claude-klabauter's agreed instrument (structural counters -- `len(sys.modules)`, its
`coordinator_core.*` subset, file opens, spawn count, adopted here via `_hook_cost_probe.py`,
same fresh-interpreter-subprocess discipline as their own `coordinator_core.benchmarks.
import_budget`) is right about everything except the http-transport round trip, which has no
structural signature at all -- it is a network/pipe wait, not an import or a file access. This
module measures BOTH arms of a class with that instrument, and separately measures the round
trip as its own named line, never folded into either arm's structural counters.

The round trip is reported as a full distribution, never a mean, because a mean hides exactly the
failure that already bit this surface once: an earlier scratch harness produced a bimodal 14-17ms
band, published as a "Windows timer quantum floor," which re-measurement refuted outright (n=1600,
zero in-band -- see `coordinator/bin/measure-loopback-round-trip.py` and
`docs/research/2026-08-19-hook-class-route-budget.md`). The measured round trip is sub-millisecond
on the `127.0.0.1` literal. Dialing the name `localhost` instead costs ~2s/call on this platform.

Guard-rails (AC3) are enforced here, not merely documented: `guard_wall_clock_report` refuses to
let a wall-clock figure out when N differs across arms, when the arms were not measured
interleaved within one load window, when the concurrent-session count is absent, or when the two
arms' structural counters are indistinguishable -- a failed control, measurement void. Precedent
for the last one, cited in the refusal message: claude-klabauter's own d450109ab, where a confirmed
warm hit measured no faster than cold (221ms vs 224ms CLI ping) because the two arms were not yet
structurally distinguishable -- the module-count delta is what exposed the regression wall-clock
alone called a wash. Claude-klabauter's own prior harness reported COLD at n=8 against WARM at
n=200 in one table; this module's N-equality refusal is what stops this plan inheriting that.

Zero-spawn does NOT apply to this script. Per `coordinator/hooks/scripts/_engine_root.py`'s
module docstring, the zero-spawn constraint applies to "hot-path PreToolUse/PostToolUse
dispatch" and is "a constraint on this repo's hook code in its own right" -- this is a bin tool
run deliberately, on demand, never on the tool-call hot path.

Spec backlink: pln-the-doe-side-of-the-warm-engin-a6876d chunk C2 (AC2, AC3).
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROBE_PATH = Path(__file__).parent / "_hook_cost_probe.py"

_PROBE_TIMEOUT_S = 30

# Cited verbatim in the indistinguishable-arms refusal (AC3) -- claude-klabauter's own precedent
# for why "the two arms look the same" is a failed control, not a clean result: a confirmed warm
# hit measured no faster than cold (221ms vs 224ms CLI ping) until the module-count delta, not
# wall-clock, exposed that the two arms were not yet structurally distinguishable.
D450109AB_PRECEDENT = (
    "claude-klabauter d450109ab: a confirmed warm hit measured no faster than cold "
    "(221ms vs 224ms, CLI ping) because the structural cost dominated and the two arms were "
    "not actually distinguishable -- the module-count delta, not wall-clock, is what exposed "
    "the regression."
)


class MeasurementRefused(RuntimeError):
    """Raised when this harness's own guard-rails refuse to emit a wall-clock figure (AC3)."""


@dataclass(frozen=True)
class StructuralCost:
    """One arm's structural counters, aggregated across `n` fresh-interpreter trials."""

    label: str
    module_count: int
    own_module_count: int
    file_open_count: int
    spawn_count: int
    n: int

    def as_report(self) -> dict:
        return {
            "label": self.label,
            "module_count": self.module_count,
            "own_module_count": self.own_module_count,
            "file_open_count": self.file_open_count,
            "spawn_count": self.spawn_count,
            "n": self.n,
        }


@dataclass(frozen=True)
class RoundTripDistribution:
    """The transport round-trip term -- the thing the structural instrument cannot see.

    Reported as a full sample distribution, never a mean (see module docstring). `platform` and
    `timer_resolution_ms` are required fields (AC3): the harness refuses to emit a round-trip
    figure that does not record the platform it was measured on.
    """

    samples_ms: tuple
    platform: str
    timer_resolution_ms: float

    def as_report(self) -> dict:
        return {
            "n": len(self.samples_ms),
            "platform": self.platform,
            "timer_resolution_ms": self.timer_resolution_ms,
            "distribution_ms": sorted(self.samples_ms),
            "note": (
                "distribution only -- a mean over a quantized bimodal distribution "
                "describes nothing that happens"
            ),
        }


@dataclass(frozen=True)
class ClassCostReport:
    """One class's full C2 report: both structural arms, plus the round-trip term as its own
    named line -- never folded into either arm."""

    class_name: str
    arm_a: StructuralCost
    arm_b: StructuralCost
    interleaved: bool
    concurrent_session_count: Optional[int]
    round_trip: Optional[RoundTripDistribution] = None

    def as_report(self) -> dict:
        report = {
            "class_name": self.class_name,
            "arm_a": self.arm_a.as_report(),
            "arm_b": self.arm_b.as_report(),
            "interleaved": self.interleaved,
            "concurrent_session_count": self.concurrent_session_count,
        }
        if self.round_trip is not None:
            report["round_trip"] = self.round_trip.as_report()
        return report


def _run_probe_once(entrypoint: str, python: Optional[str] = None) -> dict:
    python = python or sys.executable
    result = subprocess.run(
        [python, str(_PROBE_PATH), entrypoint],
        capture_output=True,
        text=True,
        timeout=_PROBE_TIMEOUT_S,
        check=False,
        cwd=str(_REPO_ROOT),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"structural probe for entrypoint {entrypoint!r} exited {result.returncode}: "
            f"{result.stderr}"
        )
    return json.loads(result.stdout.strip())


def _aggregate_structural(label: str, samples: Sequence[dict]) -> StructuralCost:
    """Structural counters are deterministic for a fixed dependency graph -- assert every trial
    agrees rather than averaging, so a flaky probe surfaces as a refusal rather than a silently
    smoothed number."""
    first = samples[0]
    for other in samples[1:]:
        if other != first:
            raise MeasurementRefused(
                f"structural probe for arm {label!r} disagreed across {len(samples)} trials "
                f"({first} vs {other}) -- not a fixed dependency graph, refusing to report a "
                "single figure"
            )
    return StructuralCost(
        label=label,
        module_count=first["module_count"],
        own_module_count=first["own_module_count"],
        file_open_count=first["file_open_count"],
        spawn_count=first["spawn_count"],
        n=len(samples),
    )


def measure_structural_arms(
    class_name: str,
    arm_a_label: str,
    arm_a_entrypoint: str,
    arm_b_label: str,
    arm_b_entrypoint: str,
    *,
    n: int = 1,
    python: Optional[str] = None,
) -> tuple:
    """Measure both arms, interleaved trial-by-trial within one load window (A, B, A, B, ...)
    rather than batched (A x n then B x n) -- the shape claude-klabauter's own prior harness did
    NOT use, and whose absence (COLD at n=8 against WARM at n=200 in one table) this harness's
    N-equality guard-rail exists to catch."""
    a_samples = []
    b_samples = []
    for _ in range(n):
        a_samples.append(_run_probe_once(arm_a_entrypoint, python))
        b_samples.append(_run_probe_once(arm_b_entrypoint, python))
    arm_a = _aggregate_structural(arm_a_label, a_samples)
    arm_b = _aggregate_structural(arm_b_label, b_samples)
    return arm_a, arm_b


def _timer_resolution_ms() -> float:
    return time.get_clock_info("perf_counter").resolution * 1000


def measure_round_trip(call_fn: Callable[[], None], n: int = 200) -> RoundTripDistribution:
    """Measure the transport round trip -- the term the structural instrument cannot see -- as
    `n` samples, reported as a distribution (see module docstring; never averaged here)."""
    samples = []
    for _ in range(n):
        t0 = time.perf_counter()
        call_fn()
        samples.append((time.perf_counter() - t0) * 1000)
    return RoundTripDistribution(
        samples_ms=tuple(samples),
        platform=platform.platform(),
        timer_resolution_ms=_timer_resolution_ms(),
    )


def guard_wall_clock_report(
    arm_a: StructuralCost,
    arm_b: StructuralCost,
    *,
    interleaved: bool,
    concurrent_session_count: Optional[int],
    round_trip: Optional[RoundTripDistribution] = None,
) -> None:
    """Enforce AC3: refuse to emit a wall-clock figure under any of the four named conditions.
    Raises `MeasurementRefused`; callers that want a report must catch this and print the
    refusal, never suppress it and fall back to reporting anyway."""
    if arm_a.n != arm_b.n:
        raise MeasurementRefused(
            "refusing to emit a wall-clock figure: arm N differs "
            f"({arm_a.label}={arm_a.n} vs {arm_b.label}={arm_b.n})"
        )
    if not interleaved:
        raise MeasurementRefused(
            "refusing to emit a wall-clock figure: arms were not interleaved within one load "
            "window"
        )
    if concurrent_session_count is None:
        raise MeasurementRefused(
            "refusing to emit a wall-clock figure: concurrent-session count is absent"
        )
    if (
        arm_a.module_count == arm_b.module_count
        and arm_a.own_module_count == arm_b.own_module_count
        and arm_a.file_open_count == arm_b.file_open_count
        and arm_a.spawn_count == arm_b.spawn_count
    ):
        raise MeasurementRefused(
            "refusing to emit a wall-clock figure: the two arms' structural counters are "
            "indistinguishable (identical module count, coordinator_core.* subset, file-open "
            f"count, spawn count) -- a failed control, measurement void. Precedent: "
            f"{D450109AB_PRECEDENT}"
        )
    if round_trip is not None:
        if not round_trip.platform:
            raise MeasurementRefused(
                "refusing to emit a round-trip figure: missing required field 'platform'"
            )
        if round_trip.timer_resolution_ms is None:
            raise MeasurementRefused(
                "refusing to emit a round-trip figure: missing required field "
                "'timer_resolution_ms'"
            )


def measure_class(
    class_name: str,
    arm_a_label: str,
    arm_a_entrypoint: str,
    arm_b_label: str,
    arm_b_entrypoint: str,
    *,
    n: int = 1,
    python: Optional[str] = None,
    concurrent_session_count: Optional[int] = None,
    round_trip_call: Optional[Callable[[], None]] = None,
    round_trip_n: int = 200,
) -> ClassCostReport:
    """Run one class's full C2 measurement: both structural arms (interleaved), plus the
    round-trip term as its own named line when `round_trip_call` is supplied."""
    arm_a, arm_b = measure_structural_arms(
        class_name, arm_a_label, arm_a_entrypoint, arm_b_label, arm_b_entrypoint, n=n, python=python
    )
    round_trip = None
    if round_trip_call is not None:
        round_trip = measure_round_trip(round_trip_call, n=round_trip_n)
    return ClassCostReport(
        class_name=class_name,
        arm_a=arm_a,
        arm_b=arm_b,
        interleaved=True,
        concurrent_session_count=concurrent_session_count,
        round_trip=round_trip,
    )


def render_report(report: ClassCostReport) -> dict:
    """Render `report` to a plain dict, running the AC3 guard-rail first. On refusal, the
    returned dict carries `refused: true` and the refusal message -- never a wall-clock figure
    alongside it."""
    try:
        guard_wall_clock_report(
            report.arm_a,
            report.arm_b,
            interleaved=report.interleaved,
            concurrent_session_count=report.concurrent_session_count,
            round_trip=report.round_trip,
        )
    except MeasurementRefused as exc:
        return {
            "class_name": report.class_name,
            "refused": True,
            "reason": str(exc),
            "arm_a": report.arm_a.as_report(),
            "arm_b": report.arm_b.as_report(),
        }
    return {**report.as_report(), "refused": False}


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="measure-hook-class-cost",
        description=(
            "Per-class structural-cost harness (two fresh-interpreter arms) plus the transport "
            "round-trip term, reported as its own named line."
        ),
    )
    parser.add_argument("class_name", help="Name of the class being measured (report label only)")
    parser.add_argument("arm_a_label")
    parser.add_argument("arm_a_entrypoint", help="Importable module path for arm A")
    parser.add_argument("arm_b_label")
    parser.add_argument("arm_b_entrypoint", help="Importable module path for arm B")
    parser.add_argument("--n", type=int, default=1, help="Trials per arm (interleaved)")
    parser.add_argument(
        "--concurrent-session-count",
        type=int,
        default=None,
        help="Concurrent-session count at measurement time -- required for a wall-clock figure",
    )
    parser.add_argument("--out", type=Path, default=None, help="Write JSON report here instead of stdout")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    report = measure_class(
        args.class_name,
        args.arm_a_label,
        args.arm_a_entrypoint,
        args.arm_b_label,
        args.arm_b_entrypoint,
        n=args.n,
        concurrent_session_count=args.concurrent_session_count,
    )
    rendered = render_report(report)
    text = json.dumps(rendered, indent=2)
    if args.out is not None:
        args.out.write_text(text, encoding="utf-8", newline="\n")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
