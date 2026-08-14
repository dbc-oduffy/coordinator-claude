# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""merge-gate-and-pr.py — merge-time imperative logic ported off the bash
fences embedded in DoE-claude coordinator/skills/merging-to-main/SKILL.md.

Subcommands (argv[1] selects):

  coverage-gate [<range>] [--override]
      Wraps review-coverage-gate.py's VERDICT line. C10
      (docs/plans/2026-08-05-coverage-gate-planning-artifact-class.md):
      the pre-C10 halt-or-override policy (SKILL.md Step 1.65) is retired —
      VERDICT=UNCOVERED no longer exists. Below the code-partition coverage
      ratio threshold, the gate now reports VERDICT=WARN, which never halts:
      this subcommand prints the remediation offer (dispatch
      coordinator:review-code over the uncovered commits) to stderr and
      passes the underlying gate's exit code through unchanged (0). Nothing
      hard-blocks on ordinary coverage — see coordinator_core.coverage's
      module-level hard-block decision note for the deliberate, named scope
      of that answer. `--override` / `COORDINATOR_OVERRIDE_COVERAGE_GATE`
      are accepted for backward compatibility with existing callers but are
      now no-ops (there is nothing left to override) — this subcommand does
      NOT gain a new override surface, per the plan's anti-scope.
      VERDICT=COVERED always exits 0. This subcommand owns no halt policy
      any more; review-coverage-gate.py itself deliberately does not either
      (it exits 0 on both verdicts — see its own docstring).

  pr-body --ship-verdict <text> --release-notes <text>
           [--demo-path <text>] [--commit-range <range>]
      Composes the PR body markdown from SKILL.md Step 1.5 Parts 1-3 + Step 2:
      ship verdict, release notes, optional demo path, and a collapsed commit
      log. Prints the composed body to stdout.

  active-branch-guard --pr <PR> [--force]
      SKILL.md Step 4 "Pre-merge quiet check (5-minute activity gate)": reads
      the PR's newest commit timestamp via `gh pr view --json commits` and
      halts (exit 1) if it is younger than 300 seconds, unless --force is
      given (mirrors the skill's `--force-merge-active-branch` escape hatch).

Spec backlink: docs/plans/2026-07-21-doe-skill-bash-to-claude-klabauter-python-port.md [DEAD-CITATION: plan file never committed to this repo]
  (M3 chunk MTM-2 — merging-to-main review-coverage gate / PR body / active-
  branch merge guard). Source: DoE-claude
  coordinator/skills/merging-to-main/SKILL.md §§ Step 1.5, Step 1.65, Step 4.

Exit codes:
  coverage-gate         — 0 (covered, or warn — C10: warn never halts),
                          1 (transport failure only — the underlying gate
                          could not be reached), 2 (indeterminate,
                          propagated from the underlying gate)
  pr-body               — 0 on success, 2 on usage error
  active-branch-guard   — 0 (settled or forced), 1 (too young / gh failure),
                          2 on usage error
"""
from __future__ import annotations

import argparse
import datetime
import os
import subprocess
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(_SCRIPT_DIR, "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from cc_invoke import require_engine_on_path  # noqa: E402

# The engine root must be on sys.path before the coordinator_core import
# below: this file is also published into the claude-klabauter mirror, where
# coordinator_core is NOT pip-installed and the interpreter's sys.path[0] is
# this bin/ directory, not the checkout root. Same bootstrap as
# coordinator/bin/coordinator-lesson-add (9b979ee5f).
require_engine_on_path(__file__)

from coordinator_core.win_portability import no_console_creationflags  # noqa: E402


# ---------------------------------------------------------------------------
# coverage-gate
# ---------------------------------------------------------------------------

def _run_review_coverage_gate(range_arg: str | None) -> tuple[int, str, str]:
    """Invoke the sibling review-coverage-gate.py and return
    (returncode, stdout, stderr). Isolated for test monkeypatching."""
    cmd = [sys.executable, os.path.join(_SCRIPT_DIR, "review-coverage-gate.py")]
    if range_arg:
        cmd.append(range_arg)
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        **no_console_creationflags(),  # popup-safe-env-suppressed
    )
    return proc.returncode, proc.stdout, proc.stderr


def cmd_coverage_gate(args: argparse.Namespace) -> int:
    returncode, stdout, stderr = _run_review_coverage_gate(args.range)

    if stdout:
        print(stdout, end="" if stdout.endswith("\n") else "\n")

    # C10: VERDICT=UNCOVERED is gone — below-threshold is VERDICT=WARN, which
    # never halts (see this module's docstring). This subcommand prints the
    # same remediation OFFER as before, but does not gate the return code on
    # it: the underlying gate's own exit_code (0 for WARN, same as COVERED)
    # is what gets propagated. `--override` / COORDINATOR_OVERRIDE_COVERAGE_GATE
    # are read for backward compatibility only — accepted, never a new bypass
    # surface (nothing left to bypass) — and their use is noted, not acted on.
    if "VERDICT=WARN" in stdout:
        print(
            "WARN: review-coverage gate below threshold — the following "
            "commits in origin/main..HEAD have no code-reviewer trail "
            "record:",
            file=sys.stderr,
        )
        if stderr:
            print(stderr, end="" if stderr.endswith("\n") else "\n", file=sys.stderr)
        print("", file=sys.stderr)
        print(
            "The gate does not block on this — but the commits above are "
            "still owed a review. Remedy: dispatch coordinator:review-code "
            "over them, then re-run /merge-to-main.",
            file=sys.stderr,
        )
        overridden = args.override or os.environ.get(
            "COORDINATOR_OVERRIDE_COVERAGE_GATE", "0"
        ) == "1"
        if overridden:
            print(
                "NOTE: --override / COORDINATOR_OVERRIDE_COVERAGE_GATE=1 was "
                "set but has no effect — the coverage gate no longer halts "
                "(C10), so there is nothing to override.",
                file=sys.stderr,
            )
        return returncode

    if stderr:
        print(stderr, end="" if stderr.endswith("\n") else "\n", file=sys.stderr)

    # VERDICT=COVERED, or the underlying gate could not be reached at all —
    # propagate its exit code (0 on COVERED, 2 on INDETERMINATE, 1 on transport
    # failure) rather than reinterpreting it.
    return returncode


# ---------------------------------------------------------------------------
# pr-body
# ---------------------------------------------------------------------------

def _commit_log(commit_range: str) -> str:
    proc = subprocess.run(
        ["git", "log", commit_range, "--oneline"],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout.rstrip("\n")


def cmd_pr_body(args: argparse.Namespace) -> int:
    parts = [args.ship_verdict.rstrip("\n"), "", args.release_notes.rstrip("\n")]
    if args.demo_path:
        parts.append("")
        parts.append(args.demo_path.rstrip("\n"))
    parts.append("")
    parts.append("---")
    parts.append("")
    parts.append("<details>")
    parts.append("<summary>Commit log</summary>")
    parts.append("")
    parts.append(_commit_log(args.commit_range))
    parts.append("</details>")
    print("\n".join(parts))
    return 0


# ---------------------------------------------------------------------------
# active-branch-guard
# ---------------------------------------------------------------------------

_QUIET_WINDOW_SECONDS = 300


def _gh_pr_view_json(pr: str, jq_field: str) -> tuple[int, str]:
    """Isolated for test monkeypatching — mirrors `gh pr view <pr> --json <field>
    -q .<jq_field-or-path>`."""
    proc = subprocess.run(
        ["gh", "pr", "view", pr, "--json", jq_field.split(".")[0], "-q", f".{jq_field}"],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode, proc.stdout.strip()


def cmd_active_branch_guard(args: argparse.Namespace) -> int:
    if args.force:
        return 0

    returncode, last_iso = _gh_pr_view_json(args.pr, "commits[-1].committedDate")
    if returncode != 0 or not last_iso:
        print(
            f"merge-gate-and-pr active-branch-guard: could not read commit "
            f"timestamps for PR {args.pr!r} via gh pr view",
            file=sys.stderr,
        )
        return 1

    try:
        last = int(
            datetime.datetime.fromisoformat(
                last_iso.replace("Z", "+00:00")
            ).timestamp()
        )
    except ValueError:
        print(
            f"merge-gate-and-pr active-branch-guard: unparseable commit "
            f"timestamp {last_iso!r}",
            file=sys.stderr,
        )
        return 1

    now = int(datetime.datetime.now(tz=datetime.timezone.utc).timestamp())

    if now - last < _QUIET_WINDOW_SECONDS:
        branch_rc, branch = _gh_pr_view_json(args.pr, "headRefName")
        branch_desc = branch if branch_rc == 0 and branch else "<unknown>"
        print(
            f"Source branch {branch_desc} has commits younger than 5 minutes — "
            "wait for activity to settle, or pass --force-merge-active-branch.",
            file=sys.stderr,
        )
        return 1

    return 0


# ---------------------------------------------------------------------------
# argv plumbing
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="merge-gate-and-pr.py")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    p_gate = sub.add_parser("coverage-gate")
    p_gate.add_argument("range", nargs="?", default=None)
    p_gate.add_argument("--override", action="store_true")
    p_gate.set_defaults(func=cmd_coverage_gate)

    p_body = sub.add_parser("pr-body")
    p_body.add_argument("--ship-verdict", required=True)
    p_body.add_argument("--release-notes", required=True)
    p_body.add_argument("--demo-path", default=None)
    p_body.add_argument("--commit-range", default="main..HEAD")
    p_body.set_defaults(func=cmd_pr_body)

    p_guard = sub.add_parser("active-branch-guard")
    p_guard.add_argument("--pr", required=True)
    p_guard.add_argument("--force", action="store_true")
    p_guard.set_defaults(func=cmd_active_branch_guard)

    return parser


def main(argv: list[str]) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
