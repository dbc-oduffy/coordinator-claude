"""
_copy_leg_engine_mirror -- engine-mirror leg of the Copies line.

Two verdicts for the one copy: currency (the resolved engine's `_engine_stamp`
against live engine-source HEAD, via `warm.skew.publish_lag`) and completeness (the
shared constant `could-not-check (no expected-manifest emitted)`). Spawn-free
here; the only git work is inside the injectable `publish_lag` callable.

Invariants:
    - `publish_lag` is reached only through `cc.resolve_engine_symbol` over
      `cc.ENGINE_CONSUMED_SYMBOLS`; never a bare import.
    - `None` from `publish_lag`, an unresolved symbol, or an absent stamp is
      could-not-check, never current.
    - `import_origin` (the cached `coordinator_core` package dir and interpreter) left
      at `UNCHECKED` skips the origin question; given, it must lie under the engine root
      or currency is drift, and an absent or errored field is could-not-check.
    - Completeness reads no manifest, allowlist or rename map.
    - No engine-source clone is could-not-check on both axes; the live-tree env
      override is currency current (no copy in play) and leaves completeness
      at the shared constant.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _copy_currency as cc  # noqa: E402

COPY = "engine-mirror"
OWNER = "claude-klabauter"
PUBLISH_LAG_SYMBOL = cc.ENGINE_CONSUMED_SYMBOLS[0]
STAMP_RELPATH = "coordinator_core/_engine_stamp"

UNCHECKED = object()

_NO_CLONE = "no claude-klabauter clone registered"
_LIVE_TREE_EVIDENCE = "session executes the live tree; no copy in play"


def _default_claude_klabauter_root() -> str | None:
    import _engine_root

    return _engine_root._resolve_live_working_tree()[0]


def _default_engine_root() -> str | None:
    import _engine_root

    return _engine_root.resolve_claude_klabauter_root()


def _default_live_tree() -> bool:
    import _engine_root

    return _engine_root._resolve_live_tree_env_override() is not None


def _remedy() -> str:
    return cc.no_local_remedy(OWNER)


def _completeness() -> cc.CopyVerdict:
    return cc.file_completeness_verdict(COPY, OWNER)


def _both_unchecked(reason: str) -> list[cc.CopyVerdict]:
    return [
        cc.could_not_check(COPY, cc.CURRENCY, reason),
        cc.could_not_check(COPY, cc.COMPLETENESS, reason),
    ]


def _under(child: str, root: str | Path) -> bool:
    try:
        return Path(os.path.realpath(child)).is_relative_to(os.path.realpath(root))
    except (OSError, ValueError):
        return False


def _origin_verdict(engine_root: str | Path, origin: object) -> cc.CopyVerdict | None:
    """None when the import origin lies under the engine root; otherwise the verdict to return."""
    if not isinstance(origin, dict):
        return cc.could_not_check(COPY, cc.CURRENCY, "coordinator_core import origin not recorded")
    if origin.get("error"):
        return cc.could_not_check(COPY, cc.CURRENCY, str(origin["error"]))
    package_dir = origin.get("package_dir")
    if not isinstance(package_dir, str) or not package_dir:
        return cc.could_not_check(COPY, cc.CURRENCY, "coordinator_core import origin not recorded")
    if _under(package_dir, engine_root):
        return None
    return cc.CopyVerdict(
        COPY,
        cc.CURRENCY,
        cc.DRIFT,
        detail=(
            f"coordinator_core imports from {package_dir} "
            f"(interpreter {origin.get('executable') or 'unknown'}), outside engine root {engine_root}"
        ),
        remedy=_remedy(),
    )


def check_currency(
    engine_root: str | Path,
    claude_klabauter_root: str | Path,
    publish_lag: Callable[[Path, Path], object] | None = None,
    import_origin: object = UNCHECKED,
) -> cc.CopyVerdict:
    """Currency verdict. `publish_lag` overrides the resolved engine symbol (tests)."""
    if not (Path(engine_root) / STAMP_RELPATH).is_file():
        return cc.could_not_check(COPY, cc.CURRENCY, "engine stamp absent")
    if import_origin is not UNCHECKED:
        verdict = _origin_verdict(engine_root, import_origin)
        if verdict is not None:
            return verdict
    fn = publish_lag
    if fn is None:
        fn, reason = cc.resolve_engine_symbol(PUBLISH_LAG_SYMBOL, engine_root)
        if fn is None:
            return cc.could_not_check(COPY, cc.CURRENCY, reason)
    lag = fn(Path(engine_root), Path(claude_klabauter_root))
    if lag is None:
        return cc.could_not_check(
            COPY,
            cc.CURRENCY,
            f"{PUBLISH_LAG_SYMBOL} could not establish freshness",
        )
    behind = getattr(lag, "engine_commits_behind", None)
    stamp = getattr(lag, "stamp_sha", "") or ""
    if not isinstance(behind, int) or isinstance(behind, bool) or behind < 0:
        return cc.could_not_check(
            COPY, cc.CURRENCY, f"{PUBLISH_LAG_SYMBOL} returned no usable commit count"
        )
    if behind > 0:
        return cc.CopyVerdict(
            COPY,
            cc.CURRENCY,
            cc.DRIFT,
            detail=f"{behind} engine-touching commit(s) past stamp {stamp[:10]}",
            remedy=_remedy(),
        )
    return cc.CopyVerdict(
        COPY,
        cc.CURRENCY,
        cc.CURRENT,
        evidence=f"stamp {stamp[:10]} is 0 engine-touching commits behind live claude-klabauter HEAD",
    )


def check_engine_mirror(
    engine_root: Callable[[], str | None] | str | Path | None = None,
    claude_klabauter_root: Callable[[], str | None] | str | Path | None = None,
    publish_lag: Callable[[Path, Path], object] | None = None,
    live_tree: Callable[[], bool] | bool | None = None,
    import_origin: object = UNCHECKED,
) -> list[cc.CopyVerdict]:
    """[currency, completeness] verdicts; any argument left None resolves from the registry."""
    is_live = live_tree() if callable(live_tree) else live_tree
    if live_tree is None:
        is_live = _default_live_tree()
    if is_live:
        return [
            cc.CopyVerdict(COPY, cc.CURRENCY, cc.CURRENT, evidence=_LIVE_TREE_EVIDENCE),
            _completeness(),
        ]
    claude_klabauter = claude_klabauter_root() if callable(claude_klabauter_root) else claude_klabauter_root
    if claude_klabauter_root is None:
        claude_klabauter = _default_claude_klabauter_root()
    if not claude_klabauter:
        return _both_unchecked(_NO_CLONE)
    engine = engine_root() if callable(engine_root) else engine_root
    if engine_root is None:
        engine = _default_engine_root()
    if not engine:
        return [
            cc.could_not_check(COPY, cc.CURRENCY, "no published engine root resolved"),
            _completeness(),
        ]
    return [check_currency(engine, claude_klabauter, publish_lag, import_origin), _completeness()]


def legs(
    engine_root: Callable[[], str | None] | str | Path | None = None,
    claude_klabauter_root: Callable[[], str | None] | str | Path | None = None,
    publish_lag: Callable[[Path, Path], object] | None = None,
    live_tree: Callable[[], bool] | bool | None = None,
) -> list[cc.CopyVerdict]:
    """The legs as the banner calls them: each axis wrapped so it can never raise or render current unrun."""

    def axis(index: int, name: str) -> cc.CopyVerdict:
        return cc.run_leg(
            COPY,
            name,
            lambda: check_engine_mirror(engine_root, claude_klabauter_root, publish_lag, live_tree)[index],
        )

    return [axis(0, cc.CURRENCY), axis(1, cc.COMPLETENESS)]
