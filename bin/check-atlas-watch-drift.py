# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
check-atlas-watch-drift.sh — CLI trampoline over claude-klabauter
coordinator_core.ops.check_atlas_watch_drift.

Aggregates per-system `<name>.watch.sh` outputs into one line per atlas
system, plus a default-on STALE walk over `last_attested` frontmatter
(currency timestamp; bumped by audits AND bare re-attestations).

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

Spec backlink: docs/plans/2026-06-04-architecture-audit-atlas-refresh-gate.md § C2
Spec backlink: docs/plans/2026-06-08-atlas-attested-clock-split.md (last_attested
    as currency signal)
Port backlink: docs/plans/2026-07-16-bash-clean-slate-residual-migration.md

CLI: --stale-days N              (default 30; alias --last-attested-stale-days;
                                   accepts legacy --last-mapped-stale-days)
     --no-stale-walk             (suppress STALE walk entirely)

Negative-spec: does NOT modify any atlas page, does NOT trigger any audit,
does NOT read or write `Last full audit`. Pure read. Always exits 0 —
informational contract preserved even when the claude-klabauter link itself fails
(this script must never block a caller pipeline on transport unavailability).
"""

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402


def _import_runner():
    """Resolve the engine root, put it on sys.path, and import the DR-276 in-process
    runner.

    Reuses cc_invoke's battle-tested engine-root resolution ladder rather than
    re-deriving it — this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.

    DR-276: routed through `coordinator_core.cli_entry.run_op_main` for
    baseline consistency with the other converted trampolines — this op is
    pure read (see module docstring), so it declares nothing and this
    conversion changes no observable behavior.
    """
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main
    return run_op_main


def main() -> None:
    try:
        run_op_main = _import_runner()
    except RuntimeError as exc:
        print(f"check-atlas-watch-drift: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(0)
    except ImportError as exc:
        print(
            f"check-atlas-watch-drift: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(0)

    try:
        code = run_op_main("coordinator_core.ops.check_atlas_watch_drift", sys.argv[1:])
    except ImportError as exc:
        print(
            f"check-atlas-watch-drift: coordinator_core.ops.check_atlas_watch_drift not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(0)
    sys.exit(code)


if __name__ == "__main__":
    main()
