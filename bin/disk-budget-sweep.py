"""disk-budget-sweep -- run the disk-budget sweep by hand and print the GB freed.

`--dry-run` (default) reports what would be deleted and changes nothing; `--apply` deletes and
writes the sweep log, unbounded unless `--max-wall-s N` caps it; `--ignore-throttle` skips the 6 h
gate on an applied sweep. Hand-run only: nothing schedules it.
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

_HOOK = Path(__file__).resolve().parent.parent / "hooks" / "scripts" / "session-start-disk-budget.py"
_GIB = 1024**3


def _load_hook():
    spec = importlib.util.spec_from_file_location("session_start_disk_budget", str(_HOOK))
    if spec is None or spec.loader is None:
        raise ImportError(str(_HOOK))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="report only (default)")
    mode.add_argument("--apply", action="store_true", help="delete and log")
    ap.add_argument("--ignore-throttle", action="store_true")
    ap.add_argument("--max-wall-s", type=float, default=None, help="hard wall-clock cap in seconds")
    args = ap.parse_args(argv)
    hook = _load_hook()
    kwargs = {}
    if args.max_wall_s is not None:
        kwargs["deadline_s"] = args.max_wall_s
    elif args.apply:
        kwargs["deadline_s"] = None
    record = hook.run_sweep(apply=args.apply, ignore_throttle=args.ignore_throttle, **kwargs)
    if record is None:
        print("throttled: a sweep ran within the throttle window (use --ignore-throttle)")
        return 0
    verb = "freed" if args.apply else "would free"
    print(f"{verb} {record['freed_bytes'] / _GIB:.2f} GB")
    for root, freed in sorted(record["per_root"].items()):
        print(f"  {root}: {freed / _GIB:.2f} GB")
    for line in record["log"]:
        print(f"  note: {line}")
    print("still over budget" if record["still_over"] else "under budget")
    return 0


if __name__ == "__main__":
    sys.exit(main())
