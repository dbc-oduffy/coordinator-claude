"""sizing-accept-exit-criterion.py -- argparse trampoline over the
`sizing.accept_exit_criterion` op (`coordinator_core/ops/sizing_accept_exit_criterion.py`).

Records the PM's verbatim acceptance of a sizing-object's exit criterion
(`exit_criterion.accepted`) through `lib/op_trampoline.run`; the op owns every
rule, this file owns only the argv grammar and the `--help` text.

Usage:
    sizing-accept-exit-criterion.py --sizing PATH (--pm-quote TEXT | --apm-ruling TEXT)
        [--statement TEXT] [--mode {hands-on,pm,ceo}] [--supersede]

Exit codes:
    0 -- accepted, or an identical acceptance was already on record (no-op).
    1 -- the op refused (see the epilog) or the engine/repo root was unreachable.
    2 -- argparse usage error (a missing --sizing, neither or both of
         --pm-quote/--apm-ruling, an unknown flag).

Negative-spec: does NOT compose, infer, or default `--pm-quote` or `--apm-ruling`; does NOT
touch any sizing field except `exit_criterion` (and `interaction_mode` when
`--mode` is given and none is recorded); does NOT commit.
"""
from __future__ import annotations

import argparse
import os
import sys

_BIN_DIR = os.path.dirname(os.path.abspath(__file__))

_MODES = ("hands-on", "pm", "ceo")

_EPILOG = """\
Exit 1 (refused) when: --sizing escapes state/sizings/ or is absent on disk;
--pm-quote/--apm-ruling is empty; --apm-ruling is given on a hands-on sizing
(effective mode: --mode, else the recorded interaction_mode, else hands-on) or over a
PM acceptance; --mode is not one of hands-on/pm/ceo; no statement is on
record and none is given; the criterion is already accepted and neither a new
--statement nor --supersede is given; schema validation or the file lock fails.
Exit 0 with applied=true when exit_criterion.accepted was written; exit 0 with
applied=false when an identical acceptance was already recorded.
A new --statement on an already-accepted sizing amends the statement and
appends to exit_criterion.amendments, leaving `accepted` untouched."""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="sizing-accept-exit-criterion.py",
        description=(
            "Record the PM's acceptance of a sizing-object's exit criterion "
            "(sizing.accept_exit_criterion)."
        ),
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--sizing",
        required=True,
        help="absolute or repo-relative path to the sizing-object under state/sizings/.",
    )
    who = p.add_mutually_exclusive_group(required=True)
    who.add_argument(
        "--pm-quote",
        help="the PM's own verbatim words accepting the criterion; never composed or "
        "paraphrased. Must be non-empty. Replaces an APM acceptance without --supersede.",
    )
    who.add_argument(
        "--apm-ruling",
        help="the APM's verbatim ruling standing in for the PM; only in pm/ceo mode and "
        "never over a PM acceptance.",
    )
    p.add_argument(
        "--statement",
        default=None,
        help="the PM's amended criterion, replacing the proposed one in the same write. "
        "Omitted: the statement already on record is kept.",
    )
    p.add_argument(
        "--mode",
        choices=_MODES,
        default=None,
        help="the interaction_mode the sizing ran under at acceptance (default: the "
        "sizing's recorded interaction_mode, else hands-on); also recorded "
        "as the sizing's interaction_mode when it has none.",
    )
    p.add_argument(
        "--supersede",
        action="store_true",
        help="overwrite an already-accepted criterion; without it a second acceptance "
        "is refused.",
    )
    return p


def build_params(argv: list[str]) -> dict[str, object]:
    ns = build_parser().parse_args(argv)
    params: dict[str, object] = {"sizing": ns.sizing}
    if ns.pm_quote is not None:
        params["pm_quote"] = ns.pm_quote
    if ns.apm_ruling is not None:
        params["apm_ruling"] = ns.apm_ruling
    if ns.statement is not None:
        params["statement"] = ns.statement
    if ns.mode is not None:
        params["mode"] = ns.mode
    if ns.supersede:
        params["supersede"] = True
    return params


def main(argv: list[str] | None = None) -> int:
    import lib  # noqa: F401 -- bootstraps coordinator/bin/lib onto sys.path
    from op_trampoline import run

    argv = sys.argv[1:] if argv is None else argv
    return run("sizing.accept_exit_criterion", build_params, argv=argv)


if __name__ == "__main__":
    sys.exit(main())
