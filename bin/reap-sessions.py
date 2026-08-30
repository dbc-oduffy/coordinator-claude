# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""reap-sessions.py — reap stale session substrate via session.reap.

Purpose: pure-Python replacement for the retired bash strangler-finish
wrapper — Port of: reap-sessions.sh (DoE f703efad, 2026-07-21). Routes stale-session cleanup through the
coordinator_core session op (`session.reap`) via cc_invoke.route() — no
shell, no legacy fallback (the bash oracle itself dispatched session.reap
unconditionally-native with no legacy_fn; this port matches that posture).

Review: code-reviewer / the Staff Engineer — the legacy cs_reap_stale / cs_reap_agents /
cs_reap_stale_claims trio (formerly coordinator/lib/coordinator-session.sh,
coordinator/lib/session/scope.sh) was SUPERSEDED here before being deleted
(session-family-repoint C4a, 2026-07-22): session.reap is the single op that
covers all three sub-reaps (stale sessions, stale agent dirs, orphaned
claim dirs) in one dispatch, and once this trampoline is wired into
/workday-start it is the intended live reap path going forward. The op
self-gates and self-manages its own cadence bookkeeping.

Usage:
    python3 reap-sessions.py [<repo_root>]

    <repo_root>  Optional; defaults to `git rev-parse --show-toplevel`.

Commit semantics: NO git commit on ANY path. session.reap mutates only
.git/coordinator-sessions/ (untracked substrate; Class-B op). No git diff,
no git commit.

Transport routing (unconditional native — no legacy fallback): route()
dispatches session.reap, with a _no_fallback() legacy_fn that always
raises (no bash body to fall back to). On transport failure (import
error, timeout, non-zero op exit) route() raises; log-and-continue to
stderr; exit 0. On transport SUCCESS, the returned bare result is
inspected via cc_invoke.mutation_refusal_message() (DR-215 exit_code
trap) — an in-envelope op-level refusal (non-zero 'exit_code' / non-empty
'error') is logged to stderr rather than silently discarded, though the
"never block session start" contract still holds: exit 0 either way.

Exit codes:
    0 — normal completion (including transport warn). Reaper MUST NOT block
        session start; all error paths exit 0.

Negative-spec:
    - Does NOT commit to git on any path.
    - Does NOT pass `force` to the op (let the op self-gate cadence).
    - Does NOT print an integer count to stdout (unlike sweep-terminal-plans.py;
      session-init's reaper block does not consume a count).
    - Does NOT fall back to legacy on transport failure (no legacy path exists).

Spec backlink: DoE-claude:pln-session-init-sh-boot-sweep-rea-fff7cc § C1
Spec backlink: docs/plans/2026-07-19-debash-coordinator-windows.md § Wave F1 (facade collapse)
"""
from __future__ import annotations

import os
import sys


def _no_console_creationflags() -> dict:
    """Resolve the engine root onto `sys.path` before importing `coordinator_core`
    (mirrors `safe-commit-offer.py` / `sweep-boot.py`'s resolve-then-insert
    shape, which every other in-process op import in this directory uses).

    This module used to import `coordinator_core.win_portability` at module
    level with no root bootstrap at all, so it resolved only where
    `coordinator_core` happened to already be importable -- i.e. when the
    process cwd was the engine checkout. Invoked through the settings-home
    `bin` shim from a SIBLING repo (the ordinary case: this is the reaper an
    operator reaches for after a scoped-commit refusal names a claim), it
    raised `ModuleNotFoundError: No module named 'coordinator_core'` at
    import time -- before `main`'s best-effort error handling could run, so
    the "never block session start" contract in this module's own docstring
    was defeated by its own import line. Reported 2026-08-07 by doe-claude-em
    (cross-repo memo `...-scoped-commit-calls-a-live-peer-dead-and-reapable`).

    Degrades to `{}` rather than raising: a missing subprocess-window flag is
    cosmetic, and this reaper must not fail on any path.
    """
    try:
        _bootstrap_imports()
        claude_klabauter_root = _resolve_claude_klabauter_root()
        if claude_klabauter_root and claude_klabauter_root not in sys.path:
            sys.path.insert(0, claude_klabauter_root)
        from coordinator_core.win_portability import no_console_creationflags

        return no_console_creationflags()
    except Exception:
        return {}


def _no_fallback() -> None:
    raise RuntimeError(
        "session.reap: native seam required (no bash fallback -- big-bang cutover)"
    )


def _resolve_repo_root(argv: list[str]) -> str | None:
    if argv:
        return argv[0]
    try:
        _bootstrap_imports()
        claude_klabauter_root = _resolve_claude_klabauter_root()
        if claude_klabauter_root and claude_klabauter_root not in sys.path:
            sys.path.insert(0, claude_klabauter_root)
        from coordinator_core.git.repo_root import show_toplevel

        return show_toplevel()
    except Exception:
        return None


_BOOTSTRAP_NAMES = ("cc_invoke", "_resolve_claude_klabauter_root")


def __getattr__(name: str):
    """PEP 562 module `__getattr__` -- lets a caller that reaches for
    `cc_invoke` / `_resolve_claude_klabauter_root` before `main()` has run (e.g. this
    file's own test suite, which reads `mod.cc_invoke.route` ahead of calling
    `mod.main()`) trigger `_bootstrap_imports()` lazily on first access,
    instead of requiring the name to already be a module global at import
    time. Only fires when the name is NOT already present in this module's
    `__dict__` -- once `_bootstrap_imports()` has run once (via this hook or
    via `main()`), the plain global wins on every later lookup and this
    function is not called again for that name.

    NEGATIVE SPEC -- the bootstrap guard checks ALL of `_BOOTSTRAP_NAMES`,
    not a single sentinel: `mock.patch.object` teardown, which `delattr`s
    rather than restoring and then probes via `hasattr`, is exactly the case
    the all-names guard covers -- a name absent from `__dict__` means
    `_bootstrap_imports()` re-runs. The re-run publishes each
    freshly-imported name via `globals().setdefault(...)`, so it rebinds
    exactly what is missing and leaves any OTHER already-present
    bootstrapped name untouched. No pop/restore snapshot is needed because a
    partially-bound state is never mistaken for a fully-bound one."""
    if name in _BOOTSTRAP_NAMES:
        _bootstrap_imports()
        try:
            return globals()[name]
        except KeyError:
            raise AttributeError(
                f"module {__name__!r} has no attribute {name!r}"
            ) from None
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _bootstrap_imports() -> None:
    """Import every non-stdlib dependency this module needs and bind it at
    module scope, called from main() (C6k import-motion: module bodies stay
    inert on both the warm door and the un-bootstrapped settings-home
    forwarder load routes). Idempotent by construction: a name already bound
    at module scope (via a prior call, or a test that reaches for
    `mod.cc_invoke` ahead of calling `main()`) is left alone rather than
    clobbered by a real import.
    """
    if all(n in globals() for n in _BOOTSTRAP_NAMES):
        return

    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    import cc_invoke as _cc_invoke
    from cc_invoke import _resolve_claude_klabauter_root as _resolve_claude_klabauter_root_fn

    for _name, _value in (
        ("cc_invoke", _cc_invoke),
        ("_resolve_claude_klabauter_root", _resolve_claude_klabauter_root_fn),
    ):
        globals().setdefault(_name, _value)


def main(argv: list[str] | None = None) -> int:
    _bootstrap_imports()
    argv = sys.argv[1:] if argv is None else argv
    repo_root = _resolve_repo_root(argv)
    if repo_root is None:
        print("reap-sessions.py: cannot resolve git repo root", file=sys.stderr)
        return 0  # best-effort: never block session start

    try:
        result = cc_invoke.route("session.reap", {}, repo_root, _no_fallback)
    except RuntimeError as exc:
        print(f"reap-sessions.py: session.reap failed -- continuing (best-effort): {exc}", file=sys.stderr)
        return 0

    message = cc_invoke.mutation_refusal_message("session.reap", result)
    if message is not None:
        print(f"reap-sessions.py: {message} -- continuing (best-effort)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
