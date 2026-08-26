# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
audit-enabled-plugins.py — CLI trampoline over claude-klabauter
coordinator_core.ops.audit_enabled_plugins.

Finish-strangler port (DR-047/DR-059): the bash implementation (drift-check this
repo's `.claude/settings.json` enabledPlugins against `coordinator.local.md`
project_type / stack_tags — state/lessons.md:302, claude-central 2026-05-14) has
been fully ported to coordinator_core/ops/audit_enabled_plugins.py (co-located
test: test_audit_enabled_plugins.py). This file is now a thin DoE-side (contract)
trampoline over that claude-klabauter (engine) module, per DR-047 (DoE owns
contract/generator, claude-klabauter owns engine).

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
    audit-enabled-plugins.py [repo-root]   (default repo-root = pwd)

Always exits 0 — advisory only, never propagated to ceremony exit
(`/workweek-complete` Step 4f). audit_enabled_plugins.main() already enforces
this internally; this trampoline mirrors that on the engine root/import failure too
(fail-open, matching the oracle's unconditional `exit 0`).

Spec backlink: DoE-claude:pln-bash-polyglot-clean-slate-full-5c71ee
Prior bash implementation: see git log (audit-enabled-plugins.py, 122 lines,
retired on this cutover).
"""

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402


def _import_main():
    """Resolve the engine root, put it on sys.path, and import the ported entrypoint.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it -- this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.
    """
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.ops.audit_enabled_plugins import main as _op_main

    return _op_main


def main() -> None:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        # CLAUDE_KLABAUTER_ROOT resolution failed. This is an advisory check that must
        # never block the calling ceremony, so this is a loud stderr note, not
        # a nonzero exit.
        print(f"audit-enabled-plugins.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(0)
    except ImportError as exc:
        print(
            f"audit-enabled-plugins.py: coordinator_core.ops.audit_enabled_plugins not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(0)

    # audit_enabled_plugins.main() always returns 0 (advisory-only contract) --
    # no additional try/except needed here.
    sys.exit(op_main(sys.argv[1:]))


if __name__ == "__main__":
    main()
