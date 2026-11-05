"""Coverage scorer: weighted requirement coverage per stage, written to <run>/coverage.json.

Weights must=3, should=2, could=1. Items marked `excluded` are deliberate exclusions and
sit in neither numerator nor denominator. An unlanded stage, a landed stage with no stage
file, or a stage with no in-scope weight reads `coverage: unknown` and never gets a score.
Stdlib only.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_folder  # noqa: E402

WEIGHTS = {"must": 3, "should": 2, "could": 1}
COVERAGE_FILE = "coverage.json"


def score_stage(run, stage, items):
    """Coverage record for one stage over the requirement `items`."""
    rec = {"stage": stage, "coverage": "unknown", "provisional": False, "score": None}
    if not run_folder.is_landed(stage):
        rec["provisional"] = True
        return rec
    if run_folder.read_stage(run, stage) is None:
        return rec
    in_scope = [
        i for i in items
        if i.get("stage") == stage and not i.get("excluded") and i.get("priority") in WEIGHTS
    ]
    total = sum(WEIGHTS[i["priority"]] for i in in_scope)
    if total == 0:
        return rec
    evidenced = run_folder.evidenced_ids(run, stage)
    got = sum(WEIGHTS[i["priority"]] for i in in_scope if i.get("id") in evidenced)
    rec["score"] = got / total
    rec["coverage"] = "complete" if got == total else "partial"
    rec["evidenced_weight"] = got
    rec["in_scope_weight"] = total
    return rec


def score_run(run):
    items = run_folder.read_requirements(run)
    return {"stages": [score_stage(run, s, items) for s in run_folder.stage_ids()]}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Score per-stage requirement coverage for a run folder.")
    ap.add_argument("run", help="run folder")
    args = ap.parse_args(argv)
    result = score_run(args.run)
    run_folder._write_json(Path(args.run) / COVERAGE_FILE, result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
