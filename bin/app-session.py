# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""app-session.py — bareword CLI trampoline over app_session.launch / .census / .teardown.

Purpose: `coordinator_core/ops/app_session.py` registers three ops
(`app_session.launch`, `app_session.census`, `app_session.teardown`) that
start, inspect, and stop a local dev app in whatever consuming repo the
operator is sitting in — but, prior to this file, none of them had a
bareword `coordinator/bin/` entrypoint to invoke through, the same shape gap
`advance-tracker-status.py`'s own module docstring describes for its op
(see this file's own Spec backlink below for the peer repo's request). This
file is that trampoline — ONE binary, THREE verbs,
single dispatch through `coordinator/bin/lib/cc_invoke.py`'s `route()` for
each — no shell, no bash re-exec, no local mirror of the op's config-
resolution / runtime-resolution / handle-persistence mechanics (those live
entirely in `coordinator_core/ops/app_session.py`, reused unchanged).

Usage:
    python3 app-session.py launch --key <k> [--repo-root <path>]
    python3 app-session.py census [--key <k>] [--repo-root <path>]
    python3 app-session.py teardown --key <k> [--repo-root <path>]
    python3 app-session.py validate --key <k> [--variant <v>] [--out <dir>]
                                    [--wait <seconds>] [--repo-root <path>]

    validate calls app_session.validate, then polls the run dir's result.json
    and prints it as indented, key-sorted JSON. --wait (integer seconds) re-calls the op every 2 s
    while it refuses with stage "guard". On a poll lapse it tears down
    "<key>@validate" and prints an ok:false stage "sweep" timeout result.

    launch/teardown/validate require --key; census's --key is optional (omitted lists
    every persisted handle in the consuming repo — see the op's own
    docstring). --repo-root is optional on every verb; when omitted it
    defaults the same way advance-tracker-status.py's own <repo_root>
    positional does: `git rev-parse --show-toplevel`.

Result shape: the op's OWN result object, printed verbatim as JSON to
stdout — this trampoline does not reshape, prettify, or re-key it. A
"not configured" result (`{"ok": true, "configured": false, ...}` — see
app_session.py's DP-2 / `_absent_key_result`) is a SUCCESSFUL dispatch: the
op reached a genuine "nothing to do here" state, not an error, and the
consumer's skill renders it as a silent no-op. Do NOT "fix" this into a
non-zero exit — a later reader mistaking `configured: false` for a failure
would be reintroducing exactly the loud-on-absence behavior DP-2's own
docstring explains `app_session` deliberately does NOT want (unlike
`fast_test_cmd`'s absent-key case, which fails loud by design).

Exit codes (locally scoped to this CLI, NOT inherited from the op's own
response shape, which carries no error signal of its own beyond its `ok`
field):
    0 — OK, dispatch succeeded. This includes a structured "not configured"
        result (`ok: true, configured: false`) — see Result shape above.
    2 — usage error (missing verb, missing required --key on launch/
        teardown, unrecognized verb/argument, or repo_root unresolvable).
    3 — transport/op failure (the engine root unresolvable, coordinator_core.
        invoke seam absent, or the op itself raised).
    validate only:
    4 — the sweep finished with defect_count > 0.
    5 — the result is ok:false (refusal, incomplete run) or the wait lapsed.

Spec backlink: cross-repo/inbox/2026-08-15-*-app-session-ops-need-a-cli-entrypoint.md
Spec backlink: claude-klabauter coordinator_core/ops/app_session.py

Negative-spec: does NOT re-implement config resolution, runtime resolution,
argv-splitting, handle persistence, or PID/create-time liveness
re-validation — those are entirely the op's (`_launch` / `_census` /
`_teardown` and their shared helpers in `coordinator_core/ops/app_session.py`).
Does NOT fall back to a legacy shell body on seam-absent — the op is the
only implementation; a seam-absent install is a genuine transport failure
(exit 3), never silently routed to a retired shell body (there never was
one).
"""
from __future__ import annotations

import json
import os
import sys
import time

_sleep = time.sleep
_monotonic = time.monotonic

_USAGE_FAIL = 2
_TRANSPORT_FAIL = 3

_BOOTSTRAP_DONE = False

_BOOTSTRAPPED_NAMES = ("cc_invoke",)


def _bootstrap_engine() -> None:
    global _BOOTSTRAP_DONE
    if _BOOTSTRAP_DONE:
        return
    global cc_invoke
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    import cc_invoke

    cc_invoke.ensure_engine_on_path(__file__)
    _BOOTSTRAP_DONE = True


def __getattr__(name: str):
    """PEP 562 hook so a caller reaching for `cc_invoke` before `main()` has
    run -- a test monkeypatching `_cli_mod.cc_invoke` -- triggers
    `_bootstrap_engine()` lazily instead of finding the name absent.

    NEGATIVE SPEC -- the forced re-run is not belt-and-braces.
    `_bootstrap_engine()` short-circuits on `_BOOTSTRAP_DONE`, so a name
    that leaves `__dict__` AFTER the bootstrap has run is never rebound by
    a plain call. `mock.patch.object` does exactly that: it reads the name
    through this hook (so the value is not in `__dict__` at enter), sets
    its mock, and on exit `delattr`s rather than restoring -- then probes
    `hasattr`, which lands here with the flag already set. Without the
    reset that probe raises KeyError instead of returning the name.
    """
    if name in _BOOTSTRAPPED_NAMES:
        _bootstrap_engine()
        if name not in globals():
            global _BOOTSTRAP_DONE
            _BOOTSTRAP_DONE = False
            _bootstrap_engine()
        try:
            return globals()[name]
        except KeyError:
            raise AttributeError(
                f"module {__name__!r} has no attribute {name!r}"
            ) from None
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

_VERBS = {
    "launch": "app_session.launch",
    "census": "app_session.census",
    "teardown": "app_session.teardown",
    "validate": "app_session.validate",
}
_KEY_REQUIRED_VERBS = ("launch", "teardown", "validate")
_VALIDATE_DEFECTS = 4
_VALIDATE_INCOMPLETE = 5
_GUARD_RETRY_S = 2
_RESULT_POLL_S = 1


def _resolve_repo_root(explicit: str | None) -> str | None:
    if explicit:
        return explicit
    from coordinator_core.git.repo_root import show_toplevel

    return show_toplevel()


def _no_fallback() -> None:
    raise RuntimeError(
        "app-session: native seam required (no legacy fallback -- "
        "app_session.launch/.census/.teardown are the only implementation, "
        "see module docstring)"
    )


def _usage(prog: str, stream=None) -> int:
    print(
        f"{prog}: usage: {prog} launch --key <k> [--repo-root <path>]\n"
        f"       {prog} census [--key <k>] [--repo-root <path>]\n"
        f"       {prog} teardown --key <k> [--repo-root <path>]\n"
        f"       {prog} validate --key <k> [--variant <v>] [--out <dir>] [--wait <seconds>] [--repo-root <path>]",
        file=stream or sys.stderr,
    )
    return _USAGE_FAIL


def _emit(result: dict) -> None:
    print(json.dumps(result, indent=2, sort_keys=True))


def _validate_exit(result: dict) -> int:
    if result.get("ok") is False:
        return _VALIDATE_INCOMPLETE
    defects = result.get("defect_count")
    if isinstance(defects, int) and defects > 0:
        return _VALIDATE_DEFECTS
    return 0


def _run_validate(prog: str, params: dict, repo_root: str, key: str, wait_s: int) -> int:
    """Call app_session.validate, poll its run_dir for result.json, map exit 0/4/5."""
    op = _VERBS["validate"]
    deadline = _monotonic() + wait_s
    try:
        while True:
            result = cc_invoke.route(op, params, repo_root, _no_fallback)
            refused_on_guard = (
                result.get("ok") is False and result.get("stage") == "guard"
            )
            if not refused_on_guard or _monotonic() + _GUARD_RETRY_S > deadline:
                break
            _sleep(_GUARD_RETRY_S)

        if not result.get("started"):
            _emit(result)
            return _validate_exit(result)

        from coordinator_core.ops._app_session_validate_contract import read_result

        run_dir = result["run_dir"]
        poll_deadline = _monotonic() + float(result.get("wait_budget_s") or 0)
        while True:
            final = read_result(run_dir)
            if final is not None:
                _emit(final)
                return _validate_exit(final)
            if _monotonic() >= poll_deadline:
                break
            _sleep(_RESULT_POLL_S)

        try:
            cc_invoke.route(
                _VERBS["teardown"],
                {"repo_root": repo_root, "key": f"{key}@validate"},
                repo_root,
                _no_fallback,
            )
        except RuntimeError as exc:
            print(f"{prog}: teardown of {key}@validate failed: {exc}", file=sys.stderr)
        _emit(
            {
                "ok": False,
                "configured": True,
                "stage": "sweep",
                "error": f"timeout: no result.json after {result.get('wait_budget_s')}s",
                "run_dir": run_dir,
            }
        )
        return _VALIDATE_INCOMPLETE
    except RuntimeError as exc:
        print(f"{prog}: {op} failed (transport error): {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    prog = "app-session"

    if "--help" in argv or "-h" in argv:
        _usage(prog, stream=sys.stdout)
        return 0

    _bootstrap_engine()

    if not argv:
        return _usage(prog)

    verb = argv[0]
    if verb not in _VERBS:
        print(f"{prog}: unrecognized verb {verb!r}", file=sys.stderr)
        return _usage(prog)

    key = None
    repo_root_arg = None
    variant = None
    out_dir = None
    wait_raw = None
    rest = argv[1:]
    i = 0
    unrecognized: list[str] = []
    while i < len(rest):
        tok = rest[i]
        if tok == "--key" and i + 1 < len(rest):
            key = rest[i + 1]
            i += 2
        elif tok == "--repo-root" and i + 1 < len(rest):
            repo_root_arg = rest[i + 1]
            i += 2
        elif verb == "validate" and tok == "--variant" and i + 1 < len(rest):
            variant = rest[i + 1]
            i += 2
        elif verb == "validate" and tok == "--out" and i + 1 < len(rest):
            out_dir = rest[i + 1]
            i += 2
        elif verb == "validate" and tok == "--wait" and i + 1 < len(rest):
            wait_raw = rest[i + 1]
            i += 2
        else:
            unrecognized.append(tok)
            i += 1

    if unrecognized:
        print(f"{prog}: unrecognized extra argument(s) {unrecognized!r}", file=sys.stderr)
        return _usage(prog)

    if verb in _KEY_REQUIRED_VERBS and not key:
        print(f"{prog}: {verb} requires --key", file=sys.stderr)
        return _usage(prog)

    repo_root = _resolve_repo_root(repo_root_arg)
    if repo_root is None:
        print(f"{prog}: cannot resolve git repo root", file=sys.stderr)
        return _usage(prog)

    wait_s = 0
    if wait_raw is not None:
        try:
            wait_s = int(wait_raw)
        except ValueError:
            wait_s = -1
        if wait_s < 0:
            print(f"{prog}: --wait requires a non-negative integer", file=sys.stderr)
            return _usage(prog)

    params: dict = {"repo_root": repo_root}
    if key:
        params["key"] = key

    if verb == "validate":
        if variant:
            params["variant"] = variant
        if out_dir:
            params["out_dir"] = out_dir
        return _run_validate(prog, params, repo_root, key, wait_s)

    op = _VERBS[verb]
    try:
        result = cc_invoke.route(op, params, repo_root, _no_fallback)
    except RuntimeError as exc:
        print(f"{prog}: {op} failed (transport error): {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
