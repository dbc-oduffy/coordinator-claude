#!/usr/bin/env python3
"""approvability-calibration — join judgment records against their plans' close-out truth.

WHY THIS EXISTS. C1/C2 of this workstream give the Group EM a rubric and a judgment-record
schema for delegated approve-for-execution; the rubric's own threshold is authored with a
`threshold_provenance` note admitting it is UNVALIDATED, chosen at the strict end per the gem-01
corpus's imprecise-signal rule, "to be revisited once D6 has closed records." This CLI is that
revisit instrument: it walks every judgment record written under
`state/review-trail/approvability/`, resolves the plan it judged, and compares the record's
`verdict` (the PREDICTION, made before the work) against that plan's `exit_criterion_met.asserted`
(the ACTUAL close-out truth, known only after). Nothing here writes anything, ever — it is read
instrumentation for a human or a ceremony to look at, not a gate a plan or a dispatch depends on.

WHY "PREDICTED" IS DERIVED FROM `verdict` ALONE, NOT FROM THE SCORES. The judgment schema
(`plan-approvability-judgment.schema.json`, C2) already collapses the four scored dimensions plus
the two mechanical reversibility facts into one `verdict` enum (`approve` | `escalate`) at
authoring time — that collapse IS the prediction. Re-deriving a second "would this have passed"
signal from `scores` here would let a calibration reader disagree with the rubric threshold that
produced `verdict` without ever admitting it, silently drifting from the versioned contract this
instrument exists to calibrate.

WHY ONLY `approve` RECORDS FEED THE FALSE-APPROVAL RATE. An `escalate` record is not a claim that
the plan will meet its exit criterion — it is a refusal to claim either way, deferred to the PM. A
`escalate` verdict cannot be "false" in the sense this rate measures (a rubber-stamp that later
proved wrong), so it is reported per-record for visibility but excluded from the aggregate's
numerator and denominator alike. Only `approve` records are close-out-comparable predictions.

WHY `pending` IS EXCLUDED FROM THE DENOMINATOR RATHER THAN COUNTED AS "NOT YET WRONG". A plan with
no `exit_criterion_met` block at all has not closed — its prediction has not yet been tested
against anything. Counting it toward the rate (in either direction) would let volume of
open-but-not-yet-false-proven approvals dilute a true false-approval signal, exactly the kind of
denominator inflation the D6 "closed records only" instruction (staff-eng finding 14) exists to
prevent. `exit_criterion_met.asserted` is `required` inside that object per `plan.schema.json`, so
its presence (any boolean value) is what "closed" means here — its absence, or the object's own
absence, is what "pending" means.

READ-ONLY, WRITES NOTHING. This CLI opens judgment records and plan frontmatter and prints; it
never stamps a plan, never mutates a record, never touches `execution_authorized_by`. That
authorization path is `review-exec-auth-stamp` (engine-side), entirely separate from this
instrument.

`--json` emits the same rows and aggregate as a single JSON object for machine consumption
(a ceremony step, a future dashboard); the default is a human-readable table on stdout.

Zero third-party runtime dependency beyond PyYAML (already imported elsewhere in this directory,
e.g. `compose-review-wave.py`, `tier-last-run.py`), stdlib otherwise.

PATH RESOLUTION — SESSION REPO, EXPLICIT. `--repo-root` (default: cwd) is the only repo-relative
seam and every path below it is caller-supplied; this module derives no path from its own
`__file__` and needs no engine or plugin-root resolution
(`docs/plans/2026-09-18-doe-holds-no-scripts.md` § Path resolution).

Spec backlink: docs/plans/2026-09-18-doe-holds-no-scripts.md, chunk W3-C2.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

_RECORDS_RELATIVE = Path("state") / "review-trail" / "approvability"


def _repo_root(explicit: Optional[str]) -> Path:
    return Path(explicit).resolve() if explicit else Path.cwd()


def _records_dir(repo_root: Path) -> Path:
    return repo_root / _RECORDS_RELATIVE


def _load_record(path: Path) -> dict[str, Any]:
    """Parse one judgment record JSON file. Raises `ValueError` naming the defect on failure."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"{path} did not parse to a JSON object")
    return parsed


def _load_plan_frontmatter(plan_path: Path) -> dict[str, Any]:
    """Parse a plan markdown file's YAML frontmatter and return the parsed mapping.

    Raises `ValueError` (with a human-readable message) on a missing file, missing/malformed
    frontmatter delimiters, or a YAML document that is not a mapping.
    """
    try:
        text = plan_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read plan {plan_path}: {exc}") from exc

    if not text.startswith("---"):
        raise ValueError(f"{plan_path} has no YAML frontmatter (expected leading '---')")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"{plan_path} frontmatter is not closed with a second '---'")

    try:
        import yaml
    except ImportError:  # pragma: no cover - environment defect, not a code path under test
        raise ValueError("PyYAML is not installed; cannot parse plan frontmatter")

    try:
        parsed = yaml.safe_load(parts[1])
    except yaml.YAMLError as exc:
        raise ValueError(f"{plan_path} frontmatter is not valid YAML: {exc}") from exc

    if not isinstance(parsed, dict):
        raise ValueError(f"{plan_path} frontmatter did not parse to a mapping")
    return parsed


def _resolve_plan_path(repo_root: Path, plan_path: str) -> Path:
    candidate = Path(plan_path)
    return candidate if candidate.is_absolute() else repo_root / candidate


def _row_for_record(repo_root: Path, record_path: Path) -> dict[str, Any]:
    """Build one calibration row for a single judgment record.

    `status` is one of: `correct`, `false_approval`, `pending`, `escalate`. Only `correct` and
    `false_approval` (both require verdict == "approve" AND a closed plan) feed the aggregate
    false-approval rate; `pending` (no close-out yet) and `escalate` (no prediction to score) are
    reported per-row but excluded from it.
    """
    record = _load_record(record_path)
    verdict = record.get("verdict")
    plan_path_field = record.get("plan_path")

    row: dict[str, Any] = {
        "record_path": str(record_path),
        "plan_path": plan_path_field,
        "verdict": verdict,
        "predicted": True if verdict == "approve" else None,
        "actual": None,
        "falsifier_verdict": None,
        "status": None,
    }

    if not plan_path_field:
        row["status"] = "pending"
        return row

    plan_path = _resolve_plan_path(repo_root, plan_path_field)
    try:
        frontmatter = _load_plan_frontmatter(plan_path)
    except ValueError:
        row["status"] = "pending"
        return row

    exit_criterion_met = frontmatter.get("exit_criterion_met")
    if not isinstance(exit_criterion_met, dict) or "asserted" not in exit_criterion_met:
        row["status"] = "pending"
        return row

    actual = exit_criterion_met.get("asserted")
    row["actual"] = actual
    row["falsifier_verdict"] = exit_criterion_met.get("falsifier_verdict")

    if verdict != "approve":
        row["status"] = "escalate"
        return row

    row["status"] = "correct" if actual is True else "false_approval"
    return row


def _collect_rows(repo_root: Path) -> list[dict[str, Any]]:
    records_dir = _records_dir(repo_root)
    if not records_dir.is_dir():
        return []
    rows = []
    for record_path in sorted(records_dir.glob("*.json")):
        rows.append(_row_for_record(repo_root, record_path))
    return rows


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    closed_approve = [r for r in rows if r["status"] in ("correct", "false_approval")]
    false_approvals = [r for r in closed_approve if r["status"] == "false_approval"]
    denominator = len(closed_approve)
    rate = (len(false_approvals) / denominator) if denominator else None
    return {
        "closed_approve_count": denominator,
        "false_approval_count": len(false_approvals),
        "false_approval_rate": rate,
        "pending_count": len([r for r in rows if r["status"] == "pending"]),
        "escalate_count": len([r for r in rows if r["status"] == "escalate"]),
    }


def _print_table(rows: list[dict[str, Any]], aggregate: dict[str, Any]) -> None:
    if not rows:
        print("no approvability judgment records found")
    else:
        header = f"{'record':<40} {'verdict':<10} {'predicted':<10} {'actual':<8} {'status':<15}"
        print(header)
        print("-" * len(header))
        for row in rows:
            print(
                f"{Path(row['record_path']).name:<40} "
                f"{str(row['verdict']):<10} "
                f"{str(row['predicted']):<10} "
                f"{str(row['actual']):<8} "
                f"{str(row['status']):<15}"
            )
    print()
    rate = aggregate["false_approval_rate"]
    rate_display = f"{rate:.3f}" if rate is not None else "n/a (no closed approve records)"
    print(f"closed approve records: {aggregate['closed_approve_count']}")
    print(f"false approvals: {aggregate['false_approval_count']}")
    print(f"false-approval rate: {rate_display}")
    print(f"pending: {aggregate['pending_count']}")
    print(f"escalate (not scored): {aggregate['escalate_count']}")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--repo-root", default=None, help="repo root (default: cwd)")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args(argv)

    repo_root = _repo_root(args.repo_root)
    rows = _collect_rows(repo_root)
    aggregate = _aggregate(rows)

    if args.json:
        print(json.dumps({"rows": rows, "aggregate": aggregate}, indent=2, sort_keys=True))
    else:
        _print_table(rows, aggregate)
    return 0


if __name__ == "__main__":
    sys.exit(main())
