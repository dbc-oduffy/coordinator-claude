"""review-findings-ledger.py — CLI trampoline over claude-klabauter's
coordinator_core.ops.review_findings_ledger.

Replaces append-integrator-dispositions.py (DoE-claude
docs/plans/2026-09-26-retire-review-integrator.md, row M2). A reviewer applies
every finding it logs directly to the reviewed artifact, then runs
`verify --sidecar <own sidecar>` to check its own `## Findings Ledger` block
before returning. `reject` and `targets` are EM-only — a subagent invoking
either is denied by `coordinator_core.bash_guards.block_subagent_findings_reject`
(M3).

Usage:
  review-findings-ledger.py verify --sidecar <path>
  review-findings-ledger.py reject --sidecar <path> --finding <id> --reason "<one line>"
  review-findings-ledger.py targets --add <path> [--add <path> ...] --session-id <id>

Exit codes (parity with the ported module — coordinator_core/ops/review_findings_ledger.py):
  0 — success
  1 — content/evidence error (verify failed, reject refused, ...)
  2 — usage/transport error (bad args, unresolvable repo root)
  3 — engine-root resolution / import failure

Spec backlink: coordinator_core/ops/review_findings_ledger.py module docstring.
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
        print(f"review-findings-ledger.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return EXIT_TRANSPORT_FAILURE
    except ImportError as exc:
        print(
            f"review-findings-ledger.py: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        return EXIT_TRANSPORT_FAILURE

    try:
        code = run_op_main(
            "coordinator_core.ops.review_findings_ledger", (sys.argv[1:] if argv is None else argv)
        )
    except ImportError as exc:
        print(
            f"review-findings-ledger.py: coordinator_core.ops.review_findings_ledger not importable: {exc}",
            file=sys.stderr,
        )
        return EXIT_TRANSPORT_FAILURE

    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
