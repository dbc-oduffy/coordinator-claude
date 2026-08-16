"""lib/session_ensure_branch.py — shared gate: cut work/{machine}/{today} when the
session opens on main, detached HEAD, or a zero-ahead non-span branch.

Native port of the retired bash gate (de-bash campaign, chunk E3-f). The
bash oracle's own `cs_parse_branch_span` was already a bridge shelling out to
`coordinator_core.daily_branch.parse_branch_span`; this port imports that
function directly instead — a straight Python import, not a subprocess spawn.

Source this module and call `session_ensure_branch`, or run the git-mutating
branch-cut logic ad hoc — this is an importable library, not a bin/ trampoline
(mirrors lib/release_currency.py — no .cmd launcher).

Spec backlink: state/handoffs/2026-07-04_220004_roadmap-strang-04.md § Phase 1
Port: docs/plans/2026-07-19-debash-coordinator-windows.md (chunk E3-f)

Soft seam — claude-klabauter action layer: a future `session.ensure_branch` op
(pcore-06/10) may eventually own the git-mutation half of this gate; until
that op exists, this module performs the git checkout/push subprocess calls
directly (matching the bash oracle's behavior — the bash oracle was never
gated on that future op either, it always did the git ops itself).
"""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from typing import Optional

# ---------------------------------------------------------------------------
# COORDINATOR_OVERRIDE_BRANCH pattern: every git mutation carries this env pair
# so the off-daily-branch PreToolUse guard does not deny it. Do NOT remove —
# the guard denies git checkout/push on non-daily branches without it.
# ---------------------------------------------------------------------------
_OVERRIDE_ENV = {
    "COORDINATOR_OVERRIDE_BRANCH": "1",
    "COORDINATOR_OVERRIDE_BRANCH_REASON": "session-ensure-branch: create/push workstream branch",
}


class SuffixCollisionError(RuntimeError):
    """Raised when no unused work/{machine}/{today}[-N] suffix is found (tried -2..-9)."""


@dataclass
class EnsureResult:
    result: str  # "FRESH-CUT", "REFUSED-LIVE-PEERS", or "" (no-op)
    new_branch: str  # branch name when FRESH-CUT; "" otherwise


def _branch_ref_exists(name: str) -> bool:
    proc = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{name}"],
        capture_output=True,
    )
    return proc.returncode == 0


def _branch_mutation_verdict():
    """Import indirection mirroring `_parses_as_branch_span` — native
    import, no subprocess spawn. Isolated so a missing/broken
    coordinator_core install degrades loudly via ImportError at call time
    rather than silently at module load."""
    from coordinator_core.session.worktree_safety import branch_mutation_verdict

    return branch_mutation_verdict


def _parses_as_branch_span(name: str) -> bool:
    """cs_parse_branch_span drop-in — native import, no subprocess spawn."""
    try:
        from coordinator_core.daily_branch import parse_branch_span
    except ImportError:
        return False
    try:
        return parse_branch_span(name) is not None
    except Exception:
        return False


def session_ensure_branch(
    machine: str,
    today: str,
    current: str,
    head_detached: str,
    commits_ahead,
    env: Optional[dict] = None,
    stderr=None,
) -> EnsureResult:
    """Gate: on main, detached HEAD, or zero-ahead non-span branch → cut
    work/{machine}/{today} (collision-safe suffix loop), push it, return
    EnsureResult("FRESH-CUT", branch). Silent no-op (EnsureResult("", "")) when
    the gate condition is not met.

    Before cutting, consults
    coordinator_core.session.worktree_safety.branch_mutation_verdict — a
    branch is a property of the shared TREE, not of a session, so cutting
    one switches every live peer session's checkout out from under it. A
    non-"ok" verdict (both "refused" and "unknown" — the latter is FAIL
    CLOSED per that module's contract and MUST be treated the same as
    "refused") aborts the cut without touching git, prints
    "REFUSED-LIVE-PEERS branch=... reason=..." naming the peer detail, and
    returns EnsureResult("REFUSED-LIVE-PEERS", ""). This value is
    deliberately distinguishable from both "" (nothing-to-do) and
    "FRESH-CUT" (cut succeeded) — callers must not conflate it with either.

    Parameters mirror the bash oracle's positional contract:
      machine       — coordinator machine slug (from cs_compute_machine)
      today         — today's date YYYY-MM-DD (local day)
      current       — current branch name (git branch --show-current)
      head_detached — "yes" if HEAD is detached, "no" otherwise
      commits_ahead — commits ahead of origin/main (0 when on main or detached);
                       accepts int or str.

    Raises SuffixCollisionError when work/{machine}/{today}-2..-9 are all taken.

    Ceremony/oracle incoherence on -N collision suffixes (deliberate, not a
    bug): the -N branches this function mints are NOT accepted by
    daily_branch.is_canonical_branch (or parse_branch_span) — collision names
    are structurally non-canonical and stay that way. This is not a bug on
    either side: branch creation here runs via in-process subprocess.run with
    argv lists, never through the PreToolUse Bash seam, so the branch-
    creation deny guard structurally cannot see or reject a -N suffix —
    verified against HEAD, all nine ceremony-side creation/rename sites in
    the repo are in-process with no shell-visible path. Because the guard
    never judges these names, the oracle is not required to accept a shape
    it never has to judge at that seam. Widening parse_branch_span to accept
    -N was evaluated and rejected: it has four live tool-time callers
    (workday-start-step0.py Checks 2/3.5/4, workday-start-day-branch-
    resolve.py's _span_assert, workday-complete-step3-consolidate.py's
    _parse_branch_span, and this module's _parses_as_branch_span), and
    widening would move Step 0's Check 3.5 named-workstream precedence
    boundary for -N branches — a real ceremony-path behavior change with no
    guard-side benefit. See coordinator_core/daily_branch.py's module
    docstring for the full record.
    """
    err = stderr if stderr is not None else sys.stderr
    try:
        commits_ahead_int = int(commits_ahead)
    except (TypeError, ValueError):
        commits_ahead_int = 0

    is_main = current == "main"
    is_detached = head_detached == "yes"
    is_zero_ahead_non_span = (
        bool(current)
        and current != "main"
        and commits_ahead_int == 0
        and not _parses_as_branch_span(current)
    )

    if not (is_main or is_detached or is_zero_ahead_non_span):
        return EnsureResult(result="", new_branch="")

    branch_mutation_verdict = _branch_mutation_verdict()
    verdict = branch_mutation_verdict()
    if verdict.outcome != "ok":
        print(
            f"REFUSED-LIVE-PEERS branch=work/{machine}/{today} reason={verdict.reason}",
            file=err,
        )
        return EnsureResult(result="REFUSED-LIVE-PEERS", new_branch="")

    new_branch = f"work/{machine}/{today}"

    if _branch_ref_exists(new_branch):
        n = 2
        while _branch_ref_exists(f"{new_branch}-{n}"):
            n += 1
            if n > 9:
                raise SuffixCollisionError(
                    "cannot find unused workstream branch suffix (tried -2 through -9)"
                )
        new_branch = f"{new_branch}-{n}"

    checkout_env = dict(env) if env is not None else None
    if checkout_env is not None:
        checkout_env.update(_OVERRIDE_ENV)

    # run_forwarding, not subprocess.run: `err` may be workday-start-step0's
    # own `sys.stderr`, which is an io.StringIO with no fileno() when this
    # gate runs in-process through coordinator_core.workday_complete.apply's
    # capture-buffer dispatch — see coordinator_core.win_portability.
    # run_forwarding's own docstring.
    from coordinator_core.win_portability import no_console_creationflags, run_forwarding

    run_forwarding(
        ["git", "checkout", "-b", new_branch],
        env=checkout_env,
        stdout=err,
        stderr=err,
        check=True,
        **no_console_creationflags(),
    )

    push = subprocess.run(
        ["git", "push", "-u", "origin", new_branch],
        env=checkout_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        **no_console_creationflags(),
    )
    if push.returncode != 0:
        print("WARN: push of new branch failed — crash-insurance push not established", file=err)
        if push.stdout:
            err.write(push.stdout.decode("utf-8", errors="replace"))

    print(f"FRESH-CUT branch={new_branch}")
    return EnsureResult(result="FRESH-CUT", new_branch=new_branch)
