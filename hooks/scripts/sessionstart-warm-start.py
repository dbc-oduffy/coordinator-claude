"""SessionStart shim — start the warm engine, if this machine opted in.

Discharges the 2026-08-18 warm-engine-SessionStart ask in `cross-repo/inbox/`:
the engine's `session.warm_start` op has been dispatchable and has declared its
own `SESSIONSTART_MATCHERS` since that date, and nothing consumed them. Hook and
discovery surfaces are this repo's by the tri-plane boundary, which is why that
arrived as a memo rather than as a commit here.

Without this entry the engine is only ever spawned lazily, by the first client
that finds no pipe — so the first tool call of every session on the box pays the
full cold spawn. The engine plane measured 540ms on that first hit against 2-3ms
steady-state warm.

    Cost note, stated because it is the obvious objection: this file adds no
    process to boot. It rides `sessionstart-async-dispatch.py`'s existing
    interpreter, whose whole reason for existing is that a second SessionStart
    registration would price another permanent interpreter cold start (~642ms
    fleet-wide) against DR-344's 500ms brightline. A dedicated `hooks.json`
    entry for this op would buy nothing and cost exactly that.

    Negative-spec — this shim decides NOTHING about whether to warm. Opt-in is
    the engine's `warm.settings.is_warm_enabled` single exported answer (the
    `COORDINATOR_WARM` env with falsy always winning, then `engine.warm.enabled`
    in the machine-local registry, then off), read by the op itself. Do not add
    an env check, a registry read, or a "should we" predicate here: a second
    copy of that precedence is a second thing to drift, and this shim cannot see
    the machine-local registry the op reads. If warm appears not to start, the
    answer is in the op or the setting, never here.

    Negative-spec — this shim writes NOTHING to stdout. The op is side-effect
    only (its `{"spawned": bool}` return exists for tests and manual invocation,
    not for us), and the async fan-in re-emits whatever its guards print straight
    into session context. A banner here would put a line about engine plumbing in
    front of the operator on every single session start, forever.

Fails open unconditionally, like every guard in the async fan-in: an
unresolvable engine, an unimportable engine package, a `HookDispatchError` and
any other exception all return 0 silently. A SessionStart hook that raises
greets the whole fleet with a stack trace, and a cold engine is a latency
problem while a wedged boot is an outage.
"""

import sys
from pathlib import Path

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

#: The op's own name for itself. Not spelled anywhere else in this repo — the
#: engine owns the op table, this is the single consumer-side reference.
_OP = "session.warm_start"


def main() -> int:
    try:
        from _engine_root import resolve_claude_klabauter_root
    except Exception:
        return 0

    try:
        root = resolve_claude_klabauter_root()
    except Exception:
        return 0
    if not root:
        return 0  # engine unresolvable on this machine

    if root not in sys.path:
        sys.path.insert(0, root)

    try:
        from coordinator_core.ipc import HookDispatchError, dispatch_from_hook
    except Exception:
        return 0  # engine unimportable -> fail-open silent pass

    # Machine-scoped, not repo-scoped: the op warms THIS engine clone whichever
    # repo's session triggered it, and its handler ignores both `params` and
    # `repo_root`. So no `_origin_worktree` is forwarded and `{}` is complete,
    # not a stub someone should later fill in.
    try:
        dispatch_from_hook(_OP, {})
    except HookDispatchError as exc:
        # The ONE path that gets a breadcrumb. A refused dispatch is not the
        # same as warm being switched off: `is_warm_enabled()` false returns
        # cleanly with {"spawned": false}, so reaching here means the call
        # itself could not be made. The likely cause is the IPC layer's
        # unconditional stamp gate refusing an unstamped `coordinator_core`
        # root, which depends on registry state (`engine.target`,
        # `engine.working_repos.*`) this shim does not control and cannot see.
        # Staying silent here would make the whole feature invisibly inert on
        # any machine whose registry points at an unstamped root -- the exact
        # "nothing was red for five days" shape this file was written to close,
        # reintroduced one layer down. stderr, never stdout: a breadcrumb, not
        # a banner.
        try:
            sys.stderr.write(
                f"[warm-start] {_OP} refused ({type(exc).__name__}) -- the warm "
                "engine is NOT running this session and every op will pay its "
                "cold path. Usually an unstamped engine root; check "
                "`engine.target` and `engine.working_repos.*`.\n"
            )
        except Exception:
            pass
        return 0
    except Exception:
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
