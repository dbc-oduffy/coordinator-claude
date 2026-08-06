#!/usr/bin/env python3
# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""generate-exec-summary.py — CLI trampoline regenerating a repo's exec-summary doc.

Populates the two MANAGED sections (identity, progress) of a per-repo
docs/exec-summary.md from disk artifacts while preserving the two HAND
sections (special, goals) verbatim across regenerations. Derivation/emission
logic lives claude-klabauter-side in coordinator_core.ops.generate_exec_summary; this
file resolves CLAUDE_KLABAUTER_ROOT and forwards argv. Invoked from /workweek-start and
repo-setup as a best-effort cadence-step doc generator, never a merge gate.
"""
# generate-exec-summary.py — CLI trampoline over claude-klabauter
# coordinator_core.ops.generate_exec_summary.
#
# Purpose: populate the two MANAGED sections (identity, progress) of a per-repo
# docs/exec-summary.md from disk artifacts and preserve the two HAND sections
# (special, goals) verbatim across regenerations. Full logic lives claude-klabauter-side;
# see coordinator_core/ops/generate_exec_summary.py for the derivation/emission
# implementation and its co-located pytest (test_generate_exec_summary.py).
#
# Spec backlink: docs/plans/2026-07-03-exec-summary-per-repo-brief.md § C2
# Spec backlink: docs/wiki/exec-summary-artifact.md § Generator contract
# Spec backlink: docs/plans/2026-07-16-bash-clean-slate-residual-migration.md
#
# Usage:
#   generate-exec-summary.py [--check]
#
# Options:
#   --check   Print generated content to stdout without writing to disk.
#
# Exit-code contract:
#   Module-level (coordinator_core.ops.generate_exec_summary.main), UNCHANGED
#   from the pre-port bash oracle:
#     0 — success (file written, or --check printed).
#     1 — fail-loud: not inside a git repository; a HAND fence pair is absent
#         or malformed on an existing target; or the state-root resolver
#         failed (coordinator_claude_klabauter_root() raised).
#     2 — CLI usage error (unknown argument).
#   Trampoline-level (THIS file, CLAUDE_KLABAUTER_ROOT-resolution / import failure):
#     0 — best-effort degrade, loud on stderr. This script is a cadence-step
#         doc generator (invoked from /workweek-start, repo-setup) — never a
#         merge/commit gate — so a broken claude-klabauter link is advisory, matching
#         the same posture as coordinator-auto-push / handoff-gate-aging
#         (per PORTER-BRIEF-ADDENDUM.md § 3b "best-effort/never-block").
#         Never collides with the module-level business codes 1/2 above,
#         since it is returned from a distinct code path (before the module
#         is ever reached) and never propagates a module-level 0/1/2 through
#         this branch.
#
# Negative-spec (mirrors the pre-port bash oracle, now enforced claude-klabauter-side):
#   - Does NOT overwrite HAND sections on existing files.
#   - Does NOT continue silently if HAND fences are malformed on an existing file.
#   - Does NOT add a cockpit-contract entity or bump CONTRACT_VERSION (anti-scope).
#   - Does NOT write to disk when --check is passed.

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402


def _import_runner():
    """Resolve CLAUDE_KLABAUTER_ROOT and import the runner.

    DR-276: the op is run through `coordinator_core.cli_entry.run_op_main`
    rather than by calling its `main` directly, so the paths it declares become
    a session scope-touch claim. Without that, everything this CLI writes is an
    orphan at the `scoped_git_commit` sink.
    """
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.cli_entry import run_op_main
    return run_op_main


def main() -> None:
    try:
        run_op_main = _import_runner()
    except RuntimeError as exc:
        print(f"generate-exec-summary: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(0)
    except ImportError as exc:
        print(
            f"generate-exec-summary: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(0)

    try:
        code = run_op_main("coordinator_core.ops.generate_exec_summary", sys.argv[1:])
    except ImportError as exc:
        print(
            f"generate-exec-summary: coordinator_core.ops.generate_exec_summary not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(0)
    sys.exit(code)


if __name__ == "__main__":
    main()
