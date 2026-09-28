"""review-stamp.py — CLI trampoline over claude-klabauter's coordinator_core.ops.review_stamp.

DoE-claude docs/plans/2026-09-27-review-inside-execute-plan.md, row MK1. Binds a
plan to the terminal commit its execute-review wave verified, and refuses to
mint the stamp on any of: a FAIL delivery verdict, a failed/missing build-test
record, an unresolved finding, a confinement violation, a foreign claim, or
zero product files.

Usage:
  review-stamp.py mint --plan <path> --build-test <sidecar path> [--repo-root <path>]
  review-stamp.py check --plan <path> [--supersession] [--repo-root <path>]
  review-stamp.py product-files --diff <path>

Exit codes (parity with the ported module — coordinator_core/ops/review_stamp.py):
  0 — success
  1 — content/refusal error (mint refused, check found a refusal reason)
  2 — usage/transport error (bad args, unresolvable repo root)
  3 — engine-root resolution / import failure

Spec backlink: coordinator_core/ops/review_stamp.py module docstring.
"""

import sys

EXIT_TRANSPORT_FAILURE = 3


def _import_runner():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main(argv: "list[str] | None" = None) -> int:
    try:
        run_op_main = _import_runner()
    except RuntimeError as exc:
        print(f"review-stamp.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return EXIT_TRANSPORT_FAILURE
    except ImportError as exc:
        print(
            f"review-stamp.py: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        return EXIT_TRANSPORT_FAILURE

    try:
        code = run_op_main(
            "coordinator_core.ops.review_stamp", (sys.argv[1:] if argv is None else argv)
        )
    except ImportError as exc:
        print(
            f"review-stamp.py: coordinator_core.ops.review_stamp not importable: {exc}",
            file=sys.stderr,
        )
        return EXIT_TRANSPORT_FAILURE

    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
