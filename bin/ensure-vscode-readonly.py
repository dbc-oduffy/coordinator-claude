# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
ensure-vscode-readonly — CLI trampoline over claude-klabauter
coordinator_core.ops.ensure_vscode_readonly.

Idempotently, additively merges `files.readonlyInclude` globs for the two
generated handoff-tracker renders into a repo's `.vscode/settings.json` — the
EDITOR-side guard (layer 1) complementing the AGENT-side `block-tracker-edit.sh`
PreToolUse hook (layer 2). See docs/wiki/handoff-tracker-system.md and
docs/wiki/coordinator-tripwires.md § BLOCK-TRACKER-EDIT.

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

Usage: ensure-vscode-readonly [--root <repo-root>]   (default: cwd)
Exit codes: 0 — merged/created/idempotent/skipped-loudly; 2 — bad CLI usage.
Called from repo-setup (Phase 3f.6) at project onboarding time — not a hot path.

Spec backlink: docs/plans/2026-05-29-handoff-tracker-system.md (edit-resistance follow-up)
Port backlink: docs/plans/2026-07-16-bash-clean-slate-residual-migration.md
Port of: coordinator/bin/ensure-vscode-readonly.sh (894d4bc6, 2026-07-22)
"""

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402


def _import_runner():
    """Resolve the engine root, put it on sys.path, and import the runner.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it — this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.

    DR-276: the op is run through `coordinator_core.cli_entry.run_op_main`
    rather than by calling its `main` directly, so the paths it declares become
    a session scope-touch claim. Without that, everything this CLI writes is an
    orphan at the `scoped_git_commit` sink.
    """
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main() -> None:
    try:
        run_op_main = _import_runner()
    except RuntimeError as exc:
        print(f"ensure-vscode-readonly.sh: engine-root resolution failed: {exc}", file=sys.stderr)
        sys.exit(2)
    except ImportError as exc:
        print(
            f"ensure-vscode-readonly.sh: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)

    try:
        code = run_op_main("coordinator_core.ops.ensure_vscode_readonly", sys.argv[1:])
    except ImportError as exc:
        print(
            f"ensure-vscode-readonly.sh: coordinator_core.ops.ensure_vscode_readonly "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(code)


if __name__ == "__main__":
    main()
