# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
check-em-environment.py — CLI trampoline over claude-klabauter coordinator_core.ops.check_em_environment.

Finish-strangler port (clean-slate residual migration, R2-R6): the bash
implementation (EFFORT/MODEL drift banner for the three start ceremonies) has
been fully ported to coordinator_core/ops/check_em_environment.py, tests
co-located as test_check_em_environment.py. This file is now a thin DoE-side
(contract) trampoline over that claude-klabauter (engine) module, per DR-047 (DoE owns
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

Exit convention: ALWAYS exits 0, even if the claude-klabauter link fails — this check
is a best-effort orientation banner inside a start ceremony, never a gate.
The bash oracle's own final line is an unconditional `exit 0`; this trampoline
preserves that even on CLAUDE_KLABAUTER_ROOT-resolution / import failure (unlike a
fail-loud gate/config-writer trampoline, which would sys.exit(1) there).

Spec backlink: DoE-claude:pln-bash-polyglot-clean-slate-full-5c71ee
"""

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402


def _import_runner():
    """Resolve CLAUDE_KLABAUTER_ROOT and import `run_op_main`.

    DR-276: routed through `coordinator_core.cli_entry.run_op_main` rather
    than importing the op's `main` directly, so any paths it declares become
    a session scope-touch claim instead of an unclaimed orphan at the
    `scoped_git_commit` sink.
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
        print(f"check-em-environment.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(0)
    except ImportError as exc:
        print(f"check-em-environment.py: coordinator_core.cli_entry not importable: {exc}", file=sys.stderr)
        sys.exit(0)
    try:
        code = run_op_main("coordinator_core.ops.check_em_environment", sys.argv[1:])
    except ImportError as exc:
        print(f"check-em-environment.py: coordinator_core.ops.check_em_environment not importable: {exc}", file=sys.stderr)
        sys.exit(0)
    sys.exit(code)


if __name__ == "__main__":
    main()
