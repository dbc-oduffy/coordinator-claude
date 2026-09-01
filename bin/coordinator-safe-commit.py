"""coordinator-safe-commit — Scoped safety commit helper (naked-Python port,
Wave 2 of the coordinator-session-family-repoint-and-delete plan, chunk C2a).

Port of the bash `coordinator-safe-commit` (Phase 3, scoped-safety-commits
plan) onto `coordinator_core.session` (core/liveness/scope/claims), in-process
imported via the `cc_invoke.resolve_engine_root` seam (self-location-first —
engine-root env (COORDINATOR_ENGINE_ROOT, or its legacy spelling
CLAUDE_KLABAUTER_ROOT) -> walk-up to this script's own enclosing checkout -> the
pointer-file/registry ladder) — the DR-047
Python-caller-shape ruling (the Director of Engineering, 2026-07-22; see
docs/plans/2026-07-22-coordinator-session-family-repoint-and-delete.md
§ Decisions). Same path, zero caller repoint — every dispatch prompt /
hook / doc that shells out to `coordinator-safe-commit` keeps working
unchanged; only the interpreter behind the shebang changed.

THIS CHUNK (C2a) implemented, as real working logic:
  - Session-id resolution, full priority chain (COORDINATOR_SESSION_ID >
    CLAUDE_SESSION_ID > CLAUDE_CODE_SESSION_ID > coordinator_core.session.
    core.resolve_session_id's 4-tier chain w/ tier-4 ambiguity guard >
    live-session-count auto-detect fallback).
  - Scope computation via coordinator_core.session.scope.compute_scope,
    plus the do_scoped-side mtime-only-orphan reclassification and the
    Case A/B/C/D "nothing to stage" diagnosis.
  - Scoped git add / git commit with the Sentinel-1/Sentinel-2 no-op-commit
    FAIL contract.
  - The overlap-gate lock primitive (`with_overlap_lock`) — ported as a
    self-contained function; C2b (below) wires it into --scope-from and
    --include-orphans, the only bash callers.
  - The >1-live-session fail-closed gate in default mode (outside
    combined/scope-from delegation): refuses (exit 1), naming the
    candidate session IDs.

THIS CHUNK (C2b) additionally implements, as real working logic:
  - `--scope-from <path>` (do_scope_from): parses the handoff YAML
    frontmatter `scope:` list, validates + expands each pathspec, publishes
    active-scope.txt under the overlap-gate lock (Fix 6 — closes the
    read-peers/write-own TOCTOU window), checks for collisions against live
    peer sessions' active-scope.txt, computes out-of-scope-dirty, and stages
    + commits the declared-scope intersection.
  - `--allow-out-of-scope-dirty` (scope-from-only): downgrades the
    out-of-scope-dirty check from a hard error to a warning; the check
    itself still runs, and semantics are identical whether or not --dry-run
    is also passed.
  - `--include-orphans <pathspec>...` (variadic, one-shot claim — not
    appended to touched.txt): resolves pathspecs to concrete dirty files,
    publishes/unions into active-scope.txt, runs the overlap gate, writes
    orphan-claims.log, and requires either a single live session (default
    mode) or --scope-from (combined mode) — do_scope_from delegates to
    do_scoped when both flags are combined, mirroring the bash's single
    canonical implementation (no duplicated combined-mode block).

THIS CHUNK (C2c-build) additionally implements, as real working logic:
  - `--blanket` (do_blanket): carve-out enforcement (CLAUDE_INVOKING_COMMAND
    allowlist — workstream-start / update-docs / relay-protocol /
    distillation — with a parent-process-cmdline fallback), logged to
    blanket-invocations.log; `git add -A` (the one sanctioned blanket-add
    path); the F0/F1 foreign-path subtract (sibling-claimed staged paths
    minus own/agent-touched, intersected with the staged set;
    `COORDINATOR_BLANKET_ACCEPT_FOREIGN=1` escape hatch; genesis-repo skip
    since a genesis repo cannot have live siblings); the destructive-shape
    gate (>=3 files with deletion-heavy diffs and no plan/handoff/PR/lessons
    /queue reference in the subject; soft-warn through 2026-06-01 then
    hard-fail; `COORDINATOR_OVERRIDE_BLANKET_SHAPE=1` /
    `COORDINATOR_BLANKET_SHAPE_STRICT=1`); Sentinel-1/Sentinel-2.
  - `COORDINATOR_OVERRIDE_SCOPE=1` (do_override): the audit-trail-degraded
    emergency escape hatch — logs to overrides.log, Sentinel-1/Sentinel-2.
    Intercepts default mode only. Staging is conditional (fixed 2026-07-25,
    see do_override docstring): commits a pre-staged explicit-path index
    as-is when one exists, falling back to `git add -A` only when the index
    is empty at entry.
  - `--dry-run`: an ORTHOGONAL boolean (`args.dry_run`), not a mode value —
    combinable with `--blanket`, `--scope-from`, or the plain default path,
    in any flag order. Prints what would be staged/committed without
    running `git add`/`git commit`, then exits 0: declared scope +
    orphan-claimed + unclaimed orphans + other-session-excluded on the
    default/`--include-orphans` path (do_scoped); the `git add -A`
    candidate set + commit subject on `--blanket` (do_blanket), computed
    from the current dirty-file union so no index mutation is needed to
    preview it; the scope-intersection set on `--scope-from`
    (do_scope_from). (Fixed 2026-07-22: `args.mode` was previously a
    single last-writer-wins field, so `--dry-run --blanket` and `--blanket
    --dry-run` disagreed — whichever flag parsed last won, so the second
    order silently fired a real commit despite the explicit `--dry-run`.
    See docs/plans/2026-06-15-harden-safe-commit-against-sibling-add-all.md
    for the original scoped-only dry-run; this promoted it to orthogonal.)

2026-07-24 (M4, docs/plans/2026-07-24-g4-execute-pipeline-two-repo-rebuild.md
§ chunk M4): the `--expected-owner em-only` gate (cooperative
`COORDINATOR_AGENT_CONTEXT` signal, fail-open by construction when unset)
and the `--expected-branch` self-commit bypass are BOTH REMOVED — not
bypassed, deleted. Both are SUPERSEDED by
`coordinator_core/bash_guards/block_subagent_commit.py`, a PreToolUse(Bash)
hard-deny guard keyed on the harness-supplied caller identity (a subagent
cannot unset it, unlike an env var). There is now exactly one rule
governing whether a caller may run this script's underlying `git commit` —
the guard, not a flag this script parses.

Canonical invocation:
  ~/.claude/plugins/coordinator/bin/coordinator-safe-commit "<subject>"

Usage forms:
  coordinator-safe-commit "<subject>"                      # default — scoped staging
  coordinator-safe-commit --blanket "<subject>"             # blanket — carve-outs only
  coordinator-safe-commit --scope-from <path> "<subject>"   # workstream-anchored
  coordinator-safe-commit --dry-run "<subject>"              # show what would be staged
  coordinator-safe-commit --body-file <path> "<subject>"     # multi-paragraph message
  coordinator-safe-commit "<subject>" -- <path> [<path>...]  # pathspec —
                                                               # routed through
                                                               # ceremony.commit_v2

2026-08-06 (cross-repo/inbox/2026-08-06-doe-claude-em-safe-commit-pathspec-
and-allowlist-naming.md, Defect 1): the `-- <paths>` form above is a
passthrough — originally it shelled out to `scoped-git-commit -m "<subject>"
-- <paths>` (coordinator_core/ops/ceremony/scoped_git_commit.py) rather than
re-implementing pathspec-scoped staging here; that delegate was killed
2026-08-23 (DR-344) and refused (`do_pathspec`) until this restore, which
repointed the same passthrough at `ceremony.commit`
(coordinator_core/ops/ceremony/commit_op.py), dispatched in-process via
`coordinator_core.ipc.dispatch_from_hook` rather than a CLI subprocess —
delegate, don't duplicate, same rationale as the original fix. `ceremony.
commit` was ITSELF killed 2026-08-27 (200ms process-time bar,
`coordinator_core/op_budget_suspension.py`) and this passthrough repointed
again, to `ceremony.commit_v2` (docs/plans/2026-08-27-something-must-commit-
ceremony-commit-v2.md, C7) — see `do_pathspec`'s own docstring for the
current wiring. Incompatible with `--blanket`, `--scope-from`,
`--include-orphans`, and `--allow-out-of-scope-dirty` (the op has no
orphan-claim/handoff-scope support of its own). `--body-file` WAS on that
list and is not any more (2026-08-31): the exclusion cited the killed
`scoped-git-commit`, while `ceremony.commit_v2`'s `message` is a plain
string this caller already composes.

Negative-spec: `--dry-run` must NEVER reach `git add`/`git commit` and must
be gated in EVERY mode branch, the `-- <paths>` pathspec form included --
that form was the third incident (2026-08-28) and it failed the same way
both earlier ones did: a new branch was added to `main()` and nobody
carried the flag into it. A mode that delegates its staging elsewhere has
no internal chokepoint to add the gate to later, so the gate goes in
`main()` ahead of the dispatch, never inside the handler.
NEVER mutate the staged index or refs, in EVERY mode and EVERY combination —
including `COORDINATOR_OVERRIDE_SCOPE=1` (do_override), which intercepts
default mode in main() BEFORE mode dispatch and therefore needs its own
`args.dry_run` gate (see do_override docstring, 2026-07-25 second fix). A
future change that adds a new `do_*` entry point or a new env-var
interception in main() and does not thread `args.dry_run` through it
reintroduces this exact class of defect.

Environment:
  CLAUDE_SESSION_ID                  — explicit session-ID override (manual / tests)
  CLAUDE_CODE_SESSION_ID             — platform-injected session ID
  COORDINATOR_SESSION_ID             — lib tier-1 test override (highest priority)
  COORDINATOR_OVERRIDE_SCOPE=1       — emergency: commits a pre-staged explicit-path index
                                        as-is if one exists, else stages all dirty files
                                        (git add -A); logged, default-mode only
  COORDINATOR_BLANKET_ACCEPT_FOREIGN=1 — skip the blanket F0/F1 foreign-path subtract
  COORDINATOR_ACCEPT_LIVENESS_PROBE_FAILURE=1 — bypass the resolve_session_id fail-closed
                                        liveness-probe-exception gate; degrades to 0 live
                                        sessions, session misidentification is possible
  COORDINATOR_OVERRIDE_BLANKET_SHAPE=1 — silence the blanket destructive-shape warning/fail
  COORDINATOR_BLANKET_SHAPE_STRICT=1   — promote the destructive-shape warning to a hard fail

Spec backlinks: docs/plans/2026-06-15-harden-safe-commit-against-sibling-add-all.md § E3,
docs/plans/2026-05-05-session-misidentification-fix.md,
docs/plans/safe-commit-fixes.md § Phase 1/2,
docs/plans/safe-commit-fixes-5-and-6.md § Fix 5/6,
docs/plans/2026-06-22-authorized-blanket-orphan-capture-not-sibling-sweep.md § C1a F0/F1,
docs/plans/2026-05-13-safe-commit-demote-to-sweep.md § Chunk 1 — Sentinel 1/2,
docs/plans/2026-07-22-coordinator-session-family-repoint-and-delete.md § C2a/C2b/C2c-build,
docs/plans/2026-07-24-g4-execute-pipeline-two-repo-rebuild.md § chunk M4
  (em-only + --expected-branch REMOVED, superseded by
  coordinator_core/bash_guards/block_subagent_commit.py).
"""
from __future__ import annotations

import contextlib
import io
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import re
import uuid
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

_BOOTSTRAPPED_NAMES = ("require_engine_on_path",)


_BOOTSTRAP_DONE = False


def _bootstrap_engine() -> None:
    """Bind `coordinator/bin/lib` onto sys.path, then the engine-root resolver
    that depends on it. Idempotent; safe to call more than once.

    What moved and what did not: this sequence ran at MODULE scope until now, so
    every import of this file mutated the `sys.path` of a warm server ~50 sessions
    share. Only the trigger moved; the order is byte-for-byte the same.
    """
    global _BOOTSTRAP_DONE
    if _BOOTSTRAP_DONE:
        return
    try:
        import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
        from cc_invoke import require_engine_on_path  # noqa: E402
    finally:
        # Publish whatever bound, EVEN IF a later import raised, and NEVER
        # overwrite a name a caller already installed (e.g. a monkeypatch).
        _resolved = locals()
        for _name in _BOOTSTRAPPED_NAMES:
            if _name not in globals() and _name in _resolved:
                globals()[_name] = _resolved[_name]

    # Only on a clean run: a partial bootstrap must stay retryable.
    _BOOTSTRAP_DONE = True


def __getattr__(name: str):
    """PEP 562 hook: a consumer that imports this module rather than executing it
    reaches these names before `main()` runs. Without this, deferring the
    bootstrap leaves them simply absent. Only fires for names not already in
    `__dict__`, so once bootstrapped the plain global wins.
    """
    if name in _BOOTSTRAPPED_NAMES:
        _bootstrap_engine()
        if name not in globals():
            global _BOOTSTRAP_DONE
            _BOOTSTRAP_DONE = False
            _bootstrap_engine()
        try:
            return globals()[name]
        except KeyError:
            raise AttributeError(
                f"module {__name__!r} has no attribute {name!r} after bootstrap"
            ) from None
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


BLANKET_ALLOWED_COMMANDS = frozenset(
    {"workstream-start", "update-docs", "relay-protocol", "distillation", "distill"}
)
# Parent-process-cmdline fallback markers (mirrors bash's ppid_cmd substring
# checks) — "distillation" deliberately has no `.md` suffix in bash, matching
# the ceremony's own dispatch-prompt naming, not a `.md` file. "distill.md"
# is the actual skill file (coordinator/commands/distill.md) — the natural
# `CLAUDE_INVOKING_COMMAND=distill` value was refused by neither marker
# before this fix (cross-repo/inbox/2026-08-06-doe-claude-em-safe-commit-
# pathspec-and-allowlist-naming.md, Defect 2).
BLANKET_ALLOWED_PPID_MARKERS = (
    "workstream-start.md",
    "update-docs.md",
    "relay-protocol.md",
    "distillation",
    "distill.md",
)

# Subject-reference grep for the blanket destructive-shape gate: word-boundary
# anchored tokens only (bare substrings like `plan`/`queue`/`review` were
# false-positive magnets — matched `workplan`, `dequeue`, "code review style
# comments"). Mirrors the bash grep -qiE pattern exactly.
_DESTRUCTIVE_SHAPE_REF_RE = re.compile(
    r"(\bhandoff\b|\bspinoff\b|\blearn-lessons\b|\bupdate-docs\b|\bdistill\b|"
    r"\bPR[ #]|#[0-9]+|\bplan/|plan #|\blessons\.md\b|\bqueue\.md\b|"
    r"\breview-trail\b|\bworkday-(complete|start)\b|\bworkweek-(complete|start)\b|"
    r"\bworkstream-(complete|start)\b)",
    re.IGNORECASE,
)


class UsageError(RuntimeError):
    """Raised for CLI usage errors; caught at the top level, prints to stderr, exit 1."""


def _import_session():
    """Resolve claude-klabauter root (cc_invoke.require_engine_on_path seam, wrapping
    resolve_engine_root's ladder, DR-047) and import the four
    coordinator_core.session submodules this port needs.
    Mirrors the refresh-queries.py in-process-import precedent."""
    _bootstrap_engine()
    try:
        require_engine_on_path(__file__)
    except RuntimeError as exc:
        print(f"coordinator-safe-commit: engine-root resolution failed: {exc}", file=sys.stderr)
        sys.exit(3)
    try:
        from coordinator_core.session import claims as cs_claims
        from coordinator_core.session import core as cs_core
        from coordinator_core.session import liveness as cs_liveness
        from coordinator_core.session import scope as cs_scope
    except ImportError as exc:
        print(
            f"coordinator-safe-commit: coordinator_core.session not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(3)
    return cs_core, cs_liveness, cs_scope, cs_claims


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

class Args:
    def __init__(self) -> None:
        self.mode = "default"  # default | blanket | scope-from
        self.dry_run = False  # orthogonal to mode — combinable with any of the above
        self.scope_from_path: str = ""
        self.subject: str = ""
        self.allow_out_of_scope_dirty = False
        self.include_orphans: List[str] = []
        self.body_file: str = ""
        self.body: str = ""
        self.paths: List[str] = []


def usage() -> None:
    print(
        """Usage:
  coordinator-safe-commit "<subject>"
  coordinator-safe-commit --blanket "<subject>"
  coordinator-safe-commit --scope-from <handoff.md> "<subject>"
  coordinator-safe-commit --dry-run "<subject>"
  coordinator-safe-commit --body-file <path> "<subject>"
  coordinator-safe-commit "<subject>" -- <path> [<path>...]

Optional flags (combinable):
  --allow-out-of-scope-dirty        (--scope-from only) warn instead of error
                                    when dirty files exist outside declared scope
  --include-orphans <pathspec>...   Claim hook/install-script-touched files for
                                    this commit. Variadic until next flag or --.
  --body-file <path>                Commit BODY (second paragraph) read from a
                                    file — avoids shell-quoting hazards for
                                    multi-paragraph messages. <subject> is
                                    still the required positional; the file's
                                    content becomes `git commit -m <subject>
                                    -m <body>`, never replaces the subject.

The `-- <path> [<path>...]` form commits exactly the given paths, routed
through the `ceremony.commit_v2` op
(coordinator_core/ops/ceremony/commit_v2.py) — not the killed
`scoped-git-commit` CLI (DR-344, 2026-08-23) nor the killed `ceremony.commit`
op it repointed to before (2026-08-27, 200ms process-time bar).
Still incompatible with --blanket, --scope-from, --include-orphans,
and --allow-out-of-scope-dirty. --body-file IS supported here (2026-08-31):
put a long message in a file so its prose never enters the command string,
where the harness's own destructive-action scan reads argv.

Whether a caller may commit at all is enforced by the
coordinator_core/bash_guards/block_subagent_commit.py PreToolUse(Bash)
guard, not by a flag this script parses (2026-07-24, M4).
""",
        file=sys.stderr,
    )


def parse_args(argv: Sequence[str]) -> Args:
    args = Args()
    i = 0
    n = len(argv)
    positionals: List[str] = []
    saw_pathspec_separator = False
    # Review: code-reviewer — Finding 3 (fixed 2026-07-22): args.mode was
    # previously a single last-writer-wins field, so parse order determined
    # which of --scope-from / --dry-run "won" — either silently dropped the
    # declared scope, or (worse) silently fired a real commit despite an
    # explicit --dry-run. Fix: --dry-run is now an ORTHOGONAL boolean
    # (args.dry_run) that never competes for the mode field, so it combines
    # cleanly with --blanket or --scope-from in either flag order.
    while i < n:
        tok = argv[i]
        if tok == "--blanket":
            args.mode = "blanket"
            i += 1
        elif tok == "--scope-from":
            args.mode = "scope-from"
            if i + 1 >= n:
                raise UsageError("--scope-from requires a path argument.")
            args.scope_from_path = argv[i + 1]
            i += 2
        elif tok == "--dry-run":
            args.dry_run = True
            i += 1
        elif tok == "--allow-out-of-scope-dirty":
            args.allow_out_of_scope_dirty = True
            i += 1
        elif tok == "--body-file":
            if i + 1 >= n:
                raise UsageError("--body-file requires a path argument.")
            args.body_file = argv[i + 1]
            i += 2
        elif tok == "--include-orphans":
            i += 1
            # Variadic: consume until next flag (starts with -), '--', or until
            # only one positional remains (the subject must be last).
            while i < n - 1 and argv[i] != "--" and not argv[i].startswith("-"):
                args.include_orphans.append(argv[i])
                i += 1
            if not args.include_orphans:
                raise UsageError("--include-orphans requires at least one pathspec argument.")
        elif tok == "--":
            # Pathspec-passthrough separator (Defect 1,
            # cross-repo/inbox/2026-08-06-doe-claude-em-safe-commit-
            # pathspec-and-allowlist-naming.md): everything after `--` is a
            # path handed to `scoped-git-commit`, mirroring `git commit`'s
            # own `-m <subject> -- <paths>` shape. The subject is whatever
            # positional token(s) were already collected before `--`.
            i += 1
            saw_pathspec_separator = True
            args.paths = list(argv[i:])
            i = n
            break
        elif tok.startswith("-"):
            raise UsageError(f"Unknown flag: {tok}")
        else:
            # Token-by-token (append + i+=1), NOT `positionals.extend(argv[i:]);
            # break` — deliberate 2026-08-06 behavior change (Review:
            # coordinator-code-reviewer bd2f004c): a flag-shaped token
            # appearing after the subject now raises UsageError immediately
            # via the `tok.startswith("-")` branch above on the next loop
            # iteration, instead of being silently swallowed into
            # `positionals` as an extra "positional" that only errored later,
            # indirectly, via the `len(positionals) > 1` check below.
            positionals.append(tok)
            i += 1

    if not positionals:
        if saw_pathspec_separator:
            raise UsageError(
                "Commit subject is required. `--` was seen before any subject "
                "token — did you mean `<subject> -- <paths>` (subject first, "
                "then the pathspec separator)?"
            )
        raise UsageError("Commit subject is required.")
    if len(positionals) > 1:
        raise UsageError("Too many positional arguments. Quote your subject.")
    args.subject = positionals[0]
    if not args.subject:
        raise UsageError("Commit subject cannot be empty.")

    if saw_pathspec_separator and not args.paths:
        raise UsageError("`--` requires at least one path argument after it.")
    if args.paths:
        if any(not p for p in args.paths):
            raise UsageError("`--` requires at least one non-empty path argument after it.")
        if args.mode != "default":
            raise UsageError("`-- <paths>` cannot be combined with --blanket or --scope-from.")
        if args.include_orphans:
            raise UsageError("`-- <paths>` cannot be combined with --include-orphans.")
        if args.allow_out_of_scope_dirty:
            raise UsageError("`-- <paths>` cannot be combined with --allow-out-of-scope-dirty.")
        # `--body-file` IS supported on this form as of 2026-08-31. The
        # refusal that stood here cited `scoped-git-commit`, a CLI DR-344
        # killed on 2026-08-23; this form has routed through
        # `ceremony.commit_v2` since 2026-08-27, whose `message` param is a
        # plain string that `do_pathspec` already composes. Nothing needed
        # building -- the constraint had outlived the thing that imposed it,
        # which is the killed-name-persists-in-a-string-keyed-check class.
        #
        # It is not merely a tidy-up. `-- <paths>` is the ONLY form scoped-
        # commit discipline permits, so while this refusal stood, every
        # sanctioned commit had to put its entire prose in argv -- where the
        # harness's own destructive-action scan reads it as operands. A
        # commit message describing a path separator was refused as
        # `Remove-Item on system path '/'`; rewording let the identical
        # commit through. That scan is not ours to fix, but handing it the
        # prose was, and `--body-file` is how a caller stops.
        pass

    if args.body_file:
        try:
            args.body = Path(args.body_file).read_text(encoding="utf-8")
        except OSError as exc:
            raise UsageError(f"--body-file: cannot read {args.body_file}: {exc}")
        if not args.body.strip():
            raise UsageError(f"--body-file: {args.body_file} is empty.")

    return args


def do_pathspec(args: "Args") -> None:
    """Restores the `-- <paths>` pathspec-passthrough form (DR-344 killed the
    old `scoped-git-commit` CLI delegate 2026-08-23; this routes through its
    replacement instead of resurrecting the killed binary or re-implementing
    pathspec-scoped staging here — delegate, don't duplicate, same rationale
    as the pre-kill form's own docstring).

    REPOINTED 2026-08-27 (docs/plans/2026-08-27-something-must-commit-
    ceremony-commit-v2.md, C7): the prior replacement, `ceremony.commit`
    (`coordinator_core/ops/ceremony/commit_op.py`), was itself KILLED at the
    200ms process-time bar (`coordinator_core/op_budget_suspension.py`) --
    p50 421.9ms process time, n=241. The current replacement is
    `ceremony.commit_v2` (`coordinator_core/ops/ceremony/commit_v2.py`), a
    fresh dispatchable identity over the zero-spawn `commit.commit_paths`
    (`coordinator_core/git/commit.py`) -- spawned via `cc_invoke.cc_invoke()`
    (`coordinator/bin/lib/cc_invoke.py`), same as before: the same
    warm-first-then-cold-`coordinator_core.invoke` transport every other
    thin CLI door in `coordinator/bin/` uses (see `priority-set.py`,
    `set-goal-kr-status.py`), not a direct `coordinator_core.ipc` import:
    this script's own module-level import already only pulls in
    `cc_invoke`'s lib-relative helpers, never `coordinator_core` itself
    (`_import_session()` is the one place that crosses that boundary, and
    only for the session-family modules do_scoped/do_scope_from/do_blanket
    need). Going through a bare in-process `dispatch_from_hook` here would
    additionally trip the stamp gate (`ipc.py`'s `_STAMP_GATE_ARMED`) on an
    unstamped dev checkout — `cc_invoke()` is the sanctioned unstamped-safe
    route (warm reach first, cold `coordinator_core.invoke` subprocess
    otherwise, neither of which requires this process's own import to be a
    published/stamped engine).

    `params.paths`/`params.deleted_paths` are split from `args.paths` via
    `_split_paths_for_commit_v2` (a path absent from the worktree is a
    deletion) -- this wrapper's whole job here is "commit exactly these
    paths", so nothing narrows or widens that set. No orphan-claim or
    handoff-scope machinery applies to this explicit-path form, mirroring
    the killed CLI's own scope. OWNERSHIP is no longer in that exemption:
    `_refuse_contested_pathspec` runs ahead of the dispatch and refuses a
    path a live peer still holds (see its docstring for the incident that
    closed the gap). It does not narrow the set either -- it refuses the
    whole call, so "commit exactly these paths, or none of them" still
    holds. There is no in-process
    fallback for an unregistered op any more: `ceremony.commit_v2` not being
    registered is a real, reportable failure now, not something to route
    around by re-entering a killed handler (see this plan's own note on why
    a fallback that reaches the old pipeline is how the deleted path becomes
    the live path again).

    Negative-spec: does NOT resurrect `scoped-git-commit`, `ceremony.commit`,
    or any string-keyed reference to either — the op name is
    `ceremony.commit_v2`, a fresh identity (commit_v2.py's own docstring),
    not either killed op reincarnated.

    AC8 reconcile (2026-08-26, docs/plans/2026-08-26-the-commit-becomes-a-
    warm-served-op.md § AC8, "RESOLVED — reconcile, not prevention"): an
    attempt id is minted before dispatch and threaded through as an
    `Attempt-Id:` trailer appended to the commit message body (`ceremony.
    commit_v2` has no separate `trailers` param -- it is a thin envelope over
    `commit_paths`, not the `commit_trailers.py` machinery the killed op
    carried). On an INDETERMINATE outcome (a `cc_invoke` timeout, a
    `BrokenPipeError`-shaped failure, or a malformed/ambiguous envelope —
    see `_is_indeterminate_outcome`'s own docstring for the exact,
    deliberately narrow predicate) this caller reconciles BEFORE reporting
    anything: it searches recent branch history for a commit carrying this
    call's own `Attempt-Id:` trailer via `commit_reconcile
    ._reconcile_landed_despite_failure` — the same bounded-log-search
    primitive `commit()`'s own reported-failure-but-landed repair already
    uses, reused rather than re-derived (delegate, don't duplicate, this
    function's own established idiom). Found means the commit already
    landed — report success. Absent means nothing landed — report failure
    and say the retry is safe. This is detect-and-report, never
    detect-and-redo: no retry is issued from here (Anti-scope, this plan —
    a commit is not idempotent)."""
    _bootstrap_engine()
    from cc_invoke import cc_invoke

    # Puts coordinator_core on sys.path so cc_invoke()'s in-process warm-reach
    # attempt (coordinator_core.warm.client) can import cleanly — mirrors
    # _import_session()'s own require_engine_on_path() call for the
    # session-family do_* functions; without it a dev checkout with no
    # editable-installed coordinator_core raises ModuleNotFoundError out of
    # the warm-reach probe before ever reaching the cold-spawn fallback.
    require_engine_on_path(__file__)

    worktree_root = _worktree_root_from_cwd()
    attempt_id = uuid.uuid4().hex
    attempt_trailer = f"Attempt-Id: {attempt_id}"
    pre_sha = _resolve_pre_sha_for_reconcile(worktree_root)

    _refuse_contested_pathspec(args.paths, worktree_root)

    present_paths, deleted_paths = _split_paths_for_commit_v2(worktree_root, args.paths)
    # Body BEFORE the trailer: `Attempt-Id:` is a trailer, and git's own
    # trailer parsing reads the LAST paragraph. Composing them the other way
    # round would push the trailer into the middle of the message, where
    # `commit_reconcile`'s post-indeterminate search cannot find it -- and
    # that search is the only thing standing between a timed-out commit and
    # a blind retry that double-commits.
    body = args.body.strip() if args.body else ""
    message = (
        f"{args.subject}\n\n{body}\n\n{attempt_trailer}"
        if body
        else f"{args.subject}\n\n{attempt_trailer}"
    )
    params = {
        "paths": present_paths,
        "deleted_paths": deleted_paths,
        "message": message,
    }
    try:
        result = cc_invoke("ceremony.commit_v2", params, worktree_root)
    except BrokenPipeError as exc:
        _reconcile_after_indeterminate(args, worktree_root, attempt_trailer, pre_sha, exc)
        return
    except RuntimeError as exc:
        if _is_indeterminate_outcome(exc):
            _reconcile_after_indeterminate(args, worktree_root, attempt_trailer, pre_sha, exc)
            return
        print(f"ERROR: ceremony.commit_v2: {exc}", file=sys.stderr)
        sys.exit(1)

    if result.get("nothing_to_commit"):
        # SEPARATED FROM THE GENERIC REFUSAL because the two need opposite
        # things from the reader. A generic refusal says the route failed; this
        # says the route worked and there was nothing there -- which, when the
        # caller believed it had just written something, means the write is the
        # thing that did not land. That is the sentence a session took at face
        # value from `committed sha=` and lost a twelve-finding review pass to.
        print(
            "NOTHING TO COMMIT: every named path already matches HEAD -- no "
            "commit was made and HEAD is unmoved. If you expected a change, "
            "your edit never landed.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not result.get("committed"):
        print(
            f"ERROR: ceremony.commit_v2 did not commit: {result.get('error') or result}",
            file=sys.stderr,
        )
        sys.exit(1)

    # WARNINGS PRINT BESIDE THE SHA, and their absence here was half of the
    # zero-delta bug rather than a cosmetic gap: `ceremony.commit_v2` has
    # raised structured warnings for a while -- passed-over staged bytes,
    # repaired line endings, and now declared paths that contributed nothing
    # -- and this helper dropped every one of them on the floor, leaving
    # `committed sha=` as the whole of what a caller saw. A fact returned to a
    # surface that does not print it is not reported.
    for warning in result.get("warnings") or ():
        print(f"WARNING: {warning}", file=sys.stderr)

    print(f"committed sha={result.get('sha')}", file=sys.stderr)


def _holder_context(
    worktree_root: str, sid: str, path: str, registry_snapshot: Optional[dict] = None
) -> str:
    """One holder's identity, rendered so the caller can act on the refusal.

    A bare `sid[:8]` is not an address, and worse, it is stale by default: a
    session RE-POINTS its id while keeping its name (measured 2026-08-31 by
    claude-klabauter-ad: six re-points across five of twelve peers in one
    shift, one session twice). So the sid printed here can name a session
    that no longer exists under it, and attributing on one produced a
    three-hop misattribution that reached a peer's execution wave as a false
    premise that same day. `harness_registry.snapshot()` holds the stable
    name -- the thing `SendMessage` actually accepts -- and answers in 5.4ms
    over 31 records, so the name is resolved HERE, at the moment of the
    refusal, never carried in from a record or a document that mentions it.

    A sid with no registry entry is reported as unnamed, never as dead: this
    helper runs only inside a branch `contested_by_live_peers` has already
    decided, so liveness is established before the name is looked up and the
    label may not contradict it. A label reading "stale id" here produced
    "held by live session(s) 6ab7b0d8 (stale id...)" -- self-contradicting in
    one line, and a peer who believed the stale half left an artifact dirty
    rather than commit it. What the miss means is that the sid has no
    resolvable name, and the caller cannot reach the holder by one: printing
    it bare as if it were an address is how a guard teaches the fleet to
    route around it, which costs the true positives too.

    Two facts make the sid actionable, and both are already on disk:
    the holder's baton title (what they are working on, so the caller can
    tell live work from residue), and how long the TOUCH has gone
    unreleased. An 11h-old claim on a file whose work is committed reads
    differently from a 2-minute-old one, and the caller currently cannot
    distinguish them.

    Best-effort in every part: an unreadable baton, a missing sink, or any
    `Exception` degrades to the bare sid rather than raising. This runs only
    in the already-contested branch, after `_refuse_contested_pathspec`'s own
    `_import_session()` call has already put `coordinator_core.session` on
    `sys.path` -- calling it again here would be redundant AND would break
    this function's own best-effort contract: `_import_session()` degrades
    failure via `sys.exit(3)`, which is `SystemExit`, not a subclass of
    `Exception`, so it would pass straight through the `except Exception`
    below and kill the whole invocation instead of degrading to the bare sid.
    """
    bits: List[str] = []
    try:
        if registry_snapshot is None:
            from coordinator_core.session import harness_registry  # noqa: PLC0415

            registry_snapshot = harness_registry.snapshot()
        record = registry_snapshot.get(sid)
    except Exception:
        record = None
    name = getattr(record, "name", None) if record is not None else None
    if name:
        bits.append(f"{name} [{sid[:8]}]")
    else:
        bits.append(f"{sid[:8]} (live, no name in the harness registry)")
    sessions_dir = os.path.join(worktree_root, ".git", "coordinator-sessions", sid)
    try:
        import json  # noqa: PLC0415

        with open(os.path.join(sessions_dir, "baton.json"), encoding="utf-8") as fh:
            title = (json.load(fh) or {}).get("title")
        if title:
            bits.append(f'"{str(title)[:70]}"')
    except Exception:
        pass
    try:
        last_ts = None
        with open(
            os.path.join(sessions_dir, "touch-record.jsonl"), encoding="utf-8"
        ) as fh:
            for line in fh:
                line = line.strip()
                if not line or path not in line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if rec.get("path") == path and rec.get("verb") == "T":
                    last_ts = rec.get("ts") or last_ts
        if last_ts:
            hours = (time.time() - float(last_ts)) / 3600.0
            bits.append(
                f"held {hours:.1f}h" if hours >= 1 else f"held {hours * 60:.0f}m"
            )
    except Exception:
        pass
    return " ".join(bits)


def _norm(path: object) -> str:
    """Backslashes to forward slashes, strip leading/trailing `/` -- the one
    spelling of this rule, used everywhere `_paths_with_no_uncommitted_content`
    and `_refuse_contested_pathspec` compare a git-porcelain path against a
    caller-supplied one.

    Review: overengineering-reviewer (finding #6, nitpick, accepted) -- this
    normalisation used to be spelled out three times (building `wanted`, per
    porcelain entry, and again filtering `contested`); one drifting from the
    other two would have quietly stopped `clean`/`contested` from matching.
    """
    return str(path).replace("\\", "/").strip("/")


def _paths_with_no_uncommitted_content(
    paths: "Sequence[str]", worktree_root: str
) -> "Set[str]":
    """Of `paths`, those whose worktree state matches HEAD exactly.

    THE NARROWING THE REFUSAL NEVER HAD. `_refuse_contested_pathspec` takes the
    raw pathspec with no dirtiness filter, so a path a live peer holds a TOUCH
    on refuses the whole commit even when that path carries no uncommitted
    content of anyone's. A touch is unreleased until its own session releases
    it, and a session releases nothing when it commits its work and moves on --
    so a file touched hours ago, long since committed, contests against every
    peer for the rest of that session's lifetime. Measured 2026-08-31: one
    holder blocked `coordinator/bin/publish.py` for 11.3h with zero
    uncommitted content in it, with bypass as the only exit, and a bypass
    normalised is how the true positives die too.

    The named harm is "committing it lands their uncommitted work under your
    message". A path identical to its HEAD blob has no uncommitted work in it
    to land -- anyone's -- so that harm is impossible regardless of who holds a
    touch. This is the only narrowing available without per-hunk provenance,
    which `docs/research/2026-08-27-hunk-level-ownership-spike.md` anti-scopes.
    Explicitly NOT the tempting one: dropping the refusal when the holder's
    recorded `content_hash` differs from disk looks sound and is not -- a
    peer's hunk already sitting in a file this session then edits produces
    exactly that mismatch, which is the incident the guard was built for.

    FAILS CLOSED, to the empty set: an unrunnable git, a timeout, a nonzero
    exit, or an unparseable line all mean "cannot establish that anything is
    clean", and the refusal stands whole. The one thing this must never do is
    turn "I could not tell" into "safe to commit".

    UNTRACKED COUNTS AS DIRTY, which is why this reads `status --porcelain`
    rather than `diff HEAD`: a peer's brand-new file is absent from HEAD, so a
    diff would call it clean while committing it lands exactly their work.

    ONE spawn for the whole set, on the already-rare contested path (~25ms,
    against the ~140ms this refusal already costs) -- never one per path, per
    the amplification gate.
    """
    wanted = {_norm(p) for p in paths if str(p).strip()}
    if not wanted:
        return set()
    try:
        # Review: coordinator:code-reviewer af0c0865daafdd73a, Finding P1 --
        # the subprocess argv MUST carry the same normalized form `wanted`
        # already is, not raw `paths`. A backslash-bearing contested path
        # (this is a Windows-first repo) can fail git's pathspec matching as
        # a literal argument, produce empty porcelain output with
        # returncode==0, and silently be classified `clean` -- exactly the
        # "I could not tell -> safe to commit" flip this function's own
        # docstring forbids. `sorted(wanted)` is the same set `dirty` is
        # compared against below, deterministic argv order for free.
        result = subprocess.run(
            ["git", "status", "--porcelain", "-z", "--untracked-files=all", "--"]
            + sorted(wanted),
            cwd=worktree_root,
            capture_output=True,
            text=True,
            # Review: coordinator:code-reviewer af0c0865daafdd73a, Finding P2
            # -- was 10s, 20x this repo's 500ms brightline for a call on
            # every explicit-pathspec commit's hot path. Fails closed to the
            # empty (refuse-everything) set on timeout, never a corruption
            # risk, so shortening this costs a spurious refusal under a truly
            # stuck git, not a wrong answer -- reusing SUSPENSION_BAR_MS
            # (2000ms, `docs/decisions/DR-344-*`) as the ceiling here, not as
            # a target: ~80x the ~25ms typical cost this function already
            # measures, and the same number this repo already treats as
            # "switch off before this" everywhere else.
            timeout=2,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired):
        return set()
    if result.returncode != 0:
        return set()

    dirty: "Set[str]" = set()
    fields = [f for f in result.stdout.split("\x00") if f]
    index = 0
    while index < len(fields):
        entry = fields[index]
        index += 1
        if len(entry) < 4:
            # A porcelain entry is `XY <path>`; anything shorter is a shape
            # this parser does not understand, and an unparsed line must not
            # silently reduce the dirty set.
            return set()
        status_code, path_field = entry[:2], entry[3:]
        dirty.add(_norm(path_field))
        if "R" in status_code or "C" in status_code:
            # A rename/copy entry is followed by its ORIGIN path in its own
            # NUL-separated field; both ends are dirty.
            if index < len(fields):
                dirty.add(_norm(fields[index]))
                index += 1
            else:
                return set()

    clean = set()
    for path in wanted:
        prefix = path + "/"
        if not any(d == path or d.startswith(prefix) for d in dirty):
            clean.add(path)
    return clean


def _refuse_contested_pathspec(paths: Sequence[str], worktree_root: str) -> None:
    """The ownership gate the explicit-pathspec form never had.

    `do_pathspec`'s own docstring states the anti-scope it inherited from
    the killed `scoped-git-commit` CLI -- "no session id, orphan-claim, or
    handoff-scope machinery applies to this explicit-path form" -- and
    `main`'s dispatch comment still says the delegate "does its own
    session/ownership gating". That delegate is gone (DR-344 killed it
    2026-08-23) and its replacement, `ceremony.commit_v2`, is a thin
    envelope over `commit.commit_paths` that gates nothing: it releases
    claims AFTER the commit and checks none before it. So the one commit
    route doctrine mandates was the one route with no ownership check on
    it, while `check_validate_commit`'s whole Check-5 apparatus -- peer
    claims, foreign hunks, the C11 content-hash refusal -- guards only what
    its own regex matches, a literal `git commit`.

    Measured 2026-08-31 on work/machine-a/2026-08-18to31: sessions d12e25cf
    and 1ad288d0 each held uncommitted hunks in
    `coordinator_core/workstream_complete/__init__.py`; e74e4ce8 committed
    the whole file at 40abe011d0 for an unrelated fix and landed both,
    under a message describing neither and, for one of them, without its
    regression tests. Nothing warned any of the three, and e74e4ce8's
    session dir carries no `scope-warnings.log` for it. Check 5's C11 hash
    arm could not have caught this even had it run: e74e4ce8 wrote the file
    LAST, so its own recorded hash matched disk exactly, and that arm only
    ever sees a peer edit landing AFTER this session's last write. A peer's
    hunk already sitting in a file this session then edits is invisible to
    it. Live-peer CLAIMS are the signal that was available and unread.

    REFUSES rather than warning: a warning on stderr competes with
    `ceremony.commit_v2`'s own warnings beside a `committed sha=` line for a
    commit that has already landed, and what has landed on a shared branch
    a peer then commits on top of is not revertible by the session that
    noticed. Refusing costs the caller a round-trip; warning costs someone
    else their work.

    FAILS OPEN on everything -- an unresolvable session id, an unreadable
    sink, any exception -- via `contested_by_live_peers`'s own contract plus
    the ring here. ~62ms process time when nothing is contested (the common
    case), ~140ms when something is; both inside the 500ms brightline this
    route already spends a `cc_invoke` round trip against.
    """
    try:
        cs_core, _cs_liveness, cs_scope, _cs_claims = _import_session()
        # NOT `resolve_session_id` (this file's own helper): that one is
        # fail-CLOSED by design and exits(1) on an ambiguous or unavailable
        # identity. Here an unresolved identity must mean "cannot establish
        # a contest", never "refuse the commit" -- so the lib call alone,
        # with no auto-detect fallback and no exit.
        session_id = cs_core.resolve_session_id()
        if not session_id:
            return
        contested = cs_scope.contested_by_live_peers(
            list(paths), session_id, worktree_root
        )
    except Exception:
        return
    if not contested:
        return

    # A claim has a birth and no death: a TOUCH outlives the work that made it,
    # so most of what reaches here is residue rather than a live hold. Drop the
    # paths that provably cannot carry the harm -- worktree identical to HEAD --
    # before naming anyone. Fails closed: an undeterminable answer leaves the
    # whole refusal standing.
    clean = _paths_with_no_uncommitted_content(sorted(contested), worktree_root)
    if clean:
        contested = {
            path: holders
            for path, holders in contested.items()
            if _norm(path) not in clean
        }
        if not contested:
            return

    # Review: coordinatorcode-reviewer.a075e39a58642def2, Finding 4 -- one
    # registry read for the whole refusal instead of one per (path, holder)
    # pair; `_holder_context` still degrades to its own read if this is None.
    try:
        from coordinator_core.session import harness_registry  # noqa: PLC0415

        registry_snapshot = harness_registry.snapshot()
    except Exception:
        registry_snapshot = None
    for path in sorted(contested):
        owners = "; ".join(
            _holder_context(worktree_root, o, path, registry_snapshot)
            for o in contested[path]
        )
        print(
            f"BLOCKED: {path} is also held by live session(s) {owners} -- "
            "committing it lands their uncommitted work under your message.",
            file=sys.stderr,
        )
    print(
        "Drop the named path(s) from the pathspec, or coordinate with the "
        "holder(s) first BY NAME -- a session id re-points, a name does not. "
        "A holder releases a path it no longer needs with "
        "`session-claim-cli release-artifact artifact <path>`; "
        "`session-claim-cli who-claims-path <path>` lists every holder. "
        "A holder shown without a name is live but not addressable from "
        "here: drop that path and commit the rest -- it frees when that "
        "session commits or releases.",
        file=sys.stderr,
    )
    sys.exit(1)


def _worktree_root_from_cwd() -> str:
    """The repo toplevel, walked up from the process cwd with zero spawns.

    NOT `os.getcwd()`, which is what this used to be. `args.paths` are
    repo-relative and `ceremony.commit_v2` resolves them against
    `main_worktree_root(repo_root)`, so a caller invoked from a SUBDIRECTORY
    made the two roots disagree: `_split_paths_for_commit_v2` probed
    `<cwd>/<repo-relative path>`, missed, and forwarded the miss as
    `params.deleted_paths` -- a negative existence probe becoming a positive
    deletion declaration for a file that was never gone. Both signatures of
    the committer-P0 fall out of that one line
    (`state/audits/2026-08-31-committer-p0-*`).

    Falls back to the cwd when no `.git` is found: this is a path
    computation, not a gate, and the ordinary refusals downstream are what
    report an unresolvable repo.
    """
    here = os.path.abspath(os.getcwd())
    while True:
        if os.path.exists(os.path.join(here, ".git")):
            return here
        parent = os.path.dirname(here)
        if parent == here:
            return os.path.abspath(os.getcwd())
        here = parent


def _split_paths_for_commit_v2(worktree_root: str, paths: Sequence[str]) -> "tuple[List[str], List[str]]":
    """Split `paths` into (present, deleted) relative to `worktree_root`, for
    `ceremony.commit_v2`'s `params.paths`/`params.deleted_paths` split -- a
    distinction the killed `ceremony.commit`'s `stage_paths`/`caller_paths`
    shape never needed (`git add` handled a missing path as a deletion
    transparently).

    A path absent from the worktree is treated as deleted ONLY IF HEAD carries
    it. It used to be treated as deleted unconditionally, and that was the
    committer-P0: a failed existence probe became a positive deletion
    declaration, so a caller invoked from a subdirectory silently deleted every
    path it named, and an untracked new file was silently skipped instead of
    committed (state/audits/2026-08-31-committer-p0-*).

    The root bug is fixed upstream (`_worktree_root_from_cwd`), but a probe can
    still answer False for a file that exists -- `os.path.exists` returns False
    on ANY OSError, including a Windows sharing violation on a file one of the
    ~50 concurrent peers holds open. So the inference itself is closed here:
    absent from BOTH the worktree and HEAD is not a deletion anyone could have
    meant, and it refuses rather than guessing which."""
    present: List[str] = []
    missing: List[str] = []
    for p in paths:
        if not p:
            continue
        if os.path.exists(os.path.join(worktree_root, p)):
            present.append(p)
        else:
            missing.append(p)

    if not missing:
        return present, []

    # One batched spawn, and only when something is actually missing -- the
    # ordinary commit names no missing path and pays nothing.
    tracked = _paths_tracked_at_head(worktree_root, missing)
    deleted = [p for p in missing if p in tracked]
    unknown = [p for p in missing if p not in tracked]
    if unknown:
        for p in unknown:
            print(
                f"BLOCKED: {p} is neither in the worktree nor in HEAD -- "
                "refusing to commit it as a deletion.",
                file=sys.stderr,
            )
        print(
            "Check the path, or run from the repo root. To commit a real "
            "deletion the path must exist in HEAD.",
            file=sys.stderr,
        )
        sys.exit(1)
    return present, deleted


def _paths_tracked_at_head(worktree_root: str, paths: Sequence[str]) -> "set[str]":
    """Which of `paths` HEAD carries, in one spawn.

    Fails CLOSED: if the probe cannot answer, the caller refuses rather than
    inferring a deletion. Treating an unanswerable probe as "not a deletion"
    would reinstate the P0 in its quieter form -- a guess dressed as a fact.

    `-r` (Review: coordinator:code-reviewer Finding 2, 8f787b71-c) -- without
    it, a directory pathspec absent from the worktree but present in HEAD
    matches its single tree-mode (040000) entry by that exact directory
    name, and `_split_paths_for_commit_v2` would classify the directory
    itself as a "deleted file" and forward it into `deleted_paths`, which
    `ceremony.commit_v2` expects to hold file paths only. `-r` expands the
    listing to the tree's recursive file entries (`dir/file.txt`, ...),
    which never exact-match the bare directory name the caller asked about,
    so an absent directory now falls into the `unknown` branch below and is
    refused rather than silently misclassified as a file deletion.
    """
    result = subprocess.run(
        [
            "git",
            "-C",
            worktree_root,
            "ls-tree",
            "-r",
            "-z",
            "--name-only",
            "HEAD",
            "--",
            *paths,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or "").strip() or "git ls-tree failed"
        print(
            "BLOCKED: could not read HEAD to tell a deletion from a bad "
            f"path: {detail}",
            file=sys.stderr,
        )
        sys.exit(1)
    return {line for line in result.stdout.split("\0") if line}


def _is_indeterminate_outcome(exc: RuntimeError) -> bool:
    """True when `exc` (a `RuntimeError` raised by `cc_invoke()`) means the
    dispatch outcome is UNKNOWN — the op may or may not have already
    executed and possibly committed — rather than a clean, determinate
    answer.

    Deliberately narrow, mirroring `_op_is_unregistered`'s own narrow-
    predicate discipline (this file's established pattern — see that
    function's docstring): getting this wrong in the PERMISSIVE direction
    would route a real, determinate failure (a gate declining, an empty
    pathspec — reported by `cc_invoke` as a clean JSON-RPC error envelope
    with a real code) through the reconcile path and could silently mask it
    as "reconcile found nothing, retry is safe" when it should instead
    report the refusal as-is.

    Matches exactly:
      - `cc_invoke.is_timeout_error(exc)` — the client-side `cc_invoke:
        engine timeout after Ns` shape (`_timeout_exceeded_message`). A
        timeout never stops the engine (project CLAUDE.md § Load norm), so
        a mutating ceremony op may already have landed.
      - `"warm dispatch indeterminate"` — the warm transport's OWN
        indeterminate classification (`cc_invoke.py ::
        _apply_warm_envelope`, `WARM_DISPATCH_INDETERMINATE`): a mutating
        op delivered to the warm server but never answered.
      - A malformed/unparseable envelope (`"invoke stdout is not valid
        JSON"`, `"envelope is not a JSON object"`, `"envelope missing
        'result' key"`) — the process ran and produced *something*, but not
        a clean success or a structured error either; neither a "clean
        success" nor an "explicit structured refusal" per this plan's own
        AC8 text.

    Does NOT match: `-32601`/Method-not-found (handled separately by
    `_op_is_unregistered`, before this predicate ever runs — request never
    reached a handler), a real JSON-RPC error envelope carrying an actual
    op-level refusal (`"op returned JSON-RPC error envelope"` with a
    non-indeterminate code — a gate decline, a validation error), or any
    pre-dispatch failure (engine-root resolution, params serialization,
    engine-won't-start) — none of those leave the outcome in doubt."""
    from cc_invoke import is_timeout_error

    if is_timeout_error(exc):
        return True
    text = str(exc)
    return (
        "warm dispatch indeterminate" in text
        or "invoke stdout is not valid JSON" in text
        or "envelope is not a JSON object" in text
        or "envelope missing 'result' key" in text
    )


def _resolve_pre_sha_for_reconcile(worktree_root: str) -> Optional[str]:
    """`git rev-parse HEAD`, resolved BEFORE dispatch, for the reconcile's
    own bounded-range search (`_reconcile_landed_despite_failure`'s
    `pre_sha` argument). Returns `None` on any failure (no commits yet, the
    call itself timed out/errored) — that function's own fallback path
    already handles a missing `pre_sha` safely via an unfiltered, walk-
    bounded `git rev-list --max-count` probe, so failing open to `None`
    here is correct, not a gap."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=worktree_root,
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    sha = result.stdout.strip()
    return sha or None


def _reconcile_after_indeterminate(
    args: "Args",
    worktree_root: str,
    attempt_trailer: str,
    pre_sha: Optional[str],
    exc: Exception,
) -> None:
    """The AC8 mechanism itself: on an indeterminate `ceremony.commit_v2`
    outcome, search recent branch history for a commit already carrying
    this call's own `Attempt-Id:` trailer BEFORE reporting anything.

    Reuses `commit_reconcile._reconcile_landed_despite_failure` — the exact
    bounded-log-search primitive named in this plan's dispatch brief as
    prior art — rather than re-implementing a `git log`/`git rev-list`
    bound here: same function, same collision-free-trailer safety argument,
    same "a match inside the window is ours no matter how wide the window
    is" reasoning (that function's own docstring).

    `repo_root` for that call is the git COMMON DIR, matching
    `_commit_via_pipeline_fallback`'s own resolution (this handler's own
    established idiom) — not the worktree.

    Exits 0 with the reconciled sha on FOUND (a slow success, never a
    failure); exits 1 naming the original exception plus "reconcile found
    nothing, retry is safe" on ABSENT. Never retries a mutation itself
    (Anti-scope, this plan)."""
    _bootstrap_engine()
    common_dir = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        cwd=worktree_root,
        capture_output=True,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if common_dir.returncode != 0:
        print(f"ERROR: ceremony.commit_v2: {exc}", file=sys.stderr)
        print(
            "Reconcile could not run: git common dir unresolved "
            f"({(common_dir.stderr or '').strip()}). Do not assume the "
            "commit landed; verify manually before retrying.",
            file=sys.stderr,
        )
        sys.exit(1)

    resolved = Path(common_dir.stdout.strip())
    if not resolved.is_absolute():
        resolved = Path(worktree_root) / resolved

    require_engine_on_path(__file__)
    from coordinator_core.ops.ceremony.commit_reconcile import (
        _reconcile_landed_despite_failure,
    )

    # A reconcile fired on a CLIENT timeout races the write it is looking for.
    # The client's deadline expiring is not evidence the engine has stopped --
    # that is the entire premise of the hazard this reconcile exists to close.
    # So re-probe across the op's own remaining budget before concluding
    # anything: it converts "has not happened yet" into "found" without
    # weakening the rule below, and costs nothing when the commit is genuinely
    # absent. Bounded, and never a retry of the mutation itself.
    probe = _reconcile_landed_despite_failure(resolved, attempt_trailer, pre_sha, args.paths)
    if probe.sha is None:
        deadline = time.monotonic() + _RECONCILE_SETTLE_SECS
        while probe.sha is None and time.monotonic() < deadline:
            time.sleep(_RECONCILE_POLL_SECS)
            probe = _reconcile_landed_despite_failure(
                resolved, attempt_trailer, pre_sha, args.paths
            )

    if probe.sha is not None:
        print(
            f"committed sha={probe.sha} — ceremony.commit_v2 exceeded its deadline "
            f"({exc}), but the commit is confirmed landed via reconcile "
            "(Attempt-Id trailer found in history): this is a slow success, "
            "not a failure.",
            file=sys.stderr,
        )
        sys.exit(0)

    # ABSENCE IS NOT A DETERMINATE NEGATIVE. Presence of the Attempt-Id proves
    # the commit landed; absence cannot distinguish "did not happen" from "has
    # not happened yet", because the engine may still be inside its own budget
    # writing it. Reporting absence as "a retry is safe" is an INSTRUCTION, and
    # it is wrong exactly when the hazard is real -- claude-klabauter-15 followed
    # it at ~20:20 against a commit that had in fact landed (455cbdf53), and
    # only escaped a duplicate because the retry found the pathspec clean.
    # See state/lessons/2026-08-26-a-reconcile-that-runs-too-soon-says-retry-
    # is-safe.md. The outcome here is UNKNOWN and must read as unknown.
    print(f"ERROR: ceremony.commit_v2: {exc}", file=sys.stderr)
    print(
        "Reconcile found no commit carrying this attempt's Attempt-Id trailer "
        f"after re-probing for {_RECONCILE_SETTLE_SECS:.0f}s "
        f"(decline={probe.decline!r}). This is UNKNOWN, not a confirmed "
        "failure: the engine may still have been writing when the client's "
        "deadline expired. VERIFY with `git log` before re-running -- a blind "
        "retry can double-commit.",
        file=sys.stderr,
    )
    sys.exit(1)


#: How long the AC8 reconcile keeps re-probing for its Attempt-Id after a
#: client-side timeout, and how often. The engine may still be inside its own
#: ceremony budget when the client gives up, so a single probe reads a race as
#: a determinate negative. Sized above the 2.0s ceremony ceiling so a commit
#: still landing when the client bailed is normally observed rather than
#: reported unknown.
_RECONCILE_SETTLE_SECS = 3.0
_RECONCILE_POLL_SECS = 0.25


def _commit_message_argv(subject: str, body: str) -> List[str]:
    """Build the `git commit` message args: `-m <subject>` alone, or `-m
    <subject> -m <body>` when a body is present — git renders each `-m` as
    its own paragraph, so this is the standard subject/body commit shape,
    not a string concatenation. Never used to replace the subject; the body
    is strictly additive."""
    if body:
        return ["-m", subject, "-m", body]
    return ["-m", subject]


# ---------------------------------------------------------------------------
# git helpers
# ---------------------------------------------------------------------------

def _git_output_lines(git_args: Sequence[str]) -> List[str]:
    try:
        result = subprocess.run(["git", *git_args], capture_output=True, text=True, check=False)
    except OSError:
        return []
    if result.returncode != 0:
        return []
    return result.stdout.splitlines()


def _git_rev_parse_head() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
        )
    except OSError:
        return "INITIAL"
    if result.returncode != 0:
        return "INITIAL"
    return result.stdout.strip()


def _current_dirty_files() -> List[str]:
    """Union of `git diff --name-only HEAD` and `git ls-files --others
    --exclude-standard`, sort -u'd. Deliberately two git commands, not
    `git status --porcelain` — porcelain collapses an untracked directory to
    `dir/` (see coordinator_core.session.scope module negative-spec)."""
    diff = _git_output_lines(["diff", "--name-only", "HEAD"])
    others = _git_output_lines(["ls-files", "--others", "--exclude-standard"])
    return sorted({f for f in (diff + others) if f})


def _own_touched_paths_for_banner() -> "tuple[Optional[Set[str]], str]":
    """Best-effort resolve of THIS session's own `touched.txt`, for
    `_scoped_commit_suggestion`'s attribution banner ONLY — presentation,
    never a filter. It must never change which paths the generated script
    commits (2026-08-26 follow-up requirement); it only labels them so an
    operator skimming a dozens-of-entries list can see how many are NOT
    theirs at a glance.

    Returns `(None, reason)` on ANY resolution failure — no session id in
    the usual env-var chain, no sessions dir, no touched.txt, an unreadable
    touched.txt — so the caller renders an explicit "attribution
    unavailable, every path below is unattributed" banner. A missing
    signal must never render as "0 belong to other sessions": that is a
    false all-clear manufactured from absent data, the same failure class
    this whole mitigation exists to prevent. Deliberately does NOT call
    this file's own heavier `resolve_session_id()` (module-level, ~line
    1056) — that function's own liveness-probe fallback and stderr/exit
    side effects are wrong for a presentation-only best-effort lookup; this
    reads the same env-var chain `do_scoped` checks first, with no probe
    and no side effect on failure."""
    session_id = (
        os.environ.get("COORDINATOR_SESSION_ID")
        or os.environ.get("CLAUDE_SESSION_ID")
        or os.environ.get("CLAUDE_CODE_SESSION_ID")
        or ""
    )
    if not session_id:
        return None, (
            "no session id found (COORDINATOR_SESSION_ID/CLAUDE_SESSION_ID/"
            "CLAUDE_CODE_SESSION_ID all unset)"
        )
    try:
        from coordinator_core.session import core as cs_core  # noqa: PLC0415
    except ImportError as exc:
        return None, f"session module unavailable ({exc})"
    try:
        base = cs_core.sessions_dir()
    except OSError as exc:
        return None, f"sessions dir unresolved ({exc})"
    if not base:
        return None, "sessions dir unresolved (empty)"
    touched_path = os.path.join(base, session_id, "touched.txt")
    if not os.path.isfile(touched_path):
        return None, f"no touched.txt at {touched_path}"
    try:
        lines = Path(touched_path).read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return None, f"touched.txt unreadable ({exc})"
    return {ln.strip() for ln in lines if ln.strip()}, "ok"


def _scoped_commit_suggestion(subject: str) -> str:
    """Build a copy-pasteable retry command for the concurrency-refusal deny
    message in `do_scoped` — the rung-B shape
    (`docs/wiki/bash-guard-threat-model.md`): reproduce the caller's own
    situation in corrected form rather than naming a destination with no
    route.

    2026-08-26 fix (C5, this chunk): retires the tempfile-script generator
    this function used to write to disk. That workaround existed solely
    because there was no module a printed suggestion could invoke directly
    — first the killed `ceremony.scoped_git_commit` CLI, then nothing at
    all (see git history for the retired `run_commit_pipeline`-invoking
    generator this replaces). Its own docstring already carried the
    incident this class of drift produces: a "verified runnable" claim true
    when written, false from the day its target was killed out from under
    it, and nothing re-verified it in between — eleven days of shipping a
    dead retry command to every caller who hit this refusal.

    `do_pathspec`'s `-- <paths>` form now routes through the
    `ceremony.commit_v2` op (docs/plans/2026-08-27-something-must-commit-
    ceremony-commit-v2.md § C3, `coordinator_core/ops/ceremony/
    commit_v2.py`), so the correct retry command is simply THIS SAME script
    invoked with `-- <paths>` — no tempfile, no PYTHONPATH/interpreter
    resolution, no Windows/POSIX shell-form branching to keep in sync with a
    generated payload. The caller already knows how to invoke
    `coordinator-safe-commit`; this reproduces that exact shape, corrected,
    which is also why there is nothing left here for a killed-op class of
    drift to attach to.

    Params come from `_current_dirty_files()` (this session's own dirty
    tree, the same source `do_scoped` itself stages from) — the WHOLE
    shared working tree's dirty set, not necessarily what the operator
    intends to commit (a dirty tree may hold a sibling session's files too).
    The printed placeholder (`<trim-to-your-own-paths>`) both names that
    obligation and keeps the line non-executable verbatim — there is no
    generated script left to gate on a hand-flipped confirmation sentinel,
    so non-executability by construction is what stands in its place. The
    attribution banner beneath it distinguishes this session's own
    touched.txt entries (`_own_touched_paths_for_banner`) from everything
    else, so an operator skimming a dozens-of-entries dirty tree can see at
    a glance which lines are not theirs before hand-picking the trimmed
    pathspec."""
    dirty = _current_dirty_files()
    paths = dirty if dirty else ["<your-paths>"]

    # Attribution banner (presentation only). `foreign` is either "provably
    # not in this session's own touched.txt" or, when that signal is
    # unavailable, EVERY path — a missing signal must never render as "0
    # foreign", which would be a false all-clear manufactured from absent
    # data.
    own_touched, own_touched_reason = _own_touched_paths_for_banner()
    if own_touched is None:
        foreign = list(paths)
        attribution_line = (
            "attribution unavailable (%s) — every path below is treated as "
            "unattributed, not as \"none foreign\"" % own_touched_reason
        )
    else:
        foreign = [p for p in paths if p not in own_touched]
        attribution_line = "%d of %d paths below are NOT in this session's own touched.txt" % (
            len(foreign),
            len(paths),
        )
    foreign_set = sorted(set(foreign))

    lines = [
        "  coordinator-safe-commit %s -- <trim-to-your-own-paths>"
        % shlex.quote(subject or "<subject>"),
        "",
        "  # %s" % attribution_line,
    ]
    for p in paths:
        flag = " [foreign/unattributed]" if p in foreign_set else ""
        lines.append("  #   %s%s" % (p, flag))
    return "\n".join(lines)


def _git_add(paths: Iterable[str]) -> None:
    paths = [p for p in paths if p]
    if not paths:
        return
    subprocess.run(["git", "add", "--", *paths], check=True)


def _git_add_all_blanket() -> None:
    """Port of `( export _COORDINATOR_SAFE_COMMIT_INTERNAL_BLANKET=1 && git
    add -A )` — the ONE sanctioned `git add -A` path (SC-DR-014). Runs `git
    add -A` in a subprocess carrying the internal env-var marker so the
    parent process's own environment never leaks the marker into any other
    code path (mirrors the bash subshell's scope-safety rationale — a
    subprocess dies with the call on any exit, same guarantee)."""
    env = dict(os.environ)
    env["_COORDINATOR_SAFE_COMMIT_INTERNAL_BLANKET"] = "1"
    subprocess.run(["git", "add", "-A"], check=True, env=env)


def _git_diff_cached_names() -> List[str]:
    return _git_output_lines(["diff", "--cached", "--name-only"])


def _git_diff_cached_numstat() -> List[str]:
    return _git_output_lines(["diff", "--cached", "--numstat"])


def _git_reset_unstage(path: str) -> None:
    subprocess.run(["git", "reset", "-q", "HEAD", "--", path], check=False)


def _git_reset_unstage_many(paths: List[str]) -> None:
    """Batched form of `_git_reset_unstage`: one `git reset -q HEAD --
    <paths...>` spawn for the whole exclusion set instead of one per path.
    `check=False` either way -- a pathspec git can't resolve is silently
    skipped by git itself, same as a single bad path was silently ignored
    per-call before."""
    if not paths:
        return
    subprocess.run(["git", "reset", "-q", "HEAD", "--", *paths], check=False)


def _git_diff_cached_is_empty() -> bool:
    result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"], capture_output=True, check=False
    )
    return result.returncode == 0


def _git_ls_files_pathspec(pathspec: str) -> List[str]:
    """Port of the bash `git ls-files -- "$ps"; git ls-files --others
    --exclude-standard -- "$ps"` two-command union used to expand a
    pathspec to concrete tracked + untracked files. Order matches bash
    (tracked first, then untracked); no sort/dedup — mirrors the original."""
    tracked = _git_output_lines(["ls-files", "--", pathspec])
    untracked = _git_output_lines(["ls-files", "--others", "--exclude-standard", "--", pathspec])
    return [f for f in (tracked + untracked) if f]


def _validate_pathspec(pathspec: str) -> bool:
    """Port of `validate_pathspec`: a pathspec is valid iff `git ls-files --
    <pathspec>` exits 0 (git accepts the pathspec syntax), independent of
    whether it matches any files."""
    try:
        result = subprocess.run(
            ["git", "ls-files", "--", pathspec], capture_output=True, text=True, check=False
        )
    except OSError:
        return False
    return result.returncode == 0


def _first_invalid_pathspec(pathspecs: List[str]) -> Optional[str]:
    """Validates a list of pathspecs with ONE `git ls-files --` call in the
    common (all-valid) case: N -> 1 spawns. `git ls-files` exits non-zero if
    ANY pathspec in the batch is malformed, so the batched call can positively
    confirm "all valid" but cannot identify WHICH entry failed on the invalid
    path -- falls back to per-item `_validate_pathspec` only then, to keep the
    existing per-item error message without paying an N-spawn cost on the
    (overwhelmingly common) all-valid path. Returns None if every pathspec is
    valid, else the first invalid one (matching this module's existing
    fail-on-first-bad-entry contract at both call sites)."""
    if not pathspecs:
        return None
    try:
        batch_result = subprocess.run(
            ["git", "ls-files", "--", *pathspecs], capture_output=True, text=True, check=False
        )
    except OSError:
        batch_result = None
    if batch_result is not None and batch_result.returncode == 0:
        return None
    for ps in pathspecs:
        if not _validate_pathspec(ps):
            return ps
    return None


_SCOPE_ITEM_RE = re.compile(r"^\s+-\s+(.+)$")
_TOPLEVEL_KEY_RE = re.compile(r"^[a-zA-Z]")
_SCOPE_KEY_RE = re.compile(r"^scope:\s*$")


def _parse_scope_from_frontmatter(fpath: str) -> Optional[List[str]]:
    """Port of `parse_scope_from_frontmatter <file>`: reads lines between
    the first two `---` YAML-frontmatter delimiters, finds the `scope:`
    list key, and collects its `  - value` items. Returns None (having
    already printed the ERROR) on missing file / missing / empty scope:
    field — mirrors the bash function's `return 1` contract."""
    if not os.path.isfile(fpath):
        print(f"ERROR: Handoff file not found: {fpath}", file=sys.stderr)
        return None
    try:
        raw_lines = Path(fpath).read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        print(f"ERROR: Handoff file not found: {fpath} ({exc})", file=sys.stderr)
        return None

    in_frontmatter = False
    started = False
    in_scope = False
    found_scope = False
    scope_entries: List[str] = []

    for raw_line in raw_lines:
        # Strip trailing CR for CRLF-encoded files (Windows handoffs).
        line = raw_line[:-1] if raw_line.endswith("\r") else raw_line

        if line == "---":
            if not started:
                started = True
                in_frontmatter = True
                continue
            elif in_frontmatter:
                in_frontmatter = False
                break

        if not in_frontmatter:
            continue

        if _SCOPE_KEY_RE.match(line):
            in_scope = True
            found_scope = True
            continue

        if in_scope:
            m = _SCOPE_ITEM_RE.match(line)
            if m:
                scope_entries.append(m.group(1))
            elif _TOPLEVEL_KEY_RE.match(line):
                in_scope = False

    if not found_scope:
        print(f"ERROR: No 'scope:' field found in YAML frontmatter of {fpath}", file=sys.stderr)
        return None
    if not scope_entries:
        print(f"ERROR: 'scope:' field is present but empty in {fpath}", file=sys.stderr)
        return None
    return scope_entries


# ---------------------------------------------------------------------------
# Overlap-gate lock + scoped overlap-check helpers (Fix 6). Ported in C2a as
# a self-contained primitive; C2b wires it into --scope-from /
# --include-orphans, the only bash callers.
# ---------------------------------------------------------------------------

def with_overlap_lock(base: str, cs_core, body_fn, *body_args, timeout_s: int = 10):
    """Port of bash `_with_overlap_lock <body_fn> [args...]`: acquire the
    per-repo overlap-gate lock via atomic mkdir, run body_fn(*body_args),
    release. Propagates body_fn's return value; a SystemExit raised by
    body_fn propagates unchanged (mirrors bash's exit-code passthrough,
    the Staff Engineer finding 1). flock is NOT used (unavailable on Git Bash for
    Windows); mkdir is universal.

    Spec backlink: plans/safe-commit-fixes-5-and-6.md § Fix 6 — mkdir-lock.
    """
    lock_dir = os.path.join(base, ".overlap-gate.lock")
    os.makedirs(base, exist_ok=True)
    waited = 0
    while True:
        try:
            os.mkdir(lock_dir)
            break
        except FileExistsError:
            held_pid = ""
            try:
                held_pid = Path(os.path.join(lock_dir, "pid")).read_text(encoding="utf-8").strip()
            except OSError:
                held_pid = ""
            if held_pid and not cs_core.pid_alive(held_pid):
                print(f"WARNING: reaping stale overlap-gate lock (dead PID {held_pid})", file=sys.stderr)
                shutil.rmtree(lock_dir, ignore_errors=True)
                continue
            if waited >= timeout_s:
                print(
                    f"ERROR: overlap-gate lock timeout ({timeout_s}s); held by PID {held_pid or '?'}",
                    file=sys.stderr,
                )
                sys.exit(1)
            time.sleep(1)
            waited += 1

    try:
        with open(os.path.join(lock_dir, "pid"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(str(os.getpid()))
    except OSError:
        pass

    try:
        return body_fn(*body_args)
    finally:
        shutil.rmtree(lock_dir, ignore_errors=True)


def _iter_peer_scope_dirs(base: str, session_id: str):
    """Yield (peer_id, active-scope.txt path) for every live-looking peer
    session dir under base, excluding self / .archive / .agents — mirrors
    the bash `for peer_sdir in "${base}"/*/` loop shared by both overlap
    helpers below."""
    if not base or not os.path.isdir(base):
        return
    for entry in sorted(os.listdir(base)):
        peer_dir = os.path.join(base, entry)
        if not os.path.isdir(peer_dir):
            continue
        if entry == session_id or entry in (".archive", ".agents"):
            continue
        peer_scope = os.path.join(peer_dir, "active-scope.txt")
        if not os.path.isfile(peer_scope):
            continue
        yield entry, peer_scope


def _publish_scope_and_check_overlap(
    active_scope_file: str,
    base: str,
    session_id: str,
    handoff_files: Sequence[str],
    scope_set: Set[str],
) -> None:
    """Port of `_do_scope_from_overlap_check_and_publish`: write this
    session's declared handoff scope to active-scope.txt, then check every
    live peer session's active-scope.txt for a path already in scope_set.
    Runs inside with_overlap_lock — write + check are atomic (no TOCTOU
    window). exits 1 on first collision found (matches bash `exit 1` inside
    the loop, which the caller's SystemExit propagation now carries)."""
    try:
        with open(active_scope_file, "w", encoding="utf-8", newline="\n") as fh:
            for f in handoff_files:
                if f:
                    fh.write(f + "\n")
    except OSError:
        pass

    for peer_id, peer_scope in _iter_peer_scope_dirs(base, session_id):
        try:
            lines = Path(peer_scope).read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for path in lines:
            if path and path in scope_set:
                print(
                    f"ERROR: scope overlaps with session {peer_id}'s handoff at {path}; "
                    "resolve via explicit-path commit.",
                    file=sys.stderr,
                )
                sys.exit(1)


def _append_orphans_and_check_overlap(
    active_scope_file: str,
    base: str,
    session_id: str,
    orphan_resolved: Sequence[str],
    union_scope_set: Set[str],
) -> None:
    """Port of `_do_scoped_orphan_overlap_check_and_publish`: append
    resolved --include-orphans paths to active-scope.txt (additive in
    combined-mode, initial write in pure default-mode — caller already
    created the empty file), then check the union (handoff scope + orphans)
    against every live peer session's active-scope.txt."""
    if active_scope_file and orphan_resolved:
        try:
            with open(active_scope_file, "a", encoding="utf-8", newline="\n") as fh:
                for f in orphan_resolved:
                    fh.write(f + "\n")
        except OSError:
            pass

    for peer_id, peer_scope in _iter_peer_scope_dirs(base, session_id):
        try:
            lines = Path(peer_scope).read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for path in lines:
            if path and path in union_scope_set:
                print(
                    f"ERROR: --include-orphans: '{path}' is already claimed by session {peer_id}.",
                    file=sys.stderr,
                )
                print(
                    "Resolve: wait for that session to finish, or use explicit-path commit without the helper.",
                    file=sys.stderr,
                )
                sys.exit(1)


# ---------------------------------------------------------------------------
# Structured pre-commit summary printer
# ---------------------------------------------------------------------------

def print_summary(
    staged_count: int,
    staged_list: Sequence[str],
    orphan_count: int,
    orphan_list: Sequence[str],
    other_count: int,
    other_list: Sequence[str],
) -> None:
    print("", file=sys.stderr)
    print(f"Scope: {staged_count} file(s) staged", file=sys.stderr)
    for f in staged_list:
        if f:
            print(f"  {f}", file=sys.stderr)

    print(f"Orphans (dirty, no session claim): {orphan_count} file(s) — NOT STAGED", file=sys.stderr)
    for f in orphan_list:
        if f:
            print(f"  {f}", file=sys.stderr)

    print(f"Other-session-owned (excluded): {other_count} file(s)", file=sys.stderr)
    for f in other_list:
        if f:
            print(f"  {f}", file=sys.stderr)
    print("", file=sys.stderr)


# ---------------------------------------------------------------------------
# Session-ID resolution
# ---------------------------------------------------------------------------

def resolve_session_id(cs_core, cs_liveness) -> str:
    """Priorities 0-3 (COORDINATOR_SESSION_ID > CLAUDE_SESSION_ID >
    CLAUDE_CODE_SESSION_ID > sentinel w/ tier-4 ambiguity guard) are all
    handled by coordinator_core.session.core.resolve_session_id — that port
    already folds in the bash caller's own Phase-1 stale-sentinel pre-check
    (0-live + session-dir-still-present -> untrusted -> empty), so a single
    call covers the full 4-tier chain byte-for-byte. Priority 4 (the
    live-session-count auto-detect fallback) is this function's own
    responsibility — it is NOT part of the lib's resolve_session_id.

    Fail-closed contract: a liveness-probe exception must NEVER be silently
    reinterpreted as "0 live sessions" — that degrade previously fed a
    distrusted empty set into the len==0 ("no live session", safe-looking)
    and len==1 (an identity derived from data the probe just failed to
    produce) branches below, on the commit hot path every live session
    shares. This mirrors the two sibling liveness gates in this file
    (the --blanket F0/F1 foreign-path subtract and the default-mode
    >1-live-session gate), which already abort rather than degrade.
    COORDINATOR_ACCEPT_LIVENESS_PROBE_FAILURE=1 restores the old
    degrade-to-empty behavior for an operator who needs a way through the
    commit hot path with liveness genuinely unavailable; never enabled
    implicitly."""
    sid = cs_core.resolve_session_id()
    if sid:
        return sid

    base = cs_core.sessions_dir()
    if not base or not os.path.isdir(base):
        _print_no_live_session_error()
        return ""

    # Review: code-reviewer — Finding 2: this is a fail-closed safety gate —
    # an exception here must not silently degrade to "0 live sessions"
    # (which reads as the safe case and can misresolve session identity from
    # data the probe was just unable to produce). Abort instead of guessing,
    # matching the F0/F1 subtract (:946) and the default-mode >1-live-session
    # gate (:1085).
    try:
        live_sessions = sorted(cs_liveness.live_session_ids())
    except Exception as exc:
        if os.environ.get("COORDINATOR_ACCEPT_LIVENESS_PROBE_FAILURE") == "1":
            print(
                f"WARNING: session-liveness check failed ({exc}); "
                "COORDINATOR_ACCEPT_LIVENESS_PROBE_FAILURE=1 is set — resolving "
                "session identity from an UNTRUSTED liveness read (treating as 0 "
                "live sessions). Session misidentification is possible.",
                file=sys.stderr,
            )
            live_sessions = []
        else:
            print(
                f"ERROR: cannot verify session liveness ({exc}); refusing to resolve "
                "session identity from an untrusted liveness read. Set "
                "COORDINATOR_ACCEPT_LIVENESS_PROBE_FAILURE=1 to bypass at your own risk "
                "(degrades to treating this as 0 live sessions), or bypass the helper "
                "with explicit-path commit:",
                file=sys.stderr,
            )
            print('  git add -- <your-paths> && git commit -m "<subject>" -- <your-paths>', file=sys.stderr)
            sys.exit(1)

    if len(live_sessions) == 1:
        return live_sessions[0]
    if len(live_sessions) == 0:
        _print_no_live_session_error()
        return ""
    print(
        "ERROR: Multiple live sessions found — cannot auto-detect session ID. "
        f"Set CLAUDE_SESSION_ID explicitly. Candidates: {' '.join(live_sessions)}",
        file=sys.stderr,
    )
    print(
        "If session-ownership is misidentifying your work (your files blocked, "
        "others' files swept), the safer fallback is to bypass the helper:",
        file=sys.stderr,
    )
    print('  git add -- <your-paths> && git commit -m "<subject>" -- <your-paths>', file=sys.stderr)
    return ""


def _print_no_live_session_error() -> None:
    print(
        "ERROR: No live session found. Set CLAUDE_SESSION_ID or ensure a session was initialized.",
        file=sys.stderr,
    )
    print("Fallback: bypass the helper with explicit-path commit:", file=sys.stderr)
    print('  git add -- <your-paths> && git commit -m "<subject>" -- <your-paths>', file=sys.stderr)


# ---------------------------------------------------------------------------
# BLANKET MODE
# ---------------------------------------------------------------------------

def _blanket_invoking_command_allowed() -> bool:
    """Carve-out enforcement: --blanket is only valid from authorized sweep
    ceremonies. Primary signal is CLAUDE_INVOKING_COMMAND; fallback inspects
    the parent process's command line (Linux /proc, else `ps -p <ppid> -o
    command=`) for one of the ceremony markers, matching bash's dual-path
    check exactly."""
    invoking = os.environ.get("CLAUDE_INVOKING_COMMAND", "")
    if invoking in BLANKET_ALLOWED_COMMANDS:
        return True

    ppid = os.getppid()
    ppid_cmd = ""
    proc_cmdline = f"/proc/{ppid}/cmdline"
    if os.path.isfile(proc_cmdline):
        try:
            with open(proc_cmdline, "rb") as fh:
                ppid_cmd = fh.read().replace(b"\x00", b" ").decode("utf-8", errors="replace")
        except OSError:
            ppid_cmd = ""
    else:
        # Review: code-reviewer — Finding 4: `ps` reliably existed under the
        # prior bash-under-git-bash implementation (MSYS ships its own
        # ps.exe); now that this runs as native Python, `ps` may not be on
        # PATH on native Windows. Try psutil first (already a stated
        # dependency elsewhere in this codebase — see
        # coordinator/bin/probe-memory-headroom.py) as a Windows-native
        # fallback before falling through to `ps`. Neither being available
        # fails closed (rejects the blanket carve-out), which is the
        # documented accepted gap, not a security hole.
        ppid_cmd = ""
        try:
            import psutil  # noqa: PLC0415 — optional, Windows-native fallback only

            ppid_cmd = " ".join(psutil.Process(ppid).cmdline())
        except Exception:
            ppid_cmd = ""
        if not ppid_cmd:
            try:
                result = subprocess.run(
                    ["ps", "-p", str(ppid), "-o", "command="],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                ppid_cmd = result.stdout if result.returncode == 0 else ""
            except OSError:
                ppid_cmd = ""

    return any(marker in ppid_cmd for marker in BLANKET_ALLOWED_PPID_MARKERS)


def _blanket_check_destructive_shape(subject: str) -> None:
    """Port of the nested `_blanket_check_destructive_shape`: soft-warn
    through 2026-06-01, then hard-fail (>= 3 files with deletion-heavy diffs
    AND no plan/handoff/PR/lessons/queue reference in the subject).
    `sys.exit(3)` here terminates the whole process (do_blanket -> main),
    exactly matching bash's `exit 3` inside a nested function terminating
    the calling script, not just the function.
    Spec backlink: archive/improvement-queue/coordinator-improvement-queue.md
    (2026-05-16, blanket commit shape-check entry)."""
    if os.environ.get("COORDINATOR_OVERRIDE_BLANKET_SHAPE") == "1":
        return
    if _DESTRUCTIVE_SHAPE_REF_RE.search(subject):
        return

    heavy_count = 0
    for line in _git_diff_cached_numstat():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        added_raw, deleted_raw = parts[0], parts[1]
        if not (added_raw.isdigit() and deleted_raw.isdigit()):
            continue  # binary files report "-"/"-" — skipped, matches bash's ^[0-9]+$ guard
        added, deleted = int(added_raw), int(deleted_raw)
        if deleted >= 10 and deleted > added:
            heavy_count += 1

    if heavy_count < 3:
        return

    if os.environ.get("COORDINATOR_BLANKET_SHAPE_STRICT") == "1":
        print(
            f"FAIL: blanket-commit destructive-shape gate: {heavy_count} files with "
            "deletion-heavy diffs and no plan/handoff/PR/lessons/queue reference in subject.",
            file=sys.stderr,
        )
        print(f"  Subject: {subject}", file=sys.stderr)
        print(
            "  Set COORDINATOR_OVERRIDE_BLANKET_SHAPE=1 to bypass, or add a reference token to the subject.",
            file=sys.stderr,
        )
        sys.exit(3)

    print(
        f"WARN: blanket-commit destructive-shape: {heavy_count} files with deletion-heavy diffs; "
        "subject lacks plan/handoff/PR/lessons/queue reference.",
        file=sys.stderr,
    )
    print(f"  Subject: {subject}", file=sys.stderr)
    print(
        "  This warning becomes a hard fail after 2026-06-01. Add a reference token now to "
        "suppress, or set COORDINATOR_OVERRIDE_BLANKET_SHAPE=1.",
        file=sys.stderr,
    )


def do_blanket(session_id: str, args: "Args", cs_core, cs_liveness, cs_claims) -> None:
    """Port of `do_blanket`. Stages everything (the one sanctioned `git add
    -A` path), subtracts sibling-claimed paths (F0/F1), runs the
    destructive-shape gate, then commits under the Sentinel-1/Sentinel-2
    no-op-commit FAIL contract.

    Fail-closed contract on F0/F1: own_set/sibling_set resolution failures
    (unreadable touched.txt, a raising claims/liveness call) abort the
    commit rather than proceeding with an incomplete set — the subtract IS
    the only correction on this path, so a partial set is unsafe, not
    merely degraded. COORDINATOR_BLANKET_ACCEPT_FOREIGN=1 skips the whole
    subtract as the escape hatch. Negative-spec: a touched.txt that simply
    does not exist is a normal empty-set case (a session that has touched
    nothing) and must NOT abort — only a read/resolution error does. An
    absent session_id (own_set/agent-touched resolution) is likewise a
    normal empty-identity case, not a failure, and must NOT abort."""
    if not _blanket_invoking_command_allowed():
        print(
            "ERROR: --blanket is only valid from authorized sweep ceremonies: "
            "/workstream-start, /update-docs, relay-protocol, or /distill (distillation).",
            file=sys.stderr,
        )
        print(
            "Use scoped staging (default) or COORDINATOR_OVERRIDE_SCOPE=1 for emergencies.",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.dry_run:
        # Preview the git-add-A candidate set without mutating the index —
        # the F0/F1 foreign-path subtract and destructive-shape gate both
        # act on the staged index, so a true preview of their outcome would
        # require actually staging; a dry-run's contract is "no git add or
        # commit executed", so this reports the pre-subtract dirty-file
        # union instead (may overcount by any sibling-claimed paths F0/F1
        # would otherwise subtract).
        dirty = _current_dirty_files()
        print(f"DRY RUN — blanket: would stage {len(dirty)} file(s) via 'git add -A':", file=sys.stderr)
        for f in dirty:
            print(f"  {f}", file=sys.stderr)
        print(f"Would commit with subject: {args.subject}", file=sys.stderr)
        print("(no git add or commit executed)", file=sys.stderr)
        sys.exit(0)

    invoking = os.environ.get("CLAUDE_INVOKING_COMMAND", "")
    base = cs_core.sessions_dir()
    if base and session_id:
        # `ensure_session`, not `os.makedirs`: `<base>/<session_id>` IS a
        # session directory, and creating it without a `meta.json` record is
        # what left sessions invisible to `liveness.live_session_ids` and
        # unreapable by `ops/session/reap.py`. The ceremony runs in a real
        # session, so the record belongs here -- unlike a guard's audit log,
        # which takes `_override_log_path`'s `no-session` bucket instead.
        sdir = cs_core.ensure_session(session_id, sessions_base=base)
        log_file = os.path.join(sdir, "blanket-invocations.log")
        try:
            with open(log_file, "a", encoding="utf-8", newline="\n") as fh:
                fh.write(f"{cs_core.now_iso()} invoking_command={invoking or 'unknown'}\n")
        except OSError:
            pass

    # Sentinel 1: capture HEAD before commit to detect silent no-ops.
    pre_head = _git_rev_parse_head()
    _git_add_all_blanket()

    # ---------------------------------------------------------------------
    # F0/F1: Foreign-path subtract — remove sibling-EM-claimed paths from
    # the staged index so a blanket sweep captures orphans but never
    # absorbs a concurrent sibling EM's in-flight files.
    # Fail-closed contract: own_set and sibling_set resolution (touched.txt
    # reads, my_agent_touched(), live_session_ids()) must never silently
    # degrade to an incomplete set — an incomplete own_set strips "own
    # wins" and can drop a legitimately-owned staged path as a sibling's;
    # an incomplete sibling_set can let a live sibling's in-flight file get
    # absorbed into this commit. Any resolution failure aborts the
    # --blanket commit. A touched.txt simply not existing (a session that
    # has touched nothing) is a normal empty-set case, NOT a failure, and
    # must not abort.
    # Escape hatch: COORDINATOR_BLANKET_ACCEPT_FOREIGN=1 skips the whole
    # subtract (own_set/sibling_set resolution included), the same escape
    # named in every abort message below.
    # Genesis-repo guard: no HEAD yet means no live siblings are possible
    # (single-operator bootstrap) AND `git reset HEAD` would error without
    # a HEAD — skip the subtract entirely.
    # Spec backlink: docs/plans/2026-06-22-authorized-blanket-orphan-capture-not-sibling-sweep.md § C1a F0/F1.
    # ---------------------------------------------------------------------
    subtracted_count = 0
    if os.environ.get("COORDINATOR_BLANKET_ACCEPT_FOREIGN") != "1" and pre_head != "INITIAL":
        # do_blanket's own signature is not threaded with cs_scope (it is
        # called positionally by existing tests with 5 args) — local import,
        # same idiom as this file's other in-function imports (e.g.
        # `from coordinator_core.ops.ceremony import git_native` below).
        # `_git_root` (distinct from the injected `cs_core`, which some
        # callers stub with a sessions_dir()/now_iso()-only double) is used
        # only for the sibling-mtime resolution below.
        from coordinator_core.session import core as _git_root_core  # noqa: PLC0415
        from coordinator_core.session import scope as cs_scope  # noqa: PLC0415

        own_set: Set[str] = set()
        own_lines: List[str] = []
        if base and session_id:
            touched_path = os.path.join(base, session_id, "touched.txt")
            if os.path.isfile(touched_path):
                try:
                    own_lines = Path(touched_path).read_text(encoding="utf-8").splitlines()
                except OSError as exc:
                    print(
                        f"ERROR: cannot read this session's own touched.txt "
                        f"({touched_path}: {exc}); refusing --blanket commit — the F0/F1 "
                        "subtract's 'own wins' protection cannot be trusted with an "
                        "incomplete own_set, and a legitimately-owned staged path could be "
                        "incorrectly subtracted as a sibling's. Set "
                        "COORDINATOR_BLANKET_ACCEPT_FOREIGN=1 to skip the whole subtract "
                        "and bypass at your own risk.",
                        file=sys.stderr,
                    )
                    sys.exit(1)
                # SELF-facing projection (P3): own_set is this session's own
                # scope, so a path last RELEASED (R) must not re-enter it —
                # `project_self_scope` never applies the peer-facing mtime
                # re-claim (that arm must not widen `my_scope`/own_set).
                own_set.update(cs_scope.project_self_scope(own_lines))
        # exact mode: broadened would scoop a sibling EM's own sub-agent
        # back-pointer into "own", causing the blanket to absorb the
        # sibling's in-flight files — no downstream correction exists on
        # the blanket path (the subtract IS the only correction).
        # Negative-spec: this skip is scoped to an absent session id ONLY. A
        # raising my_agent_touched with a REAL session id still aborts — there
        # the machinery genuinely failed and own_set is untrustworthy.
        try:
            if session_id:
                own_set.update(f for f in cs_claims.my_agent_touched(session_id, "exact") if f)
        except Exception as exc:
            print(
                f"ERROR: cannot resolve own dispatched-agent touched files ({exc}); "
                "refusing --blanket commit — the F0/F1 subtract's 'own wins' protection "
                "cannot be trusted with an incomplete own_set. Set "
                "COORDINATOR_BLANKET_ACCEPT_FOREIGN=1 to skip the whole subtract and "
                "bypass at your own risk.",
                file=sys.stderr,
            )
            sys.exit(1)

        sibling_set: Set[str] = set()
        if base and os.path.isdir(base):
            # Review: code-reviewer — Finding 2: this feeds the F0/F1
            # foreign-path subtract, the only correction preventing a
            # blanket sweep from absorbing a concurrent sibling EM's
            # in-flight files. An exception here must not silently degrade
            # to "no live siblings" (which reads as the safe case) — abort
            # the blanket commit instead of proceeding unsafely.
            try:
                live_ids = cs_liveness.live_session_ids()
            except Exception as exc:
                print(
                    f"ERROR: cannot verify sibling-session liveness ({exc}); refusing "
                    "--blanket commit — the foreign-path subtract cannot be trusted. "
                    "Set COORDINATOR_BLANKET_ACCEPT_FOREIGN=1 to bypass at your own risk.",
                    file=sys.stderr,
                )
                sys.exit(1)
            # PEER-facing challenger evidence (EM ratification 2026-08-03,
            # item 1: option (a)): only this session's own REAL-timestamped
            # T events feed `project_peer_claims`'s `challenger_t_events`
            # argument, mirroring `compute_scope` Step 3's own construction
            # — a legacy/fail-safe T (unknown time) carries no evidence of
            # post-dating anything and is excluded.
            # Review: code-reviewer Finding 1 (sidecar
            # coordinatorcode-reviewer-5c643f30.md) — this scan is now the
            # shared `cs_scope._challenger_t_events` helper, rather than a
            # third independent rewrite of the same derivation.
            # Dict[str, datetime] — `datetime` is not imported into this file
            # (Finding 2, same sidecar); local variable annotations are never
            # evaluated at runtime (this file already has `from __future__
            # import annotations`), so the bare name is safe here without a
            # new import.
            challenger_t_events: Dict[str, datetime] = cs_scope._challenger_t_events(
                own_lines
            )
            root = _git_root_core.git_root()
            for sl_sid in live_ids:
                if sl_sid == session_id:
                    continue
                sl_touched = os.path.join(base, sl_sid, "touched.txt")
                if not os.path.isfile(sl_touched):
                    continue
                try:
                    sl_lines = Path(sl_touched).read_text(encoding="utf-8").splitlines()
                except OSError as exc:
                    print(
                        f"ERROR: cannot read touched.txt for live sibling session {sl_sid} "
                        f"({sl_touched}: {exc}); refusing --blanket commit — the F0/F1 "
                        "subtract cannot verify that session's claimed files, risking "
                        "absorption of a sibling's in-flight work. Set "
                        "COORDINATOR_BLANKET_ACCEPT_FOREIGN=1 to skip the whole subtract "
                        "and bypass at your own risk.",
                        file=sys.stderr,
                    )
                    sys.exit(1)
                # PEER-facing projection (P3): route sibling_set through
                # `project_peer_claims` — a released path re-projects to
                # CLAIMED only under the mtime-re-claim rule (§ Decision 3);
                # a released path with no re-claim evidence stays absent
                # here, same as sibling_set never gaining an entry for it
                # today.
                nonblank_sl_lines = [ln for ln in sl_lines if ln]
                sl_path_mtimes = cs_scope._collect_peer_path_mtimes(nonblank_sl_lines, root)
                sibling_set.update(
                    cs_scope.project_peer_claims(
                        nonblank_sl_lines, sl_path_mtimes, challenger_t_events
                    )
                )

        excluded_paths: List[str] = []
        for staged_path in _git_diff_cached_names():
            if not staged_path:
                continue
            if staged_path not in sibling_set:
                continue
            if staged_path in own_set:
                continue  # own wins — do NOT subtract
            subtracted_count += 1
            excluded_paths.append(staged_path)
        _git_reset_unstage_many(excluded_paths)

        if subtracted_count > 0 and not session_id:
            # Review: code-reviewer — Finding 1 (P2): own_set is empty here
            # specifically because session_id is absent, so the "own wins"
            # check above could never have protected any of these paths. A
            # path this session genuinely owns that also appears in a live
            # sibling's touched.txt is excluded above with no other signal.
            # Non-destructive (the file stays dirty, not discarded) — this
            # is visibility only, so an operator can notice and re-commit
            # the excluded path explicitly.
            print(
                f"INFO: blanket: session_id unresolved — {subtracted_count} path(s) "
                "excluded without 'own wins' protection (may include a path this "
                "session genuinely owns):",
                file=sys.stderr,
            )
            for p in excluded_paths:
                print(f"  {p}", file=sys.stderr)

        if subtracted_count > 0 and _git_diff_cached_is_empty():
            print(
                "INFO: blanket: nothing to commit — all staged paths belong to live siblings "
                f"({subtracted_count} path(s) subtracted) [session: {session_id or '?'}]",
                file=sys.stderr,
            )
            sys.exit(0)

    _blanket_check_destructive_shape(args.subject)

    # Sentinel 2: wrap commit call so mid-call failures surface as a FAIL line.
    result = subprocess.run(["git", "commit", *_commit_message_argv(args.subject, args.body)])
    if result.returncode != 0:
        print(f"FAIL: git commit returned {result.returncode} in do_blanket", file=sys.stderr)
        sys.exit(2)
    post_head = _git_rev_parse_head()
    if pre_head == post_head:
        print(
            "FAIL: helper produced no commit (reason: HEAD unchanged after do_blanket commit attempt)",
            file=sys.stderr,
        )
        sys.exit(2)


# ---------------------------------------------------------------------------
# OVERRIDE MODE helper
# ---------------------------------------------------------------------------

def do_override(session_id: str, args: "Args", cs_core) -> None:
    """Port of `do_override`: COORDINATOR_OVERRIDE_SCOPE=1 emergency escape
    hatch — audit-trail-degraded, logs to overrides.log, then
    Sentinel-1/Sentinel-2 commit.

    2026-07-25 fix (real incident, project-rag same-day): staging is now
    CONDITIONAL, not unconditionally blanket. If the caller already staged
    an explicit-path index (`git add -- <paths>`) before invoking this
    helper, that pre-staged index is committed AS-IS — `_git_add_all_blanket`
    is never called, so a careful caller's explicit staging is no longer
    silently discarded and replaced with `git add -A`. Only when the index
    is empty at entry does this fall back to the original blanket-add
    behavior. Negative-spec: the refusal text in `do_scoped` (~1145/~1159)
    phrases the override as "explicit-path staging", which previously lied —
    `do_override` ignored any pre-staged index and always blanket-added
    regardless. This is the fix for that lie, not a new feature.

    2026-07-25 second fix (this dispatch, real incident #2): `--dry-run` is
    now honored HERE, before any staging or commit. Previously `main()`
    intercepted `COORDINATOR_OVERRIDE_SCOPE=1` (default mode only) and
    dispatched straight to `do_override` without ever consulting
    `args.dry_run` — so `--dry-run` combined with the override env var
    silently fell through every check and reached a real `git commit`,
    consuming and mutating the caller's staged index and (on `work/*`
    branches) auto-pushing the result. `--dry-run` must win over
    `COORDINATOR_OVERRIDE_SCOPE=1` in every combination and every flag
    order — an override of *scope* must never become an override of
    *dry-run*. Negative-spec: a future edit that reads `args.dry_run` only
    in `do_scoped`/`do_blanket`/`do_scope_from` and not here reintroduces
    this exact defect — `do_override` is reached from `main()` BEFORE mode
    dispatch, so it needs its own dry-run gate; it does not inherit one from
    any other `do_*` function."""
    # Sentinel 1: capture HEAD before commit to detect silent no-ops. Must be
    # captured before either staging path below (pre_head is HEAD-before-
    # commit regardless of which staging branch runs). Also used by the
    # dry-run preview below — reading it is a no-op query (`git rev-parse`),
    # never a mutation.
    pre_head = _git_rev_parse_head()

    pre_staged = not _git_diff_cached_is_empty()

    if args.dry_run:
        print("WARNING: COORDINATOR_OVERRIDE_SCOPE=1 is set — audit-trail-degraded path.", file=sys.stderr)
        if pre_staged:
            staged_files = _git_diff_cached_names()
            print(
                f"DRY RUN — override: would commit the pre-staged index as-is "
                f"({len(staged_files)} file(s)):",
                file=sys.stderr,
            )
            for f in staged_files:
                print(f"  {f}", file=sys.stderr)
        else:
            dirty = _current_dirty_files()
            print(
                f"DRY RUN — override: nothing staged; would stage ALL {len(dirty)} "
                "dirty file(s) via 'git add -A':",
                file=sys.stderr,
            )
            for f in dirty:
                print(f"  {f}", file=sys.stderr)
        print(f"Would commit with subject: {args.subject}", file=sys.stderr)
        print("(no git add or commit executed; staged index left untouched)", file=sys.stderr)
        sys.exit(0)

    if pre_staged:
        print("WARNING: COORDINATOR_OVERRIDE_SCOPE=1 is set — audit-trail-degraded path.", file=sys.stderr)
        print(
            "         Index already has staged changes — committing the pre-staged index "
            "as-is (NOT staging additional dirty files). This will be logged.",
            file=sys.stderr,
        )
    else:
        print("WARNING: COORDINATOR_OVERRIDE_SCOPE=1 is set — audit-trail-degraded path.", file=sys.stderr)
        print(
            "         Nothing was staged — staging ALL dirty files (git add -A). This may "
            "pull in ANY concurrent session's unstaged dirty work. This will be logged.",
            file=sys.stderr,
        )
        _git_add_all_blanket()

    staged_files = _git_diff_cached_names()

    base = cs_core.sessions_dir()
    if base and session_id:
        # `ensure_session`, not `os.makedirs`: `<base>/<session_id>` IS a
        # session directory, and creating it without a `meta.json` record is
        # what left sessions invisible to `liveness.live_session_ids` and
        # unreapable by `ops/session/reap.py`. The ceremony runs in a real
        # session, so the record belongs here -- unlike a guard's audit log,
        # which takes `_override_log_path`'s `no-session` bucket instead.
        sdir = cs_core.ensure_session(session_id, sessions_base=base)
        log_file = os.path.join(sdir, "overrides.log")
        try:
            with open(log_file, "a", encoding="utf-8", newline="\n") as fh:
                fh.write(f"=== Override at {cs_core.now_iso()} ===\n")
                fh.write(f"Subject: {args.subject}\n")
                fh.write(f"Mode: {'pre-staged-index' if pre_staged else 'blanket (git add -A)'}\n")
                fh.write("Files staged:\n")
                for f in staged_files:
                    fh.write(f"  {f}\n")
                fh.write("\n")
        except OSError:
            pass

    # Sentinel 2: wrap commit call so mid-call failures surface as a FAIL line.
    result = subprocess.run(["git", "commit", *_commit_message_argv(args.subject, args.body)])
    if result.returncode != 0:
        print(f"FAIL: git commit returned {result.returncode} in do_override", file=sys.stderr)
        sys.exit(2)
    post_head = _git_rev_parse_head()
    if pre_head == post_head:
        print(
            "FAIL: helper produced no commit (reason: HEAD unchanged after do_override commit attempt)",
            file=sys.stderr,
        )
        sys.exit(2)


# ---------------------------------------------------------------------------
# DEFAULT MODE (scoped staging path)
# ---------------------------------------------------------------------------

def do_scoped(
    session_id: str,
    args: "Args",
    cs_core,
    cs_liveness,
    cs_scope,
    cs_claims,
    combined_mode: bool = False,
    active_scope_file: str = "",
) -> None:
    """combined_mode=True means do_scope_from delegated here (mirrors bash
    `_sfm_trap_installed=1`): the >1-live-session gate below is skipped
    (do_scope_from already resolved identity + the handoff-scope overlap
    gate), and active_scope_file already exists (do_scope_from's own
    active-scope.txt) rather than being created fresh here."""
    subject = args.subject
    include_orphans = list(args.include_orphans)

    # Issue C fail-closed gate: default mode is unsafe under concurrent
    # sessions because it relies on session-id resolution, which is
    # ambiguity-guarded but still a single-session model. When >1 live
    # session is detected, refuse and direct the caller to a direct
    # `run_commit_pipeline` retry script or COORDINATOR_OVERRIDE_SCOPE=1
    # — which honors a pre-staged explicit-path `git add -- <paths>` index
    # as-is, falling back to `git add -A` only when nothing was pre-staged
    # (2026-07-25 fix — see do_override docstring).
    #
    # NOT --scope-from <handoff> (2026-07-29 fix, DoE-claude audit
    # state/audits/2026-07-29-safe-commit-scope-from-defect.md): the
    # /handoff skill stopped emitting the `scope:` frontmatter block
    # --scope-from parses (2026-07-25, DoE-claude 1d5aa82b) and every
    # handoff written since fails it on arrival — a named alternative that
    # is inoperative in the situation the caller is actually in is worse
    # than none (docs/wiki/bash-guard-threat-model.md). `_scoped_commit_
    # suggestion` below reproduces the caller's own dirty-path set as a
    # verified-runnable `run_commit_pipeline` retry script instead — a
    # copy, not a re-derivation. (2026-08-25: `ceremony.scoped_git_commit`
    # itself was killed 2026-08-23 under DR-344 — see that function's own
    # docstring.)
    #
    # Exception: combined-mode (do_scope_from delegating). do_scope_from
    # already handled identity resolution and the handoff-scope overlap
    # gate, so concurrent sessions are expected and safe at this point.
    if not combined_mode:
        # Review: code-reviewer — Finding 2: this is a fail-closed safety
        # gate; an exception here must not silently degrade to "0 live
        # sessions" (which reads as the safe case and lets an unsafe
        # concurrent commit proceed). Abort instead of guessing.
        try:
            live_ids = sorted(cs_liveness.live_session_ids())
        except Exception as exc:
            print(
                f"ERROR: cannot verify session liveness ({exc}); refusing default-mode "
                "commit under concurrency-unknown conditions.\n\n"
                "Did you mean:\n" + _scoped_commit_suggestion(subject) + "\n\n"
                "(trim 'paths' to what THIS workstream owns before running). For a true "
                "emergency, stage explicitly (git add -- <paths>) and set "
                "COORDINATOR_OVERRIDE_SCOPE=1 — it commits your pre-staged index as-is, "
                "audit-trail-degraded, last resort.",
                file=sys.stderr,
            )
            sys.exit(1)
        if len(live_ids) > 1:
            print(
                f"ERROR: multiple live sessions detected ({len(live_ids)}); "
                "default-mode commit is unsafe under concurrency.",
                file=sys.stderr,
            )
            for sid in live_ids:
                print(f"  {sid}", file=sys.stderr)
            print(
                "\nDid you mean:\n" + _scoped_commit_suggestion(subject) + "\n\n"
                "(dirty files this session touched are pre-filled above — trim 'paths' "
                "to what THIS workstream owns before running). For a "
                "true emergency, stage explicitly (git add -- <paths>) and set "
                "COORDINATOR_OVERRIDE_SCOPE=1 — it commits your pre-staged index as-is "
                "(falls back to staging ALL dirty files, including any concurrent "
                "session's, only if nothing was pre-staged), audit-trail-degraded, last "
                "resort.",
                file=sys.stderr,
            )
            sys.exit(1)

    base = cs_core.sessions_dir()

    # Read my touched.txt for post-filtering (mtime-only orphan exclusion).
    my_touched: List[str] = []
    # Own-session paths whose LAST event is R (committed-and-released) —
    # tracked separately from `my_touched` purely for Case B's diagnostic
    # clause below (AC11/C6): distinguishes "this session released these
    # paths" from "this session never touched anything", so the dirty-file
    # ERROR doesn't read as if THIS session's own work went unclaimed.
    released_paths: List[str] = []
    if base and session_id:
        touched_path = os.path.join(base, session_id, "touched.txt")
        if os.path.isfile(touched_path):
            try:
                lines = Path(touched_path).read_text(encoding="utf-8").splitlines()
            except OSError:
                lines = []
            # LC_ALL=C sort -u dedup on read (bash: Phase 3a). SELF-facing
            # projection (P3): a path last RELEASED (R) must not re-enter
            # my_touched — `project_self_scope` never applies the
            # peer-facing mtime re-claim (that arm must not widen
            # `my_scope`).
            my_touched.extend(sorted(cs_scope.project_self_scope(lines)))
            # Review: code-reviewer Finding 1 (sidecar
            # coordinatorcode-reviewer-5c643f30.md) — shares the
            # last-event-per-path scan with `project_self_scope` via
            # `cs_scope._last_verb_map`, rather than re-deriving it here.
            last_verb: Dict[str, str] = cs_scope._last_verb_map(lines)
            released_paths = sorted(path for path, verb in last_verb.items() if verb == "R")

    # Union dispatched-agent touched files (broadened mode: recovers the
    # EM's own fan-out output on old Claude Code sentinel-pollution).
    # Review: code-reviewer — Finding 2: surface a swallowed exception here
    # rather than silently narrowing my_touched (a diagnostic, not a
    # safety-gate reversal — dropping to empty only makes scope narrower).
    try:
        agent_touched = [f for f in cs_claims.my_agent_touched(session_id, "broadened") if f]
    except Exception as exc:
        print(
            f"WARNING: could not resolve dispatched-agent touched files ({exc}); "
            "scoped commit may miss fan-out output this run.",
            file=sys.stderr,
        )
        agent_touched = []
    my_touched.extend(agent_touched)
    touched_set = set(my_touched)

    scope_result = cs_scope.compute_scope(session_id)
    dirty_list = _current_dirty_files()
    dirty_set = set(dirty_list)

    # Post-filter: cs_scope.compute_scope's my_scope already unions
    # touched.txt with mtime-dirty-since-started_at files. Re-derive which
    # candidates are genuinely ours (in touched_set) vs. mtime-only
    # additions (reclassified as orphans — warn, never auto-stage), and
    # drop touched-but-now-clean files (Case C candidates) rather than
    # feeding them to `git commit` as no-op paths.
    my_scope: List[str] = []
    mtime_orphans: List[str] = []
    clean_touched: List[str] = []
    for candidate in scope_result.my_scope:
        if candidate in touched_set:
            if candidate in dirty_set:
                my_scope.append(candidate)
            else:
                clean_touched.append(candidate)
        else:
            mtime_orphans.append(candidate)

    orphan_files: List[str] = list(scope_result.orphans)
    for mto in mtime_orphans:
        orphan_files.append(mto)
        print(f"orphan (mtime-only, not in touched.txt): {mto}", file=sys.stderr)

    other_excluded_files = [
        f"skipping {path} — owned by session {owner}" for (path, owner) in scope_result.skipped
    ]

    # -------------------------------------------------------------------
    # Phase 2: --include-orphans processing.
    # Spec backlink: plans/safe-commit-fixes.md § Phase 2 — flag spec.
    # Spec backlink: plans/safe-commit-fixes-5-and-6.md § Fix 5 — combined-mode
    # delegation (single canonical implementation, no duplicated block).
    #
    # In combined_mode, active_scope_file already exists (written by
    # do_scope_from); we append/union into it. In pure default-mode we
    # create it fresh here for the overlap gate. Ownership of cleaning it
    # up on a failure exit belongs to the creator: do_scope_from wraps its
    # delegate call in a cleanup finally (mirrors its bash EXIT trap
    # persisting across the delegated do_scoped call); pure default-mode
    # owns its own cleanup via the finally below (mirrors do_scoped's own
    # bash EXIT trap, active only when _sfm_trap_installed==0).
    # -------------------------------------------------------------------
    orphan_claimed_paths: List[str] = []
    local_active_scope_file = active_scope_file
    own_active_scope_file = False  # True iff THIS call created the file (pure mode)

    def _cleanup_local_active_scope_file() -> None:
        if local_active_scope_file:
            try:
                os.remove(local_active_scope_file)
            except OSError:
                pass

    if include_orphans:
        if not local_active_scope_file and base and session_id:
            # See the `ensure_session` note above: a session directory and
            # its record are created together or neither.
            sdir = cs_core.ensure_session(session_id, sessions_base=base)
            local_active_scope_file = os.path.join(sdir, "active-scope.txt")

        if not combined_mode and local_active_scope_file:
            own_active_scope_file = True
            try:
                open(local_active_scope_file, "w", encoding="utf-8", newline="\n").close()
            except OSError:
                pass

        try:
            invalid_ps = _first_invalid_pathspec(include_orphans)
            if invalid_ps is not None:
                print(
                    f"ERROR: --include-orphans: malformed or invalid pathspec '{invalid_ps}'",
                    file=sys.stderr,
                )
                sys.exit(1)
            orphan_candidate_files: List[str] = []
            for ops in include_orphans:
                orphan_candidate_files.extend(_git_ls_files_pathspec(ops))

            if not orphan_candidate_files:
                print(
                    f"WARNING: --include-orphans: no files matched the given pathspec(s): {' '.join(include_orphans)}",
                    file=sys.stderr,
                )

            # Filter to only dirty files (no point staging clean files as orphans).
            orphan_resolved = [f for f in orphan_candidate_files if f in dirty_set]

            # Union of declared scope (from active-scope.txt if combined-mode)
            # and orphan paths — both must clear the overlap gate.
            union_scope_set: Set[str] = set()
            if combined_mode and local_active_scope_file and os.path.isfile(local_active_scope_file):
                try:
                    union_scope_set.update(
                        p for p in Path(local_active_scope_file).read_text(encoding="utf-8").splitlines() if p
                    )
                except OSError:
                    pass
            union_scope_set.update(f for f in orphan_resolved if f)

            if base:
                with_overlap_lock(
                    base,
                    cs_core,
                    _append_orphans_and_check_overlap,
                    local_active_scope_file,
                    base,
                    session_id,
                    orphan_resolved,
                    union_scope_set,
                )

            if base and session_id:
                claim_log = os.path.join(base, session_id, "orphan-claims.log")
                try:
                    with open(claim_log, "a", encoding="utf-8", newline="\n") as fh:
                        fh.write(f"=== Claim at {cs_core.now_iso()} ===\n")
                        fh.write(f"Pathspecs: {' '.join(include_orphans)}\n")
                        fh.write("Resolved dirty files:\n")
                        for p in orphan_resolved:
                            fh.write(f"  {p}\n")
                        fh.write("\n")
                except OSError:
                    pass

            orphan_claimed_paths = orphan_resolved
            if orphan_claimed_paths:
                claimed_set = set(orphan_claimed_paths)
                orphan_files = [f for f in orphan_files if f not in claimed_set]
        except SystemExit:
            if own_active_scope_file:
                _cleanup_local_active_scope_file()
            raise
    # ---------------------------------------------------------------
    # End --include-orphans processing
    # ---------------------------------------------------------------

    # From here to function exit, own_active_scope_file (pure default-mode,
    # --include-orphans) must be cleaned up on EVERY exit path — success or
    # any sys.exit below — mirroring the bash EXIT trap that persists for
    # the rest of do_scoped's execution. Combined-mode cleanup ownership
    # belongs to do_scope_from's own wrapping finally.
    try:
        # Dry-run: print and exit without committing. Placed after
        # --include-orphans processing (so orphan-claimed/unclaimed lists
        # are accurate) and before the four-case "nothing to stage"
        # diagnosis, matching bash's do_scoped placement exactly.
        if args.dry_run:
            print(f"DRY RUN — would stage {len(my_scope)} file(s):", file=sys.stderr)
            for f in my_scope:
                print(f"  {f}", file=sys.stderr)
            if orphan_claimed_paths:
                print(
                    f"Orphan-claimed (would also stage): {len(orphan_claimed_paths)} file(s):",
                    file=sys.stderr,
                )
                for f in orphan_claimed_paths:
                    print(f"  {f}  (orphan-claimed)", file=sys.stderr)
            if orphan_files:
                print(f"Orphans (not staged): {len(orphan_files)} file(s):", file=sys.stderr)
                for f in orphan_files:
                    print(f"  {f}", file=sys.stderr)
            if other_excluded_files:
                print(f"Excluded (other-session-owned): {len(other_excluded_files)}", file=sys.stderr)
            print("(no git add or commit executed)", file=sys.stderr)
            sys.exit(0)

        if not my_scope and not orphan_claimed_paths:
            dirty_count = len(dirty_list)
            if clean_touched:
                # Case C: touched.txt has entries but they're clean now (reverted).
                print(
                    "NOTE: Edit/Write fired on these path(s), but they are clean now (likely reverted):",
                    file=sys.stderr,
                )
                for f in clean_touched:
                    print(f"  {f}", file=sys.stderr)
                if orphan_files:
                    print(f"Working tree dirty (unclaimed): {len(orphan_files)} file(s):", file=sys.stderr)
                    for f in orphan_files:
                        print(f"  {f}", file=sys.stderr)
                sys.exit(1)
            elif not my_touched and dirty_count > 0:
                # Case B: sentinel valid, touched.txt empty, dirty tree exists.
                print(
                    f"ERROR: {dirty_count} dirty file(s) but none claimed by this session via Edit/Write.",
                    file=sys.stderr,
                )
                if released_paths:
                    # AC11/C6: this session DID touch paths — they were
                    # already committed and released, so they correctly
                    # dropped out of `my_touched`. Without this clause the
                    # ERROR above reads as if this session's own work went
                    # unclaimed, which nudges toward staging the dirty
                    # file(s) below — those are NOT this session's released
                    # work; do not treat this note as license to
                    # --include-orphans them.
                    print(
                        f"NOTE: {len(released_paths)} path(s) touched by this session were "
                        "already committed and released; they are not among the dirty "
                        "file(s) below:",
                        file=sys.stderr,
                    )
                    for f in released_paths:
                        print(f"  {f}", file=sys.stderr)
                print("These are likely hook-touched or install-script-touched files.", file=sys.stderr)
                print("To stage them, use one of:", file=sys.stderr)
                print(
                    "  coordinator-safe-commit --include-orphans <pathspec>...  (preferred — audited, overlap-checked)",
                    file=sys.stderr,
                )
                print(
                    '  git reset && git add -- <paths> && git commit -m "<subject>" -- <paths>  (fallback)',
                    file=sys.stderr,
                )
                print("Dirty file(s):", file=sys.stderr)
                for f in dirty_list:
                    print(f"  {f}", file=sys.stderr)
                sys.exit(1)
            elif not my_touched and dirty_count == 0:
                # Case A: sentinel valid, touched.txt absent/empty, tree clean.
                print(
                    "NOTE: Nothing to commit — no Edit/Write fired this session and the working tree is clean.",
                    file=sys.stderr,
                )
                sys.exit(0)
            else:
                # Case D: session dir genuinely missing between resolution and here.
                print(
                    "ERROR: No live session scope detected. The session directory may have been archived or reaped.",
                    file=sys.stderr,
                )
                print("Fallback: bypass the helper with explicit-path commit:", file=sys.stderr)
                print('  git add -- <your-paths> && git commit -m "<subject>" -- <your-paths>', file=sys.stderr)
                sys.exit(1)

        # commit_scoped (C3, coordinator_core.ops.ceremony.git_native) picks
        # the safe write mechanism from OBSERVED index/worktree state --
        # `git add -- paths && git commit -F msg -- paths` when nothing has
        # diverged, or a private-index compare-and-swap branch when a peer
        # has partial-staged one of these paths. Replaces the prior
        # `_git_add` + pathspec-less `git commit`, which committed THE
        # INDEX and could silently absorb a concurrent sibling's staged
        # file (DoE-claude 726925b2). Scope COMPUTATION above (my_scope,
        # orphan_claimed_paths) is unchanged; only the write mechanism is
        # repointed. sys.path already carries claude_klabauter_root at this point
        # (main() runs _import_session() before dispatching to do_scoped).
        from coordinator_core.ops.ceremony import git_native  # noqa: PLC0415

        commit_paths = list(my_scope) + list(orphan_claimed_paths)
        message = f"{subject}\n\n{args.body}" if args.body else subject
        msg_fd, msg_path = tempfile.mkstemp(prefix="coordinator-safe-commit.do_scoped.")
        pre_head = _git_rev_parse_head()
        try:
            with os.fdopen(msg_fd, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(message)
            commit_result = git_native.commit_scoped(commit_paths, msg_path, cwd=os.getcwd())
        finally:
            try:
                os.remove(msg_path)
            except OSError:
                pass
        if not commit_result.ok:
            print(
                f"FAIL: git commit returned {commit_result.returncode} in do_scoped: "
                f"{commit_result.stderr.strip()}",
                file=sys.stderr,
            )
            sys.exit(2)
        post_head = _git_rev_parse_head()
        if pre_head == post_head:
            print(
                "FAIL: helper produced no commit (reason: HEAD unchanged after do_scoped commit attempt)",
                file=sys.stderr,
            )
            sys.exit(2)

        # Success-path cleanup: remove active-scope.txt so peer sessions do
        # not false-positive on the overlap gate. Runs for both pure
        # default-mode (--include-orphans only) and combined-mode
        # (do_scope_from delegated here) — matches bash's unconditional
        # `if _orphan_claimed_paths: _cleanup_active_scope`.
        if orphan_claimed_paths:
            _cleanup_local_active_scope_file()

        # Annotate orphan-claimed paths in the staged display list.
        display_staged_list = list(my_scope) + [f"{f}  (orphan-claimed)" for f in orphan_claimed_paths]
        total_staged = len(my_scope) + len(orphan_claimed_paths)

        print_summary(total_staged, display_staged_list, len(orphan_files), orphan_files, len(other_excluded_files), other_excluded_files)
    finally:
        if own_active_scope_file:
            _cleanup_local_active_scope_file()


# ---------------------------------------------------------------------------
# SCOPE-FROM MODE
# ---------------------------------------------------------------------------

def do_scope_from(args: "Args", session_id: str, cs_core, cs_liveness, cs_scope, cs_claims) -> None:
    """Port of `do_scope_from`. The handoff `scope:` field is the
    declarative truth for what this session owns — no cross-session
    touched.txt subtraction (removed 2026-05-05, Issue C: identity-
    resolution bugs under concurrent EMs / subagent SessionStart were
    causing the helper to exclude the calling session's own scope).
    Overlapping scopes are caught by the runtime overlap gate, not
    post-hoc identity-keyed subtraction."""
    scope_from_path = args.scope_from_path

    if not os.path.isfile(scope_from_path):
        print(f"ERROR: --scope-from path does not exist: {scope_from_path}", file=sys.stderr)
        sys.exit(1)

    handoff_pathspecs = _parse_scope_from_frontmatter(scope_from_path)
    if handoff_pathspecs is None:
        # `scope:` is schema-optional on handoffs (coordinator/schemas/
        # handoff.schema.json) — roughly half the live corpus omits it, so
        # this is a routine, expected failure mode under concurrency, not an
        # edge case. Every OTHER identity-ambiguity refusal in this file
        # (resolve_session_id, _print_no_live_session_error) hands the
        # caller a concrete escape; this one previously dead-ended at the
        # bare parse error and left COORDINATOR_OVERRIDE_SCOPE=1 (audit-
        # trail-degraded) as the only visible next step. Mirror those
        # siblings and name the safe fallback explicitly.
        #
        # Deliberately NOT auto-populated from this session's touched.txt:
        # that log is session-wide (every subagent this session has spawned),
        # not scoped to the one baton/workstream the caller is committing —
        # offering it as a ready-made `git add` list would routinely sweep in
        # a concurrent subagent's still-in-flight files, the exact hazard
        # this fallback exists to avoid. The caller must name their own
        # paths.
        print(
            "This handoff has no usable 'scope:' list, so --scope-from cannot "
            "compute what to stage. The safe path is explicit-path staging — "
            "bypass this helper and commit only the files you actually touched:",
            file=sys.stderr,
        )
        print('  git add -- <your-paths> && git commit -m "<subject>" -- <your-paths>', file=sys.stderr)
        print(
            "COORDINATOR_OVERRIDE_SCOPE=1 is an audit-trail-degraded emergency "
            "hatch, not the routine answer to a missing scope: field — prefer "
            "explicit-path staging above.",
            file=sys.stderr,
        )
        sys.exit(1)

    invalid_handoff_ps = _first_invalid_pathspec(handoff_pathspecs)
    if invalid_handoff_ps is not None:
        print(
            f"ERROR: Malformed or invalid pathspec in scope: '{invalid_handoff_ps}'",
            file=sys.stderr,
        )
        sys.exit(1)

    handoff_files: List[str] = []
    for ps in handoff_pathspecs:
        handoff_files.extend(_git_ls_files_pathspec(ps))

    scope_set: Set[str] = {f for f in handoff_files if f}

    base = cs_core.sessions_dir()

    active_scope_file = ""
    if base and session_id:
        # `ensure_session`, not `os.makedirs`: `<base>/<session_id>` IS a
        # session directory, and creating it without a `meta.json` record is
        # what left sessions invisible to `liveness.live_session_ids` and
        # unreapable by `ops/session/reap.py`. The ceremony runs in a real
        # session, so the record belongs here -- unlike a guard's audit log,
        # which takes `_override_log_path`'s `no-session` bucket instead.
        sdir = cs_core.ensure_session(session_id, sessions_base=base)
        active_scope_file = os.path.join(sdir, "active-scope.txt")

    def _cleanup() -> None:
        if active_scope_file:
            try:
                os.remove(active_scope_file)
            except OSError:
                pass

    try:
        # Step 5+6: publish this session's declared scope and check for
        # collisions with live peer sessions, atomically under the
        # overlap-gate lock (closes the read-peers/write-own TOCTOU window).
        if active_scope_file:
            with_overlap_lock(
                base,
                cs_core,
                _publish_scope_and_check_overlap,
                active_scope_file,
                base,
                session_id,
                handoff_files,
                scope_set,
            )

        # Combined-mode: --include-orphans delegates to do_scoped, the
        # single canonical implementation (eliminates a duplicated block).
        if args.include_orphans:
            do_scoped(
                session_id,
                args,
                cs_core,
                cs_liveness,
                cs_scope,
                cs_claims,
                combined_mode=True,
                active_scope_file=active_scope_file,
            )
            return

        # No-orphan path: intersect the declared scope with currently dirty files.
        dirty_files = _current_dirty_files()
        my_scope: List[str] = []
        out_of_scope_dirty: List[str] = []
        for f in dirty_files:
            if f in scope_set:
                my_scope.append(f)
            else:
                out_of_scope_dirty.append(f)

        # Out-of-scope dirty check: files this session edited but did NOT
        # declare in handoff scope are not staged, unless
        # --allow-out-of-scope-dirty downgrades this to a warning.
        if out_of_scope_dirty:
            if args.allow_out_of_scope_dirty:
                print(
                    f"WARNING: {len(out_of_scope_dirty)} dirty file(s) outside declared scope "
                    "(not staged; --allow-out-of-scope-dirty in effect):",
                    file=sys.stderr,
                )
                for f in out_of_scope_dirty:
                    print(f"  {f}", file=sys.stderr)
            else:
                print(f"ERROR: {len(out_of_scope_dirty)} dirty file(s) outside declared scope:", file=sys.stderr)
                for f in out_of_scope_dirty:
                    print(f"  {f}", file=sys.stderr)
                print(
                    "Resolve: include them in the handoff scope, stash them, or pass --allow-out-of-scope-dirty.",
                    file=sys.stderr,
                )
                sys.exit(1)

        # Empty-array guard: without it, `git add --` with no args emits an
        # obscure error instead of this actionable message.
        if not my_scope:
            print("ERROR: declared scope filtered to zero dirty files — nothing to commit.", file=sys.stderr)
            sys.exit(1)

        if args.dry_run:
            print(f"DRY RUN — scope-from: would stage {len(my_scope)} file(s):", file=sys.stderr)
            for f in my_scope:
                print(f"  {f}", file=sys.stderr)
            if out_of_scope_dirty:
                print(f"Excluded (out-of-scope dirty): {len(out_of_scope_dirty)} file(s):", file=sys.stderr)
                for f in out_of_scope_dirty:
                    print(f"  {f}", file=sys.stderr)
            print(f"Would commit with subject: {args.subject}", file=sys.stderr)
            print("(no git add or commit executed)", file=sys.stderr)
            sys.exit(0)

        # commit_scoped (C3, coordinator_core.ops.ceremony.git_native) picks
        # the safe write mechanism from OBSERVED index/worktree state --
        # `git add -- paths && git commit -F msg -- paths` when nothing has
        # diverged, or a private-index compare-and-swap branch when a peer
        # has partial-staged one of these paths. Replaces the prior
        # `_git_add` + pathspec-less `git commit`, which committed THE
        # INDEX and could silently absorb a concurrent sibling's staged
        # file (DoE-claude 726925b2) -- the same horn do_scoped's no-orphan
        # sibling branch was closed against. Scope COMPUTATION above
        # (my_scope) is unchanged; only the write mechanism is repointed.
        # sys.path already carries claude_klabauter_root at this point (main() runs
        # _import_session() before dispatching to do_scope_from).
        from coordinator_core.ops.ceremony import git_native  # noqa: PLC0415

        message = f"{args.subject}\n\n{args.body}" if args.body else args.subject
        msg_fd, msg_path = tempfile.mkstemp(prefix="coordinator-safe-commit.do_scope_from.")
        pre_head = _git_rev_parse_head()
        try:
            with os.fdopen(msg_fd, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(message)
            commit_result = git_native.commit_scoped(my_scope, msg_path, cwd=os.getcwd())
        finally:
            try:
                os.remove(msg_path)
            except OSError:
                pass
        if not commit_result.ok:
            print(
                f"FAIL: git commit returned {commit_result.returncode} in do_scope_from: "
                f"{commit_result.stderr.strip()}",
                file=sys.stderr,
            )
            sys.exit(2)
        post_head = _git_rev_parse_head()
        if pre_head == post_head:
            print(
                "FAIL: helper produced no commit (reason: HEAD unchanged after do_scope_from commit attempt)",
                file=sys.stderr,
            )
            sys.exit(2)

        # Declared scope is no longer active after a successful commit —
        # without this, peer sessions read stale entries and false-positive
        # on the overlap gate.
        _cleanup()

        print_summary(len(my_scope), my_scope, 0, [], 0, [])
    finally:
        # Mirrors the bash EXIT/INT/TERM/HUP trap installed at step 5: any
        # exit path (including one raised inside the delegated do_scoped
        # call above) must not leak active-scope.txt to peer sessions.
        # Idempotent with do_scoped's own cleanup calls (os.remove on an
        # already-removed path is a no-op via the try/except above).
        _cleanup()


# ---------------------------------------------------------------------------
# Main dispatch
# ---------------------------------------------------------------------------

def main(argv: Sequence[str]) -> None:
    _bootstrap_engine()
    if argv[:1] and argv[0] in ("--help", "-h"):
        usage()
        sys.exit(0)

    try:
        args = parse_args(argv)
    except UsageError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        usage()
        sys.exit(1)

    if args.paths:
        # Pathspec-passthrough (Defect 1). This comment used to read "the
        # delegate (`scoped-git-commit`) does its own session/ownership
        # gating — no need to resolve THIS wrapper's session id". That
        # delegate was killed by DR-344 and its replacement gates nothing,
        # so for three months the sentence excused an absence it described
        # as coverage; `_refuse_contested_pathspec` (called inside
        # `do_pathspec`) is now what actually holds it. The lock reap is
        # still deliberately skipped here.
        #
        # 2026-08-28, real incident #3 of the same class as the two this
        # file's module docstring already records: this branch dispatched
        # without ever reading `args.dry_run`, and `do_pathspec` does not
        # read it either, so `--dry-run "<subject>" -- <paths>` executed a
        # REAL commit. Observed as a commit landing on a shared branch with
        # a throwaway probe subject, unamendable by the time it was seen
        # because a peer had already committed on top. The gate belongs
        # HERE, ahead of the dispatch, for the same reason the override-env
        # branch grew its own: `do_pathspec` delegates staging to
        # `ceremony.commit_v2`, so there is no later chokepoint inside it
        # where a preview could still intercept.
        if args.dry_run:
            present, deleted = _split_paths_for_commit_v2(
                _worktree_root_from_cwd(), args.paths
            )
            print(
                f"DRY RUN — pathspec: would commit {len(present)} path(s) "
                f"and {len(deleted)} deletion(s) via ceremony.commit_v2:",
                file=sys.stderr,
            )
            for path in present:
                print(f"  {path}", file=sys.stderr)
            for path in deleted:
                print(f"  {path} [deleted]", file=sys.stderr)
            return
        do_pathspec(args)
        return

    # 2026-07-24 (M4): the em-only gate (cooperative COORDINATOR_AGENT_CONTEXT
    # signal) and the --expected-branch self-commit bypass both lived here
    # and are REMOVED — deleted, not bypassed. Whether the caller may commit
    # at all is now enforced upstream by the PreToolUse(Bash) hard-deny guard
    # coordinator_core/bash_guards/block_subagent_commit.py, keyed on the
    # harness-supplied caller identity (non-cooperative — a subagent cannot
    # unset it). See docs/plans/2026-07-24-g4-execute-pipeline-two-repo-
    # rebuild.md § chunk M4.

    # Self-heal orphaned git locks before any git operation. Best-effort:
    # non-zero rc is not fatal — git itself surfaces a real collision.
    # See docs/wiki/concurrent-em-hazards.md § H21.
    # Review: code-reviewer — Finding 1: invoke via sys.executable, not the
    # bare extensionless path, so this self-heal is Windows-invocable
    # (CreateProcess has no shebang support; the old bare-path form raised
    # FileNotFoundError there and was silently swallowed).
    reap_script = os.path.join(SCRIPT_DIR, "coordinator-reap-stale-locks.py")
    try:
        subprocess.run(
            [sys.executable, reap_script],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
    except OSError:
        pass

    cs_core, cs_liveness, cs_scope, cs_claims = _import_session()

    # Resolve session ID (needed for all modes except blanket, which tries
    # for logging purposes but doesn't fail if absent — bash:
    # `session_id=$(resolve_session_id 2>/dev/null) || session_id=""`).
    if args.mode != "blanket":
        session_id = resolve_session_id(cs_core, cs_liveness)
        if not session_id:
            sys.exit(1)
    else:
        # Blanket mode resolves the session id for LOGGING ONLY and must never
        # fail on it. redirect_stderr suppresses the diagnostic text but not
        # control flow, so resolve_session_id's fail-closed sys.exit(1) (the
        # liveness-probe-raised branch) would otherwise propagate out of main()
        # and abort the commit — wedging the one sanctioned blanket path used by
        # /workstream-start, /update-docs, relay-protocol and distillation.
        # Negative-spec: catching SystemExit here is scoped to this best-effort
        # logging read ONLY. The default-mode branch above must keep exiting —
        # there the session id is load-bearing for the concurrency gate, and
        # degrading it to "" would be the fail-open this file exists to prevent.
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                session_id = resolve_session_id(cs_core, cs_liveness) or ""
        except SystemExit:
            session_id = ""

    # COORDINATOR_OVERRIDE_SCOPE=1 intercepts default mode only.
    if os.environ.get("COORDINATOR_OVERRIDE_SCOPE") == "1" and args.mode == "default":
        do_override(session_id, args, cs_core)
        return

    if args.mode == "blanket":
        do_blanket(session_id, args, cs_core, cs_liveness, cs_claims)
    elif args.mode == "scope-from":
        do_scope_from(args, session_id, cs_core, cs_liveness, cs_scope, cs_claims)
    else:
        # mode == "default" reaches do_scoped; args.dry_run (orthogonal
        # boolean) is honored inside do_scoped regardless of mode.
        do_scoped(session_id, args, cs_core, cs_liveness, cs_scope, cs_claims)


if __name__ == "__main__":
    main(sys.argv[1:])
