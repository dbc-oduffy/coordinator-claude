# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

def _bootstrap_engine() -> None:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_colocated_engine_on_path

    try:
        require_colocated_engine_on_path(__file__)
    except RuntimeError as _exc:
        print(f"{Path(__file__).name}: engine-root resolution failed: {_exc}", file=sys.stderr)
        sys.exit(1)


def main(argv: list[str] | None = None) -> int:
    _bootstrap_engine()
    from coordinator_core.distill.ripe_filter import scan_spec_dir

    parser = argparse.ArgumentParser(
        description="Scan a spec directory's frontmatter and partition into harvest-ripe vs skip."
    )
    parser.add_argument("spec_dir", type=str, help="Path to the spec directory to scan.")
    args = parser.parse_args(argv)

    spec_dir = Path(args.spec_dir)
    if not spec_dir.is_dir():
        print(f"error: not a directory: {spec_dir}", file=sys.stderr)
        return 1

    result = scan_spec_dir(spec_dir)
    json.dump(result.to_dict(), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
