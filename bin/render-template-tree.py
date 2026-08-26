# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
render-template-tree.py — CLI trampoline over claude-klabauter
coordinator_core.ops.render_template_tree.

Port (DOE-PORT R1, template-variant #1 — direct-import, no registered op): the
bash implementation (render-template-tree.sh, DoE 290997c7, 2026-07-22 —
tree-walker that copies a template dir tree and delegates per-file {{KEY}}
substitution to render-template.py) has been ported to
coordinator_core/ops/render_template_tree.py, co-located test
test_render_template_tree.py. This file is now a thin DoE-side (contract)
trampoline over that claude-klabauter (engine) module, per DR-047 (DoE owns
contract/generator, claude-klabauter owns engine).

render-template.py itself (the single-file token renderer this script
delegates each token-bearing file to) has NOT been ported in this wave — the
Claude-klabauter module shells out to it by resolving the DoE clone root and locating
`coordinator/bin/render-template.py` there, exactly as this bash oracle located
it as a script-directory-relative sibling. That division of labor
(tree-walk here, substitution there) is unchanged by the port.

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

DR-276: the op is run through `coordinator_core.cli_entry.run_op_main` rather
than by calling its `main` directly, so the paths it declares (every file this
tree-renderer writes under `<dst-tree-dir>`, declared inside its copy/render
loop) become a session scope-touch claim. Without that, everything this CLI
writes is an orphan at the `scoped_git_commit` sink.

Fail-loud convention (unchanged from the bash oracle): usage errors, an
unreadable src dir, a non-empty dst dir, a missing render-template.py, or any
per-file render failure all exit non-zero. A claude-klabauter-link failure (the engine root
unresolvable, or the op module not importable) is treated the same way —
sys.exit(1), not a silent no-op — because callers (new-project-scaffold.py)
depend on this script's exit code to gate scaffold success.

Spec backlink: docs/plans/2026-06-22-new-project-bootstrap-skill.md § C2
"""

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402


def _import_runner():
    """In-process import, not an RPC invoke — this is a plain local file
    mutation, same rationale as edit-live-hook.py's own trampoline.

    DR-276: the op is run through `coordinator_core.cli_entry.run_op_main`
    rather than by calling its `main` directly, so the paths it declares become
    a session scope-touch claim. Without that, everything this CLI writes is an
    orphan at the `scoped_git_commit` sink.
    """
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main() -> None:
    try:
        run_op_main = _import_runner()
    except RuntimeError as exc:
        print(f"render-template-tree.sh: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(1)
    except ImportError as exc:
        print(
            f"render-template-tree.sh: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        code = run_op_main("coordinator_core.ops.render_template_tree", sys.argv[1:])
    except ImportError as exc:
        print(
            f"render-template-tree.sh: coordinator_core.ops.render_template_tree not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    sys.exit(code)


if __name__ == "__main__":
    main()
