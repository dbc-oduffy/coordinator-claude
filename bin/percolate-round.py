"""percolate-round.py — one-command sequencer for a single-target percolate
publish round: dry-run -> parse -> scan-secrets -> inverse-drift -> Step 3
gate -> real run -> commit -> CI smoke -> push (on a clean round; DR-301).
`--no-publish` stops before the push, same as this module's old behaviour.

Ports the nine hand-driven steps `coordinator/skills/percolate/SKILL.md`
(DoE-claude) currently has the EM drive one CLI invocation at a time into a
single sequenced driver. Every step already has its own CLI
(`percolate-gate.py`, `percolate-parse-dryrun.py`, `publish.py`,
`scoped-git-commit`) — this module SEQUENCES them via subprocess, it does
not reimplement any of their logic. Single-target only: multi-target
(no-argument) round orchestration is explicitly out of scope (see the
originating plan's Out of scope section).

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

Commit-pathspec provenance (AC7): the pathspec passed to `scoped-git-commit`
is derived from the REAL publish run's OWN reported `NEW:`/`UPDATE:`/
`DELETE:`/`REMOVE:` lines (`_extract_change_lines`), never from a `git
status` survey of the destination. A change-line path that is a percolate-
engine rename SOURCE (reported on the same channel as a `RENAME:` line,
also parsed by `_extract_change_lines`) is resolved to its rename TARGET
before the pathspec entry is built (`_build_commit_pathspec`), so the
pathspec names only paths that exist post-transform
(docs/plans/2026-08-13-the-publish-round-commits-the-names-it-a.md § C2,
AC2). Every entry is a specific file path — these report lines never name a
directory — so the pathspec `scoped-git-commit` receives never contains a
directory element, satisfying both of `ceremony.scoped_git_commit`'s
by-design behaviours (directory pathspec refused; untracked files beneath a
directory never swept) by construction, without needing to touch that
module (see the originating plan's Substrate corrections § 1-2 for why
touching it would be wrong).

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
  --dry-run-first      Opt-in preview (PM ruling, 2026-08-15): runs Step 2's
                       dry-run pass before the real sync, the way every prior
                       round always did. OFF by default now: a round used to
                       pay the full ~1,800-file materialization twice (Step
                       2's dry run, then Step 4's real run) before writing a
                       single byte the operator actually keeps, even though
                       the sync into `dest` is a LOCAL git clone a `git reset
                       --hard HEAD && git clean -fd` fully reverts, and Step
                       2c's own leak scan reads SOURCE files (never dry-run
                       output). The Step 3 gate still fires on the same
                       inputs -- touched-file count, MEDIUM leak hits,
                       inverse-drift hits -- it is just sourced from the real
                       run's own change lines instead of a second
                       materialization, and now sits immediately before
                       commit/push (the one genuinely irreversible step)
                       rather than before the sync. Every verdict path
                       (PASS / PASS-WITH-WARNINGS / FAIL), `--yes`,
                       `--invocation-authorized`, `--no-publish`, and
                       `--reconcile-dest` behave identically either way.
                       Spec backlink: PM ruling 2026-08-15, in-session
                       (percolate-round.py dry-run-optional dispatch).
  --reconcile-dest      `refuse` (default, unchanged) or `discard`. A dirty
                       dest (crash-recovery pre-flight, `_dest_dirty_status`)
                       normally refuses the round outright; `discard` resets
                       dest to HEAD and removes untracked residue first
                       (`_reconcile_dest_discard`), refusing itself if dest
                       carries commits ahead of its remote. Opt-in only —
                       never implied by `--yes`, which answers the publish
                       confirmation and nothing else.

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
does NOT edit `scoped_git_commit.py` or `percolate-gate.py` (both
owned by a concurrent chunk of the same plan), does NOT drive Branch 0's
interactive first-run setup walk (a target that fails the branch0-gate
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
from pathlib import Path
from typing import List, Optional, Tuple

_BIN_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _BIN_DIR.parent.parent

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_COORDINATOR_LIB = _BIN_DIR.parent / "lib"
if str(_COORDINATOR_LIB) not in sys.path:
    sys.path.insert(0, str(_COORDINATOR_LIB))

from coordinator_core.locked_write import (  # noqa: E402  type: ignore[import-not-found]
    LockTimeout as _RoundLockTimeout,
    held_lock as _round_held_lock,
)
from percolate.wire_contract import (  # noqa: E402  type: ignore[import-not-found]
    INHERITED_LOCK_ROOTS_ENV as _INHERITED_LOCK_ROOTS_ENV,
)
from coordinator_core.percolate.rewrite_basename import (  # noqa: E402  type: ignore[import-not-found]
    RenameCycleError as _RenameCycleError,
    RenameManifest as _RenameManifest,
    RenameRecord as _RenameRecord,
)

GENERATES = []  # writes only round-failure markers and pushes commits under the resolved percolate `dest` (a foreign publish-mirror repo), never a fixed claude-klabauter-tracked path

_EXIT_OK = 0
_EXIT_FAIL = 1
_EXIT_USAGE = 2
_EXIT_CONFIRM_REQUIRED = 3

_PERCOLATE_GATE = _BIN_DIR / "percolate-gate.py"
_PARSE_DRYRUN = _BIN_DIR / "percolate-parse-dryrun.py"
_PUBLISH = _BIN_DIR / "publish.py"
_SCOPED_GIT_COMMIT = _BIN_DIR / "scoped-git-commit"
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

#: Per-leg subprocess bound. Per docs/wiki/machine-load-norm.md, a timeout
#: here means "slow", not "hung" — this box runs 50-70 concurrent LLM
#: sessions as its average, so a generous, non-aggressive bound is chosen
#: rather than one sized against an idle box. Overridable per call via
#: `timeout=` for a leg that needs a different bound.
# Review: review-integrator — bounds every one of `_run`'s 7+ call sites
# (dry run, parse-dryrun x2, scan-secrets, inverse-drift, real run, commit,
# CI smoke) so a hung child no longer blocks the round forever.
_SUBPROCESS_TIMEOUT_SECS = 600.0

#: The two `publish.py` legs are an order of magnitude heavier than the rest:
#: each walks the whole source tree, applies the rename transform into a fresh
#: staging root, and runs the per-row guard set over it — ~2400 files and ~1300
#: guard-scanned files for `claude-klabauter` — where the sibling legs shell out
#: to one `git` command apiece. A 2026-08-14 round was killed mid-real-run at the
#: shared bound with the publish already staged, so the shared value is not a
#: "slow, not hung" bound for these two; it is a false negative.
#: Spec backlink: state/audits/2026-08-14-the-real-blocker-is-the-mirrors-dirty-tree.md
_PUBLISH_LEG_TIMEOUT_SECS = 3600.0


def _run(cmd: List[str], **kwargs) -> subprocess.CompletedProcess:
    # Suppresses the console-window flash a headless Windows Bash spawn would
    # otherwise pop for every sibling-CLI invocation this driver makes.
    kwargs.setdefault("creationflags", getattr(subprocess, "CREATE_NO_WINDOW", 0))
    timeout = kwargs.pop("timeout", _SUBPROCESS_TIMEOUT_SECS)
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
        result = _run([machine_local, "get", "coordinator.python"])
        pin = result.stdout.strip()
        if result.returncode == 0 and pin:
            return pin

    return sys.executable


def _resolve_percolate_root(override: Optional[str]) -> Optional[str]:
    if override:
        return override
    result = _run([sys.executable, str(_PERCOLATE_GATE), "resolve-root"])
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
    result = _run([python, str(_STATE_ROOT_RESOLVER), "--central"])
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
        [sys.executable, str(_PERCOLATE_GATE), "branch0-gate", target, "--percolate-root", percolate_root]
    )
    if result.returncode != 0:
        print(f"percolate-round: target '{target}' is not ready for a round:", file=sys.stderr)
        print(result.stdout.strip(), file=sys.stderr)
        print(f"Run `/percolate {target}` once to walk first-run setup, then retry.", file=sys.stderr)
        return None
    stdout = result.stdout.strip()
    if not stdout.startswith("CONFIGURED:"):
        print(f"percolate-round: unexpected branch0-gate output: {stdout!r}", file=sys.stderr)
        return None
    return stdout[len("CONFIGURED:") :]


def _resolve_dest(target: str, percolate_root: str) -> Optional[str]:
    result = _run(
        [sys.executable, str(_PERCOLATE_GATE), "list-targets", "--percolate-root", percolate_root, "--target", target]
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
    result = _run(["git", "-C", dest, "--no-optional-locks", "rev-parse", "--show-toplevel"])
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return result.stdout.strip()


# ---------------------------------------------------------------------------
# Change-line parsing — shared by the dry-run gate prompt and the real-run
# commit-pathspec derivation. `publish.py` prints `NEW:`/`UPDATE:`/`DELETE:`/
# `REMOVE:` lines (two spellings of "removed" across its manifest-mode vs
# mirror-mode sync paths) with a dest-relative path, sometimes trailed by a
# parenthesised annotation (e.g. "(plugin.json — structural)") this parse
# strips. It also prints one `RENAME:` line per percolate-engine rename
# (old -> new, both dest-relative, § `publish.py::_report_rename_manifest`)
# — a distinct tag, parsed separately from the (tag, path) change lines
# rather than folded into them, since a rename pair names two paths, not one
# change (docs/plans/2026-08-13-the-publish-round-commits-the-names-it-a.md
# § Tasks C1/C2, AC1/AC2).
#
# `publish.py` also groups change lines into nested sub-blocks headed by a
# `  --- <subdir> ---` line, printing each member relative to that block at
# a deeper indent. A block stays open across lines by INDENT DEPTH alone —
# any line (header or change/rename line) whose own indent is
# shallower-or-equal to the current block-stack top's header indent pops
# that block (and, transitively, any block nested inside it) before the
# line is otherwise handled; a header is then pushed, a change line is
# prefixed with whatever remains open. This also covers a block dedenting
# straight back to a bare, already-fully-qualified change line with no
# closing header in between (observed in the real-run "Phase 4 audit"
# section, which reuses the same 2-space top-level indent but bakes any
# subdir straight into the printed path rather than nesting under a
# header) — the indent-based pop keeps that flat listing from inheriting a
# stale prefix left open by an earlier grouped section. Nesting is
# arbitrary depth, not just one level (docs/plans/2026-08-13-the-publish-
# round-commits-the-names-it-a.md § C4, AC8). `RENAME:` lines are already
# dest-relative and fully qualified (§ C1), so their own indent only
# participates in popping — never gets a block prefix applied.
# ---------------------------------------------------------------------------

_CHANGE_LINE_RE = re.compile(r"^(\s*)(NEW|UPDATE|DELETE|REMOVE):\s+(.+?)\s*$")
# The optional `[directory]` kind tag (§ publish.py `_report_rename_manifest`,
# 2026-08-14 fix) is a PREFIX on the `RENAME` keyword, not a trailing suffix
# on the path -- a suffix is a position a real `new_path` can occupy (a path
# literally ending in ` [directory]` would misparse as directory-kind, and
# an un-upgraded reader's old regex would silently fold a trailing tag into
# its captured path). A prefix can never be forged by path content, and
# this regex (anchored on `^\s*RENAME` with the tag consumed before the
# `:`) simply fails to match a `RENAME[directory]:` line emitted by a
# newer publish.py if this file predates the fix, rather than corrupting
# the path it extracts -- publish.py and percolate-round.py are one wire
# contract for this tag and upgrade together in the same commit. Captured
# as group 2 -- absent (group 2 is `None`) for a file-kind rename, whose
# line (`RENAME: old -> new`) is byte-identical to what this always printed.
_RENAME_LINE_RE = re.compile(r"^(\s*)RENAME(?:\[(directory)\])?:\s+(.+?)\s*->\s*(.+?)\s*$")
_TRAILING_ANNOTATION_RE = re.compile(r"\s+\([^()]*\)$")
_BLOCK_HEADER_RE = re.compile(r"^(\s*)---\s+(.+?)\s+---\s*$")
_TARGET_LINE_RE = re.compile(r"^\s*Target:\s+(.+?)\s*$")


def _extract_change_lines(
    stdout_text: str,
) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str, str]]]:
    """Returns `(changes, renames)` — `changes` is the existing (tag, path)
    list; `renames` is the separate list of (old, new, kind) triples parsed
    from `RENAME:` lines, kept apart rather than folded into `changes` since
    a rename pair is not itself a `(tag, path)` change line. `kind` is
    `'directory'` when the line carries the `RENAME[directory]:` prefix tag
    (§ `_RENAME_LINE_RE`, publish.py `_report_rename_manifest`), else
    `'file'` — the same default `RenameRecord.kind` itself carries, so an
    untagged (pre-existing, file-kind) line resolves identically to before
    this fix.

    A change line inside one or more open `  --- <subdir> ---` sub-blocks is
    prefixed with the joined block-stack chain before it is returned (§ C4).
    """
    from pathlib import PurePosixPath

    changes: List[Tuple[str, str]] = []
    renames: List[Tuple[str, str, str]] = []
    block_stack: List[Tuple[int, str]] = []  # (header indent depth, name)

    def _pop_to(indent: int) -> None:
        while block_stack and block_stack[-1][0] >= indent:
            block_stack.pop()

    for line in stdout_text.splitlines():
        header_match = _BLOCK_HEADER_RE.match(line)
        if header_match:
            indent = len(header_match.group(1))
            name = header_match.group(2).strip()
            _pop_to(indent)
            if name:
                block_stack.append((indent, name))
            continue
        rename_match = _RENAME_LINE_RE.match(line)
        if rename_match:
            indent = len(rename_match.group(1))
            _pop_to(indent)
            old, new = rename_match.group(3).strip(), rename_match.group(4).strip()
            kind = "directory" if rename_match.group(2) else "file"
            if old and new:
                renames.append((old, new, kind))
            continue
        match = _CHANGE_LINE_RE.match(line)
        if not match:
            continue
        indent = len(match.group(1))
        _pop_to(indent)
        tag, path = match.group(2), match.group(3)
        path = _TRAILING_ANNOTATION_RE.sub("", path).strip()
        if not path:
            continue
        if block_stack:
            prefix_parts = [name for _, name in block_stack]
            path = str(PurePosixPath(*prefix_parts, path))
        changes.append((tag, path))
    return changes, renames


# ---------------------------------------------------------------------------
# Row-dest attribution (§ C5, AC9). One `percolate-round.py <target>`
# invocation expands to MANY `publish.py` rows — a real round can process
# several registered targets sharing the invoked target's rename/scan
# machinery, each with its OWN dest. `publish.py` prints that dest once per
# row, on a `  Target: <abs path>` line under that row's own
# `=== <row-name> (mirror|flat-mirror) ===` header. Splitting the run's
# stdout on that line, BEFORE handing each segment to the unchanged
# `_extract_change_lines`, keeps AC7's provenance invariant intact (still
# derived from publish.py's own reported output, never a dest-tree survey)
# and resets C4's block stack at every row boundary for free — each segment
# gets its own `_extract_change_lines` call, so no open sub-block can leak a
# prefix across a row it was never printed under.
# ---------------------------------------------------------------------------


def _split_stdout_by_row_dest(
    stdout_text: str, fallback_dest: str
) -> List[Tuple[str, str]]:
    """Splits REAL-run stdout into per-row `(dest, chunk_text)` pairs keyed
    by each row's own reported `  Target:` line. `fallback_dest` covers any
    line preceding the first `Target:` line — a single-row run has no such
    line at all, so its whole stdout stays one chunk under `fallback_dest`,
    matching today's single-row behaviour byte-identically (§ C5 body)."""
    rows: List[Tuple[str, List[str]]] = [(fallback_dest, [])]
    for line in stdout_text.splitlines():
        target_match = _TARGET_LINE_RE.match(line)
        if target_match:
            rows.append((target_match.group(1).strip(), []))
            continue
        rows[-1][1].append(line)
    return [(row_dest, "\n".join(lines)) for row_dest, lines in rows]


def _build_commit_pathspec(
    dest: str,
    change_lines: List[Tuple[str, str]],
    rename_pairs: Optional[List[Tuple[str, str, str]]] = None,
    *,
    repo_root: Optional[str] = None,
) -> List[str]:
    """File paths under `dest`, de-duplicated in first-seen order. Every
    element names a specific file (never a directory) by construction — see
    this module's docstring § AC7.

    `repo_root` (§ docs/plans/2026-08-14-the-publish-round-commits-the-
    names-it-a.md follow-up, the 83-decline defect): when given, every
    returned entry is `repo_root`-relative instead of absolute. `dest` here
    is a single publish ROW's own reported `Target:` (§
    `_split_stdout_by_row_dest`), which for most `claude-klabauter*` rows is
    a `dest_subdir` BENEATH the actual commit target -- `repo_root` is that
    outer commit target, the same path the caller hands `scoped-git-commit`
    as `--repo`. `scoped_git_commit.commit_pipeline.explicit_stage`'s own
    deletion probes (`git_native.ls_files_deleted`,
    `diff_cached_name_status`) run with `cwd=worktree_root` (that same
    `--repo` value) and git prints their matches CWD-relative -- an ABSOLUTE
    pathspec entry can never equality-match a CWD-relative name, so every
    unstaged/staged deletion this call names was silently undetectable by
    those probes and fell through to `missing_caller_paths` (a benign,
    false decline) regardless of whether `_filter_commit_pathspec` correctly
    judged it still-live. Emitting `repo_root`-relative entries instead
    makes this call's own pathspec form match what those probes already
    compare against -- no `scoped-git-commit`/`commit_pipeline.py` change
    needed. `None` (the default) preserves the prior absolute-path form
    byte-for-byte, for any caller not naming an outer commit root.

    `rename_pairs` (old, new, kind — dest-relative, § `_extract_change_lines`)
    is reconstructed into a real `coordinator_core.percolate.rewrite_
    basename.RenameManifest` and resolved via ITS OWN `.resolve()` (never a
    hand-rolled prefix resolver here — § docs/plans/2026-08-14-publishing-
    runs-itself.md § C1: `resolve()` already handles the composed
    directory-rename-then-file-rename case a single-pass prefix match
    cannot, by looping until a pass produces no further change). An
    EXACT-key dict lookup (the pre-fix behaviour) can only ever match a
    rename-SOURCE path named byte-for-byte in the manifest — never a path
    living BENEATH a renamed directory, which is exactly why
    `declined_paths` was permanently non-empty before this fix: a directory
    rename is one manifest entry naming the directory, so no file beneath
    it ever matched. The resolved path is what gets joined to `dest` and
    containment-checked — the pathspec must name only paths that exist
    post-transform (AC2). A rename target that also appears as its own
    change line is not double-counted — de-duplication is on the resolved
    absolute path, same as today."""
    import os

    dest_root = Path(dest)
    dest_root_norm = os.path.normpath(str(dest_root))
    manifest = _RenameManifest(
        records=[
            _RenameRecord(old_path=old, new_path=new, kind=kind)
            for old, new, kind in (rename_pairs or [])
        ]
    )
    seen: dict = {}
    for _tag, rel in change_lines:
        # A cycle here (§ `RenameManifest.resolve`, `RenameCycleError`) is an
        # upstream rename-generation bug, never a resolvable path -- surfaced
        # loudly (a fatal error for this round) rather than silently falling
        # into the containment-check's "dropped from commit pathspec" path
        # below, which is reserved for a legitimately-resolved path that
        # merely lands outside `dest`.
        try:
            resolved_rel = manifest.resolve(rel)
        except _RenameCycleError as exc:
            raise _RenameCycleError(
                f'percolate-round: refusing to build a commit pathspec for '
                f'dest={dest!r} -- {exc}'
            ) from exc
        abs_path = dest_root / resolved_rel
        abs_path_norm = os.path.normpath(str(abs_path))
        # Review: code-reviewer — `rel` comes from publish.py's own stdout,
        # not directly agent/user-supplied, but nothing upstream guards
        # against a `../`-bearing value producing a pathspec entry outside
        # `dest`. Cheap containment check (no symlink resolution). This cuts
        # both ways: it avoids a false mismatch when a tmp dir itself sits
        # behind a symlink, but it also would NOT catch a real escape if
        # `dest` itself were a symlink out of the intended tree, or if a
        # change-line `rel` resolved through a symlinked intermediate
        # directory inside `dest` — normpath alone can't see either. Accepted
        # because `dest` comes from `percolate-gate.py list-targets`'s own
        # resolution, not attacker-controlled input.
        if abs_path_norm != dest_root_norm and not abs_path_norm.startswith(
            dest_root_norm + os.sep
        ):
            # Review: review-integrator — a miss here silently narrowed the
            # commit pathspec with no operator-visible signal; name the
            # dropped path so a real change is never excluded without a
            # trace (containment check itself is unchanged).
            print(
                f"percolate-round: dropped from commit pathspec (outside dest): "
                f"{rel!r} -> {abs_path_norm} (dest={dest_root_norm})",
                file=sys.stderr,
            )
            continue
        seen.setdefault(str(abs_path), (_tag, resolved_rel))
    return _filter_commit_pathspec(dest_root, dest_root_norm, seen, repo_root=repo_root)


def _filter_commit_pathspec(
    dest_root: Path, dest_root_norm: str, seen: dict, *, repo_root: Optional[str] = None
) -> List[str]:
    """Drops two benign-decline classes from the derived pathspec BEFORE it
    reaches `scoped-git-commit`, so a real round no longer names 100+ paths
    it already knows cannot land (`_round_refusal_reason` gates the push on
    `declined_paths` being empty, so these otherwise-benign declines used to
    block the publish from ever pushing itself):

    - gitignored paths at dest (`.gitignore`-excluded content, e.g.
      `__pycache__/*.pyc`, must never be published — naming them is a
      derivation bug, not a legitimate change to land).
    - deletion-intents (`DELETE`/`REMOVE` tag) for a path that does not
      exist at dest in the worktree OR the index — the desired end state
      (absent) already holds, so there is nothing to commit.

    Deliberately narrow: does NOT filter anything else. A path that
    genuinely should land and does not is the real failure mode here — an
    uncertain case is left in, so a real decline still surfaces via
    `scoped-git-commit`'s own report rather than being silently swallowed
    here.

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

    kept: List[str] = []
    gitignored_dropped = 0
    absent_deletion_dropped = 0
    for (abs_path, (tag, resolved_rel)), rel_path in zip(entries, rel_paths):
        if rel_path in ignored:
            gitignored_dropped += 1
            continue
        if tag in ("DELETE", "REMOVE") and not _dest_path_exists(str(dest_root), resolved_rel):
            absent_deletion_dropped += 1
            continue
        if repo_root:
            rel_to_repo_root = Path(os.path.relpath(abs_path, repo_root)).as_posix()
            if rel_to_repo_root == ".." or rel_to_repo_root.startswith("../"):
                # `abs_path` fell outside `repo_root` -- `repo_root` was not
                # actually this entry's git worktree root (§ `_resolve_repo_root`
                # docstring). Emitting it would hand `scoped-git-commit` a
                # pathspec entry it can only ever reject.
                raise ValueError(
                    f"percolate-round: commit pathspec entry {abs_path!r} falls "
                    f"outside repo_root {repo_root!r} (resolved {rel_to_repo_root!r}) "
                    "-- repo_root is not this entry's git worktree root."
                )
            kept.append(rel_to_repo_root)
        else:
            kept.append(abs_path)

    if gitignored_dropped or absent_deletion_dropped:
        print(
            "percolate-round: filtered "
            f"{gitignored_dropped + absent_deletion_dropped} path(s) from "
            "commit pathspec before commit -- "
            f"{gitignored_dropped} gitignored at dest, "
            f"{absent_deletion_dropped} deletion-intent(s) already absent "
            "at dest.",
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
    )
    if result.returncode not in (0, 1):
        return set()
    return {path for path in result.stdout.split("\0") if path}


def _dest_path_exists(dest: str, rel: str) -> bool:
    """Whether `rel` exists at `dest` in the worktree OR the index -- a
    deletion-intent for a path absent from both has nothing left to
    commit. A real, still-uncommitted deletion (the physical file already
    removed by Step 4's real publish) stays TRACKED in the index until the
    deletion itself is committed, so `git ls-files --error-unmatch` still
    reports it as existing -- only a path absent from BOTH worktree and
    index is treated as already gone.

    Fails OPEN, not closed: `git ls-files --error-unmatch` exits `1` only
    for a confirmed not-tracked path; any other non-zero (not a git repo,
    dest missing, etc.) is an undetermined probe, not a confirmed absence,
    and this returns `True` so the caller does not drop a path it could not
    actually verify is gone."""
    abs_path = Path(dest) / rel
    if abs_path.exists() or abs_path.is_symlink():
        return True
    tracked = _run(["git", "-C", dest, "ls-files", "--error-unmatch", "--", rel])
    if tracked.returncode == 1:
        return False
    return True


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
    just staged), but NOT what this round is about to commit. `pathspec` is
    what `_build_commit_pathspec`/`_filter_commit_pathspec` already derived
    from those same change lines, filtered for gitignored-at-dest and
    already-absent-deletion paths (§ `_filter_commit_pathspec`) — the
    honest count of paths this call is about to hand `scoped-git-commit`.

    A commit message is fixed at commit-invocation time (it IS the `-m`
    argument), so this cannot wait for a post-commit landed-diff count
    scoped-git-commit's own JSON result does not report (see
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
    `scoped-git-commit`. A round that reports a subject sized off
    `real_changes` while `pathspec` (or the eventual commit) is far
    smaller is exactly the defect this function exists to make loud
    rather than silent. No-op when the two already agree.
    """
    if len(real_changes) == len(pathspec):
        return
    print(
        f"percolate-round: {target} — intent vs commit pathspec diverge: "
        f"{len(real_changes)} change line(s) reported by the real publish run vs "
        f"{len(pathspec)} path(s) in the derived commit pathspec "
        f"({len(real_changes) - len(pathspec)} not carried into the pathspec by "
        "filtering/containment/dedup).",
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


def _dest_dirty_status(dest: str) -> Optional[str]:
    """Returns `dest`'s `git status --porcelain` output if non-empty (dest's
    working tree already carries uncommitted changes), or `None` if the
    tree is clean or its status could not be determined.

    This is a crash-recovery PRE-FLIGHT, NOT the concurrency guard against a
    peer round racing this one (debt entry f8e70de2991c,
    `state/debt-backlog/2026-08-13-percolate-round-has-no-guard-against-con-f8e70de2991c.yaml`).
    It runs once, before Step 4, on every round — it cannot detect a peer
    round landing mid-sequence, between this round's own Step 4 write and
    its commit. The concurrency guard is the `held_lock(dest)` `percolate-
    round`'s own `_cmd_round` now holds across that whole Step 4 -> commit
    span (state/audits/2026-08-13-percolate-round-race-repro.md); a reader
    should not mistake this function for that guard.

    Review: review-integrator — pre-flight for the crash-recovery gap: Step
    4's real publish write and the following scoped-commit are two
    unguarded subprocess calls, so a process death between them leaves
    `dest` mutated-but-uncommitted. The NEXT round's real run then diffs
    source against dest content, sees nothing new, takes the "nothing to
    commit" branch, and exits 0 PASS — silently stranding the earlier
    mutation. This check runs before Step 4 on every round, not just after a
    detected crash, so it also catches a dest dirtied by something other
    than this tool.

    Chosen behaviour: REFUSE, not reconcile. A prior mutation could be
    partial, unreviewed, or unrelated to this run's own real-run output —
    auto-committing it under this round's subject line would land
    unattributed changes under a misleading commit message. The considered
    alternative (auto-commit the orphaned dest state under its own
    "recovered from interrupted round" commit before proceeding) is a
    legitimate design and may be worth adding later, but folding it in here
    silently would decide a real tradeoff without the EM's sign-off; refuse
    and name the exact recovery step (`git -C <dest> status`, review, commit
    or discard by hand) instead.
    """
    result = _run(["git", "-C", dest, "--no-optional-locks", "status", "--porcelain"])
    if result.returncode != 0:
        # Can't determine dest's status — don't block the round over a
        # status-check failure the operator didn't cause; let the round
        # proceed and surface any real problem at the steps that follow.
        # Said out loud rather than returned bare: this check exists to stop a
        # round reporting PASS over an uncommitted mutation, so an
        # undetermined answer must not itself become a silent pass.
        print(
            f"  dest dirty-check: undetermined (git status exited "
            f"{result.returncode}) — proceeding unchecked",
            file=sys.stderr,
        )
        return None
    return result.stdout if result.stdout.strip() else None


def _reconcile_dest_discard(dest: str, dirty_status: str) -> Tuple[bool, str]:
    """Carries out the `refuse`-path's own named remedy (`--reconcile-dest=
    discard`): resets `dest` to its checked-out HEAD and removes untracked
    residue, but ONLY when that residue is safely reconstructible by the
    publish round that is about to run. `dest`'s generated publish output,
    wholesale-rewritten by every real run, is the safe case; anything a
    publish would NOT regenerate is not, and this function refuses rather
    than guess.

    `dest` carrying local commits its remote does not have
    (`_dest_ahead_count`) is NOT a refusal condition: a reset to HEAD never
    destroys commits, it only discards uncommitted working-tree and index
    state, so an unpushed commit survives this function's reset intact. The
    ahead count is reported in the returned message (not silently), so the
    operator sees it rather than being surprised; a probe failure (ahead
    count undeterminable) still refuses, since that failure could equally
    mean the discard itself cannot be evaluated safely.

    A dest with NO upstream tracking ref is a third, definite state (PM
    ruling, 2026-08-14) — distinct from a probe failure and, unlike it, NOT
    a refusal condition: `dest` simply has no remote counterpart yet (a
    fresh mirror, never pushed), and this function's reset/clean only ever
    discards uncommitted working-tree state regardless of upstream
    presence. That distinction is only resolvable via `_dest_ahead_probe`
    directly — `_dest_ahead_count` collapses no-upstream and probe-failure
    into the same `None`.

    NEVER touches the source repo — every git invocation here is `-C dest`.
    Returns `(ok, message)`: `message` is either the refusal reason (`ok`
    False) or an audit report naming the reset HEAD, any ahead-of-remote
    commit count (or the no-upstream state), and every discarded path,
    capped, with a total count (`ok` True) — printed by the caller, never
    silent either way."""
    ahead, has_upstream, probe_ok = _dest_ahead_probe(dest)
    if not probe_ok:
        return False, (
            "could not determine whether dest has commits ahead of its "
            "remote (git status probe failed) — refusing to discard under "
            "an unknown state."
        )

    head_result = _run(["git", "-C", dest, "--no-optional-locks", "rev-parse", "HEAD"])
    head_sha = head_result.stdout.strip() if head_result.returncode == 0 else "?"

    lines = [line for line in dirty_status.splitlines() if line.strip()]
    by_status: dict = {}
    paths: List[str] = []
    for line in lines:
        code = line[:2].strip() or line[:2]
        by_status[code] = by_status.get(code, 0) + 1
        paths.append(line[3:].strip())

    reset = _run(["git", "-C", dest, "reset", "--hard", "HEAD"])
    if reset.returncode != 0:
        return False, f"git reset --hard HEAD failed:\n{reset.stderr.strip()}"
    clean = _run(["git", "-C", dest, "clean", "-fd"])
    if clean.returncode != 0:
        return False, f"git clean -fd failed:\n{clean.stderr.strip()}"

    cap = 20
    shown = paths[:cap]
    path_report = "\n".join(f"    {p}" for p in shown)
    if len(paths) > cap:
        path_report += f"\n    ... ({len(paths) - cap} more)"
    counts_report = ", ".join(f"{code}: {n}" for code, n in sorted(by_status.items()))
    if not has_upstream:
        ahead_report = (
            "dest has no upstream tracking ref (no remote counterpart yet); "
            "discard proceeds.\n"
        )
    elif ahead:
        ahead_report = (
            f"dest is ahead of remote by {ahead} commit(s); reset to HEAD "
            "preserves them.\n"
        )
    else:
        ahead_report = ""
    message = (
        f"discarded {len(paths)} path(s), reset to HEAD {head_sha}:\n"
        f"{ahead_report}"
        f"  by status: {counts_report}\n"
        f"{path_report}"
    )
    return True, message


def _partition_gitignored_declines(declined: list) -> "tuple[list, list]":
    """Splits `scoped-git-commit`'s `declined_paths` into (material, gitignored).

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
    path.write_text(json.dumps(payload), encoding="utf-8")


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
    """Source of truth behind `_dest_ahead_count` and
    `_reconcile_dest_discard`'s permissive no-upstream path (PM ruling,
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
        ]
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
    no-upstream from a genuine probe failure (e.g.
    `_reconcile_dest_discard`, which may proceed permissively on
    no-upstream but must still refuse on a real probe failure) should call
    `_dest_ahead_probe` directly instead of this collapsed wrapper.
    """
    # Review: coordinatorcode-reviewer-c58be590 -- a missing `branch.ab`
    # line (no upstream tracking ref) previously fell through to the
    # `ahead = 0` initializer, indistinguishable from a real "+0" — every
    # consumer trusts `ahead == 0` to mean "in sync, nothing to push" and
    # prints exactly that to the operator.
    ahead, _has_upstream, probe_ok = _dest_ahead_probe(dest)
    return ahead if probe_ok else None


def _push_dest(dest: str) -> subprocess.CompletedProcess:
    return _run(["git", "-C", dest, "push"])


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
        with _round_held_lock(Path(dest), holder_label=f"percolate-round:{target}"):
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
            f"could not acquire the per-destination round lock for '{dest}' "
            f"(another round is running against this dest) — {exc}",
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
    """The default (no `--dry-run-first`) round, PM ruling 2026-08-15: one
    sync, not two. Step 2's dry run is dropped entirely -- Step 1 IS the
    real `publish.py` run, and it materializes bytes into `dest` directly.
    Step 2 (leak scan) and Step 2b (inverse-drift) run against THAT run's
    own output, same as before (the leak scan reads SOURCE files either
    way, never dry-run output, so it never depended on a preceding dry run
    at all). The Step 3 gate -- same predicate, same inputs
    (touched-file count / MEDIUM leak hits / inverse-drift hits), same
    verdict paths -- now sits immediately before commit/push instead of
    before the sync: the sync into `dest` (a local git clone) is fully
    `git reset --hard HEAD && git clean -fd`-revertible, so a decline here
    leaves a synced-but-uncommitted `dest`, never a lost push. See this
    module's own `--dry-run-first` help text for the full rationale.

    Spec backlink: PM ruling 2026-08-15, in-session (percolate-round.py
    dry-run-optional dispatch).
    """
    dirty_status = _dest_dirty_status(dest)
    if dirty_status is not None:
        if args.reconcile_dest == "discard":
            ok, message = _reconcile_dest_discard(dest, dirty_status)
            if not ok:
                print(
                    f"percolate-round: refusing to discard dest '{dest}' "
                    f"residue — {message}",
                    file=sys.stderr,
                )
                return _EXIT_FAIL
            print(f"percolate-round: {message}")
        else:
            print(
                f"percolate-round: dest '{dest}' already has uncommitted changes — "
                "a prior round may have crashed between its real run and commit. "
                "Retry with --reconcile-dest=discard to reset dest to HEAD and "
                "remove residue, or reconcile by hand (review, commit) first:",
                file=sys.stderr,
            )
            print(dirty_status, file=sys.stderr)
            return _EXIT_FAIL

    real_stdout_path = tmp / "real-stdout.txt"
    scan_files_path = tmp / "scan-files.txt"

    try:
        with _round_held_lock(Path(dest), holder_label=f"percolate-round:{target}"):
            # --- Step 1: real run (sync) -- no dry run by default ----------
            print(f"=== percolate-round {target} — Step 1: real run (sync) ===")
            real_cmd = [sys.executable, str(_PUBLISH), target]
            if args.delta:
                real_cmd.append("--delta")
            import os as _os

            real_env = dict(_os.environ)
            real_env[_INHERITED_LOCK_ROOTS_ENV] = f"{_os.getpid()}={_os.path.realpath(dest)}"
            real = _run(real_cmd, timeout=_PUBLISH_LEG_TIMEOUT_SECS, env=real_env)
            print(real.stdout)
            _real_row_failure_text = (
                "Rows FAILED:" in real.stderr or "STATUS: PARTIAL" in real.stderr
            )
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

            real_stdout_path.write_text(real.stdout, encoding="utf-8")

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
                ]
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
                "\n".join(scan_file_list) + ("\n" if scan_file_list else ""), encoding="utf-8"
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
            scan = _run(scan_cmd)
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
            drift = _run(drift_cmd)
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
                ]
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

            real_changes, real_renames = _extract_change_lines(real.stdout)
            added, modified, removed = _summarize_change_lines(real_changes)

            if gate_fires:
                evidence = ""
                for jp in envelope2.get("judgment_points", []):
                    if jp.get("id") == "jp_step3_percolate_confirmation_gate":
                        evidence = jp.get("evidence", "")
                print("")
                print(f"Step 3 gate fired: {evidence}")
                print(f"Change summary for target '{target}' (already synced to dest):")
                print(f"  added:    {added}")
                print(f"  modified: {modified}")
                print(f"  removed:  {removed}")
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

            # --- pathspec build --------------------------------------------
            repo_root = _resolve_repo_root(dest)
            if repo_root is None:
                print(
                    f"percolate-round: could not resolve git worktree root for "
                    f"dest '{dest}'.",
                    file=sys.stderr,
                )
                return _EXIT_FAIL

            pathspec_seen: dict = {}
            for row_dest, row_stdout in _split_stdout_by_row_dest(real.stdout, dest):
                row_changes, row_renames = _extract_change_lines(row_stdout)
                for entry in _build_commit_pathspec(
                    row_dest, row_changes, row_renames, repo_root=repo_root
                ):
                    pathspec_seen.setdefault(entry, None)
            pathspec = list(pathspec_seen.keys())

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
                "\n".join(pathspec) + "\n", encoding="utf-8"
            )
            commit_cmd = [
                sys.executable,
                str(_SCOPED_GIT_COMMIT),
                "-m",
                subject,
                "--repo",
                repo_root,
                "--json",
                "--pathspec-from-file",
                str(pathspec_file_path),
            ]
            commit = _run(commit_cmd)
            print(commit.stdout.strip())
            try:
                commit_result = json.loads(commit.stdout)
            except (json.JSONDecodeError, TypeError):
                commit_result = {}
            declined_paths, gitignored_declines = _partition_gitignored_declines(
                commit_result.get("declined_paths") or []
            )
            if gitignored_declines:
                print(
                    f"percolate-round: {len(gitignored_declines)} path(s) declined as "
                    "gitignored at dest — not a round failure.",
                )
            if commit_result.get("committed") and declined_paths:
                sha = commit_result.get("sha") or "?"
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
            if commit.returncode != 0:
                _print_step_failure("commit (scoped-git-commit)", commit_cmd, commit.stderr)
                return _EXIT_FAIL

            _write_round_failure_marker(
                target,
                percolate_root,
                "uncommitted-verdict",
                commit_result.get("sha") or "?",
            )

            # --- Step 4: CI smoke (after the commit) ------------------------
            print(f"=== percolate-round {target} — Step 4: CI smoke ===")
            ci_script = Path(dest) / ".github" / "scripts" / "run-all-checks.py"
            ci_exit: Optional[int] = None
            if ci_script.is_file():
                python = _resolve_python()
                ci = _run([python, str(ci_script)], cwd=dest)
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
                sha = commit_result.get("sha") or "?"
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
        print(
            f"percolate-round: could not acquire the per-destination round "
            f"lock for '{dest}' (another round is running against this "
            f"dest) — {exc}",
            file=sys.stderr,
        )
        return _EXIT_FAIL


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
        if not args.dry_run_first:
            return _cmd_round_default(args, target, percolate_root, source_dir, dest, tmp)

        dryrun_stdout_path = tmp / "dryrun-stdout.txt"
        scan_files_path = tmp / "scan-files.txt"

        # --- Step 2: dry run ---------------------------------------------
        print(f"=== percolate-round {target} — Step 2: dry run ===")
        dryrun_cmd = [sys.executable, str(_PUBLISH), "--dry-run", target]
        if args.delta:
            dryrun_cmd.append("--delta")
        dryrun = _run(
            dryrun_cmd,
            timeout=_PUBLISH_LEG_TIMEOUT_SECS,
        )
        dryrun_stdout_path.write_text(dryrun.stdout, encoding="utf-8")
        print(dryrun.stdout)
        if dryrun.returncode != 0:
            _print_step_failure("Step 2 (dry run)", dryrun_cmd, dryrun.stderr)
            return _EXIT_FAIL

        # --- percolate-parse-dryrun pass 1 (scan-file-list build) --------
        parse1 = _run(
            [
                sys.executable,
                str(_PARSE_DRYRUN),
                "parse-dryrun",
                "--stdout-file",
                str(dryrun_stdout_path),
                "--source-dir",
                source_dir,
            ]
        )
        if parse1.returncode != 0:
            _print_step_failure("percolate-parse-dryrun (pass 1)", [], parse1.stderr)
            return _EXIT_FAIL
        try:
            envelope1 = json.loads(parse1.stdout)
            preflight = envelope1["preflight"]
            scan_file_list = preflight["step2c_scan_file_list"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            # Review: review-integrator — route a malformed/schema-mismatched
            # envelope through this module's own failure register instead of
            # an uncaught traceback (exit code still lands on 1 by accident
            # today; this makes the step name and cause explicit too).
            _print_step_failure(
                "percolate-parse-dryrun (pass 1) — malformed envelope",
                [],
                f"{type(exc).__name__}: {exc}\nstdout:\n{parse1.stdout}",
            )
            return _EXIT_FAIL
        scan_files_path.write_text("\n".join(scan_file_list) + ("\n" if scan_file_list else ""), encoding="utf-8")

        # --- Step 2c: content-leakage scan --------------------------------
        print(f"=== percolate-round {target} — Step 2c: content-leakage scan ===")
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
            # Without this, scan-secrets' MEDIUM split (transform-covered
            # vs. not) silently doesn't happen -- it degrades to the old
            # unsplit panel rather than failing, so a caller that forgets
            # this flag gets no error, just a worse panel. See C1
            # (coordinator/bin/percolate-gate.py, same plan).
            "--percolate-root",
            percolate_root,
        ]
        if peer_repos_file is not None:
            scan_cmd += ["--peer-repos-file", str(peer_repos_file)]
        scan = _run(scan_cmd)
        print(scan.stdout)
        if scan.returncode == 2:
            print("percolate-round: HIGH-tier content leak detected — aborting before Step 3.", file=sys.stderr)
            return _EXIT_FAIL
        if scan.returncode != 0:
            _print_step_failure("Step 2c (scan-secrets)", scan_cmd, scan.stderr)
            return _EXIT_FAIL
        medium_count = _count_medium_hits(scan.stdout)

        # --- Step 2d: inverse-drift detection -----------------------------
        print(f"=== percolate-round {target} — Step 2d: inverse-drift detection ===")
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
        drift = _run(drift_cmd)
        print(drift.stdout)
        if drift.returncode != 0:
            _print_step_failure("Step 2d (inverse-drift)", drift_cmd, drift.stderr)
            return _EXIT_FAIL
        drift_count = _count_drift_hits(drift.stdout)

        # --- Step 3: gate-fire predicate + confirmation -------------------
        parse2 = _run(
            [
                sys.executable,
                str(_PARSE_DRYRUN),
                "parse-dryrun",
                "--stdout-file",
                str(dryrun_stdout_path),
                "--source-dir",
                source_dir,
                "--medium-leak-count",
                str(medium_count),
                "--inverse-drift-count",
                str(drift_count),
            ]
        )
        if parse2.returncode != 0:
            _print_step_failure("percolate-parse-dryrun (pass 2)", [], parse2.stderr)
            return _EXIT_FAIL
        try:
            envelope2 = json.loads(parse2.stdout)
            gate_fires = bool(envelope2["gates"]["step3_gate_fires"])
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            # Review: review-integrator — same rationale as pass 1's envelope
            # read above.
            _print_step_failure(
                "percolate-parse-dryrun (pass 2) — malformed envelope",
                [],
                f"{type(exc).__name__}: {exc}\nstdout:\n{parse2.stdout}",
            )
            return _EXIT_FAIL

        dryrun_changes, _dryrun_renames = _extract_change_lines(dryrun.stdout)
        added, modified, removed = _summarize_change_lines(dryrun_changes)

        if added == 0 and modified == 0 and removed == 0:
            print(f"percolate-round {target} — PASS (no-op): nothing to publish.")
            print("")
            print("Summary:")
            print(f"  dry-run:   exit 0  (0 files)")
            print("  real-run:  skipped (no-op)")
            print("  ci-smoke:  n/a (no changes to verify)")
            if args.no_publish:
                return _EXIT_OK
            pushed, refused, message = _publish_unpushed_dest_commits(target, dest, percolate_root)
            print("")
            print(f"percolate-round: {message}")
            return _EXIT_FAIL if refused else _EXIT_OK

        if gate_fires:
            evidence = ""
            for jp in envelope2.get("judgment_points", []):
                if jp.get("id") == "jp_step3_percolate_confirmation_gate":
                    evidence = jp.get("evidence", "")
            print("")
            print(f"Step 3 gate fired: {evidence}")
            print(f"Dry-run summary for target '{target}':")
            print(f"  added:    {added}")
            print(f"  modified: {modified}")
            print(f"  removed:  {removed}")
            print("")
            print("First 10 paths:")
            for _tag, path in dryrun_changes[:10]:
                print(f"  {path}")
            if len(dryrun_changes) > 10:
                print(f"  ... ({len(dryrun_changes) - 10} more)")
            print("")
            if args.yes:
                print("Proceed with real publish? [y/N] y (--yes)")
            elif args.invocation_authorized:
                print("Proceed with real publish? [y/N] y (--invocation-authorized)")
            elif sys.stdin.isatty():
                answer = input("Proceed with real publish? [y/N] ").strip().lower()
                if answer not in ("y", "yes"):
                    print("Publish cancelled.")
                    return _EXIT_OK
            else:
                print("Step 3 confirm required, no tty and no --invocation-authorized.")
                print("Re-run in a terminal, or pass --yes / --invocation-authorized from an authorized caller.")
                return _EXIT_CONFIRM_REQUIRED

        # --- Pre-flight: dest crash-recovery check --------------------------
        dirty_status = _dest_dirty_status(dest)
        if dirty_status is not None:
            if args.reconcile_dest == "discard":
                ok, message = _reconcile_dest_discard(dest, dirty_status)
                if not ok:
                    print(
                        f"percolate-round: refusing to discard dest '{dest}' "
                        f"residue — {message}",
                        file=sys.stderr,
                    )
                    return _EXIT_FAIL
                print(f"percolate-round: {message}")
            else:
                print(
                    f"percolate-round: dest '{dest}' already has uncommitted changes — "
                    "a prior round may have crashed between its real run and commit. "
                    "Retry with --reconcile-dest=discard to reset dest to HEAD and "
                    "remove residue, or reconcile by hand (review, commit) first:",
                    file=sys.stderr,
                )
                print(dirty_status, file=sys.stderr)
                return _EXIT_FAIL

        # --- Step 4 -> commit -> CI smoke -> gate -> push: held under one
        # lock ------------------------------------------------------------
        # Widens `held_lock(dest)` to span the Step 4 real-run subprocess,
        # the scoped-git-commit subprocess, CI smoke, the C2 gate, AND the
        # push (C3) — closing the gap `publish.py`'s own `held_lock`
        # (released in its `finally` when that subprocess exits) leaves
        # open between Step 4 and commit, and extending it so a push is
        # never issued outside the same span its own commit landed under.
        # If round A released the lock after committing and pushed later,
        # round B could acquire the lock and commit against the same dest
        # in between, and A's `git push` would then publish B's
        # uncertified commit — CI smoke sitting outside the lock is not
        # precedent for the push to sit outside it too; CI smoke is
        # read-only, a push is not. Same primitive, same key derivation
        # (`held_lock`'s own `sha1(realpath(target))`) as
        # `publish.py::main`'s Part B lock — a second concurrent round
        # against the same dest contends on the identical key. The parent
        # re-acquiring this key after `publish.py`'s own internal
        # acquire/release for the same dest already completed is
        # sequential, not re-entrant contention.
        # Spec backlink: state/audits/2026-08-13-percolate-round-race-repro.md
        try:
            with _round_held_lock(Path(dest), holder_label=f"percolate-round:{target}"):
                # --- Step 4: real run --------------------------------------
                print(f"=== percolate-round {target} — Step 4: real run ===")
                real_cmd = [sys.executable, str(_PUBLISH), target]
                if args.delta:
                    real_cmd.append("--delta")
                # Inherited-holder handoff (§ `_INHERITED_LOCK_ROOTS_ENV`
                # above) — scoped to THIS child's own env only (a fresh dict
                # derived from a copy of the parent's environment, never a
                # mutation of `os.environ`), so the token cannot leak into
                # any other subprocess this driver spawns and never persists
                # past this one call.
                import os as _os

                real_env = dict(_os.environ)
                # Review: code-reviewer P2 — bind the token to this process's
                # own PID (`os.getpid()`, the direct parent of the `publish.py`
                # child spawned just below) so the receiving side can verify
                # the entry actually came from its true parent via
                # `os.getppid()`, rather than trusting a bare realpath string
                # match on presence alone (a stray exported value in a
                # debugging shell, or a nested/second-order invocation, could
                # otherwise forge the skip). `=` is the pid/path delimiter —
                # split on the FIRST `=` only, since a Windows path never
                # starts with one but can contain `:` (drive letter).
                real_env[_INHERITED_LOCK_ROOTS_ENV] = f"{_os.getpid()}={_os.path.realpath(dest)}"
                real = _run(
                    real_cmd,
                    timeout=_PUBLISH_LEG_TIMEOUT_SECS,
                    env=real_env,
                )
                print(real.stdout)
                # publish.py prints its own per-row tally ("Rows succeeded:
                # N/M", "Rows FAILED: ...", "STATUS: PARTIAL — ...") to
                # STDERR, not stdout — `print(real.stdout)` above never
                # surfaces it. Treat that tally text as the trustworthy
                # signal alongside the exit code rather than the exit code
                # alone: a partial-rows-failed run must never read as a
                # clean pass just because `returncode` happened to come
                # back 0 on some future publish.py revision — the caller
                # only ever sees THIS process's own exit code and verdict.
                # Spec backlink: doe-claude-em corroborated-run report,
                # 2026-08-14 ("Rows succeeded: 3/5", exit 0, no verdict).
                # Review: code-reviewer P3 — this substring check is
                # deliberately defence-in-depth, not a live trigger against
                # today's `publish.py::main`: both literals print only
                # inside `if failed_row_names:`, which unconditionally
                # `return 1`s before that function can reach `return 0`, so
                # `real.returncode == 0` and either literal being present in
                # `real.stderr` cannot co-occur under the current
                # `publish.py` source (confirmed by reading, not just an
                # unreproducible incident). Keep this branch — it exists to
                # catch a FUTURE regression in that return contract, not a
                # currently-reachable path; don't prune it as dead code.
                _real_row_failure_text = (
                    "Rows FAILED:" in real.stderr or "STATUS: PARTIAL" in real.stderr
                )
                if real.returncode != 0 or _real_row_failure_text:
                    tally = _extract_row_tally(real.stdout, real.stderr)
                    print("")
                    print(f"percolate-round {target} — FAIL")
                    print("  dry-run:   exit 0")
                    if real.returncode != 0:
                        print(f"  real-run:  exit {real.returncode}")
                    else:
                        print(
                            "  real-run:  exit 0, but reported failed row(s) "
                            "(exit-code/summary mismatch — treated as FAIL)"
                        )
                    if tally is not None:
                        print(f"  rows:      {tally}")
                    print("  ci-smoke:  skipped (Step 4 did not complete cleanly)")
                    print("  push:      skipped")
                    _print_step_failure("Step 4 (real run)", real_cmd, real.stderr)
                    return _EXIT_FAIL
                has_review_warnings = "REVIEW WARNING" in real.stdout
                if has_review_warnings:
                    print("Phase 4 audit found REVIEW items — acknowledge before next publish round:")
                    for line in real.stdout.splitlines():
                        if "REVIEW WARNING" in line:
                            print(f"  {line.strip()}")

                real_changes, real_renames = _extract_change_lines(real.stdout)

                # Review: coordinatorcode-reviewer-c58be590 (live-round
                # follow-up) -- `dest` can itself be a subdirectory of the
                # mirror's git worktree (a `dest_subdir` row), while other
                # rows in the SAME real run report against sibling
                # subtrees of that same worktree. Using `dest` as
                # `repo_root` walked `os.path.relpath` upward
                # (`../coordinator/bin/...`) for those sibling rows,
                # which `scoped-git-commit --repo` then rejected outright
                # -- resolve the actual worktree root once and use it for
                # both the pathspec and `--repo` below, so they can never
                # diverge.
                repo_root = _resolve_repo_root(dest)
                if repo_root is None:
                    print(
                        f"percolate-round: could not resolve git worktree root for "
                        f"dest '{dest}'.",
                        file=sys.stderr,
                    )
                    return _EXIT_FAIL

                pathspec_seen: dict = {}
                for row_dest, row_stdout in _split_stdout_by_row_dest(real.stdout, dest):
                    row_changes, row_renames = _extract_change_lines(row_stdout)
                    for entry in _build_commit_pathspec(
                        row_dest, row_changes, row_renames, repo_root=repo_root
                    ):
                        pathspec_seen.setdefault(entry, None)
                pathspec = list(pathspec_seen.keys())

                # --- Commit step ---------------------------------------------
                if not pathspec:
                    print(f"percolate-round {target} — real run reported no changed files; nothing to commit.")
                    print("")
                    print("Summary:")
                    print("  dry-run:   exit 0")
                    print("  real-run:  exit 0  (no-op)")
                    print("  ci-smoke:  n/a (no changes to verify)")
                    if args.no_publish:
                        return _EXIT_OK
                    # AC2b: this round produced no bytes of its own, but the
                    # dest may already hold unpushed commits from an earlier
                    # round that stopped at the old print-and-stop terminus
                    # — still under THIS lock instance (already held; do not
                    # call `_publish_unpushed_dest_commits`, which acquires
                    # its own — `held_lock` is non-reentrant).
                    ahead = _dest_ahead_count(dest)
                    # Review: review-integrator — same probe-failure-vs-zero
                    # distinction as `_publish_unpushed_dest_commits` above;
                    # a failed probe must not print "already in sync".
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
                # Always via --pathspec-from-file, never argv, even for a
                # small pathspec: a length-threshold split makes the
                # large-payload branch the one that only ever runs on a
                # full publish round, which is exactly the branch that just
                # broke unnoticed (WinError 206, this file's own history --
                # a Windows CreateProcess command line caps at 32767 chars,
                # and an ~2000-path full-publish pathspec exceeds it well
                # before any threshold worth picking would trip). One code
                # path for every round size means the common (small) case
                # exercises the same route the rare (huge) case depends on.
                pathspec_file_path = tmp / "commit-pathspec.txt"
                pathspec_file_path.write_text(
                    "\n".join(pathspec) + "\n", encoding="utf-8"
                )
                commit_cmd = [
                    sys.executable,
                    str(_SCOPED_GIT_COMMIT),
                    "-m",
                    subject,
                    "--repo",
                    repo_root,
                    "--json",
                    "--pathspec-from-file",
                    str(pathspec_file_path),
                ]
                commit = _run(commit_cmd)
                print(commit.stdout.strip())
                try:
                    commit_result = json.loads(commit.stdout)
                except (json.JSONDecodeError, TypeError):
                    commit_result = {}
                declined_paths = commit_result.get("declined_paths") or []
                if commit_result.get("committed") and declined_paths:
                    # `scoped-git-commit` already exits non-zero here (its own
                    # `_exit_code_for_result`), so `commit.returncode != 0` below
                    # would already fail this round loud — but the generic
                    # step-failure rendering reads as "nothing landed", when in
                    # fact a commit DID land with only some paths declined. Name
                    # both halves explicitly (AC5) rather than leaving the operator
                    # to infer which happened from a raw JSON dump.
                    sha = commit_result.get("sha") or "?"
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
                    # PM ruling 1 (2026-08-14): the commit LANDED at dest even
                    # though this round fails — write the round-failure marker
                    # so `percolate-push.py`'s destination-state gate (C4)
                    # refuses this uncertified commit rather than publishing
                    # it on tree-hygiene alone.
                    _write_round_failure_marker(target, percolate_root, "declined_paths", sha)
                    return _EXIT_FAIL
                if commit.returncode != 0:
                    _print_step_failure("commit (scoped-git-commit)", commit_cmd, commit.stderr)
                    return _EXIT_FAIL

                # Marker inversion (P2, review-integrator): the commit has
                # now landed at dest — mark it unverified BEFORE CI smoke
                # and the C2 gate run, so a crash anywhere past this point
                # leaves the marker standing (fail-safe) instead of leaving
                # a landed-but-uncertified commit unmarked. Cleared only on
                # the clean-verdict path below.
                _write_round_failure_marker(
                    target,
                    percolate_root,
                    "uncommitted-verdict",
                    commit_result.get("sha") or "?",
                )

                # --- Step 5: CI smoke (AFTER the commit — see module docstring)
                print(f"=== percolate-round {target} — Step 5: CI smoke ===")
                ci_script = Path(dest) / ".github" / "scripts" / "run-all-checks.py"
                ci_exit: Optional[int] = None
                if ci_script.is_file():
                    python = _resolve_python()
                    ci = _run([python, str(ci_script)], cwd=dest)
                    print(ci.stdout)
                    if ci.stderr.strip():
                        print(ci.stderr, file=sys.stderr)
                    ci_exit = ci.returncode
                else:
                    print("  (no .github/scripts/run-all-checks.py at dest — skipped)")

                # --- Step 6/7: gate predicate + summary + push -------------
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
                print("  dry-run:   exit 0")
                print("  real-run:  exit 0")
                print(f"  ci-smoke:  {'exit ' + str(ci_exit) if ci_exit is not None else 'n/a (no run-all-checks.py)'}")

                if verdict == "FAIL":
                    print("")
                    print(f"percolate-round: publish refused — {refusal_reason}")
                    print("CI smoke is red after the commit — the commit already landed locally;")
                    print("fix the failure, then push by hand once CI is green. No push command")
                    print("is printed for a red CI run.")
                    # Same PM-ruling-1 rationale as the declined-paths branch
                    # above: the commit already landed locally at dest, and
                    # C4's destination-state gate would otherwise read this
                    # dest as clean-with-commits-to-push.
                    sha = commit_result.get("sha") or "?"
                    _write_round_failure_marker(target, percolate_root, "ci_red", sha)
                    return _EXIT_FAIL

                # PASS or PASS-WITH-WARNINGS from here.
                #
                # Marker inversion (P2, review-integrator): clear the marker
                # written right after the commit landed ONLY when this round
                # is genuinely clean (`refusal_reason is None`) — independent
                # of `--no-publish`, which merely defers the push, not
                # certification. A `refusal_reason`-refused round (e.g.
                # unacknowledged review warnings) leaves the marker standing
                # even under `--no-publish`: that commit is still uncertified.
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
            print(
                f"percolate-round: could not acquire the per-destination round "
                f"lock for '{dest}' (another round is running against this "
                f"dest) — {exc}",
                file=sys.stderr,
            )
            return _EXIT_FAIL


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="percolate-round",
        description="Sequence a single-target percolate publish round: dry-run through commit, CI smoke, and (on a clean round) push. --no-publish stops before the push instead.",
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
        "--dry-run-first",
        dest="dry_run_first",
        action="store_true",
        default=False,
        help=(
            "Opt-in preview (PM ruling, 2026-08-15): run Step 2's dry-run + "
            "leak-scan pass before the real sync, same as this tool's "
            "pre-2026-08-15 default. Off by default -- the round now syncs "
            "once and sources the Step 3 gate's touched-file count from that "
            "same real run, since the sync target is a revertible local git "
            "clone and the leak scan itself always read source files, never "
            "dry-run output."
        ),
    )
    parser.add_argument(
        "--reconcile-dest",
        choices=("refuse", "discard"),
        default="refuse",
        help=(
            "How to handle a dirty dest left by a prior crashed round. "
            "'refuse' (default) stops the round. 'discard' resets dest to "
            "HEAD and removes untracked residue -- refused itself if dest "
            "carries commits ahead of its remote. Never implied by --yes."
        ),
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
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
