# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""render-handoff-tracker.py — CLI trampoline over the handoff-tracker render op.

Thin DoE-side (contract) trampoline over claude-klabauter
coordinator_core.ops.ceremony.render_handoff_tracker, per DR-047 (DoE owns
contract/generator, claude-klabauter owns engine). Renders `state/handoff-tracker.md`
(per-repo). The fleet-aggregate `--all-repos` mode (DoE-aggregate
`state/doe-handoff-tracker.md`) was REMOVED 2026-07-23 (PM-ratified) — see
the removal negative-spec in
coordinator_core/ops/ceremony/render_handoff_tracker.py.
Finish-strangler port of the retired coordinator/bin/render-handoff-tracker.js
CLI surface (the .js file itself is kept on disk, delete-gated on a two-arm
gate — see the inline comment below and docs/architecture/migration-
hitlist.md — but production callers now import this Python module's op
directly).
"""
from __future__ import annotations
# render-handoff-tracker.py — CLI trampoline over claude-klabauter
# coordinator_core.ops.ceremony.render_handoff_tracker.
#
# Finish-strangler port (C9, 2026-07-22): the node implementation
# (coordinator/bin/render-handoff-tracker.js) has been ported to
# coordinator_core/ops/ceremony/render_handoff_tracker.py (the C9 disk seam
# over C8b's render_repo_section), exposing both a registered op
# (ceremony.render_handoff_tracker, for IPC-dispatch callers) and a
# trampoline-importable main(argv) -> int (for this CLI). This file is a thin
# DoE-side (contract) trampoline over that claude-klabauter (engine) module, per DR-047
# (DoE owns contract/generator, claude-klabauter owns engine) — mirrors the
# refresh-queries.py precedent exactly.
#
# Filename note / DELIBERATELY NOT DELETED: coordinator/bin/render-handoff-
# tracker.js is retained pending a double gate — (a) claude-klabauter's wsc_commit
# _OP_HANDOFF_TRACKER repoint (their de-node-query-read-layer spinoff), and
# (b) nothing else regressing. Arm (a) is now DISCHARGED: the C9 pure-Python
# tail rebuild (docs/plans/2026-07-16-wsc-pure-python-tail-rebuild.md)
# repointed _OP_HANDOFF_TRACKER's caller from wsc_commit.py to
# coordinator_core/ops/ceremony/tail_ops.py's native
# render_handoff_tracker/renderers.render_repo_section path before wsc_commit.py
# was ever deleted, and wsc_commit.py itself was then deleted outright
# 2026-07-29 (kill-list op removal) — there is no longer a "wsc_commit repoint"
# left to gate on. Arm (b) ("nothing else regressing") was NOT assessed as
# part of that deletion and remains open; tracker.js retirement itself is a
# separate decision this comment does not make. See
# docs/architecture/migration-hitlist.md for the tracked status and the
# claude-klabauter clearance-memo commitment.
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
# Exit-code contract:
#   0 — success (rendered and wrote, or --stdout printed)
#   1 — BUSINESS fail: a state-root resolution error. Matches the oracle's own
#       exit 1. An unknown CLI argument ALSO surfaces as exit 1 here — the
#       oracle's main() (coordinator_core.ops.ceremony.render_handoff_tracker)
#       has no own argparse and this trampoline is a bare
#       sys.exit(op_main(...)) with no pre-validation of its own, so there is
#       no path that can produce a distinct usage-error code. Asymmetric with
#       the refresh-queries.py exemplar, whose own CLI layer does distinguish
#       usage errors as exit 2 — that precedent does not apply here.
#   3 — TRANSPORT failure: CLAUDE_KLABAUTER_ROOT resolution or import failure AT THIS
#       trampoline layer (mirrors refresh-queries.py's own transport code).
#
# Review: code-reviewer — F1
#
# Spec backlink: pln-rebuild-the-wsc-commit-ceremon-f7c2a0 § C8b/C9
# Prior node implementation: coordinator/bin/render-handoff-tracker.js (still
# present, delete-gated — see "Filename note" above)

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402


def _import_main():
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.ops.ceremony.render_handoff_tracker import main as _op_main
    return _op_main


def main() -> None:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"render-handoff-tracker.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(3)
    except ImportError as exc:
        print(
            f"render-handoff-tracker.py: coordinator_core.ops.ceremony.render_handoff_tracker "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(3)

    # DR-276: this trampoline calls main(argv, self_commit=True) — a kwarg
    # run_op_main's argv-only contract has no room for — so it owns its
    # write-recording via recording_declared_writes() rather than routing
    # through run_op_main, matching that helper's documented carve-out for a
    # caller whose entrypoint signature run_op_main cannot express.
    from coordinator_core.cli_entry import recording_declared_writes

    with recording_declared_writes():
        code = op_main(sys.argv[1:], self_commit=True)
    sys.exit(code)


if __name__ == "__main__":
    main()
