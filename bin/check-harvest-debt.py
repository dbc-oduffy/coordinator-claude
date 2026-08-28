# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
check-harvest-debt.sh — CLI trampoline over claude-klabauter
coordinator_core.ops.check_harvest_debt.

Finish-strangler port (DR-059): the bash implementation (read-only harvest-
debt nudge probe — basename-matched archive/specs vs canonical distillation
log) has been fully ported to coordinator_core/ops/check_harvest_debt.py
(direct-import op, co-located test coordinator_core/tests/test_check_harvest_debt.py).
This file is now a thin DoE-side (contract) trampoline over that claude-klabauter
(engine) module, per DR-047 (DoE owns contract/generator, claude-klabauter owns engine).

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

Exit convention: this is an ADVISORY orientation-nudge probe (invoked from
`/workday-start`), not a commit gate — never blocks the caller on a
trampoline/transport failure (the engine root unresolvable, module not
importable). On such failure this prints a stderr note and exits 0, same
posture as `coordinator-auto-push`. Business-logic exit codes (0 = probe ran,
nudge or silent; 1 = archive/specs/ present but canonical log absent —
fail-loud, see the claude-klabauter module's own docstring) are UNCHANGED and produced
by check_harvest_debt.main() itself once import succeeds.

Spec backlink: DoE-claude:pln-bash-to-naked-python-engine-mi-c09292
"""

from __future__ import annotations

import os
import sys


def _import_main():
    """Resolve the engine root, put it on sys.path, and import the ported entrypoint.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it -- this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.
    """
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.ops.check_harvest_debt import main as _op_main

    return _op_main


def main(argv: "list[str] | None" = None) -> int:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        # CLAUDE_KLABAUTER_ROOT resolution failed. This is an orientation nudge, not a
        # gate -- never block the caller on a transport failure.
        print(f"check-harvest-debt.sh: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return 0
    except ImportError as exc:
        print(
            f"check-harvest-debt.sh: coordinator_core.ops.check_harvest_debt not importable: {exc}",
            file=sys.stderr,
        )
        return 0

    return op_main((sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    sys.exit(main())
