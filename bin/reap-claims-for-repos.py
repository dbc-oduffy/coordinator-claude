# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
from __future__ import annotations

import os
import sys


# Guarded, unlike reap-sessions.py's identical bare import, and for the same
# reason `main` below catches Exception rather than RuntimeError: this module is
# loaded IN-PROCESS by the ceremony apply loop, and
# `ceremony_common.cli_dispatch.load_cli_module` propagates an import-time
# exception uncaught. An unguarded ImportError here would halt
# /workday-complete and /workweek-complete BEFORE `main` is ever called, so
# `main`'s own handler could never see it -- the "exit 0 on every path"
# contract in this module's docstring would be defeated by its own import
# line. reap-sessions.py is safe bare only because it runs as its own
# subprocess under a fail-open hook. The import itself now runs inside
# `_try_import_cc_invoke`, called from `main` -- `load_cli_module` never
# executes it at module-load time, only `main` does, and `main` still guards
# it with the identical try/except, so the "exit 0 on every path" contract is
# unchanged.
def _try_import_cc_invoke():
    try:
        import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
        import cc_invoke
        from cc_invoke import _resolve_claude_klabauter_root

        return cc_invoke, _resolve_claude_klabauter_root, None
    except Exception as _exc:  # noqa: BLE001 -- see comment above
        return None, None, _exc


def _no_fallback() -> None:
    raise RuntimeError(
        "session.reap_claims_for_repos: native seam required (no bash fallback -- big-bang cutover)"
    )


def _resolve_repo_root(argv: list[str], resolve_claude_klabauter_root) -> str | None:
    if argv:
        return argv[0]
    try:
        claude_klabauter_root = resolve_claude_klabauter_root()
        if claude_klabauter_root and claude_klabauter_root not in sys.path:
            sys.path.insert(0, claude_klabauter_root)
        from coordinator_core.git.repo_root import show_toplevel

        return show_toplevel()
    except Exception:
        return None


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    cc_invoke, _resolve_claude_klabauter_root, _import_error = _try_import_cc_invoke()
    if _import_error is not None:
        print(
            f"reap-claims-for-repos.py: cc_invoke import failed -- continuing (best-effort): {_import_error}",
            file=sys.stderr,
        )
        return 0
    repo_root = _resolve_repo_root(argv, _resolve_claude_klabauter_root)
    if repo_root is None:
        print("reap-claims-for-repos.py: cannot resolve git repo root", file=sys.stderr)
        return 0

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
