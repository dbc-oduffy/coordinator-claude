"""render-ceremony-receipt.py — render a ceremony receipt's op_tail for a human.

Purpose: `op_tail` (coordinator_core/ops/ceremony/receipt_schema.py) carries an
`unknown[]` partition — a step that could not determine its own outcome — but
the receipt is JSON on disk at state/ceremony/<ceremony>-receipt.json and
nothing renders it for a human. A step that reports `unknown` is legible to
code and invisible to the operator, which restates the original defect one
layer up. This CLI closes that gap: it reads one receipt file and prints its
op_tail partitions, with `unknown` visually distinct from `acted`/`skipped`/
`failed`/`failed_critical` — never collapsed into a total, never silently
omitted when empty-vs-absent differ.

`unknown` is legible indeterminacy, not failure: it never influences this
CLI's exit code and is never styled as an error.

A missing or unreadable receipt refuses loudly — exits non-zero and names
what could not be read — rather than rendering an empty summary. Silent
"I read nothing, nothing is wrong" is the exact defect class this workstream
has already found three times elsewhere (os.walk yielding nothing without
raising); this CLI does not add a fourth instance.

Usage:
    render-ceremony-receipt.py <path-to-receipt.json>

Exit 0: the receipt was read and rendered (regardless of what op_tail
  contains — `unknown` entries never affect this).
Exit 1: the receipt path does not exist, is not a file, could not be read,
  or does not parse as JSON. The stderr message names the path and the
  specific failure.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_THIS_DIR))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from coordinator_core.ops.ceremony.receipt_render import render_receipt_summary  # noqa: E402


def _load_receipt(path: str) -> tuple[dict | None, str | None]:
    """Return (receipt, error). Exactly one is None.

    Never raises — every failure mode (missing path, directory, unreadable,
    malformed JSON, non-dict JSON) is converted to a named error string so
    the caller can refuse loudly instead of rendering an empty summary.
    """
    if not os.path.exists(path):
        return None, f"receipt not found: {path}"
    if not os.path.isfile(path):
        return None, f"receipt path is not a file: {path}"
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = fh.read()
    except OSError as exc:
        return None, f"receipt unreadable: {path} ({exc})"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f"receipt is not valid JSON: {path} ({exc})"
    if not isinstance(data, dict):
        return None, f"receipt JSON is not an object: {path} (got {type(data).__name__})"
    return data, None


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Render a ceremony receipt's op_tail for a human, with unknown[] "
        "visually distinct from acted/skipped/failed/failed_critical.",
    )
    parser.add_argument("receipt_path", help="path to a <ceremony>-receipt.json file")
    args = parser.parse_args(argv[1:])

    receipt, error = _load_receipt(args.receipt_path)
    if error is not None:
        print(f"render-ceremony-receipt.py: {error}", file=sys.stderr)
        return 1

    print(render_receipt_summary(receipt))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
