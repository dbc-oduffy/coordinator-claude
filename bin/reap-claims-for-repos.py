# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""reap-claims-for-repos.py — reap orphaned claim dirs via session.reap_claims_for_repos.

Purpose: pure-Python trampoline routing orphaned-claim-dir cleanup through the
coordinator_core session op (`session.reap_claims_for_repos`) via cc_invoke.route()
— no shell, no legacy fallback. Mirrors reap-sessions.py's shape exactly (the
sanctioned op-invoking trampoline pattern in this directory).

Why this exists: sub-reap (iii) — the orphaned-claim-dir cull, an irreversible
`rm -rf` — was cut out of `session.reap`'s `_handler` by PM ruling 2026-08-22
(it fired at boot, the busiest moment) and relocated to the standalone op
`session.reap_claims_for_repos`. The ceremony gate it was relocated TO was
never built, so from 2026-08-22 to 2026-08-26 the op had no caller and
orphaned claim dirs were reaped by nothing. This script is that destination:
wired into the `/workday-complete` and `/workweek-complete` cleanup phases
(`coordinator_core.workday_complete.brief` / `coordinator_core.workweek_complete.brief`),
each a low-traffic end-of-cycle ceremony rather than the busy boot path.

Usage:
    python3 reap-claims-for-repos.py [<repo_root>]

    <repo_root>  Optional; defaults to `git rev-parse --show-toplevel`.

Commit semantics: NO git commit on ANY path. session.reap_claims_for_repos
mutates only untracked `.git/coordinator-sessions/` claim-dir substrate
(Class-B op). No git diff, no git commit.

Transport routing (unconditional native — no legacy fallback): route()
dispatches session.reap_claims_for_repos with `{"target_roots": [repo_root]}`,
with a _no_fallback() legacy_fn that always raises (no bash body to fall
back to). On transport failure (import error, timeout, non-zero op exit)
route() raises; log-and-continue to stderr; exit 0. On transport SUCCESS,
the returned envelope is inspected via cc_invoke.mutation_refusal_message()
(DR-215 exit_code trap) — an in-envelope op-level refusal (non-zero
'exit_code' / non-empty 'error') is logged to stderr rather than silently
discarded, though the "never fail a ceremony" contract still holds: exit 0
either way.

Exit codes:
    0 — normal completion (including transport warn or op-level refusal). A
        cleanup step MUST NOT fail a ceremony; all error paths exit 0.

Negative-spec:
    - Does NOT commit to git on any path.
    - Does NOT pass `force` or any cadence override to the op (let the op
      self-gate).
    - Does NOT print an integer count to stdout.
    - Does NOT fall back to legacy on transport failure (no legacy path
      exists).
    - Does NOT get re-added to `session.reap`'s `_handler` — the 2026-08-22
      PM ruling relocated sub-reap (iii) here permanently; a ratchet test
      (`coordinator_core/ops/session/test_reap.py`) forbids reversal.

Spec backlink: state/sizings/2026-08-26-the-orphaned-claim-reap-gets-the-ceremon.yaml
"""
from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

# Guarded, unlike reap-sessions.py's identical bare import, and for the same
# reason `main` below catches Exception rather than RuntimeError: this module is
# loaded IN-PROCESS by the ceremony apply loop, and
# `ceremony_common.cli_dispatch.load_cli_module` propagates an import-time
# exception uncaught. An unguarded ImportError here would halt
# /workday-complete and /workweek-complete BEFORE `main` is ever called, so
# `main`'s own handler could never see it -- the "exit 0 on every path"
# contract in this module's docstring would be defeated by its own import
# line. reap-sessions.py is safe bare only because it runs as its own
# subprocess under a fail-open hook.
try:
    import cc_invoke  # noqa: E402
    from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402

    _IMPORT_ERROR: Exception | None = None
except Exception as _exc:  # noqa: BLE001 -- see comment above
    cc_invoke = None  # type: ignore[assignment]
    _resolve_claude_klabauter_root = None  # type: ignore[assignment]
    _IMPORT_ERROR = _exc


def _no_fallback() -> None:
    raise RuntimeError(
        "session.reap_claims_for_repos: native seam required (no bash fallback -- big-bang cutover)"
    )


def _resolve_repo_root(argv: list[str]) -> str | None:
    if argv:
        return argv[0]
    try:
        claude_klabauter_root = _resolve_claude_klabauter_root()
        if claude_klabauter_root and claude_klabauter_root not in sys.path:
            sys.path.insert(0, claude_klabauter_root)
        from coordinator_core.git.repo_root import show_toplevel

        return show_toplevel()
    except Exception:
        return None


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if _IMPORT_ERROR is not None:
        # cc_invoke is None here -- without this branch, cc_invoke.route(...)
        # below would raise AttributeError, caught by the broad except and
        # still exiting 0, but reporting the wrong failure to the operator.
        print(
            f"reap-claims-for-repos.py: cc_invoke import failed -- continuing (best-effort): {_IMPORT_ERROR}",
            file=sys.stderr,
        )
        return 0
    repo_root = _resolve_repo_root(argv)
    if repo_root is None:
        print("reap-claims-for-repos.py: cannot resolve git repo root", file=sys.stderr)
        return 0  # best-effort: never block ceremony completion

    try:
        result = cc_invoke.route(
            "session.reap_claims_for_repos",
            {"target_roots": [repo_root]},
            repo_root,
            _no_fallback,
        )
    except Exception as exc:
        # Deliberately broader than reap-sessions.py's `except RuntimeError`,
        # which this module otherwise mirrors. That trampoline is spawned as
        # its own process by a fail-open hook, so an escaping non-RuntimeError
        # (ImportError, OSError, a transport timeout) kills only itself. This
        # one is loaded and called IN-PROCESS by the ceremony apply loop
        # (`ceremony_common.cli_dispatch.invoke_cli_main`), so the same escape
        # would propagate into /workday-complete and /workweek-complete and
        # halt the ceremony -- defeating this module's own "exit 0 on every
        # path" contract. Narrow is correct there and wrong here.
        print(
            f"reap-claims-for-repos.py: session.reap_claims_for_repos failed -- continuing (best-effort): {exc}",
            file=sys.stderr,
        )
        return 0

    message = cc_invoke.mutation_refusal_message("session.reap_claims_for_repos", result)
    if message is not None:
        print(f"reap-claims-for-repos.py: {message} -- continuing (best-effort)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
