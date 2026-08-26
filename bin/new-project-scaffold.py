# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""new-project-scaffold.py — CLI trampoline scaffolding a new greenfield project.

Deterministic greenfield-scaffold helper backing the coordinator:new-project
skill: directory creation, `git init` pinned to branch `main`, optional
template render via render-template-tree.py, seed-file writes, and an
optional pnpm smoke pass. Scaffold logic lives claude-klabauter-side in
coordinator_core.ops.new_project_scaffold; this file is a thin DoE-side
trampoline forwarding argv to it.
"""
# new-project-scaffold.py — CLI trampoline over claude-klabauter
# coordinator_core.ops.new_project_scaffold.
#
# Port (DOE-PORT R1/BIG_PORT, template-variant #1 — direct-import, no registered
# op): the bash implementation (deterministic greenfield-scaffold helper for the
# coordinator:new-project skill — dir creation, git init pinned to branch `main`,
# optional template render via render-template-tree.py, seed-file writes,
# optional pnpm smoke pass) has been ported to
# coordinator_core/ops/new_project_scaffold.py, co-located test
# test_new_project_scaffold.py. This file is now a thin DoE-side (contract)
# trampoline over that claude-klabauter (engine) module, per DR-047 (DoE owns
# contract/generator, claude-klabauter owns engine).
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
# Fail-loud convention (unchanged from the bash oracle): pre-flight failures
# (bad args, occupied target dir), a missing/unresolvable DoE-side template
# sibling, or a pnpm smoke-step failure all exit 1. A claude-klabauter-link failure
# (the engine root unresolvable, or the op module not importable) is treated the
# same way — sys.exit(1) — because callers (coordinator:new-project skill)
# depend on this script's exit code to gate scaffold success, and there is no
# OTHER distinct business failure mode on this path to collide with (same
# precedent as render-template-tree.py / render-template.py; a cross-trampoline
# exit-code consistency sweep is a separate Wave-B item, not addressed
# piecemeal here).
#
# Spec backlink: docs/plans/2026-06-22-new-project-bootstrap-skill.md § C3
#
# DR-276: routed through `coordinator_core.cli_entry.run_op_main` rather than a
# plain in-process `import ... as _op_main` + `sys.exit(op_main(argv))` tail,
# so the rendered-template-tree files and the two seed files
# (`coordinator.local.md`, `README.md`) the op declares via `declare_write`
# become a session scope-touch claim instead of orphans.

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402


def _import_run_op_main():
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main
    return run_op_main


def main() -> None:
    try:
        run_op_main = _import_run_op_main()
    except RuntimeError as exc:
        print(f"new-project-scaffold.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(1)
    except ImportError as exc:
        print(
            f"new-project-scaffold.py: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        code = run_op_main("coordinator_core.ops.new_project_scaffold", sys.argv[1:])
    except ImportError as exc:
        print(
            f"new-project-scaffold.py: coordinator_core.ops.new_project_scaffold not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)
    sys.exit(code)


if __name__ == "__main__":
    main()
