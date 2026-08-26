"""SessionStart guard — assert the day-branch as a property of the TREE.

Chunk C4a of `docs/plans/2026-08-18-enforce-day-branch-cut-tree-invariant.md`.
This file is the SessionStart entrypoint and nothing else: the git logic is
engine-plane and lives in the engine tree's
`coordinator_core/hooks/day_branch_assert.py` (chunk C4b), which this shim
imports and calls.

Why the split: `sessionstart-dispatch.py` loads guards BY FILENAME from its own
directory via a `StartGuard(module_key, filename, sources)` tuple in `REGISTRY`,
so an engine-resident module is structurally unreachable from that loader. The
hosting and firing-set decision is doctrine-plane; the git logic is
engine-plane. Same stub shape as `sessionstart-bin-drift-refresh.py`.

Authorising ruling (PM, 2026-08-18): "we cut automatically if we're on main. we
warn if we are on a branch that is not compliant with our auto-push rules."
Case (A), on `main`, cuts with no ask and no EM judgment; case (B), a
non-compliant non-`main` branch, warns. `coordinator/docs/wiki/coordinator-tripwires/
day-branch-auto-cut-supersedes-pm-gate.md` records that this is a ratified
narrowing, not a regression to be "fixed" back to the PM-gated ask.

    Negative-spec — `sources` is `frozenset({"startup"})` and MUST NOT be
    widened. The fan-in's hooks.json matcher is
    `startup|resume|clear|compact|fork`, and per-guard `sources` is the ONLY
    narrowing mechanism (`sessionstart-dispatch.py`'s `ctx.source and not
    any(...)` gate). Three of those five values — `compact`, `resume`, `fork` —
    fire in a session that is ALREADY MID-EXECUTION, and a cut on `compact` is
    exactly the mid-execution mutation `docs/wiki/daily-branch-discipline.md`
    keeps out of bounds: a peer's next commit would land on a branch it never
    chose. The PM ruling authorises the on-`main` case at session BOOT only,
    never a ref move triggered by a mid-session compaction.
    `test_sessionstart_day_branch_assert_registered.py` turns red on a widening.

    Consequence, stated rather than hidden: a session that only ever compacts
    and never sees a fresh `startup` does not assert the invariant for itself.
    That is acceptable — it was asserted at its own startup, and the invariant
    is tree-level, not session-level.

    Negative-spec — this shim does not re-render, re-word, or suppress the
    engine's message. C4b returns the operator-facing line already rendered by
    C5's single banner mechanism; a second renderer printing
    similar-but-different text is the failure mode that mechanism exists to
    prevent.

Fails open, always: a session must never fail to start because the branch
assert could not run. Every failure path returns 0 with no output.
"""

import os
import sys
from pathlib import Path

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)


_PENDING_RECORD_NAME = "coordinator-auto-push-pending.json"
_REF_PREFIX = "ref: refs/heads/"


def _certainly_compliant(repo_root) -> bool:
    """True only when `assert_day_branch()` would certainly return COMPLIANT.

    The boot-cost pre-gate. `assert_day_branch()` costs 4149ms cold / ~1100ms
    warm and emits NOTHING on the compliant path -- 96% of the whole sync
    SessionStart fan-in -- because reaching its silent return first imports
    `coordinator_core` (193ms), computes `compute_machine()` (317ms, used ONLY
    by the on-`main` cut arm) and spawns `git branch --show-current` (446ms).
    Every one of those is wasted on the branch shape almost every session has.

    Mirrors `coordinator_core/hooks/day_branch_assert.case_b_verdict`'s
    compliance definition exactly: a `work/*` branch with no pending-push
    record. Reads `.git/HEAD` as a file rather than spawning git.

        Negative-spec -- this function is a FAST PATH, never an authority. It
        may only ever return True; every uncertainty returns False and falls
        through to the engine, which remains the single source of the verdict.
        Do not grow it into a second implementation of the warn arms: a
        detached HEAD, a non-`work/*` branch, a long-lived shape, a pending
        record, a worktree/submodule `.git` file, an unreadable HEAD, a
        `GIT_DIR`/`GIT_COMMON_DIR` override (which the engine's git subprocess
        honours and this file read would not, so the two could disagree about
        WHICH repo they are answering for) and any exception at all are ALL
        False here, precisely so the engine keeps
        rendering every operator-facing message through its one banner
        mechanism. A False that should have been True costs latency; a True
        that should have been False silently suppresses a warning the operator
        needed. Those are not symmetric -- when in doubt, return False.
    """
    try:
        if os.environ.get("GIT_DIR") or os.environ.get("GIT_COMMON_DIR"):
            return False

        git_dir = Path(repo_root) / ".git"
        if not git_dir.is_dir():
            return False

        head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
        if not head.startswith(_REF_PREFIX):
            return False

        branch = head[len(_REF_PREFIX):].strip()
        if not branch.startswith("work/"):
            return False

        return not (git_dir / _PENDING_RECORD_NAME).exists()
    except Exception:
        return False


def main() -> int:
    try:
        from _engine_root import _session_repo_root, resolve_claude_klabauter_root
    except Exception:
        return 0

    # ORDER IS LOAD-BEARING, not stylistic: the pre-gate runs BEFORE
    # `resolve_claude_klabauter_root()`, because the compliant path -- the overwhelmingly
    # common one -- never imports `coordinator_core` and so never needs the
    # engine root at all. Resolving it first spent ~0.87ms per session on an
    # answer the early return then discarded. `_session_repo_root()` genuinely
    # is needed first: it is what the pre-gate reads, and it is pure-Python
    # (env var plus an upward walk for `.git`) with no dependency on the engine
    # being importable or on sys.path having been extended.
    try:
        repo_root = _session_repo_root()
    except Exception:
        return 0
    if repo_root is None:
        return 0

    if _certainly_compliant(repo_root):
        return 0

    try:
        root = resolve_claude_klabauter_root()
    except Exception:
        return 0
    if not root:
        return 0  # engine unresolvable on this machine

    if root not in sys.path:
        sys.path.insert(0, root)

    try:
        from coordinator_core.hooks.day_branch_assert import assert_day_branch
        from coordinator_core.machine_resolver import compute_machine
        from coordinator_core.daily_day import local_day
    except Exception as exc:
        # Two failures reach here and they are NOT the same, so they must not
        # degrade to the same silence — that identical-silence collapse is the
        # GUARD-WIRING-SILENT-SKIP shape this whole workstream exists to close,
        # and it would otherwise survive inside its own fix.
        #   - No engine at all on this machine: expected, already returned above.
        #   - Engine RESOLVED but an import failed: the invariant is silently
        #     not in force, and nothing else would ever say so.
        # The breadcrumb reports the failure it OBSERVED and does not diagnose
        # a cause. Three imports sit under this one `except`, and a module can
        # fail to import for reasons other than absence (a broken import inside
        # it, a syntax error, a missing dependency of its own). Naming one
        # module and asserting "a publish is pending" would misdirect a reader
        # toward waiting when the engine is broken and needs fixing now.
        # Breadcrumb only, never a failure: exit stays 0. Same shape as
        # `sessionstart-dispatch.py`'s `_UNMATCHED_SOURCE_BREADCRUMB`.
        try:
            sys.stderr.write(
                f"[day-branch-assert] engine at {root}: import failed "
                f"({type(exc).__name__}: {exc}) -- the day-branch invariant is "
                "NOT being asserted this boot. Either the engine lags its "
                "source (a publish is pending) or the module itself is "
                "broken; the error above says which.\n"
            )
        except Exception:
            pass
        return 0

    try:
        result = assert_day_branch(str(repo_root), compute_machine(), local_day())
    except Exception:
        # Review: coordinator:code-reviewer -- an exception raised by the
        # engine's cut/warn logic (lock contention, a git subprocess failure)
        # must not collapse to the same silent "nothing happened" signature
        # as a clean no-op result; that is the identical-silence collapse
        # this module's docstring says it exists to close, one call deeper.
        try:
            sys.stderr.write(
                "[day-branch-assert] assert_day_branch() raised -- the "
                "day-branch invariant was NOT asserted this boot.\n"
            )
        except Exception:
            pass
        return 0

    try:
        if result.message:
            print(result.message)
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
