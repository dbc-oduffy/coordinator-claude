# this file as `"$PYTHON_BIN" "${PYTHON_ARGS[@]}" ".../lib/discover-working-repos.py"`
# PORTER-BRIEF-ADDENDUM.md § 3b: best-effort/advisory scripts degrade to exit 0).
from __future__ import annotations
import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bin", "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402


def _import_main():
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.ops.discover_working_repos import main as _op_main
    return _op_main


def main() -> None:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"discover-working-repos.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(0)
    except ImportError as exc:
        print(
            f"discover-working-repos.py: coordinator_core.ops.discover_working_repos "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(0)
    sys.exit(op_main(sys.argv[1:]))


if __name__ == "__main__":
    main()
