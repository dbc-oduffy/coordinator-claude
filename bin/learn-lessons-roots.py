# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
learn-lessons-roots — CLI trampoline over claude-klabauter coordinator_core.ops.learn_lessons_roots.

Finish-strangler port: the bash implementation (emit every on-disk repo root that
learn-lessons should process on this machine — $CLAUDE_HOME + machine-local
`repos.*` registry, minus publish-target/mirror repos, plus an optional
supplemental-roots sentinel) has been fully ported to
coordinator_core/ops/learn_lessons_roots.py (co-located test:
coordinator_core/ops/test_learn_lessons_roots.py, 10 tests). This file is now a
thin DoE-side (contract) trampoline over that claude-klabauter (engine) module, per DR-047
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

Contract preserved verbatim from the bash oracle's own header:
  1. $CLAUDE_HOME (default $HOME/.claude) is always the first line.
  2. Each machine-local repos.* key that resolves to an existing directory is
     included, EXCLUDING publish-target/mirror repos.
  3. Optional supplemental roots from the BEGIN/END learn-lessons-roots sentinel in
     <central-state>/learn-lessons-config.md are appended (empty by default).
  4. The output list is de-duplicated; every emitted line is an existing directory.
  5. Exit 0 always — graceful degradation if machine-local is absent or returns
     nothing (OSS fresh-install: emits exactly $CLAUDE_HOME).

Always exits 0 — this is a never-block enumeration helper (rule 5 above), matching
the `coordinator-auto-push` exit convention, NOT the fail-loud `handoff-gate-aging`
convention. Even a total engine-root-resolution failure degrades to emitting the
best-effort local $CLAUDE_HOME line rather than emitting nothing/erroring — a
learn-lessons discovery run that finds only the meta-repo is a lesser degradation
than a hard failure that blocks the whole triage.

Spec backlink: docs/plans/2026-06-19-portability-tracked-per-machine-config.md § C1
             + docs/plans/2026-07-16-bash-clean-slate-residual-migration.md

DR-276: routed through `coordinator_core.cli_entry.run_op_main` rather than a
plain in-process `import ... as _op_main` + `sys.exit(op_main(argv))` tail, so
any paths the op declares via `declare_write` become a session scope-touch
claim (this op is a read-only root enumerator that writes stdout only — see
module docstring's contract rules 1-5 — so it declares none; routing it is a
baseline-shrink, not a behavior change).
"""

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402


def _import_run_op_main():
    """Resolve the engine root, put it on sys.path, and import `run_op_main`.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it — this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is deliberately
    NOT used here.
    """
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def _fallback_claude_home() -> str:
    """Best-effort local re-derivation of just the $CLAUDE_HOME line — used ONLY
    when the claude-klabauter module itself is unreachable, so this never-block helper still
    emits its one unconditional guarantee (contract rule 1) instead of nothing."""
    base = (
        os.environ.get("CLAUDE_HOME")
        or os.environ.get("HOME")
        or os.environ.get("USERPROFILE")
        or os.path.expanduser("~")
    )
    return os.path.join(base, ".claude")


def main() -> None:
    try:
        run_op_main = _import_run_op_main()
    except RuntimeError as exc:
        print(f"learn-lessons-roots.sh: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        print(_fallback_claude_home())
        sys.exit(0)
    except ImportError as exc:
        print(
            f"learn-lessons-roots.sh: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        print(_fallback_claude_home())
        sys.exit(0)

    try:
        code = run_op_main("coordinator_core.ops.learn_lessons_roots", sys.argv[1:])
    except ImportError as exc:
        print(
            f"learn-lessons-roots.sh: coordinator_core.ops.learn_lessons_roots not importable: {exc}",
            file=sys.stderr,
        )
        print(_fallback_claude_home())
        sys.exit(0)

    sys.exit(code)


if __name__ == "__main__":
    main()
