# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""check-no-illegal-paths.py — backstop gate: scan tracked + staged paths for NTFS-illegal chars.

PURPOSE: Catch NTFS-illegal path components in the git tree before they reach
origin/main and block Windows checkout. Complements the PreToolUse
block-illegal-filename hook (which catches agent Bash/Write/Edit calls); this
script catches human `git mv` and any non-agent write the hook cannot observe.
Intended to run as a ceremony gate step (e.g. /workweek-complete,
/merging-to-main).

Usage: check-no-illegal-paths.py [<repo-root>]

  <repo-root> — optional explicit repo root; absent -> auto-discover via
                `git rev-parse --show-toplevel` (safe to run from any subdir).

Scans:
  tracked  — git ls-tree -r --name-only HEAD
  staged   — git diff --cached --name-only

Predicate: `csn_check` from coordinator/bin/lib/coordinator_safe_name.py (the
canonical SoT for the NTFS-illegal charset, ported to Python by the sibling
de-bash chunk E3-c). Do NOT re-hardcode the charset here — that lib is the
single source of truth.

Checks every path COMPONENT, not just the basename: a colon in a directory
name is equally illegal on NTFS as one in a filename.

Exit 0 — all paths clean.
Exit 1 — one or more illegal path components found (offending paths on stderr).
Exit 2 — setup error (not in a git repo).

Spec backlink: docs/plans/2026-06-30-cross-platform-file-naming-helper.md § Wave D2 (AC6)
Realises: AC6 commit/merge backstop
Port backlink: docs/plans/2026-07-19-debash-coordinator-windows.md § E3-b
"""
from __future__ import annotations

import os
import subprocess
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(_SCRIPT_DIR, "lib")

# The two helper imports below are deferred and sys.path-dependent: `coordinator_safe_name`
# and `cc_invoke` both live in bin/lib, which is not a package and is on no default path.
# Self-resolve it from __file__, never cwd — this runs as a pre-commit gate from any repo.
#
# DEFERRED WITH ITS CONSUMERS, not run at module scope. This name warm-serves, and a
# warm server imports the module once and calls `main` many times, so a module-body
# `sys.path.insert` mutates the SERVER's interpreter on behalf of one request and keeps
# it for every later one. Idempotent here and harmless in isolation, but the rule it
# would need an exception to is the one keeping 363 names inert in a shared process
# (`coordinator_core.warm.serve_classifier`). The imports were already deferred; the rung
# they depend on now defers with them.
def _ensure_lib_on_path() -> None:
    if _LIB_DIR not in sys.path:
        sys.path.insert(0, _LIB_DIR)


def _csn_check(component: str) -> str | None:
    """Return a violation reason string, or None if the component is clean."""
    _ensure_lib_on_path()
    from coordinator_safe_name import csn_check  # noqa: E402  (sys.path-dependent)

    ok, reason = csn_check(component)
    return None if ok else reason


def _git(repo_root: str, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", repo_root, *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return ""
    return proc.stdout


def _resolve_repo_root(explicit: str | None) -> str:
    _ensure_lib_on_path()
    from cc_invoke import ensure_engine_on_path  # noqa: E402  (sys.path-dependent)

    ensure_engine_on_path(__file__)
    from coordinator_core.git.repo_root import show_toplevel

    if explicit:
        root = show_toplevel(explicit)
        if not root:
            print(
                'check-no-illegal-paths: "%s" is not inside a git repo' % explicit,
                file=sys.stderr,
            )
            sys.exit(2)
        return root

    root = show_toplevel()
    if not root:
        print("check-no-illegal-paths: not inside a git repo", file=sys.stderr)
        sys.exit(2)
    return root


def main(argv: list[str]) -> int:
    explicit_root = argv[0] if argv else None
    repo_root = _resolve_repo_root(explicit_root)

    tracked = _git(repo_root, "ls-tree", "-r", "--name-only", "HEAD")
    staged = _git(repo_root, "diff", "--cached", "--name-only")
    all_paths = sorted(
        {p for p in (tracked + "\n" + staged).splitlines() if p}
    )

    found = False
    for path in all_paths:
        for component in path.split("/"):
            if not component:
                continue
            reason = _csn_check(component)
            if reason is not None:
                print(
                    'ILLEGAL PATH: %s  (component %s)' % (path, reason),
                    file=sys.stderr,
                )
                found = True

    if not found:
        print(
            "check-no-illegal-paths: all tracked+staged paths are clean.",
            file=sys.stderr,
        )
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
