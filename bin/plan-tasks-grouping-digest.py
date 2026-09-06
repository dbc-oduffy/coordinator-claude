"""plan-tasks-grouping-digest.py — CLI trampoline over claude-klabauter's
coordinator_core.ops.plan_tasks_grouping_digest.

Prints the `sha256:<hex>` membership digest for a plan `## Tasks` task-spine
grouping (every member of `schema_validate._PLAN_TASKS_GROUPING_ORDER` —
`do`/`spun_off`/`defer`/`ruled_out`), computed over the membership a
prospective close (`--cut`) would produce — the value a PM approving a cut
records as `digest` in that grouping's `grouping_approvals` block. Read-only:
never writes the plan, never takes the file lock. Same "plain local read,
direct import" shape as append-integrator-dispositions.py's trampoline — no
JSON-RPC round-trip needed for an in-process Python caller.

This tool computes a value; it does not grant an approval. It never checks or
asserts `status`/`pm_utterance` — that gate belongs to
`plan_tasks_mutate.py`'s `resolve` verb, checked at write time. Having a
digest is not evidence a cut was approved.

Usage:
  plan-tasks-grouping-digest.py --plan <path> --grouping do|spun_off|defer|ruled_out \\
      [--cut <id>:<disposition>[,<id>:<disposition>...]] [--root <repo-root>]

  Omitting --cut (or passing an empty string) computes the digest over the
  spine's CURRENT membership rather than a prospective one.

Exit codes (parity with the ported module):
  0 — digest printed to stdout.
  1 — validation error (missing spine, unknown grouping/task-id/disposition,
      plan not found, ...).
  2 — usage/transport error (bad args, unresolvable repo root, plan_path
      escapes docs/plans/).
  3 — engine-root resolution / import failure.

Spec backlink: coordinator_core/ops/plan_tasks_grouping_digest.py module docstring.
"""

import os
import sys

EXIT_TRANSPORT_FAILURE = 3


def _import_runner():
    """In-process import, not an RPC invoke — pure local read + compute, same
    rationale as append-integrator-dispositions.py's own trampoline.

    DR-276: routed through `coordinator_core.cli_entry.run_op_main` for
    baseline consistency — this op never writes the plan and never takes the
    file lock (see module docstring), so it declares nothing and this
    conversion changes no observable behavior."""
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main(argv: "list[str] | None" = None) -> int:
    try:
        run_op_main = _import_runner()
    except RuntimeError as exc:
        print(
            f"plan-tasks-grouping-digest.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}",
            file=sys.stderr,
        )
        return EXIT_TRANSPORT_FAILURE
    except ImportError as exc:
        print(
            f"plan-tasks-grouping-digest.py: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        return EXIT_TRANSPORT_FAILURE

    try:
        code = run_op_main("coordinator_core.ops.plan_tasks_grouping_digest", (sys.argv[1:] if argv is None else argv))
    except ImportError as exc:
        print(
            f"plan-tasks-grouping-digest.py: coordinator_core.ops.plan_tasks_grouping_digest "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        return EXIT_TRANSPORT_FAILURE

    return code


if __name__ == "__main__":
    sys.exit(main())
