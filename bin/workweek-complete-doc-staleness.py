# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
coordinator/bin/workweek-complete-doc-staleness.py — CLI trampoline over
coordinator_core.ops.doc_staleness.

Purpose: bareword-invokable entrypoint for the human-facing doc staleness
detector (AC1) — reads the calling repo's declared human-facing docs and
threshold overrides via `coordinator_core.ops.doc_registry.
resolve_doc_registry_config` and prints the resulting
`build_doc_staleness_report` as JSON to stdout. `--root PATH` overrides the
repo root (default: cwd) so the CLI is invocable from any working directory,
matching the `--root` convention used by `check_arch_audit_staleness.py`.

Not registered as an IPC op (`_registry_map.py`/`@register_op`) — this is a
plain `main(argv) -> int` CLI, the same shape `check_arch_audit_staleness.py`
uses (confirmed: neither appears in `OP_MODULE_MAP` nor
`_EAGER_OP_MODULES`). `_registry_map.py`'s own docstring states the map is a
performance optimization over the IPC dispatch path, not a correctness gate,
and every consumer of this op (the workweek-complete brief builder's
`directives[].cli`) names it as a bareword CLI string, never an IPC op name
— registering it there would add a dead entry (no module here calls
`register_op`) for no dispatch path that reads it. See this file's sibling
`workweek-complete-doc-verify.py` for the same reasoning applied identically
(C2: "decide the shape once and apply it to both new ops consistently").

Usage:
    workweek-complete-doc-staleness [--root PATH]

Exits 3 if CLAUDE_KLABAUTER_ROOT cannot be resolved (see stderr); otherwise exits 0.

Spec backlink: DoE-claude DoE-claude:pln-human-facing-doc-staleness-det-d9c047 § C2, AC1
Spec backlink: claude-klabauter coordinator_core/ops/doc_staleness.py

Negative-spec: does NOT compute staleness itself — delegates entirely to
`coordinator_core.ops.doc_staleness.build_doc_staleness_report_from_registry`;
this wrapper is argv parsing + JSON emission only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_LIB_DIR = str(Path(__file__).resolve().parent / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_colocated_engine_on_path  # noqa: E402

try:
    require_colocated_engine_on_path(__file__)
except RuntimeError as _exc:
    print(f"{Path(__file__).name}: CLAUDE_KLABAUTER_ROOT resolution failed: {_exc}", file=sys.stderr)
    sys.exit(3)

from coordinator_core.ops.doc_staleness import (  # noqa: E402
    build_doc_staleness_report_from_registry,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="workweek-complete-doc-staleness",
        description="Human-facing doc staleness report for the calling repo.",
    )
    parser.add_argument(
        "--root",
        default=None,
        help="Repo root to check (default: current working directory).",
    )
    return parser


def main(argv: list[str]) -> int:
    args = _build_parser().parse_args(argv)
    root = args.root or Path.cwd()
    report = build_doc_staleness_report_from_registry(root)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
