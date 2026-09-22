"""Measure what a widened amplification discriminator actually silences, before it lands.

Every suppressor in `coordinator_core/tests/test_no_unbatched_per_item_git_spawn.py` ships
MEASURED (2026-08-19 PM ruling, recorded in that module's `_EXEMPT_SITES` docstring): a matcher
that retires its intended register keys AND silences a real amplification site elsewhere is worse
than the prose entry it replaced, because nothing downstream notices.

This measures the DELTA, never the mechanism. The 2026-08-19 session lost half a day twice to the
opposite approach -- stubbing the whole helper a widening lives in reports every key that mechanism
EVER suppressed as newly-suppressed, which misreads as catastrophic collateral and argues for
backing out a correct change. The only honest comparison is two collector runs over the same tree
with the registers emptied, one before the edit and one after.

Usage
-----
Before editing the collector::

    measure-amplification-discriminator.py baseline

Then edit, then::

    measure-amplification-discriminator.py delta --intended <key> [--intended <key> ...]

where each `<key>` is `relpath::enclosing::callee`. Exit 0 iff every intended key was retired and
nothing else changed; nonzero (with the offending keys named) otherwise.

The baseline lands under `tasks/` -- ephemera by design, one per measurement round. It is NOT a
frozen inventory: `_KNOWN_SITES` in the gate module is that, and this file must never be mistaken
for it.
"""

from __future__ import annotations

import argparse
import importlib
import json
import pathlib
import sys

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_BASELINE = _REPO_ROOT / "tasks" / "amp-discriminator-baseline.json"
_GATE_MODULE = "coordinator_core.tests.test_no_unbatched_per_item_git_spawn"


def _raw_violation_keys() -> set[tuple[str, str, str, int]]:
    """Collector output with BOTH suppression registers emptied.

    Emptying them is what makes the two runs comparable: with the registers live, retiring a key
    from `_EXEMPT_SITES` in the same edit would make the site reappear and read as a regression.
    The registers are re-read fresh each invocation because this runs as a separate process per
    round -- there is no cached verdict here, deliberately (see the module's "no status cache in
    the oracle layer" ruling; a cached measurement rots the same way).
    """
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    gate = importlib.import_module(_GATE_MODULE)
    setattr(gate, "_EXEMPT_SITES", set())
    setattr(gate, "_ORACLE_CLAIMS", {})
    roots = tuple(_REPO_ROOT / root for root in gate._GATE_SCOPE_ROOTS)
    return {site.key for site in gate.find_unbatched_per_item_spawns(roots)}


def _fmt(key: tuple[str, str, str, int]) -> str:
    """AC8: `relpath::enclosing::callee::ordinal` -- the 4-tuple `AmpSite.key` shape, round-
    tripped through `_parse` below. `ordinal` is always the LAST field, never interpolated among
    the first three, so a `::`-bearing path/enclosing/callee (none exist today, but the split
    below does not assume it) still parses left-to-right unambiguously against a trailing int."""
    path, enclosing, callee, ordinal = key
    return "::".join((path, enclosing, callee, str(ordinal)))


def _parse(raw: str) -> tuple[str, str, str, int]:
    parts = raw.split("::")
    if len(parts) != 4:
        raise argparse.ArgumentTypeError(
            f"expected relpath::enclosing::callee::ordinal, got {raw!r} ({len(parts)} fields)"
        )
    path, enclosing, callee, ordinal_raw = parts
    try:
        ordinal = int(ordinal_raw)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"expected an integer ordinal as the last field, got {ordinal_raw!r} in {raw!r}"
        ) from None
    return (path, enclosing, callee, ordinal)


def _project_3tuple(keys: set[tuple[str, str, str, int]]) -> set[tuple[str, str, str]]:
    """AC7: the honest baseline/delta invariant is on the 3-tuple `(path, enclosing, callee)`
    projection, not the 4-tuple key -- a baseline taken under the pre-AC8 3-tuple CLI cannot be
    diffed against post-migration 4-tuple keys without this projection first (see AC7's own
    sequencing note: baseline pre-migration/pre-AC8, comparison on the projection)."""
    return {(path, enclosing, callee) for path, enclosing, callee, _ordinal in keys}


def _cmd_baseline() -> int:
    keys = _raw_violation_keys()
    _BASELINE.parent.mkdir(parents=True, exist_ok=True)
    _BASELINE.write_text(
        json.dumps({"keys": sorted(_fmt(k) for k in keys)}, indent=2) + "\n",
        encoding="utf-8", newline="\n",
    )
    print(f"baseline: {len(keys)} raw violation keys -> {_BASELINE.relative_to(_REPO_ROOT)}")
    return 0


def _cmd_delta(
    intended: list[tuple[str, str, str, int]],
    intended_new: list[tuple[str, str, str, int]],
) -> int:
    """AC7: compared on the 3-tuple `(path, enclosing, callee)` projection of the post-migration
    4-tuple keys -- a baseline recorded pre-migration (under the pre-AC8 3-tuple CLI) has no
    `ordinal` field to diff a 4-tuple key against directly. `before` is read as a 3-tuple
    regardless of whether the stored baseline file predates or postdates AC8 (`k.split("::")[:3]`
    drops a trailing ordinal field if present, a no-op if not). `--intended-new` is the AC3-split
    allowlist: keys this migration deliberately, correctly surfaces (never `--intended`, which
    means "this edit RETIRES this key" -- the opposite claim)."""
    if not _BASELINE.exists():
        print(
            f"no baseline at {_BASELINE.relative_to(_REPO_ROOT)} -- run `baseline` BEFORE editing "
            "the collector; a baseline taken after the edit measures nothing",
            file=sys.stderr,
        )
        return 2

    before = {
        tuple(k.split("::")[:3])
        for k in json.loads(_BASELINE.read_text(encoding="utf-8"))["keys"]
    }
    after = _project_3tuple(_raw_violation_keys())

    retired = before - after
    appeared = after - before
    intended_set = _project_3tuple(set(intended))
    intended_new_set = _project_3tuple(set(intended_new))

    collateral = retired - intended_set
    missed = intended_set - retired
    unintended_appearances = appeared - intended_new_set

    print(f"3-tuple keys: {len(before)} -> {len(after)}  (retired {len(retired)})")
    for label, keys in (
        ("RETIRED AS INTENDED", sorted(retired & intended_set)),
        ("COLLATERAL -- silenced outside the register", sorted(collateral)),
        ("NOT RETIRED -- intended but still firing", sorted(missed)),
        ("APPEARED AS INTENDED (--intended-new)", sorted(appeared & intended_new_set)),
        ("APPEARED -- newly flagged, not in --intended-new", sorted(unintended_appearances)),
    ):
        if keys:
            print(f"\n{label} ({len(keys)}):")
            for key in keys:
                print(f"  {'::'.join(key)}")

    if collateral or missed or unintended_appearances:
        return 1
    print("\nclean: exactly the intended keys, zero collateral")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("baseline", help="record raw violation keys BEFORE editing the collector")
    delta = sub.add_parser("delta", help="compare against the baseline AFTER editing")
    delta.add_argument(
        "--intended",
        action="append",
        default=[],
        type=_parse,
        metavar="relpath::enclosing::callee::ordinal",
        help="a key this edit is meant to retire; repeat per key",
    )
    delta.add_argument(
        "--intended-new",
        action="append",
        default=[],
        type=_parse,
        metavar="relpath::enclosing::callee::ordinal",
        help="a key this edit deliberately, correctly NEWLY surfaces (AC3-class split); "
        "repeat per key",
    )
    args = parser.parse_args(argv)
    if args.command == "baseline":
        return _cmd_baseline()
    return _cmd_delta(args.intended, args.intended_new)


if __name__ == "__main__":
    raise SystemExit(main())
