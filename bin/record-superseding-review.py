"""record-superseding-review.py -- CLI over review_mint.record_superseding_review.

Writes the stranded-run superseding review record and prints its
repo-root-relative path as the ONLY line on stdout, so
`/workstream-complete`'s `{d-record-superseding-review.entry_path}` token
threads it into `review-stamp mint --superseding-record`.

Usage:
  record-superseding-review.py --plan <plan-path|plan_id> --session-id <sid> --base <sha> --head <sha>
      [--wave-sidecar <path> ...] [--prep-sidecar <path>]
      [--stage-returns-json <json>] [--supersedes <sha>] [--repo-root <path>]

Exit codes:
  0 -- record written; its path is the only stdout line
  1 -- the op refused (reason on stderr), nothing written
  2 -- usage error, or engine import failure
"""
from __future__ import annotations

import sys


def main(argv: "list[str] | None" = None) -> int:
    try:
        import lib  # noqa: F401 -- bootstraps coordinator/bin/lib onto sys.path
        from cc_invoke import require_dispatch_engine_on_path

        require_dispatch_engine_on_path()
        from coordinator_core.cli_entry import run_op_main
    except (RuntimeError, ImportError) as exc:
        print(f"record-superseding-review.py: engine unreachable: {exc}", file=sys.stderr)
        return 2
    return run_op_main(
        "coordinator_core.ops.review_mint.supersede", sys.argv[1:] if argv is None else argv
    )


if __name__ == "__main__":
    sys.exit(main())
