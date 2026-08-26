# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""verify-ps51-clean.py — CLI trampoline over claude-klabauter coordinator_core.ops.verify_ps51_clean.

Repo-agnostic smoke check asserting Windows PowerShell .ps1 setup/install
legs are PS-5.1-clean: they parse under the Windows PowerShell 5.1 console
host (not pwsh 7) and contain no pwsh-7-only syntax. Four-way per-file
classification (OK / FAIL / EXPECTED-PS7 / WARN); shared home in coordinator
bin/ — each consuming repo (coordinator, example-game-workbench-repo) calls it
pointing at its own .ps1 set.
"""
# verify-ps51-clean.py — CLI trampoline over claude-klabauter
# coordinator_core.ops.verify_ps51_clean. Repo-agnostic smoke check that asserts
# Windows PowerShell .ps1 setup/install legs are PS-5.1-clean: they PARSE under
# the Windows PowerShell 5.1 console host (NOT pwsh 7) and contain no pwsh-7-only
# syntax patterns. Four-way per-file classification (OK / FAIL / EXPECTED-PS7 /
# WARN) — see the claude-klabauter module's own docstring for the full classification
# rules; this trampoline only resolves the engine root, imports the op, and
# forwards argv/exit-code. (The actual console-host subprocess invocation, with
# its CREATE_NO_WINDOW popup guard, lives entirely in the claude-klabauter module — this
# trampoline itself spawns nothing.)
#
# Shared home in coordinator bin/; each consuming repo (coordinator,
# example-game-workbench-repo) calls it pointing at its own .ps1 set.
#
# Shebang note: the SHEBANG line above is `#!/usr/bin/env python3`, generator-
# owned by `gen-launcher-shim.py --ensure-unix`, and correct for this shape. On
# Windows, this file's co-located `.cmd` twin wins via `PATHEXT` when invoked
# as a bareword, so the shebang is never read there; on macOS/Linux `python3`
# is the right interpreter. Caution: callers must invoke via the extensionless
# name or a resolved-interpreter prefix, never a bareword `.py` through git-
# bash — git-bash DOES honor the shebang and would exec-127 with no `python3`
# present. See the carve-out in DoE-claude's coordinator/docs/wiki/bash-on-
# windows-gotchas.md § Carve-out (cross-repo — this wiki lives in the
# DoE-claude repo, not here).
#
# Usage: verify-ps51-clean.py <path-or-dir> [<path-or-dir> ...]
#   Each arg is a .ps1 file OR a directory (recurse for *.ps1, excluding
#   node_modules/ and .git/ paths).
# Exit:  0 if all files parse-clean under PS 5.1 (WARN/EXPECTED-PS7 are still 0),
#        or if the PS 5.1 console host is absent (SKIP — Windows-only check);
#        1 if any file has an unexpected 5.1 parse error (genuine FAIL);
#        2 if called with no arguments (usage error);
#        3 if the claude-klabauter link itself is unreachable (engine-root resolution
#          failure or the op module is not importable) — a DEDICATED code so a
#          transport/infra outage is never misread as "all clean" (exit 0) or
#          a business FAIL (exit 1). This is a fail-loud gate script (a broken
#          Windows-clean-install smoke check must not silently report green),
#          so unlike auto-push/handoff-gate-aging's never-block posture, a
#          claude-klabauter-link failure here is loud, not swallowed. Per
#          PORTER-BRIEF-ADDENDUM § 3b.
#
# Spec backlink: state/handoffs/2026-06-22_215618_windows-clean-install-verification.md
# (Part B). Path is relative to the ~/.claude meta-repo root; not present in distributed installs.
#
# Port of: coordinator/bin/verify-ps51-clean.py (bash body retired on cutover; see git log)
# Port backlink: docs/plans/2026-07-15-bash-to-naked-python-engine-migration.md (BIG_PORT wave A)

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402


def _import_runner():
    """Resolve the engine root, put it on sys.path, and import `run_op_main`.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it — this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here (template-variant #1, direct-import trampoline;
    this op has no @register_op — it is a plain module, not a JSON-RPC op).

    DR-276: routed through `coordinator_core.cli_entry.run_op_main` rather
    than importing the op's `main` directly, so any paths it declares become
    a session scope-touch claim instead of an unclaimed orphan at the
    `scoped_git_commit` sink.
    """
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main() -> None:
    try:
        run_op_main = _import_runner()
    except RuntimeError as exc:
        print(f"verify-ps51-clean.py: engine-root resolution failed: {exc}", file=sys.stderr)
        sys.exit(3)
    except ImportError as exc:
        print(
            f"verify-ps51-clean.py: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(3)
    try:
        code = run_op_main("coordinator_core.ops.verify_ps51_clean", sys.argv[1:])
    except ImportError as exc:
        print(
            f"verify-ps51-clean.py: coordinator_core.ops.verify_ps51_clean not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(3)
    sys.exit(code)


if __name__ == "__main__":
    main()
