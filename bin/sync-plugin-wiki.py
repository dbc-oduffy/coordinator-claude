# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""sync-plugin-wiki.py — CLI trampoline over claude-klabauter coordinator_core.ops.sync_plugin_wiki.

Validates the plugin-doctrine wiki single-tree invariant: grep-discovers
`docs/wiki/` citations across plugin files and checks that no dev-side mirror
exists at `~/.claude/docs/wiki/<name>.md`. Part of the DoE-owns-contract /
Claude-klabauter-owns-engine split (DR-047) — this file is the thin CLI shim, the
validation logic lives in coordinator_core.
"""
from __future__ import annotations
# sync-plugin-wiki.py — CLI trampoline over claude-klabauter coordinator_core.ops.sync_plugin_wiki.
#
# Finish-strangler port (bash-to-naked-python clean-slate migration): the bash
# implementation (plugin-doctrine wiki single-tree-invariant validator — grep-discovers
# docs/wiki/ citations across plugin files, checks no dev-side mirror exists at
# ~/.claude/docs/wiki/<name>.md) has been fully ported to
# coordinator_core/ops/sync_plugin_wiki.py, with parity tests in
# coordinator_core/ops/test_sync_plugin_wiki.py. This file is now a thin DoE-side
# (contract) trampoline over that claude-klabauter (engine) module, per DR-047 (DoE owns
# contract/generator, claude-klabauter owns engine).
#
# Shebang note: the SHEBANG line above is `#!/usr/bin/env python3`, generator-
# owned by `gen-launcher-shim.py --ensure-unix`, and correct for this shape. On
# Windows, this file's co-located `.cmd` twin wins via `PATHEXT` when invoked
# as a bareword, so the shebang is never read there; on macOS/Linux `python3`
# is the right interpreter. Caution: callers must invoke via the extensionless
# name or a resolved-interpreter prefix, never a bareword `.py` through git-
# bash — git-bash DOES honor the shebang and would exec-127 with no `python3`
# present. See the carve-out in DoE-claude's coordinator/docs/wiki/bash-on-
# windows-gotchas.md § Carve-out (cross-repo — this wiki lives in the
# DoE-claude repo, not here).
#
# Exit codes (preserved from the bash oracle): 0 clean, 1 PLUGIN_ROOT unresolvable
# (fail-loud — this is a doctrine-integrity gate, not a best-effort nudge), 2 usage
# error (unknown flag), 5 dev-side mirror detected (single-tree invariant broken).
#
# Spec backlink: DoE-claude:pln-bash-polyglot-clean-slate-full-5c71ee

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402


def _import_runner():
    """Resolve the engine root, put it on sys.path, and import `run_op_main`.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it — this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.

    DR-276: routed through `coordinator_core.cli_entry.run_op_main` rather
    than importing the op's `main` directly, so any paths it declares become
    a session scope-touch claim instead of an unclaimed orphan at the
    `scoped_git_commit` sink.
    """
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main() -> None:
    try:
        run_op_main = _import_runner()
    except RuntimeError as exc:
        print(f"sync-plugin-wiki.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(1)
    except ImportError as exc:
        print(
            f"sync-plugin-wiki.py: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        code = run_op_main("coordinator_core.ops.sync_plugin_wiki", sys.argv[1:])
    except ImportError as exc:
        print(
            f"sync-plugin-wiki.py: coordinator_core.ops.sync_plugin_wiki not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    sys.exit(code)


if __name__ == "__main__":
    main()
