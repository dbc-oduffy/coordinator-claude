#!/usr/bin/env python3
"""validate-code-comparison-record.py — schema-conformance + objectivity-spine
check for code-comparison-record YAML fixtures.

Validates a code-comparison-record (per
coordinator/pipelines/deep-research/code-comparison-record-schema.md, DoE-claude doctrine asset)
against: (1) required-field presence, (2) verdict/confidence enum range,
(3) evidence permalink shape (blob/<sha>/path#Lx-Ly), (4) peer_ref present,
(5) competitor_uid ABSENT (negative-spec 1), (6) analysis contains no
recommendation/imperative language (negative-spec — analysis is an
annotation, never a recommendation).

Usage:
  validate-code-comparison-record.py <record.yaml> [<record.yaml> ...]
  (with no path given, falls back to a `code-comparison-sample-record.yaml`
  sibling — a DoE-resident sample fixture this row does not move — which will
  ordinarily read as "record file not found" from here; invoke with explicit
  paths.)

Exit: 0 on all records passing all checks; non-zero (count of violations)
on any violation, with each violation printed to stderr.

Spec backlink: coordinator/pipelines/deep-research/code-comparison-record-schema.md (DoE-claude)
§ Negative Specs — Summary (items 1, 4) and § Field Reference (verdict, confidence).

Arrived from DoE-claude coordinator/pipelines/deep-research/fixtures/validate-code-comparison-record.py
(docs/plans/2026-09-18-doe-holds-no-scripts.md, chunk W3-C7). Path resolution: "engine" class
(§ Path resolution) — `SCRIPT_DIR` is `Path(__file__).resolve().parent`, unchanged in shape,
now resolving to `coordinator/bin/` instead of the DoE pipeline fixtures directory.

Runs the checker (`_validate-code-comparison-record-checker.py`, same directory) IN-PROCESS via a
by-path import, not a subprocess spawn: DoE's copy shelled out to it per record
(`subprocess.run([sys.executable, str(CHECKER_PY), record_path])`), which is an unjustified spawn
now that both land in the same `coordinator/bin/` directory as siblings — no cross-repo or
cross-interpreter boundary to cross, and the warm door's "no invocation tax" hard constraint
gives no room for a spawn with no remaining justification. `check_record()` is called directly;
the exit-code semantics (0 on pass, violation count on fail) are preserved exactly.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_FIXTURE = SCRIPT_DIR / "code-comparison-sample-record.yaml"
CHECKER_PATH = SCRIPT_DIR / "_validate-code-comparison-record-checker.py"


def _load_checker_module():
    """Import `_validate-code-comparison-record-checker.py` (same directory) by file path.

    Hyphenated, underscore-prefixed filename, so `import _validate-code-comparison-record-checker`
    is not valid Python — same by-path-sibling idiom as `corpus-currency-probe.py`'s
    `_load_tier_last_run_module()`. Raises on failure rather than failing open: an absent or
    broken checker means this CLI cannot validate anything, which `main()` reports as an error
    (mirroring DoE's own "checker script not found" early-exit), not a silent pass.
    """
    spec = importlib.util.spec_from_file_location(
        "_validate_code_comparison_record_checker", CHECKER_PATH
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load checker module spec from {CHECKER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv: list[str]) -> int:
    import yaml

    if not CHECKER_PATH.is_file():
        print(f"ERROR: checker script not found at {CHECKER_PATH}", file=sys.stderr)
        return 1

    try:
        checker = _load_checker_module()
    except Exception as exc:
        print(f"ERROR: failed to load checker module: {exc}", file=sys.stderr)
        return 1

    records = argv if argv else [str(DEFAULT_FIXTURE)]

    total_violations = 0
    any_failed = False

    for record_path in records:
        path = Path(record_path)
        if not path.is_file():
            print(f"ERROR: record file not found: {record_path}", file=sys.stderr)
            total_violations += 1
            any_failed = True
            continue

        print(f"Validating: {record_path}")
        try:
            with path.open("r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f)
        except Exception as exc:
            print(f"  VIOLATION: could not parse YAML: {exc}", file=sys.stderr)
            total_violations += 1
            any_failed = True
            continue

        if isinstance(loaded, list):
            if not loaded:
                print(
                    "  VIOLATION: emit file holds an empty sequence — no records to validate",
                    file=sys.stderr,
                )
                total_violations += 1
                any_failed = True
                continue
            violations = []
            for i, record in enumerate(loaded):
                violations.extend(checker.check_record(record, label=f"record[{i}]"))
        else:
            violations = checker.check_record(loaded)

        if violations:
            for v in violations:
                print(f"  VIOLATION: {v}", file=sys.stderr)
            total_violations += len(violations)
            any_failed = True

    if any_failed:
        print(f"FAIL: {total_violations} violation(s) found.", file=sys.stderr)
        return total_violations

    print("PASS: all records conform to schema and objectivity-spine checks.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
