# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.

import os
import sys

_PROG = "verify-parallel-review-lens-orthogonality.py"
_EXIT_TRANSPORT_FAILURE = 2


def _import_main():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.ops.verify_parallel_review_lens_orthogonality import main as _op_main

    return _op_main


def main(argv: "list[str] | None" = None) -> int:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"{_PROG}: engine-root resolution failed: {exc}", file=sys.stderr)
        return _EXIT_TRANSPORT_FAILURE
    except ImportError as exc:
        print(
            f"{_PROG}: coordinator_core.ops.verify_parallel_review_lens_orthogonality not importable: {exc}",
            file=sys.stderr,
        )
        return _EXIT_TRANSPORT_FAILURE

    return op_main((sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    sys.exit(main())
