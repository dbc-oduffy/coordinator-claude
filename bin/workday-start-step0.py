"""workday-start-step0.py — deterministic Step 0 (Branch Setup) for /workday-start.

Encapsulates the precedence switch documented in pipelines/workday-start-internals.md
§ Step 0. Exists because the procedure was empirically EM-skippable when expressed as
inline bash in the skill body — concentrating the precedence logic in a single invokable
entrypoint removes EM judgment from a mechanical procedure.

Stdout: one-line status notice consumed by the briefing (RENAMED / IN-SPAN / FRESH-CUT /
NAMED-WORKSTREAM / STALE-NEEDS-ABC / SYNC-MAIN-ABORT / RENAME-PUSH-FAILED / CRASH),
followed by the reconcile leg's own line on the FRESH-CUT / NAMED-WORKSTREAM / RENAMED
paths. CRASH is emitted by two guards, covering the two places an unhandled exception
can propagate BEFORE any of the deliberate-refusal lines above got a chance to print:
a module-level try/except around the ``workday_ceremony_lib``/``cc_invoke`` imports
(near the top of this file — the ACTUAL 2026-08-12 incident, a ``ModuleNotFoundError``
raised at that import), and ``_main_with_crash_guard`` wrapping ``main()`` itself
(near the bottom, for anything unhandled inside the precedence switch). Without either,
a crash-before-first-line and a refusal-that-ran-and-found-nothing-to-do are
indistinguishable from the ceremony's side (state/bug-backlog/
2026-08-12-ceremony-cannot-distinguish-a-step-0-tha-2245f21fe6d0.yaml). Still exits 1,
same as every other unexpected-error path — nothing downstream keys off exit code to
tell a crash apart from a deliberate abort (see ``_main_with_crash_guard``'s own
docstring for the consumer-grep that established this).
Stderr: human-readable detail; on CRASH, the full traceback (never swallowed).

Exit codes:
  0 — step 0 succeeded; proceed to step 1.
  2 — stale-commit guard triggered; A/B/C Branch Reconciliation needed.
  3 — reconcile with origin/main hit a conflict; PM resolves first.
  1 — sync-main aborted, an unhandled exception (CRASH; see Stdout above), or other
      unexpected error.

Test seam (internal, not part of the ceremony contract):
  --self-heal-machine-slug      run only the Step 0.2a machine-slug self-heal/drift block.
  --self-heal-contributor-slug  run only the Step 0.2b contributor-slug self-heal/drift block.
  These exist so bin/tests/test-coordinator-daily-branch.sh (AC5/AC6; DoE 2fbe0e77,
  2026-07-19) can exercise the slug blocks in isolation now that they are Python,
  not an awk-extractable bash region.

Check 4 (midnight rename)'s remote-ref deletion is liveness-gated: deleting
`origin/<old>` removes the crash-insurance remote ref for any OTHER live session
sharing this worktree that has not yet pushed under the old name (this repo
routinely runs 4-5 concurrent EM sessions against ONE shared clone — see project
CLAUDE.md § Coordinator Operating Doctrine). The gate is
`coordinator_core.session.worktree_safety.history_rewrite_verdict` — the same
fail-closed peer-liveness predicate used elsewhere on this ceremony's
history-rewriting paths. An UNDETERMINABLE liveness read (the probe raises, or the
verdict itself comes back `"unknown"`) is treated exactly like a CONFIRMED live
peer (`"refused"`) — never collapsed to "no peers, safe to delete". Only a clean
`"ok"` verdict (provably zero live peers) permits the remote-delete refspec.

Port of: workday-start-step0.sh (DoE 091c0f3e, 2026-07-19). `today` is
natively imported from coordinator_core.daily_day.local_day (de-bash campaign,
2026-07-21 — Port of: coordinator-daily-day.sh, DoE c6d97219, 2026-07-22;
commands/workday-start.md's Step 0.45 span-assertion was repointed to the same
native peer in the same chunk).
session-ensure-branch is natively imported from
lib/session_ensure_branch.py (de-bash campaign, chunk E3-f — Port of:
session-ensure-branch.sh, DoE 9cc1d315, 2026-07-21). sync-main.py and
workday-start-step0-reconcile.py are invoked as subprocesses (separate
surfaces). cs_compute_machine / cs_compute_machine_live /
cs_compute_contributor_live / cs_parse_branch_span / cs_should_prompt_rename /
cs_rename_target are natively imported from coordinator_core.machine_resolver /
coordinator_core.daily_branch (de-bash campaign, unit "daily-branch" —
Port of: coordinator-daily-branch.sh, DoE 2fbe0e77, 2026-07-19).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Module-level crash guard — narrow, covers only the imports below (and their
# sys.path bootstrap) that can realistically fail at import time: a missing
# lib dir, a broken workday_ceremony_lib/cc_invoke, or (the 2026-08-12
# incident this closes) an unreachable coordinator_core transitively pulled
# in by them. Without this, such a failure propagates before
# `_main_with_crash_guard` (which wraps `main()`, further below) is ever
# reached — the exact "crash before any status line" failure mode
# state/bug-backlog/2026-08-12-ceremony-cannot-distinguish-a-step-0-tha-
# 2245f21fe6d0.yaml describes; a REAL 2026-08-12 incident on this exact
# import (ModuleNotFoundError: coordinator_core, since fixed in d2d4ec545)
# is what proved the class, not just the theory. Uses only stdlib
# (print/sys/traceback) already imported above — never depends on anything
# from the imports it is guarding, which may not exist in a half-imported
# module.
try:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "lib"))
    import workday_ceremony_lib as wc  # noqa: E402
    from cc_invoke import child_env, require_dispatch_engine_on_path  # noqa: E402
except Exception:
    import traceback
    print("CRASH")
    traceback.print_exc(file=sys.stderr)
    sys.exit(1)

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LIB_DIR = os.path.join(PLUGIN_ROOT, "lib")
sys.path.insert(0, _LIB_DIR)  # for session_ensure_branch (native import, chunk E3-f)
# STEP0_SYNC_MAIN override mirrors step3's STEP3_SYNC_MAIN seam (defaults to the real
# path — behavior is unchanged when unset; the override exists for hermetic testing).
_BIN_SYNC_MAIN = os.environ.get("STEP0_SYNC_MAIN") or os.path.join(PLUGIN_ROOT, "bin", "sync-main.py")
_BIN_RECONCILE = os.path.join(PLUGIN_ROOT, "bin", "workday-start-step0-reconcile.py")

_OVERRIDE_ENV_BASE = {
    "COORDINATOR_OVERRIDE_BRANCH": "1",
}


def _out(msg: str) -> None:
    print(msg)


def _err(msg: str) -> None:
    print(msg, file=sys.stderr)


# ---------------------------------------------------------------------------
# Native bridge — coordinator_core.daily_branch / coordinator_core.machine_resolver
# (replaces the retired coordinator-daily-branch.sh bash-lib bridge, DoE 2fbe0e77, 2026-07-19)
# ---------------------------------------------------------------------------

def _ensure_claude_klabauter_on_path() -> None:
    claude_klabauter_root = require_dispatch_engine_on_path()


# ---------------------------------------------------------------------------
# Step 0.2a / 0.2b — machine/contributor slug self-heal + drift detection
# ---------------------------------------------------------------------------

def _slug_self_heal(key: str, live_func, drift_label: str, machine_rename_option: bool) -> None:
    ml_bin = os.environ.get("MACHINE_LOCAL_BIN", "machine-local")
    resolved = shutil.which(ml_bin)
    if resolved is None:
        return
    has = subprocess.run([resolved, "has", key], capture_output=True, text=True)
    if has.returncode != 0:
        # Key absent — seed from live value (not from the env override).
        live = live_func()
        subprocess.run([resolved, "set", key, live], capture_output=True, text=True)
        return
    # Key present — compare persisted vs live; surface drift, do not pick.
    get = subprocess.run([resolved, "get", "--default", "", key], capture_output=True, text=True)
    persisted = get.stdout.strip() if get.returncode == 0 else ""
    live = live_func()
    if persisted and persisted != live:
        _err(f"{drift_label}: persisted='{persisted}', "
             + ("this session's hostname yields" if machine_rename_option else "git user.email yields")
             + f" '{live}'.")
        if machine_rename_option:
            _err("  Option 1 — stale session: this process has a stale hostname. "
                 "Keeping persisted value is correct; no action needed.")
            _err(f"  Option 2 — machine renamed: run 'machine-local set {key} {live}' "
                 "to update the registry.")
        else:
            _err("  Option 1 — keep persisted: this is the intentional slug; no action needed.")
            _err(f"  Option 2 — update: run 'machine-local set {key} {live}' to update the registry.")


def machine_slug_self_heal() -> None:
    _ensure_claude_klabauter_on_path()
    from coordinator_core.machine_resolver import compute_machine_live
    _slug_self_heal("coordinator.machine_slug", compute_machine_live,
                    "Machine-slug drift", machine_rename_option=True)


def contributor_slug_self_heal() -> None:
    _ensure_claude_klabauter_on_path()
    from coordinator_core.machine_resolver import compute_contributor_live
    _slug_self_heal("coordinator.contributor_slug", compute_contributor_live,
                    "Contributor-slug drift", machine_rename_option=False)


# ---------------------------------------------------------------------------
# Reconcile leg
# ---------------------------------------------------------------------------

def _exec_reconcile() -> int:
    _ensure_claude_klabauter_on_path()
    from coordinator_core.win_portability import no_console_creationflags

    result = subprocess.run(
        [sys.executable, _BIN_RECONCILE],
        **no_console_creationflags(),
        capture_output=True,
        text=True,
        env=child_env(),
    )
    # Relay captured stdio to this process's own stdout/stderr to preserve the
    # module docstring's contract (reconcile's own line on stdout on the
    # FRESH-CUT / NAMED-WORKSTREAM / RENAMED paths) — capture_output is needed
    # so a Windows silent-kill (inherited-stdio + CREATE_NO_WINDOW) is
    # diagnosable instead of a bare rc=1 with nothing printed.
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="" if result.stderr.endswith("\n") else "\n")
    return result.returncode


# ---------------------------------------------------------------------------
# Check 4 — session-meta branch carry (AC8-AC10)
# ---------------------------------------------------------------------------

def _session_meta_dirs() -> "list[str]":
    """Enumerate this tree's session-claim directories under the git common
    dir's ``coordinator-sessions/`` hub (``coordinator_core.session.core.
    sessions_dir``), skipping the hub's own non-session bookkeeping entries
    (``_NON_SESSION_DIR_NAMES`` — the same denylist ``live_session_ids``
    filters on). Deliberately unfiltered by liveness: a session that has
    already ended still has other readers of its ``meta.json:branch`` field
    (``pickup_assemble/holder_evidence.py``), so a stale/dead session's
    record needs the same old->new carry a live one does.

    Returns ``[]`` on any resolution failure (not a git repo, hub walk
    raised) — callers treat that as "no sessions to touch", not as an error
    to propagate; the rename itself must never depend on this succeeding.
    """
    from coordinator_core.session import core as session_core
    from coordinator_core.session import liveness as session_liveness

    try:
        base = session_core.sessions_dir()
    except Exception:
        return []
    if not base:
        return []
    basep = Path(base)
    if not basep.is_dir():
        return []
    dirs: list[str] = []
    try:
        for entry in basep.iterdir():
            if not entry.is_dir() or entry.name in session_liveness._NON_SESSION_DIR_NAMES:
                continue
            dirs.append(str(entry))
    except OSError:
        return dirs
    return dirs


def _rewrite_session_meta_branch(old: str, new: str) -> None:
    """Rewrites ``meta.json:branch`` from ``old`` to ``new`` for every session
    directory on this tree currently recording ``old`` (AC8). Keeps the
    session hub's branch bookkeeping in step with Check 4's
    ``git branch -m old new``, which renames the ONE local ref every
    concurrent session on this shared tree is sitting on (see module
    docstring / ``_rename_across_midnight``) — the rename site is the only
    place that knows the old->new mapping, so read-time resolution elsewhere
    cannot substitute for this.

    Best-effort and never fatal (AC9): an unwritable or corrupt meta is
    skipped with a stderr note rather than raising. A failed meta rewrite is
    strictly less bad than a failed rename, and by the time this runs the
    local rename has already happened.
    """
    from coordinator_core.session import core as session_core

    for sdir in _session_meta_dirs():
        try:
            recorded = session_core.read_meta_field(sdir, "branch")
        except Exception as exc:
            _err(f"WARN: could not read session meta branch at '{sdir}': {exc}")
            continue
        if recorded != old:
            continue
        try:
            wrote = session_core.update_meta_field(sdir, "branch", new)
        except Exception as exc:
            _err(f"WARN: could not rewrite session meta branch at '{sdir}' "
                 f"({old} -> {new}): {exc}")
            continue
        if not wrote:
            _err(f"WARN: session meta at '{sdir}' unwritable or corrupt; "
                 f"branch field left at '{old}' (expected rewrite to '{new}').")


def _handle_rename_push_failure(old: str, new: str, attempted_remote_delete: bool) -> int:
    """Push-failure handler for Check 4's rename push, called AFTER the local
    ``git branch -m old new`` has already happened.

    Purpose: a failed ``--atomic`` push is USUALLY clean (no ref update applied on
    the remote), but a genuine network partition/ack-loss can leave the server
    having applied the update while this process never saw the acknowledgement —
    in that edge case, blindly renaming the local branch back to ``old`` would be
    WRONG, because the remote would then disagree with local. This function
    re-queries the actual remote ref state via ``git ls-remote`` before deciding:
    local is only rolled back when the remote CONFIRMS ``old`` still exists and
    ``new`` does not (the clean-failure signature).

    Negative-spec:
        - Does NOT assume rollback is correct just because the push returned
          non-zero — that was the pre-existing bug (asymmetric rollback restored
          only the local name, on the unverified assumption that --atomic failure
          always means zero remote effect).
        - On an ambiguous remote read (ls-remote itself fails, or the observed
          remote refs don't match either the clean-failure or the
          already-applied signature), does NOT guess a rollback direction —
          fails loudly instead, leaves local as-is, and tells the operator
          exactly what was observed and how to reconcile by hand.
        - On the clean-rollback path, also reverses the session-meta
          ``branch`` rewrite ``_rename_across_midnight`` performed (AC10) — a
          local-only rollback with no meta reversal would leave live session
          directories recording the now-nonexistent ``new`` name.
    """
    ls = wc.git("ls-remote", "--heads", "origin", old, new)
    ls_lines = (ls.stdout or "").splitlines() if ls.returncode == 0 else []
    old_present = any(line.endswith(f"refs/heads/{old}") for line in ls_lines)
    new_present = any(line.endswith(f"refs/heads/{new}") for line in ls_lines)

    if ls.returncode == 0 and old_present and not new_present:
        # Clean failure — remote confirmed unchanged; safe to roll back locally.
        rollback_env = dict(os.environ)
        rollback_env.update(_OVERRIDE_ENV_BASE)
        rollback_env["COORDINATOR_OVERRIDE_BRANCH_REASON"] = "workday-start step 0 rename rollback"
        wc.git("branch", "-m", new, old, env=rollback_env)
        # AC10: reverse the forward meta rewrite too, or the rollback leaves
        # behind the stale `new` names it exists to undo.
        _rewrite_session_meta_branch(new, old)
        _out(f"RENAME-PUSH-FAILED old={old}")
        _err(f"Remote rename rejected; remote confirmed unchanged (origin/{old} present, "
             f"origin/{new} absent); local rolled back to '{old}'. Investigate remote "
             "ref-update hooks or permissions.")
        return 1

    # Remote state disagrees with the clean-failure signature (partial apply / ack
    # loss on the server side) or the ls-remote probe itself failed — do NOT guess a
    # rollback direction. Leave local as-is (still named `new`) and fail loudly.
    _out(f"RENAME-PUSH-FAILED-AMBIGUOUS old={old} new={new}")
    detail = (
        f"Remote push reported failure but remote state is AMBIGUOUS "
        f"(ls-remote rc={ls.returncode}, origin/{old} present={old_present}, "
        f"origin/{new} present={new_present}). Local branch was NOT rolled back — "
        f"it is still named '{new}'. Do NOT re-run step 0 blindly; manually run "
        f"`git ls-remote origin {old} {new}` and reconcile by hand"
    )
    if attempted_remote_delete:
        detail += f" (the atomic push also attempted to delete origin/{old})."
    else:
        detail += f" (this run did NOT attempt to delete origin/{old})."
    _err(detail)
    return 1


def _rename_across_midnight(old: str, new: str) -> int:
    """Step 0 Check 4 — rename the shared local branch across the midnight boundary
    and, liveness-permitting, mirror the rename on the remote.

    Purpose: ``git branch -m`` renames the ONE local branch ref every concurrent
    session sharing this worktree currently has checked out — that half is not
    further gated here (see module docstring). The REMOTE half is gated: deleting
    ``origin/<old>`` is skipped whenever
    ``coordinator_core.session.worktree_safety.history_rewrite_verdict`` does not
    return a clean ``"ok"`` (a confirmed peer, an undeterminable read, AND a raised
    exception all fail closed the same way — see module docstring). The skip is
    reported on stderr, never silent.

    Negative-spec:
        - An "unknown" verdict (probe exception, unresolvable liveness) is NEVER
          treated as "no peers" — see module docstring's liveness-gate note.
        - Push failure handling is delegated to ``_handle_rename_push_failure``,
          which re-verifies actual remote state rather than assuming the local
          rollback alone restores consistency.
        - Every session directory on this tree recording ``old`` as its
          ``meta.json:branch`` is rewritten to ``new`` right after the local
          rename succeeds (AC8) — best-effort, never fails the rename (AC9).
          Without this, ``_shared_branch_live_count`` in
          ``coordinator_core/hooks/auto_push.py`` string-compares that stale
          field and undercounts live peers on exactly the branch a rename
          just touched.
    """
    rename_env = dict(os.environ)
    rename_env.update(_OVERRIDE_ENV_BASE)
    rename_env["COORDINATOR_OVERRIDE_BRANCH_REASON"] = "workday-start step 0 rename across midnight"
    _rename = wc.git("branch", "-m", old, new, env=rename_env)
    sys.stderr.write((_rename.stdout or "") + (_rename.stderr or ""))
    sys.stderr.flush()

    if _rename.returncode == 0:
        # AC8: carry every session's meta.json:branch across the rename this
        # process just performed on the ONE shared local ref.
        _rewrite_session_meta_branch(old, new)

    from coordinator_core.session.worktree_safety import history_rewrite_verdict
    try:
        verdict = history_rewrite_verdict()
        verdict_outcome, verdict_reason = verdict.outcome, verdict.reason
    except Exception as exc:
        verdict_outcome, verdict_reason = "unknown", f"liveness probe raised: {exc}"

    delete_old_remote = verdict_outcome == "ok"

    push_env = dict(os.environ)
    push_env.update(_OVERRIDE_ENV_BASE)
    push_env["COORDINATOR_OVERRIDE_BRANCH_REASON"] = "workday-start step 0 atomic rename push"

    push_refspecs = [f"{new}:{new}"]
    if delete_old_remote:
        push_refspecs.append(f":{old}")
    else:
        _err(f"LIVENESS-GATE: leaving origin/{old} in place ({verdict_reason}); "
             f"pushing origin/{new} only — the old remote ref is orphaned, not deleted.")

    push = wc.git("push", "--atomic", "origin", *push_refspecs, env=push_env)
    sys.stderr.write((push.stdout or "") + (push.stderr or ""))
    sys.stderr.flush()
    if push.returncode != 0:
        return _handle_rename_push_failure(old, new, delete_old_remote)

    if not wc.git_ok("branch", f"--set-upstream-to=origin/{new}", new):
        _err(f"WARN: could not set upstream to origin/{new}; check remote tracking manually.")

    _out(f"RENAMED old={old} new={new}")
    return _exec_reconcile()


def main(argv: list[str]) -> int:
    # Test seams — run a single slug block and exit.
    if argv[:1] == ["--self-heal-machine-slug"]:
        machine_slug_self_heal()
        return 0
    if argv[:1] == ["--self-heal-contributor-slug"]:
        contributor_slug_self_heal()
        return 0

    # Native-module availability guard (daily_branch, machine_resolver, daily_day all
    # resolve via the same engine-root ladder).
    try:
        _ensure_claude_klabauter_on_path()
    except RuntimeError as exc:
        _err(f"ERROR: daily-branch native module unreachable — engine-root resolution failed: {exc}")
        return 1
    from coordinator_core.daily_branch import parse_branch_span, rename_target, should_prompt_rename
    from coordinator_core.daily_day import local_day
    from coordinator_core.machine_resolver import compute_machine
    from coordinator_core.win_portability import no_console_creationflags, run_forwarding

    # Step 0.1 — Sync main
    # run_forwarding, not subprocess.run: this directive is reachable
    # in-process through coordinator_core.workday_complete.apply's
    # capture-buffer dispatch, where sys.stderr is an io.StringIO with no
    # fileno() — see run_forwarding's own docstring.
    sm = run_forwarding(
        [sys.executable, _BIN_SYNC_MAIN], stdout=sys.stderr, stderr=sys.stderr,
        env=child_env(),
        **no_console_creationflags(),
    )
    if sm.returncode != 0:
        _out("SYNC-MAIN-ABORT")
        return 1

    # Step 0.2 — Determine machine and today
    machine = compute_machine()
    today = local_day()
    current = wc.git_out("branch", "--show-current")

    # Step 0.2a / 0.2b — slug self-heal + drift
    machine_slug_self_heal()
    contributor_slug_self_heal()

    # Step 0.3 — Precedence switch

    # Check 1 — Stale-commit guard
    last_epoch_s = wc.git_out("log", "-1", "--format=%ct") or "0"
    try:
        last_epoch = int(last_epoch_s)
    except ValueError:
        last_epoch = 0
    now_epoch = int(time.time())
    age_days = (now_epoch - last_epoch) // 86400
    if age_days > 2 and current.startswith("work/"):
        _out(f"STALE-NEEDS-ABC branch={current} age_days={age_days}")
        _err(f"Stale-commit guard: {current} last commit {age_days} days ago. "
             "Surface A/B/C Branch Reconciliation Decision.")
        return 2

    # Check 2 — Already in span
    rename_needed = should_prompt_rename(current, today, float(last_epoch))
    if not rename_needed and parse_branch_span(current) is not None:
        _out(f"IN-SPAN branch={current}")
        return 0

    # Check 3 — On main / detached / empty branch
    head_detached = "no" if wc.git_ok("symbolic-ref", "-q", "HEAD") else "yes"
    commits_ahead = "0"
    if current and current != "main":
        commits_ahead = wc.git_out("rev-list", "--count", "origin/main..HEAD") or "0"

    from session_ensure_branch import SuffixCollisionError, session_ensure_branch

    try:
        ensure = session_ensure_branch(
            machine, today, current, head_detached, commits_ahead,
            env=dict(os.environ), stderr=sys.stderr,
        )
    except SuffixCollisionError as exc:
        _err(f"ERROR: {exc}")
        return 1
    if ensure.result in ("FRESH-CUT", "ADOPTED-EXISTING", "INHERITED"):
        # ADOPTED-EXISTING (today's branch already existed and HEAD was at its
        # tip) and INHERITED (another session won the cut lock) are the same
        # settled-on-a-day-branch terminal as FRESH-CUT: the invariant HOLDS.
        # They are deliberately NOT folded into REFUSED-LIVE-PEERS, which
        # reports the opposite state -- see session_ensure_branch's negative
        # spec on the result vocabulary.
        return _exec_reconcile()
    if ensure.result == "REFUSED-LIVE-PEERS":
        # Settled-on-this-branch terminal, same shape as FRESH-CUT and
        # NAMED-WORKSTREAM: the cut was declined because it would switch the
        # shared checkout under live peers, so the tree stays where it is and
        # we reconcile it rather than falling through to Check 3.5/4, whose
        # span parse cannot succeed on `main` and would exit 1 on a
        # non-EM-skippable step. session_ensure_branch has already printed the
        # peer detail; this line names the day-level consequence.
        _err("LIVENESS-GATE: staying on "
             f"{current or '<detached>'} — no day branch was cut. "
             "Branch discipline is NOT in force for this session.")
        return _exec_reconcile()

    # Check 3.5 — Named long-lived workstream
    parseable = parse_branch_span(current) is not None
    try:
        commits_ahead_int = int(commits_ahead)
    except ValueError:
        commits_ahead_int = 0
    if not parseable and commits_ahead_int > 0:
        _out(f"NAMED-WORKSTREAM branch={current}")
        return _exec_reconcile()

    # Check 4 — Midnight rename
    old = current
    span = parse_branch_span(old)
    if span is None:
        _err(f"ERROR: Check 4 reached with unparseable branch '{old}' — "
             "precedence switch fell through unexpectedly")
        return 1
    start_date = span[0]
    if not start_date:
        _err(f"ERROR: cs_parse_branch_span returned empty start_date for branch '{old}'")
        return 1

    new = rename_target(machine, start_date, today, commits_ahead)

    # Concurrent-rename race guard.
    current_recheck = wc.git_out("branch", "--show-current")
    today_dd = today.rsplit("-", 1)[-1]
    if current_recheck.endswith(f"to{today_dd}") or current_recheck.endswith(f"/{today}"):
        _out(f"IN-SPAN branch={current_recheck} note=concurrent-rename")
        return 0

    # Collision guard.
    if new != old and wc.git_ok("show-ref", "--verify", "--quiet", f"refs/heads/{new}"):
        n = 2
        while wc.git_ok("show-ref", "--verify", "--quiet", f"refs/heads/{new}-{n}"):
            n += 1
            if n > 9:
                _err(f"ERROR: cannot find unused rename target for '{new}' (tried -2 through -9)")
                return 1
        new = f"{new}-{n}"

    return _rename_across_midnight(old, new)


def _main_with_crash_guard(argv: list[str]) -> int:
    """Top-level guard around ``main()`` — makes an unhandled exception
    distinguishable from a deliberate refusal on the stdout status-line
    contract the ceremony already consumes (module docstring's Stdout
    block).

    Without this, ``main()`` had no top-level exception handler and was
    invoked bare as ``sys.exit(main(argv))``: a crash BEFORE any status
    line printed exited 1 with nothing on stdout — identical, from
    /workday-start's side, to a step that ran and legitimately found
    nothing to do. Filed as state/bug-backlog/2026-08-12-ceremony-cannot-
    distinguish-a-step-0-tha-2245f21fe6d0.yaml.

    Reuses exit code 1 rather than minting a new one: grepping
    ``coordinator/commands/workday-start.md`` (DoE-claude) shows the
    consumer already treats exit 1 as "unexpected error -> halt"
    unconditionally of WHICH unexpected error — nothing downstream
    branches on 1 vs. a hypothetical distinct crash code, so a new code
    would add a contract surface with no reader. The CRASH stdout line is
    the only new signal needed; the traceback goes to stderr exactly as
    it would have with no guard at all (``BaseException`` — SystemExit,
    KeyboardInterrupt — is deliberately NOT caught here, so ``sys.exit()``
    and Ctrl-C keep their normal behavior).
    """
    try:
        return main(argv)
    except Exception:
        import traceback
        _out("CRASH")
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(_main_with_crash_guard(sys.argv[1:]))
