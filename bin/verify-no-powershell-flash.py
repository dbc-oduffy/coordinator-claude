# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
verify-no-powershell-flash.sh — thin shim; canonical guard is now verify-no-console-flash.py.

CLI trampoline over claude-klabauter coordinator_core.ops.verify_no_powershell_flash.

This script is preserved so existing callers by the old name continue to work.
The guard logic was generalised to cover python/node/variable-interpreter and
heredoc spawn shapes in addition to powershell/pwsh — that logic lives
entirely in verify-no-console-flash.py (a separate port item); this trampoline
does nothing but locate that sibling script and re-invoke it with argv
forwarded verbatim.

Do NOT add logic here — edit bin/verify-no-console-flash.py instead.

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
  verify-no-powershell-flash.sh [ROOT]    # ROOT forwarded to the canonical guard

Exit codes: passes through the canonical guard's own exit code (0 clean, 1
violations found) unchanged; 2 only on a shim-level failure (engine-root
resolution, op import, or canonical-guard-script-not-found) — the canonical
guard itself never exits 2.

Spec backlink: docs/plans/2026-05-29-windows-console-flash-elimination.md § Chunk 3
"""

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def _import_runner():
    """Resolve the engine root, put it on sys.path, and import the DR-276 in-process
    runner.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it — this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.

    DR-276: routed through `coordinator_core.cli_entry.run_op_main` for
    baseline consistency — this shim re-invokes a sibling guard script that
    itself only reads source text to detect console-flash shapes (see module
    docstring), so it declares nothing and this conversion changes no
    observable behavior on either macOS/Linux or Windows.
    """
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main() -> None:
    try:
        run_op_main = _import_runner()
    except RuntimeError as exc:
        print(f"verify-no-powershell-flash.sh: engine-root resolution failed: {exc}", file=sys.stderr)
        sys.exit(2)
    except ImportError as exc:
        print(
            f"verify-no-powershell-flash.sh: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)

    try:
        code = run_op_main("coordinator_core.ops.verify_no_powershell_flash", [_SCRIPT_DIR] + sys.argv[1:])
    except ImportError as exc:
        print(
            f"verify-no-powershell-flash.sh: coordinator_core.ops.verify_no_powershell_flash not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(code)


if __name__ == "__main__":
    main()
