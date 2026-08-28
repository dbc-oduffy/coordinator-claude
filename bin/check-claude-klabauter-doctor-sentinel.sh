# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
# check-claude-klabauter-doctor-sentinel.sh — pure-Python CLI; no sh/python polyglot
# trampoline. Wave 4a (2026-07-20) dropped the .sh suffix and the trampoline
# entirely — this used to be check-claude-klabauter-doctor-sentinel.sh, kept on .sh
# because commands/workday-start.md:744 and codename-provenance-seed.sh
# referenced this exact basename; that call is reversed by the Wave 4a PM
# amendment. workday-start.md is repointed in this wave; NOTE:
# codename-provenance-seed.sh is outside this chunk's remit and was left
# unedited — flag for the owning chunk/EM to repoint separately.
"""
Check-claude-klabauter-doctor-sentinel.sh — CLI trampoline over claude-klabauter
coordinator_core.ops.check_claude_klabauter_doctor_sentinel.

Read-only consumer of claude-klabauter's health sentinel
(<engine root>/state/doctor-last-run.json, claude-klabauter-owned schema). Surfaces the
GREEN/AMBER/RED verdict during fleet `/workday-start`, mirroring how
check-plugin-drift.py nudges on drift. This trampoline never writes the
sentinel — claude-klabauter's `bin/claude-klabauter-doctor-probe.py` owns that.

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

Always exits 0 — advisory only, never gating (matches check-plugin-drift.py /
scan-addon-health.py convention of "probe never fails the ceremony"). This
mirrors the original bash script's own convention: engine-root-unresolvable
and sentinel-absent/malformed are all soft-skip states, not failures.

Divergence from the original .sh (documented, not a parity break): the
original silently discarded the engine-root-resolution stderr
(`coordinator_claude_klabauter_root 2>/dev/null || exit 0`); this trampoline follows the
house convention of printing the resolution failure to stderr before the same
exit-0 fallback (matches coordinator-auto-push/handoff-gate-aging). stdout and
exit code — the parity-critical contract this script's callers depend on — are
unchanged.

Spec backlink: cross-repo/inbox/2026-07-04-workday-start-claude-klabauter-doctor-sentinel.md
Port backlink: docs/plans/2026-07-15-bash-to-naked-python-engine-migration.md

DR-276: routed through `coordinator_core.cli_entry.run_op_main` rather than a
plain in-process `import ... as _op_main` + `sys.exit(op_main(argv))` tail, so
any paths the op declares via `declare_write` become a session scope-touch
claim (this op is read-only — see module docstring — so it declares none;
routing it is a baseline-shrink, not a behavior change).
"""

from __future__ import annotations

import os
import sys


def _import_run_op_main():
    """Resolve the CO-LOCATED engine root and import the in-process runner.

    LOCATOR AXIS, NOT DISPATCH, for the same named reason as
    `install-claude-klabauter-precommit-hook.py`: the publish transform renames the op
    this dispatches (`check_claude_klabauter_doctor_sentinel.py` ->
    `check_claude_klabauter_doctor_sentinel.py`, the `basename_rename` table in
    setup/percolate-hooks/percolate-store.yaml), so the module name spelled
    below resolves ONLY inside the tree this file itself ships in. On any box
    whose dispatch root is the published mirror, the op is present under its
    other name and the import failed unconditionally — and because this probe
    is advisory (exit 0 on every failure path, per the module docstring), that
    failure was silent: the workday-start sentinel nudge had simply stopped
    running. Measured 2026-08-26 alongside the pre-commit installer's louder
    instance of the same defect.

    Guard: coordinator/bin/tests/test_precommit_trampoline_engine_axis.py
    (AC-axis) cross-checks every dispatch-axis trampoline against the store's
    rename table, so a third instance fails a test rather than going quiet.
    """
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_colocated_engine_on_path

    claude_klabauter_root = require_colocated_engine_on_path(__file__)
    from coordinator_core.cli_entry import run_op_main
    return run_op_main


def main(argv: "list[str] | None" = None) -> int:
    try:
        run_op_main = _import_run_op_main()
    except RuntimeError as exc:
        print(f"check-claude-klabauter-doctor-sentinel.sh: engine root resolution failed: {exc}", file=sys.stderr)
        return 0
    except ImportError as exc:
        print(
            f"check-claude-klabauter-doctor-sentinel.sh: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        return 0

    try:
        code = run_op_main("coordinator_core.ops.check_claude_klabauter_doctor_sentinel", (sys.argv[1:] if argv is None else argv))
    except ImportError as exc:
        print(
            f"check-claude-klabauter-doctor-sentinel.sh: coordinator_core.ops.check_claude_klabauter_doctor_sentinel "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        return 0
    return code


if __name__ == "__main__":
    sys.exit(main())
