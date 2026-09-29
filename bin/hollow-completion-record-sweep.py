# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""hollow-completion-record-sweep.py — CLI trampoline for
completion_record_sweep.sweep_repos.

Purpose: READ-ONLY diagnostic. For one or more repo roots, report every
``archive/completed/**/*.md`` record failing
``coordinator_core.completion_record_integrity.hollow_reasons`` --
placeholder markers still present, ``commits: []``, and/or a governing plan
that never reached ``implemented``/``landed`` status. Never mutates, moves,
or deletes a record.

Usage:
    python coordinator/bin/hollow-completion-record-sweep.py <repo-root> [<repo-root> ...]

With no arguments, sweeps the current repo (resolved via
``repo_identity.resolve_checked_repo_root``).

Exit codes:
  0 — swept successfully (regardless of how many hollow records were found
      — this is a diagnostic, not a pass/fail gate).
  1 — no repo root resolvable (no args, and cwd is not inside a git repo).
  2 — engine-root resolution failed / coordinator_core not importable.

NEVER writes anything.
"""
from __future__ import annotations

import os
import sys

_BIN_DIR = os.path.dirname(os.path.abspath(__file__))


def _bootstrap_engine():
    """See day-coverage-sweep.py's identical helper docstring for why this
    exact two-import sequence (lib, then coordinator_core) is load-bearing."""
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    require_dispatch_engine_on_path()
    import coordinator_core  # noqa: F401


def main(argv: list[str]) -> int:
    _bootstrap_engine()
    from pathlib import Path

    from cc_invoke import require_dispatch_engine_on_path

    try:
        require_dispatch_engine_on_path()
        from coordinator_core.ops.completion_record_sweep import sweep_repos, summarize_by_check
    except RuntimeError as exc:
        print(f"hollow-completion-record-sweep.py: engine-root resolution failed: {exc}", file=sys.stderr)
        return 2
    except ImportError as exc:
        print(f"hollow-completion-record-sweep.py: coordinator_core.ops.completion_record_sweep not importable: {exc}", file=sys.stderr)
        return 2

    args = argv[1:]
    if args:
        roots = [Path(a) for a in args]
    else:
        from repo_identity import resolve_checked_repo_root

        repo_root, verdict = resolve_checked_repo_root(explicit_root=None)
        if repo_root is None:
            print(f"hollow-completion-record-sweep.py: cannot resolve git repo root from {os.getcwd()}", file=sys.stderr)
            return 1
        if verdict["verdict"] == "MISMATCH":
            print(verdict["message"], file=sys.stderr)
        roots = [Path(repo_root)]

    findings = sweep_repos(roots)
    summary = summarize_by_check(findings)

    print(f"repos_swept={len(roots)}")
    print(f"hollow_records={len(findings)}")
    print("--- per-repo, per-check breakdown ---")
    for root in roots:
        counts = summary.get(str(root), {})
        print(
            f"{root}\t"
            f"placeholder-marker={counts.get('placeholder-marker', 0)}\t"
            f"empty-commits={counts.get('empty-commits', 0)}\t"
            f"plan-not-landed={counts.get('plan-not-landed', 0)}\t"
            f"plan-unresolvable={counts.get('plan-unresolvable', 0)}"
        )
    print("--- raw findings ---")
    for f in findings:
        print(f"{f.repo_root}\t{f.record_path}\tchecks={','.join(f.failed_checks)}\tchain={f.chain_slug}\tplan={f.plan_path}\tplan_status={f.plan_status}")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
