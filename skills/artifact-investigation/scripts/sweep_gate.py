"""Sweep gate: blocks the next artifact-investigation stage until the current one is clean.

Usage: python sweep_gate.py <run> <stage>

Landed stage: exit 0 only when its stage file exists, no claim lacks a
source_link, and every non-excluded `must` requirement of the stage is
evidenced; otherwise exit 1. Unlanded stage: exit 0 with a provisional
`coverage: unknown` entry (skipped, never covered). Each run writes the
stage's entry into <run>/sweep.json under `stages`, keeping other stages' entries.
Stdlib only.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_folder  # noqa: E402

SWEEP_FILE = "sweep.json"


def sweep_stage(run, stage):
    """Gate entry for `stage`: {stage, status, blockers[, coverage, provisional]}."""
    if not run_folder.is_landed(stage):
        return {
            "stage": stage,
            "status": "skipped",
            "coverage": "unknown",
            "provisional": True,
            "blockers": [],
        }

    blockers = []
    data = run_folder.read_stage(run, stage)
    if data is None:
        blockers.append(
            {"kind": "stage-file-missing", "file": run_folder.stage_file(run, stage).name}
        )
    else:
        for idx, claim in enumerate(run_folder.stage_claims(run, stage)):
            if not run_folder.has_source_link(claim):
                blockers.append(
                    {"kind": "claim-without-source-link", "index": idx, "claim_id": claim.get("id") if isinstance(claim, dict) else None}
                )
        evidenced = run_folder.evidenced_ids(run, stage)
        for item in run_folder.read_requirements(run):
            if (
                item.get("stage") == stage
                and item.get("priority") == "must"
                and not item.get("excluded", False)
                and item.get("id") not in evidenced
            ):
                blockers.append({"kind": "must-item-unevidenced", "requirement_id": item.get("id")})

    return {"stage": stage, "status": "blocked" if blockers else "clean", "blockers": blockers}


def _record(run, entry):
    path = Path(run) / SWEEP_FILE
    doc = {}
    if path.is_file():
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            doc = {}
    stages = doc.get("stages")
    if not isinstance(stages, dict):
        stages = {}
    stages[entry["stage"]] = entry
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"stages": stages}, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Sweep gate for one stage of a run folder.")
    parser.add_argument("run", help="run folder")
    parser.add_argument("stage", help="stage id from the run_folder registry")
    args = parser.parse_args(argv)

    try:
        entry = sweep_stage(args.run, args.stage)
    except ValueError as exc:
        print(f"sweep_gate: {exc}", file=sys.stderr)
        return 2
    _record(args.run, entry)
    if entry["status"] == "blocked":
        for b in entry["blockers"]:
            print(f"BLOCKED {args.stage}: {json.dumps(b, sort_keys=True)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
