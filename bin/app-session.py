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

    launch/teardown require --key; census's --key is optional (omitted lists
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

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
import cc_invoke  # noqa: E402

cc_invoke.ensure_engine_on_path(__file__)

_USAGE_FAIL = 2
_TRANSPORT_FAIL = 3

_VERBS = {
    "launch": "app_session.launch",
    "census": "app_session.census",
    "teardown": "app_session.teardown",
}
_KEY_REQUIRED_VERBS = ("launch", "teardown")


def _resolve_repo_root(explicit: str | None) -> str | None:
    """Repo root — accept as an explicit --repo-root value or resolve from git.

    Returns None (never raises) on resolution failure, mirroring
    advance-tracker-status.py's own posture.
    """
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


def _usage(prog: str) -> int:
    print(
        f"{prog}: usage: {prog} launch --key <k> [--repo-root <path>]\n"
        f"       {prog} census [--key <k>] [--repo-root <path>]\n"
        f"       {prog} teardown --key <k> [--repo-root <path>]",
        file=sys.stderr,
    )
    return _USAGE_FAIL


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    prog = "app-session"

    if not argv:
        return _usage(prog)

    verb = argv[0]
    if verb not in _VERBS:
        print(f"{prog}: unrecognized verb {verb!r}", file=sys.stderr)
        return _usage(prog)

    key = None
    repo_root_arg = None
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

    params: dict = {"repo_root": repo_root}
    if key:
        params["key"] = key

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
