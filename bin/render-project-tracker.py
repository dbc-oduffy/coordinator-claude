#
# render-project-tracker — CLI trampoline over claude-klabauter
# coordinator_core.ops.render_project_tracker.main.
#
# Purpose: the SOLE writer of docs/project-tracker.md. Reads all
# state/workstreams/<id>.yaml definitions plus all
# state/workstreams/events/<date>-<id>-<session>.yaml field-scoped events,
# folds each (workstream, field) pair to its current value by
# (sequence, session-id lexical) — NEVER wall-clock — filters to the
# current repo via the coordinator_root_path discriminator, and renders
# the result in the format contract defined by
# coordinator/pipelines/update-docs/tracker-maintenance.md
# § Project Tracker Format Reference, with schema-conformant
# title/created/status frontmatter per coordinator/schemas/tracker.schema.json.
#
# Idempotent: two consecutive renders of an unchanged store are byte-identical
# (render order = (created, workstream-id); fold order = (sequence, session-id)
# — both deterministic total orders).
#
# Spec backlink: docs/plans/2026-07-08-project-tracker-render-from-queue.md
# § Approach (fold rule, fold granularity, render order) / § Substrate /
# § Chunks C3.
# Port backlink: BIG_PORT Wave B, item render-project-tracker.
#
# THIS FILE keeps the store-root / coordinator_root_path RESOLUTION logic
# (unit 1) — it does NOT re-derive coordinator_root_path inside the claude-klabauter
# module. This is load-bearing (see
# docs/plans/2026-07-08-project-tracker-render-from-queue.md § Chunks C2/C3,
# AC9): coordinator_root_path MUST match what coordinator-queue-append's
# writer stamped onto each record, which resolves via `_current_repo_root()
# or os.getcwd()` at the WRITER's OWN invocation cwd. The only stable anchor
# from inside a script that may itself run with cwd pointed at an isolated
# test root (QUEUE_APPEND_OUTPUT_ROOT) is THIS SCRIPT'S OWN on-disk git root
# — never the claude-klabauter module's __file__ location, which resolves to
# claude-klabauter's tree, not this repo's. Resolve here, pass the value in.
#
# Negative-spec: do NOT fold or sort by file mtime/wall-clock anywhere
# upstream of this trampoline's claude-klabauter call — that reintroduces the exact
# non-monotonic-clock hazard (clock skew, NTP correction, DST) the fold rule
# exists to rule out (enforced claude-klabauter-side; see
# coordinator_core/ops/render_project_tracker.py's own negative-spec).
#
# Exit codes:
#   0 — rendered successfully.
#   1 — usage/config error (QUEUE_APPEND_OUTPUT_ROOT not absolute) OR a
#       business-fail-loud _MalformedRecordError propagated from the claude-klabauter
#       module (fail-loud store corruption — matches the oracle's unhandled-
#       exception-exits-1 behavior).
#   2 — DEDICATED transport-failure code (CLAUDE_KLABAUTER_ROOT resolution failed, or
#       coordinator_core.ops.render_project_tracker not importable) — never
#       reused for a business outcome, per PORTER-BRIEF-ADDENDUM.md rule A3b.

from __future__ import annotations

import os
import subprocess
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402

_SUBPROCESS_TIMEOUT_SECS = 15


def _no_console_kwargs() -> dict:
    """Deferred coordinator_core import — matches this file's CLAUDE_KLABAUTER_ROOT
    bootstrap posture so a transport-failure path never pays the resolution
    cost unnecessarily. On any CLAUDE_KLABAUTER_ROOT resolution/import failure, falls
    back to the same suppression kwargs computed inline (zero imports beyond
    ``subprocess``) rather than silently dropping console suppression -- a
    resolution failure must never turn a quiet spawn into a visible console
    window."""
    try:
        claude_klabauter_root = _resolve_claude_klabauter_root()
        if claude_klabauter_root not in sys.path:
            sys.path.insert(0, claude_klabauter_root)
        from coordinator_core.win_portability import no_console_creationflags

        return no_console_creationflags()
    except Exception:  # noqa: BLE001 -- fail-open, matches this module's bootstrap posture
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


def _git_toplevel(cwd: str) -> str:
    """Run `git -C <cwd> rev-parse --show-toplevel`, returning the trimmed
    stdout or "" on any failure (not a git repo, git absent, timeout).
    Bounded timeout + stdin=DEVNULL per PORTER-BRIEF-ADDENDUM.md rule A2 —
    git is locally-trusted but a hung/wedged git process must not hang this
    tool indefinitely."""
    try:
        result = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=_SUBPROCESS_TIMEOUT_SECS,
            stdin=subprocess.DEVNULL,
            **_no_console_kwargs(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _resolve_store_root() -> str:
    """Resolve the store root (mirrors coordinator-queue-append._output_path
    precedence, oracle lines 46-61):
      1. QUEUE_APPEND_OUTPUT_ROOT env override wins (test isolation) — must
         be an absolute path.
      2. Else the current git repo root (git rev-parse --show-toplevel from
         the process cwd).
      3. Else the cwd (last-resort; not in a git repo)."""
    override_root = os.environ.get("QUEUE_APPEND_OUTPUT_ROOT", "")
    if override_root:
        if not os.path.isabs(override_root):
            print(
                f"render-project-tracker: QUEUE_APPEND_OUTPUT_ROOT must be an "
                f"absolute path, got {override_root}",
                file=sys.stderr,
            )
            sys.exit(1)
        return override_root
    git_root = _git_toplevel(os.getcwd())
    if git_root:
        return git_root
    return os.getcwd()


def _resolve_coordinator_root_path(root: str) -> str:
    """Resolve the coordinator_root_path discriminator this render targets
    — anchored on THIS SCRIPT'S OWN on-disk git root (oracle lines 63-90),
    never on the process cwd. Falls back to "." (with a loud stderr warning)
    whenever that anchor cannot establish a real position for `root` — see
    below for the two distinct cases that share this fallback.

    The contract (contract/cockpit_schema/entities/coordinator_root.py)
    declares coordinator_root_path as repo-root-relative — "." for a
    single-root repo (the overwhelming common case: `root` IS the git
    repo's own top level), "subdir" for a monorepo sub-root (`root` nested
    below the repo's git top level) — never an absolute path (an absolute
    value is machine-specific and mints a phantom second repo identity in a
    dual-tenant store). `_git_toplevel` returns an ABSOLUTE path, so the
    correct discriminator is `root`'s OWN position relative to that
    anchor — ``relpath(root, git_toplevel)`` — computed in THAT direction
    (root relative to the anchor, not the anchor relative to root); the
    reversed direction silently mis-renders a genuine monorepo sub-root as
    ".." instead of "subdir". This closes the 2026-07-22 fold-correctness
    outage at its source: the writer (coordinator-queue-append) stamps "."
    on its auto-resolve path, and an absolute (or wrongly-directed)
    discriminator here could never match that stored value under strict
    equality, filtering every workstream record out before the fold ever
    ran. render_project_tracker.py's own loaders now also normalize both
    sides of that comparison defensively, but this resolver must still emit
    the contract shape rather than re-arm the same trap for any other
    reader of this discriminator.

    Two distinct fallback-to-"." cases, both meaning "this script's own git
    anchor cannot place `root`, so trust `root` as its own self-contained
    coordinator root":
      1. `_git_toplevel(script_dir)` itself fails (vendored/copied outside a
         git checkout, a detached-HEAD/worktree edge case, or the git binary
         is absent) — the historical fallback case.
      2. `_git_toplevel(script_dir)` succeeds but is NOT an ancestor of
         `root` — e.g. test isolation overriding the store root to a
         directory entirely unrelated to this script's own on-disk git
         tree. `os.path.relpath(root, git_toplevel)` in that case starts
         with ".." (it must climb OUT of the anchor to reach `root` at
         all), which is the tell that the anchor and `root` share no real
         monorepo-nesting relationship — as opposed to a genuine sub-root
         case, where `root` is nested BELOW the anchor and the relpath has
         no leading "..". On Windows this case has a second route in:
         when the anchor and `root` sit on different drives, `ntpath`
         cannot express any relative path between them and `relpath`
         raises ValueError instead of returning a ".."-prefixed one — the
         published-mirror-on-E:, repo-on-X: shape reported by example-game-repo-em
         and example-cockpit-repo-em on 2026-08-11. Semantically that is the
         same "the anchor cannot place `root`" verdict, so it routes into
         this branch rather than escaping to the caller. Both fallback
         branches warn to stderr, since both indicate a
         dual-tenant/vendoring setup worth double-checking.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    git_toplevel = _git_toplevel(script_dir)
    if not git_toplevel:
        print(
            f"render-project-tracker: warning: could not resolve this script's "
            f"own git root (script_dir={script_dir}); falling back to "
            f"coordinator_root_path=\".\" (treating {root} as its own "
            "self-contained coordinator root) — verify this matches the "
            "writer's discriminator in a dual-tenant setup",
            file=sys.stderr,
        )
        return "."
    try:
        rel = os.path.relpath(os.path.realpath(root), os.path.realpath(git_toplevel))
    except ValueError:
        rel = os.pardir
    if rel == os.curdir:
        return "."
    if rel == os.pardir or rel.startswith(os.pardir + os.sep):
        print(
            f"render-project-tracker: warning: this script's own git root "
            f"({git_toplevel}) is not an ancestor of the store root ({root}) "
            "(or lies on a different Windows drive, which admits no relative "
            "path at all); "
            "falling back to coordinator_root_path=\".\" (treating the store "
            "root as its own self-contained coordinator root) — verify this "
            "matches the writer's discriminator in a dual-tenant setup",
            file=sys.stderr,
        )
        return "."
    return rel


def _import_runner():
    """Resolve CLAUDE_KLABAUTER_ROOT, put it on sys.path, and import the DR-276 runner.

    Plain in-process import (template variant #1 — direct-import
    trampoline), not an RPC invoke: this is a single-shot maintenance
    render, not a hot path, and has no live cross-process caller to
    motivate a registered-op wire contract.

    DR-276: the op is run through `coordinator_core.cli_entry.run_op_main`
    rather than by calling its `main` directly, so the docs/project-tracker.md
    write it performs becomes a session scope-touch claim. Without that, this
    file's write is an orphan at the `scoped_git_commit` sink.
    """
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


_USAGE = (
    "usage: render-project-tracker\n"
    "\n"
    "Renders docs/project-tracker.md from the current state/workstreams/\n"
    "store (the sole writer of that file). Takes no arguments -- store root\n"
    "and coordinator_root_path are both self-resolved (see this file's own\n"
    "module comment). May refuse with exit 3 if the target tracker file is\n"
    "frozen (see the underlying op's own frozen-tracker guard); that refusal\n"
    "is a real app-level outcome, not a startup failure.\n"
)


def main() -> None:
    if any(arg in ("-h", "--help") for arg in sys.argv[1:]):
        print(_USAGE, end="")
        sys.exit(0)

    root = _resolve_store_root()
    coordinator_root_path = _resolve_coordinator_root_path(root)

    try:
        run_op_main = _import_runner()
    except RuntimeError as exc:
        print(
            f"render-project-tracker: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)
    except ImportError as exc:
        print(
            f"render-project-tracker: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)

    try:
        code = run_op_main(
            "coordinator_core.ops.render_project_tracker", [root, coordinator_root_path]
        )
    except ImportError as exc:
        print(
            "render-project-tracker: "
            f"coordinator_core.ops.render_project_tracker not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(code)


if __name__ == "__main__":
    main()
