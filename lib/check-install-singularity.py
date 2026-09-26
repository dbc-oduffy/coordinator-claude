#       (PORTER-BRIEF-ADDENDUM rule 3b; review-integrator F4,
#       2026-07-17 BIG_PORT Wave B review).
#   (BIG_PORT Wave B, item check-install-singularity)
from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin", "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402


def _import_main():
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.install.check_install_singularity import main as _op_main

    return _op_main


def main() -> None:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"check-install-singularity: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(3)
    except ImportError as exc:
        print(
            f"check-install-singularity: coordinator_core.install.check_install_singularity "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(3)

    sys.exit(op_main(sys.argv[1:]))


if __name__ == "__main__":
    main()
