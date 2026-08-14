# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""scan_unresolved_ubt_records.py — CLI trampoline over claude-klabauter
coordinator_core.ops.scan_unresolved_ubt_records.

Dispatched by the `d-run-ubt-pending-check` directive
(`coordinator_core/workstream_complete/directives_review.py`'s
`build_ubt_pending_check_directive`, a `CONSUMES_MANIFEST` member of
`coordinator_core.workstream_complete`) — until this file existed the
manifest named a script with no `coordinator/bin/` CLI on disk, so the
directive could only ever fail loud (`FileNotFoundError`) if it ever fired;
`workstream_complete.apply`'s module docstring names this exact gap as a
documented, expected residual. This trampoline closes it, mirroring the
`blocked.py`/`classify-dispatch-shape.py` bin/ops split already used for
every other bareword-argv CONSUMES_MANIFEST member.

Usage: scan_unresolved_ubt_records.py --mode pending --since <sha>

Full behavioral spec, argument contract, and exit-code ladder live on the
Claude-klabauter module docstring (`coordinator_core/ops/scan_unresolved_ubt_records.
py`'s `main()`) — this file is a thin argv/exit-code passthrough over that
module's `main()`.

Spec backlink: DoE-claude coordinator/docs/wiki/coordinator-tripwires.md
§ phantom-cli-guard-seam
"""

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402


def _prepare_claude_klabauter_root() -> None:
    """Resolve CLAUDE_KLABAUTER_ROOT and put it on sys.path.

    Reuses cc_invoke's battle-tested CLAUDE_KLABAUTER_ROOT resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it.

    DR-276: the op is run through `coordinator_core.cli_entry.run_op_main`
    rather than by importing and calling its `main` directly, so any paths it
    declares via `declare_write()` become a session scope-touch claim instead
    of landing unclaimed as an orphan at the `scoped_git_commit` sink.
    """
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)


def main() -> None:
    try:
        _prepare_claude_klabauter_root()
    except RuntimeError as exc:
        print(f"scan_unresolved_ubt_records.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(2)

    from coordinator_core.cli_entry import run_op_main

    try:
        code = run_op_main("coordinator_core.ops.scan_unresolved_ubt_records", sys.argv[1:])
    except ImportError as exc:
        print(
            f"scan_unresolved_ubt_records.py: coordinator_core.ops.scan_unresolved_ubt_records "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(code)


if __name__ == "__main__":
    main()
