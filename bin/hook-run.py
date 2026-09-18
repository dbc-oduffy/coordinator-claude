# Unix shebang not required here: never installed by byte copy (see
# claude-doe.py's own header for that contract); this file is invoked
# either as `coordinator/bin/hook-run.py` directly (python3 <path>) or
# resolved as the door's cold fall-through image, which always execs it
# under an explicit interpreter, never relies on execve(2).
"""
coordinator/bin/hook-run.py — the ONE command-door entrypoint for every
`hooks.<name>` op DoE registers (W4-C16, docs/plans/2026-09-18-doe-holds-no-
scripts.md).

The W4-C1 verdict chose command/native-door for wave 4's hook bodies, and the
door resolves only `coordinator/bin/<name>.py` — never a hook-body module
under `coordinator_core/hooks/` directly. This file IS that one resolved
image: DoE registers every wave-4 hook as `<settings-bin>/hook-run
hooks.<name>`, so `hooks.<name>` travels as argv[1] rather than each hook
growing its own `coordinator/bin/<name>.py` shim.

Contract:
    argv[1]   — the op to dispatch. MUST start with "hooks." — refused
                (exit 2, nothing on stdout) for anything else, so a
                registration typo can never reach an unrelated op through
                this door.
    stdin     — the harness's own hook event JSON (session_id, cwd,
                hook_event_name, tool_name, tool_input, ...), same shape
                every existing cold hook script already reads.
    stdout    — the hook response envelope, rendered through the SAME
                translation `coordinator_core/warm/hook_http.py` applies
                over its own transport:
                  - `payload_from_event` builds the op's `params.payload`
                    from the raw event (env-diet forwarding, computed
                    `plugin_root`) — imported, never re-derived, so a
                    command-door fire and a warm-http fire see the same
                    payload shape for the same event.
                  - `unreachable_response` / `is_blocking_event` render the
                    "guard did not run" envelope on a dispatch failure — the
                    module's own obligation 3: a guard that cannot run must
                    never read as a guard that passed.
    exit code — 0 on every dispatch outcome except the two argv-contract
                refusals above (missing/non-"hooks." argv[1], unknown op).
                The verdict itself always travels in the JSON body, never in
                the exit code: `hooks.*` op handlers already return the full
                harness envelope (`_hook_envelope.py`'s shape builders), so
                there is no second, exit-code-encoded copy of the decision
                to keep in sync with the body.

Dispatch is IN PROCESS via `coordinator_core.ipc.dispatch_from_hook` — never
`coordinator/bin/lib/cc_invoke.py`'s `cc_invoke`, which spawns a SECOND cold
interpreter to reach the engine. This file already runs under the resolved
engine's own interpreter (via `require_dispatch_engine_on_path`'s sys.path
splice), so a subprocess spawn here would reintroduce exactly the
per-fire cold-interpreter tax this plan exists to retire.

No per-hook shim, no http registration: `warm_guard.evaluate` and this
file's `hooks.*` dispatch are deliberately separate paths (http fails open
on a blocking guard and is never dialled for SessionStart — see W4-C1's
verdict artifact); a hook landing on the command/native-door shape reaches
its op through this one file, unconditionally.

Spec backlink: docs/plans/2026-09-18-doe-holds-no-scripts.md § W4-C16, W4-C1
"""

from __future__ import annotations

import json
import sys


def _read_event() -> dict:
    """Parse the harness's hook event JSON off stdin.

    An empty or unparsable stdin degrades to `{}` rather than raising —
    the payload-building translation below (`payload_from_event`) already
    tolerates a missing field per-key (`setdefault(key, None)`), so a
    malformed event still reaches the op as a mostly-empty payload instead
    of taking the whole dispatch down before the op gets a chance to answer
    with its own `unreachable_response`-shaped verdict.
    """
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        obj = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return {}
    return obj if isinstance(obj, dict) else {}


def main(argv: "list[str] | None" = None) -> int:
    args = sys.argv[1:] if argv is None else argv[1:]
    if not args or not args[0].startswith("hooks."):
        sys.stderr.write(
            "hook-run: refuses op %r -- only \"hooks.<name>\" ops are servable "
            "through this door.\n" % (args[0] if args else None)
        )
        return 2

    op_name = args[0]

    try:
        import lib  # noqa: F401 -- bootstraps coordinator/bin/lib onto sys.path
        from cc_invoke import require_dispatch_engine_on_path

        require_dispatch_engine_on_path()
        from coordinator_core.ipc import HookDispatchError, dispatch_from_hook
        from coordinator_core.warm.hook_http import (
            is_blocking_event,
            payload_from_event,
            unreachable_response,
        )
    except (RuntimeError, ImportError) as exc:
        sys.stderr.write("hook-run: %s: engine unreachable (%s)\n" % (op_name, exc))
        return 2

    event = _read_event()
    event_name = event.get("hook_event_name")
    params = {"payload": payload_from_event(event)}

    try:
        result = dispatch_from_hook(op_name, params)
    except HookDispatchError as exc:
        # Same obligation `hook_http.py` itself carries for its own transport:
        # a guard that could not run must never read as one that passed.
        # `is_blocking_event` is consulted for parity with that module's own
        # accounting only -- the response shape (and the exit code) are the
        # same either way, per this file's own docstring.
        _ = is_blocking_event(event_name)
        sys.stdout.write(json.dumps(unreachable_response(event_name, str(exc))))
        sys.stdout.write("\n")
        sys.stderr.write("hook-run: %s: %s\n" % (op_name, exc))
        return 0

    sys.stdout.write(json.dumps(result))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
