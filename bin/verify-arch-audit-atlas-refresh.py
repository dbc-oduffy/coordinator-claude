# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
# commit-message file ($3 or .git/COMMIT_EDITMSG).
#   - SKIP   — no atlas page exists for <TARGET_SYSTEM>
#   - PASS branch=A — staged body diff AND staged last_mapped == AUDIT_DATE
#                     AND staged last_attested == AUDIT_DATE
#   - PASS branch=B — commit-msg contains `atlas-current-as-of:<AUDIT_DATE>`
#                     AND staged last_attested == AUDIT_DATE
#                     AND zero staged body delta AND last_mapped UNCHANGED
# INCLUDING on a engine-root resolution or import (transport) failure — this
# coordinator/pipelines/weekly-architecture-audit/PIPELINE.md and

import os
import sys

def _import_run_op_main():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main(argv: "list[str] | None" = None) -> int:
    try:
        run_op_main = _import_run_op_main()
    except RuntimeError as exc:
        print(
            f"verify-arch-audit-atlas-refresh.py: engine-root resolution failed: {exc}",
            file=sys.stderr,
        )
        print(
            "FAIL: /architecture-audit Step 6.5 atlas-refresh gate could not run "
            "(claude-klabauter-link resolution failed) — treat as gate-not-satisfied and retry."
        )
        return 0
    except ImportError as exc:
        print(
            f"verify-arch-audit-atlas-refresh.py: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        print(
            "FAIL: /architecture-audit Step 6.5 atlas-refresh gate could not run "
            "(claude-klabauter-link import failed) — treat as gate-not-satisfied and retry."
        )
        return 0

    try:
        code = run_op_main("coordinator_core.ops.verify_arch_audit_atlas_refresh", (sys.argv[1:] if argv is None else argv))
    except ImportError as exc:
        print(
            f"verify-arch-audit-atlas-refresh.py: coordinator_core.ops.verify_arch_audit_atlas_refresh not importable: {exc}",
            file=sys.stderr,
        )
        print(
            "FAIL: /architecture-audit Step 6.5 atlas-refresh gate could not run "
            "(claude-klabauter-link import failed) — treat as gate-not-satisfied and retry."
        )
        return 0

    return code


if __name__ == "__main__":
    sys.exit(main())
