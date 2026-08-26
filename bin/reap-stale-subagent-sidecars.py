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
artifact it fed (the review-integrator's Disposition block, the executor's
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

Spec backlink: DoE-claude:pln-reviewer-sidecar-provisioning--6ba704 § C7
Spec backlink (DR-091 home): docs/decisions/DR-091-agent-citizenship-identity-typed-sidecar-contract.md
  (repo ROOT of the DoE-claude tree; a same-numbered archived twin exists —
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
import glob
import os
import subprocess
from pathlib import Path as _Path
import sys
import tempfile
import time
import uuid
from typing import Optional

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(_SCRIPT_DIR, "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402

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
import coordinator_core  # noqa: E402,F401

from repo_identity import resolve_checked_repo_root  # noqa: E402
from coordinator_core.win_portability import no_console_creationflags  # noqa: E402

#: Default age floor in days — mirrors the retired review-trail/findings
#: aged-reap precedent this op supersedes (state-placement-law.md § the
#: review-trail/findings reap doctrine).
_DEFAULT_AGE_FLOOR_DAYS = 14

#: status: values that NEVER get reaped, regardless of liveness/age (the
#: "status can only subtract, never add" carve-out — see module docstring).
_STATUS_NEVER_REAP = {"blocked", "thrashing"}

#: Directory entries under state/subagent-share/ that are not session-id
#: leaves (defensive — mirrors the _NON_SESSION_DIR_NAMES pattern in
#: coordinator_core.session.liveness for the analogous enumeration).
_NON_SESSION_DIR_NAMES = {".git", "__pycache__"}


def _resolve_session_live():
    """Import coordinator_core.session.liveness.session_live via the engine root.

    In-process import (no subprocess, no bash) — same trampoline shape as
    reap-orphaned-in-flight-handoffs.py's _resolve_session_live.
    """
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.session.liveness import session_live
    return session_live


def _fm_field(path: str, key: str) -> str:
    """Single-key frontmatter scan — same idiom as
    reap-orphaned-in-flight-handoffs.py's _fm_field (kept local/duplicated
    rather than imported: that script's copy is not exported as a shared
    lib function, and this op's frontmatter shape — sidecar docs, not
    handoffs — is a different consumer of the same tiny primitive)."""
    prefix = key + ":"
    val = ""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            in_fm = False
            for line in fh:
                stripped_line = line.rstrip("\n").rstrip("\r")
                if not in_fm:
                    if stripped_line.strip() == "---":
                        in_fm = True
                    continue
                if stripped_line.strip() == "---":
                    break
                if stripped_line.startswith(prefix):
                    val = stripped_line[len(prefix):].strip()
                    break
    except OSError:
        return ""
    if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
        val = val[1:-1]
    return val


def _age_days(path: str, now: float) -> float:
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return 0.0
    return max(0.0, (now - mtime) / 86400.0)


def _write_pathspec_file(paths: list) -> str:
    """Write ``paths`` to a uniquely-named temp file, one per line, and
    return its path — the newline-delimited input ``git ...
    --pathspec-from-file=<f>`` expects by default. Mirrors
    ``coordinator_core.ops.ceremony.git_native._write_pathspec_file``'s own
    convention (PID+uuid uniqueness, newline-delimited: no path this op
    ever reaps — a session-id dir plus a sidecar key — contains a literal
    newline byte).

    Sidesteps the ~32KB Windows ``CreateProcess`` command-line ceiling
    (WinError 206) that an argv-list ``git rm``/``git commit -- <paths>``
    hits once the tracked-reap population is large (measured live: 6617
    tracked sidecars under ``state/subagent-share/``, 621047 bytes of
    pathspec argv — 19x the limit). ``--pathspec-from-file`` is supported
    by both ``git rm`` and ``git commit`` since git 2.25, and — unlike
    chunking — keeps the tracked-reap commit atomic: one commit for the
    whole population, not one per chunk. Caller owns cleanup
    (``finally: os.remove(path)``).
    """
    pathspec_path = os.path.join(
        tempfile.gettempdir(), f"reap-stale-sidecars-pathspec-{os.getpid()}-{uuid.uuid4().hex}.txt"
    )
    with open(pathspec_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(paths) + "\n")
    return pathspec_path


def _tracked_paths(repo_root: str, rel_paths: list, under: str = "state/subagent-share") -> set:
    """Batched tracked-check: one `git ls-files` spawn scoped to `under`
    (the whole reap subtree) instead of one `--error-unmatch` probe per
    file. `git ls-files` has no `--pathspec-from-file` support (verified
    live — `error: unknown option`, unlike `git rm`/`git commit`), so an
    argv-list `-- <paths>` would still hit the ~32KB Windows `CreateProcess`
    ceiling at reap-population scale (§ `_write_pathspec_file`). Naming the
    single directory instead keeps this to one fixed-size spawn regardless
    of candidate count — every path this script ever reaps lives under
    `under` by construction (it is `share_dir`, relative to `repo_root`).

    `git ls-files` always echoes matches in POSIX (forward-slash) form even
    when fed a backslash-separated pathspec on Windows — a raw string
    comparison against a Windows `os.path.relpath` value silently matches
    nothing. Both legs go through `.as_posix()` before comparing; the
    returned set keeps the caller's original (possibly backslash) strings
    so callers need no format awareness."""
    if not rel_paths:
        return set()
    result = subprocess.run(
        ["git", "ls-files", "--", _Path(under).as_posix()],
        cwd=repo_root, capture_output=True, text=True, check=False, **no_console_creationflags(),
    )
    if result.returncode != 0:
        return set()
    tracked_posix = {line for line in result.stdout.splitlines() if line}
    posix_by_orig = {rel: _Path(rel).as_posix() for rel in rel_paths}
    return {rel for rel, posix in posix_by_orig.items() if posix in tracked_posix}


def main(argv: Optional[list] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    parser = argparse.ArgumentParser(
        prog="reap-stale-subagent-sidecars.py",
        description="Delete-by-convention sweep of state/subagent-share/ (DR-091 sidecar home).",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--age-floor-days", type=int, default=_DEFAULT_AGE_FLOOR_DAYS)
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

    repo_root, verdict = resolve_checked_repo_root(explicit_root=None)
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

    share_dir = os.path.join(repo_root, "state", "subagent-share")
    if not os.path.isdir(share_dir):
        print(f"reap-stale-subagent-sidecars.py: {share_dir} does not exist; nothing to do")
        return 0

    now = time.time()

    to_reap: list = []
    preserved_live_session = 0
    preserved_too_young = 0
    preserved_status = 0

    for session_id in sorted(os.listdir(share_dir)):
        if session_id in _NON_SESSION_DIR_NAMES:
            continue
        session_dir = os.path.join(share_dir, session_id)
        if not os.path.isdir(session_dir):
            continue

        if session_live(session_id, cwd=repo_root):
            # Entire directory preserved — an in-flight session's own
            # sidecar(s) are never reaped out from under it, regardless of
            # any individual file's status or age.
            preserved_live_session += len(glob.glob(os.path.join(session_dir, "*.md")))
            continue

        for f in sorted(glob.glob(os.path.join(session_dir, "*.md"))):
            if not os.path.isfile(f):
                continue

            status = _fm_field(f, "status").lower()
            if status in _STATUS_NEVER_REAP:
                preserved_status += 1
                continue

            age = _age_days(f, now)
            if age < age_floor_days:
                preserved_too_young += 1
                continue

            to_reap.append(f)

    if not to_reap:
        print("nothing to reap")
        if preserved_live_session:
            print(f"{preserved_live_session} sidecar(s) retained (owning session still live)")
        if preserved_status:
            print(f"{preserved_status} sidecar(s) retained (status: blocked/thrashing)")
        if preserved_too_young:
            print(f"{preserved_too_young} sidecar(s) retained (younger than {age_floor_days}-day age floor)")
        return 0

    rel_by_file = {f: os.path.relpath(f, repo_root) for f in to_reap}
    tracked_rels = _tracked_paths(
        repo_root, list(rel_by_file.values()), under=os.path.relpath(share_dir, repo_root)
    )
    tracked_to_reap = []
    untracked_to_reap = []
    for f in to_reap:
        if rel_by_file[f] in tracked_rels:
            tracked_to_reap.append(f)
        else:
            untracked_to_reap.append(f)

    if dry_run:
        for f in tracked_to_reap:
            print(f"reap-stale-subagent-sidecars.py: [dry-run] would reap {f}")
        for f in untracked_to_reap:
            print(f"reap-stale-subagent-sidecars.py: [dry-run] would reap {f} (untracked; plain rm)")
        print(f"{len(to_reap)} stale subagent-share sidecar(s) would be reaped (dry-run)")
        if preserved_live_session:
            print(f"{preserved_live_session} sidecar(s) would be retained (owning session still live)")
        if preserved_status:
            print(f"{preserved_status} sidecar(s) would be retained (status: blocked/thrashing)")
        if preserved_too_young:
            print(f"{preserved_too_young} sidecar(s) would be retained (younger than {age_floor_days}-day age floor)")
        return 0

    for f in untracked_to_reap:
        try:
            os.remove(f)
        except OSError:
            pass
        print(f"reaped {f} (untracked, plain rm)")

    if tracked_to_reap:
        tracked_rel = [os.path.relpath(f, repo_root) for f in tracked_to_reap]
        # --pathspec-from-file=<f> instead of a full argv pathspec list --
        # see _write_pathspec_file's docstring: at scale (thousands of
        # tracked sidecars) the argv form blows Windows's ~32KB
        # CreateProcess command-line ceiling (WinError 206). One pathspec
        # file feeds both calls, preserving single-commit atomicity.
        pathspec_file = _write_pathspec_file(tracked_rel)
        try:
            rm_res = subprocess.run(
                ["git", "rm", "-q", f"--pathspec-from-file={pathspec_file}"], cwd=repo_root,
                capture_output=True, text=True, check=False, **no_console_creationflags(),
            )
            if rm_res.returncode != 0:
                sys.stderr.write(rm_res.stderr)
                return rm_res.returncode

            commit_msg = f"reap {len(tracked_to_reap)} stale subagent-share sidecar(s)"
            commit_res = subprocess.run(
                ["git", "commit", "-q", "-m", commit_msg, f"--pathspec-from-file={pathspec_file}"],
                cwd=repo_root,
                capture_output=True, text=True, check=False, **no_console_creationflags(),
            )
            if commit_res.returncode != 0:
                sys.stderr.write(
                    f"reap-stale-subagent-sidecars.py: git commit failed after git rm — "
                    f"{len(tracked_to_reap)} sidecar(s) staged for deletion, not committed:\n"
                )
                for f in tracked_to_reap:
                    sys.stderr.write(f"  {f}\n")
                return commit_res.returncode
        finally:
            try:
                os.remove(pathspec_file)
            except OSError:
                pass
        for f in tracked_to_reap:
            print(f"reaped {f}")

    print(f"{len(to_reap)} stale subagent-share sidecar(s) reaped")
    if preserved_live_session:
        print(f"{preserved_live_session} sidecar(s) retained (owning session still live)")
    if preserved_status:
        print(f"{preserved_status} sidecar(s) retained (status: blocked/thrashing)")
    if preserved_too_young:
        print(f"{preserved_too_young} sidecar(s) retained (younger than {age_floor_days}-day age floor)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
