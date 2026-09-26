# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""verify-orientation-cache-sync.py — Schema verifier for state/orientation_cache.md.

Trampoline over claude-klabauter coordinator_core.ops.verify_orientation_cache_sync
(DR-047: DoE owns contract/generator, claude-klabauter owns engine). Resolves
REPO_ROOT/STATE_ROOT/CACHE_FILE and owns the `--list` / no-cache-file no-op;
the schema-check logic (frontmatter, heading allowlist, per-section shape
regexes, UE-detector-regression guard) lives in the claude-klabauter op module. No
--fix mode — violations are structural, fixed by regenerating via
bin/regenerate-orientation-cache.
"""
# Division of labor: this trampoline resolves REPO_ROOT / STATE_ROOT / CACHE_FILE
#   2 — transport failure: REPO_ROOT/STATE_ROOT resolution or the claude-klabauter
from __future__ import annotations

import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def _ensure_engine_bound() -> None:
    """Resolve the engine root and BIND `coordinator_core` to it, in that order.

    LOAD-BEARING, NOT DEAD -- called first thing in `main()`, before any other
    coordinator_core-touching helper below. `require_dispatch_engine_on_path()`
    only mutates sys.path -- it imports nothing. Without the `import
    coordinator_core` call immediately after, the next coordinator_core import
    anywhere in this process (a binder module that resolves on the LOCATOR
    axis) wins the race and binds coordinator_core off the working tree
    instead of the dispatch root, and no later sys.path insert can rebind an
    already-imported package. Removing this restores a silent wrong-tree
    divergence that require_dispatch_engine_on_path now raises on.
    Why: docs/plans/2026-08-26-the-seam-reports-what-it-got.md C9,
    docs/research/engine-provenance-carrier-dependence.md
    """
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    require_dispatch_engine_on_path()
    import coordinator_core  # noqa: F401


def _resolve_repo_root() -> str:
    """Resolve the repo root via the checked resolver (coordinator/bin/lib/repo_identity.py).

    READER script (AC10): this entry dispatches into the verify op, which is
    read-only (no write path anywhere in this trampoline or the op it calls —
    it only sys.exit()s on verify outcomes). On a positive MISMATCH, warn to
    stderr and proceed with the resolved root rather than refuse — DR-277
    exists to prevent a write into a foreign tree, and there is no write here
    to protect. UNRESOLVED never refuses either (DR-277, AC4).
    """
    from repo_identity import resolve_checked_repo_root

    root, verdict = resolve_checked_repo_root(explicit_root=None)
    if verdict["verdict"] == "MISMATCH":
        print(verdict["message"], file=sys.stderr)
    if not root:
        return os.getcwd()
    return root


def _resolve_state_root() -> str:
    """Resolve STATE_ROOT via the native `coordinator_core.state_root` seam,
    imported in-process once the engine root is resolved (same engine root
    resolution `_import_op_main` below already performs for the op module —
    shared here rather than re-resolved). Raises RuntimeError on any
    transport failure (engine root unresolvable, module not importable, or
    the seam's own StateRootError/CrossCuttingStateRoot).
    """
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    try:
        from coordinator_core.state_root import coordinator_state_root as _native_state_root
    except ImportError as exc:
        raise RuntimeError(
            f"coordinator_core.state_root not importable: {exc}"
        ) from exc

    return _native_state_root()


def _import_op_main():
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.ops.verify_orientation_cache_sync import main as _op_main

    return _op_main


def main(argv: "list[str] | None" = None) -> int:
    argv = (sys.argv[1:] if argv is None else argv)

    try:
        _ensure_engine_bound()
    except RuntimeError as exc:
        print(f"verify-orientation-cache-sync: engine-root resolution failed: {exc}", file=sys.stderr)
        return 2

    try:
        state_root = _resolve_state_root()
    except RuntimeError as exc:
        print(f"verify-orientation-cache-sync: STATE_ROOT resolution failed: {exc}", file=sys.stderr)
        return 2

    cache_file = os.path.join(state_root, "orientation_cache.md")

    if argv and argv[0] == "--list":
        print(cache_file)
        return 0

    if not os.path.isfile(cache_file):
        print(f"verify-orientation-cache-sync: no cache file at {cache_file} — nothing to verify")
        return 0

    try:
        repo_root = _resolve_repo_root()
    except RuntimeError as exc:
        print(f"verify-orientation-cache-sync: engine-root resolution failed: {exc}", file=sys.stderr)
        return 2

    try:
        op_main = _import_op_main()
    except RuntimeError as exc:
        print(f"verify-orientation-cache-sync: engine-root resolution failed: {exc}", file=sys.stderr)
        return 2
    except ImportError as exc:
        print(
            "verify-orientation-cache-sync: "
            f"coordinator_core.ops.verify_orientation_cache_sync not importable: {exc}",
            file=sys.stderr,
        )
        return 2

    return op_main([cache_file, repo_root])


if __name__ == "__main__":
    sys.exit(main())
