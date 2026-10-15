# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""reap-stale-subagent-sidecars.py — delete-by-convention sweep over
``state/subagent-share/`` (DR-091's one-home for every identity-typed
subagent sidecar: run-report, review-findings, staff-eng-review, assessment
[the provision_report template that also covers prior-art-checker /
docs-checker / plan-coverage-checker spawns], and any other
``report_sidecar``-eligible type).

Purpose: DR-091 moved every provisioned sidecar (review findings included)
off the double-reaped legacy ``state/review-trail/findings/`` home onto
``state/subagent-share/<session>/<key>.md`` — a location that had NO reaper
of its own, meaning sidecars would otherwise accumulate git-tracked
indefinitely (the "DR-091 tracked-inversion" cost named in
docs/plans/2026-07-24-reviewer-sidecar-provisioning-reconciliation.md § C7).
This script is that reaper: a simple fire-when-invoked delete op, operating
by DELETE-BY-CONVENTION — a sidecar's durable value is folded into the
artifact it fed (the reviewer's own findings applied in place, the executor's
plan-progress update, the EM's read of an assessment/run-report) before this
sweep ever runs; the sidecar itself is disposable scaffolding once folded.

Deletion gate — session liveness AND/OR an age floor, NEVER ``status:``
alone (the hard rule this op and its DoE-side test
``coordinator/tests/test_distill_subagent_share_sweep.py`` both encode):

  1. LIVENESS (per session directory, not per file). Each top-level child of
     ``state/subagent-share/`` is named for the REQUESTING lead session that
     spawned the sidecar(s) inside it (provision_report's
     ``sanitized_session_id`` directory leaf — see claude-klabauter
     coordinator_core/subagent_sandbox/provision_report.py). If that session
     is still LIVE (coordinator_core.session.liveness.session_live), EVERY
     sidecar under that directory is preserved regardless of status or age —
     an in-flight concurrent session's own sidecar must never be yanked out
     from under it mid-review/mid-execution.
  2. AGE FLOOR (per file, only reached once the owning session is dead). A
     dead-session sidecar is reapable only once its mtime age is at least
     ``--age-floor-days`` (default: 14, mirroring the retired
     ``review-trail/findings`` aged-reap precedent this op supersedes).
  3. STATUS carve-out (per file). ``status: blocked`` and
     ``status: thrashing`` sidecars are NEVER reaped by this op regardless of
     liveness/age — they are terminal-but-unresolved states that need EM/PM
     attention before the record they describe is safe to discard (mirrors
     the run-report lifecycle doctrine at coordinator-doc-new's ``--type
     run-report`` scaffold comment: "blocked and thrashing terminal sidecars
     SURVIVE the sweep").

Reapable = dead-session AND age >= floor AND status NOT IN
{blocked, thrashing}. This is an AND-of-two-gates-plus-a-carve-out, not an
OR — "never status: alone" means status can only ever SUBTRACT from the
reapable set (the blocked/thrashing carve-out), never independently ADD to
it (an old "status: complete" sidecar is not reaped just because it says
complete; it is reaped because its session died and it aged out).

Tracked vs untracked split (mirrors reap-integrated-review-findings.py):
DR-091 sidecars are git-tracked (that's the whole "tracked-inversion" cost
this op exists to bound) — tracked files are removed via ``git rm``
(history-preserving) plus one scoped commit; any untracked stray is removed
via plain ``os.remove`` (nothing in history to preserve).

Cadence: invoked from ``/distill`` Phase 5 (alongside
``reap-integrated-review-findings.py``), ``/update-docs``'s sweep, a
``/workweek-complete`` cron-equivalent step, and on-demand. Wiring those
call sites into the skills/commands themselves is a SEPARATE chunk (this
op's existence is the prerequisite, not the wiring) — see
docs/plans/2026-07-24-reviewer-sidecar-provisioning-reconciliation.md § C7.

Usage:
    python3 reap-stale-subagent-sidecars.py [--dry-run] [--age-floor-days N]

--dry-run: report what WOULD be reaped/preserved; remove and commit nothing.
--age-floor-days N: override the default 14-day age floor (must be >= 0).

Exit codes:
    0 — normal (including zero candidates; best-effort, non-blocking)
    2 — internal error (not inside a git repo, or the session-liveness
        engine is not importable)

Spec backlink: coordinator-content-repo:pln-reviewer-sidecar-provisioning--6ba704 § C7
Spec backlink (DR-091 home): docs/decisions/DR-091-agent-citizenship-identity-typed-sidecar-contract.md
  (repo ROOT of the coordinator-content-repo tree; a same-numbered archived twin exists —
  see that plan's C1 body for the disambiguation note).

Negative-spec (RAW-PID-LIVENESS): the liveness gate calls
coordinator_core.session.liveness.session_live() ONLY — never mtime/pid of
the session directory or any file inside it for the LIVENESS decision (mtime
is used solely for the separate, file-level AGE FLOOR check, gated 2 above).
Negative-spec: this op never mutates frontmatter and never rewrites a
sidecar's contents — it only deletes whole files once they clear every gate.
Negative-spec: does NOT add a ``/distill``/``/update-docs``/`/workweek-complete``
call site — that wiring, and the flip of ``distill.md``'s
"state/subagent-share/<session-id>/*.md run-report sidecars" named exception
from "blocked — op not yet built" to describe this shipped op, is a
separate, later chunk (this op existing is that chunk's precondition).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from typing import Optional

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def _bootstrap_imports() -> None:
    """Import every non-stdlib dependency this module needs and bind it at
    module scope, called from main() (C6k import-motion: module bodies stay
    inert on both the warm door and the un-bootstrapped settings-home
    forwarder load routes). Order is load-bearing — preserved verbatim from
    the former module-scope sequence; see the inline comments below.
    """
    global require_dispatch_engine_on_path, resolve_checked_repo_root
    global no_console_creationflags

    if all(
        _n in globals()
        for _n in ("require_dispatch_engine_on_path", "resolve_checked_repo_root", "no_console_creationflags")
    ):
        return

    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    import cc_invoke as _cc_invoke_mod

    globals().setdefault("require_dispatch_engine_on_path", _cc_invoke_mod.require_dispatch_engine_on_path)
    require_dispatch_engine_on_path()
    # LOAD-BEARING, NOT DEAD. Do not delete on an unused-import sweep: this line is
    # what BINDS coordinator_core, and binding it HERE is the whole fix.
    # require_dispatch_engine_on_path() above only mutates sys.path -- it imports
    # nothing. Without this line the next module-level import below (a binder module
    # that resolves on the LOCATOR axis) wins the race and binds coordinator_core off
    # the working tree instead of the dispatch root, and no later sys.path insert can
    # rebind an already-imported package. Removing it restores a silent wrong-tree
    # divergence that require_dispatch_engine_on_path now raises on.
    # Why: docs/plans/2026-08-26-the-seam-reports-what-it-got.md C9,
    # docs/research/engine-provenance-carrier-dependence.md
    import coordinator_core  # noqa: F401

    from repo_identity import resolve_checked_repo_root as _resolve_checked_repo_root
    from coordinator_core import win_portability as _win_portability_mod

    # `globals().setdefault`, not a bare `from X import Y` rebind: a caller's
    # monkeypatch of one of these names (e.g. a test's `mod.resolve_checked_repo_root
    # = ...`) must never be clobbered by a later bootstrap call — see this
    # function's own per-name guard above and the module's __getattr__ absence
    # note (no PEP 562 hook here; every reader of these names is a function in
    # THIS module, so a bootstrap call at each read site is what serves them).
    globals().setdefault("resolve_checked_repo_root", _resolve_checked_repo_root)
    globals().setdefault("no_console_creationflags", _win_portability_mod.no_console_creationflags)

def _resolve_session_live():
    """Import coordinator_core.session.liveness.session_live via the engine root.

    In-process import (no subprocess, no bash).
    """
    _bootstrap_imports()
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.session.liveness import session_live
    return session_live


def _load_reap_core():
    """Bind the shared sweep module's names (the sweep itself lives in
    coordinator_core.sidecar_reap) once the engine root is on sys.path."""
    _bootstrap_imports()
    require_dispatch_engine_on_path()
    from coordinator_core import sidecar_reap as _core

    globals().setdefault("classify_sidecars", _core.classify_sidecars)
    globals().setdefault("_fm_field", _core.fm_field)
    globals().setdefault("_tracked_paths", _core.tracked_paths)
    globals().setdefault("_write_pathspec_file", _core.write_pathspec_file)
    globals().setdefault("_DEFAULT_AGE_FLOOR_DAYS", _core.DEFAULT_AGE_FLOOR_DAYS)
    return _core


def __getattr__(name: str):
    if name in ("classify_sidecars", "_fm_field", "_tracked_paths", "_write_pathspec_file", "_DEFAULT_AGE_FLOOR_DAYS"):
        _load_reap_core()
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def main(argv: Optional[list] = None) -> int:
    _bootstrap_imports()
    argv = list(sys.argv[1:] if argv is None else argv)

    parser = argparse.ArgumentParser(
        prog="reap-stale-subagent-sidecars.py",
        description="Delete-by-convention sweep of the subagent-share sidecar homes (DR-091).",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--age-floor-days", type=int, default=_load_reap_core().DEFAULT_AGE_FLOOR_DAYS)
    parser.add_argument("--repo-root", default=None)
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        print(f"reap-stale-subagent-sidecars.py: unknown argument: {argv}", file=sys.stderr)
        return 2
    if args.age_floor_days < 0:
        print("reap-stale-subagent-sidecars.py: --age-floor-days must be >= 0", file=sys.stderr)
        return 2

    dry_run = args.dry_run
    age_floor_days = args.age_floor_days

    repo_root, verdict = resolve_checked_repo_root(explicit_root=args.repo_root)
    if not repo_root:
        print("reap-stale-subagent-sidecars.py: not inside a git repo", file=sys.stderr)
        return 2
    if verdict["verdict"] == "MISMATCH":
        # DR-277: this is a READER (no write into resolved root) -- warn
        # and proceed. UNRESOLVED never refuses either (AC4).
        print(verdict["message"], file=sys.stderr)

    try:
        session_live = _resolve_session_live()
    except (RuntimeError, ImportError) as exc:
        print(f"reap-stale-subagent-sidecars.py: session liveness engine not importable: {exc}", file=sys.stderr)
        return 2

    core = _load_reap_core()
    return core.reap_stale_sidecars(
        repo_root, session_live, dry_run=dry_run, age_floor_days=age_floor_days,
    )


if __name__ == "__main__":
    sys.exit(main())
