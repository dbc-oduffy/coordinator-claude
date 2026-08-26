# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
# check-no-monolith-completion-append.py — pure-Python CLI; no sh/python
# polyglot trampoline. Wave 4a (2026-07-20) dropped the .sh suffix and the
# trampoline entirely — this used to be check-no-monolith-completion-append.sh,
# kept on .sh because three call sites hardcode the literal filename
# (coordinator/bin/tests/test-coordinator-complete-entry.sh,
# coordinator/bin/tests/test-check-no-monolith-completion-append.sh, and
# coordinator/skills/workstream-complete/SKILL.md's tripwire-comment
# cross-ref); that call is reversed by the Wave 4a PM amendment.
# test-check-no-monolith-completion-append.sh is repointed in this wave;
# NOTE: test-coordinator-complete-entry.sh and workstream-complete/SKILL.md
# are outside this chunk's remit and were left unedited — flag for the
# owning chunk/EM to repoint separately.
"""
check-no-monolith-completion-append.py — CLI trampoline over claude-klabauter
coordinator_core.ops.check_no_monolith_completion_append.

Static-grep tripwire: detects unauthorized writes to the legacy monolith
completion-log path archive/completed/YYYY-MM.md on the coordinator surface
(skills/, commands/, agents/, pipelines/, hooks/). Enforces the
monolithic-completion-log-write-check tripwire registered in
docs/wiki/coordinator-tripwires.md.

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

Usage:
  check-no-monolith-completion-append.py [--root <path>]

  --root  Path to the coordinator plugin root (default: this script's own two
           levels up, i.e. the coordinator/ directory). Override for testing.

Exit codes (fail-loud gate script — matches the retired bash oracle exactly):
  0  No unauthorized hits found (clean).
  1  One or more unauthorized hits found; offending file:line written to stderr.
  2  Script invocation error (bad args, engine-root resolution failure, ported
     module not importable, or no recognized search subdirs under root).

Root-default resolution stays on THIS side (not the claude-klabauter module) — the
ported op has no notion of "this trampoline file's own path", so this
trampoline computes the bash oracle's `dirname(dirname(script))` default and
passes it through as an explicit --root when the caller didn't supply one.

Spec backlink: docs/plans/2026-05-19-completion-log-phase1-foundational-loop.md § Chunk 10
Port backlink: docs/plans/2026-07-15-bash-to-naked-python-engine-migration.md
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
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.

    DR-276: the op is run through `coordinator_core.cli_entry.run_op_main`
    rather than by calling its `main` directly, so any path it declares via
    `declare_write` becomes a session scope-touch claim instead of an
    unclaimed orphan at the `scoped_git_commit` sink.
    """
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def _default_coordinator_root() -> str:
    # Mirrors the retired bash script's own default: SCRIPT_DIR=dirname(script)
    # (bin/), COORDINATOR_ROOT=dirname(SCRIPT_DIR) (coordinator/).
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(script_dir)


def _argv_with_default_root(argv: list) -> list:
    if "--root" in argv or "--help" in argv or "-h" in argv:
        return argv
    return ["--root", _default_coordinator_root()] + argv


def main() -> None:
    try:
        run_op_main = _import_run_op_main()
    except RuntimeError as exc:
        print(
            f"check-no-monolith-completion-append.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)
    except ImportError as exc:
        print(
            f"check-no-monolith-completion-append.py: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)

    try:
        code = run_op_main(
            "coordinator_core.ops.check_no_monolith_completion_append",
            _argv_with_default_root(sys.argv[1:]),
        )
    except ImportError as exc:
        print(
            "check-no-monolith-completion-append.py: "
            f"coordinator_core.ops.check_no_monolith_completion_append not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(code)


if __name__ == "__main__":
    main()
