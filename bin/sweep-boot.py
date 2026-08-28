# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""sweep-boot.py — GRAVESTONE for session.boot_sweep, plus boot-time forwarder self-heal.

This entrypoint used to trampoline `session.boot_sweep`: ONE cold-start covering
four boot-time archival classes (consumed handoffs, terminal plans, shipped
handoffs, actioned memos). That op is KILLED, not suspended — it measured
30017ms against a 2000ms bar, 8 of 8 calls ending in caller_timeout — and the
kill bar means kill forever. The dial could only ever refuse.

What the dial cost, measured rather than supposed: 49 refusals in 28 hours in
Claude-klabauter and 32 in DoE-claude, from 55 distinct sessions, one per session
boot. The cost was never just the wasted call. The refusal came back through
`route_mutation`, whose warm client blocks up to 15s waiting for a respawned
server before it can deliver the error — so every session on a ~50-session box
paid that wait, at boot, to be told about an op that cannot come back. The
`_record_housekeeping_failure` call on that path then wrote a CHILD-FAILED
record every boot, which is how the shared housekeeping log filled with news
about a permanently-dead op and stopped being readable for anything else.

WHY NOTHING REPLACES IT. The kill bar requires naming the requirement rather
than assuming it: *does anything still need this job done?* Measured, not
argued — across the same 28 hours in which this composite was 100% dead, the
repo landed 368 archival commits (consumed handoffs, superseded handoffs,
terminal plans). They went through the per-artifact lifecycle ops that
registered while the composite did not: `handoff.archive_transition`,
`handoff.ship_and_archive`, `handoff.close_origin_stub`,
`fleet.archive_completed_handoffs`, `fleet.archive_terminal_sizings`. The four
classes are archived on the paths that create them, which is where the work
belongs; sweeping the whole corpus at boot was the shape that could not meet
the bar in the first place.

If a boot-time archival sweep is ever wanted again it is a NEW plan, spiked,
written from first principles under 500ms — never a repoint of this file.
`test_sweep_boot.py` fails any edit that reintroduces a dispatch here.

WHAT STAYS, and why this file is not simply deleted: the SessionStart hook that
fires this trampoline is owned in the coordinator-claude plane, not here, so
deleting the entrypoint would require a coordinated cross-repo edit to retire a
call that is now free. It also still does real boot work that was never the
killed op's: resolving the dispatch engine root and self-healing the bare-name
forwarders (`coordinator_core.install.forwarder_self_heal`).

Usage:
    python sweep-boot.py [<repo_root>] [<state_common_dir>]

    Both positionals are accepted and ignored. They are retained rather than
    rejected because the hook passes them today; refusing them would turn a
    free no-op into a boot-time error for no gain.

Stdout contract: one INTEGER, always — now always `0`. Byte-parity with the
retired bash oracle, and with the dispatch version's own transport-failure
path. The hook parses this.

Exit codes:
    0 — always. Best-effort ceremony, never a boot-blocking gate.

Negative-spec: never dispatches an op, never stages, never commits, never
spawns bash, and writes no housekeeping-failure record — a dead op refusing is
not news, and recording it every boot is what made the real signal unreadable.

Spec backlink: pln-strang-11-b8-session-init-boot-f78455 § C2 / AC7
Spec backlink: docs/plans/2026-07-19-debash-coordinator-windows.md § Pinned pattern, Wave 1b
→ docs/research/2026-08-26-the-ceremony-budget-is-spent-on-one-git-status.md
"""
from __future__ import annotations

import os
import sys

_BIN_DIR = os.path.dirname(os.path.abspath(__file__))

_USAGE = "usage: python sweep-boot.py [-h] [<repo_root>] [<state_common_dir>]"


def main(argv: list[str] | None = None) -> int:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path
    from sweep_argv import parse_repo_root_argv

    argv = sys.argv[1:] if argv is None else argv
    _positional, _flags, early_exit = parse_repo_root_argv(
        argv, prog="sweep-boot.py", usage=_USAGE, max_positional=2
    )
    if early_exit is not None:
        return early_exit

    # Best-effort, and deliberately so: the forwarder self-heal is worth doing at
    # boot but is not worth failing boot over, and this entrypoint's exit-0
    # contract predates it. A divergent engine root (the common case in a
    # test interpreter that already bound `coordinator_core` from a working tree)
    # raises here and is not this file's problem to resolve.
    try:
        require_dispatch_engine_on_path()
        from coordinator_core.install.forwarder_self_heal import self_heal_forwarders

        self_heal_forwarders()
    except Exception:  # noqa: BLE001 -- see above; never block session boot
        pass

    print("0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
