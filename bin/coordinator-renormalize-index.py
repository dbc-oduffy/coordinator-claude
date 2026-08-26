"""
coordinator-renormalize-index — CLI trampoline over claude-klabauter
coordinator_core.ops.renormalize_index.

Clears EOL "phantom-dirty" index entries safely under concurrent-EM sessions.

THE BUG. On Git-for-Windows a tracked file's index entry can record a stale
line-ending-era blob size while HEAD and the worktree already agree on the
normalized content. `git diff` / `git diff --cached` renormalize then hash, so
they see the content as equal and report nothing to commit. But `git status`
uses the recorded blob SIZE as a stat shortcut, and size differs across the
EOL round-trip — so the file is flagged modified forever. This tool refreshes
ONLY the phantom set (stat-modified MINUS real worktree-vs-index content diffs
MINUS deleted-in-worktree), never a blanket `git add --renormalize .` — see
the ported module's docstring for the full mechanism, the residual-race
disclosure, and the negative-spec (never commits; never touches a real edit
or a sibling's staged blob).

Finish-strangler port: the bash implementation (187 lines) has been fully
ported to coordinator_core/ops/renormalize_index.py (claude-klabauter), with parity
coverage in the co-located pytest
(coordinator_core/ops/test_renormalize_index.py). This file is now a thin
DoE-side trampoline over that claude-klabauter module. Zero production callers of the
bash original as of this port — tests only, which exec'd this file in place
and needed no rework: this trampoline preserves the same argv contract (bare /
`--check`), the same stdout-silent / stderr-messaged behavior, and the same
exit codes.

Dropped, not translated: the bash oracle's `BASH_VERSINFO < 4` portability
no-op guard has no equivalent here — this port never spawns bash/sh, so there
is no shell version to gate on (see the ported module's docstring negative
-spec). This trampoline runs identically on every platform Python runs on.

Usage:
  coordinator-renormalize-index            # refresh phantom entries in the current repo
  coordinator-renormalize-index --check    # report the phantom count only; never writes

Exit codes (parity-critical — matches coordinator_core.ops.renormalize_index.main
exactly; see that module's docstring for the full contract):
  0 — clean (no phantoms), counted (--check), refreshed, or deferred (index.lock present).
  1 — not a git repository, a required `git diff`/`git ls-files -m` probe FAILED, or the
      `git add` refresh reported a failure for at least one path.
  2 — DEDICATED transport/config-failure code, distinct from the business codes above:
      engine-root resolution failed, or coordinator_core.ops.renormalize_index not
      importable.

Spec backlink: docs/wiki/concurrent-em-hazards.md § H23.

DR-276: routed through `coordinator_core.cli_entry.run_op_main` rather than a
plain in-process `import ... as _op_main` + `sys.exit(op_main(argv))` tail, so
any paths the op declares via `declare_write` become a session scope-touch
claim (this op only ever refreshes git INDEX entries via `git add`, never a
repo-relative file's content — see module docstring's negative-spec — so it
declares none; routing it is a baseline-shrink, not a behavior change).
"""

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
    NOT used here (variant-#1 direct-import trampoline — see
    tasks/2026-07-16-clean-slate-recon/r1-doe-port-template.md § 1).
    """
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main() -> None:
    try:
        run_op_main = _import_run_op_main()
    except RuntimeError as exc:
        print(f"coordinator-renormalize-index: engine-root resolution failed: {exc}", file=sys.stderr)
        sys.exit(2)
    except ImportError as exc:
        print(
            f"coordinator-renormalize-index: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)

    try:
        code = run_op_main("coordinator_core.ops.renormalize_index", sys.argv[1:])
    except ImportError as exc:
        print(
            f"coordinator-renormalize-index: coordinator_core.ops.renormalize_index not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(code)


if __name__ == "__main__":
    main()
