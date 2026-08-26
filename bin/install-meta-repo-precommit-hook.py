# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
install-meta-repo-precommit-hook — CLI trampoline over claude-klabauter
coordinator_core.ops.install_meta_repo_precommit_hook.

Finish-strangler port: the bash implementation (meta-repo pre-commit exec-bit +
illegal-path gate installer — identity-gated to $HOME/.claude, idempotent,
append-not-clobber on an existing custom hook) has been fully ported to
coordinator_core/ops/install_meta_repo_precommit_hook.py, with characterization
tests in the co-located test_install_meta_repo_precommit_hook.py. This file is
now a thin DoE-side (contract) trampoline over that claude-klabauter (engine) module, per
DR-047 (DoE owns contract/generator, claude-klabauter owns engine).

2026-07-29: this trampoline calls `main_install_all`, not `main` — it drives
BOTH the sending-side `pre-commit` gate (`main`/`_GATE_REGISTRY`) and the
receiving-side `post-merge`/`post-checkout` gates (`main_post_sync`/
`_POST_SYNC_GATE_REGISTRY`) in one call, so this is the single install-time
call site for all three hooks. `main_post_sync` previously had no call site
at all anywhere in the tree despite shipping fully tested — see
`install_meta_repo_precommit_hook.main_install_all`'s own docstring for that
history. Do not repoint this back at bare `main` — that reintroduces the gap.

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

Exit convention: this is a config-writer/gate-installer, not a never-block hook
(unlike coordinator-auto-push). A claude-klabauter-link failure means the installer
literally could not run — silently exiting 0 would read as "hook installed"
to callers (`/coordinator:install`, `/repo-setup`) when it was not, so this
trampoline exits 1 (fail-loud) on engine-root resolution or import failure.
The op's own internal skip paths (not a git repo, not the meta-repo, already
installed) all still exit 0, exactly as the bash oracle did.

Spec backlink: cross-repo/inbox/2026-06-08-exec-bit-drift-runtime-tripwire-tests.md
Port backlink: docs/plans/2026-07-16-bash-clean-slate-residual-migration.md
"""

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402


def _import_runner():
    """DR-276: routed through `coordinator_core.cli_entry.run_op_main` with
    `entrypoint="main_install_all"` so its declared writes become a session
    scope-touch claim, without repointing it at bare `main` (see module
    docstring — that reintroduces the post-merge/post-checkout gap).
    """
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main
    return run_op_main


def main() -> None:
    try:
        run_op_main = _import_runner()
    except RuntimeError as exc:
        print(
            f"install-meta-repo-precommit-hook: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)
    except ImportError as exc:
        print(
            "install-meta-repo-precommit-hook: "
            f"coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        code = run_op_main(
            "coordinator_core.ops.install_meta_repo_precommit_hook",
            sys.argv[1:],
            entrypoint="main_install_all",
        )
    except ImportError as exc:
        print(
            "install-meta-repo-precommit-hook: "
            f"coordinator_core.ops.install_meta_repo_precommit_hook not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)
    sys.exit(code)


if __name__ == "__main__":
    main()
