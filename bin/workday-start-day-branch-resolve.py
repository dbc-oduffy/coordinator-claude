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
        non-empty — appends one UTC-timestamped line to ~/.claude/logs/coordinator-reap.log
        (creating the log directory if absent). Mirrors the bash fragment:
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

Exit codes:
    reap-log:    always 0 (best-effort hygiene, never a gate).
    span-assert: 0 — no mismatch (silent); 1 — mismatch detected (message on stdout).
    Both:        2 — bad subcommand/usage.

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

Spec backlink: DoE-claude commands/workday-start.md § Step -1 (Session Reaper),
§ Step 0.45 (Post-Step-0 Span Assertion)
Spec backlink: docs/plans/2026-07-23-extirpate-bash-from-workday-start.md § WDS-1 [DEAD-CITATION: plan file never committed to this repo]
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

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_colocated_engine_on_path, child_env  # noqa: E402

_GIT_TIMEOUT = 10


def _ensure_claude_klabauter_on_path() -> str:
    """Resolve+push this checkout's own root onto sys.path (self-colocated —
    this file lives at coordinator/bin/ inside the claude-klabauter checkout itself)."""
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
        log_dir = Path.home() / ".claude" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with open(log_dir / "coordinator-reap.log", "a", encoding="utf-8") as f:
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
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="workday-start-day-branch-resolve.py")
    sub = p.add_subparsers(dest="subcommand", required=True)

    sub.add_parser("reap-log", help="run reap-sessions.py and conditionally append its output to ~/.claude/logs/coordinator-reap.log")

    span_p = sub.add_parser("span-assert", help="assert the active branch's span covers today's local day")
    span_p.add_argument("--branch", default=None, help="branch name to check (default: `git branch --show-current`)")

    return p


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    args = _build_parser().parse_args(argv)
    if args.subcommand == "reap-log":
        return cmd_reap_log(args)
    if args.subcommand == "span-assert":
        return cmd_span_assert(args)
    print(f"workday-start-day-branch-resolve.py: unknown subcommand {args.subcommand!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
