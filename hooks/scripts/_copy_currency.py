"""
_copy_currency -- three-state verdict contract for the copies a session runs.

One question per verdict: is this copy current, drifted, or unknown, and why.
Legs build `CopyVerdict`s, run inside `run_leg`, and `render_copies_lines`
prints the pinned `Copies:` banner. Stdlib-only; no spawns.

Invariants:
    - `current` requires non-empty evidence; `could-not-check` requires a reason.
    - `run_leg` converts any exception into could-not-check, never current.
    - A `drift` remedy is a confirmed-reachable command or the literal
      `no local remedy -- <owner> publish`; never `setup.py`.
    - File completeness of both mirrors is the constant
      `could-not-check (no expected-manifest emitted)` until a publisher
      manifest exists; no manifest reader or join lives here.
"""
from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

CURRENT = "current"
DRIFT = "drift"
COULD_NOT_CHECK = "could-not-check"
STATES = (CURRENT, DRIFT, COULD_NOT_CHECK)

CURRENCY = "currency"
COMPLETENESS = "completeness"
AXES = (CURRENCY, COMPLETENESS)

NO_MANIFEST_REASON = "no expected-manifest emitted"

ENGINE_CONSUMED_SYMBOLS = ("coordinator_core.warm.skew.publish_lag",)


def no_local_remedy(owner: str) -> str:
    """The only admissible remedy for a drift no command on this box can fix."""
    return f"no local remedy — {owner} publish"


@dataclass(frozen=True)
class CopyVerdict:
    """One copy, one axis, one state. Construction enforces the three rules."""

    copy: str
    axis: str
    state: str
    detail: str = ""
    evidence: str = ""
    remedy: str = ""

    def __post_init__(self) -> None:
        if self.axis not in AXES:
            raise ValueError(f"axis must be one of {AXES}, got {self.axis!r}")
        if self.state not in STATES:
            raise ValueError(f"state must be one of {STATES}, got {self.state!r}")
        if self.state == CURRENT and not self.evidence.strip():
            raise ValueError("a current verdict requires non-empty evidence")
        if self.state == COULD_NOT_CHECK and not self.detail.strip():
            raise ValueError("a could-not-check verdict requires a reason in detail")
        if self.state == DRIFT:
            if not self.remedy.strip():
                raise ValueError("a drift verdict requires a remedy")
            if "setup.py" in self.remedy:
                raise ValueError("a drift remedy must not name setup.py")


def could_not_check(copy: str, axis: str, reason: str, remedy: str = "") -> CopyVerdict:
    return CopyVerdict(copy, axis, COULD_NOT_CHECK, detail=reason, remedy=remedy)


def file_completeness_verdict(copy: str, owner: str = "claude-klabauter") -> CopyVerdict:
    """Shared constant completeness verdict both mirror legs return."""
    return could_not_check(
        copy, COMPLETENESS, NO_MANIFEST_REASON, remedy=no_local_remedy(owner)
    )


def run_leg(copy: str, axis: str, leg: Callable[[], CopyVerdict]) -> CopyVerdict:
    """Run a leg; any exception or non-verdict return becomes could-not-check."""
    try:
        verdict = leg()
    except Exception as exc:  # noqa: BLE001 -- the contract is to never raise
        return could_not_check(copy, axis, f"leg raised {type(exc).__name__}: {exc}")
    if not isinstance(verdict, CopyVerdict):
        return could_not_check(copy, axis, "leg returned no CopyVerdict")
    return verdict


def resolve_engine_symbol(
    symbol: str, engine_root: str | Path | None
) -> tuple[Callable | None, str]:
    """Resolve a dotted engine symbol under engine_root.

    Returns (callable, "") or (None, reason naming the symbol). The module is
    loaded by file path under a private name so the resolved root is the only
    source and sys.modules is not polluted.
    """
    if not engine_root:
        return None, f"{symbol}: no engine root resolved"
    module_path, _, attr = symbol.rpartition(".")
    if not module_path:
        return None, f"{symbol}: not a dotted symbol"
    root = Path(engine_root)
    parts = module_path.split(".")
    candidate = root.joinpath(*parts).with_suffix(".py")
    if not candidate.is_file():
        return None, f"{symbol}: module file absent under engine root"
    name = "_copy_currency_engine_" + "_".join(parts)
    try:
        spec = importlib.util.spec_from_file_location(name, candidate)
        if spec is None or spec.loader is None:
            return None, f"{symbol}: module not loadable"
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        finally:
            sys.modules.pop(name, None)
    except Exception as exc:  # noqa: BLE001
        return None, f"{symbol}: import failed ({type(exc).__name__}: {exc})"
    fn = getattr(module, attr, None)
    if not callable(fn):
        return None, f"{symbol}: symbol does not resolve"
    return fn, ""


def _detail_line(v: CopyVerdict) -> str:
    detail = f"{COULD_NOT_CHECK} ({v.detail})" if v.state == COULD_NOT_CHECK else v.detail
    text = f"   {v.copy} {v.axis}: {detail}"
    if v.remedy:
        text += f" — remedy: {v.remedy}"
    return text


def _cell(verdicts: Iterable[CopyVerdict], copy: str, axis: str) -> str:
    for v in verdicts:
        if v.copy == copy and v.axis == axis:
            return v.state
    return COULD_NOT_CHECK


def render_copies_lines(verdicts: Iterable[CopyVerdict]) -> list[str]:
    """Pinned `Copies:` banner: one summary line, then a detail line per non-current verdict.

    A (copy, axis) cell with no verdict renders could-not-check, never current.
    """
    vs = list(verdicts)
    head = (
        "── Copies: "
        f"engine-mirror currency={_cell(vs, 'engine-mirror', CURRENCY)} "
        f"completeness={_cell(vs, 'engine-mirror', COMPLETENESS)}; "
        f"plugin-mirror currency={_cell(vs, 'plugin-mirror', CURRENCY)} "
        f"completeness={_cell(vs, 'plugin-mirror', COMPLETENESS)}; "
        f"capability-index currency={_cell(vs, 'capability-index', CURRENCY)}"
    )
    lines = [head]
    for v in vs:
        if v.state != CURRENT:
            lines.append(_detail_line(v))
    return lines
