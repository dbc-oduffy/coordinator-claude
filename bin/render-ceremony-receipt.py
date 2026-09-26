
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
