# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
check-arch-audit-staleness.py — CLI trampoline over claude-klabauter
coordinator_core.ops.check_arch_audit_staleness.

Computes how stale the rotational architecture audit is, by reading the
`Last targeted audit` clock from the health ledger. /workweek-complete Step
7.6 reads this to decide whether to auto-fold a targeted-on-diff architecture
audit.

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

Filename note: the `.sh` extension is retained (NOT dropped per the
`coordinator-auto-push`/`handoff-gate-aging` convention) — this script is
invoked by its literal `.sh`-suffixed name from
coordinator/commands/workweek-complete.md and
coordinator/docs/wiki/weekly-gate-architecture.md; the polyglot shebang makes
the retained suffix harmless (`python check-arch-audit-staleness.py ...` still
Just Works), avoiding an otherwise-unnecessary multi-caller repoint.

Output: one line to stdout — STALE / FRESH / UNKNOWN.
Exit code: always 0 (informational — callers decide whether to surface the
signal), INCLUDING on an engine-root resolution or import failure — this
mirrors the original bash oracle's own always-exit-0 contract (never-block
shape, not a fail-loud gate/config-writer), so a claude-klabauter-link failure degrades
to the same UNKNOWN verdict a caller already treats as "don't auto-fold",
rather than introducing a new nonzero exit code callers never handled.

Spec backlink: docs/plans/2026-05-23-weekly-gate-restructure-and-arch-survey-audit-rename.md § Strand 3b
Port of: coordinator/bin/check-arch-audit-staleness.py (bash body retired on cutover; see git log)
Port backlink: docs/plans/2026-07-16-bash-clean-slate-residual-migration.md
"""

from __future__ import annotations

import os
import sys


def _prepare_claude_klabauter_root() -> None:
    """Resolve the engine root and put it on sys.path.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it.

    DR-276: the op itself is run through `coordinator_core.cli_entry.run_op_main`
    rather than by importing and calling its `main` directly, so any paths it
    declares via `declare_write()` become a session scope-touch claim instead
    of landing unclaimed as an orphan at the `scoped_git_commit` sink.
    """
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()


def main(argv: "list[str] | None" = None) -> int:
    try:
        _prepare_claude_klabauter_root()
    except RuntimeError as exc:
        print(f"check-arch-audit-staleness.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        print("UNKNOWN")
        return 0

    from coordinator_core.cli_entry import run_op_main

    try:
        code = run_op_main("coordinator_core.ops.check_arch_audit_staleness", (sys.argv[1:] if argv is None else argv))
    except ImportError as exc:
        print(
            f"check-arch-audit-staleness.py: coordinator_core.ops.check_arch_audit_staleness not importable: {exc}",
            file=sys.stderr,
        )
        print("UNKNOWN")
        return 0

    return code


if __name__ == "__main__":
    sys.exit(main())
