#!/usr/bin/env python3
"""plan-spine-check — validate a plan's `## Tasks` spine against plan-tasks.schema.json.

WHY THIS EXISTS. The schema has been the authoring contract for the task spine since 1.4.0, and
until now nothing ran it. Every consumer validates late and from inside its own job: the dispatch
emitter refuses at emit time, a wave-builder refuses at fire time, and a reviewer catches it only
by hand-validating on their own initiative. So an invalid spine survives authoring, survives
review integration, and surfaces as "this plan produces nothing" at the point where somebody was
trying to execute it.

Measured 2026-09-10, plan-blitz run 20260910T114745Z fire 1, on
`docs/plans/2026-09-02-sanctioned-executor-amendment-channel.md`: a review integrator applying a
BLOCKING finding removed chunk C0 and re-pointed four `depends_on` edges at
`artifact: <path>` + `gate_kind: file-existence`. That shape fails three ways per edge — `chunk`
is required, `file-existence` is not in the closed two-value `gate_kind` enum, and `artifact` is
not an admissible property — and four of the plan's five rows carried it. The integrator wrote it,
the citation-resolution pass did not look, and the readiness gate caught it only because that
particular reviewer chose to run the schema themselves. The other two plans in the same fire
validated clean, so nothing about the wave was systematically broken; the check simply did not
exist to be run.

WHAT IT DOES NOT DO. It does not judge the plan, the wave shape, or whether a declared dependency
is the RIGHT one — only whether each row is a shape the schema admits. It writes nothing. It
resolves no engine op and spawns no subprocess: the fenced-block locator is this engine's own
(`coordinator_core.frontmatter.body_blocks`, imported, never re-transcribed), and validation is
`jsonschema` over bytes already on disk.

A plan carrying NO `## Tasks` spine is reported `NO-SPINE` and is not a failure. Plenty of plans
legitimately carry none, and conflating "absent" with "invalid" is how a checker gets ignored.

TWO CLASSES, BECAUSE THE CORPUS CARRIES TOLERATED VINTAGE AND THE SCHEMA SAYS SO. An unadmitted
property, a wrong type, a closed-enum violation, a missing required key on an edge is STRUCTURAL
and fails; a retired `change_kind` value or an absent legacy conditional key the schema's own
`x-bump-note` says is deliberately NOT retro-opened is LEGACY and does not.

Arrived from DoE-claude coordinator/bin/plan-spine-check.py (docs/plans/2026-09-18-doe-holds-no-
scripts.md, chunk W2-C9). Requirement-restated, not carried verbatim: the DoE-side `_locate_spine`
resolved `coordinator_core` through an `_engine_root` seam because that copy lived outside the
engine; this copy lives inside it, so the locator and the schema resolve through this module's own
tree (§ Path resolution, "engine" class) with no seam at all.

Spec backlink: docs/plans/2026-09-18-doe-holds-no-scripts.md, chunk W2-C9.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

#: "engine" class per § Path resolution — this module lives inside the engine checkout, so its
#: own tree IS the engine root. `coordinator/bin/plan-spine-check.py`.parents[2] is the repo root.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCHEMA = _REPO_ROOT / "coordinator_core" / "frontmatter" / "schemas" / "plan-tasks.schema.json"

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_UNREADABLE = 2

#: Findings the schema itself declares tolerated on the existing corpus -- reported, never fatal.
#: Both families are quoted in this module's docstring from `plan-tasks.schema.json`'s own
#: `x-bump-note`. Widening this set silences real defects, so it is a closed list, not a pattern.
_LEGACY_CONDITIONAL_KEYS = ("pm_approved", "case_against", "disposition_ref", "disposition_detail")


#: jsonschema echoes the offending INSTANCE into some messages -- a `not` violation on a task row
#: reproduces the whole row, bodies and all, which on this corpus is thousands of characters of
#: unreadable output for a one-line defect. Truncate at the point the message stops being about
#: the schema and starts being about the data the reader already has open.
_MESSAGE_CAP = 160


def _trim(message: str) -> str:
    collapsed = " ".join(message.split())
    if len(collapsed) <= _MESSAGE_CAP:
        return collapsed
    return collapsed[:_MESSAGE_CAP].rstrip() + " …"


def _message_for(error) -> str:
    """The schema's complaint, never the instance that triggered it.

    A `not` violation's default message reproduces the whole offending row -- on a plan spine that
    is every chunk body verbatim. The reader has the file open; what they lack is the CONDITION,
    which `validator_value` carries directly.
    """
    if error.validator == "not":
        return f"row must NOT satisfy {error.validator_value} here (a conditional branch forbids it)"
    return error.message


def _is_legacy(at: str, message: str) -> bool:
    if at == "change_kind" and "is not one of" in message:
        return True
    return any(f"'{key}' is a required property" == message for key in _LEGACY_CONDITIONAL_KEYS)


class CheckError(RuntimeError):
    """A precondition this module cannot proceed without, named rather than guessed."""


def _locate_spine(text: str):
    """The `## Tasks` ```yaml plan-tasks block, via the engine's own locator.

    Imported directly: this module lives inside the engine, so the fence rules (heading match,
    info string, blanking of nested fences) resolve through this module's own tree with no seam —
    a second copy here is how the two would drift into disagreeing about what a spine even is.
    """
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    try:
        from coordinator_core.frontmatter.body_blocks import LocateStatus, locate_fenced_block
    except Exception as exc:  # pragma: no cover - import-shape guard
        raise CheckError(f"coordinator_core.frontmatter.body_blocks unimportable: {exc}")

    result = locate_fenced_block(text)
    return result, LocateStatus


def check_plan(path: Path) -> dict:
    """One plan's verdict: PREPPED-shaped report, never a raise for an ordinary outcome."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return {"path": str(path), "verdict": "UNREADABLE", "detail": str(exc), "rows": []}

    result, LocateStatus = _locate_spine(text)
    if result.status is LocateStatus.ABSENT:
        return {"path": str(path), "verdict": "NO-SPINE", "detail": None, "rows": []}
    if result.status is LocateStatus.MALFORMED:
        return {
            "path": str(path),
            "verdict": "MALFORMED",
            "detail": "a `## Tasks` block is present but its fence does not parse",
            "rows": [],
        }

    import yaml

    try:
        rows = yaml.safe_load(result.body)
    except yaml.YAMLError as exc:
        return {"path": str(path), "verdict": "MALFORMED", "detail": f"YAML: {exc}", "rows": []}
    if not isinstance(rows, list):
        return {
            "path": str(path),
            "verdict": "MALFORMED",
            "detail": "the plan-tasks block is not a list of task rows",
            "rows": [],
        }

    import jsonschema

    schema = json.loads(_SCHEMA.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    findings = []
    for index, row in enumerate(rows):
        row_id = (row or {}).get("id") if isinstance(row, dict) else None
        label = row_id or f"row {index + 1} (no id)"
        if not isinstance(row, dict):
            findings.append({"row": label, "error": "not a mapping", "at": ""})
            continue
        for error in sorted(validator.iter_errors(row), key=lambda e: list(e.path)):
            at = "/".join(str(part) for part in error.path)
            findings.append(
                {
                    "row": label,
                    "error": _trim(_message_for(error)),
                    "at": at,
                    "class": "legacy" if _is_legacy(at, error.message) else "structural",
                }
            )
    if any(f["class"] == "structural" for f in findings):
        verdict = "INVALID"
    elif findings:
        verdict = "LEGACY"
    else:
        verdict = "VALID"
    return {"path": str(path), "verdict": verdict, "detail": None, "rows": findings}


def _render(report: dict) -> str:
    name = Path(report["path"]).name
    if report["verdict"] in ("VALID", "NO-SPINE"):
        return f"plan-spine-check: {report['verdict']} — {name}"
    if report["verdict"] == "LEGACY":
        return (
            f"plan-spine-check: LEGACY — {name} ({len(report['rows'])} tolerated finding(s), "
            "no structural defect)"
        )
    lines = [f"plan-spine-check: {report['verdict']} — {name}"]
    if report["detail"]:
        lines.append(f"  {report['detail']}")
    for finding in report["rows"]:
        at = f" at `{finding['at']}`" if finding["at"] else ""
        tag = "" if finding["class"] == "structural" else "  [legacy, not fatal]"
        lines.append(f"  {finding['row']}{at}: {finding['error']}{tag}")
    return "\n".join(lines)


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        prog="plan-spine-check",
        description="Validate a plan's `## Tasks` spine against plan-tasks.schema.json. Writes nothing.",
    )
    parser.add_argument("plans", nargs="+", help="plan file(s)")
    parser.add_argument("--json", action="store_true", help="emit the full report as JSON")
    args = parser.parse_args(argv)

    try:
        reports = [check_plan(Path(p)) for p in args.plans]
    except CheckError as exc:
        print(f"plan-spine-check: {exc}", file=sys.stderr)
        return EXIT_UNREADABLE

    if args.json:
        print(json.dumps({"reports": reports}, indent=2))
    else:
        for report in reports:
            print(_render(report))

    if any(r["verdict"] == "UNREADABLE" for r in reports):
        return EXIT_UNREADABLE
    if any(r["verdict"] in ("INVALID", "MALFORMED") for r in reports):
        return EXIT_INVALID
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
