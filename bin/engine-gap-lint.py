from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="engine-gap-lint",
        description="Lint engine-gap markers against the joint grammar.",
    )
    p.add_argument("paths", nargs="+", help="file(s) and/or directory(ies) to scan")
    return p


def main(argv: list[str] | None = None) -> int:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    import cc_invoke

    cc_invoke.ensure_engine_on_path(__file__)

    from coordinator_core.fact_contract_gate.engine_gap_lint import lint_paths

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
