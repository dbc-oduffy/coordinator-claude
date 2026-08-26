# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
coordinator-render-rollup.py — CLI trampoline over claude-klabauter
coordinator_core.ops.coordinator_render_rollup.

Finish-strangler port: the bash implementation (transport-seam consumer that
called the already-registered "deliverable.rollup" op via cc_invoke, then
rendered each direct-mode initiative as a human-readable "advances initiative"
line) has been fully ported to
coordinator_core/ops/coordinator_render_rollup.py (co-located
test_coordinator_render_rollup.py) per the R2-R6 clean-slate residual
migration. This file is now a thin DoE-side (contract) trampoline over that
Claude-klabauter (engine) module, per DR-047 (DoE owns contract/generator, claude-klabauter owns
engine).

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

Exit convention — never-block (auto-push shape), NOT fail-loud: this is a
render helper feeding a completion-entry sentence, not a gate. An engine-root
resolution failure or import failure degrades to a loud stderr note and exit 0
(omit the sentence), exactly like the pre-port bash's "coordinator-core-
invoke.sh not found" / cc_invoke transport-fail-closed paths, both of which
exited 0. The ONLY non-zero exit is a missing/empty required CLI argument
(<deliverable_id> / <repo_root>), matching the original bash's
`${1:?...}`/`${2:?...}` unbound-variable convention — that check now lives
inside coordinator_render_rollup.main(), not this trampoline.

Usage: coordinator-render-rollup.py <deliverable_id> <repo_root>

Spec backlink: docs/plans/2026-07-06-deliverable-rollup-render-and-fk-population.md § AC3
"""

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402


def _resolve_run_op_main():
    """Resolve the engine root, put it on sys.path, and import `run_op_main`.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it -- this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here. The ported module itself calls the
    "deliverable.rollup" op handler directly, in-process, for the same reason.

    DR-276: routed through `coordinator_core.cli_entry.run_op_main` rather than
    a bare `main` import, so any paths the op declares become a session
    scope-touch claim instead of an unclaimed orphan at the
    `scoped_git_commit` sink.
    """
    claude_klabauter_root = require_dispatch_engine_on_path()
    import coordinator_core

    # Guard against an ambient (e.g. editable-install) `coordinator_core`
    # already sitting in `sys.modules` from an EARLIER sys.path entry
    # shadowing the one this engine-root resolution is meant to select — a
    # bogus/stale engine root (no real coordinator_core inside it) would
    # otherwise silently succeed by falling through to that ambient module
    # instead of surfacing as the "not importable" never-block skip this
    # trampoline's own docstring documents. Compare the resolved module's
    # actual file location against claude_klabauter_root; a mismatch is treated the
    # same as an outright ImportError.
    resolved_file = getattr(coordinator_core, "__file__", None) or ""
    if not os.path.abspath(resolved_file).startswith(os.path.abspath(claude_klabauter_root) + os.sep):
        raise ImportError(
            f"coordinator_core resolved from {resolved_file!r}, not under "
            f"the engine root {claude_klabauter_root!r}"
        )

    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main() -> None:
    try:
        run_op_main = _resolve_run_op_main()
    except RuntimeError as exc:
        # engine-root resolution failed. Never-block render helper: loud
        # stderr note, exit 0 (matches the pre-port "coordinator-core-invoke.sh
        # not found" fail-open path).
        print(
            f"coordinator-render-rollup.py: engine-root resolution failed: {exc}",
            file=sys.stderr,
        )
        sys.exit(0)
    except ImportError as exc:
        print(
            f"coordinator-render-rollup.py: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(0)

    try:
        # op_main() owns the missing-arg (exit 1) vs fail-open-skip (exit 0)
        # distinction internally — no additional try/except needed here.
        code = run_op_main("coordinator_core.ops.coordinator_render_rollup", sys.argv[1:])
    except ImportError as exc:
        print(
            f"coordinator-render-rollup.py: coordinator_core.ops.coordinator_render_rollup "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(0)

    sys.exit(code)


if __name__ == "__main__":
    main()
