# roadmap-planning-assemble — CLI trampoline over claude-klabauter
# coordinator_core.roadmap_planning_assemble (the spine-seam computed-skill
# assembler for `roadmap-planning`'s Phase 1 synthesis / N sprint
# descriptors / cross-sprint edge set). Direct-import shape (mirrors
# coordinator/bin/sizing-assemble.py's own file BEFORE its conversion into
# entry_point_shim.py's ASSEMBLE_TARGETS dispatch table): a plain
# in-process function call after resolving the engine root, no cc_invoke/IPC
# hop, no entry_point_shim registration (this chunk's writes list does not
# include entry_point_shim.py — that fan-in table is a separate surface,
# out of C10's scope).
#
# Contract: DoE-claude coordinator/docs/wiki/computed-skills.md, DR-047
# Spec backlink: docs/plans/2026-08-21-engine-half-of-the-roadmap-sprint-spine-split.md,
# chunk C10. Source memo:
# cross-repo/inbox/2026-08-20-doe-claude-em-roadmap-sprint-split-assembler-ops.md
#
# Subcommand: none — this trampoline forwards straight to
# coordinator_core.roadmap_planning_assemble.main(argv). See that module's
# `main()` for the flag surface (--run-id, --input-corpus, --stub-id,
# --problem-set, --sizing-object, --decisions).
#
# HARD: no module-scope import of coordinator_core.ops anywhere on this
# path — coordinator_core.roadmap_planning_assemble is imported lazily,
# inside main(), only after CLAUDE_KLABAUTER_ROOT resolves. Mirrors sizing-assemble's
# own shape verbatim (module-scope imports here are only os/sys).
#
# READ-ONLY — mutates nothing. roadmap_planning_assemble.brief() never
# writes a stub/OVERVIEW/spine record; it returns the routing fields for a
# future mutating `apply` half (out of this chunk's scope) to execute.
#
# Exit codes (locally scoped to this CLI, NOT inherited):
#   0 — OK, a decision object was computed and printed.
#   2 — usage error (malformed --decisions JSON, unrecognized argument).
#   3 — transport failure (the engine root unresolvable, coordinator_core
#       import failure, or an unexpected exception inside brief()).
from __future__ import annotations

import os
import sys


_TRANSPORT_FAIL = 3


def _main(argv: list[str]) -> int:
    from cc_invoke import require_dispatch_engine_on_path  # noqa: E402

    try:
        require_dispatch_engine_on_path()
    except RuntimeError as exc:
        print(f"roadmap-planning-assemble: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL

    try:
        import coordinator_core.roadmap_planning_assemble as mod
    except ImportError as exc:
        print(
            f"roadmap-planning-assemble: coordinator_core.roadmap_planning_assemble not importable: {exc}",
            file=sys.stderr,
        )
        return _TRANSPORT_FAIL

    return mod.main(argv)


def main(argv: list[str]) -> int:
    return _main(argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
