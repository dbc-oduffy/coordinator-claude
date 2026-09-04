"""
group-em-watch.py — CLI trampoline over the engine repo's
coordinator_core.group_em.watch.

WHY THIS EXISTS. The standing Group EM watch is armed FROM the repo it
watches, by an agent dispatched in that repo — and `python -m
coordinator_core.group_em.watch` only resolves from a cwd whose interpreter
can already import the engine. From any other repo it is a
`ModuleNotFoundError` at start-up, and a watcher whose subprocess never
started presents to the Group-EM as `idle`: indistinguishable from a quiet
fleet, no error anywhere. Measured 2026-09-01 from `<example-game-repo-root>`
(cross-repo/inbox/2026-09-01-example-game-repo-em-group-em-fleet-watch-wake-on-session-state.md);
the group-em skill body named the gap in prose ("there is no settings-home
`group-em-watch` launcher yet") and prose is not a launcher.

This is that launcher. It resolves CLAUDE_KLABAUTER_ROOT the way every other bin
trampoline does, so the arm form is `group-em-watch --repo-root <root>
--group-em-session-id <sid>` from anywhere on PATH.

Three modes, all forwarded verbatim to the module's own `_cli`:
  - default: hold the poll loop for the life of the session (`Monitor`).
  - `--once`: one tick against the carried parked map, then exit — the form a
    cron floor or a session-state wake fires, holding nothing between wakes.
  - `--status`: answer "is a watch alive here?" in plain words and exit,
    watching nothing. This is the human-facing half of the defect above: the
    engine could already tell a live-but-quiet watch from a dead one and from a
    repo nobody ever armed, but the only surface a person had said `idle` for
    all three. Exit 0 alive, 1 not running, 2 unknown — unknown is never green.

Cold path — one process, one call. Direct in-process import + call, not
cc_invoke()/route(): the long-running mode IS the process, so there is no
JSON-RPC transport to put under it.
"""

from __future__ import annotations

import sys


def _import_cli():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    require_dispatch_engine_on_path()
    from coordinator_core.group_em.watch import _cli as _watch_cli
    return _watch_cli


def main(argv: "list[str] | None" = None) -> int:
    try:
        watch_cli = _import_cli()
    except RuntimeError as exc:
        print(f"group-em-watch.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return 1
    except ImportError as exc:
        print(f"group-em-watch.py: coordinator_core.group_em.watch not importable: {exc}", file=sys.stderr)
        return 1
    return watch_cli(sys.argv[1:] if argv is None else argv)


if __name__ == "__main__":
    sys.exit(main())
