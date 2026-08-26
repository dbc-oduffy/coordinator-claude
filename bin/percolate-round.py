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
so the commit leg calls `commit_pipeline.run_commit_pipeline` in-process
instead, mirroring `publish.py::_commit_published_dests` (2026-08-25).
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
leg (`commit_pipeline.run_commit_pipeline`, § C6, 2026-08-25) is derived from
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
does NOT edit `commit_pipeline.py` or `percolate-gate.py` (both
owned elsewhere — the commit leg below is a CALLER of
`commit_pipeline.run_commit_pipeline`, not an editor of it), does NOT drive
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
from typing import Dict, List, Optional, Tuple

_BIN_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _BIN_DIR.parent.parent

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_COORDINATOR_LIB = _BIN_DIR.parent / "lib"
if str(_COORDINATOR_LIB) not in sys.path:
    sys.path.insert(0, str(_COORDINATOR_LIB))

from coordinator_core.locked_write import (  # noqa: E402  type: ignore[import-not-found]
    LockTimeout as _RoundLockTimeout,
    CONTENDED_LOCK_WAIT_ENV as _CONTENDED_LOCK_WAIT_ENV,
    contended_lock_wait_secs as _round_lock_wait_secs,
    held_lock as _round_held_lock,
)
from percolate.wire_contract import (  # noqa: E402  type: ignore[import-not-found]
    INHERITED_LOCK_ROOTS_ENV as _INHERITED_LOCK_ROOTS_ENV,
)
from coordinator_core import publish_lane  # noqa: E402  type: ignore[import-not-found]
from coordinator_core.percolate.manifest import (  # noqa: E402  type: ignore[import-not-found]
    RoundManifest as _RoundManifest,
    read_manifest as _read_manifest,
)
from coordinator_core.percolate.round import (  # noqa: E402  type: ignore[import-not-found]
    default_manifest_path as _default_manifest_path,
)

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
    """One refusal line for a contended per-destination lock.

    Register (docs/wiki/guard-messaging.md): the fact is "a peer holds this
    dest and nothing was written"; the alternative is the wait knob. The old
    text read as a failure — it led with "could not acquire" and exited the
    same code as a broken round — so a session that needed a specific commit
    in a mirror would retry harder, spawning a fresh process per attempt
    against a queue that was never going to clear faster for the pressure.

    Negative-spec: does NOT advise retrying in a loop. Retrying is the
    behaviour this message exists to stop; waiting inside one process is what
    the knob buys.
    """
    return (
        f"dest '{dest}' is held by another round — waited "
        f"{_round_lock_wait_secs():.0f}s, nothing was written. Let it land and "
        f"re-run, or wait inside one process instead of retrying: "
        f"{_CONTENDED_LOCK_WAIT_ENV}=<seconds>. ({exc})"
    )


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
_ROUND_SCAN_LEG_TIMEOUT_SECS = 60.0

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
    result = _run(
        [sys.executable, str(_PERCOLATE_GATE), "resolve-root"],
        timeout=_REGISTRY_CLI_TIMEOUT_SECS,
    )
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
    if not _STATE_ROOT_RESOLVER.is_file():
        return None
    python = _resolve_python()
    result = _run(
        [python, str(_STATE_ROOT_RESOLVER), "--central"],
        timeout=_REGISTRY_CLI_TIMEOUT_SECS,
    )
    if result.returncode != 0:
        return None
    central = result.stdout.strip()
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
    result = _run(
        [sys.executable, str(_PERCOLATE_GATE), "branch0-gate", target, "--percolate-root", percolate_root],
        timeout=_REGISTRY_CLI_TIMEOUT_SECS,
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
    result = _run(
        [sys.executable, str(_PERCOLATE_GATE), "list-targets", "--percolate-root", percolate_root, "--target", target],
        timeout=_REGISTRY_CLI_TIMEOUT_SECS,
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
    manifest_path = _default_manifest_path(repo_root, "")  # round_id is not part of the path
    try:
        mtime = manifest_path.stat().st_mtime
    except OSError:
        return None
    if mtime < not_before:
        return None
    return _read_manifest(manifest_path)


_REMOVAL_SIDE_ENABLED = False
"""The HEAD-minus-declared-payload removal side stays OFF until AC1b proves
`declared_payload` equals the row's full payload (docs/plans/2026-08-26-a-
refused-round-strands-its-payload-forever.md § HARD CONSTRAINT).

Why this is a gate and not a flag anyone may flip: the removal rule is
`head_tree - declared_payload`, and BOTH operands are wider/narrower than
the rule assumes.

`head_tree` is every path dest HEAD tracks across the WHOLE mirror -- 8643
paths spanning all nine `claude-klabauter*` rows -- while `declared_payload`
carries only the rows this run actually processed. A `--target`-filtered
round, or any row `--delta` proved unchanged and skipped, therefore
contributes nothing to `declared_payload` while its files stay in
`head_tree`: the difference marks the entire rest of the mirror for
deletion.

`declared_payload` is itself narrower than the payload. C1 sources it from
`end_of_run_visited_by_repo_root`, fed by the post_rsync/inject sweeps,
which walk the percolation SURFACE (`surface.iter_surface_files`, which
takes `include_extensions`/`narrow_to_include_extensions`) -- publish.py's
own comment calls it "what was SCANNED, not what was PUBLISHED". A binary
or any non-transform-eligible payload file is tracked at HEAD, absent from
the declared set, and reads as "no row declares this".

Either operand alone turns this side from a fix into data loss, which is
strictly worse than the stranding the plan exists to fix. The add/modify
side is unaffected and ships now -- `git add` on an unchanged path is a
no-op, never data loss. Turning this on requires the AC1b measurement AND a
repo-root/row scoping of `head_tree`, not a one-line flip."""


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


def _pathspec_from_manifest(manifest: _RoundManifest, repo_root: str) -> List[str]:
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

    repo_root_path = Path(repo_root)
    repo_root_norm = os.path.normpath(str(repo_root_path))

    head_tree = _dest_head_tree(repo_root)
    diff_names = _dest_head_diff_names(repo_root)

    seen: dict = {}
    for rel in sorted(manifest.declared_payload):
        if rel not in head_tree or rel in diff_names:
            seen.setdefault(str(repo_root_path / rel), ("NEW", rel))
    if _REMOVAL_SIDE_ENABLED:
        for rel in sorted(head_tree - manifest.declared_payload):
            seen.setdefault(str(repo_root_path / rel), ("REMOVE", rel))
    return _filter_commit_pathspec(repo_root_path, repo_root_norm, seen, repo_root=repo_root)


def _filter_commit_pathspec(
    dest_root: Path, dest_root_norm: str, seen: dict, *, repo_root: Optional[str] = None
) -> List[str]:
    """Drops three benign-decline classes from the derived pathspec BEFORE it
    reaches the commit leg (`commit_pipeline.run_commit_pipeline`), so a real
    round no longer names 100+ paths
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
    """
    import os

    if not seen:
        return []

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

    survivors = [
        (abs_path, tag, resolved_rel)
        for (abs_path, (tag, resolved_rel)), rel_path in zip(entries, rel_paths)
        if rel_path not in ignored and not _under_staging_dir(rel_path)
    ]
    staging_dropped = sum(
        1
        for rel_path in rel_paths
        if rel_path not in ignored and _under_staging_dir(rel_path)
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

    if gitignored_dropped or absent_deletion_dropped or staging_dropped:
        print(
            "percolate-round: filtered "
            f"{gitignored_dropped + absent_deletion_dropped + staging_dropped} path(s) from "
            "commit pathspec before commit -- "
            f"{gitignored_dropped} gitignored at dest, "
            f"{absent_deletion_dropped} deletion-intent(s) already absent "
            f"at dest, {staging_dropped} beneath a publish-staging directory.",
            file=sys.stderr,
        )
    return kept


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

def _summarize_change_lines(change_lines: List[Tuple[str, str]]) -> Tuple[int, int, int]:
    added = sum(1 for tag, _ in change_lines if tag == "NEW")
    modified = sum(1 for tag, _ in change_lines if tag == "UPDATE")
    removed = sum(1 for tag, _ in change_lines if tag in ("DELETE", "REMOVE"))
    return added, modified, removed


def _build_commit_subject(
    target: str, real_changes: List[Tuple[str, str]], pathspec: List[str]
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
    (`commit_pipeline.run_commit_pipeline`).

    A commit message is fixed at commit-invocation time (it IS the `-m`
    argument), so this cannot wait for a post-commit landed-diff count
    the commit leg's own `PipelineResult` does not report (see
    `_report_commit_residual` for the closest available post-commit
    signal, printed separately on stderr rather than folded in here).
    Reporting `pathspec`'s size as if it were "modified" would just move
    the same defect one step downstream if `pathspec` itself still runs
    near dest's full tree size (see this file's CRLF-normalization
    investigation note) — so both counts are named, never blended into a
    single misleading added/modified/removed triple.
    """
    added, modified, removed = _summarize_change_lines(real_changes)
    return (
        f"percolate publish: {target} "
        f"({len(pathspec)} file(s) to commit; dest diverged on "
        f"{added} added, {modified} modified, {removed} removed)"
    )


def _report_commit_residual(
    target: str, real_changes: List[Tuple[str, str]], pathspec: List[str]
) -> None:
    """Surfaces, on stderr, the gap this module used to discard silently:
    `real_changes` is publish.py's own dest-working-tree comparison (see
    `_build_commit_subject`); `pathspec` is what actually gets named to
    the commit leg (`commit_pipeline.run_commit_pipeline`), now derived from
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
    """
    if len(real_changes) == len(pathspec):
        return
    delta = len(real_changes) - len(pathspec)
    if delta >= 0:
        detail = (
            f"{delta} not carried into the pathspec by filtering/containment/dedup"
        )
    else:
        detail = (
            f"{-delta} carried into the pathspec beyond what this run's own "
            "worktree comparison reported -- stranded residue from an earlier "
            "round's declared-payload-vs-HEAD gap, not new filtering"
        )
    print(
        f"percolate-round: {target} — intent vs commit pathspec diverge: "
        f"{len(real_changes)} change line(s) reported by the real publish run vs "
        f"{len(pathspec)} path(s) in the derived commit pathspec ({detail}).",
        file=sys.stderr,
    )


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
    try:
        with _round_held_lock(
            Path(dest),
            holder_label=f"percolate-round:{target}",
            timeout=_round_lock_wait_secs(),
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
    sync into `dest` (a local git clone) is fully `git reset --hard HEAD &&
    git clean -fd`-revertible, so a decline here leaves a synced-but-
    uncommitted `dest`, never a lost push.

    The old `--dry-run-first` opt-in (a second, pre-sync materialization
    pass) was retired outright by a later PM ruling (2026-08-23, in-session
    -- "I don't want a dry run, I never asked for a dry run") rather than
    kept as an opt-in this driver still carries; `_cmd_round` now calls this
    function unconditionally, with no branch left to opt back into.

    Spec backlink: PM ruling 2026-08-15, in-session (percolate-round.py
    dry-run-optional dispatch).
    """
    real_stdout_path = tmp / "real-stdout.txt"
    scan_files_path = tmp / "scan-files.txt"

    try:
        with _round_held_lock(
            Path(dest),
            holder_label=f"percolate-round:{target}",
            timeout=_round_lock_wait_secs(),
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
            parse1 = _run(
                [
                    sys.executable,
                    str(_PARSE_DRYRUN),
                    "parse-dryrun",
                    "--stdout-file",
                    str(real_stdout_path),
                    "--source-dir",
                    source_dir,
                ],
                timeout=_ROUND_SCAN_LEG_TIMEOUT_SECS,
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
                sys.executable,
                str(_PERCOLATE_GATE),
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
            scan = _run(scan_cmd, timeout=_ROUND_SCAN_LEG_TIMEOUT_SECS)
            print(scan.stdout)
            if scan.returncode == 2:
                print(
                    "percolate-round: HIGH-tier content leak detected — refusing to "
                    "commit/push (already synced to dest; revert with `git -C <dest> "
                    "reset --hard && git clean -fd` if desired).",
                    file=sys.stderr,
                )
                return _EXIT_FAIL
            if scan.returncode != 0:
                _print_step_failure("Step 2 (scan-secrets)", scan_cmd, scan.stderr)
                return _EXIT_FAIL
            medium_count = _count_medium_hits(scan.stdout)

            # --- Step 2b: inverse-drift detection ---------------------------
            print(f"=== percolate-round {target} — Step 2b: inverse-drift detection ===")
            drift_cmd = [
                sys.executable,
                str(_PERCOLATE_GATE),
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
            drift = _run(drift_cmd, timeout=_ROUND_SCAN_LEG_TIMEOUT_SECS)
            print(drift.stdout)
            if drift.returncode != 0:
                _print_step_failure("Step 2b (inverse-drift)", drift_cmd, drift.stderr)
                return _EXIT_FAIL
            drift_count = _count_drift_hits(drift.stdout)

            # --- Step 3: gate-fire predicate + confirmation, sourced from the
            # real run's own output -- no second materialization -----------
            parse2 = _run(
                [
                    sys.executable,
                    str(_PARSE_DRYRUN),
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
                timeout=_ROUND_SCAN_LEG_TIMEOUT_SECS,
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
                        )
                        return _EXIT_OK
                else:
                    print("Step 3 confirm required, no tty and no --invocation-authorized.")
                    print("Re-run in a terminal, or pass --yes / --invocation-authorized from an authorized caller.")
                    return _EXIT_CONFIRM_REQUIRED

            # --- pathspec build ----------------------------------------------
            pathspec = (
                _pathspec_from_manifest(manifest, repo_root) if manifest is not None else []
            )

            # --- Commit step -------------------------------------------------
            if not pathspec:
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

            _report_commit_residual(target, real_changes, pathspec)
            subject = _build_commit_subject(target, real_changes, pathspec)
            print(f"=== percolate-round {target} — commit ({len(pathspec)} file(s)) ===")
            pathspec_file_path = tmp / "commit-pathspec.txt"
            pathspec_file_path.write_text(
                "\n".join(pathspec) + "\n", encoding="utf-8", newline="\n"
            )
            # `scoped-git-commit` (the `ceremony.scoped_git_commit` CLI) was
            # killed 2026-08-23 (PM ruling, DR-344) — deleted, not suspended.
            # Re-pointed at `commit_pipeline.run_commit_pipeline` in-process
            # (2026-08-25), mirroring `publish.py::_commit_published_dests`
            # — same mechanism (the killed CLI was a trampoline over this
            # exact function), one fewer interpreter start, and no per-item
            # process amplification. `push_mode=PUSH_MODE_NEVER`: this round
            # owns its own commit -> CI-smoke -> push sequence (DR-301) and
            # ends this step at a local commit; `_push_dest` below drives the
            # push once CI smoke is green.
            import uuid  # noqa: PLC0415 - lazy, keeps this driver's import cost off every non-commit run

            from coordinator_core.ops.ceremony import commit_pipeline  # noqa: PLC0415
            from coordinator_core.ops.session_context import (  # noqa: PLC0415
                resolve_current_session_id,
            )
            from coordinator_core.session import scope as session_scope  # noqa: PLC0415

            pipeline_result = commit_pipeline.run_commit_pipeline(
                repo_root,
                session_id=f"percolate-round-{uuid.uuid4().hex}",
                subject=subject,
                stage_paths=pathspec,
                caller_paths=set(pathspec),
                push_mode=commit_pipeline.PUSH_MODE_NEVER,
            )
            sha = pipeline_result.committed_sha or ("(sha unverified)" if pipeline_result.sha_unverified else "?")
            declined_paths, gitignored_declines = _partition_gitignored_declines(
                _declined_paths_from_stage(pipeline_result.stage)
            )
            if gitignored_declines:
                print(
                    f"percolate-round: {len(gitignored_declines)} path(s) declined as "
                    "gitignored at dest — not a round failure.",
                )
            committed = pipeline_result.committed_sha is not None or pipeline_result.sha_unverified
            if committed and declined_paths:
                print(
                    f"percolate-round: commit {sha[:12]} LANDED, but "
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
                _write_round_failure_marker(target, percolate_root, "declined_paths", sha)
                return _EXIT_FAIL
            if pipeline_result.commit_failed:
                _print_step_failure(
                    "commit (run_commit_pipeline)",
                    [],
                    "; ".join(pipeline_result.diagnostics) or pipeline_result.reason or "commit_failed",
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

            verdict = "PASS"
            if ci_exit not in (None, 0):
                verdict = "FAIL"
            elif has_review_warnings:
                verdict = "PASS-WITH-WARNINGS"

            print("")
            print(f"percolate-round {target} — {verdict}")
            print("  real-run:  exit 0")
            print(f"  ci-smoke:  {'exit ' + str(ci_exit) if ci_exit is not None else 'n/a (no run-all-checks.py)'}")

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
