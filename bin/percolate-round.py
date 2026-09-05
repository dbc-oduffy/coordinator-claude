"""percolate-round.py — one-command sequencer for a single-target percolate
publish round: dry-run -> parse -> scan-secrets -> inverse-drift -> Step 3
gate -> real run -> commit -> CI smoke -> push (on a clean round; DR-301).
`--no-publish` stops before the push, same as this module's old behaviour.

Ports the nine hand-driven steps `coordinator/skills/percolate/SKILL.md`
(DoE-claude) currently has the EM drive one CLI invocation at a time into a
single sequenced driver. Every step already has its own CLI
(`percolate-gate.py`, `percolate-parse-dryrun.py`, `publish.py`) — this
module SEQUENCES those via subprocess, it does not reimplement any of their
logic. The commit step is the one exception: `scoped-git-commit` (the
`ceremony.scoped_git_commit` CLI) was killed 2026-08-23 (PM ruling, DR-344),
so the commit leg calls `coordinator_core.git.commit.commit_paths` in-process
instead (C3, docs/plans/2026-08-29-the-push-subsystem-leaves-and-then-the-
pipeline-can-go.md -- repointed off the killed `commit_pipeline.
run_commit_pipeline`, which itself mirrored `publish.py::
_commit_published_dests`, 2026-08-25).
Single-target only: multi-target (no-argument) round orchestration is
explicitly out of scope (see the originating plan's Out of scope section).

THE LOAD-BEARING CONSTRAINT IS RELAXED BY DR-301, NOT BY A LATER READER'S
INFERENCE (docs/decisions/DR-301-agent-initiated-publish-push-is-automatable.md):
this CLI now DOES invoke `git push` — on a clean round, publishing is the
default, not an operator's separate step. What replaced the old never-push
constraint is the EVIDENCE GATE (`_round_refusal_reason`, C2/AC3): the push
runs only when every row succeeded, `declined_paths` is empty, no
unacknowledged Phase 4 REVIEW warnings remain, and CI smoke (run AFTER the
commit — see below) came back green. `--no-publish` opts back into the old
print-and-stop behaviour, and `_print_push_notice` survives as exactly that
path (plus the gate-refused path, where it names the condition
`_round_refusal_reason` reported) — it prints `percolate-push <target>`
(coordinator/bin/percolate-push.py) rather than running anything, in both
of those cases. A future reader restoring "never push" as a "fix" would be
reverting DR-301, not correcting a bug.

The self-disarm half of the old constraint is UNCHANGED and stays true:
this CLI still never creates or clears an `allow-xrepo-write` marker.
`bump_foreign_repo_write` denying an unauthorized push into a publish
mirror is the guard working as designed; a CLI that clears its own marker
is the self-disarm shape the guard pack blocks elsewhere, and DR-301 does
not license it (DR-301 § Negative-spec). The round-failure marker this
module DOES write/clear (`setup/percolate-state/<target>.round-failed.json`,
see `_round_failure_marker_path` below) is a different marker, under a
different name, gating a different thing — it can only make
`percolate-push.py`'s own destination-state gate (C4) refuse harder; its
absence never grants a push that gate would otherwise refuse. It never
touches the `allow-xrepo-write` namespace.

Commit-pathspec provenance (AC7, superseded 2026-08-23 by chunk C4 of
docs/plans/2026-08-23-rebuild-the-percolate-round-as-six-steps.md AC4/AC5,
and again 2026-08-26 by chunk C2 of docs/plans/2026-08-26-a-refused-round-
strands-its-payload-forever.md AC2/AC2b): the pathspec passed to the commit
leg (`coordinator_core.git.commit.commit_paths`, repointed C3 2026-08-29 off
the § C6 2026-08-25 `commit_pipeline.run_commit_pipeline`) is derived from
a `RoundManifest` (`coordinator_core.percolate.manifest`) publish.py's real
run persists to disk (`_read_fresh_round_manifest`), never from a re-parse of
that run's printed `NEW:`/`UPDATE:`/`DELETE:`/`REMOVE:` lines, and never from
a `git status` survey of the destination either. `_pathspec_from_manifest`
compares the manifest's `declared_payload` set against dest HEAD, not
against dest's working tree -- the worktree baseline is what let a stranded,
already-synced-but-uncommitted round compare byte-equal forever and hid a
still-uncommitted deletion outright, since Step 4's real run had already
removed the file from disk before the next round's comparison ever ran (see
that plan's "The root cause, stated exactly"). A rename needs no
source-to-target resolution under this shape: it naturally reports as a
REMOVE (old name, tracked at HEAD, absent from the declared payload) plus a
NEW (new name, in the declared payload, absent from or differing at HEAD) --
a correct end state for the commit regardless of whether git's own
similarity detector later recognises it as a rename (docs/plans/2026-08-13-
the-publish-round-commits-the-names-it-a.md § C2, AC2, whose pathspec-names-
only-post-transform-paths invariant this still satisfies, just via a
different mechanism). Every entry is a specific file path — never a
directory — so the pathspec the commit leg receives never contains a
directory element, satisfying `commit_pipeline.explicit_stage`'s
untracked-files-beneath-a-directory-never-swept behaviour by construction,
without needing to touch that module (see the originating
plan's Substrate corrections § 1-2 for why touching it would be wrong).

CI-smoke ordering (the other subtlety the plan calls out): CI smoke
(`_run_ci_smoke`) runs AFTER the commit, never before. A file the real run
de-allowlisted out of the destination stays TRACKED at the destination's
pre-commit HEAD until that deletion is committed — `check-python-checks`
false-reds on it until then. Running CI smoke pre-commit reproduces that
false red; this module's step order rules it out.

Usage:
    percolate-round.py <target> [--percolate-root <path>] [--yes] [--no-publish]

  <target>            Single registered percolate target name (resolved via
                       `setup/publish-targets.portable`). Required.
  --percolate-root     Override the resolved PERCOLATE_ROOT (SKILL.md Step
                       0.5). Defaults to `percolate-gate.py resolve-root`'s
                       own four-rung ladder. Exists mainly so a test or a
                       repo-local percolate-root clone can pin the root
                       without env-var plumbing.
  --yes                Skip the interactive Step 3 confirmation prompt and
                       proceed as though the operator answered "y". The
                       gate-fire DETECTION logic still runs unconditionally
                       (deletions / >=10 files / sensitive paths / MEDIUM
                       leak hits / inverse-drift hits are still computed and
                       still printed) — this flag only removes the blocking
                       `input()` call, for scripted/CI invocation. It never
                       touches the push step: `--yes` cannot make this tool
                       push, only skip the human=y/N read on the publish
                       gate.
  --invocation-authorized
                       Treat THIS invocation itself as the Step 3 confirm.
                       For a skill/slash-command wrapper only: the human
                       already supplied authorization by invoking the
                       command, and the wrapper passes this flag to say so
                       — it must never be set by a bare human CLI run or by
                       an unattended/cron/nested-agent caller, since it
                       skips the prompt unconditionally the same as --yes
                       (distinct flag because --yes is forbidden on an
                       interactive PM session by the invoking skill's own
                       rules, and conflating the two would collapse that
                       distinction). A tty invocation without this flag
                       still prompts; a non-tty invocation without it
                       exits _EXIT_CONFIRM_REQUIRED instead of prompting.
  --no-publish         Opt out of the default publish-on-clean-round
                       behaviour (DR-301). Keeps the old print-and-stop
                       terminus: `_print_push_notice` prints the
                       `percolate-push <target>` command instead of running
                       it, even on an otherwise-clean round.

Exit codes:
    0 — PASS or PASS-WITH-WARNINGS on a clean round: pushed (unless
        `--no-publish`, in which case the push command was printed
        instead). Also 0 for a no-op round (nothing to publish) whether or
        not it found unpushed dest commits to push (AC2b).
    1 — FAIL: some step exited non-zero, or the operator declined the Step 3
        gate, or CI smoke came back red, or a green round's push itself
        failed. No push command is printed on a FAIL that reaches past the
        commit (AC8/AC4) — printing it after CI has already told the
        operator not to push would contradict the FAIL this function
        itself just reported.
    2 — usage error (bad argv, target not resolvable via Branch 0 gate).
    3 — Step 3 confirm required: the round reached the publish gate on a
        non-tty stdin without `--invocation-authorized`. Fires for ANY
        non-tty stdin, `sys.stdin.isatty()` being false is the entire test —
        including a piped answer (`echo y | percolate-round.py ...`) that
        would have supplied one; this driver never calls `input()` off a
        tty, on purpose, so a piped answer is refused rather than read.
        Named refusal, not a crash — the round's dry-run verdict prints
        first, nothing is published. Use `--invocation-authorized` or
        `--yes` for the scripted/non-interactive path.

Negative-spec: does NOT create or touch `setup/percolate-state/<target>
.lastsync` or any `allow-xrepo-write` marker (it DOES read/write/clear its
own, differently-named round-failure marker — see module docstring above),
does NOT edit `coordinator_core/git/commit.py` or `percolate-gate.py` (both
owned elsewhere — the commit leg below is a CALLER of
`coordinator_core.git.commit.commit_paths`, not an editor of it), does NOT drive
Branch 0's interactive first-run setup walk (a target that fails the branch0-gate
check here is a usage error pointing back at `/percolate <target>` to walk
setup, not something this CLI attempts itself), and does NOT support
multi-target/no-argument rounds.

Spec backlink: pln-percolate-publish-round-read-t-9d73fa
§ Tasks C2, Acceptance Criteria AC6-AC10.
Spec backlink: coordinator/skills/percolate/SKILL.md (DoE-claude) — Steps 0.5,
1, 2, 2c, 2d, 3, 4, 5, 6, 7.
Spec backlink: docs/plans/2026-08-14-publishing-runs-itself.md § C3,
Acceptance Criteria AC2/AC2b/AC3/AC4/AC5/AC9.
Spec backlink: docs/decisions/DR-301-agent-initiated-publish-push-is-automatable.md
— the ruling that relaxed THE LOAD-BEARING CONSTRAINT above.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

_BIN_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _BIN_DIR.parent.parent
_COORDINATOR_LIB = _BIN_DIR.parent / "lib"

_ENGINE_BOUND_NAMES = (
    "_RoundLockTimeout",
    "_round_held_lock",
    "_INHERITED_LOCK_ROOTS_ENV",
    "publish_contention_wait_secs",
    "publish_lane",
    "_RoundManifest",
    "_read_manifest",
    "_default_manifest_path",
)


def __getattr__(name: str):
    """PEP 562 module `__getattr__` -- lets a caller that reaches for one of
    `_ENGINE_BOUND_NAMES` BEFORE `main()` has run (e.g. this file's own test
    suite and `percolate-mirror.py`, both of which monkeypatch/read these
    names off the module ahead of calling `main()`) trigger
    `_bootstrap_engine()` lazily on first access, instead of requiring them
    to already be module globals at import time. Only fires when the name is
    NOT already present in this module's `__dict__` -- once
    `_bootstrap_engine()` has run once (via this hook or via `main()`), the
    plain global wins on every later lookup and this function is not called
    again for that name."""
    if name in _ENGINE_BOUND_NAMES:
        _bootstrap_engine()
        try:
            return globals()[name]
        except KeyError:
            raise AttributeError(
                f"module {__name__!r} has no attribute {name!r}"
            ) from None
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _bootstrap_engine() -> None:
    """Bind every `_ENGINE_BOUND_NAMES` module global. Called once, first
    thing in `main()` (or lazily via `__getattr__` above, for a caller that
    reaches for one of these names before `main()` runs). Idempotent by
    construction: the all-names guard covers every name in
    `_ENGINE_BOUND_NAMES`, not a single sentinel, and each freshly-imported
    name is published via `globals().setdefault(...)` -- so a caller's
    monkeypatch of just one of these globals (e.g. `publish_lane`) is left
    alone even when some other bootstrapped name is still missing, rather
    than being clobbered by a later incidental trigger."""
    if all(n in globals() for n in _ENGINE_BOUND_NAMES):
        return

    # Moved out of module scope (was two unconditional sys.path.insert calls
    # here): mutating sys.path on every import of this file was a process
    # global ~50 warm-server sessions share. Only the trigger moved.
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    if str(_COORDINATOR_LIB) not in sys.path:
        sys.path.insert(0, str(_COORDINATOR_LIB))

    from coordinator_core.locked_write import (  # type: ignore[import-not-found]
        LockTimeout as _RoundLockTimeout_,
        held_lock as _round_held_lock_,
    )
    from percolate.wire_contract import (  # type: ignore[import-not-found]
        INHERITED_LOCK_ROOTS_ENV as _INHERITED_LOCK_ROOTS_ENV_,
        publish_contention_wait_secs as publish_contention_wait_secs_,
    )
    from coordinator_core import publish_lane as _publish_lane_  # type: ignore[import-not-found]
    from coordinator_core.percolate.manifest import (  # type: ignore[import-not-found]
        RoundManifest as _RoundManifest_,
        read_manifest as _read_manifest_,
    )
    from coordinator_core.percolate.round import (  # type: ignore[import-not-found]
        default_manifest_path as _default_manifest_path_,
    )

    for _name, _value in (
        ("_RoundLockTimeout", _RoundLockTimeout_),
        ("_round_held_lock", _round_held_lock_),
        ("_INHERITED_LOCK_ROOTS_ENV", _INHERITED_LOCK_ROOTS_ENV_),
        ("publish_contention_wait_secs", publish_contention_wait_secs_),
        ("publish_lane", _publish_lane_),
        ("_RoundManifest", _RoundManifest_),
        ("_read_manifest", _read_manifest_),
        ("_default_manifest_path", _default_manifest_path_),
    ):
        globals().setdefault(_name, _value)


GENERATES = []  # writes only round-failure markers and pushes commits under the resolved percolate `dest` (a foreign publish-mirror repo), never a fixed claude-klabauter-tracked path

_EXIT_OK = 0
_EXIT_FAIL = 1
_EXIT_USAGE = 2
_EXIT_CONFIRM_REQUIRED = 3
#: Contended per-destination lock: a peer holds the dest, nothing is broken,
#: and this round did not start. Distinct from `_EXIT_FAIL` because the two
#: want opposite responses — a failure wants diagnosis, a queue wants either
#: a wait or a shrug — and a caller that cannot tell them apart reads every
#: refusal as breakage. Value 75 is `EX_TEMPFAIL` (sysexits.h): "temporary
#: failure, the user is invited to retry".
#: Spec backlink: docs/reference/percolate-lock-contention.md
_EXIT_LOCK_BUSY = 75

def _lock_busy_message(dest: str, exc: Exception) -> str:
    """Thin delegate onto `percolate.wire_contract.lock_busy_message` (C3,
    staff-eng finding 0) — the builder itself now lives there, shared with
    `publish.py`'s own inline BUSY branch, so round/mirror/publish all emit
    one text. `percolate-mirror.py` no longer calls this delegate — it was
    repointed directly at `percolate.wire_contract.lock_busy_message`. The
    real reader left is
    `test_publish_lock_denies_fast.py::test_publish_emits_the_same_text_round_does`,
    which calls this delegate directly to prove round and publish emit
    byte-identical text; do not delete it without updating that test.
    """
    from percolate.wire_contract import (  # noqa: PLC0415 - thin delegate, deferred import
        lock_busy_message as _lock_busy_message_shared,
    )

    return _lock_busy_message_shared(dest, exc)


_PERCOLATE_GATE = _BIN_DIR / "percolate-gate.py"
_PARSE_DRYRUN = _BIN_DIR / "percolate-parse-dryrun.py"
_PUBLISH = _BIN_DIR / "publish.py"
_STATE_ROOT_RESOLVER = _REPO_ROOT / "coordinator" / "lib" / "coordinator-state-root.py"

#: D1 fix — inherited-holder handoff. `_cmd_round` opens `_round_held_lock`
#: over `Path(dest)` and spawns `publish.py` (Step 4 real run) as a
#: subprocess INSIDE that `with` block; `publish.py::main`'s own lock loop
#: (`_publish_held_lock`, keyed identically via `held_lock`'s
#: `sha1(realpath(target))`) then tries to acquire that SAME key from a
#: fresh `os.open` in the child process, which blocks against the parent's
#: still-open flock (flock is per-open-file-description, so it blocks
#: across the process boundary too) until `LOCK_TIMEOUT_SECS` and the round
#: dies. This env var, set ONLY on the Step 4 real-run child's own env (never
#: on any other subprocess this driver spawns, and never left in
#: `os.environ` afterward), carries the `os.pathsep`-joined list of
#: `"<this process's own pid>=<realpath>"` entries this parent process
#: already holds `_round_held_lock` over. `publish.py::main`'s lock loop
#: skips acquiring exactly those roots, only once it has verified the
#: entry's PID against its own `os.getppid()` (§ code-reviewer P2 —
#: presence alone is not authentication), and still acquires every other
#: root the run's rows resolve to — never a blanket "skip all locking when
#: this token is present." `_INHERITED_LOCK_ROOTS_ENV` itself now lives in
#: `percolate.wire_contract` (shared with `publish.py`, single source of
#: truth — see that module).
#: Spec backlink: docs/plans/2026-08-14-percolate-round-deadlock-and-gate-attribution.md § D1/C1.


# ---------------------------------------------------------------------------
# Subprocess plumbing — every sibling CLI is invoked as `[python, script, ...]`
# so this driver stays Windows-first-class (no shebang/exec-bit dependence).
# ---------------------------------------------------------------------------

#: ---------------------------------------------------------------------
#: Per-leg subprocess bounds — one named family per cost model, and NO
#: shared default. `_run` takes `timeout` as a REQUIRED keyword (below),
#: so a leg's bound is a decision its author had to make, never something
#: inherited by omission.
#:
#: This replaces a single `_SUBPROCESS_TIMEOUT_SECS = 600.0` that ~24 call
#: sites inherited silently — one constant spanning a 24ms
#: `git rev-parse --show-toplevel` and a full-tree publish — plus a
#: `_PUBLISH_LEG_TIMEOUT_SECS = 3600.0` over six more. Both were defended
#: by machine-load-norm.md read as a licence to widen; DR-344 § 7 retired
#: that reading (load raises the bar, it never relaxes a number), and an
#: hour-long bound cannot tell "slow" from "wedged" at all, so it detects
#: nothing it was installed to detect.
#: Spec backlink: docs/problems/2026-08-21-the-over-budget-timeout-hitlist.md § G1;
#: DR-349 § "An implicit default spanning unrelated call sites".
#:
#: Measurement basis: process time (user+kernel across the spawned tree)
#: via `coordinator_core.benchmarks.process_time :: batched_process_time_ms`,
#: taken 2026-08-21 against the live `claude-klabauter` mirror (102,024
#: non-`.git` files).
#: ---------------------------------------------------------------------

#: ---------------------------------------------------------------------
#: THE UNIT MISMATCH THIS BLOCK EXISTS TO HANDLE, stated first because
#: every constant below is built out of it and a later reader will
#: otherwise "simplify" it back out.
#:
#: DR-344 gates on PROCESS TIME. `subprocess.run(timeout=)` can only ever
#: enforce WALL CLOCK. On this box those differ by two orders of
#: magnitude, and not because anything is slow — because 50-70 concurrent
#: sessions is the design condition, so a spawn waits to be scheduled.
#: Measured 2026-08-21, plain `subprocess.run`, 60 samples each:
#:
#:   leg                            process   wall p50   wall p95   wall max
#:   `git --version`                 33.6ms    1,462ms    2,891ms    4,588ms
#:   `git -C dest rev-parse`         33.6ms      847ms    2,907ms    4,065ms
#:   `git -C dest status --porcelain` 190.6ms     791ms    2,524ms    2,841ms
#:   `python -c pass`                36.7ms      411ms      905ms    1,644ms
#:
#: So a leg costing 34ms of CPU routinely takes 1.5 wall-seconds to
#: complete, and took 4.6 at worst. A `timeout=2.0` on local git — the
#: value `coordinator_core/git/repo_root.py :: _TIMEOUT_SECS` ships and
#: the hitlist prescribes — is therefore a coin flip HERE, where the
#: bound is a hard kill of a live publish round rather than a degrade to
#: a parent-walk. It was tried: `test_percolate_round_dest_paths_exist ::
#: test_mixed_batch_with_worktree_fast_path_and_git_probe_combined` went
#: red under a concurrent suite and green in isolation, which is the
#: definition of a bound firing on peer load instead of on cost.
#:
#: The resolution is ADDITIVE, never multiplicative: the scheduling delay
#: is a roughly fixed per-spawn cost of sharing the box, not a factor
#: that scales with the leg. So each bound below is
#: `<what this leg may cost> + <what the box adds to any spawn>`, and the
#: second term is ONE named constant. That keeps the load norm visible as
#: its own term instead of dissolved into a house number, and it means
#: raising it for one leg raises it for all of them (DR-349 § 2).
#: ---------------------------------------------------------------------

#: What the box adds to any spawn under its design load, over and above
#: the leg's own cost. 2.2x the worst wall-clock spawn-to-exit observed
#: across the 170 samples above (4,588ms, for a 33.6ms `git --version`).
#: It is headroom over a measured maximum, not a budget: nothing is
#: allowed to COST this, and a leg that consumes it is either wedged or
#: the box has gone twice past its worst observed scheduling delay —
#: both reportable, neither a reason to raise this.
_SPAWN_SCHEDULING_HEADROOM_SECS = 10.0

#: Local git: the nine sites that spawn `git` against `dest` and wait for
#: one answer, plus the two batched whole-pathspec index reads.
#: Measured process time per spawn at dest — `rev-parse --show-toplevel`
#: 24.2ms, `rev-parse HEAD` 24.2ms, `status --porcelain` 190.6ms (the
#: family's worst member), `status --porcelain=v2 --branch` 151.6ms,
#: `ls-files --error-unmatch` over 400 paths 37.5ms, `check-ignore -z
#: --stdin` over 400 paths 212.5ms, `clean -fdn` 40.6ms.
#: The cost term is 2.0 — CLAUDE.md § Load norm's absolute per-process
#: ceiling, and 10.5x the family's measured worst member, so it is the
#: tree's existing local-git budget rather than a number typed here.
#:
#: Relationship to `coordinator_core.git.run :: run_git`, where hitlist
#: § G7 wants these sites. That seam originally applied 2.0 as a
#: narrow-only wall-clock CEILING, which the measurements above show
#: false-fires; it has since adopted this same split
#: (`LOCAL_PLUMBING_BUDGET_SECS = 2.0` + its own
#: `_SPAWN_SCHEDULING_HEADROOM_SECS = 10.0`, converted in one place by
#: `_wall_bound`), so the two now agree on both axes and this constant is
#: numerically identical to what `run_git(args)` resolves to.
#:
#: The remaining gap is shape, not bounds: `run_git` returns a
#: `GitResult` where every call site here consumes a `CompletedProcess`,
#: and takes args WITHOUT a leading `"git"`. All nine legs can migrate —
#: including `_dest_gitignored_paths`' `check-ignore -z --stdin`, once
#: that seam grew a bytes-only `input=` whose binary mode keeps the text
#: wrapper off the pipe (the `-z` scar below is written into its
#: docstring as the reason). Deferred deliberately: a shape-only sweep
#: across nine sites is its own reviewable unit, and folding it in here
#: would cost a reviewer the ability to see either change clearly.
#:
#: Negative spec: this bounds a PATHSPEC-scale input, not a tree-scale
#: one. `check-ignore -z --stdin` measured 4,553ms of process time when
#: fed all 102,024 dest paths, so a round whose pathspec approached tree
#: scale would breach — that is a defect report about
#: `_dest_gitignored_paths`' unbounded input, never a licence to raise
#: either term.
_GIT_PLUMBING_TIMEOUT_SECS = 2.0 + _SPAWN_SCHEDULING_HEADROOM_SECS

#: The one genuinely remote leg (`_push_dest`'s `git push`). Named
#: separately because a network round trip has a cost model no local
#: measurement bounds; DR-349 grants network legs no standing carve-out,
#: so this is a runaway guard, not a budget — the scheduling term is
#: immaterial against it and is deliberately not added. A read-only round
#: trip to the same remote (`git ls-remote --exit-code origin HEAD`)
#: measured 62.5ms of process time over 4 spawns and 1,347ms of wall, so
#: 120 is ~89x the observed trip; the margin is for a push's upload, not
#: for the handshake. Takes the tree's existing named push bound
#: (`coordinator_core/hooks/auto_push.py :: GIT_PUSH_TIMEOUT_SECS`) so the
#: two push sites agree instead of differing by 5x. A reduction from the
#: inherited 600, never a raise.
#:
#: It does NOT yet take `coordinator_core.git.run`'s remote lane
#: (`run_git(..., remote=True)` → `REMOTE_BUDGET_SECS` 30.0 + headroom =
#: 40.0s wall), and the reason is that the difference is a real decision
#: rather than a rename: 40 vs 120 is a 3x cut on the one leg here that
#: uploads a whole publish round's objects over a network, and no
#: measurement of a real push exists on either side. That seam documents
#: migrations onto it as needing to surface as decisions; this is one.
#: Measure a real push before adopting it.
_GIT_PUSH_TIMEOUT_SECS = 120.0

#: Registry/target resolution: `machine-local get`, `percolate-gate.py`'s
#: `resolve-root` / `branch0-gate` / `list-targets`, and
#: `coordinator-state-root.py --central`. Each is one interpreter start
#: plus a small config read. Measured process time — `percolate-gate.py`
#: 67.2ms, `coordinator-state-root.py --central` 50.0ms, against a
#: `python -c pass` floor of 36.7ms. Same 2.0 cost term as the git
#: family: these resolve identity, and identity resolution that COSTS
#: seconds is the defect, not the bound.
_REGISTRY_CLI_TIMEOUT_SECS = 2.0 + _SPAWN_SCHEDULING_HEADROOM_SECS

# NOT dead, despite this module's own legs no longer passing it: the scan and
# parse legs here became in-process `_run_step` calls, but `percolate-mirror.py`
# loads THIS module as `_round` and still spawns `percolate-parse-dryrun.py`
# through `_round._run(..., timeout=_round._ROUND_SCAN_LEG_TIMEOUT_SECS)` at
# three sites, and `test_percolate_round.py :: _DECLARED_LEG_BOUNDS` names it.
# Deleting it as unreferenced-in-this-file breaks the mirror driver at runtime.
_ROUND_SCAN_LEG_TIMEOUT_SECS = 60.0

#: The round's own scan legs: `percolate-parse-dryrun.py` (x2 per branch)
#: over the publish leg's stdout, and `percolate-gate.py`'s `scan-secrets`
#: and `inverse-drift` over the round's scan-file-list.
#: Measured on the registered `claude-klabauter-bin` row (2,064-file scan
#: list): `parse-dryrun` 96.9ms of process time over 1 spawn;
#: `scan-secrets` 307.3ms over 1 spawn; `inverse-drift` 880.2ms over
#: **25 spawns**, 4,569ms wall. 60.0 is 13x that worst member's wall.
#:
#: Sized above the additive shape the two families above use, and the
#: reason is the spawn count: `inverse-drift` pays the scheduling delay 25
#: times, not once, so a single headroom term does not cover it. That is
#: the honest bound for the code as it stands, and it blesses nothing —
#: both underlying numbers are defect reports owed upward. 880ms of
#: process time is over DR-344's 500ms brightline, and 25 spawns for one
#: gate leg is the amplification shape
#: `coordinator_core/tests/test_no_unbatched_per_item_git_spawn.py`
#: exists to catch. This constant comes down when they are fixed.
#:
#: All four call sites that once passed this as `timeout=` to a spawned
#: `_run` moved to in-process `_run_step`, which takes no timeout -- the
#: derivation above is preserved as the provenance record for
#: `percolate-gate.py`'s `_GIT_LEG_TIMEOUT_SECS` (60s, same figure), which
#: cites this number by value, not by name.

#: The commit leg used to be a `scoped-git-commit` subprocess with its own
#: timeout, split OUT of the publish bound below (staging/committing is a
#: different cost model from re-walking the whole source tree). Re-pointed
#: 2026-08-25 (§ C6) at `commit_pipeline.run_commit_pipeline` in-process —
#: no subprocess, no timeout of its own; the constant that named it
#: (`_COMMIT_LEG_TIMEOUT_SECS`, was 300.0) is retired along with it.

#: The three `publish.py` call sites — `_cmd_round_default`'s real run,
#: and `_cmd_round`'s dry run plus its real run — of which any one round
#: fires at most two. Each walks the whole source tree, applies the rename
#: transform into a fresh staging root, and runs the per-row guard set
#: over it.
#:
#: HELD at 3600, on a measurement rather than on the "slow, not hung, the
#: box is busy" sentence this docstring used to carry (DR-344 § 7 retired
#: that sentence). One `publish.py --dry-run --no-delta` of the SINGLE
#: `claude-klabauter-bin` row measured **88,750ms of process time across
#: 211 spawns**, 139s wall. `percolate-mirror` publishes all nine of that
#: mirror's rows through ONE `publish.py` invocation, so the measured
#: single-row cost extrapolates past 1,200s — which is why the reduction
#: to 900 this rebuild first attempted was withdrawn: it would have
#: hard-killed every mirror publish. Lowering it is a scope call reserved
#: to the PM (DR-349 § "What this record does not decide").
#:
#: So this number is not defended here, it is REPORTED. 88.75s of CPU and
#: 211 process creations to dry-run one row is the defect the 3600 marks,
#: exactly as the hitlist's framing predicts, and no value of this
#: constant is a fix for it. The hitlist's own answer stands: the bound
#: has nothing left to justify it once that spawn count comes down.
_PUBLISH_LEG_TIMEOUT_SECS = 3600.0

#: `<dest>/.github/scripts/run-all-checks.py` — consumer-owned code this
#: repo does not control, whose members include a pytest run
#: (`run-tests.py`). That is DR-349's *named* test-runner carve-out, so
#: this is the one bound in this module that is a runaway guard by
#: doctrine rather than by unpaid debt. Named rather than inherited so it
#: cannot be copied onto a leg that is claude-klabauter's own compute — which is
#: exactly what the deleted shared default did.
_EXTERNAL_CI_TIMEOUT_SECS = 600.0


def _run(cmd: List[str], *, timeout: float, **kwargs) -> subprocess.CompletedProcess:
    """Spawn one leg of the round under an EXPLICIT bound.

    `timeout` is keyword-only and required by design: a shared default is
    what let a 24ms `git rev-parse` and a full-tree publish sit under one
    ten-minute grant, and a new call site must not be able to acquire a
    bound by omitting an argument. Pick the family constant above whose
    cost model matches the leg; if none does, the leg needs its own named
    constant and a measurement, not the nearest existing number.
    """
    # Suppresses the console-window flash a headless Windows Bash spawn would
    # otherwise pop for every sibling-CLI invocation this driver makes.
    kwargs.setdefault("creationflags", getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **kwargs)
    except subprocess.TimeoutExpired as exc:
        # Converted to a non-zero CompletedProcess (never raised) so every
        # existing call site's own `returncode != 0` -> `_print_step_failure`
        # path handles a timeout the same way it handles any other failure,
        # with no per-call-site try/except needed.
        stdout = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout or b"").decode("utf-8", "replace")
        stderr = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr or b"").decode("utf-8", "replace")
        stderr = f"{stderr}\npercolate-round: timed out after {timeout}s: {' '.join(cmd)}".strip()
        return subprocess.CompletedProcess(cmd, returncode=124, stdout=stdout, stderr=stderr)


_SIBLING_CLI_MODULES: Dict[str, object] = {}


def _sibling_cli(script: Path):
    """Import a sibling step CLI once and keep it for the rest of the round.

    Same `importlib.util` idiom as `percolate-gate.py::_import_publish_module`
    and `percolate-sweep-scope-probe.py::_import_publish_module`. Cached per
    script because a round calls into `percolate-parse-dryrun.py` twice and
    `percolate-gate.py` five times; re-executing a module body per call would
    trade a process for an import and keep most of the cost.
    """
    key = str(script)
    module = _SIBLING_CLI_MODULES.get(key)
    if module is not None:
        return module
    import importlib.util  # noqa: PLC0415 - only needed on this path

    name = "_percolate_round_" + script.stem.replace("-", "_")
    spec = importlib.util.spec_from_file_location(name, script)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not build a module spec for {script}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    _SIBLING_CLI_MODULES[key] = module
    return module


def _run_step(script: Path, argv: List[str]) -> subprocess.CompletedProcess:
    """Call a sibling step CLI's `main(argv)` in THIS interpreter.

    A round used to spawn eight Python interpreters: five `percolate-gate.py`,
    two `percolate-parse-dryrun.py`, one `publish.py`. That is an artifact of
    this module's own origin -- it ports nine steps the EM used to type one CLI
    invocation at a time, and the subprocess boundary came along with them
    rather than being required by any of them. Measured with
    `coordinator_core/benchmarks/process_time.py :: batched_process_time_ms`
    (k=6): `percolate-gate.py resolve-root`, which does almost nothing, costs
    39.1ms process / 104.2ms wall against a 15.6ms bare-interpreter floor.

    Both sibling CLIs are shaped for this: `main(argv)` is three lines over
    `args.func(args)`, every `_cmd_*` handler RETURNS an int, and the only
    `sys.exit` in either file is its `__main__` guard. `SystemExit` is caught
    anyway -- a handler is free to grow one, and the round must not die of a
    step's exit the way it would not have died of a child's.

    Returns a `CompletedProcess` rather than a bare int so every call site
    keeps its existing `returncode`/`stdout`/`stderr` handling verbatim,
    including `_print_step_failure`, which prints the argv. `args[0]` is
    therefore the equivalent spawn, not a real one: it is what a reader would
    run by hand to reproduce the step.

    WHAT STAYS SPAWNED, and why it is not an oversight: `publish.py` (§ the
    real run). It is the only leg whose `_run` bound guards actual work rather
    than spawn scheduling (`_PUBLISH_LEG_TIMEOUT_SECS`, 3600s), it needs a
    distinct child environment (`_INHERITED_LOCK_ROOTS_ENV`), and one
    interpreter for the round's real work is proportionate where eight for its
    bookkeeping was not. An in-process call cannot be timed out -- there is no
    killable unit -- so a leg whose bound is load-bearing keeps its process.
    That is also why `percolate-gate.py`'s two `git` calls grew their own
    `timeout=` in the same change: collapsing `inverse-drift` in here would
    otherwise have removed the only bound they had.

    This function itself carries no timeout of any kind -- verified true for
    the two sibling CLIs as they stand today (no other blocking call, no
    unbounded loop, no network I/O), but that is an inspection of the
    current bodies, not a property this function enforces. The old
    subprocess boundary was a backstop regardless of what the child did;
    this one is not. A future change adding a blocking call (another
    `subprocess.run`, a network fetch, an unbounded read) to either sibling
    CLI must bring its own bound the way `_GIT_LEG_TIMEOUT_SECS` does,
    because the round driver no longer supplies one.
    """
    import contextlib  # noqa: PLC0415 - only needed on this path
    import io  # noqa: PLC0415 - only needed on this path
    import traceback  # noqa: PLC0415 - only needed on this path

    out, err = io.StringIO(), io.StringIO()
    equivalent_spawn = [sys.executable, str(script), *argv]
    try:
        module = _sibling_cli(script)
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = module.main(argv)
    except SystemExit as exc:
        code = 0 if exc.code is None else (exc.code if isinstance(exc.code, int) else 1)
    except Exception:
        err.write(traceback.format_exc())
        code = 1
    return subprocess.CompletedProcess(
        equivalent_spawn,
        returncode=int(code) if code is not None else 0,
        stdout=out.getvalue(),
        stderr=err.getvalue(),
    )


def _resolve_python() -> str:
    """CI-smoke interpreter resolution ladder (SKILL.md Step 5's `coordinator.
    python` contract): COORDINATOR_PYTHON env -> `machine-local get
    coordinator.python` -> this process's own interpreter. Never raises —
    CI smoke is a best-effort leg (skipped entirely when `run-all-checks.py`
    doesn't exist), so a ladder that can't resolve a pin degrades to
    `sys.executable` rather than failing the whole round over an optional
    step.
    """
    import os

    env_pin = os.environ.get("COORDINATOR_PYTHON", "").strip()
    if env_pin:
        return env_pin

    machine_local = shutil.which("machine-local")
    if machine_local is None:
        candidate = _BIN_DIR / "machine-local"
        if candidate.is_file():
            machine_local = str(candidate)
    if machine_local:
        result = _run(
            [machine_local, "get", "coordinator.python"],
            timeout=_REGISTRY_CLI_TIMEOUT_SECS,
        )
        pin = result.stdout.strip()
        if result.returncode == 0 and pin:
            return pin

    return sys.executable


def _resolve_percolate_root(override: Optional[str]) -> Optional[str]:
    if override:
        return override
    result = _run_step(_PERCOLATE_GATE, ["resolve-root"])
    if result.returncode != 0:
        print("percolate-round: could not resolve PERCOLATE_ROOT:", file=sys.stderr)
        print(result.stderr.strip(), file=sys.stderr)
        return None
    return result.stdout.strip()


def _resolve_central_state() -> Optional[Path]:
    """Best-effort `<central-state>/repo-registry.md` resolution (SKILL.md
    Step 2c's peer-repos-file). Absent central state degrades to no
    peer-repo-name scan leg, same as the skill's own "omit the flag if it
    doesn't exist" contract — never fatal to the round.
    """
    # Calls the native seam DIRECTLY rather than `_run_step`-ing the CLI over
    # it, and that distinction is load-bearing rather than a shortcut.
    # `coordinator-state-root.py`'s `main()` opens with
    # `require_dispatch_engine_on_path()`, whose whole job is putting an engine
    # on `sys.path` for an interpreter that has not got one. Run in a CHILD --
    # a clean slate, no `coordinator_core` bound -- it resolves and exits 0.
    # Run HERE it raises `ProvenanceDivergenceError`: this module binds
    # `coordinator_core` at module scope off the LOCATOR axis (ordinary
    # `sys.path`), and on a box whose DISPATCH ladder (env var / pointer file /
    # machine-local registry) names a different engine root, the two disagree
    # and the guard fires. Measured on this box: spawned rc=0
    # ('<repo>/state'), in-process rc=1 (`coordinator_core` bound from
    # claude-klabauter against a dispatch root of claude-klabauter).
    #
    # `_run_step` would swallow that in its `except Exception` and this
    # best-effort caller would return None, silently dropping the
    # peer-repo-name scan leg on a box where the old spawn worked. The seam
    # underneath the CLI needs no engine-root resolution at all -- we are
    # already running inside the engine -- so reaching past the argv wrapper
    # keeps the spawn eliminated AND the leg alive.
    # Review: coordinator:code-reviewer, slice B finding 1.
    if not _STATE_ROOT_RESOLVER.is_file():
        return None
    try:
        from coordinator_core.state_root import (  # noqa: PLC0415 - engine-only path
            coordinator_state_root as _coordinator_state_root,
        )

        central = (_coordinator_state_root(central=True) or "").strip()
    except Exception:
        return None
    if not central:
        return None
    registry = Path(central) / "repo-registry.md"
    return registry if registry.is_file() else None


# ---------------------------------------------------------------------------
# Branch 0 / Step 1 — target resolution
# ---------------------------------------------------------------------------

def _branch0_gate(target: str, percolate_root: str) -> Optional[str]:
    """Returns the target's `<source_dir>`, or None on any Branch-0 failure
    (already printed to stderr). Never walks the interactive first-run setup
    procedure — see this module's own negative-spec."""
    result = _run_step(
        _PERCOLATE_GATE, ["branch0-gate", target, "--percolate-root", percolate_root]
    )
    if result.returncode != 0:
        stdout = result.stdout.strip()
        print(f"percolate-round: target '{target}' is not ready for a round:", file=sys.stderr)
        print(stdout, file=sys.stderr)
        # A `route:` line means the gate already resolved the next move: the name
        # matches several registered rows sharing one mirror, which is a
        # coordinator-publish job, not a round. Offering the first-run setup walk
        # on top of that would contradict it and send an operator to re-register
        # rows that already exist (§ `percolate-gate.py::
        # _missing_target_entry_guidance`). Setup is still the right offer for
        # every other Branch-0 failure.
        if not any(line.startswith("route:") for line in stdout.splitlines()):
            print(f"Run `/percolate {target}` once to walk first-run setup, then retry.", file=sys.stderr)
        return None
    stdout = result.stdout.strip()
    if not stdout.startswith("CONFIGURED:"):
        print(f"percolate-round: unexpected branch0-gate output: {stdout!r}", file=sys.stderr)
        return None
    return stdout[len("CONFIGURED:") :]


def _resolve_dest(target: str, percolate_root: str) -> Optional[str]:
    result = _run_step(
        _PERCOLATE_GATE,
        ["list-targets", "--percolate-root", percolate_root, "--target", target],
    )
    if result.returncode != 0 or not result.stdout.strip():
        print(f"percolate-round: could not resolve dest for target '{target}'.", file=sys.stderr)
        return None
    return result.stdout.strip()


def _resolve_repo_root(dest: str) -> Optional[str]:
    """`dest` (§ `_resolve_dest`) may itself be a subdirectory of the
    mirror's git worktree — e.g. a `dest_subdir` row's `<mirror>/coordinator_core`
    rather than `<mirror>` — while a real run's OTHER rows can report
    against sibling subtrees of the SAME worktree (`<mirror>/coordinator/bin`).
    Resolves the actual worktree root once via `git rev-parse
    --show-toplevel` so every row's pathspec entry (`_build_commit_pathspec`'s
    `repo_root=`) and the commit's own `--repo` argument share the identical
    root — the two must never be allowed to diverge (§ Review below)."""
    result = _run(
        ["git", "-C", dest, "--no-optional-locks", "rev-parse", "--show-toplevel"],
        timeout=_GIT_PLUMBING_TIMEOUT_SECS,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return result.stdout.strip()


# `_TARGET_LINE_RE` is the one survivor of the retired stdout-scrape family
# (chunk C4, docs/plans/2026-08-23-rebuild-the-percolate-round-as-six-
# steps.md AC5, further retired 2026-08-23 with `--dry-run-first` itself):
# `_extract_change_lines`/`_CHANGE_LINE_RE`/`_RENAME_LINE_RE`/
# `_TRAILING_ANNOTATION_RE`/`_BLOCK_HEADER_RE` parsed publish.py's printed
# `NEW:`/`UPDATE:`/`RENAME:`/`--- <subdir> ---` report to build a commit
# pathspec; that whole family is gone (`_pathspec_from_manifest` reads a
# `RoundManifest` instead). This one regex survives for
# `_split_stdout_by_row_dest` below, whose only remaining caller
# (`percolate-mirror.py`'s scan-secrets/inverse-drift row attribution) is
# unrelated to the commit pathspec.
_TARGET_LINE_RE = re.compile(r"^\s*Target:\s+(.+?)\s*$")


def _split_stdout_by_row_dest(
    stdout_text: str, fallback_dest: str
) -> List[Tuple[str, str]]:
    """Splits REAL-run stdout into per-row `(dest, chunk_text)` pairs keyed
    by each row's own reported `  Target:` line. `fallback_dest` covers any
    line preceding the first `Target:` line — a single-row run has no such
    line at all, so its whole stdout stays one chunk under `fallback_dest`,
    matching today's single-row behaviour byte-identically (§ C5 body).

    SURVIVES chunk C4 (docs/plans/2026-08-23-rebuild-the-percolate-round-as-
    six-steps.md AC4/AC5) for exactly one remaining caller:
    `percolate-mirror.py`'s scan-secrets/inverse-drift per-row file-list
    attribution (that module's own `_run_gate_legs`) -- unrelated to the
    commit pathspec AC5 targets, the same category as the two
    `percolate-parse-dryrun.py` scrapes this plan's own scoping note leaves
    alone. `percolate-round.py`'s OWN pathspec-building callers of this
    function are gone; do not resurrect one."""
    rows: List[Tuple[str, List[str]]] = [(fallback_dest, [])]
    for line in stdout_text.splitlines():
        target_match = _TARGET_LINE_RE.match(line)
        if target_match:
            rows.append((target_match.group(1).strip(), []))
            continue
        rows[-1][1].append(line)
    return [(row_dest, "\n".join(lines)) for row_dest, lines in rows]


# ---------------------------------------------------------------------------
# The manifest (chunk C4, docs/plans/2026-08-23-rebuild-the-percolate-round-
# as-six-steps.md AC4/AC5) -- replaces `_build_commit_pathspec`'s
# stdout-derived pathspec for the REAL-run commit.
# publish.py's own real run (C3.5) now persists a `RoundManifest` for every
# repo root it touched, keyed to what `_report_published_diff` actually
# compared (the fully-transformed staging tree against dest's CURRENT
# on-disk state, right before the swap) -- never a re-parse of what publish.py
# printed. A rename needs no resolution machinery under this shape: it is
# built from real file PRESENCE (staging vs dest), so it naturally reports as
# a REMOVE (old name, absent from staging) plus a NEW (new name, present in
# staging) -- a correct end state for the commit either way, whether or not
# git's own similarity detector later recognises it as a rename.
# ---------------------------------------------------------------------------


def _read_fresh_round_manifest(
    repo_root: Path, not_before: float
) -> Optional[_RoundManifest]:
    """Reads the manifest publish.py's real run just persisted at `repo_root`
    (`round.default_manifest_path` -- one file per dest repo, overwritten
    each round), or `None` if it is missing or STALE.

    THE LOAD-BEARING FRESHNESS CHECK that makes deleting the destination-
    dirtiness gate safe (AC5): `not_before` is a `time.time()` timestamp
    captured by the caller immediately before spawning the real-run
    subprocess. If the manifest file's mtime predates it, this is a LEFTOVER
    from an earlier round -- either a crashed predecessor that wrote a
    manifest but never got to commit it, or (the ordinary case) a prior
    successful round whose manifest THIS round's real run had nothing to
    overwrite because THIS round was a genuine no-op. Either way, treating a
    stale file as this round's own bytes is exactly the "can't distinguish
    this round's bytes from a crashed predecessor's" defect the dirtiness
    gate used to guard against by inspecting `dest` BEFORE the real run ever
    started; this check inspects the manifest's OWN provenance AFTER the
    real run finishes, which is the more direct question to ask.

    Absence at this point can ONLY mean a genuine no-op, never an
    undetermined row: this function's caller only reaches it after
    confirming the real run exited 0 with no per-row failure text, and
    publish.py's own `main()` folds every succeeded row's changed/removed
    sets (sourced from `_report_published_diff`, which is unconditionally
    determined once reached, never `None`) into its end-of-run accumulators
    before deciding whether to write a manifest at all -- it skips the write
    ONLY when the accumulated added/updated and removed sets are BOTH empty
    (§ publish.py `main()`, the manifest-write block). A row that failed, or
    whose changed-set publish.py itself could not determine, would have made
    THIS caller's own `real.returncode != 0` / row-failure-text check refuse
    the round already, before this function is ever called.
    """
    _bootstrap_engine()
    manifest_path = _default_manifest_path(repo_root, "")  # round_id is not part of the path
    try:
        mtime = manifest_path.stat().st_mtime
    except OSError:
        return None
    if mtime < not_before:
        return None
    return _read_manifest(manifest_path)


_REMOVAL_SIDE_ENABLED = True
"""The removal side is ON (PM, 2026-08-26). It derives `(head_tree ∩
row_scope) - declared_payload` and commits those deletions at the mirror.

WHAT OPENED IT, in the order the objections fell. Each was a real gate, and
none was waved through -- the history is here because a reader deciding
whether to trust this flag needs to know which arguments were answered by
evidence and which dissolved.

  Both operands mis-scoped   -> fixed (C1). `row_scope` from
                                `manifest.published_dest_dirs` bounds width;
                                `declared_payload` widened past the scan
                                surface by `_walk_published_payload` bounds
                                narrowness.
  Could delete a live file   -> `_refuse_removals_present_on_disk`, a hard
                                refusal, doe-claude-em's condition of assent.
  Per-mirror assent needed   -> DISSOLVED, not satisfied. klabauter is ours
                                (PM); both owners can assent, so the
                                per-target scoping this flag lacks is
                                unnecessary. See the space-vs-time note below.
  Numbers off stale walks    -> a round on the fixed walk ran at each mirror.
  A crash could fake it      -> `publish.py :: _refuse_stranded_root_swap_
                                prior`. The root-dest swap's window was the
                                one mechanism that manufactures this leg's
                                exact preconditions; it is guarded at the
                                source rather than predicated around here.

MEASURED before the flip, both manifests postdating `e6ca74a70` (the walk fix):

  coordinator-claude   66 candidates, 0 present on disk, all 66 verified by
                       hand as absent from DoE source (tracked or untracked),
                       so none is re-publishable payload.
  claude-klabauter     0 candidates. declared 4673 / head 4670 / 0
                       `.fleet-env`.

klabauter read 0 BEFORE the walk fix too, and that 0 was the opposite of this
one: `declared_payload` had swamped the tree (48,929 declared, 44,264 of them
`.fleet-env`), emptying the removal set while the round reported a clean pass.
Same digit, opposite meaning. Never read a 0 here as "no backlog" without
checking the manifest's provenance first.

THE STANDING RISK, said out loud rather than left to be discovered:
`_refuse_removals_present_on_disk` is DORMANT at coordinator-claude, because 0
of the 66 are present on disk. The safety of that set therefore rests on the
by-hand source verification above, not on the guard. The guard protects the
NEXT round, not this one.

Two notes worth carrying to the next question on this module:

  - A property someone proposes to scope by SPACE (per-mirror, per-target,
    per-path), where the scoping does not bite, is usually one that varies
    over TIME. Every safety question here had that shape (DoE-claude
    coordinator/docs/wiki/verification-discipline.md, tripwire
    A-SAFETY-PROPERTY-HOLDS-OVER-AN-INTERVAL-NOT-OVER-A-THING).
  - An in-process predicate cannot close a cross-process hole. Two attempts
    were made here -- a round-clean predicate and a pre-sync probe -- and both
    failed for that reason. What works is a durable witness written BEFORE the
    window opens.

Leg A (`manifest.removed`, ungated, below) is not retired by this. The two
legs cover disjoint cases: Leg A carries a removal the CURRENT round observed;
only this leg can clear a backlog, which is by construction invisible to
`_report_published_diff`."""


def _pending_removal_warning(dest: str) -> str:
    """The revert instruction this module prints on its two decline paths is
    NOT the neutral undo its own architecture comment claims (§ `_cmd_round`,
    "the sync into `dest` ... is fully `git reset --hard HEAD && git clean
    -fd`-revertible, so a decline here leaves a synced-but-uncommitted `dest`,
    never a lost push"). Returns text to append to that instruction, or "".

    The premise held while the dest worktree carried nothing but the current
    round's bytes. It stopped holding the moment stranded removals began
    accumulating there -- which is the condition this whole deliverable exists
    because of. A path deleted from dest's worktree and still tracked at dest
    HEAD exists NOWHERE else: publish.py's `_report_published_diff` compares
    staging against that same worktree, so once a path is absent from it the
    removal is unobservable and never re-reported. The worktree IS the only
    record. `reset --hard && git clean -fd` restores every one of them and
    walks the mirror back to a state both removal legs have to re-earn --
    silently, and by following this module's own documented remedy.

    Measured 2026-08-26 at the `coordinator-claude` mirror: 66 such paths (43
    stranded from an earlier pass, 23 from a hand sweep). A HIGH-tier leak
    refusal there would have cost the entire backlog with no signal that it
    had.

    Named, never blocked. The revert is still the right move for an operator
    who wants the round undone; what was missing is that it is not free. Reads
    `git status --porcelain=v1` and counts a `D` in EITHER the staged or the
    worktree column (`line[0] == "D"` or `line[1] == "D"`) -- both leave a
    deleted-and-tracked-at-HEAD path whose only record is dest's worktree, the
    hazard this probe exists to catch. An unstaged deletion (`" D"`) is the
    ordinary case; a staged one (`"D "`) is left behind by a prior invocation
    of THIS module's own commit leg (`commit_pipeline.explicit_stage`'s
    `git add -- <paths>`) that died between staging and committing. A
    rename-with-delete (`"R  old -> new"`) is correctly excluded by this
    predicate: the destination content still exists under the new name, so
    there is no lost record for this warning to raise. `=v1` pins the format
    explicitly rather than relying on it staying git's untagged default.
    Fails toward saying nothing on a probe failure -- an unreadable dest must
    not manufacture a warning about a count it does not have.

    Reported by doe-claude-6e (2026-08-26)."""
    result = _run(
        ["git", "-C", dest, "--no-optional-locks", "status", "--porcelain=v1"],
        timeout=_GIT_PLUMBING_TIMEOUT_SECS,
    )
    if result.returncode != 0:
        return ""
    pending = sum(
        1 for line in result.stdout.splitlines() if len(line) >= 2 and (line[0] == "D" or line[1] == "D")
    )
    if not pending:
        return ""
    return (
        f"\n    WARNING: that revert is not free. dest holds {pending} pending "
        "removal(s) -- paths already deleted from its worktree and still tracked "
        "at its HEAD. The worktree is their ONLY record; a publish round cannot "
        "re-report a removal it can no longer observe. `reset --hard` restores "
        "them and discards the backlog. To keep them, commit the deletions at "
        "dest instead, or leave dest as it is and re-run the round."
    )


def _dest_head_tree(repo_root: str) -> set:
    """One `git ls-tree -r HEAD --name-only` spawn -- every dest-relative,
    POSIX path dest HEAD tracks (AC4: one process, never one per path).

    This is one of the two dest-HEAD reads `_pathspec_from_manifest` uses in
    place of the worktree baseline (docs/plans/2026-08-26-a-refused-round-
    strands-its-payload-forever.md § "The root cause, stated exactly"): the
    prior code compared the declared payload against dest's WORKING TREE,
    which is exactly what makes a stranded deletion invisible -- Step 4's
    real run already removed the file from disk, so a worktree-baseline
    comparison finds no difference and never re-reports it, even though the
    file is still tracked at HEAD and was never committed as removed.

    Fails toward doing nothing on a probe failure (empty set): the caller's
    removal side is `head_tree - declared_payload`, so an empty `head_tree`
    here means the removal side fires on nothing rather than risking a
    misread HEAD driving a deletion; the add side still falls back to
    treating every declared path as differing (safe -- `git add` on an
    unchanged path is a no-op, never data loss)."""
    result = _run(
        ["git", "-C", repo_root, "--no-optional-locks", "ls-tree", "-r", "HEAD", "--name-only"],
        timeout=_GIT_PLUMBING_TIMEOUT_SECS,
    )
    if result.returncode != 0:
        return set()
    return {line for line in result.stdout.splitlines() if line}


def _dest_head_diff_names(repo_root: str) -> set:
    """One `git diff --name-only HEAD` spawn -- tracked paths whose worktree
    bytes differ from dest HEAD (the content leg of the add-side union; AC4).

    MEASURED not sufficient alone (plan § "Two processes, not one, and `git
    diff HEAD` is not sufficient alone"): `git diff` never reports untracked
    files, so a declared-payload path with no HEAD entry at all (a genuine
    new file, or the residue of an earlier round that synced-but-never-
    committed it) never appears here -- the caller's add side also checks
    membership in `_dest_head_tree`'s output for exactly that reason, never
    relies on this set alone. Fails open (empty set) on a probe failure --
    narrows the add side to only the untracked-in-HEAD paths rather than
    fabricating a diverged HEAD read; a real problem still surfaces via the
    commit leg's own report."""
    result = _run(
        ["git", "-C", repo_root, "--no-optional-locks", "diff", "--name-only", "HEAD"],
        timeout=_GIT_PLUMBING_TIMEOUT_SECS,
    )
    if result.returncode != 0:
        return set()
    return {line for line in result.stdout.splitlines() if line}


def _pathspec_from_manifest(
    manifest: _RoundManifest, repo_root: str
) -> Tuple[List[str], Dict[str, int]]:
    """Builds the commit pathspec by comparing `manifest.declared_payload`
    against DEST HEAD, in both directions, then reusing
    `_filter_commit_pathspec` UNCHANGED rather than re-deriving its three
    safety filters (gitignored-at-dest, an already-absent deletion-intent,
    beneath a publish-staging directory). Those three matter just as much
    here as they did over a stdout-derived pathspec -- neither dest-HEAD read
    above applies any of them; each is an honest tree read, not a
    commit-safety filter. Skipping them would silently reopen the exact
    incident this plan's Problem section names: round `eebf1c67` committing
    1,028 files of a stranded `.bin.publish-staging-*.prior` directory into
    the public mirror.

    AGAINST HEAD, NOT THE WORKTREE (docs/plans/2026-08-26-a-refused-round-
    strands-its-payload-forever.md): a declared-payload path is named "NEW"
    when it is absent from dest HEAD's tree (`_dest_head_tree`) OR its
    worktree bytes differ from HEAD (`_dest_head_diff_names`) -- the union of
    both legs, since `git diff` alone never reports an untracked path. A dest
    HEAD path absent from the declared payload is named "REMOVE" -- the
    declared-payload restriction (not a raw HEAD-vs-worktree survey) is what
    keeps a stranded staging directory, which no row declares, out of this
    set by construction (AC3).

    `seen`'s value shape (`(tag, resolved_rel)`) matches what
    `_filter_commit_pathspec` has always consumed; `tag` here is only ever
    `"NEW"` or `"REMOVE"` (no `"UPDATE"`/`"DELETE"` spelling -- this
    derivation does not distinguish new-from-updated within the added side,
    and `_filter_commit_pathspec` only ever branches on `tag in ("DELETE",
    "REMOVE")` for its absent-deletion check, so `"REMOVE"` alone is
    sufficient)."""
    import os

    from coordinator_core.percolate.surface import (  # noqa: PLC0415 - lazy, engine-only path
        STRUCTURAL_NEVER_PUBLISHED_PREFIXES,
        matches_exclude_prefix,
    )

    repo_root_path = Path(repo_root)
    repo_root_norm = os.path.normpath(str(repo_root_path))

    head_tree = _dest_head_tree(repo_root)
    diff_names = _dest_head_diff_names(repo_root)

    seen: dict = {}
    for rel in sorted(manifest.declared_payload):
        if rel not in head_tree or rel in diff_names:
            seen.setdefault(str(repo_root_path / rel), ("NEW", rel))
    if _REMOVAL_SIDE_ENABLED:
        # § AC3, docs/dispatch-briefs/2026-08-26-open-the-percolate-removal-
        # side/C1.md -- the removal rule is `(head_tree ∩
        # row_scope) - declared_payload`, never a bare `head_tree -
        # declared_payload`. `row_scope` is `manifest.published_dest_dirs`
        # expanded to every dest-HEAD path beneath one of those directories
        # -- a `--target`-excluded sibling row or an untouched rest-of-mirror
        # path is in `head_tree` but never in `row_scope`, so it cannot be
        # named for removal no matter what `declared_payload` does or does
        # not contain. An empty `published_dest_dirs` (an old manifest with
        # no fourth set, or a round that published nothing) yields an empty
        # `row_scope` and therefore an empty removal set, always -- no probe,
        # no extra spawn, filtering the same `head_tree` `_dest_head_tree`
        # already read with one `ls-tree` call.
        # A row whose `dest_dir` IS the mirror root renders through `rel_id`
        # as "." (`Path.relative_to` of a path against itself), and the
        # flat-mirror rows this system publishes are exactly that shape (§
        # `publish.py`'s manifest-write block: "A flat-mirror row's `dest_dir`
        # IS the mirror root -- `LICENSE` and `.gitignore` sit in
        # `declared_payload` today"). A prefix test alone reads "." as a
        # directory NAMED `.` and matches no dest-HEAD path at all, so the
        # removal side would silently fire on nothing for precisely the
        # mirrors it was built for -- the failure looks like a clean round,
        # never like a mis-scope. Root entries scope to the whole tree, which
        # is what publishing into the root means; `""` is accepted alongside
        # "." so a manifest written by any other root-relative renderer reads
        # the same.
        row_scope_dirs = manifest.published_dest_dirs
        scopes_whole_tree = any(d in (".", "") for d in row_scope_dirs)
        row_scope = {
            rel
            for rel in head_tree
            if scopes_whole_tree
            or any(rel == d or rel.startswith(d + "/") for d in row_scope_dirs)
        }
        # A path the SSOT calls STRUCTURALLY NEVER PUBLISHED is neither
        # declarable nor removable, and both halves have to agree or the round
        # refuses on its own bookkeeping. `_walk_published_payload` prunes this
        # exact prefix set out of `declared_payload` deliberately (§ its own
        # NEGATIVE SPEC: an unpruned walk declared 44,264 `.fleet-env/` paths
        # and silently disabled the removal side). `row_scope` did not prune
        # it, so any such path TRACKED at dest HEAD fell out of
        # `row_scope - declared_payload` as a removal candidate, was found on
        # disk, and refused the round before sync.
        #
        # Measured witness (`coordinator-claude`, 2026-08-31): percolate writes
        # its own `.percolate/round-manifest.json` into the mirror and that file
        # is tracked at the mirror's HEAD, so every round after a fail-closed
        # one died at `_refuse_removals_present_on_disk` naming percolate's own
        # bookkeeping -- an error whose remedy text ("widen `declared_payload`")
        # is the one fix that must NOT be applied here: re-admitting `.percolate`
        # to the declaration would over-declare it back into the same
        # removal-side suppression the walker's prune exists to prevent. The
        # asymmetry is the defect, not the prune.
        row_scope -= {
            rel
            for rel in row_scope
            if matches_exclude_prefix(rel, list(STRUCTURAL_NEVER_PUBLISHED_PREFIXES))
        }
        removal_candidates = sorted(row_scope - manifest.declared_payload)
        _refuse_removals_present_on_disk(repo_root_path, removal_candidates)
        for rel in removal_candidates:
            seen.setdefault(str(repo_root_path / rel), ("REMOVE", rel))

    # UNGATED, and deliberately so -- a second removal source that needs no
    # `_REMOVAL_SIDE_ENABLED` because it cannot make the mistake that flag
    # exists to prevent. `manifest.removed` is publish.py's own per-row record
    # of what THIS round's source stopped publishing
    # (`_report_published_diff`), so it is row-scoped by construction and is a
    # POSITIVE assertion rather than an inference from absence. It structurally
    # cannot name an unprocessed row's payload or a never-scanned binary --
    # the two hazards AC1 and AC2 exist to contain on the gated leg.
    #
    # The two legs cover DISJOINT cases and neither retires the other (§ AC6
    # RESOLVED in the brief). Measured 2026-08-26: of 43 paths stranded at the
    # `coordinator-claude` mirror, ZERO appear in `manifest.removed`, and none
    # ever will -- `_report_published_diff` derives its removed-set by
    # comparing the staging dir against dest's WORKING TREE, so a path already
    # absent from that worktree leaves nothing to observe. This leg therefore
    # prevents NEW stranding; only the gated leg above can clear the backlog.
    #
    # Paths still present on disk are skipped rather than named. `explicit_stage`
    # runs `git add -- <paths>`, which stages a deletion only when the path is
    # GONE from the worktree; on a path still present and clean it is a pure
    # no-op. Naming one would put an entry in the pathspec that silently
    # accomplishes nothing -- measured on `whoami/`, all 23 of which sit in
    # `manifest.removed` while their mirror worktree copy is intact and clean
    # against HEAD. The skip is reported, never swallowed: a removal this round
    # observed and could not carry is exactly the class this module was told to
    # stop losing quietly.
    removed_still_on_disk: List[str] = []
    # `lexists`, not `exists` -- same reason as `_refuse_removals_present_on_
    # disk`'s own test, and load-bearing HERE FIRST because this leg is
    # UNGATED. `exists` follows symlinks, so a tracked symlink with a missing
    # target reads as absent, skips this guard, and is named for deletion: the
    # one file class where "not on disk" describes the target, not the path.
    for rel in sorted(manifest.removed):
        if os.path.lexists(repo_root_path / rel):
            removed_still_on_disk.append(rel)
            continue
        seen.setdefault(str(repo_root_path / rel), ("REMOVE", rel))
    if removed_still_on_disk:
        print(
            f"percolate-round: {len(removed_still_on_disk)} path(s) this round "
            "reported as removed are still present in dest's worktree, so a "
            "commit cannot express their deletion -- left out of the pathspec "
            "rather than named as a silent no-op. Their worktree copy must be "
            "swept before any rule can retire them.",
            file=sys.stderr,
        )
    return _filter_commit_pathspec(repo_root_path, repo_root_norm, seen, repo_root=repo_root)


class RemovalCandidateOnDiskError(RuntimeError):
    """A path the removal side named for deletion still exists at dest.

    Raised BEFORE any pathspec is built, so nothing is committed on this path
    -- same fail-closed ordering as `RoundVerifyFailure` and
    `RoundIdentityLeakError`.
    """


def _refuse_removals_present_on_disk(dest_root: Path, candidates: Sequence[str]) -> None:
    """AC6 -- the removal side may not delete a path that exists on disk.

    Added as a CONDITION OF ASSENT by doe-claude-em (2026-08-26), in their
    words "in the code, not in the procedure", before the removal side may be
    opened against a mirror this repo does not own.

    Why this exists on top of AC2. AC2 fixes the CAUSE of the known
    false-positive class: `declared_payload` sourced from the percolation SCAN
    surface misses a published-but-never-scanned file, which then reads as
    "no row declares this". Two members are known --
    `.github/scripts/check-persona-names.py` (both mirrors; deliberately
    excluded from the transform sweep so the release-CI checker never scrubs
    itself) and `coordinator_core/warm/door/door.exe` (a binary in a declared
    directory). A measured `live-undeclared == 0` is a snapshot of that class
    at one moment; the next member is a file nobody has written yet. AC2 fixes
    the cause, this catches the recurrence.

    LOUD, NEVER SILENT. A candidate that survives `(head_tree ∩ row_scope) -
    declared_payload` and is STILL on disk means the operands are wrong again
    -- that is a defect report, not a path to quietly drop from the set. A
    silent-skip version would have hidden both known witnesses rather than
    surfacing them, which is how the mis-scope stays invisible until it
    deletes something that mattered.

    The shaping consequence, which is the point rather than a side effect:
    with this invariant in place the pre-flight dry run is a CHECK, not a
    load-bearing gate. An irreversible rule against a public mirror should not
    depend on a human having run the right measurement at the right moment.

    `lexists`, NOT `exists`. `exists` follows symlinks, so a TRACKED symlink
    whose target is missing reads as absent, passes this refusal untouched,
    and is deleted by the removal side -- the one file class where "not on
    disk" is a statement about the target rather than about the path itself.
    Zero tracked symlinks on either mirror today; this is what keeps the first
    one from being reaped silently on the round that introduces it.
    """
    import os  # noqa: PLC0415 - lazy, matching this module's other `os` users

    present = [rel for rel in candidates if os.path.lexists(dest_root / rel)]
    if not present:
        return
    shown = present[:20]
    more = len(present) - len(shown)
    raise RemovalCandidateOnDiskError(
        f"percolate-round: removal side named {len(present)} path(s) that still "
        f"exist at {dest_root} -- refusing to delete any of them.\n"
        "    A removal candidate present on disk means the operands are wrong: it "
        "is published payload the declaration failed to name, not an orphan at "
        "HEAD. Widen `declared_payload` (AC2) rather than deleting the file.\n"
        + "".join(f"    ! {rel}\n" for rel in shown)
        + (f"    ... and {more} more\n" if more else "")
    )


def _already_committed_non_executable_scripts(
    repo_root: Path, staged: "list[str]"
) -> "list[str]":
    """Dest paths ALREADY COMMITTED at `100644` whose content opens `#!`.

    Without this the fix above only reaches files a round happens to be
    copying, and a mirror that already committed a script at `100644` stays
    stuck forever: the file no longer changes, so it never enters a pathspec
    again, while the mirror's CI `check-exec-bit` keeps failing every round and
    the durable fix at source has nothing left to cross. That is the state
    doe-claude-em's mirror was in after three rounds. Correcting it needs a
    write at the mirror, which the publish-mirror guard denies by design and
    correctly -- so the round, which is the sanctioned writer, has to do it.

    Converging, not recurring work: a path leaves this set permanently once its
    mode is recorded, and only `100644` entries are ever read.

    Cost, measured 2026-08-26 against the real OSS mirror (1484 tracked files,
    1411 at `100644`): one `git ls-files -s` process and 62.5 ms of process
    time for the 2-byte reads, on a leg already committing. It found exactly
    the one stuck file. Read against DR-344's 500ms end-to-end brightline
    before widening this: it is a whole-index scan, and a much larger mirror
    would want the read set narrowed rather than this budget quietly grown.
    """
    result = subprocess.run(
        ["git", "ls-files", "-s"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    already = set(staged)
    stuck = []
    for line in result.stdout.splitlines():
        if not line.startswith("100644 "):
            continue
        _, _, rel_path = line.partition("	")
        if not rel_path or rel_path in already:
            continue
        try:
            with open(repo_root / rel_path, "rb") as fh:
                if fh.read(2) == b"#!":
                    stuck.append(rel_path)
        except OSError:
            continue
    return stuck


def _stage_shebang_exec_bits(repo_root: "str | Path", pathspec: "list[str]") -> int:
    """Set mode `100755` IN THE DEST INDEX for every path in `pathspec` whose
    destination file opens with `#!`. Returns how many paths were named.

    WHY THE FILESYSTEM BIT IS NOT ENOUGH, which is the whole defect this
    closes. `publish_sync._restore_shebang_executable_bit` chmods the copied
    file on disk, and that is the module's only exec-bit mechanism. Both the
    source and the mirror run `core.fileMode=false`, so git ignores the
    filesystem bit entirely and the file lands `100644` however the source is
    recorded. The bit therefore reached mirrors only from hosts where
    `core.fileMode` happens to be true -- accidentally correct on macOS,
    silently wrong on Windows, and visible only when a NEW executable is
    published from the wrong host. Reported by doe-claude-em 2026-08-26 after
    three rounds self-blocked: the round committed locally and then failed its
    own mirror CI `check-exec-bit`, whose remediation ("run `git update-index
    --chmod=+x` in source and commit") was both already satisfied at source and
    unreachable at the mirror, since the publish-mirror guard correctly denies
    a direct write there. Nothing on the side the failure named could fix it.

    ONE PROCESS, BATCHED, NEVER PER FILE -- `git add --chmod=+x -- <paths>` in
    a single call for the whole set (the amplification gate at
    `coordinator_core/tests/test_no_unbatched_per_item_git_spawn.py` governs
    this loop). `add` rather than `update-index` because a newly published file
    is not in the index yet and `update-index --chmod` requires an existing
    entry; `add --chmod=+x` stages and sets the mode in the same operation. The
    commit leg's own `git add` that follows preserves the recorded 100755,
    because with `core.fileMode=false` git reuses the index mode rather than
    re-reading it off disk -- which is the same property that makes the
    on-disk chmod inert.

    FAILURE IS NOT A ROUND FAILURE, AND THAT COVERS RAISING, NOT ONLY A
    DECLINE. A path git refuses here (gitignored at dest, most likely) leaves
    the round exactly where it stands today, at `100644`, so this can only
    improve on the status quo and must never be the thing that fails a publish.
    The whole body is wrapped for the same reason: this step sits BETWEEN the
    pathspec derivation and the commit, so an exception escaping it leaves the
    dest synced with paths staged-but-uncommitted — a strictly worse failure
    class than the refusals around it, which all leave a state the next round
    simply re-derives. It raised exactly once, on 2026-08-26, when
    `_cmd_round_default` passed `_resolve_repo_root`'s `str` into a `Path /`
    expression and took a live round down at the commit leg (doe-claude-em).
    A best-effort mode fix has no business ending a publish.

    `repo_root` therefore takes `str` or `Path`: `_resolve_repo_root` returns
    `Optional[str]`, and coercing here rather than at the call site keeps a
    future caller from re-introducing the same crash.
    """
    try:
        root = Path(repo_root)
        shebang_paths = []
        for rel_path in pathspec:
            try:
                with open(root / rel_path, "rb") as fh:
                    if fh.read(2) == b"#!":
                        shebang_paths.append(rel_path)
            except OSError:
                continue
        shebang_paths.extend(
            _already_committed_non_executable_scripts(root, shebang_paths)
        )
        if not shebang_paths:
            return 0
        result = subprocess.run(
            ["git", "add", "--chmod=+x", "--"] + shebang_paths,
            cwd=str(root),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(
                f"percolate-round: could not set the executable bit on "
                f"{len(shebang_paths)} shebanged path(s) at dest "
                f"({result.stderr.strip()}); they land non-executable, as they did "
                "before this step existed.",
                file=sys.stderr,
            )
            return 0
        return len(shebang_paths)
    except Exception as exc:  # noqa: BLE001 - a best-effort mode fix never ends a publish
        print(
            f"percolate-round: executable-bit step failed ({exc!r}); shebanged "
            "paths land non-executable, as they did before this step existed. "
            "The commit continues.",
            file=sys.stderr,
        )
        return 0


_FILTER_DROP_LABELS = {
    "gitignored": "gitignored at dest",
    "absent_deletion": "deletion-intent(s) already absent at dest",
    "staging": "beneath a publish-staging directory",
}


def _no_filter_drops() -> Dict[str, int]:
    """The all-zero drop record, so every return path of
    `_filter_commit_pathspec` hands back the same shape and no caller has to
    branch on `None` before it can count. Keys are fixed
    (`_FILTER_DROP_LABELS`), never accreted at call sites: a class that is
    counted but has no label would reach the operator as a bare number."""
    return {name: 0 for name in _FILTER_DROP_LABELS}


def _partition_pathspec_for_commit(
    pathspec: "Sequence[str]", repo_root: str, head_tracked: "set"
) -> "Tuple[List[str], List[str], List[Dict[str, str]]]":
    """Split a commit pathspec into (present, tracked-deletions, declined).

    ABSENT-FROM-DISK IS TWO CASES, NOT ONE. A path can be missing from the
    worktree because it never existed there, or because it is TRACKED AT DEST
    HEAD and this round means to delete it -- the removal side's entire
    payload. Collapsing both into a decline made a round structurally
    incapable of carrying a removal: the file stayed at dest HEAD, returned as
    a removal candidate next round, and the round refused on its own backlog
    forever.

    `head_tracked` is the caller's `_dest_head_tree` read, passed in rather
    than taken here so the whole pathspec costs ONE spawn (§ that function's
    own AC4: "one process, never one per path").

    PATH FORM IS THE WHOLE DEFECT SURFACE, and is why this is a named function
    with its own tests rather than a loop inline in the round. Entries arrive
    DEST-RELATIVE and POSIX from `_filter_commit_pathspec` (§ its `rel_paths`),
    which is exactly the key form `_dest_head_tree` emits -- so a relative
    entry is already the key and must NOT be resolved. Resolving one against
    the process CWD (claude-klabauter's own repo, never the destination) puts every
    entry outside `repo_root`, so the membership test misses ALL of them and
    every tracked deletion declines. A total miss reads exactly like a working
    filter, which is how it shipped: measured on the coordinator-claude mirror
    2026-08-31, eight `bin/` deletions declined across three rounds while
    `git ls-tree HEAD` listed every one. Absolute entries are still accepted,
    for a caller that supplies them, without `resolve()`.

    Never raises, and never consults `.gitignore` -- the caller applies that
    filter to the returned `present` list separately.
    """
    present: "List[str]" = []
    deletions: "List[str]" = []
    declined: "List[Dict[str, str]]" = []
    for entry in pathspec:
        if (Path(repo_root) / entry).exists():
            present.append(entry)
            continue
        candidate = Path(entry)
        if candidate.is_absolute():
            try:
                rel = candidate.relative_to(Path(repo_root)).as_posix()
            except ValueError:
                rel = None
        else:
            rel = candidate.as_posix()
        if rel is not None and rel in head_tracked:
            deletions.append(entry)
        else:
            declined.append({
                "path": entry,
                "reason": (
                    "absent from the worktree AND untracked at dest HEAD, so "
                    "there is no deletion to commit (never existed, or already "
                    "removed by something other than a tracked deletion)"
                ),
            })
    return present, deletions, declined


def _filter_commit_pathspec(
    dest_root: Path, dest_root_norm: str, seen: dict, *, repo_root: Optional[str] = None
) -> Tuple[List[str], Dict[str, int]]:
    """Drops three benign-decline classes from the derived pathspec BEFORE it
    reaches the commit leg (`coordinator_core.git.commit.commit_paths`), so a
    real round no longer names 100+ paths
    it already knows cannot land (`_round_refusal_reason` gates the push on
    `declined_paths` being empty, so these otherwise-benign declines used to
    block the publish from ever pushing itself):

    - gitignored paths at dest (`.gitignore`-excluded content, e.g.
      `__pycache__/*.pyc`, must never be published — naming them is a
      derivation bug, not a legitimate change to land).
    - deletion-intents (`DELETE`/`REMOVE` tag) for a path that does not
      exist at dest in the worktree OR the index — the desired end state
      (absent) already holds, so there is nothing to commit.
    - anything beneath a publish-STAGING directory (§
      `surface.PUBLISH_STAGING_DIR_RE`, the same SSOT every walk prunes on).
      A staging directory is scratch a crashed round left behind; it is not
      payload any row declares. This filter is not hypothetical — 1,028 files
      of `coordinator/.bin.publish-staging-dsnce3r6.prior` reached the public
      mirror through this exact pathspec in round `eebf1c67`, because nothing
      between the change-line report and the commit knew what a staging
      directory was. They carried no identity findings (a `.prior` is a
      post-swap backup of already-transformed bytes), so this closes a
      cruft-in-the-payload hole, not a leak.

      Matched on DIRECTORY segments only, never the basename: a file named
      `x-publish-staging-y.py` is real payload, the same distinction
      `store.py` and `engine.run_parse_sweep` draw.

    Deliberately narrow: does NOT filter anything else. A path that
    genuinely should land and does not is the real failure mode here — an
    uncertain case is left in, so a real decline still surfaces via the
    commit leg's own report (`_declined_paths_from_stage`) rather than
    being silently swallowed here.

    Preserves AC7 provenance: filtering happens on the pathspec already
    derived from the real run's own reported change lines, never adding or
    substituting a `git status` survey.

    RETURNS `(kept, drops)`, never the bare list. `drops` is the per-class
    count of what this function removed, and it is returned rather than only
    printed because an empty `kept` is otherwise indistinguishable from a row
    that declared nothing: the caller's no-op branch read a filtered-to-empty
    pathspec and printed "real run reported no changed files", a statement
    about the ROW made on evidence about the FILTER. Same ruling as
    `_round_warnings` — a stderr line above a green verdict is not a report
    (DoE-claude memo 2026-08-26, percolate-round-passes-but-drops-every-
    removal); the count has to reach the verdict block.

    NEGATIVE SPEC — `drops` is not an error channel. Every class it counts is
    a legitimate drop (`git check-ignore` is index-aware, so an ignored path
    here is one `git add` would refuse without `-f`; a deletion-intent whose
    target is already absent has nothing to express; staging scratch is not
    payload). It exists so the round can NAME what it dropped, never so it
    can refuse on it.
    """
    import os

    if not seen:
        return [], _no_filter_drops()

    entries = list(seen.items())
    # `git check-ignore` always reads and echoes POSIX, forward-slash
    # relative paths regardless of host OS -- `os.path.relpath` on Windows
    # emits backslash-separated paths, which never byte-match either that
    # input contract or `ignored`'s output values. Canonicalizing to POSIX
    # here (rather than backslash-normalizing `ignored`) matches git's own
    # native form on every host, including POSIX ones where this is a no-op.
    rel_paths = [
        Path(os.path.relpath(abs_path, dest_root_norm)).as_posix() for abs_path, _ in entries
    ]
    ignored = _gitignored_dest_paths(str(dest_root), rel_paths)
    # `git check-ignore --stdin` only ever echoes a match drawn from what it
    # was fed -- once `rel_paths` and the values compared against `ignored`
    # share one canonical form (POSIX, above), `ignored` can only ever be a
    # subset of `rel_paths` by construction. A member of `ignored` absent
    # from `rel_paths` means that invariant broke -- exactly the silent-miss
    # shape this function exists to make loud rather than quietly filter
    # nothing, so it is a hard error rather than a fail-open warning: a
    # narrowed filter (missing a real gitignored path) risks committing
    # gitignored content into the mirror, the direction that corrupts it.
    _unmatched = ignored - set(rel_paths)
    if _unmatched:
        raise ValueError(
            "percolate-round: git check-ignore reported "
            f"{sorted(_unmatched)!r} as ignored, but none of these were in "
            "the pathspec entries it was asked about -- gitignore filtering "
            "is unreliable for this pathspec and must not proceed silently."
        )

    from coordinator_core.percolate.surface import (  # noqa: PLC0415 - lazy, engine-only path
        PUBLISH_STAGING_DIR_RE as _STAGING_RE,
    )

    def _under_staging_dir(rel_path: str) -> bool:
        return any(_STAGING_RE.search(part) for part in rel_path.split("/")[:-1])

    def _staging_drop(rel_path: str, tag: str) -> bool:
        """Decline staging content ENTERING the commit — never its removal.

        Direction is load-bearing. This filter exists to keep a crashed
        round's scratch out of the mirror, but a `DELETE`/`REMOVE` intent for
        a staging path is the opposite motion: the mirror shedding a
        directory that already got in. Dropping both directions makes an
        already-committed staging directory PERMANENTLY unremovable — every
        round stages its deletion and this filter puts it straight back.

        Measured, not hypothetical: after
        `.coordinator_core.publish-staging-4f5zkrth` was removed from the
        mirror's disk and index, 1,028 of its 4,045 files were still at HEAD
        one round later, because their deletions were filtered out here.
        """
        return _under_staging_dir(rel_path) and tag not in ("DELETE", "REMOVE")

    survivors = [
        (abs_path, tag, resolved_rel)
        for (abs_path, (tag, resolved_rel)), rel_path in zip(entries, rel_paths)
        if rel_path not in ignored and not _staging_drop(rel_path, tag)
    ]
    staging_dropped = sum(
        1
        for (_abs_path, (tag, _resolved_rel)), rel_path in zip(entries, rel_paths)
        if rel_path not in ignored and _staging_drop(rel_path, tag)
    )
    gitignored_dropped = len(entries) - len(survivors) - staging_dropped

    # One batched `git ls-files --error-unmatch` probe for every deletion-
    # intent still in play, instead of one spawn per row (§
    # `_dest_paths_exist`) -- same per-path verdict, one subprocess.
    delete_candidates = [
        resolved_rel for _, tag, resolved_rel in survivors if tag in ("DELETE", "REMOVE")
    ]
    exists_at_dest = _dest_paths_exist(str(dest_root), delete_candidates)

    kept: List[str] = []
    absent_deletion_dropped = 0
    for abs_path, tag, resolved_rel in survivors:
        if tag in ("DELETE", "REMOVE") and not exists_at_dest[resolved_rel]:
            absent_deletion_dropped += 1
            continue
        if repo_root:
            rel_to_repo_root = Path(os.path.relpath(abs_path, repo_root)).as_posix()
            if rel_to_repo_root == ".." or rel_to_repo_root.startswith("../"):
                # `abs_path` fell outside `repo_root` -- `repo_root` was not
                # actually this entry's git worktree root (§ `_resolve_repo_root`
                # docstring). Emitting it would hand the commit leg a
                # pathspec entry it can only ever reject.
                raise ValueError(
                    f"percolate-round: commit pathspec entry {abs_path!r} falls "
                    f"outside repo_root {repo_root!r} (resolved {rel_to_repo_root!r}) "
                    "-- repo_root is not this entry's git worktree root."
                )
            kept.append(rel_to_repo_root)
        else:
            kept.append(abs_path)

    drops = {
        "gitignored": gitignored_dropped,
        "absent_deletion": absent_deletion_dropped,
        "staging": staging_dropped,
    }
    if any(drops.values()):
        print(
            "percolate-round: filtered "
            f"{sum(drops.values())} path(s) from "
            "commit pathspec before commit -- "
            f"{gitignored_dropped} gitignored at dest, "
            f"{absent_deletion_dropped} deletion-intent(s) already absent "
            f"at dest, {staging_dropped} beneath a publish-staging directory.",
            file=sys.stderr,
        )
    return kept, drops


def _gitignored_dest_paths(dest: str, rel_paths: List[str]) -> set:
    """Which of `rel_paths` (dest-relative) `dest`'s own `.gitignore` would
    exclude, via `git check-ignore --stdin` (pure pattern matching, no
    filesystem stat -- works for a path that does not exist on disk, e.g. a
    deletion-intent). Returns an empty set on a probe failure (fail OPEN
    here: an undetermined gitignore state must not silently drop a path
    that should land; the containing commit step still surfaces any real
    problem).

    NUL-delimited on both legs (`-z`), never newline-delimited. `_run` opens
    the pipe in text mode, so a `\\n`-joined stdin is newline-translated to
    `\\r\\n` on Windows; `check-ignore` without `-z` splits on `\\n` alone and
    keeps the `\\r` as part of the pathname, then echoes it back C-quoted
    because it now contains a control character. Neither form byte-matches
    `rel_paths`, so every Windows round carrying a gitignored path (any
    `__pycache__/*.pyc`) tripped the caller's subset invariant and aborted
    between the real run and the commit. `-z` removes both hazards at once:
    there is no `\\n` in the payload for the pipe to translate, and `-z`
    output is never quoted."""
    if not rel_paths:
        return set()
    result = _run(
        ["git", "-C", dest, "check-ignore", "-z", "--stdin"],
        input="\0".join(rel_paths) + "\0",
        timeout=_GIT_PLUMBING_TIMEOUT_SECS,
    )
    if result.returncode not in (0, 1):
        return set()
    return {path for path in result.stdout.split("\0") if path}


# The single-item form (`_dest_path_exists`) was removed -- its only
# caller was its own one-line delegation to `_dest_paths_exist(dest,
# [rel])[rel]` (Review: coordinator:code-reviewer amp-review-s6 F4).
# `_dest_paths_exist` below is the sole entry point; a future single-item
# caller should call it with a one-element list directly rather than
# reintroduce the wrapper.

# Windows `CreateProcess` argv ceiling is ~32KB (measured live at
# reap-stale-subagent-sidecars.py::_tracked_paths -- 621047 bytes of
# pathspec argv, 19x over). `git ls-files` has no `--pathspec-from-file`
# support (verified live there too -- `error: unknown option`), so
# `_dest_paths_exist` chunks its own `-- <paths>` argv the same way rather
# than scoping to a directory (unlike `_tracked_paths`, this call needs a
# per-path verdict, not a subtree membership check, so directory-scoping
# isn't available here). Kept comfortably under the measured ceiling to
# leave room for the fixed `git -C <dest> ls-files --error-unmatch --`
# prefix and per-arg quoting overhead.
_LS_FILES_ARGV_BYTE_CAP = 28_000


def _chunk_paths_by_argv_bytes(
    paths: List[str], cap: int = _LS_FILES_ARGV_BYTE_CAP
) -> List[List[str]]:
    """Split `paths` into argv-sized chunks, each kept under `cap` bytes of
    UTF-8-encoded path text (a conservative proxy for actual argv bytes,
    which also carry OS-level quoting/separator overhead). Chunk boundaries
    never split a single path, and every input path lands in exactly one
    chunk, in order -- preserving per-path identity for the caller's
    per-row attribution."""
    chunks: List[List[str]] = []
    current: List[str] = []
    current_bytes = 0
    for path in paths:
        path_bytes = len(path.encode("utf-8")) + 1
        if current and current_bytes + path_bytes > cap:
            chunks.append(current)
            current = []
            current_bytes = 0
        current.append(path)
        current_bytes += path_bytes
    if current:
        chunks.append(current)
    return chunks


def _dest_paths_exist(dest: str, rels: List[str]) -> Dict[str, bool]:
    """Whether each of `rels` exists at `dest` in the worktree OR the
    index -- a deletion-intent for a path absent from both has nothing
    left to commit. A real, still-uncommitted deletion (the physical file
    already removed by Step 4's real publish) stays TRACKED in the index
    until the deletion itself is committed, so `git ls-files
    --error-unmatch` still reports it as existing -- only a path absent
    from BOTH worktree and index is treated as already gone.

    One `git ls-files --error-unmatch` spawn per argv-sized chunk
    (§ `_chunk_paths_by_argv_bytes`) of every `rel` still needing a git
    probe (absent from the worktree/symlink check), rather than one spawn
    per deletion-intent row.
    `git ls-files --error-unmatch` evaluates every named pathspec even when
    some are unmatched (an unmatched entry only ever adds an extra stderr
    line -- verified live, it never short-circuits the rest), so each
    chunk's stdout is exactly the subset of that chunk still tracked in the
    index; everything else asked about is confirmed gone from both
    worktree and index. Chunk boundaries never affect the result -- each
    `rel` is written into `result` exactly once, keyed by its own value,
    so attribution is exact across chunk boundaries.

    Fails OPEN exactly like the per-item form, per chunk: a returncode
    outside `{0, 1}` for a given chunk (not a git repo, dest missing, etc.)
    is an undetermined probe for THAT chunk only, and every `rel` in that
    chunk resolves to `True` (kept) rather than being silently dropped;
    other chunks are unaffected."""
    result: Dict[str, bool] = {}
    to_probe: List[str] = []
    for rel in rels:
        abs_path = Path(dest) / rel
        if abs_path.exists() or abs_path.is_symlink():
            result[rel] = True
        else:
            to_probe.append(rel)
    if not to_probe:
        return result
    tracked: set = set()
    for chunk in _chunk_paths_by_argv_bytes(to_probe, cap=_LS_FILES_ARGV_BYTE_CAP):
        probe = _run(
            ["git", "-C", dest, "ls-files", "--error-unmatch", "--"] + chunk,
            timeout=_GIT_PLUMBING_TIMEOUT_SECS,
        )
        if probe.returncode not in (0, 1):
            for rel in chunk:
                result[rel] = True
            continue
        tracked |= set(probe.stdout.splitlines())
    for rel in to_probe:
        if rel not in result:
            result[rel] = rel in tracked
    return result


# ---------------------------------------------------------------------------
# Step 2c — MEDIUM-hit count, scoped to the gating panel only.
#
# `scan-secrets` (percolate-gate.py::_cmd_scan_secrets) renders the MEDIUM
# tier as up to two panels: an informational Panel A (peer-repo-name reads,
# taken pre-transform — the scanner's own header states Phase-4 is the
# post-transform oracle, i.e. these are never gate input) and a Panel B
# ("surfaces to gate") that is the actual Step 3 gate input. Counting every
# `<path>:<line>:`-shaped line between the HIGH and LOW tier headers, as this
# function used to, sums both panels and over-counts by Panel A's size.
#
# The Panel A/B boundary is read via the stable, non-prose markers
# `percolate-gate.py` emits for this purpose
# (`_MEDIUM_PANEL_INFORMATIONAL_MARKER` / `_MEDIUM_PANEL_GATING_MARKER`),
# not by pattern-matching the human-facing header text, which is free to
# reword independently of this boundary. Only lines after the gating marker
# (and before LOW) are counted; Panel A, if rendered, is skipped entirely.
# ---------------------------------------------------------------------------

_SCAN_HIT_RE = re.compile(r"^\s*\S.*:\d+:\s")
_MEDIUM_PANEL_GATING_MARKER = "##SCAN-PANEL:GATING##"


def _count_medium_hits(scan_stdout: str) -> int:
    lines = scan_stdout.splitlines()
    high_idx: Optional[int] = None
    low_idx: Optional[int] = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if high_idx is None and stripped.startswith("HIGH ("):
            high_idx = i
        elif high_idx is not None and low_idx is None and stripped.startswith("LOW ("):
            low_idx = i
            break
    if high_idx is None or low_idx is None:
        return 0

    start_idx = high_idx + 1
    for i in range(high_idx + 1, low_idx):
        if lines[i].strip() == _MEDIUM_PANEL_GATING_MARKER:
            start_idx = i + 1
            break

    return sum(1 for line in lines[start_idx:low_idx] if _SCAN_HIT_RE.match(line))


def _count_drift_hits(drift_stdout: str) -> int:
    lines = drift_stdout.splitlines()
    anchor_idx: Optional[int] = None
    arrow_idx: Optional[int] = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if anchor_idx is None and stripped.startswith("anchor:"):
            anchor_idx = i
        elif anchor_idx is not None and stripped.startswith("-> Read each commit's diff"):
            arrow_idx = i
            break
    if anchor_idx is None or arrow_idx is None:
        return 0
    return max(0, arrow_idx - anchor_idx - 1)


# ---------------------------------------------------------------------------
# Step 6 summary counts (added / modified / removed), for the human-facing
# panels only — never fed back into any gate logic.
# ---------------------------------------------------------------------------

def _summarize_change_lines(change_lines: List[Tuple[str, str]]) -> Tuple[int, int]:
    """`(added_or_updated, removed)` for a run's own change lines.

    NO `modified` TERM, DELIBERATELY. There used to be one, counting
    `tag == "UPDATE"` -- a spelling the producer never emits. `real_changes`
    is built as `[("NEW", p) ...] + [("REMOVE", p) ...]`, because the
    manifest does not distinguish new-from-updated inside
    `added_or_updated`, so `modified` was structurally always zero and every
    published subject carried a literal `0 modified` that measured nothing.
    Sixty consecutive publishes read `N added, 0 modified`; the constant
    looked like a suspicious invariance worth investigating and was merely
    dead vocabulary (example-cockpit-repo-30 / doe-claude-em, 2026-09-04).

    It survived because this module's own tests hand-built `("UPDATE", ...)`
    tuples and asserted on the resulting counts -- validating a vocabulary
    the production path cannot produce. Do NOT reintroduce the term, and do
    NOT feed this function a synthetic `"UPDATE"` tag to make a test read
    nicer: the first name is `added_or_updated` precisely because the
    precision loss is real and the subject must not imply otherwise.
    """
    added_or_updated = sum(1 for tag, _ in change_lines if tag == "NEW")
    removed = sum(1 for tag, _ in change_lines if tag in ("DELETE", "REMOVE"))
    return added_or_updated, removed


def _partition_carried_changes(
    real_changes: List[Tuple[str, str]], pathspec: List[str]
) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str]]]:
    """Splits the real run's own change lines into the ones the derived
    commit pathspec actually carries and the ones it drops, so every
    downstream count can say which of the two it is counting.

    Both sides key on the same string: `_pathspec_from_manifest` builds each
    pathspec entry from `repo_root / rel` for a `rel` drawn from the SAME
    manifest that feeds `real_changes`, and `_filter_commit_pathspec` emits
    it back as a `repo_root`-relative POSIX path -- so the round-trip is
    identity for every path that survived filtering. `as_posix()` on both
    sides is the one normalization that costs nothing and protects the
    Windows leg, where a manifest path may still carry backslashes.

    A dropped entry is not an error: the three commit-safety filters
    (gitignored-at-dest, already-absent deletion-intent, beneath a
    publish-staging directory) and the gated-off removal side
    (`_REMOVAL_SIDE_ENABLED`) all legitimately drop paths. What is an error
    is reporting a dropped path as though it landed -- hence this split.
    """
    carried_keys = {Path(p).as_posix() for p in pathspec}
    carried: List[Tuple[str, str]] = []
    dropped: List[Tuple[str, str]] = []
    for tag, path in real_changes:
        (carried if Path(path).as_posix() in carried_keys else dropped).append((tag, path))
    return carried, dropped


def _source_sha_suffix() -> str:
    """`git_state.source_sha_suffix(_REPO_ROOT)` -- one definition shared with
    `publish.py`'s wrapper and, through `_round`, with `percolate-mirror.py`,
    so all three legs of mirror history stamp byte-identically. Rationale and
    the degrade contract live on the engine function.
    """
    _bootstrap_engine()
    from coordinator_core.git.git_state import source_sha_suffix  # noqa: PLC0415

    return source_sha_suffix(_REPO_ROOT)


def _build_commit_subject(
    target: str,
    real_changes: List[Tuple[str, str]],
    pathspec: List[str],
    *,
    deletion_paths: "Optional[Sequence[str]]" = None,
) -> str:
    """Two numbers, both labelled, never one presented as the other (see
    module-level defect this replaces): `real_changes` is publish.py's own
    OWN comparison of the transformed staging dir against dest's *working
    tree* (`filecmp.cmp(shallow=False)` in `_report_published_diff`) —
    genuine signal (it says how far dest content diverged from what publish
    just staged), but NOT what this round is about to commit -- `real_changes`
    is now built from the `RoundManifest` publish.py's real run persists
    (§ `_read_fresh_round_manifest`), never a re-parse of its stdout, but the
    two-numbers-never-blended shape below is unchanged. `pathspec` is what
    `_pathspec_from_manifest`/`_filter_commit_pathspec` already derived from
    that same manifest's `declared_payload` set compared against dest HEAD
    (not against `real_changes`' own worktree baseline), filtered for
    gitignored-at-dest, already-absent-deletion, and beneath-a-publish-
    staging-directory paths (§ `_filter_commit_pathspec`) — the honest count
    of paths this call is about to hand the commit leg
    (`coordinator_core.git.commit.commit_paths`).

    A commit message is fixed at commit-invocation time (it IS the `-m`
    argument), so this cannot wait for a post-commit landed-diff count
    the commit leg's own `CommitOutcome` does not report (see
    `_report_commit_residual` for the closest available post-commit
    signal, printed separately on stderr rather than folded in here).
    Reporting `pathspec`'s size as if it were "modified" would just move
    the same defect one step downstream if `pathspec` itself still runs
    near dest's full tree size (see this file's CRLF-normalization
    investigation note) — so both counts are named, never blended into a
    single misleading added/modified/removed triple.

    NEGATIVE SPEC — the added/modified/removed triple describes the CARRIED
    subset only (`_partition_carried_changes`), never all of `real_changes`.
    Sizing the triple off `real_changes` while the commit carries `pathspec`
    made the mirror's own PUBLIC git history assert changes that never
    landed: a real commit read "dest diverged on 646 added, 0 modified, 67
    removed" while carrying zero removals, because the removal side is gated
    off (`_REMOVAL_SIDE_ENABLED`) downstream of the count (DoE-claude memo
    2026-08-26, percolate-round-passes-but-drops-every-removal). A commit
    subject is the one report that outlives the round, so it states what the
    commit carries and names the remainder as not carried, rather than
    describing a comparison the commit did not act on.
    """
    carried, dropped = _partition_carried_changes(real_changes, pathspec)
    added_or_updated, removed = _summarize_change_lines(carried)
    # A REMOVAL REACHES THE PATHSPEC WITHOUT A CHANGE LINE, so counting only
    # `carried` under-reports it to zero. `real_changes` is this run's own
    # worktree comparison; the removal side derives from dest HEAD instead
    # (§ `_pathspec_from_manifest`) -- which is exactly what the divergence
    # warning means by "carried into the pathspec beyond what this run's own
    # worktree comparison reported". Measured on coordinator-claude
    # 2026-09-01: a commit carrying eight file deletions and 1,217 deleted
    # lines announced "0 removed" in its own subject, in the OSS mirror's
    # permanent history. Set difference, so a path that DOES carry a
    # DELETE/REMOVE change line is never counted twice.
    removed += len(set(deletion_paths or ()) - {path for _tag, path in carried})
    residual = (
        f"; {len(dropped)} reported change(s) not carried" if dropped else ""
    )
    return (
        f"percolate publish: {target} "
        f"({len(pathspec)} file(s) to commit; carries "
        f"{added_or_updated} added-or-updated, {removed} removed{residual})"
        f"{_source_sha_suffix()}"
    )


def _print_pathspec_surplus(
    target: str,
    real_changes: List[Tuple[str, str]],
    pathspec: List[str],
    deletion_paths: "Optional[Sequence[str]]",
) -> None:
    """Informational note when the pathspec carries MORE than this run's own
    change lines reported, with no intended change dropped.

    Not a warning and deliberately not counted as one -- see
    `_report_commit_residual`'s own early return. `real_changes` is the
    worktree comparison; a removal reaches the pathspec from the dest-HEAD
    comparison instead, so a round that deletes anything lands here BY
    CONSTRUCTION rather than by anomaly. Names the removals separately from
    the remainder so a reader can tell "this round deleted eight files" from
    "eight paths appeared that nothing in this run explains" -- the second is
    still worth an eye, and the two used to render identically.

    Silent when there is no surplus.
    """
    surplus = len(pathspec) - len(real_changes)
    if surplus <= 0:
        return
    removals = len(set(deletion_paths or ()) & set(pathspec))
    if removals:
        residue = surplus - removals
        breakdown = f"{removals} removal(s) this round carries"
        if residue > 0:
            breakdown += (
                f" and {residue} path(s) from an earlier round's "
                "declared-payload-vs-HEAD gap"
            )
    else:
        breakdown = (
            "stranded residue from an earlier round's declared-payload-vs-HEAD gap"
        )
    # Wording note: "<n> carried into the pathspec beyond this run's own
    # worktree comparison" is kept verbatim from the counted-warning this
    # replaced. `test_percolate_round.py :: test_report_commit_residual_
    # reports_pathspec_larger_than_real_changes` pins that phrase, and the
    # phrase is accurate -- so the register changes without breaking a pin
    # that is testing the right thing.
    print(
        f"percolate-round: {target} — {surplus} carried into the pathspec "
        f"beyond this run's own worktree comparison ({breakdown}). Every "
        "reported change is carried; this is not a warning.",
        file=sys.stderr,
    )


def _report_commit_residual(
    target: str,
    real_changes: List[Tuple[str, str]],
    pathspec: List[str],
    *,
    deletion_paths: "Optional[Sequence[str]]" = None,
) -> Optional[str]:
    """Surfaces, on stderr, the gap this module used to discard silently:
    `real_changes` is publish.py's own dest-working-tree comparison (see
    `_build_commit_subject`); `pathspec` is what actually gets named to
    the commit leg (`coordinator_core.git.commit.commit_paths`), now derived from
    `declared_payload` vs dest HEAD (§ `_pathspec_from_manifest`) rather than
    from `real_changes`' own worktree baseline. A round that reports a
    subject sized off `real_changes` while `pathspec` (or the eventual
    commit) is far smaller is exactly the defect this function originally
    existed to make loud rather than silent -- and the same divergence can
    now run the OTHER way: `pathspec` legitimately exceeds `real_changes`
    whenever it carries a prior round's stranded, synced-but-never-committed
    residue that `real_changes` (this run's own worktree comparison) has
    nothing left to report, because Step 4 already found the worktree
    matching the payload. Both directions are reported here as the same
    named gap, never blended into one count. No-op when the two already
    agree.

    RETURNS the one-line warning the round's own verdict block counts and
    renders, or `None` when there is nothing to report. Stderr alone was not
    enough: this function's whole purpose is to be "loud rather than
    silent", and a round that dropped 57 intended changes still printed a
    bare `PASS` with `Warnings: 0`, because nothing downstream of this print
    knew the gap existed (DoE-claude memo 2026-08-26,
    percolate-round-passes-but-drops-every-removal). The verdict is what an
    operator reads; a stderr line scrolled past above a green verdict is
    indistinguishable from a clean round.

    The returned line names the removal-side gate explicitly whenever the
    dropped set contains removals and `_REMOVAL_SIDE_ENABLED` is off — that
    was a KNOWN LIMITATION with a stale mirror as its visible consequence
    while the flag was off, and did not converge: every subsequent round
    re-reported and re-dropped the same set. AC1b landed (PM, 2026-08-26)
    and `_REMOVAL_SIDE_ENABLED` is now `True`, so this branch is dead in the
    shipped state; it stays correct for the case where the flag is ever
    flipped back.
    """
    carried, dropped = _partition_carried_changes(real_changes, pathspec)
    if not dropped and len(pathspec) >= len(real_changes):
        # NOTHING INTENDED WAS LOST, so this is not a warning. The equality
        # case always returned None; the pathspec-is-LARGER case did not, and
        # counted toward the round's `Warnings:` tally -- so a healthy round
        # that carried removals announced its own success in the register of a
        # warning (DoE, 2026-09-01, on the first round that carried deletions
        # at all). The asymmetry was an artefact of when this function was
        # written: a bigger pathspec could only mean stranded residue back
        # then, because the removal channel did not work. It is now the
        # ordinary shape of a round that deletes something. The informational
        # line still prints below either way; only the counted warning goes.
        _print_pathspec_surplus(target, real_changes, pathspec, deletion_paths)
        return None
    delta = len(real_changes) - len(pathspec)
    detail = f"{delta} not carried into the pathspec by filtering/containment/dedup"
    print(
        f"percolate-round: {target} — intent vs commit pathspec diverge: "
        f"{len(real_changes)} change line(s) reported by the real publish run vs "
        f"{len(pathspec)} path(s) named to the derived commit pathspec ({detail}).",
        file=sys.stderr,
    )
    # No `if not dropped` branch here: nothing dropped means every reported
    # change is in the pathspec, so the pathspec cannot be the smaller of the
    # two, and the surplus case returned above. Reaching this point always
    # means at least one intended change did not make it.
    dropped_removals = sum(1 for tag, _ in dropped if tag in ("DELETE", "REMOVE"))
    warning = (
        f"{len(dropped)} change(s) the real run reported were NOT committed "
        f"({len(carried)} of {len(real_changes)} carried)"
    )
    if dropped_removals and not _REMOVAL_SIDE_ENABLED:
        gate_note = (
            f"{dropped_removals} of them removal(s): the removal side is gated "
            "OFF (_REMOVAL_SIDE_ENABLED is False -- AC1b of docs/plans/"
            "2026-08-26-a-refused-round-strands-its-payload-forever.md landed "
            "and shipped it True by default; someone has flipped it back), so "
            "dest keeps files this round intended to delete and every "
            "subsequent round re-reports the same set"
        )
        print(f"percolate-round: {target} — {gate_note}.", file=sys.stderr)
        warning = f"{warning}; {gate_note}"
    return warning


# ---------------------------------------------------------------------------
# Step 7 — stop-on-first-failure rendering
# ---------------------------------------------------------------------------

_ROW_TALLY_RE = re.compile(r"Rows succeeded:\s*\d+/\d+.*")


def _extract_row_tally(stdout: str, stderr: str) -> Optional[str]:
    """Pulls publish.py's own `Rows succeeded: N/M (...)` line out of a Step
    4 real-run's combined output, for the round's own verdict line. Returns
    `None` if publish.py's output never printed one (e.g. it crashed before
    reaching its own summary) rather than fabricate a tally.
    """
    for text in (stdout, stderr):
        for line in text.splitlines():
            match = _ROW_TALLY_RE.search(line)
            if match:
                return match.group(0).strip()
    return None


def _print_step_failure(step: str, cmd: List[str], stderr: str) -> None:
    print(f"percolate-round: {step} failed.", file=sys.stderr)
    print(f"  command: {' '.join(cmd)}", file=sys.stderr)
    if stderr.strip():
        print("  stderr:", file=sys.stderr)
        for line in stderr.strip().splitlines():
            print(f"    {line}", file=sys.stderr)


def _declined_paths_from_stage(stage: object) -> "List[Dict[str, str]]":
    """Every path this round named that `explicit_stage()` declined to
    include in the commit set, paired with a human-readable reason — the
    never-silent-drop report the killed `scoped-git-commit` CLI used to
    render via its own `_declined_paths` (deleted with that CLI 2026-08-23,
    DR-344; ported here rather than imported, since the module that defined
    it no longer exists). Local, not shared: this is the one caller in this
    repo that still needs the decline-labelling shape post-kill.

    Scoped by construction: both `StageOutcome.missing_caller_paths` and
    `StageOutcome.ignored_caller_paths` are already filtered to paths THIS
    call's own `caller_paths` named (the commit leg above always passes
    `caller_paths=set(pathspec)`) — this function does not re-filter, it
    only labels the two buckets `explicit_stage()` already computed.

    Deliberately NOT exhaustive over every `StageOutcome.skipped` tag: a
    diverged path, an already-staged deletion, or a swept-rename source are
    NOT declines — each is still included in the commit set, just not via a
    fresh `git add` this call issued. `stage` may be `None` (a pipeline
    result built without ever reaching `explicit_stage()`) — degrades to
    `[]` rather than raising.
    """
    if stage is None:
        return []
    unverifiable = set(getattr(stage, "unverifiable_missing_caller_paths", ()) or ())
    declined: "List[Dict[str, str]]" = []
    for p in getattr(stage, "missing_caller_paths", ()) or ():
        if p in unverifiable:
            declined.append({
                "path": p,
                "reason": (
                    "could not be classified -- the rename/deletion probe(s) "
                    "this decision depends on did not answer, so absence was "
                    "assumed, not confirmed; re-run once git can be queried "
                    "reliably"
                ),
            })
        else:
            declined.append({
                "path": p,
                "reason": (
                    "not found in the worktree or index, and not attributable "
                    "to a deletion (never existed, or already removed by "
                    "something other than a tracked deletion)"
                ),
            })
    for p in getattr(stage, "ignored_caller_paths", ()) or ():
        declined.append({"path": p, "reason": "excluded by .gitignore"})
    return declined


def _partition_gitignored_declines(declined: list) -> "tuple[list, list]":
    """Splits the commit leg's own `declined_paths` (§
    `_declined_paths_from_stage`) into (material, gitignored).

    `_filter_commit_pathspec` already drops gitignored paths from the derived
    pathspec, but that filter reads dest state BEFORE the commit and cannot
    close the window after it: this machine runs coordinator tooling directly
    out of the publish mirror, so `__pycache__/*.pyc` reappears between the
    filter and the commit on any round long enough for a peer session to
    import a published module. A decline whose only cause is `.gitignore` is
    the desired end state (the path must never be published), so it must not
    refuse the round or block the push — gating on it made the publish
    permanently unpushable on a loaded box, which is the failure this
    partition removes. Every other decline reason stays material.
    """
    material: list = []
    gitignored: list = []
    for entry in declined:
        reason = str(entry.get("reason", "")) if isinstance(entry, dict) else ""
        (gitignored if "excluded by .gitignore" in reason else material).append(entry)
    return material, gitignored


def _round_refusal_reason(
    *,
    real_returncode: int,
    declined_paths: list,
    has_review_warnings: bool,
    ci_exit: Optional[int],
) -> Optional[str]:
    """Defence-in-depth predicate (C2, AC3) over `_cmd_round`'s own
    in-process state: every row succeeded, `declined_paths` is empty, no
    unacknowledged Phase 4 REVIEW warnings, and CI smoke came back green.
    Returns a reason string naming which condition refused, or `None` when
    every condition holds.

    A function over locals `_cmd_round` already holds — NOT a file, NOT a
    receipt, NOT a serialized envelope (see the originating plan's
    Anti-scope). `_cmd_round` already returns early on the first two
    conditions before control ever reaches this predicate's call site (a
    failed real run makes `publish.py` exit non-zero and returns FAIL; a
    non-empty `declined_paths` returns FAIL at the commit branch) — this
    predicate is cheap, honest defence-in-depth over state `_cmd_round`
    already holds, not a second enforcement path forced to fire at
    conditions unreachable at its own call site.
    """
    declined_paths, _ = _partition_gitignored_declines(declined_paths)
    if real_returncode != 0:
        return "the real publish run did not succeed"
    if declined_paths:
        return f"{len(declined_paths)} path(s) were declined during commit"
    if has_review_warnings:
        return "Phase 4 audit found unacknowledged REVIEW warnings"
    if ci_exit not in (None, 0):
        return f"CI smoke came back red (exit {ci_exit})"
    return None


def _filter_drop_warning(drops: Dict[str, int]) -> Optional[str]:
    """One verdict-block line naming what `_filter_commit_pathspec` removed,
    or `None` when it removed nothing.

    `_report_commit_residual` already warns when the real run's change lines
    and the derived pathspec DIVERGE, and it is blind to this exactly when it
    matters most: publish.py's change lines compare staging against dest's
    WORKING TREE, so once the copy has happened the two agree and
    `real_changes` is empty. A pathspec the filter emptied is then 0-vs-0 --
    agreement -- and the round reports a clean no-op. Two different reasons
    for zero, one indistinguishable verdict.

    This line is therefore keyed on the FILTER's own count, never on a
    comparison against another leg's zero.
    """
    if not any(drops.values()):
        return None
    named = ", ".join(
        f"{drops[name]} {label}" for name, label in _FILTER_DROP_LABELS.items() if drops[name]
    )
    return (
        f"{sum(drops.values())} declared path(s) were dropped from the commit "
        f"pathspec before the commit leg saw them ({named})"
    )


def _round_warnings(
    *,
    has_review_warnings: bool,
    residual_warning: Optional[str],
    filter_drop_warning: Optional[str] = None,
) -> List[str]:
    """Every condition that makes a round less than clean, collected in ONE
    place so the verdict block can both COUNT and NAME them. The count is
    what an operator reads: a round that dropped 57 intended changes printed
    a bare `PASS` with a zero warning count, because the only report of the
    drop was a stderr line scrolled past far above the verdict (DoE-claude
    memo 2026-08-26, percolate-round-passes-but-drops-every-removal).

    NEGATIVE SPEC — a warning here does NOT refuse the push.
    `_round_refusal_reason` owns refusal and is deliberately not fed from
    this list: the residual gap was a known, non-converging limitation for
    as long as the removal side was gated off (`_REMOVAL_SIDE_ENABLED`);
    refusing on it would have refused every round rather than surface
    anything. The flag is now `True` (AC1b landed, PM, 2026-08-26), so this
    path is dead in the shipped state, but if the flag is ever flipped back
    the same reasoning holds. Degrading `PASS` to `PASS-WITH-WARNINGS` is
    the whole intervention.
    """
    warnings: List[str] = []
    if has_review_warnings:
        warnings.append("Phase 4 audit found unacknowledged REVIEW warnings")
    if residual_warning:
        warnings.append(residual_warning)
    if filter_drop_warning:
        warnings.append(filter_drop_warning)
    return warnings


def _print_push_notice(target: str, *, refusal_reason: Optional[str] = None) -> None:
    """`--no-publish` and gate-refused terminal step. Prints the short push
    command; never runs it. Names `percolate-push.py` (coordinator/bin/),
    not a raw `git -C <abs-path> push` line — the entry point resolves the
    dest itself, so the operator types a target name, not an absolute path
    (state/handoffs/2026-08-13-one-command-publish.md, shape 2).

    `refusal_reason` is set only on the gate-refused path (a PASS-WITH-
    WARNINGS round whose review warnings `_round_refusal_reason` reads as
    refusing) — named here so the message reads as an explained refusal,
    not a silent failure to publish."""
    print("")
    if refusal_reason:
        print(f"Publish refused — {refusal_reason}. Push is the operator's step:")
    else:
        print("Publish committed. Push is the operator's step:")
    print("")
    print(f"    percolate-push {target}")


def _round_failure_marker_path(target: str, percolate_root: str) -> Path:
    """percolate_root-relative, same directory and naming convention as
    `<target>.lastsync` (percolate-gate.py) and `<target>.delta-state.json`
    (publish.py::_delta_state_path). MUST agree byte-for-byte with
    `percolate-push.py`'s own `_round_failure_marker_path` (C4's reader) —
    a mismatch is a hard refusal there, not a soft warning."""
    return Path(percolate_root) / "setup" / "percolate-state" / f"{target}.round-failed.json"


def _write_round_failure_marker(target: str, percolate_root: str, reason: str, sha: str) -> None:
    """PM ruling 1 (2026-08-14), polarity inverted (P2, review-integrator):
    written IMMEDIATELY once a commit lands at dest — before CI smoke and
    before the C2 gate — so `percolate-push.py`'s destination-state gate
    (C4) always sees a landed commit as uncertified by default. This closes
    the crash window a failure-only-write left open: a process death
    between the commit landing and a failure-path write (OOM, SIGKILL, host
    reboot — anywhere in CI smoke's subprocess call, potentially this
    module's longest-running step) used to leave a landed, uncertified
    commit with NO marker, which `percolate-push.py`'s gate reads as
    clean-with-commits-to-push and would publish. Writing the marker at
    commit time and clearing it ONLY on the clean-verdict path (right
    before publishing) fails safe: any crash after the commit leaves the
    marker standing. `reason` starts generic (`"uncommitted-verdict"`) at
    commit time and is overwritten with a specific one (`declined_paths`,
    `ci_red`) if the round reaches one of those branches. Additive-refusal
    only — never a claim a round WAS clean (Anti-scope)."""
    from datetime import datetime, timezone

    path = _round_failure_marker_path(target, percolate_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "reason": reason,
        "sha": sha,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    path.write_text(json.dumps(payload), encoding="utf-8", newline="\n")


def _clear_round_failure_marker(target: str, percolate_root: str) -> None:
    """Cleared right before a clean PASS/PASS-WITH-WARNINGS round publishes
    — never at the top of the round — so a round that itself fails again
    leaves a prior marker in place rather than clearing it prematurely."""
    path = _round_failure_marker_path(target, percolate_root)
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _dest_ahead_probe(dest: str) -> Tuple[Optional[int], bool, bool]:
    """Source of truth behind `_dest_ahead_count` (PM ruling,
    2026-08-14): distinguishes THREE states the collapsed `Optional[int]`
    return of `_dest_ahead_count` cannot — ahead-by-N, no-upstream
    (definite, not an error), and probe-failed (genuinely undetermined) —
    so a caller can treat the middle one differently from the third.

    Returns `(ahead, has_upstream, probe_ok)`:
      - `probe_ok=False`: the `git status` invocation errored or its
        `branch.ab` count was unparseable — `ahead` and `has_upstream`
        are meaningless; the caller cannot know either.
      - `probe_ok=True, has_upstream=False`: `dest`'s checked-out branch
        genuinely has no upstream tracking ref (git omits the
        `# branch.ab` line for this, same as detached HEAD) — a definite
        state, not an error. `ahead` is `None` here: there is no remote
        to be ahead of.
      - `probe_ok=True, has_upstream=True`: `ahead` is the definite
        ahead-of-remote commit count (may be 0).
    """
    result = _run(
        [
            "git", "-C", dest, "--no-optional-locks", "status",
            "--porcelain=v2", "--branch", "--untracked-files=normal",
        ],
        timeout=_GIT_PLUMBING_TIMEOUT_SECS,
    )
    if result.returncode != 0:
        return None, False, False
    has_upstream = False
    ahead: Optional[int] = None
    for line in result.stdout.splitlines():
        if line.startswith("# branch.ab "):
            has_upstream = True
            for token in line.split():
                if token.startswith("+"):
                    try:
                        ahead = int(token[1:])
                    except ValueError:
                        return None, True, False
    return ahead, has_upstream, True


def _dest_ahead_count(dest: str) -> Optional[int]:
    """How many local commits `dest`'s checked-out branch holds that its
    upstream does not, or `None` if that could not be determined (fails
    closed by never being treated as `0` — callers must not push on
    `None`).

    Git omits the `# branch.ab` line entirely when the checked-out branch
    has no upstream tracking ref (or `dest` is in detached HEAD) — that
    state is genuinely undetermined FOR PUSHING (there is no remote to
    push to), never "0 ahead" (§ Review below), so it must return `None`
    here too, the same as an outright probe failure — never silently fall
    through to the `ahead = 0` initializer. Callers needing to distinguish
    no-upstream from a genuine probe failure should call `_dest_ahead_probe`
    directly instead of this collapsed wrapper.
    """
    # Review: coordinatorcode-reviewer-c58be590 -- a missing `branch.ab`
    # line (no upstream tracking ref) previously fell through to the
    # `ahead = 0` initializer, indistinguishable from a real "+0" — every
    # consumer trusts `ahead == 0` to mean "in sync, nothing to push" and
    # prints exactly that to the operator.
    ahead, _has_upstream, probe_ok = _dest_ahead_probe(dest)
    return ahead if probe_ok else None


def _push_dest(dest: str) -> subprocess.CompletedProcess:
    return _run(["git", "-C", dest, "push"], timeout=_GIT_PUSH_TIMEOUT_SECS)


def _publish_unpushed_dest_commits(
    target: str, dest: str, percolate_root: str
) -> Tuple[bool, bool, str]:
    """AC2b's no-op-round leg for the DRY-RUN no-op branch, which returns
    before Step 4 ever acquires `_round_held_lock` — this helper acquires
    its own instance of that same lock (never called from inside an
    already-held one; `held_lock` is non-reentrant) so the push still runs
    under the concurrency guard. Checks whether `dest` already holds
    commits from an earlier round that stopped at the old print-and-stop
    terminus and pushes them if so — the one-command promise is that the
    mirror ends up live, not that this particular run produced bytes.

    Returns `(pushed, refused, message)`."""
    _bootstrap_engine()
    try:
        with _round_held_lock(
            Path(dest),
            holder_label=f"percolate-round:{target}",
            timeout=publish_contention_wait_secs(),
        ):
            ahead = _dest_ahead_count(dest)
            # Review: review-integrator — distinguish "the ahead-count probe
            # failed" from "genuinely zero commits ahead" (same defect class
            # already fixed on `percolate-push.py::_check_dest_state`'s side
            # of this seam, commit 7edcc4b8d): a probe failure must not be
            # reported to the operator as "already in sync", which is false
            # and sends them looking in the wrong place.
            if ahead is None:
                return (
                    False,
                    True,
                    f"could not determine whether dest '{dest}' has unpushed "
                    "commits (git status probe failed) — refusing to push "
                    "under an unknown state.",
                )
            if not ahead:
                return False, False, f"dest '{dest}' is already in sync with its upstream."
            _clear_round_failure_marker(target, percolate_root)
            push = _push_dest(dest)
            if push.returncode != 0:
                return False, True, f"push failed:\n{push.stderr.strip()}"
            return (
                True,
                False,
                f"pushed {ahead} unpushed commit(s) from an earlier round to {dest}.",
            )
    except _RoundLockTimeout as exc:
        return (
            False,
            True,
            _lock_busy_message(dest, exc),
        )


# ---------------------------------------------------------------------------
# Main sequence
# ---------------------------------------------------------------------------

def _cmd_round_default(
    args: argparse.Namespace,
    target: str,
    percolate_root: str,
    source_dir: str,
    dest: str,
    tmp: Path,
) -> int:
    """The round, PM ruling 2026-08-15: one sync, not two. Step 2's dry run
    is dropped entirely -- Step 1 IS the real `publish.py` run, and it
    materializes bytes into `dest` directly. Step 2 (leak scan) and Step 2b
    (inverse-drift) run against THAT run's own output (the leak scan reads
    SOURCE files either way, never dry-run output, so it never depended on a
    preceding dry run at all). The Step 3 gate -- same predicate, same
    inputs (touched-file count / MEDIUM leak hits / inverse-drift hits) --
    sits immediately before commit/push instead of before the sync: the
    sync into `dest` (a local git clone) is `git reset --hard HEAD && git
    clean -fd`-revertible, so a decline here leaves a synced-but-uncommitted
    `dest`, never a lost push.

    THAT REVERSIBILITY IS NOT UNIFORM ACROSS TIME, and the qualifier is
    load-bearing rather than pedantic. It holds for the bytes this round
    ADDED. It does not hold for removals already pending in the dest worktree
    from an earlier round: those paths exist nowhere but that worktree (§
    `_pending_removal_warning`), so the same command that neutralises this
    round's adds destroys them. Both decline paths below now name the count
    rather than printing the remedy as if it were free.

    The old `--dry-run-first` opt-in (a second, pre-sync materialization
    pass) was retired outright by a later PM ruling (2026-08-23, in-session
    -- "I don't want a dry run, I never asked for a dry run") rather than
    kept as an opt-in this driver still carries; `_cmd_round` now calls this
    function unconditionally, with no branch left to opt back into.

    Spec backlink: PM ruling 2026-08-15, in-session (percolate-round.py
    dry-run-optional dispatch).
    """
    _bootstrap_engine()
    real_stdout_path = tmp / "real-stdout.txt"
    scan_files_path = tmp / "scan-files.txt"

    try:
        with _round_held_lock(
            Path(dest),
            holder_label=f"percolate-round:{target}",
            timeout=publish_contention_wait_secs(),
        ):
            # --- Step 1: real run (sync) -- no dry run by default ----------
            print(f"=== percolate-round {target} — Step 1: real run (sync) ===")
            # `--no-commit`: this round owns the commit itself, as Step 5
            # below, so that DR-301's commit -> CI smoke -> push order holds
            # (§ this module's header). `publish.py` commits its own
            # successful percolation by default — correct for a bare
            # `coordinator-publish`, which otherwise exits 0 with green gates
            # and leaves the mirror dirty, but here it would move the commit
            # ahead of `_run_ci_smoke` and make this round's own commit leg a
            # no-op.
            real_cmd = [sys.executable, str(_PUBLISH), target, "--no-commit"]
            if not args.delta:
                real_cmd.append("--no-delta")
            import os as _os

            real_env = dict(_os.environ)
            real_env[_INHERITED_LOCK_ROOTS_ENV] = f"{_os.getpid()}={_os.path.realpath(dest)}"
            # Captured immediately before the spawn -- § `_read_fresh_round_
            # manifest`'s own docstring for why this is the freshness check
            # that makes deleting the destination-dirtiness gate safe.
            real_run_started_at = time.time()
            real = _run(real_cmd, timeout=_PUBLISH_LEG_TIMEOUT_SECS, env=real_env)
            print(real.stdout)
            _real_row_failure_text = (
                "Rows FAILED:" in real.stderr or "STATUS: PARTIAL" in real.stderr
            )
            if real.returncode == _EXIT_LOCK_BUSY and not _real_row_failure_text:
                # The child locks every root its rows resolve to; this round
                # only hands down the one for `dest`. A second root held by a
                # peer is that peer's queue, not this round's defect — carry
                # the distinction up rather than flattening it into FAIL.
                print(real.stderr, file=sys.stderr)
                return _EXIT_LOCK_BUSY
            if real.returncode != 0 or _real_row_failure_text:
                tally = _extract_row_tally(real.stdout, real.stderr)
                print("")
                print(f"percolate-round {target} — FAIL")
                if real.returncode != 0:
                    print(f"  real-run:  exit {real.returncode}")
                else:
                    print(
                        "  real-run:  exit 0, but reported failed row(s) "
                        "(exit-code/summary mismatch — treated as FAIL)"
                    )
                if tally is not None:
                    print(f"  rows:      {tally}")
                print("  ci-smoke:  skipped (Step 1 did not complete cleanly)")
                print("  push:      skipped")
                _print_step_failure("Step 1 (real run)", real_cmd, real.stderr)
                return _EXIT_FAIL
            has_review_warnings = "REVIEW WARNING" in real.stdout
            if has_review_warnings:
                print("Phase 4 audit found REVIEW items — acknowledge before next publish round:")
                for line in real.stdout.splitlines():
                    if "REVIEW WARNING" in line:
                        print(f"  {line.strip()}")

            real_stdout_path.write_text(real.stdout, encoding="utf-8", newline="\n")

            # --- scan-file-list build, off the real run's own output -------
            parse1 = _run_step(
                _PARSE_DRYRUN,
                [
                    "parse-dryrun",
                    "--stdout-file",
                    str(real_stdout_path),
                    "--source-dir",
                    source_dir,
                ],
            )
            if parse1.returncode != 0:
                _print_step_failure("percolate-parse-dryrun (pass 1)", [], parse1.stderr)
                return _EXIT_FAIL
            try:
                envelope1 = json.loads(parse1.stdout)
                scan_file_list = envelope1["preflight"]["step2c_scan_file_list"]
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                _print_step_failure(
                    "percolate-parse-dryrun (pass 1) — malformed envelope",
                    [],
                    f"{type(exc).__name__}: {exc}\nstdout:\n{parse1.stdout}",
                )
                return _EXIT_FAIL
            scan_files_path.write_text(
                "\n".join(scan_file_list) + ("\n" if scan_file_list else ""), encoding="utf-8", newline="\n"
            )

            # --- Step 2: content-leakage scan (reads SOURCE files) ---------
            print(f"=== percolate-round {target} — Step 2: content-leakage scan ===")
            identity_file = Path(percolate_root) / "setup" / ".percolate-identity"
            peer_repos_file = _resolve_central_state()
            scan_cmd = [
                "scan-secrets",
                "--files",
                str(scan_files_path),
                "--identity-file",
                str(identity_file),
                "--target",
                target,
                "--percolate-root",
                percolate_root,
            ]
            if peer_repos_file is not None:
                scan_cmd += ["--peer-repos-file", str(peer_repos_file)]
            scan = _run_step(_PERCOLATE_GATE, scan_cmd)
            print(scan.stdout)
            if scan.returncode == 2:
                print(
                    "percolate-round: HIGH-tier content leak detected — refusing to "
                    "commit/push (already synced to dest; revert with `git -C <dest> "
                    "reset --hard && git clean -fd` if desired)."
                    + _pending_removal_warning(dest),
                    file=sys.stderr,
                )
                return _EXIT_FAIL
            if scan.returncode != 0:
                _print_step_failure("Step 2 (scan-secrets)", list(scan.args), scan.stderr)
                return _EXIT_FAIL
            medium_count = _count_medium_hits(scan.stdout)

            # --- Step 2b: inverse-drift detection ---------------------------
            print(f"=== percolate-round {target} — Step 2b: inverse-drift detection ===")
            drift_cmd = [
                "inverse-drift",
                target,
                "--percolate-root",
                percolate_root,
                "--dest",
                dest,
                "--files",
                str(scan_files_path),
                "--source-dir",
                source_dir,
            ]
            drift = _run_step(_PERCOLATE_GATE, drift_cmd)
            print(drift.stdout)
            if drift.returncode != 0:
                _print_step_failure("Step 2b (inverse-drift)", list(drift.args), drift.stderr)
                return _EXIT_FAIL
            drift_count = _count_drift_hits(drift.stdout)

            # --- Step 3: gate-fire predicate + confirmation, sourced from the
            # real run's own output -- no second materialization -----------
            parse2 = _run_step(
                _PARSE_DRYRUN,
                [
                    "parse-dryrun",
                    "--stdout-file",
                    str(real_stdout_path),
                    "--source-dir",
                    source_dir,
                    "--medium-leak-count",
                    str(medium_count),
                    "--inverse-drift-count",
                    str(drift_count),
                ],
            )
            if parse2.returncode != 0:
                _print_step_failure("percolate-parse-dryrun (pass 2)", [], parse2.stderr)
                return _EXIT_FAIL
            try:
                envelope2 = json.loads(parse2.stdout)
                gate_fires = bool(envelope2["gates"]["step3_gate_fires"])
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                _print_step_failure(
                    "percolate-parse-dryrun (pass 2) — malformed envelope",
                    [],
                    f"{type(exc).__name__}: {exc}\nstdout:\n{parse2.stdout}",
                )
                return _EXIT_FAIL

            # --- resolve repo root + read the manifest publish.py's real run
            # just persisted (§ AC4/AC5) -- never a re-parse of its stdout ---
            repo_root = _resolve_repo_root(dest)
            if repo_root is None:
                print(
                    f"percolate-round: could not resolve git worktree root for "
                    f"dest '{dest}'.",
                    file=sys.stderr,
                )
                return _EXIT_FAIL

            manifest = _read_fresh_round_manifest(Path(repo_root), real_run_started_at)
            manifest_added = sorted(manifest.added_or_updated) if manifest is not None else []
            manifest_removed = sorted(manifest.removed) if manifest is not None else []
            # Drop-in replacement for the old stdout-derived `real_changes`:
            # same `List[Tuple[str, str]]` shape `_summarize_change_lines`/
            # `_report_commit_residual`/`_build_commit_subject` already
            # consume, so none of those three need to change. Only "NEW"/
            # "REMOVE" tags appear -- the manifest does not distinguish
            # new-from-updated within `added_or_updated` (a chosen precision
            # loss in the human-facing summary below, not a gate).
            real_changes = [("NEW", p) for p in manifest_added] + [
                ("REMOVE", p) for p in manifest_removed
            ]

            if gate_fires:
                evidence = ""
                for jp in envelope2.get("judgment_points", []):
                    if jp.get("id") == "jp_step3_percolate_confirmation_gate":
                        evidence = jp.get("evidence", "")
                print("")
                print(f"Step 3 gate fired: {evidence}")
                print(f"Change summary for target '{target}' (already synced to dest):")
                print(f"  added/updated: {len(manifest_added)}")
                print(f"  removed:       {len(manifest_removed)}")
                print("")
                print("First 10 paths:")
                for _tag, path in real_changes[:10]:
                    print(f"  {path}")
                if len(real_changes) > 10:
                    print(f"  ... ({len(real_changes) - 10} more)")
                print("")
                if args.yes:
                    print("Proceed with commit + publish? [y/N] y (--yes)")
                elif args.invocation_authorized:
                    print("Proceed with commit + publish? [y/N] y (--invocation-authorized)")
                elif sys.stdin.isatty():
                    answer = input("Proceed with commit + publish? [y/N] ").strip().lower()
                    if answer not in ("y", "yes"):
                        print("Publish cancelled.")
                        print(
                            f"percolate-round: dest '{dest}' already holds this round's "
                            "synced-but-uncommitted content -- revert with `git -C <dest> "
                            "reset --hard && git clean -fd`, or re-run to confirm and "
                            "commit it."
                            + _pending_removal_warning(dest)
                        )
                        return _EXIT_OK
                else:
                    print("Step 3 confirm required, no tty and no --invocation-authorized.")
                    print("Re-run in a terminal, or pass --yes / --invocation-authorized from an authorized caller.")
                    return _EXIT_CONFIRM_REQUIRED

            # --- pathspec build ----------------------------------------------
            pathspec, filter_drops = (
                _pathspec_from_manifest(manifest, repo_root)
                if manifest is not None
                else ([], _no_filter_drops())
            )
            filter_drop_warning = _filter_drop_warning(filter_drops)

            # --- Commit step -------------------------------------------------
            if not pathspec:
                # An empty pathspec has two causes and they are not the same
                # round. The filter emptying it is a report about the FILTER;
                # saying "the real run reported no changed files" there states
                # the other cause on this cause's evidence, and it is the
                # louder of the two -- publish.py copied the payload to dest
                # and the round then declared there was nothing to carry.
                #
                # Reporting only: this does NOT refuse. `_round_warnings`'
                # negative spec owns that call and the drops themselves are
                # each legitimate; what was wrong was the sentence, not the
                # outcome.
                if filter_drop_warning:
                    print(
                        f"percolate-round {target} — PASS-WITH-WARNINGS: every path "
                        "this round declared was removed by the commit-pathspec "
                        "filter, so there was nothing to commit. This is not a "
                        "round that declared nothing."
                    )
                    print("")
                    print("Summary:")
                    print("  real-run:  exit 0")
                    print("  ci-smoke:  n/a (nothing reached the commit leg)")
                    print("  warnings:  1")
                    print(f"    - {filter_drop_warning}")
                else:
                    print(f"percolate-round {target} — real run reported no changed files; nothing to commit.")
                    print("")
                    print("Summary:")
                    print("  real-run:  exit 0  (no-op)")
                    print("  ci-smoke:  n/a (no changes to verify)")
                if args.no_publish:
                    return _EXIT_OK
                ahead = _dest_ahead_count(dest)
                if ahead is None:
                    print("")
                    print(
                        f"percolate-round: could not determine whether dest "
                        f"'{dest}' has unpushed commits (git status probe "
                        "failed) — refusing to push under an unknown state.",
                        file=sys.stderr,
                    )
                    return _EXIT_FAIL
                if not ahead:
                    print("")
                    print(f"percolate-round: dest '{dest}' is already in sync with its upstream.")
                    return _EXIT_OK
                _clear_round_failure_marker(target, percolate_root)
                push = _push_dest(dest)
                print("")
                if push.returncode != 0:
                    print("percolate-round: push failed:", file=sys.stderr)
                    print(push.stderr.strip(), file=sys.stderr)
                    return _EXIT_FAIL
                print(
                    f"percolate-round: pushed {ahead} unpushed commit(s) from "
                    f"an earlier round to {dest}."
                )
                return _EXIT_OK

            # Partitioned BEFORE the subject is composed, not merely before the
            # commit: the subject's removed-count is only truthful if it can see
            # the deletion channel, and a removal reaches the pathspec from the
            # dest-HEAD comparison rather than from this run's change lines.
            head_tracked = _dest_head_tree(repo_root)
            present_paths, deletion_paths, declined_paths = (
                _partition_pathspec_for_commit(pathspec, repo_root, head_tracked)
            )
            residual_warning = _report_commit_residual(
                target, real_changes, pathspec, deletion_paths=deletion_paths
            )
            subject = _build_commit_subject(
                target, real_changes, pathspec, deletion_paths=deletion_paths
            )
            print(f"=== percolate-round {target} — commit ({len(pathspec)} file(s)) ===")
            pathspec_file_path = tmp / "commit-pathspec.txt"
            pathspec_file_path.write_text(
                "\n".join(pathspec) + "\n", encoding="utf-8", newline="\n"
            )
            # `scoped-git-commit` (the `ceremony.scoped_git_commit` CLI) was
            # killed 2026-08-23 (PM ruling, DR-344) — deleted, not suspended.
            # C3 (docs/plans/2026-08-29-the-push-subsystem-leaves-and-then-
            # the-pipeline-can-go.md): repointed off the killed
            # `commit_pipeline.run_commit_pipeline` onto the sanctioned
            # zero-spawn shape, `coordinator_core.git.commit.commit_paths`.
            # No `push_mode` to carry any more -- this round always owned its
            # own commit -> CI-smoke -> push sequence (DR-301) and ended this
            # step at a local commit; `commit_paths` has no push leg at all,
            # so `_push_dest` below still drives the push once CI smoke is
            # green, unchanged.
            from functools import partial  # noqa: PLC0415

            from coordinator_core.git.commit import (  # noqa: PLC0415
                CommitRefused,
                FilterUnsupported,
                commit_paths,
                hash_worktree_blobs_via_spawn,
            )
            from coordinator_core.ops.ceremony import git_native as _gn  # noqa: PLC0415
            from coordinator_core.ops.ceremony.commit_message import (  # noqa: PLC0415
                compose_message,
            )
            from coordinator_core.ops.session_context import (  # noqa: PLC0415
                resolve_current_session_id,
            )
            from coordinator_core.session import scope as session_scope  # noqa: PLC0415

            # Before the pipeline stages: record 100755 for shebanged dest
            # files. The on-disk chmod `publish_sync` performs is inert under
            # `core.fileMode=false` -- see `_stage_shebang_exec_bits`.
            executable_count = _stage_shebang_exec_bits(repo_root, pathspec)
            if executable_count:
                print(
                    f"percolate-round: staged {executable_count} shebanged path(s) "
                    "as executable at dest."
                )

            # `commit_paths` has no tolerant pre-stage: a missing or
            # gitignored path in `paths` is a hard `CommitRefused`, not a
            # silent decline the way `explicit_stage()` used to handle it.
            # Pre-filter here so the never-silent-drop `declined_paths`
            # report (`_declined_paths_from_stage`'s successor, below) still
            # fires, and so a gitignored dest artifact (`__pycache__/*.pyc`
            # reappearing between the pre-commit filter and this call) is
            # still excluded rather than committed.
            #
            ignore_result = _gn.check_ignore(repo_root, present_paths) if present_paths else None
            gitignored_set = set()
            if ignore_result is not None and ignore_result.ok:
                gitignored_set = {
                    m[3] for m in _gn.parse_check_ignore_stdin_z(ignore_result.stdout)
                }
            if gitignored_set:
                present_paths = [p for p in present_paths if p not in gitignored_set]
                declined_paths.extend(
                    {"path": p, "reason": "excluded by .gitignore"} for p in gitignored_set
                )

            declined_paths, gitignored_declines = _partition_gitignored_declines(declined_paths)
            if gitignored_declines:
                print(
                    f"percolate-round: {len(gitignored_declines)} path(s) declined as "
                    "gitignored at dest — not a round failure.",
                )

            commit_failed = False
            commit_diagnostics: List[str] = []
            sha = "?"
            try:
                if present_paths or deletion_paths:
                    # `commit_paths` documents a deletion-only commit as legal
                    # ("at least one of `paths` / `deleted_paths`"), so a round
                    # whose whole payload is removals now lands instead of
                    # reporting nothing to do.
                    outcome = commit_paths(
                        repo_root,
                        present_paths,
                        compose_message(subject=subject),
                        deleted_paths=deletion_paths,
                        blob_fallback=partial(hash_worktree_blobs_via_spawn, cwd=repo_root),
                    )
                    sha = outcome.sha
                    committed = True
                else:
                    committed = False
            except (CommitRefused, FilterUnsupported) as exc:
                commit_failed = True
                commit_diagnostics = [str(exc)]
                committed = False
            # REPORTED ON BOTH ARMS, DELIBERATELY. This report used to hang
            # off `committed` alone, so a round that committed NOTHING -- the
            # arm where the operator most needs to know WHY -- printed a bare
            # count and no reasons at all. Measured 2026-08-31: DoE grepped an
            # 878-line round log for every reason phrase this module can emit
            # and found none, because the only arm that renders them had not
            # run. Two decline reasons call for opposite operator actions
            # (re-run vs. report a derivation defect), so a count without a
            # reason is not a smaller report, it is an unactionable one.
            if declined_paths:
                landed = f"commit {sha[:12]} LANDED, but " if committed else ""
                print(
                    f"percolate-round: {landed}"
                    f"{len(declined_paths)} named path(s) were DECLINED and did "
                    "NOT land:",
                    file=sys.stderr,
                )
                for entry in declined_paths:
                    if isinstance(entry, dict):
                        path = entry.get("path", "?")
                        reason = str(entry.get("reason", "")).strip()
                        print(f"  {path} ({reason})" if reason else f"  {path}", file=sys.stderr)
                    else:
                        print(f"  {entry}", file=sys.stderr)
                # A commit that FAILED outright is the more specific fault and
                # keeps its own reporting arm below -- the declines are printed
                # above either way, but they must not swallow the diagnostics
                # that say the commit never happened.
                if not commit_failed:
                    _write_round_failure_marker(
                        target, percolate_root, "declined_paths", sha
                    )
                    return _EXIT_FAIL
            if commit_failed:
                _print_step_failure(
                    "commit (ceremony.commit_v2)",
                    [],
                    "; ".join(commit_diagnostics) or "commit_failed",
                )
                return _EXIT_FAIL

            # AC11 (docs/plans/2026-08-11-claim-release-and-the-gate-that-
            # cannot-clear.md) — this is a new production commit route and
            # claim release is wired per-route, never centrally in the
            # pipeline (`release_committed_claims` is called nowhere inside
            # `commit_pipeline.py`). Mirrors `post_commit_tail.py`'s own
            # post-commit release call: same fail-safe RETAIN direction (a
            # release failure must never fail a commit that already landed),
            # same "no sid to attribute to, skip explicitly" guard.
            release_sid = resolve_current_session_id(Path(repo_root))
            try:
                if release_sid:
                    session_scope.release_committed_claims(
                        release_sid, pathspec, cwd=str(repo_root)
                    )
            except Exception:
                print(
                    "percolate-round: release_committed_claims failed post-commit; "
                    "claim(s) retained.",
                    file=sys.stderr,
                )

            _write_round_failure_marker(
                target,
                percolate_root,
                "uncommitted-verdict",
                sha,
            )

            # --- Step 4: CI smoke (after the commit) ------------------------
            print(f"=== percolate-round {target} — Step 4: CI smoke ===")
            ci_script = Path(dest) / ".github" / "scripts" / "run-all-checks.py"
            ci_exit: Optional[int] = None
            if ci_script.is_file():
                python = _resolve_python()
                ci = _run(
                    [python, str(ci_script)],
                    cwd=dest,
                    timeout=_EXTERNAL_CI_TIMEOUT_SECS,
                )
                print(ci.stdout)
                if ci.stderr.strip():
                    print(ci.stderr, file=sys.stderr)
                ci_exit = ci.returncode
            else:
                print("  (no .github/scripts/run-all-checks.py at dest — skipped)")

            refusal_reason = _round_refusal_reason(
                real_returncode=real.returncode,
                declined_paths=declined_paths,
                has_review_warnings=has_review_warnings,
                ci_exit=ci_exit,
            )

            round_warnings = _round_warnings(
                has_review_warnings=has_review_warnings,
                residual_warning=residual_warning,
                filter_drop_warning=filter_drop_warning,
            )

            verdict = "PASS"
            if ci_exit not in (None, 0):
                verdict = "FAIL"
            elif round_warnings:
                verdict = "PASS-WITH-WARNINGS"

            print("")
            print(f"percolate-round {target} — {verdict}")
            print("  real-run:  exit 0")
            print(f"  ci-smoke:  {'exit ' + str(ci_exit) if ci_exit is not None else 'n/a (no run-all-checks.py)'}")
            print(f"  warnings:  {len(round_warnings)}")
            for warning in round_warnings:
                print(f"    - {warning}")

            if verdict == "FAIL":
                print("")
                print(f"percolate-round: publish refused — {refusal_reason}")
                print("CI smoke is red after the commit — the commit already landed locally;")
                print("fix the failure, then push by hand once CI is green. No push command")
                print("is printed for a red CI run.")
                _write_round_failure_marker(target, percolate_root, "ci_red", sha)
                return _EXIT_FAIL

            if refusal_reason is None:
                _clear_round_failure_marker(target, percolate_root)

            if args.no_publish or refusal_reason is not None:
                _print_push_notice(
                    target,
                    refusal_reason=None if args.no_publish else refusal_reason,
                )
                return _EXIT_OK

            push = _push_dest(dest)
            if push.returncode != 0:
                print("")
                print("percolate-round: push failed:", file=sys.stderr)
                print(push.stderr.strip(), file=sys.stderr)
                return _EXIT_FAIL
            print("")
            print(f"Published: pushed to {dest}.")
            return _EXIT_OK
    except _RoundLockTimeout as exc:
        print(f"percolate-round: {_lock_busy_message(dest, exc)}", file=sys.stderr)
        return _EXIT_LOCK_BUSY


def _cmd_round(args: argparse.Namespace) -> int:
    target = args.target

    percolate_root = _resolve_percolate_root(args.percolate_root)
    if percolate_root is None:
        return _EXIT_USAGE

    source_dir = _branch0_gate(target, percolate_root)
    if source_dir is None:
        return _EXIT_USAGE

    dest = _resolve_dest(target, percolate_root)
    if dest is None:
        return _EXIT_USAGE

    with tempfile.TemporaryDirectory(prefix="percolate-round-") as tmpdir:
        tmp = Path(tmpdir)
        return _cmd_round_default(args, target, percolate_root, source_dir, dest, tmp)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="percolate-round",
        description="Sequence a single-target percolate publish round: real sync through commit, CI smoke, and (on a clean round) push. --no-publish stops before the push instead.",
    )
    parser.add_argument("target", help="Single registered percolate target name.")
    parser.add_argument(
        "--percolate-root",
        required=False,
        help="Override PERCOLATE_ROOT (default: percolate-gate.py resolve-root).",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the interactive Step 3 confirmation prompt (gate-fire detection still runs).",
    )
    parser.add_argument(
        "--invocation-authorized",
        action="store_true",
        help=(
            "Skill/slash-command wrapper only: this invocation IS the Step 3 "
            "confirm. Never set on a bare human CLI run or an unattended caller."
        ),
    )
    parser.add_argument(
        "--no-publish",
        action="store_true",
        help="Opt out of the default publish-on-clean-round behaviour (DR-301); print the push command instead of running it.",
    )
    parser.add_argument(
        "--no-delta",
        dest="delta",
        action="store_false",
        default=True,
        help=(
            "Opt out of the default `--delta` publish.py invocation and force "
            "a full row re-derivation this round. --delta is on by default "
            "(PM ruling): it only skips a row publish.py can PROVE unchanged "
            "since its last successful publish (store+transform signature, "
            "source/dest HEAD, clean dest tree) -- a skip-WORK optimisation "
            "that never skips the end-of-run verification checks, which still "
            "scan the full destination unconditionally every round regardless "
            "of this flag (§ publish.py --delta help text)."
        ),
    )
    parser.set_defaults(func=_cmd_round)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    _bootstrap_engine()

    # Declare the publish lane before any argv-driven work. Historically this
    # covered every process this round spawned that could reach
    # `ceremony.scoped_git_commit` — the 2026-08-21 suspension roster turned
    # that op off and the ceremony budget caps it at 2s, neither number
    # written for a publish round (PM ruling 2026-08-21, DR-350). The commit
    # leg itself no longer reaches that op at all (§ C6, 2026-08-25:
    # re-pointed at `commit_pipeline.run_commit_pipeline` in-process, the
    # same bypass `publish.py::_commit_published_dests` already used) — this
    # declaration is retained for any OTHER process this round still spawns
    # that could reach a lane op (e.g. an engine subprocess resolving one via
    # `ipc.get_op_handler`), not for the commit leg. See
    # `coordinator_core.publish_lane` for why this is a closed list and a
    # boolean rather than a knob, and for the spawn count this bound
    # accommodates and does not fix.
    publish_lane.declare_lane()

    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
