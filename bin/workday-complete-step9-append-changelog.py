# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
# Spec backlink: DoE-claude:pln-wire-claude-klabauter-fleet-archive-prun-8fd552 § strang-10
"""
workday-complete-step9-append-changelog.py -- Step 9 of /workday-complete: append the
daily block to the week-changelog.

Purpose: encapsulates the changelog-append logic that was empirically EM-skippable
when expressed as inline bash in the skill body. Concentrating the logic here removes
EM judgment from a mechanical procedure and makes the step idempotent and testable.

Finish-strangler port (Windows de-bash campaign, chunk F1-c-step9, 2026-07-21):
Port of: workday-complete-step9-append-changelog.sh (DoE 6fb5fb37, 2026-07-22),
whose DR-216 strang-10 facade dispatched two native ops via a spawned
`python3 -m coordinator_core.invoke` subprocess (cc_invoke.route_mutation). This port
retires that subprocess hop entirely: `coordinator_core.ops.changelog_ops.compute_day_fields`
and `.append_day` are called DIRECTLY, in-process -- matching the direct-import
trampoline pattern already established for this exact op family's sibling
(backfill-week-changelog-gaps.py -> changelog.backfill_gaps). Zone A (git-log field
computation) and Zone B (HEADER staleness decision, block compose) are now pure-Python
call sites into claude-klabauter; Zone C (git add/commit/push) remains this script's own
responsibility, unchanged (DR-216 D2(v): the op never commits).

Day-anchor note (retargets the RETAIN blocker in the prior bash header): the bash
predecessor was kept as bash specifically because
bin/tests/test-workday-evening-tz-coherence.sh (T2; DoE 290997c7, 2026-07-22) grepped
its SOURCE TEXT for a literal `coordinator_local_day` shell assignment. That
structural grep-proof is retargeted (this port) to assert the equivalent Python
fact instead: this file imports and calls `coordinator_core.daily_day.local_day()`
-- the already-native Python peer of coordinator-daily-day.sh's (DoE c6d97219,
2026-07-22) coordinator_local_day() (see
coordinator_core/daily_day.py, used identically by
coordinator_core.ops.workday_complete_backfill_scan) -- for its LOCAL_TODAY anchor,
never a bare UTC-now-derived call. See the local_today/today assignments below,
which the retargeted test greps verbatim.

DR-276 note: this trampoline is NOT a pure `main(argv)` passthrough — it is
its own multi-zone orchestrator (Zone A: read-only field computation, Zone B:
compose + native write via `changelog_ops.append_day`, Zone C: git
add/commit/push) — so it cannot route through
`coordinator_core.cli_entry.run_op_main` the way
`backfill-week-changelog-gaps.py` (its changelog_ops sibling) does. It instead
wraps the Call 2 (`append_day`) invocation in
`coordinator_core.cli_entry.recording_declared_writes`, the public helper that
factors out `run_op_main`'s own collect-then-record dance for exactly this
case, so the changelog path `append_day` declares still becomes a session
scope-touch claim without this file reaching into
`ipc._record_self_reported_touches` directly.

Spec backlink: docs/plans/2026-07-19-debash-coordinator-windows.md § step9-changelog
Spec backlink: docs/plans/2026-07-21-debash-consolidated-wave.md § F1-c-step9 [DEAD-CITATION: plan file never committed to this repo]
Spec backlink: commands/workday-complete.md § Step 9: Append to Week-Changelog
Spec backlink: docs/decisions/DR-276-operator-clis-record-session-writes-at-a.md

Usage:
  workday-complete-step9-append-changelog.py [OPTIONS] [SCOPE_SUMMARY]

Positional:
  SCOPE_SUMMARY   One-line day summary for the **Scope:** field. If omitted, the
                  **Scope:** line is omitted from the block entirely (C4 omit-by-default).
                  An explicit value wins unconditionally over any derived heuristic.

Options:
  --no-push          Skip the git push step.
  --dry-run          Print block to stdout; no file write, no commit, no push. Implies --no-push.
  --commit-span R    <BASE>..<TIP> (2-dot, git range) -- keys Commits:/Plans touched: to a
                      machine-scoped span (e.g. from backfill-scan) instead of the derived
                      date window.
  --for-date DATE     Backfill a specific (past) day. Overrides TODAY.

Environment (populated by Step 1 and Step 5 of /workday-complete):
  RC_VALIDATE       Numeric exit code or a Step 1 status word ("skipped", "blocked",
                    "ubt-overridden", "lib-missing", "interp-missing", "config-malformed");
                    populates
                    Validation: validate=...   Default when UNSET: "not-run" (Step 1 never
                    ran) -- deliberately NOT "skipped", which means Step 1 ran and found
                    no fast-test configured. See docs/wiki/workday-workweek-cadence.md
                    § Week-changelog Validation: schema.
  RC_PLUGIN_SUITE   Numeric exit code; populates plugin-suite=...   Default: "n/a" if unset.
  COORDINATOR_ROOT  TEST-ONLY override for the repo root (must not be set in a live
                    ceremony; warns if set to a non-cwd-toplevel path). Default: git toplevel.
                    Also the repo_root passed to BOTH native calls (Call 1 and Call 2).
  COORDINATOR_MACHINE  Override machine name (used by tests). Read natively by
                    coordinator_core.machine_resolver.compute_machine().
  COORDINATOR_ROOT_WARN_SUPPRESS  Set to "1" to silence the COORDINATOR_ROOT mismatch warning.

Stdout: structured one-line progress messages prefixed [step9].
Stderr: human-readable detail.

Exit codes:
  0 -- block appended and committed (or dry-run succeeded, or idempotent no-op).
  1 -- CLI argument validation error, CLAUDE_KLABAUTER_ROOT/coordinator_core dependency-resolution
      error, or git commit error.
  2 -- native dispatch failure (Call 1 or Call 2: op-level exception -- neither call has
      a bash fallback), OR push rejected.
  3 -- HEADER staleness skip (informational, not failure).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class _ArgError(Exception):
    """Client-side CLI argument validation failure -- mirrors the bash oracle's exit 1."""


class _CommitError(Exception):
    """git commit failed on the frozen, explicit pathspec (Zone C)."""


def _get_staged_paths(coordinator_root):
    """Repo-root-relative paths currently staged (`git diff --cached --name-only`).

    This is a raw snapshot of the SHARED index, not a per-session set: on a
    working tree shared by multiple concurrent sessions, `git diff --cached`
    returns the UNION of every session's staged work, with no way to tell
    them apart on its own. Callers wanting "paths this session may safely
    commit" must run this through `_filter_pre_staged_by_ownership` before
    treating it as this ceremony's own pre-stage.
    """
    out = subprocess.run(
        ["git", "-C", coordinator_root, "diff", "--cached", "--name-only"],
        capture_output=True, text=True,
    ).stdout
    return [line for line in out.splitlines() if line]


def _filter_pre_staged_by_ownership(coordinator_root, pre_staged_paths):
    """Filter a raw `_get_staged_paths` snapshot down to paths this session may
    safely fold into its own commit -- i.e. paths that are unclaimed, or
    claimed by THIS session. A path claimed by a DIFFERENT live session is
    dropped: it is that peer's in-flight work, staged in the shared index
    concurrently with this ceremony, not something step9 ever staged itself.

    Reuses the SAME in-process ownership resolver
    `coordinator_core.ops.session.safe_commit_offer.full_ownership_map` that
    Step 2.5's dirty-tree scan (`workday_complete_step2_5_dirty_tree.
    _resolve_claim_context`) already relies on for the identical question --
    no second ownership mechanism is invented here.

    Fail-safe direction: EXCLUDE whenever ownership cannot be confidently
    resolved for a path, never include-by-default. Concretely:
      - session id unresolvable, or the ownership map raises -- exclude
        EVERY pre-staged path (no claim awareness this run at all).
      - a path with no peer-map entry (unclaimed, or claimed by this
        session per `mine_paths`) -- keep.
      - a path with a peer-map entry whose liveness is "live" -- drop (a
        different live session owns it).
      - a path with a peer-map entry whose liveness is "dead" -- keep (a
        stale claim is not a live peer's in-flight work).
      - a path with a peer-map entry whose liveness is "undetermined" --
        drop: an unresolved liveness verdict must never be read as
        permission to commit over a possibly-live peer.
    """
    if not pre_staged_paths:
        return []
    try:
        from coordinator_core.ops.session.safe_commit_offer import full_ownership_map
        from coordinator_core.session import core as _session_core
    except Exception:
        return []

    try:
        sid = _session_core.resolve_session_id(coordinator_root)
    except Exception:
        sid = ""
    if not sid:
        return []

    try:
        mine_paths, peer_map = full_ownership_map(sid, coordinator_root)
    except Exception:
        return []

    kept = []
    for path in pre_staged_paths:
        if path in mine_paths:
            kept.append(path)
            continue
        peer_fact = peer_map.get(path)
        if peer_fact is None:
            kept.append(path)
            continue
        if peer_fact.get("liveness") == "dead":
            kept.append(path)
            continue
        print(
            f"[step9] excluding pre-staged path claimed by another session: "
            f"{path} owner={peer_fact.get('owner')} liveness={peer_fact.get('liveness')}",
            file=sys.stderr,
        )
    return kept


def _to_repo_relative(coordinator_root, path):
    """Normalize an absolute or repo-root-relative path to a repo-root-relative,
    forward-slash pathspec (matches `git diff --cached --name-only` output on
    both POSIX and Windows)."""
    rel = os.path.relpath(path, coordinator_root)
    return Path(rel).as_posix()


def _commit_frozen_paths(coordinator_root, commit_paths, commit_msg):
    """Commit EXACTLY `commit_paths` via an explicit pathspec -- never a bare
    `git commit` that would sweep in whatever else happens to be in the index.
    `commit_paths` must be the set step9 observed and intended at entry: its own
    output files, plus whatever was ALREADY staged before step9 ran and this
    session could confirm is not a DIFFERENT live session's in-flight work (see
    `_filter_pre_staged_by_ownership` at the call site -- a raw `git diff
    --cached` snapshot on this shared working tree is the union of every
    concurrent session's staged paths, not this ceremony's own pre-stage, and
    must never be trusted unfiltered). Anything a peer stages DURING step9's
    own execution is a snapshot omission by construction and is left untouched
    in the index.

    Returns the short commit SHA, or None if none of commit_paths has staged
    changes (idempotent no-op). Raises _CommitError on a genuine git-commit failure.
    """
    if not commit_paths:
        return None
    diff = subprocess.run(
        ["git", "-C", coordinator_root, "diff", "--cached", "--name-only", "--", *commit_paths],
        capture_output=True, text=True,
    ).stdout.strip()
    if not diff:
        return None
    commit_result = subprocess.run(
        ["git", "-C", coordinator_root, "commit", "-m", commit_msg, "--", *commit_paths],
        capture_output=True, text=True,
    )
    combined_output = (commit_result.stdout or "") + (commit_result.stderr or "")
    if combined_output:
        sys.stdout.write(combined_output)
        if not combined_output.endswith("\n"):
            sys.stdout.write("\n")
    if commit_result.returncode != 0:
        raise _CommitError("git commit failed")
    return subprocess.run(
        ["git", "-C", coordinator_root, "rev-parse", "--short", "HEAD"],
        capture_output=True, text=True,
    ).stdout.strip() or "unknown"


def _head_on_remote(coordinator_root, branch):
    """Return True if local HEAD is already an ancestor of origin/<branch> (i.e.
    already reached the remote -- by this process's own push OR a racing hook that
    won first), False if it definitively is not, or None if this could not be
    determined (fetch itself failed, e.g. no network)."""
    fetch = subprocess.run(
        ["git", "-C", coordinator_root, "fetch", "origin", branch],
        capture_output=True, text=True, timeout=30,
    )
    if fetch.returncode != 0:
        return None
    check = subprocess.run(
        ["git", "-C", coordinator_root, "merge-base", "--is-ancestor", "HEAD",
         f"refs/remotes/origin/{branch}"],
        capture_output=True, text=True, timeout=15,
    )
    return check.returncode == 0


def _parse_args(argv):
    no_push = False
    dry_run = False
    scope_arg = ""
    for_date = ""
    commit_span = ""
    scope_seen_positional = False

    i = 0
    n = len(argv)
    while i < n:
        arg = argv[i]
        if arg == "--no-push":
            no_push = True
            i += 1
        elif arg == "--dry-run":
            dry_run = True
            no_push = True
            i += 1
        elif arg == "--commit-span":
            if i + 1 >= n:
                raise _ArgError(
                    "--commit-span requires a <BASE>..<TIP> argument (2-dot range only; got '')"
                )
            commit_span = argv[i + 1]
            if not commit_span or "..." in commit_span or ".." not in commit_span:
                raise _ArgError(
                    "--commit-span requires a <BASE>..<TIP> argument (2-dot range only; "
                    f"got '{commit_span}')"
                )
            i += 2
        elif arg == "--for-date":
            if i + 1 >= n:
                raise _ArgError("--for-date requires a YYYY-MM-DD argument (got '')")
            for_date = argv[i + 1]
            if not _DATE_RE.match(for_date):
                raise _ArgError(f"--for-date requires a YYYY-MM-DD argument (got '{for_date}')")
            i += 2
        elif arg == "--":
            # Byte-parity quirk carried over from the bash oracle: "--" ends
            # option parsing and the loop simply stops -- any remaining argv
            # is dropped, never treated as positional. Not a bug this port
            # introduces; preserved for exact CLI-contract parity.
            break
        elif arg.startswith("-"):
            raise _ArgError(f"Unknown option: {arg}")
        else:
            scope_arg = arg
            scope_seen_positional = True
            i += 1

    del scope_seen_positional
    return {
        "no_push": no_push,
        "dry_run": dry_run,
        "scope_arg": scope_arg,
        "for_date": for_date,
        "commit_span": commit_span,
    }


def _resolve_coordinator_root():
    """Mirror the bash oracle's COORDINATOR_ROOT resolution + mismatch warning.

    The cwd-derived candidate now comes from the checked resolver
    (`repo_identity.resolve_checked_repo_root`) rather than a fresh `git
    rev-parse --show-toplevel` spawn. WRITER (AC10): main() goes on to call
    changelog_ops.append_day(), a native mutating write into the resolved
    root's changelog. A positive MISMATCH refuses HERE, before that write
    (and before every other call site in main()) — the DR-277 carve-out
    ("prevents a write into a foreign tree") licenses the hard deny.
    UNRESOLVED never refuses (DR-277, AC4). This is independent of, and in
    addition to, the pre-existing COORDINATOR_ROOT-vs-cwd-toplevel warning
    below.

    Review: code-reviewer (P1) — COORDINATOR_ROOT read BEFORE the identity
    gate runs, and the gate is skipped entirely when the override is set.
    An explicitly-supplied root is caller intent that never touched cwd
    (AC3) -- routing it through `resolve_checked_repo_root` as
    `explicit_root` is that same rule applied to this env-var-shaped
    explicit root, exactly as it bypassed the old bare `git rev-parse`
    call. Gating a cwd-derived MISMATCH before the override was even read
    defeated the override's whole purpose.
    """
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from repo_identity import resolve_checked_repo_root

    override = os.environ.get("COORDINATOR_ROOT", "")
    warn_suppress = os.environ.get("COORDINATOR_ROOT_WARN_SUPPRESS", "") == "1"

    if override:
        # Explicit root (AC3): resolve_checked_repo_root returns EXPLICIT
        # and gates nothing on it -- the cwd-derived identity MISMATCH gate
        # below is precisely what this override exists to sidestep.
        coordinator_root, _verdict = resolve_checked_repo_root(explicit_root=override)
        if not warn_suppress:
            cwd_root, _cwd_verdict = resolve_checked_repo_root(explicit_root=None)
            cwd_top = ""
            if cwd_root:
                try:
                    cwd_top = str(Path(cwd_root).resolve(strict=False))
                except OSError:
                    cwd_top = ""
            try:
                cr_real = str(Path(override).resolve(strict=False))
            except OSError:
                cr_real = override
            if cwd_top and cr_real != cwd_top:
                print(
                    f"WARNING: COORDINATOR_ROOT='{override}' differs from the cwd git toplevel "
                    f"'{cwd_top}'. COORDINATOR_ROOT is a TEST-ONLY override; continuing with it "
                    "as the repo root for this run. If this is a live ceremony on a consumer "
                    "project, unset COORDINATOR_ROOT and re-run (COORDINATOR_ROOT_WARN_SUPPRESS=1 "
                    "silences this in tests).",
                    file=sys.stderr,
                )
        return coordinator_root

    cwd_root, verdict = resolve_checked_repo_root(explicit_root=None)
    if verdict["verdict"] == "MISMATCH":
        print(verdict["message"], file=sys.stderr)
        sys.exit(1)

    cwd_top = ""
    if cwd_root:
        try:
            cwd_top = str(Path(cwd_root).resolve(strict=False))
        except OSError:
            cwd_top = ""

    coordinator_root = cwd_top
    if not coordinator_root:
        # No git root resolved from cwd at all -- distinct from the MISMATCH
        # identity gate above (which fires on POSITIVE evidence of a
        # different real repo). This is "nowhere to write", not an identity
        # mismatch; UNRESOLVED-with-no-root refusing here is not the AC4
        # carve-out being violated (see repo_identity.py's own no-root leg).
        print("ERROR: cwd is not a git repo and COORDINATOR_ROOT is not set", file=sys.stderr)
        sys.exit(1)
    return coordinator_root


def _get_branch(coordinator_root):
    """Mirror the bash oracle's BRANCH/PUSH_BRANCH resolution chain (helper, then
    `git branch --show-current`), both scoped to -C coordinator_root."""
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    import cc_invoke
    from cc_invoke import _resolve_claude_klabauter_root, child_env

    branch_helper = os.path.join(_SCRIPT_DIR, "coordinator-current-branch.py")
    try:
        r = subprocess.run(
            [sys.executable, branch_helper], cwd=coordinator_root, capture_output=True, text=True, timeout=15,
            env=child_env(), **cc_invoke._no_console_kw(_resolve_claude_klabauter_root()),
        )
        if r.returncode == 0:
            out = r.stdout.strip()
            if out:
                return out
    except (OSError, subprocess.TimeoutExpired, RuntimeError):
        # Review: code-reviewer — subprocess.run(timeout=...) raises
        # TimeoutExpired (a SubprocessError, not an OSError); the bare
        # OSError clause left a hang uncaught and crashed the ceremony.
        # RuntimeError added (P3) — _resolve_claude_klabauter_root() inside the
        # _no_console_kw() call can raise RuntimeError, uncovered by the
        # prior tuple; low risk in practice since main() already resolves
        # and exits(2) on CLAUDE_KLABAUTER_ROOT failure before _get_branch is reached,
        # but this is the same unguarded-re-resolution shape worth covering.
        pass
    try:
        r = subprocess.run(
            ["git", "-C", coordinator_root, "branch", "--show-current"],
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode == 0:
            out = r.stdout.strip()
            if out:
                return out
    except (OSError, subprocess.TimeoutExpired):
        pass
    return ""


def main(argv):
    if "-h" in argv or "--help" in argv:
        # Intercepted before _parse_args, whose byte-parity loop would reject
        # these as unknown options. Mirrors the sibling backfill-week-changelog-
        # gaps.py, so both CLIs in this family answer --help the same way.
        print(__doc__)
        return 0

    try:
        args = _parse_args(argv)
    except _ArgError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    no_push = args["no_push"]
    dry_run = args["dry_run"]
    scope_arg = args["scope_arg"]
    for_date = args["for_date"]
    commit_span = args["commit_span"]

    coordinator_root = _resolve_coordinator_root()

    # Snapshot the index BEFORE step9 does anything of its own. On a working
    # tree used by exactly one session this would be the "already-staged-by-
    # someone-else" set the 2.6/4.5 pre-stage contract describes; on the
    # SHARED tree this repo actually runs on, `git diff --cached` returns the
    # union of every concurrent session's staged work, with no way to tell
    # them apart from the snapshot alone. `_filter_pre_staged_by_ownership`
    # (called below, once coordinator_core is importable) is what narrows
    # this raw union down to paths this ceremony may actually fold in.
    # Anything staged by a peer AFTER this snapshot point is, by
    # construction, not in this snapshot and will not be committed either way.
    pre_staged_paths = _get_staged_paths(coordinator_root)

    # ---------------------------------------------------------------------
    # Dependency resolution: CLAUDE_KLABAUTER_ROOT + coordinator_core (Call 1/Call 2's
    # engine home). Exit 1 mirrors the bash oracle's lib-sourcing/`_cc_resolve_deps`
    # failure class (dependency resolution), distinct from an op-level failure (exit 2).
    # ---------------------------------------------------------------------
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import _resolve_claude_klabauter_root

    try:
        claude_klabauter_root = _resolve_claude_klabauter_root()
        # Verify coordinator_core actually LIVES at the resolved claude_klabauter_root
        # before trusting the imports below. sys.path.insert(0, claude_klabauter_root)
        # alone does not guarantee this: if claude_klabauter_root is empty (or lacks
        # coordinator_core) but coordinator_core is ALSO reachable elsewhere
        # on this interpreter's sys.path -- e.g. a developer's ambient
        # `pip install -e .` of the engine, ahead or behind the inserted
        # entry -- the bare import below silently succeeds against that
        # OTHER install instead of failing. That is a dependency-resolution
        # failure wearing a success's clothes: the operator asked for the
        # engine at claude_klabauter_root and got a possibly-different one with no
        # signal. Fail loud here instead, before either import is attempted.
        if not os.path.isdir(os.path.join(claude_klabauter_root, "coordinator_core")):
            raise RuntimeError(
                f"coordinator_core not found under resolved CLAUDE_KLABAUTER_ROOT={claude_klabauter_root!r}"
            )
        if claude_klabauter_root not in sys.path:
            sys.path.insert(0, claude_klabauter_root)
        from coordinator_core.state_root import coordinator_state_root
        from coordinator_core.machine_resolver import compute_machine
        from coordinator_core.daily_day import local_day as coordinator_local_day
        from coordinator_core.ops import changelog_ops
        from coordinator_core.cli_entry import recording_declared_writes
    except RuntimeError as exc:
        print(f"ERROR: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return 1
    except ImportError as exc:
        print(f"ERROR: coordinator_core dependency not importable: {exc}", file=sys.stderr)
        return 1

    # Resolve per-repo state root through the seam (AC4 — coordinator_state_root
    # adoption). No subject/artifact = Rule 5 (default, non-central): claude-klabauter state
    # root when cwd git root is the meta-repo, otherwise <git_root>/state.
    try:
        repo_state_root = coordinator_state_root(git_root=coordinator_root)
    except Exception as exc:  # noqa: BLE001 — mirror bash's blanket fail-loud on this call
        print(f"ERROR: coordinator_state_root resolution failed: {exc}", file=sys.stderr)
        return 1

    machine = compute_machine()

    # LOCAL_TODAY: the actual local day at ceremony time, regardless of --for-date.
    # _LOCAL_TODAY_ANCHOR_LINE (retargeted structural-grep proof, replaces the bash
    # oracle's literal `coordinator_local_day` shell-assignment text):
    local_today = coordinator_local_day()  # noqa: F841 (kept as its own statement for the grep proof)
    today = for_date or local_today
    is_backfill = bool(for_date) and for_date != local_today

    changelog_file = os.path.join(repo_state_root, "week-changelog", f"{today}.md")
    daily_summary = os.path.join(coordinator_root, "archive", "daily-summaries", f"{today}-{machine}.md")

    # -----------------------------------------------------------------------
    # Call 1 — changelog.compute_day_fields (native, read-only). Direct
    # in-process call (no cc_invoke/JSON-RPC hop) — matches the
    # backfill-week-changelog-gaps.py direct-import precedent for this same
    # op family. repo_root = coordinator_root (the already-resolved,
    # already-warned-about repo root this whole ceremony targets).
    # -----------------------------------------------------------------------
    try:
        fields = changelog_ops.compute_day_fields(
            worktree=Path(coordinator_root),
            date=today,
            commit_span=commit_span or None,
            local_today=local_today,
        )
    except Exception as exc:  # noqa: BLE001 — op-level failure, no bash fallback (big-bang cutover)
        print(f"ERROR: changelog.compute_day_fields native dispatch failed: {exc}", file=sys.stderr)
        return 2

    commit_count = fields["commit_count"]
    commit_range = fields["commit_range"]
    plans_touched = fields["plans_touched"]
    handoffs_list = fields["handoffs_list"]
    decisions = fields["decisions"]
    blockers = fields["blockers"]
    has_non_trivial = bool(fields["has_non_trivial"])
    reviewed_lines = list(fields["reviewed_lines"])
    header_stale = bool(fields["header_stale"])
    header_stale_days = fields["header_stale_days"]

    # -------------------------------------------------------------------
    # Staleness guard: HEADER.md Week starting: must be <=14 days ago.
    # compute_day_fields reports header_stale/header_stale_days
    # report-only; this wrapper still owns the skip-or-proceed decision
    # (unchanged from the prior Zone-A behaviour). Backfill (--for-date)
    # bypasses the staleness guard.
    # -------------------------------------------------------------------
    if not for_date and header_stale:
        print(
            f"WARN: HEADER.md is stale (week started {header_stale_days} days ago, >14). "
            "Was `/workweek-complete` skipped?",
            file=sys.stderr,
        )
        print("[step9] SKIPPED (HEADER stale)")
        return 3

    # Scope field (C4 — omit-by-default). An explicit override wins unconditionally.
    scope = scope_arg

    branch = _get_branch(coordinator_root) or "unknown"

    # Unset default is `not-run` (Step 1 never emitted), NOT `skipped` — `skipped`
    # is a positive Step 1 emission meaning "validation ran, nothing configured".
    validate_val = os.environ.get("RC_VALIDATE") or "not-run"
    plugin_suite_val = os.environ.get("RC_PLUGIN_SUITE") or "n/a"

    # Compose the block via the SAME function the real write (append_day) uses
    # internally (changelog_ops._compose_block) — single source of truth, so the
    # --dry-run preview is byte-identical to what a real write produces (a strict
    # improvement over the retired bash oracle's own hand-duplicated compose_block(),
    # which was NOT byte-identical to append_day's write on a backfill day per its
    # own header comment).
    new_block = changelog_ops._compose_block(
        date=today,
        machine=machine,
        branch=branch,
        commit_count=commit_count,
        commit_range=commit_range,
        scope=scope,
        plans_touched=plans_touched,
        handoffs_list=handoffs_list,
        decisions=decisions,
        blockers=blockers,
        rc_validate=validate_val,
        rc_plugin_suite=plugin_suite_val,
        reviewed_lines=reviewed_lines,
        has_non_trivial=has_non_trivial,
        is_backfill=is_backfill,
    )

    if dry_run:
        print(new_block)
        print("[step9] push: skipped (--dry-run)")
        print("[step9] OK")
        return 0

    # -----------------------------------------------------------------------
    # Call 2 — changelog.append_day (native, mutating). Unconditional native
    # dispatch (no disk-presence gate, no legacy fallback): an op-level
    # exception fails loud (exit 2), never falls back to a legacy write.
    # -----------------------------------------------------------------------
    # DR-276: this trampoline calls changelog_ops.append_day() directly (Zone
    # A/B, not a `main(argv)` passthrough), so it cannot route through
    # `coordinator_core.cli_entry.run_op_main` the way a pure trampoline
    # does. It uses `cli_entry.recording_declared_writes` around this one
    # write call instead, so the changelog path append_day declares still
    # becomes a session scope-touch claim rather than an orphan at the
    # `scoped_git_commit` sink, without forking a second recorder dialect.
    try:
        with recording_declared_writes(cwd=coordinator_root):
            append_result = changelog_ops.append_day(
                worktree=Path(coordinator_root),
                date=today,
                machine=machine,
                branch=branch,
                commit_count=commit_count,
                commit_range=commit_range,
                scope=scope,
                plans_touched=plans_touched,
                handoffs_list=handoffs_list,
                decisions=decisions,
                blockers=blockers,
                rc_validate=validate_val,
                rc_plugin_suite=plugin_suite_val,
                reviewed_lines=reviewed_lines,
                has_non_trivial=has_non_trivial,
                is_backfill=is_backfill,
            )
    except Exception as exc:  # noqa: BLE001 — op-level failure, no bash fallback (big-bang cutover)
        print(f"ERROR: changelog.append_day native dispatch failed: {exc}", file=sys.stderr)
        return 2

    out_path = append_result.get("out_path")
    if out_path:
        changelog_file = out_path

    print(f"[step9] block written: {changelog_file}")

    # ---------------------------------------------------------------------
    # Zone C: Commit. DR-216 D2(v): caller retains commit responsibility.
    # ---------------------------------------------------------------------
    files_to_commit = [changelog_file]
    if os.path.isfile(daily_summary):
        # covered_tip_sha is emitted by the analyst agent (Step 4b) — not
        # computed here. Step9 commits the analyst-authored summary as-is;
        # the backfill scan detects a missing field as a GAP (fail-loud).
        files_to_commit.append(daily_summary)
    # Legacy read-compat: a pre-machine-naming <date>.md may also exist.
    legacy_daily_summary = os.path.join(coordinator_root, "archive", "daily-summaries", f"{today}.md")
    if os.path.isfile(legacy_daily_summary):
        files_to_commit.append(legacy_daily_summary)

    subprocess.run(
        ["git", "-C", coordinator_root, "add", "--", *files_to_commit],
        capture_output=True, text=True,
    )

    # Second guard: refuse to commit at all when this ceremony's OWN output
    # (the changelog block, plus the daily summary if present) has no actual
    # staged diff of its own -- e.g. an idempotent re-run against an already-
    # up-to-date changelog. Without this check, a non-empty PRE-STAGED set
    # (this session's or a filtered-in peer path) would still make
    # `_commit_frozen_paths`'s own union-scoped diff check pass, producing a
    # commit whose subject claims a "daily block" it does not itself contain
    # -- the exact shape seen in d721e7b3e / 9822a595f (a peer's file
    # committed alone, under this ceremony's own commit message).
    own_rel = [_to_repo_relative(coordinator_root, f) for f in files_to_commit]
    own_diff = subprocess.run(
        ["git", "-C", coordinator_root, "diff", "--cached", "--name-only", "--", *own_rel],
        capture_output=True, text=True,
    ).stdout.strip()
    if not own_diff:
        print(
            f"[step9] refusing to commit: named artifact ({changelog_file}) has no "
            "staged changes of its own -- not committing any pre-staged/peer paths "
            "under this ceremony's commit message",
        )
        print("[step9] block unchanged (idempotent no-op)")
        return 0

    # Frozen intended set: step9's own outputs, UNIONED with whatever was already
    # staged BEFORE step9 ran and this session may safely fold in -- filtered by
    # ownership (see `_filter_pre_staged_by_ownership`) so a DIFFERENT live
    # session's in-flight staged work is never swept into this commit. Never
    # "whatever happens to be in the index right now", which would also absorb
    # anything a concurrent peer staged mid-run in this shared working tree.
    filtered_pre_staged = _filter_pre_staged_by_ownership(coordinator_root, pre_staged_paths)
    commit_paths = sorted(set(filtered_pre_staged) | set(own_rel))

    # Prefix with [backfill] when wrapping a past day (C2).
    if is_backfill:
        commit_msg = f"chore(week-changelog): [backfill] daily block {today} {machine}"
    else:
        commit_msg = f"chore(week-changelog): daily block {today} {machine}"

    try:
        commit_sha = _commit_frozen_paths(coordinator_root, commit_paths, commit_msg)
    except _CommitError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if commit_sha is None:
        print("[step9] block unchanged (idempotent no-op)")
        return 0
    print(f"[step9] commit: {commit_sha}")

    # ---------------------------------------------------------------------
    # Push
    # ---------------------------------------------------------------------
    if no_push:
        print("[step9] push: skipped (--no-push)")
        print("[step9] OK")
        return 0

    push_branch = _get_branch(coordinator_root)
    if not push_branch:
        print("WARN: no current branch; skipping push", file=sys.stderr)
        print("[step9] push: skipped (no branch)")
        print("[step9] OK")
        return 0

    push_result = subprocess.run(
        ["git", "-C", coordinator_root, "push", "origin", push_branch],
        capture_output=True, text=True,
    )
    push_output = (push_result.stdout or "") + (push_result.stderr or "")
    if push_output:
        sys.stdout.write(push_output)
        if not push_output.endswith("\n"):
            sys.stdout.write("\n")
    if push_result.returncode == 0:
        print("[step9] push: ok")
        print("[step9] OK")
        return 0

    # This repo's coordinator-auto-push hook fires on every commit on work/*
    # and feature/* branches and may already have pushed this exact HEAD --
    # racing step9's own explicit push for the ref lock and losing it looks
    # identical to a genuine push failure (same "! [remote rejected] ...
    # cannot lock ref" text) but is not one. Verify against the remote before
    # reporting a failure: only a HEAD that is genuinely absent from origin
    # after the hook has had its chance is a real problem.
    remote_has_head = _head_on_remote(coordinator_root, push_branch)
    if remote_has_head:
        print(
            f"[step9] local push reported exit {push_result.returncode} "
            "(likely lost the ref-lock race against the auto-push hook), but "
            "HEAD is confirmed present on origin -- not a failure",
            file=sys.stderr,
        )
        print("[step9] push: ok (verified via remote)")
        print("[step9] OK")
        return 0

    print(f"ERROR: push rejected (exit {push_result.returncode})", file=sys.stderr)
    print("[step9] push: rejected")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
