# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""hollow-completion-record-sweep.py — CLI trampoline for
completion_record_sweep.sweep_repos, plus an opt-in --repair mode backed by
completion_record_repair.repair_repos.

Purpose: READ-ONLY diagnostic by default. For one or more repo roots, report
every ``archive/completed/**/*.md`` record failing
``coordinator_core.completion_record_integrity.hollow_reasons`` --
placeholder markers still present, ``commits: []``, and/or a governing plan
that never reached ``implemented``/``landed`` status. Never mutates, moves,
or deletes a record UNLESS ``--repair --apply`` is passed.

Usage:
    python coordinator/bin/hollow-completion-record-sweep.py <repo-root> [<repo-root> ...]
    python coordinator/bin/hollow-completion-record-sweep.py --repair <repo-root> [<repo-root> ...]
    python coordinator/bin/hollow-completion-record-sweep.py --repair --apply <repo-root> [<repo-root> ...]

``--repair`` alone is a DRY RUN: reports exactly what would be repaired and
what is residue (never fakeable — plan-not-landed/plan-unresolvable/
placeholder-marker's missing needs-author status), touches no file.
``--repair --apply`` performs the writes (``commits:`` backfill only — see
``completion_record_repair``'s own docstring for the full negative-spec).
``--apply`` without ``--repair`` is rejected (nothing to apply).

With no repo-root arguments, sweeps the current repo (resolved via
``repo_identity.resolve_checked_repo_root``).

Exit codes:
  0 — swept/repaired successfully (regardless of how many hollow/repairable
      records were found — this is a diagnostic, not a pass/fail gate).
  1 — no repo root resolvable (no args, and cwd is not inside a git repo),
      or ``--apply`` passed without ``--repair``.
  2 — engine-root resolution failed / coordinator_core not importable.

Plain sweep mode (no ``--repair``) NEVER writes anything.
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
    repair = "--repair" in args
    apply_ = "--apply" in args
    args = [a for a in args if a not in ("--repair", "--apply")]

    if apply_ and not repair:
        print("hollow-completion-record-sweep.py: --apply requires --repair", file=sys.stderr)
        return 1

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

    if repair:
        from coordinator_core.ops.completion_record_repair import repair_repos

        reports = repair_repos(roots, apply=apply_)
        total_repairable = sum(len(r.repairable) for r in reports)
        total_residue = sum(len(r.residue) for r in reports)
        total_process_ms = sum(r.process_ms for r in reports)
        total_over_cap = sum(len(r.over_cap) for r in reports)
        print(f"repos_swept={len(roots)}")
        print(f"mode={'apply' if apply_ else 'dry-run'}")
        print(f"repairable_records={total_repairable}")
        print(f"residue_records={total_residue}")
        print(f"over_cap_records={total_over_cap}  # matched >20 shas -- sent to residue, not written")
        print(f"process_ms_total={total_process_ms:.1f}")
        print("--- per-repo counts ---")
        for r in reports:
            print(
                f"{r.repo_root}\trepairable={len(r.repairable)}\tresidue={len(r.residue)}\t"
                f"over_cap={len(r.over_cap)}\tprocess_ms={r.process_ms:.1f}\t"
                f"commits_scanned={r.commits_scanned}\tcommits_kept={r.commits_kept}"
            )
        print("--- over-cap (matched >20 shas, sent to residue) ---")
        for r in reports:
            for record_path, count in r.over_cap:
                print(f"{r.repo_root}\t{record_path}\tsha_count={count}")
        print("--- repairable ---")
        for r in reports:
            for rec in r.repairable:
                written = "written" if rec.written else "would-write"
                print(f"{r.repo_root}\t{rec.record_path}\t{written}\tsource={rec.match_source}\tshas={','.join(rec.shas)}")
        print("--- residue (never written) ---")
        for r in reports:
            for record_path, reason in r.residue:
                print(f"{r.repo_root}\t{record_path}\t{reason}")
        return 0

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
