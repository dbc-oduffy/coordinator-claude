# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
from __future__ import annotations

import os
import sys


# loaded IN-PROCESS by the ceremony apply loop, and
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
        # one is loaded and called IN-PROCESS by the ceremony apply loop
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
