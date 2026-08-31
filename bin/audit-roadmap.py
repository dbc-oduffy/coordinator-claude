# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
audit-roadmap.sh — CLI trampoline over claude-klabauter coordinator_core.roadmap.audit.

Finish-strangler port (DR-059): the bash implementation (Phase 2 close
cross-file audits for coordinator:roadmap-planning — 5 audits comparing
multiple stubs in the active set and cross-referencing pm-gates.md) has been
fully ported to coordinator_core/roadmap/audit.py (48 tests in
coordinator_core/roadmap/tests/test_audit.py). This file is now a thin
DoE-side (contract) trampoline over that claude-klabauter (engine) module, per DR-047
(DoE owns contract/generator, claude-klabauter owns engine).

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

Exit convention: this is a fail-loud GATE script (exit 1 blocks Phase 2
close on any audit failure; exit 2 on usage/config error; exit 3 on a hard
internal error) — never a never-block/best-effort script. A claude-klabauter-link
failure (the engine root unresolvable, or coordinator_core.roadmap.audit not
importable) is therefore surfaced as exit 3, mirroring the ported module's
own "hard error while auditing — aborting to avoid dead-gate silent skip"
contract (coordinator_core/roadmap/audit.py `main()`'s blanket-except path)
rather than exit 0 (which would silently let a broken gate pass) or exit 1
(reserved for the module's own foreseeable usage/config errors).

Known pre-existing bash-oracle bug, NOT reproduced (fix-in-port, DR-059):
the bash oracle threads DATA_ROOT to cc_records_query via
`export CLAUDE_KLABAUTER_ROOT="$DATA_ROOT"` — a subprocess-boundary env-var overload
that silently mis-roots PMG/RECON whenever the caller's cwd is a different
repo than an explicit `--root`, AND (verified empirically during this port's
parity pass) unconditionally clobbers any ambient engine root needed to
locate the coordinator_core Python package itself, breaking cc_records_query
in any environment where the data root and the claude-klabauter installation root
differ. The ported module (coordinator_core/roadmap/audit.py) has no such
env-var boundary — DATA_ROOT is passed as an explicit `worktree_root`
argument to an in-process `query_records()` call, never through an
environment variable — fixing this by construction. See that module's
docstring for the full analysis. This trampoline does not add its own
env-var threading and must not reintroduce it.

Spec backlink: docs/plans/2026-05-08-roadmap-skill-and-handoff-lifecycle.md § Phase 5
Port backlink: docs/plans/2026-07-15-bash-to-naked-python-engine-migration.md § T3a-g3e
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
    from coordinator_core.roadmap.audit import main as _op_main

    return _op_main


def main(argv: "list[str] | None" = None) -> int:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"audit-roadmap.sh: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return 3
    except ImportError as exc:
        print(
            f"audit-roadmap.sh: coordinator_core.roadmap.audit not importable: {exc}",
            file=sys.stderr,
        )
        return 3

    return op_main((sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    sys.exit(main())
