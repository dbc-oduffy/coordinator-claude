"""append-integrator-dispositions.py — CLI trampoline over claude-klabauter's
coordinator_core.ops.append_integrator_dispositions.

Gives coordinator:review-integrator (DoE-claude coordinator/agents/review-integrator.md)
a single call to perform its ONE sanctioned sidecar write (§ Sidecar Disposition
Annotation) — the bulk `## Integrator Dispositions` block appended to the
reviewer findings sidecar — instead of hand-authoring the YAML block via Edit.
The ported module validates the target is a real, still-open, code-reviewer
findings sidecar under state/subagent-share/ before writing anything; a wrong
target (e.g. the integrator's own run-report sidecar) is refused loudly rather
than silently no-op'd.

Usage:
  append-integrator-dispositions.py --sidecar <path> \\
      [--applied F1,F2] [--escalated-disagree F4] [--escalated-ask F6,F9] \\
      [--escalated-p0 F3] [--deferred F8] [--root <repo-root>] \\
      [--rationale-stdin | --rationale-file <path>]

Rationale prose: prefer --rationale-stdin, or the equivalent --rationale-file -, and
pipe the prose in. A --rationale-file naming a real path is CALLER-CHOSEN, and that
path is shared state on a box running dozens of concurrent sessions: one reusing it
replaces this block's rationale with its own, silently and with a zero exit, leaving
the structured buckets correct and the human-readable explanation belonging to a
different review
(state/bug-backlog/2026-08-31-concurrent-sessions-collide-on-a-shared.yaml).

Exit codes (parity with the ported module — coordinator_core/ops/append_integrator_dispositions.py):
  0 — success (block appended, or already present — idempotent no-op)
  1 — validation error (wrong target, unfilled scaffold, no ids supplied, ...)
  2 — usage/transport error (bad args, both rationale flags, unreadable --rationale-file,
      unresolvable repo root)
  3 — engine-root resolution / import failure

Spec backlink: coordinator_core/ops/append_integrator_dispositions.py module docstring.
"""

import os
import sys

EXIT_TRANSPORT_FAILURE = 3


def _import_runner():
    """In-process import, not an RPC invoke — this is a plain local file
    mutation, same rationale as edit-live-hook.py's own trampoline.

    DR-276: the op is run through `coordinator_core.cli_entry.run_op_main`
    rather than by calling its `main` directly, so the paths it declares become
    a session scope-touch claim. Without that, everything this CLI writes is an
    orphan at the `scoped_git_commit` sink.
    """
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main(argv: "list[str] | None" = None) -> int:
    try:
        run_op_main = _import_runner()
    except RuntimeError as exc:
        print(f"append-integrator-dispositions.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return EXIT_TRANSPORT_FAILURE
    except ImportError as exc:
        print(
            f"append-integrator-dispositions.py: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        return EXIT_TRANSPORT_FAILURE

    try:
        code = run_op_main(
            "coordinator_core.ops.append_integrator_dispositions", (sys.argv[1:] if argv is None else argv)
        )
    except ImportError as exc:
        print(
            f"append-integrator-dispositions.py: coordinator_core.ops.append_integrator_dispositions "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        return EXIT_TRANSPORT_FAILURE

    return code


if __name__ == "__main__":
    sys.exit(main())
