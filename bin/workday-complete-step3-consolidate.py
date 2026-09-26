from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BIN_SYNC_MAIN = os.environ.get("STEP3_SYNC_MAIN") or os.path.join(PLUGIN_ROOT, "bin", "sync-main.py")
_BIN_CURRENT_BRANCH = os.path.join(PLUGIN_ROOT, "bin", "coordinator-current-branch.py")


_BOOTSTRAP_DONE = False


def _bootstrap_engine() -> None:
    """Put `coordinator/bin/lib` on `sys.path` -- idempotent, safe to call
    more than once.

    Locate the shared module via realpath (always the true bin/lib, survives
    symlinked invocation) -- PLUGIN_ROOT above stays computed from the
    non-resolved `__file__` so the lib-discovery path is fakeable by a
    symlinked entrypoint (test9 relies on this to force exit 5).

    What moved and what did not: this mutation used to run at MODULE scope,
    which made every import of this file mutate the `sys.path` of a warm
    server ~50 sessions share. Only the trigger moved; the value inserted is
    byte-for-byte the same.
    """
    global _BOOTSTRAP_DONE
    if _BOOTSTRAP_DONE:
        return
    lib_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), "lib")
    if lib_dir not in sys.path:
        sys.path.insert(0, lib_dir)
    _BOOTSTRAP_DONE = True


def __getattr__(name: str):
    if name == "wc":
        _bootstrap_engine()
        import workday_ceremony_lib

        return workday_ceremony_lib
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


_HELP = """Usage: workday-complete-step3-consolidate.py [--no-push] [--dry-run]

  --no-push   Perform local consolidation; skip push step.
  --dry-run   Print what would happen; perform no git mutations.

Exit codes: 0=ok 1=sync-main-abort 2=merge-conflict 3=reconcile-conflict
            4=push-rejected-twice 5=lib-missing"""


def _out(msg: str) -> None:
    print(msg)


def _err(msg: str) -> None:
    print(msg, file=sys.stderr)


def _git_stream(*args: str) -> int:
    _bootstrap_engine()
    import workday_ceremony_lib as wc

    proc = wc.git(*args)
    if proc.stdout:
        sys.stderr.write(proc.stdout)
    if proc.stderr:
        sys.stderr.write(proc.stderr)
    sys.stderr.flush()
    return proc.returncode


def _compute_machine() -> str:
    _bootstrap_engine()
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.machine_resolver import compute_machine
    return compute_machine()


def _parse_branch_span(branch: str) -> str | None:
    _bootstrap_engine()
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.daily_branch import parse_branch_span
    span = parse_branch_span(branch)
    if span is None:
        return None
    return f"{span[0]} {span[1]}"


def _branch_covers_today(branch: str, today: str) -> bool:
    span = _parse_branch_span(branch)
    if span is None:
        return False
    parts = span.split()
    start_date = parts[0]
    end_date = parts[-1]
    return not (today < start_date) and not (end_date < today)


def _matching_work_branches(list_args: list[str], machine: str) -> list[str]:
    _bootstrap_engine()
    import workday_ceremony_lib as wc

    proc = wc.git(*(["branch"] + list_args))
    if proc.returncode != 0:
        return []
    prefix_re = re.compile(r'^\*? *work/' + re.escape(machine) + r'/', re.IGNORECASE)
    names = []
    for raw in proc.stdout.splitlines():
        if not prefix_re.match(raw):
            continue
        name = raw.strip().lstrip('*').strip()
        if name:
            names.append(name)
    return names


def main(argv: list[str]) -> int:
    _bootstrap_engine()
    import workday_ceremony_lib as wc
    from cc_invoke import require_dispatch_engine_on_path, child_env

    no_push = False
    dry_run = False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--no-push":
            no_push = True
        elif a == "--dry-run":
            dry_run = True
        elif a in ("--help", "-h"):
            print(_HELP)
            return 0
        else:
            _err(f"[step3] ERROR: unknown argument: {a}")
            return 1
        i += 1

    try:
        claude_klabauter_root = require_dispatch_engine_on_path()
        from coordinator_core.daily_day import local_day
    except RuntimeError as exc:
        _err(f"[step3] ERROR: lib not found — engine-root resolution failed: {exc}")
        return 5

    from coordinator_core.win_portability import no_console_creationflags, run_forwarding

    if dry_run:
        _err("[step3] DRY-RUN: would run sync-main.py")
        _out("[step3] sync-main: ok")
    else:
        sm = run_forwarding(
            [sys.executable, _BIN_SYNC_MAIN], stdout=sys.stderr, stderr=sys.stderr,
            env=child_env(),
            **no_console_creationflags(),
        )
        if sm.returncode != 0:
            _err("[step3] sync-main: FAILED")
            return 1
        _out("[step3] sync-main: ok")

    machine = _compute_machine()
    today = local_day()
    _out(f"[step3] machine: {machine}")
    _out(f"[step3] today: {today}")

    current_branch = ""
    if os.path.isfile(_BIN_CURRENT_BRANCH):
        try:
            cb = subprocess.run(
                [sys.executable, _BIN_CURRENT_BRANCH], capture_output=True, text=True,
                timeout=15, env=child_env(), **no_console_creationflags(),
            )
            current_branch = cb.stdout.strip() if cb.returncode == 0 else ""
        except (OSError, subprocess.TimeoutExpired):
            current_branch = ""
    if not current_branch:
        current_branch = wc.git_out("branch", "--show-current")

    if not current_branch:
        _err("[step3] ERROR: cannot determine current branch (detached HEAD?)")
        return 1
    if current_branch in ("main", "master"):
        _err(f"[step3] ERROR: current branch is '{current_branch}' — Step 3 must run on a workstream branch")
        return 1

    from coordinator_core.session.worktree_safety import history_rewrite_verdict

    def _resolve_rewrite_verdict():
        verdict = history_rewrite_verdict()
        if verdict.outcome != "ok":
            _out(f"[step3] REFUSED-HISTORY-REWRITE: {verdict.reason}")
        return verdict, verdict.outcome == "ok"

    rewrite_verdict, rewrite_ok = _resolve_rewrite_verdict()

    sibling_branches = []
    for name in _matching_work_branches(["--list"], machine):
        if name == current_branch:
            continue
        if not _branch_covers_today(name, today):
            continue
        sibling_branches.append(name)
    siblings_display = ",".join(sibling_branches) if sibling_branches else "none"
    _out(f"[step3] siblings discovered: {siblings_display}")

    merged_count = 0
    for sibling in sibling_branches:
        if dry_run:
            _err(f"[step3] DRY-RUN: would merge {sibling}")
            merged_count += 1
            continue
        _err(f"[step3] merging sibling: {sibling}")
        if _git_stream("merge", "--no-edit", sibling) != 0:
            _err(f"[step3] CONFLICT merging sibling branch: {sibling}")
            _err("[step3] Aborting merge. Resolve conflicts, then re-run.")
            _git_stream("merge", "--abort")
            return 2
        merged_count += 1
    _out(f"[step3] siblings merged: {merged_count}")

    reconcile_status = "no-op (origin/main missing)"
    if dry_run:
        _err("[step3] DRY-RUN: would reconcile with origin/main")
        reconcile_status = "no-op (dry-run)"
    elif not wc.git_ok("rev-parse", "--verify", "origin/main"):
        _err("[step3] origin/main not present locally — skipping reconcile")
        reconcile_status = "no-op (origin/main missing)"
    else:
        behind = wc.git_out("rev-list", "--count", "HEAD..origin/main") or "0"
        if behind == "0":
            ahead = wc.git_out("rev-list", "--count", "origin/main..HEAD") or "0"
            if ahead == "0":
                _err("[step3] branch is at origin/main — no rebase needed")
                reconcile_status = "no-op (at origin/main)"
            else:
                _err("[step3] branch already contains origin/main — no rebase needed")
                reconcile_status = "no-op (ahead-only)"
        else:
            rewrite_verdict, rewrite_ok = _resolve_rewrite_verdict()
            if not rewrite_ok:
                _err(
                    f"[step3] {behind} commit(s) behind origin/main — history rewrite refused "
                    f"({rewrite_verdict.reason}); attempting fast-forward-only merge instead of rebase..."
                )
                if _git_stream("merge", "--ff-only", "origin/main") == 0:
                    reconcile_status = f"fast-forward (rewrite refused: {rewrite_verdict.reason})"
                else:
                    _err("[step3] fast-forward-only merge not possible — leaving branch unreconciled")
                    reconcile_status = f"refused ({rewrite_verdict.reason}) — branch left unreconciled"
            else:
                _err(f"[step3] {behind} commit(s) behind origin/main — rebasing...")
                if _git_stream("rebase", "origin/main") == 0:
                    reconcile_status = "rebased"
                else:
                    _err("[step3] rebase had conflicts; falling back to merge...")
                    _git_stream("rebase", "--abort")
                    if _git_stream("merge", "origin/main") == 0:
                        reconcile_status = "merged (fallback)"
                    else:
                        _err("[step3] CONFLICT reconciling with origin/main")
                        _git_stream("merge", "--abort")
                        return 3
    _out(f"[step3] reconcile: {reconcile_status}")

    push_summary = ""
    if no_push:
        push_summary = "skipped (--no-push)"
    elif dry_run:
        rewrite_verdict, rewrite_ok = _resolve_rewrite_verdict()
        if rewrite_ok:
            _err(
                f"[step3] DRY-RUN: would push origin/{current_branch} "
                "with --force-with-lease (reconcile rewrote history)"
            )
        else:
            _err(
                f"[step3] DRY-RUN: would push origin/{current_branch} "
                f"via push_outstanding() (rewrite refused: {rewrite_verdict.reason})"
            )
        push_summary = "skipped (--dry-run)"
    else:
        rewrite_verdict, rewrite_ok = _resolve_rewrite_verdict()
        if rewrite_ok:
            _err(
                f"[step3] reconcile rewrote history -- pushing to "
                f"origin/{current_branch} with --force-with-lease"
            )
            if _git_stream("push", "--force-with-lease", "origin", current_branch) != 0:
                _err(
                    "[step3] force-with-lease push failed -- the remote moved since the "
                    "last fetch, or the push was refused. PM must resolve before continuing."
                )
                return 4
            push_summary = "ok (force-with-lease, after history rewrite)"
        else:
            _err(f"[step3] pushing to origin/{current_branch} via push_outstanding()...")
            from coordinator_core.ops.push_outstanding import push_outstanding

            outcome = push_outstanding(Path(os.getcwd()))
            for note in (
                list(outcome.skipped) + list(outcome.failed) + list(outcome.unconfirmed)
            ):
                _err(f"[step3] push_outstanding: {note}")

            if outcome.failed or outcome.unconfirmed:
                _err(
                    "[step3] push failed via push_outstanding(). "
                    "PM must resolve before continuing."
                )
                return 4
            if "push:nothing-outstanding" in outcome.skipped:
                push_summary = "ok (nothing outstanding)"
            elif "push" in outcome.acted:
                push_summary = "ok"
            elif "push:no-remote" in outcome.skipped:
                push_summary = "ok (no-remote)"
            elif (
                "push:branch-policy" in outcome.skipped
                or "push:branch-unresolvable" in outcome.skipped
            ):
                push_summary = "ok (declined by branch policy)"
            else:
                push_summary = "ok"
    _out(f"[step3] push: {push_summary}")

    deleted_count = 0
    if dry_run:
        _err("[step3] DRY-RUN: would delete merged sibling branches")
    else:
        for name in _matching_work_branches(["--merged"], machine):
            if name == current_branch:
                continue
            if not _branch_covers_today(name, today):
                continue
            _err(f"[step3] deleting merged sibling: {name}")
            if _git_stream("branch", "-d", name) == 0:
                deleted_count += 1
            else:
                _err(f"[step3] WARN: could not delete {name} — may not be fully merged")
    _out(f"[step3] siblings deleted: {deleted_count}")

    _out("[step3] OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
