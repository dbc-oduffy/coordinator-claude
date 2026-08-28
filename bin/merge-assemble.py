# merge-assemble — CLI trampoline over claude-klabauter
# coordinator_core.merge_assemble (the computed-skill assembler for
# `/merge-to-main`'s branch/release-tag/PR ceremony). Direct-import variant
# (template-variant #1, mirrors coordinator/bin/pickup-assemble): a plain
# in-process function call after resolving the engine root, no cc_invoke/IPC hop.
#
# Contract: DoE-claude coordinator/docs/wiki/computed-skills.md
# Spec backlink: docs/plans/2026-07-24-computed-skills-b4-baton-branch-lifecycle.md, chunk C6
#
# Subcommands:
#   brief [--tag-prefix <prefix>]
#     Computes and returns the merge decision object (branch_state,
#     release_tag_cut proposal, version_bump proposal, gate_verdicts
#     scaffold, directives[], judgment_points[]). READ-ONLY.
#   apply [--session-id <id>] [--force] [--decisions <json>] [--tag-prefix <prefix>]
#     Recomputes the brief and dispatches its directives[] through the
#     closed CLI table. `--force` bypasses the node ceremony hard-gate.
#
# Exit codes (locally scoped to this CLI, NOT inherited — see the contract's
# own § Exit-code contract):
#   0 — OK.
#   1 — business failure (brief) / halted-at-judgment (apply).
#   2 — usage error.
#   3 — transport failure (the engine root unresolvable, import failure, no
#       enclosing git worktree).

# --- routing half: this file is now a thin shim over entry_point_shim.run_target ---
from __future__ import annotations

import os
import sys


def main(argv: list[str] | None = None) -> int:
    """Warm-loadable entry point for the native door (DR-347 Ruling 2).

    The door hardlinks itself under this CLI's basename, resolves that name via
    `door.c :: get_own_directory`, and hands it to `invoke.from_argv` as
    `params.entrypoint`; the server then calls THIS function in-process inside
    the already-warm server rather than paying a fresh cmd.exe shim plus a fresh
    Python interpreter per call. The property this removes is a cold interpreter
    start ahead of warmth -- an unenrolled forwarder pays that cost before any
    dispatch decision, against DR-347's ~60ms warm-reach bar; see the enrolment
    commit/plan for the measured before/after on any given box, since those
    numbers are box-specific and stale-by-default.

    Returns an int rather than calling `sys.exit`, because a hard exit inside
    the shared server process would take down a server ~50 concurrent sessions
    are using -- one of the properties `warm_entrypoint_allowlist.json` is the
    fail-closed gate on. All argument interpretation stays in `run_target`;
    this adds no second grammar (DR-347 Ruling 2's negative-spec)."""
    # `argv is None` is unreachable via both real call sites (the door always
    # passes an explicit list; `__main__` below passes sys.argv[1:] explicitly)
    # -- kept only so a direct `main()` call (e.g. from a REPL or test) doesn't
    # need to thread sys.argv itself.
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from entry_point_shim import run_target

    return run_target("merge-assemble", list(sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
