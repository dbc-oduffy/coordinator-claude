"""
assert-plan-sizing-citation.py — CLI trampoline over the engine repo's
coordinator_core.ops.assert_plan_sizing_citation.

AC4 gate for the plan sizing-citation gate: asserts zero dangling
`sizing_object:` frontmatter citations across `docs/plans/*.md`. Reads
ONLY the parsed frontmatter mapping for each plan — never the body text
(AC6, the load-bearing negative: a plan may legitimately cite a
nonexistent sizing object in BODY prose to document that it was never
written; a text-scanning check would make that plan unwriteable). No
`--fix` mode — unlike the analogous plan-backlinks gate there is no
move-map to repoint a dangling citation against.

No shebang, matching the current `coordinator/bin/*.py` convention —
invoke via `python3 coordinator/bin/assert-plan-sizing-citation.py` on
macOS/Linux; the co-located `.cmd` twin is the Windows entrypoint.

Exit convention: this is a fail-loud GATE script (asserts zero dangling
sizing_object citations), NOT a never-block hook like coordinator-auto-push —
an engine-link failure (CLAUDE_KLABAUTER_ROOT unresolved, module not importable) exits 1
here, not 0, so the failure is visible rather than silently swallowed.

Spec backlink: pln-plan-sizing-citation-gate-scaf-45eaed § C3 / AC4 / AC6
"""

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402


def _import_runner():
    """Resolve CLAUDE_KLABAUTER_ROOT, put it on sys.path, and import the DR-276 in-process
    runner.

    Reuses cc_invoke's battle-tested CLAUDE_KLABAUTER_ROOT resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it -- this is a plain in-process import, not an RPC invoke.

    DR-276: routed through `coordinator_core.cli_entry.run_op_main` rather than
    calling the op's `main` directly, so this op's declared writes (none, in
    practice -- this gate is read-only) become a session scope-touch claim
    instead of an orphan at the `scoped_git_commit` sink.
    """
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main() -> None:
    try:
        run_op_main = _import_runner()
    except RuntimeError as exc:
        print(
            f"assert-plan-sizing-citation.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)
    except ImportError as exc:
        print(
            f"assert-plan-sizing-citation.py: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        code = run_op_main("coordinator_core.ops.assert_plan_sizing_citation", sys.argv[1:])
    except ImportError as exc:
        print(
            "assert-plan-sizing-citation.py: "
            f"coordinator_core.ops.assert_plan_sizing_citation not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    sys.exit(code)


if __name__ == "__main__":
    main()
