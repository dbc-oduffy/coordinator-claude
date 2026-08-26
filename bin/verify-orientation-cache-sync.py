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
# verify-orientation-cache-sync.py — Schema verifier for state/orientation_cache.md.
#
# Trampoline over claude-klabauter coordinator_core.ops.verify_orientation_cache_sync
# (DR-047: DoE owns contract/generator, claude-klabauter owns engine).
#
# Spec backlink: docs/plans/2026-05-18-orientation-cache-authoring-discipline.md
# Schema:       plugins/coordinator/pipelines/workday-start-internals.md § 5.5
# Producer:     plugins/coordinator/bin/regenerate-orientation-cache (still DoE bash)
# Port source:  coordinator/bin/verify-orientation-cache-sync.py (this file, prior bash body; see git log)
# Spec backlink (port): DoE-claude:pln-bash-polyglot-clean-slate-full-5c71ee
#
# Division of labor: this trampoline resolves REPO_ROOT / STATE_ROOT / CACHE_FILE
# (reusing the native 5-rule resolver `coordinator_core.state_root`, imported
# in-process once the engine root is on sys.path — de-bash campaign,
# docs/plans/2026-07-16-bash-clean-slate-residual-migration.md; the bash
# sourced-lib oracle this used to shell out to is retired) and owns `--list` /
# the no-cache-file no-op. The actual schema-check logic (frontmatter, heading
# allowlist, per-section shape regexes, UE-detector-regression guard) lives in
# coordinator_core.ops.verify_orientation_cache_sync, imported directly
# in-process (template-variant #1 — no @register_op, no IPC round trip; this
# is a CLI, not a hot per-commit path, but the check is pure/local and gains
# nothing from an RPC envelope).
#
# Usage:
#   verify-orientation-cache-sync.py           Verify the cache. Exit non-zero on violation.
#   verify-orientation-cache-sync.py --list    Print the cache path that would be checked.
#
# Exit codes:
#   0 — OK: no violations found, OR --list, OR no cache file present (nothing to verify)
#   1 — one or more schema violations found (violation list on stderr)
#   2 — transport failure: REPO_ROOT/STATE_ROOT resolution or the claude-klabauter
#       import failed (dedicated code — never collides with the 0/1 business
#       outcomes above; this is a fail-loud validator, so a claude-klabauter-link outage
#       must not be misread as "cache is schema-clean").
#
# No --fix mode by design. Violations are structural — fix by regenerating via
# bin/regenerate-orientation-cache, not by patching the file in place.
from __future__ import annotations

import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(_SCRIPT_DIR, "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402
from repo_identity import resolve_checked_repo_root  # noqa: E402


def _resolve_repo_root() -> str:
    """Resolve the repo root via the checked resolver (coordinator/bin/lib/repo_identity.py).

    READER script (AC10): this entry dispatches into the verify op, which is
    read-only (no write path anywhere in this trampoline or the op it calls —
    it only sys.exit()s on verify outcomes). On a positive MISMATCH, warn to
    stderr and proceed with the resolved root rather than refuse — DR-277
    exists to prevent a write into a foreign tree, and there is no write here
    to protect. UNRESOLVED never refuses either (DR-277, AC4).
    """
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
    claude_klabauter_root = require_dispatch_engine_on_path()
    try:
        from coordinator_core.state_root import coordinator_state_root as _native_state_root
    except ImportError as exc:
        raise RuntimeError(
            f"coordinator_core.state_root not importable: {exc}"
        ) from exc

    return _native_state_root()


def _import_op_main():
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.ops.verify_orientation_cache_sync import main as _op_main

    return _op_main


def main() -> None:
    argv = sys.argv[1:]

    try:
        state_root = _resolve_state_root()
    except RuntimeError as exc:
        print(f"verify-orientation-cache-sync: STATE_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(2)

    cache_file = os.path.join(state_root, "orientation_cache.md")

    if argv and argv[0] == "--list":
        print(cache_file)
        sys.exit(0)

    if not os.path.isfile(cache_file):
        print(f"verify-orientation-cache-sync: no cache file at {cache_file} — nothing to verify")
        sys.exit(0)

    # Review: code-reviewer P3 — _resolve_repo_root() re-resolves the engine root
    # unguarded; safe today only because _resolve_state_root() above already
    # proved resolution succeeds, but the redundant call sat outside any
    # try/except, inconsistent with this file's own established pattern of
    # catching RuntimeError at every other engine-root-touching call site.
    try:
        repo_root = _resolve_repo_root()
    except RuntimeError as exc:
        print(f"verify-orientation-cache-sync: engine-root resolution failed: {exc}", file=sys.stderr)
        sys.exit(2)

    try:
        op_main = _import_op_main()
    except RuntimeError as exc:
        print(f"verify-orientation-cache-sync: engine-root resolution failed: {exc}", file=sys.stderr)
        sys.exit(2)
    except ImportError as exc:
        print(
            "verify-orientation-cache-sync: "
            f"coordinator_core.ops.verify_orientation_cache_sync not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(op_main([cache_file, repo_root]))


if __name__ == "__main__":
    main()
