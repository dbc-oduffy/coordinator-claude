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
    from coordinator_core.distill.log_normalize import (
        AlreadyCanonicalError,
        NotLegacyShapedError,
        normalize_log,
    )

    parser = argparse.ArgumentParser(
        description="One-time migration of a legacy pipe-table distillation log to C1 canonical shape."
    )
    parser.add_argument("--log-path", required=True, help="Path to the legacy-shaped log file.")
    args = parser.parse_args(argv)

    log_path = Path(args.log_path)

    try:
        result = normalize_log(log_path)
    except AlreadyCanonicalError as exc:
        json.dump({"error": str(exc)}, sys.stdout)
        sys.stdout.write("\n")
        return 2
    except (FileNotFoundError, NotLegacyShapedError, FileExistsError) as exc:
        json.dump({"error": str(exc)}, sys.stdout)
        sys.stdout.write("\n")
        return 1

    json.dump(result.to_dict(), sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
