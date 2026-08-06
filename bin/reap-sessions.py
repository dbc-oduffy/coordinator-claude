#!/usr/bin/env python3
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
stderr; exit 0.

Exit codes:
    0 — normal completion (including transport warn). Reaper MUST NOT block
        session start; all error paths exit 0.

Negative-spec:
    - Does NOT commit to git on any path.
    - Does NOT pass `force` to the op (let the op self-gate cadence).
    - Does NOT print an integer count to stdout (unlike sweep-terminal-plans.py;
      session-init's reaper block does not consume a count).
    - Does NOT fall back to legacy on transport failure (no legacy path exists).

Spec backlink: docs/plans/2026-07-06-session-init-op-absorption-repoint.md § C1
Spec backlink: docs/plans/2026-07-19-debash-coordinator-windows.md § Wave F1 (facade collapse)
"""
from __future__ import annotations

import os
import subprocess
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
import cc_invoke  # noqa: E402


def _no_fallback() -> None:
    raise RuntimeError(
        "session.reap: native seam required (no bash fallback -- big-bang cutover)"
    )


def _resolve_repo_root(argv: list[str]) -> str | None:
    if argv:
        return argv[0]
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError:
        return None
    resolved = (proc.stdout or "").strip()
    if proc.returncode != 0 or not resolved:
        return None
    return resolved


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    repo_root = _resolve_repo_root(argv)
    if repo_root is None:
        print("reap-sessions.py: cannot resolve git repo root", file=sys.stderr)
        return 0  # best-effort: never block session start

    try:
        cc_invoke.route("session.reap", {}, repo_root, _no_fallback)
    except RuntimeError as exc:
        print(f"reap-sessions.py: session.reap failed -- continuing (best-effort): {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
