# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
check-version-consistency.py — CLI trampoline over claude-klabauter
coordinator_core.ops.check_version_consistency.

Assert the coordinator-claude version surfaces agree: plugin.json .version ==
marketplace.json .metadata.version == latest *released* CHANGELOG `## [X.Y.Z]`
section. SSOT is plugin.json; the mechanical enforcer of
docs/wiki/versioning-convention.md.

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
  check-version-consistency.py [--root <dir>] [--check-tag] [--quiet]
  --root <dir>   bundle root containing .claude-plugin/marketplace.json
                 (default: auto-discover from cwd / git root)
  --check-tag    additionally compare the latest v* git tag (advisory: a
                 mismatch WARNs, does not fail — source_is_live repos never tag)
  --quiet        suppress the OK line (failures always print)

Exit: 0 = all surfaces agree; 1 = mismatch (or a required surface missing/
unparseable — fail-loud, this is a gate); 2 = unrecognised CLI argument.

Port of: coordinator/bin/check-version-consistency.py (DoE-claude)
Port backlink: docs/plans/2026-07-16-bash-clean-slate-residual-migration.md
"""

from __future__ import annotations

import os
import sys


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
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main(argv: "list[str] | None" = None) -> int:
    try:
        run_op_main = _import_runner()
    except RuntimeError as exc:
        print(f"check-version-consistency: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return 1
    except ImportError as exc:
        print(
            f"check-version-consistency: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        return 1

    try:
        code = run_op_main("coordinator_core.ops.check_version_consistency", (sys.argv[1:] if argv is None else argv))
    except ImportError as exc:
        print(
            f"check-version-consistency: coordinator_core.ops.check_version_consistency not importable: {exc}",
            file=sys.stderr,
        )
        return 1

    return code


if __name__ == "__main__":
    sys.exit(main())
