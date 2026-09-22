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
    exit code — 0 on every dispatch outcome, an unimportable engine included
                (a loud pass, see `_engine_down_pass`), except the two
                argv-contract refusals above (missing/non-"hooks." argv[1],
                unknown op).
                The verdict itself always travels in the JSON body, never in
                the exit code: `hooks.*` op handlers already return the full
                harness envelope (`_hook_envelope.py`'s shape builders), so
                there is no second, exit-code-encoded copy of the decision
                to keep in sync with the body.

`--check-all` verb (batch registration verification, no dispatch of any
kind): `hook-run --check-all` reads op names from stdin, one per line, or
from `@<file>` when argv[1] is `@<path>`; blank lines and `#`-prefixed
comments are ignored. Each name is resolved against the installed engine's
registry (`coordinator_core.ops._registry_map.resolves`) WITHOUT dispatching
it — no op body ever runs, no hook fires. This answers "is this name
registered", not "does this hook work": registration is a necessary
precondition for a hook to fire at all, but a registered op can still refuse
at runtime for reasons `--check-all` never probes (a required payload field
absent, a scope gate, etc.) — resolving is not a claim that every resolved
op executes cleanly. Exit codes:
    0 — every name resolves (a summary line on stdout states the count and
        repeats the registration-is-not-execution boundary).
    2 — engine resolved, one or more names do not (or a name does not start
        with "hooks." — also reported as unresolved rather than crashing).
        A real finding: the caller (DoE's pre-commit gate) blocks on this.
        Each unresolved name is printed on stdout, one per line.
    3 — infrastructure failure, not a finding: the engine root itself is
        unresolvable, the resolved engine is missing the registry-
        introspection module (a stale/unreachable mirror), or the probe
        raised for any other reason. The caller warns rather than blocks —
        collapsing this onto exit 2 would block a commit that is in fact
        correct over a broken mirror, and the only escape from a gate that
        cries wolf on its own infrastructure is disabling it, which is worse
        than not having the gate. Distinct stderr text per cause.
Both the 2 and 3 paths print the resolved engine root and its sha on
stderr, so a failure is attributable to a tree.

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
import os
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


def _engine_down_pass(event_name: "str | None", detail: str) -> dict:
    """`hook_http.unreachable_response`'s shape, inlined because that module is
    what failed to import. An unreachable engine PASSES LOUDLY, never denies:
    these guards are ergonomics, and a deny here walls off every tool call on
    the box (DoE-claude coordinator/docs/wiki/coordinator-tripwires/
    an-unreachable-engine-passes-loudly-never-denies.md). `systemMessage`
    reaches the operator and `additionalContext` the model, so an unrun guard
    never reads as one that passed. `SessionEnd` refuses `hookSpecificOutput`
    (`hook_http.EVENTS_REJECTING_HOOK_SPECIFIC_OUTPUT`)."""
    body: dict = {
        "systemMessage": "coordinator: guard did not run (engine unreachable: %s)" % detail,
        "suppressOutput": False,
    }
    if event_name != "SessionEnd":
        body["hookSpecificOutput"] = {
            "hookEventName": event_name,
            "additionalContext": "A coordinator guard for %s could not be evaluated "
            "(engine unreachable: %s). It did not pass -- it did not run." % (event_name, detail),
        }
    return body


def _read_check_all_names(args: "list[str]") -> "tuple[list[str], int]":
    """Read the batch of op names for `--check-all`: stdin, or `@<file>` when
    argv[1] names one. Returns `(names, 0)` on success or `([], 3)` on a
    read failure (infrastructure, not a finding -- an unreadable `@<file>`
    is treated the same as a probe failure, never as "0 names, all resolve").
    Blank lines and `#`-prefixed comments are dropped.
    """
    if args and args[0].startswith("@"):
        path = args[0][1:]
        try:
            with open(path, "r", encoding="utf-8") as handle:
                raw = handle.read()
        except OSError as exc:
            sys.stderr.write("hook-run --check-all: could not read %r: %s\n" % (path, exc))
            return [], 3
    else:
        raw = sys.stdin.read()

    names = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        names.append(line)
    return names, 0


def _resolve_engine_identity() -> "tuple[str, str | None]":
    """Resolve the dispatch engine root and its sha, for attributing a
    `--check-all` failure to a tree. Import-local: this module's own
    top-level import block only reaches the engine on a real `hooks.*`
    dispatch, and `--check-all` must resolve identity even when the engine
    root itself is the thing that fails to resolve.
    """
    import lib  # noqa: F401 -- bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    root = require_dispatch_engine_on_path()
    from coordinator_core.engine_version import resolve_engine_sha

    sha = resolve_engine_sha()
    return root, sha


def _engine_identity_line(root: str, sha: "str | None") -> str:
    sha_display = sha[:12] if sha else "<unresolved>"
    return "hook-run --check-all: engine root %s (sha %s)" % (root, sha_display)


def _check_all(args: "list[str]") -> int:
    """`--check-all`: resolve every `hooks.<name>` op name given on stdin or
    `@<file>` against the installed engine's registry, WITHOUT dispatching
    any of them -- no op body runs. See the module docstring's `--check-all`
    section for the exit-code contract and the registration-vs-execution
    boundary this verb deliberately does not cross.
    """
    names, rc = _read_check_all_names(args)
    if rc:
        return rc

    try:
        root, sha = _resolve_engine_identity()
    except RuntimeError as exc:
        sys.stderr.write("hook-run --check-all: engine root unresolvable: %s\n" % exc)
        return 3
    except ImportError as exc:
        sys.stderr.write("hook-run --check-all: engine mirror unreachable: %s\n" % exc)
        return 3

    try:
        from coordinator_core.ops._registry_map import resolves
    except ImportError as exc:
        sys.stderr.write("hook-run --check-all: engine mirror unreachable: %s\n" % exc)
        sys.stderr.write(_engine_identity_line(root, sha) + "\n")
        return 3

    unresolved = []
    try:
        for name in names:
            if not name.startswith("hooks.") or not resolves(name):
                unresolved.append(name)
    except Exception as exc:  # noqa: BLE001 -- probe failure is infrastructure (exit 3), not a finding
        sys.stderr.write("hook-run --check-all: probe failed: %s\n" % exc)
        sys.stderr.write(_engine_identity_line(root, sha) + "\n")
        return 3

    if unresolved:
        for name in unresolved:
            sys.stdout.write(name + "\n")
        sys.stderr.write(_engine_identity_line(root, sha) + "\n")
        return 2

    sys.stdout.write(
        "hook-run --check-all: %d name(s) resolved (registration only -- "
        "not a proof any op executes cleanly)\n" % len(names)
    )
    return 0


def main(argv: "list[str] | None" = None) -> int:
    args = sys.argv[1:] if argv is None else argv[1:]
    if args and args[0] == "--check-all":
        return _check_all(args[1:])
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
        from coordinator_core.op_scopes import WORKTREE_SCOPED_OPS
        from coordinator_core.git.repo_root import show_toplevel
        from coordinator_core.warm.hook_http import (
            is_blocking_event,
            payload_from_event,
            unreachable_response,
        )
    except (RuntimeError, ImportError) as exc:
        sys.stderr.write("hook-run: %s: engine unreachable (%s)\n" % (op_name, exc))
        sys.stdout.write(json.dumps(_engine_down_pass(_read_event().get("hook_event_name"), str(exc))))
        sys.stdout.write("\n")
        return 0

    event = _read_event()
    event_name = event.get("hook_event_name")
    # The event carries no env; this process's env is the caller's on both
    # legs (cold: the hook's own process; served: the isolated borrow bound
    # the caller's prefixed names -- see entry_seam._environ_identity_borrow).
    if not isinstance(event.get("env"), dict):
        event = {**event, "env": dict(os.environ)}
    params = {"payload": payload_from_event(event)}

    # A worktree-scoped op REQUIRES `_origin_worktree` and refuses (-32602)
    # without it; `coordinator_core/invoke/__main__.py` injects it for the
    # cold path, so this door must too or it fails open instead of running.
    #
    # NEGATIVE SPEC: `show_toplevel` WALKS ONLY, never spawns -- a spawn here
    # would be break-class on a PreToolUse hot path. Inject ONLY for ops in
    # `WORKTREE_SCOPED_OPS` (that set's parity-check contract clause (1)) --
    # never stamp a central/none-scoped op. An unresolvable worktree passes
    # None, which `dispatch_from_hook` omits rather than carrying as "".
    origin_worktree = None
    if op_name in WORKTREE_SCOPED_OPS:
        event_cwd = event.get("cwd")
        if isinstance(event_cwd, str) and event_cwd:
            origin_worktree = show_toplevel(event_cwd)

    try:
        result = dispatch_from_hook(op_name, params, origin_worktree=origin_worktree)
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
    sys.stdout.flush()
    _ask_for_the_engine_back()
    return 0


def _ask_for_the_engine_back() -> None:
    """Cold only: the warm door fell through to this process because it could
    not reach the engine, so ask for it back, or every later hook pays this
    interpreter start too. Served in-engine there is nothing to ask for.

    A ping through `warm.client.try_warm_dispatch` rather than a spawn of our
    own: that seam already owns the whole policy (spawn only on an absent
    server, debounced across processes, never on a contended one, never from
    test traffic), and a second copy of it here would drift. Best-effort:
    the verdict is already written, so nothing here may fail the hook.
    """
    if os.environ.get("COORDINATOR_EXECUTION_ROUTE") == "warm_server":
        return
    try:
        from coordinator_core.warm.client import try_warm_dispatch

        try_warm_dispatch({"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {}})
    except Exception:  # noqa: BLE001 -- see docstring: never fail a written verdict
        pass


if __name__ == "__main__":
    sys.exit(main())
