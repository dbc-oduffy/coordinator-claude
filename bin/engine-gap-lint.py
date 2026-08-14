"""engine-gap-lint — lint `<!-- engine-gap: ... -->` markers against the joint grammar.

Purpose: gives `coordinator_core.fact_contract_gate.engine_gap_lint` an
invocable surface runnable from the PEER REPO (the doctrine/ceremony
plane) against ITS OWN tree — the exact gap that let 25 markers drift into
six `producer=` spellings, none checkable until after the fact (see
`coordinator_core/fact_contract_gate/engine_gap_lint.py` module docstring).
Reuses `engine_gap_marker.parse_markers` for the base grammar and layers the
`producer=` form check on top — it never re-implements the parser.

Usage (from THIS repo or, once forwarded, from any repo with the engine
installed):
    engine-gap-lint <file-or-dir> [<file-or-dir> ...]

Exit codes:
    0   every `engine-gap:` marker found is well-formed (including zero
        markers found).
    1   at least one marker is malformed — one line per finding printed to
        stdout, naming the exact expected form and the offending value.
    2   ERROR — no path given, or a given path does not exist.

Spec backlink: cross-repo grammar agreement, peer-repo EM, 2026-08-14
Spec backlink: coordinator_core/fact_contract_gate/engine_gap_lint.py
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
import cc_invoke  # noqa: E402

cc_invoke.ensure_engine_on_path(__file__)

from coordinator_core.fact_contract_gate.engine_gap_lint import lint_paths  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="engine-gap-lint",
        description="Lint engine-gap markers against the joint grammar.",
    )
    p.add_argument("paths", nargs="+", help="file(s) and/or directory(ies) to scan")
    return p


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    args = _build_parser().parse_args(argv)

    resolved: list[Path] = []
    for raw in args.paths:
        p = Path(raw)
        if not p.exists():
            print(f"engine-gap-lint: no such file or directory: {raw}", file=sys.stderr)
            return 2
        resolved.append(p)

    findings = lint_paths(resolved)
    bad = [f for f in findings if not f.ok]
    for f in findings:
        if f.ok:
            continue
        print(f"{f.path}:{f.line_no}: MALFORMED — {f.reason}")

    if bad:
        print(
            f"engine-gap-lint: {len(bad)} malformed marker(s) of {len(findings)} found",
            file=sys.stderr,
        )
        return 1

    print(f"engine-gap-lint: {len(findings)} marker(s) checked, all well-formed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
