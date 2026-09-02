# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
coordinator/bin/workday-start-day-branch-resolve.py — native port of two genuine
imperative fragments from `commands/workday-start.md` (DoE-claude), Steps -1 and
0.45: session reap-log append, and local-day/branch-span mismatch assertion.

Purpose: these two fragments were the last non-trivial bash LOGIC left inline in
the workday-start ceremony body (everything else in those steps is either the
`_cc_trusted`/`_cc_root` guard preamble — out of scope for this port, see the
plan's WDS-1 scope note — or a thin single-CLI-invocation fence). Both fragments
are genuinely imperative: a conditional-append with a generated timestamp, and a
multi-step parse/compare/format-message ladder. Concentrating them in one
importable/invokable CLI lets the DoE ceremony call this file by name instead of
carrying the logic inline, where it is unlintable (ShellCheck does not see markdown
fences), untestable (no test registry enumerates fenced code), and unreachable by
extension-filtered code search — the same pathology documented in
`DoE-claude/CLAUDE.local.md`'s "A skill must LINK to an entrypoint" note.

Subcommands:
    reap-log
        Runs the co-located reap-sessions.py, captures its stdout, and — only when
        non-empty — appends one UTC-timestamped line to <claude-config-dir>/logs/
        coordinator-reap.log (creating the log directory if absent), where
        <claude-config-dir> is coordinator_core._settings_home.claude_config_dir()
        — ~/.claude by default, CLAUDE_CONFIG_DIR when the harness sets it. Mirrors
        the bash fragment, which predates that seam and assumed ~/.claude directly:
            REAP_LOG=$(python3 .../reap-sessions.py 2>/dev/null)
            if [[ -n "$REAP_LOG" ]]; then
              mkdir -p ~/.claude/logs
              printf '%s  %s\\n' "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" "$REAP_LOG" >> ~/.claude/logs/coordinator-reap.log
            fi
        Best-effort: a reap-sessions.py failure (non-zero exit, missing interpreter)
        is reported to stderr and does NOT block — matches the bash fragment's own
        "Non-zero exit (lib not found) -> continue; the reaper is hygiene, not a gate."
        contract (commands/workday-start.md Step -1).

    span-assert [--branch <name>]
        Local-day/branch-span mismatch check — native port of the Step 0.45
        "Post-Step-0 Span Assertion" bash fragment. Resolves TODAY via
        coordinator_core.daily_day.local_day() (the LOCAL-clock anchor Step 0 itself
        uses — NOT UTC, which would false-fire after ~17:00 in UTC-negative offsets;
        see the bash fragment's own comment on this, preserved below). Resolves the
        active branch via `--branch` if given, else `git branch --show-current`.
        Parses the branch as a work/{machine}/{date-or-span} span via
        coordinator_core.daily_branch.parse_branch_span; if the branch doesn't parse
        as that shape (named long-lived bus, main, detached), or the parsed span's
        end-date already equals TODAY, this exits 0 with NO stdout (silent pass —
        Check 3.5 / the "branch already covers today" case, respectively). Otherwise
        prints the assertion message to stdout and exits 1 — the ceremony surfaces
        that message verbatim as a top-line "### Branch Span Mismatch" block, per
        commands/workday-start.md Step 0.45. This assertion is a TRIPWIRE, not a
        retry: it never renames the branch itself.

    day-branch-assert [--repo-root <path>]
        C6 of DoE-claude docs/plans/2026-08-18-enforce-day-branch-cut-tree-invariant.md
        (AC-6). Gives `/workweek-start` a real branch leg: `orient-assemble brief
        --cadence week`'s spine is READ-ONLY BY CONSTRUCTION (module docstring of
        coordinator_core.orient_assemble, enforced by
        orient_assemble/tests/test_read_only_guarantee.py — every disk-write
        primitive and any `git fetch` fails the test if a reader touches it), so it
        structurally CANNOT host the git-mutating leg C4b/C10 own. That rules out
        folding the assertion into the cadence-invariant spine (the plan's option
        (b)); this subcommand is option (a) instead — a direct invoke DoE's
        `workweek-start.md` Step 1 calls.

        Calls coordinator_core.hooks.day_branch_assert.assert_day_branch(repo_root,
        compute_machine(), local_day()) — the SAME dispatch C4b's SessionStart shim
        uses (case (A) on `main`: cut/adopt/inherit automatically; case (B)
        otherwise: warn without switching). `repo_root` defaults to the current
        working directory (`--repo-root` overrides it, a test seam mirroring
        `span-assert`'s `--branch`). Prints `result.message` verbatim when
        non-empty — this file does NOT re-render it; warn/refusal messages are
        already rendered by `day_branch_assert.banner()`, the one shared,
        non-suppressible renderer (AC-1's "same rendering, not a re-implementation
        printing similar-but-different text" constraint for this path, since
        `/workweek-start` is a mid-session slash command and may never re-enter the
        SessionStart hook that hosts C5's banner mount point).

Exit codes:
    reap-log:          always 0 (best-effort hygiene, never a gate).
    span-assert:        0 — no mismatch (silent); 1 — mismatch detected (message on stdout).
    day-branch-assert:  0 — cut/adopted/inherited/compliant/warn (a WARN is reported,
                        not blocking — same posture as the SessionStart shim, which
                        always continues); 1 — FAILED (the cut was attempted, inside
                        the tree-keyed lock, and genuinely failed; still on `main`).
    All:                2 — bad subcommand/usage.

Negative-spec (do NOT reintroduce while touching this file):
    - Does NOT carry the `_cc_trusted`/`_cc_root` guard preamble, the
      resolve-claude-klabauter-bin resolver block, or the `_cc_claude_klabauter` resolution ladder —
      those are a separate concern (D1/D2 of the extirpation plan), and this file
      lives INSIDE the claude-klabauter checkout so it self-resolves via
      `resolve_colocated_claude_klabauter_root`, not the DoE-side ladder.
    - Does NOT re-implement reap-sessions.py's own session.reap dispatch — it
      SHELLS OUT to the co-located script and only owns the log-append conditional,
      matching the bash fragment's own division of labor.
    - Does NOT auto-rename a mismatched branch — span-assert is read-only.
    - `day-branch-assert` does NOT re-implement `assert_day_branch`'s dispatch or
      `banner()`'s rendering — it is a thin CLI wrapper over the same engine-plane
      function C4b's SessionStart shim calls, so the two entry paths can never
      drift into printing different text for the same state.

Spec backlink: DoE-claude commands/workday-start.md § Step -1 (Session Reaper),
§ Step 0.45 (Post-Step-0 Span Assertion)
Spec backlink: docs/plans/2026-07-23-extirpate-bash-from-workday-start.md § WDS-1 [DEAD-CITATION: plan file never committed to this repo]
Spec backlink: DoE-claude docs/plans/2026-08-18-enforce-day-branch-cut-tree-invariant.md
    § C6 / AC-6 (day-branch-assert subcommand)
"""
from __future__ import annotations

import argparse
import datetime
import os
import subprocess
import sys
from pathlib import Path

# Generator-provenance declaration (generator_provenance.py). cmd_reap_log's
# only write is a best-effort append to ~/.claude/logs/coordinator-reap.log --
# outside the tracked repo tree; span-assert is read-only.
GENERATES = []

_GIT_TIMEOUT = 10


def _ensure_claude_klabauter_on_path() -> str:
    """Resolve+push this checkout's own root onto sys.path (self-colocated —
    this file lives at coordinator/bin/ inside the claude-klabauter checkout itself)."""
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_colocated_engine_on_path

    return require_colocated_engine_on_path(__file__)


def _no_console_kw() -> dict:
    """Splat-ready Windows console-suppression kwarg. Falls back to the same
    suppression kwargs computed inline (zero imports beyond ``subprocess``) on
    any resolution failure, rather than silently dropping console suppression —
    a resolution failure must never turn a quiet spawn into a visible console
    window (Review: code-reviewer P2 — matched to the pattern ccbdbecc2 applied
    to sweep-boot.py/standup.py/render-project-tracker/refresh-plugin-live-install.py)."""
    try:
        _ensure_claude_klabauter_on_path()
        from coordinator_core.win_portability import no_console_creationflags

        return no_console_creationflags()
    except Exception:  # noqa: BLE001 -- fail-open, matches this file's transport posture
        # `{}` off Windows, matching the primitive's own POSIX contract exactly --
        # `{"creationflags": 0}` splats harmlessly too, but a substitute that
        # disagrees with the thing it substitutes for is a trap for any caller
        # comparing against `no_console_creationflags()`.
        if os.name != "nt":
            return {}
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


# ---------------------------------------------------------------------------
# reap-log
# ---------------------------------------------------------------------------


def _run_reap_sessions() -> str:
    """Invoke the co-located reap-sessions.py and return its stripped stdout
    ("" on any failure — best-effort, mirrors the bash fragment's `2>/dev/null`
    discard of stderr and its non-zero-exit-continues contract)."""
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import child_env

    reap_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reap-sessions.py")
    try:
        result = subprocess.run(
            [sys.executable, reap_script],
            capture_output=True,
            text=True,
            timeout=60,
            env=child_env(),
            **_no_console_kw(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"workday-start-day-branch-resolve.py: reap-sessions.py invocation failed (continuing): {exc}", file=sys.stderr)
        return ""
    if result.returncode != 0:
        print(
            f"workday-start-day-branch-resolve.py: reap-sessions.py exited {result.returncode} (continuing): {(result.stderr or '').strip()}",
            file=sys.stderr,
        )
    return (result.stdout or "").strip()


def cmd_reap_log(_args: argparse.Namespace) -> int:
    reap_log = _run_reap_sessions()
    if reap_log:
        _ensure_claude_klabauter_on_path()
        from coordinator_core._settings_home import claude_config_dir

        log_dir = claude_config_dir() / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with open(log_dir / "coordinator-reap.log", "a", encoding="utf-8", newline="\n") as f:
            f.write(f"{ts}  {reap_log}\n")
    return 0  # best-effort hygiene — never blocks session start


# ---------------------------------------------------------------------------
# span-assert
# ---------------------------------------------------------------------------


def _current_branch() -> str:
    """`git branch --show-current` — empty string on detached HEAD or failure."""
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT,
            **_no_console_kw(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    return (result.stdout or "").strip()


def _span_assert(branch: str, today: str, parse_branch_span, format_span_suffix, compute_machine) -> str | None:
    """Core comparison — pure function of its inputs (unit-test seam). Returns
    the assertion message when the branch is a work/{machine}/{span} shape whose
    end-date does not cover `today`; None on every silent-pass path (unparseable
    shape, or already covers today)."""
    span = parse_branch_span(branch)
    if span is None:
        return None  # named long-lived / main / detached — Check 3.5 covers it
    start, end = span
    if end == today:
        return None  # branch already covers today
    expected = "work/" + compute_machine() + "/" + format_span_suffix(start, today)
    return (
        f"Active branch `{branch}` does not cover today ({today}) — end={end}, "
        f"expected rename to `{expected}`. Step 0 Check 4 did not fire. The "
        "library helpers work; the rename was skipped at the command level. "
        "Re-run `/workday-start` Step 0 manually or rename inline."
    )


def cmd_span_assert(args: argparse.Namespace) -> int:
    _ensure_claude_klabauter_on_path()
    from coordinator_core.daily_branch import parse_branch_span, format_span_suffix
    from coordinator_core.daily_day import local_day
    from coordinator_core.machine_resolver import compute_machine

    branch = args.branch if args.branch else _current_branch()
    today = local_day()
    msg = _span_assert(branch, today, parse_branch_span, format_span_suffix, compute_machine)
    if msg is None:
        return 0
    print(msg)
    return 1


# ---------------------------------------------------------------------------
# day-branch-assert — C6, AC-6: the /workweek-start branch leg
# ---------------------------------------------------------------------------


def cmd_day_branch_assert(args: argparse.Namespace) -> int:
    """Invoke the SAME `assert_day_branch` dispatch C4b's SessionStart shim
    calls, from a mid-session CLI entry point instead of a `startup`-sourced
    hook. See the module docstring's `day-branch-assert` block for why this
    is the seam (orient-assemble's spine is read-only by construction) and
    what its exit codes mean."""
    _ensure_claude_klabauter_on_path()
    from coordinator_core.daily_day import local_day
    from coordinator_core.hooks.day_branch_assert import FAILED, assert_day_branch
    from coordinator_core.machine_resolver import compute_machine

    from coordinator_core.ops.ceremony.push import publish_day_branch

    repo_root = args.repo_root if args.repo_root else os.getcwd()
    result = assert_day_branch(repo_root, compute_machine(), local_day())
    if result.message:
        print(result.message)

    # The publish leg. `assert_day_branch` runs `session_ensure_branch` with
    # `caller="boot"`, whose whole contract is NO NETWORK CALL -- it cuts the
    # branch and leaves the upstream to someone else. Until this leg existed,
    # nobody was that someone: the comment in `_cut_or_adopt`'s boot arm names
    # `auto_push.push_once`, and the per-commit push that reached it was
    # deleted by C6/C7 of docs/plans/2026-08-30-who-pushes-and-when.md. The
    # cadence that replaced it pushes with a bare `git push`, which a branch
    # with no upstream refuses outright. So a boot-cut day branch got an
    # upstream from no path at all, and on 2026-09-02 carried 102 commits with
    # no remote copy until a human published it by hand.
    #
    # It lives HERE, in the ceremony CLI, and not in `assert_day_branch`,
    # because the two entry points have different budgets for the same
    # dispatch: this subcommand is invoked by `/workday-start` and
    # `/workweek-start`, ceremonies an operator is already waiting on, where
    # one round trip to the remote is affordable; `assert_day_branch`'s other
    # caller is the SessionStart fan-in, which runs under a single shared 10s
    # timeout with no per-guard budget and must stay local (see
    # `day_branch_assert`'s own boot-cost negative-spec). Putting the publish
    # in the shared function would have put a cold-connection push inside that
    # budget on every one of ~50 daily session boots.
    #
    # Not a nudge and not conditional on the operator noticing anything: the
    # ceremony publishes, or says why it could not. `publish_day_branch` is
    # idempotent and costs two config reads plus zero spawns once the day's
    # first ceremony has run, and it will only ever publish a branch
    # `daily_branch.is_canonical_branch` accepts.
    outcome, detail = publish_day_branch(repo_root)
    if outcome == "published":
        print(f"day-branch: published {detail}")
    elif outcome == "failed":
        print(f"day-branch: publish FAILED -- {detail}", file=sys.stderr)

    return 1 if result.outcome == FAILED else 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="workday-start-day-branch-resolve.py")
    sub = p.add_subparsers(dest="subcommand", required=True)

    sub.add_parser("reap-log", help="run reap-sessions.py and conditionally append its output to ~/.claude/logs/coordinator-reap.log")

    span_p = sub.add_parser("span-assert", help="assert the active branch's span covers today's local day")
    span_p.add_argument("--branch", default=None, help="branch name to check (default: `git branch --show-current`)")

    dba_p = sub.add_parser("day-branch-assert", help="the boot day-branch invariant, invoked mid-session (C6 -- gives /workweek-start a real branch leg)")
    dba_p.add_argument("--repo-root", default=None, help="repo root to assert against (default: current working directory)")

    return p


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    args = _build_parser().parse_args(argv)
    if args.subcommand == "reap-log":
        return cmd_reap_log(args)
    if args.subcommand == "span-assert":
        return cmd_span_assert(args)
    if args.subcommand == "day-branch-assert":
        return cmd_day_branch_assert(args)
    print(f"workday-start-day-branch-resolve.py: unknown subcommand {args.subcommand!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
