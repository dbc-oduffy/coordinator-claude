#!/usr/bin/env python3
"""judge-coverage-backfill.py -- record a not_met judge verdict on historical concluded runs.

Walks `<root>/state/warp/*`, classifies each run with run-outcome-audit.py `_terminal` (loaded by file
path), and calls `ask_contract.record_terminal_judge_at` on every committed|closed run. A run already
carrying a met or not_met verdict is left byte-identical; halted, live and unknown runs are untouched.
Prints `scanned=N recorded=M`; `--dry-run` counts without writing.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_AUDIT = Path(__file__).resolve().with_name("run-outcome-audit.py")


def _load_audit():
    spec = importlib.util.spec_from_file_location("run_outcome_audit", _AUDIT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ask_contract():
    if str(_REPO) not in sys.path:
        sys.path.insert(0, str(_REPO))
    from coordinator_core.ops.dispatch_emit import ask_contract

    return ask_contract


def backfill(root: Path, dry_run: bool = False) -> tuple[int, int]:
    """Return (scanned, recorded) over the concluded runs of `<root>/state/warp`."""
    audit = _load_audit()
    contract = _ask_contract()
    warp = Path(root) / "state" / "warp"
    scanned = recorded = 0
    for run in sorted(p for p in warp.iterdir() if p.is_dir() and not p.name.startswith(".")):
        try:
            names = {e.name for e in os.scandir(run)}
        except OSError:
            continue
        terminal, _ = audit._terminal(str(run), names)
        if terminal not in ("committed", "closed"):
            continue
        scanned += 1
        if dry_run:
            outcome = audit._read_optional(str(run), names, "run-outcome.json")
            if not outcome or audit._judge(outcome)[0] not in ("met", "not_met"):
                recorded += 1
        elif contract.record_terminal_judge_at(run):
            recorded += 1
    return scanned, recorded


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=str(_REPO), help="repo root holding state/warp (default: this repo)")
    ap.add_argument("--dry-run", action="store_true", help="count runs that would be recorded; write nothing")
    args = ap.parse_args(argv)
    if not (Path(args.root) / "state" / "warp").is_dir():
        print(f"no state/warp under {args.root}", file=sys.stderr)
        return 2
    scanned, recorded = backfill(Path(args.root), args.dry_run)
    print(f"scanned={scanned} recorded={recorded}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
