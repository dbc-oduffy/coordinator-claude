# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
coordinator-setup-state.py — CLI trampoline over claude-klabauter
coordinator_core.ops.coordinator_setup_state.

Single writer/reader primitive for the coordinator setup/orientation milestone
receipt at ~/.claude/coordinator-setup-state.yaml. This is a RECEIPT in the
sense of docs/wiki/plugin-identity-and-health-sentinels.md — written by the
actor whose action it witnesses, stale = signal not lie. It is the cross-repo
chaining contract: sibling (branch/leaf) repos read it to confirm coordinator
is bootstrapped before chaining their own setup/orientation after it.

Shebang note: the SHEBANG line above is `#!/usr/bin/env python3`, generator-
owned by `gen-launcher-shim.py --ensure-unix`, and correct for this shape. On
Windows, this file's co-located `.cmd` twin wins via `PATHEXT` when invoked as
a bareword, so the shebang is never read there; on macOS/Linux `python3` is the
right interpreter. Caution: callers must invoke via the extensionless name or a
resolved-interpreter prefix, never a bareword `.py` through git-bash — git-bash
DOES honor the shebang and would exec-127 with no `python3` present. See the
carve-out in DoE-claude's coordinator/docs/wiki/bash-on-windows-gotchas.md §
Carve-out (cross-repo — this wiki lives in the DoE-claude repo, not
here).

Usage:
  coordinator-setup-state.py record <milestone>   # set <milestone>_at if unset (atomic)
  coordinator-setup-state.py check  <milestone>    # exit 0 if recorded, 1 if not
  coordinator-setup-state.py status                # print the receipt (or note absence)
  coordinator-setup-state.py auto-record-if-source-is-live
                                                    # silent self-heal, always exits 0

  milestone in { setup_concluded | orientation_started | orientation_completed }

Environment: CLAUDE_HOME (defaults to $HOME/.claude) selects the install root.

Exit-convention note: this is a fail-loud config-writer/gate script (matching
its own pre-port usage-exits-2 convention), NOT a never-block hook shape like
coordinator-auto-push — a claude-klabauter-link failure here exits 2, mirroring the
oracle's own usage() exit code for malformed invocations, rather than
swallowing to 0.

Spec backlink: docs/wiki/coordinator-setup-state-receipt.md
Port of: coordinator/bin/coordinator-setup-state.py (bash body retired on
         cutover; see git log)
Port backlink: docs/plans/2026-07-16-bash-clean-slate-residual-migration.md
"""

from __future__ import annotations

import os
import sys


def _import_runner():
    """Resolve the engine root, put it on sys.path, and import the shared in-process
    runner.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it — this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.

    DR-276: the op is run through `coordinator_core.cli_entry.run_op_main`
    rather than by importing and calling its `main` directly, so the receipt
    write it declares becomes a session scope-touch claim. Without that, the
    receipt this milestone writer produces is an orphan at the
    `scoped_git_commit` sink.
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
        print(f"coordinator-setup-state.py: engine-root resolution failed: {exc}", file=sys.stderr)
        return 2
    except ImportError as exc:
        print(
            f"coordinator-setup-state.py: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        return 2

    try:
        code = run_op_main("coordinator_core.ops.coordinator_setup_state", (sys.argv[1:] if argv is None else argv))
    except ImportError as exc:
        print(
            f"coordinator-setup-state.py: coordinator_core.ops.coordinator_setup_state not importable: {exc}",
            file=sys.stderr,
        )
        return 2

    return code


if __name__ == "__main__":
    sys.exit(main())
