"""debash-scorecard.py — how close is the DoE tree to zero `.sh`?

Answers "have we rid ourselves of bash yet?" as a number, not an investigation.

The PM directive of record is CLEAN-SLATE: zero `.sh` in the DoE tree, with an
irreducible floor of one bootstrap file (`resolve-python.sh` — corrected from two
on 2026-07-22; `spawn-hidden.sh` did not hold up as irreducible and has been
ported, see MASTER-disposition.md §6). The full per-file disposition lives in
`tasks/2026-07-15-sh-inventory/MASTER-disposition.md` (7 streams, owners, gates);
this script is only the running total against that baseline.

Two populations are counted separately on purpose, because they retire under
different streams and conflating them hides progress:

  * runtime  — production `.sh` on a live path
  * tests    — `.sh` under a `tests/` dir, a separate clean-slate stream

Within runtime, the split that matters for effort estimation is:

  * polyglot   — `#!/bin/sh` header wrapping a Python body. Mechanically
                 strippable to a pure `.py` + launcher (the debash plan's W4).
  * real bash  — genuine shell logic. Needs an actual port or a delete-with-
                 caller-repoint; NOT covered by W4/W5.
  * ported     — `#!/usr/bin/env python3` (or `python`) shebang: fully-native
                 Python already, filename kept WITH its `.sh` suffix so
                 hardcoded caller paths don't need N edits (see
                 `detect-hardware.sh`'s own docstring for the precedent).
                 NOT counted toward `runtime` — it is done, not debt.

Usage:
    python coordinator/bin/debash-scorecard.py            # human summary
    python coordinator/bin/debash-scorecard.py --json     # machine-readable

Exit status is always 0 — this reports, it does not gate.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

BASELINE = {"all": 666, "tests": 278, "runtime": 388}

# similar reason (a Python parent can set CREATE_NO_WINDOW directly).
FLOOR = ()


def repo_root() -> Path:
    try:
        from coordinator_core.git.repo_root import show_toplevel

        top = show_toplevel(str(Path(__file__).resolve().parent))
        if top:
            return Path(top)
    except (ImportError, OSError):
        pass
    return Path(__file__).resolve().parents[2]


def is_polyglot(path: Path) -> bool:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            return fh.readline().startswith("#!/bin/sh")
    except OSError:
        return False


def is_ported(path: Path) -> bool:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
            return first.startswith("#!/usr/bin/env python") or first.startswith("#!python")
    except OSError:
        return False


def collect(coordinator: Path) -> dict:
    runtime_poly: list[str] = []
    runtime_bash: list[str] = []
    runtime_ported: list[str] = []
    tests: list[str] = []
    colocated_tests: list[str] = []

    for path in sorted(coordinator.rglob("*.sh")):
        if not path.is_file():
            continue
        rel = path.relative_to(coordinator).as_posix()
        if any(part in ("tests", "test") for part in path.relative_to(coordinator).parts):
            tests.append(rel)
        elif path.name.endswith(".test.sh"):
            colocated_tests.append(rel)
        elif is_polyglot(path):
            runtime_poly.append(rel)
        elif is_ported(path):
            runtime_ported.append(rel)
        else:
            runtime_bash.append(rel)

    runtime = runtime_poly + runtime_bash
    present_floor = [f for f in FLOOR if (coordinator / f).is_file()]

    return {
        "all": len(runtime) + len(tests) + len(colocated_tests),
        "runtime": len(runtime),
        "runtime_polyglot": len(runtime_poly),
        "runtime_real_bash": len(runtime_bash),
        "runtime_ported": len(runtime_ported),
        "colocated_tests": len(colocated_tests),
        "tests": len(tests),
        "floor_target": len(FLOOR),
        "floor_present": present_floor,
        "runtime_polyglot_files": runtime_poly,
        "runtime_real_bash_files": runtime_bash,
        "runtime_ported_files": runtime_ported,
    }


def delta(now: int, was: int) -> str:
    if not was:
        return str(now)
    diff = now - was
    pct = round(diff * 100.0 / was)
    return f"{was} -> {now}  ({diff:+d}, {pct:+d}%)"


def main(argv: "list[str] | None" = None) -> int:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    import cc_invoke

    cc_invoke.ensure_engine_on_path(__file__)

    ap = argparse.ArgumentParser(description="Report progress toward zero .sh in the DoE tree.")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    ap.add_argument(
        "--list",
        choices=("polyglot", "bash"),
        help="list the remaining runtime files of that kind, one per line",
    )
    args = ap.parse_args(argv)

    coordinator = repo_root() / "coordinator"
    if not coordinator.is_dir():
        print(f"ERROR: no coordinator/ tree at {coordinator}", file=sys.stderr)
        return 0

    data = collect(coordinator)

    if args.list:
        key = "runtime_polyglot_files" if args.list == "polyglot" else "runtime_real_bash_files"
        for rel in data[key]:
            print(rel)
        return 0

    if args.json:
        print(json.dumps(data, indent=2))
        return 0

    remaining = data["all"] - data["floor_target"]
    print(f"de-bash scorecard — target: zero .sh (floor {len(FLOOR)})")
    print("  baseline: MASTER-disposition.md, 2026-07-15")
    print()
    print(f"  all .sh        {delta(data['all'], BASELINE['all'])}")
    print(f"  runtime        {delta(data['runtime'], BASELINE['runtime'])}")
    print(f"    polyglot     {data['runtime_polyglot']:>4}   mechanical header-strip (W4)")
    print(f"    real bash    {data['runtime_real_bash']:>4}   needs a port or delete+repoint")
    print(f"  ported (done)  {data['runtime_ported']:>4}   .sh-named, already pure Python — not counted above")
    print(f"  co-located tests {data['colocated_tests']:>2}   *.test.sh; follow their target")
    print(f"  tests          {delta(data['tests'], BASELINE['tests'])}")
    print()
    print(f"  floor present  {len(data['floor_present'])}/{data['floor_target']}  "
          f"({', '.join(data['floor_present']) or 'none'})")
    print(f"  still to retire {remaining}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
