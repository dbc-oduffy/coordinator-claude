# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""merge-gate-and-pr.py — merge-time imperative logic ported off the bash
fences embedded in DoE-claude coordinator/skills/merging-to-main/SKILL.md.

K-001 (state/kill-ledger.md, 2026-08-16): the original `coverage-gate`
subcommand that used to live here — a thin wrapper relaying
review-coverage-gate.py's VERDICT line — was removed. It gated nothing
irreversible (WARN on the last 40 closes, COVERED zero times, every one
closing clean) and had decayed to printing an advisory offer nobody acted on
differently than if it printed nothing. `coordinator_core/ops/coverage_gate.py`
(which defined `run_coverage_gate`) was deleted by the same kill;
`wsc-coverage-gate-runner.py`'s `brightline-gate` subcommand is a distinct
caller and is unaffected by this removal, but it no longer goes through
`run_coverage_gate` — that function no longer exists anywhere in the tree.
(That subcommand was itself removed 2026-08-19, state/kill-ledger.md K-007.)

docs/plans/2026-08-27-the-merge-gate-is-pointed-back-at-the-coverage-engine.md
§ C1 restores a `coverage-gate` subcommand, but pointed at the surviving
engine rather than the deleted CLI: it calls `gate.validate_invocable`'s
registered `"review"` dimension (`coordinator_core/ops/gate_dimension_review.py`)
in-process — no subprocess/IPC hop, no second coverage computation, no
second review-trail reader. This is a CONSUMER of that seam; see the
dimension module's own docstring for the coverage contract itself.

Subcommands (argv[1] selects):

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

  coverage-gate [--commit-range <range>]
      Invokes `gate.validate_invocable`'s "review" dimension over the changed
      files in `--commit-range` (default "main..HEAD") and refuses (exit 1)
      when that dimension reports FAIL (an uncovered commit), relaying its
      detail string (which names an example uncovered sha) verbatim. An
      UNAVAILABLE/ERROR review verdict (tooling/corpus unreadable) does not
      refuse — this call site is fast feedback only; it does not enforce at
      the git-push layer, and its refusal message says so rather than
      implying otherwise (see docs/wiki/guard-messaging.md § Register).

Spec backlink: docs/plans/2026-07-21-doe-skill-bash-to-claude-klabauter-python-port.md [DEAD-CITATION: plan file never committed to this repo]
  (M3 chunk MTM-2 — merging-to-main review-coverage gate / PR body / active-
  branch merge guard). Source: DoE-claude
  coordinator/skills/merging-to-main/SKILL.md §§ Step 1.5, Step 1.65, Step 4.
  coverage-gate's re-wiring: docs/plans/2026-08-27-the-merge-gate-is-pointed-
  back-at-the-coverage-engine.md § C1.

Exit codes:
  pr-body               — 0 on success, 2 on usage error
  active-branch-guard   — 0 (settled or forced), 1 (too young / gh failure),
                          2 on usage error
  coverage-gate         — 0 (covered, empty range, or dimension unavailable),
                          1 (uncovered commit found), 2 on usage error
"""
from __future__ import annotations

import argparse
import datetime
import os
import subprocess
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def _win_portability_flags() -> dict:
    """Lazily resolve the engine root and return `no_console_creationflags()`.

    The engine root must be on sys.path before the coordinator_core import
    below: this file is also published into the claude-klabauter mirror, where
    coordinator_core is NOT pip-installed and the interpreter's sys.path[0] is
    this bin/ directory, not the checkout root. Same bootstrap as
    coordinator/bin/coordinator-lesson-add (9b979ee5f)."""
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_engine_on_path

    require_engine_on_path(__file__)

    from coordinator_core.win_portability import no_console_creationflags

    return no_console_creationflags()


# ---------------------------------------------------------------------------
# pr-body
# ---------------------------------------------------------------------------

def _commit_log(commit_range: str) -> str:
    proc = subprocess.run(
        ["git", "log", commit_range, "--oneline"],
        capture_output=True,
        text=True,
        check=False,
        **_win_portability_flags(),
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
# coverage-gate
# ---------------------------------------------------------------------------

_COVERAGE_GATE_ADVISORY_NOTE = (
    "enforced server-side: a push to main without a green `coverage-gate` "
    "status is refused by GH013 before the ref moves. Land it through a "
    "branch and a review record. The ruleset is deletable by any holder of "
    "the repo PAT, so this stops the accidental push, not a deliberate one."
)


def _changed_files(commit_range: str) -> list[str]:
    """Batched, single-spawn changed-file listing for `commit_range` — the
    ONLY git call this subcommand issues itself. Per-commit review coverage
    is computed downstream by `gate_dimension_review`'s already-batched
    `coverage.build_reviewed_set`; this function must never be extended to
    walk commits one at a time."""
    proc = subprocess.run(
        ["git", "diff", "--name-only", commit_range],
        capture_output=True,
        text=True,
        check=False,
        **_win_portability_flags(),
    )
    return [line for line in proc.stdout.splitlines() if line]


def _run_gate_validate_invocable(
    changed_files: list[str], diff_base: str, repo_root: str
) -> dict:
    """Isolated for test monkeypatching — the sole call into the engine seam.

    Calls `gate.validate_invocable`'s handler directly, in-process (no
    subprocess/IPC hop): `coordinator_core` is already on `sys.path` via
    `require_engine_on_path` at module import time (see top of file), and the
    handler itself is COMPUTE_ONLY (gate_validate_invocable.py's own
    docstring) — an in-process call is both correct and the only way to stay
    inside DR-344's 500ms brightline for this call site."""
    from pathlib import Path

    from coordinator_core.ops.gate_validate_invocable import _gate_validate_invocable

    return _gate_validate_invocable(
        {"changed_files": changed_files, "diff_base": diff_base},
        repo_root=Path(repo_root),
    )


def cmd_coverage_gate(args: argparse.Namespace) -> int:
    changed_files = _changed_files(args.commit_range)
    if not changed_files:
        print(
            "merge-gate-and-pr coverage-gate: no changed files in "
            f"{args.commit_range!r}; nothing to check."
        )
        return 0

    result = _run_gate_validate_invocable(changed_files, args.commit_range, os.getcwd())
    dimensions = {d["dimension"]: d for d in result.get("dimensions", [])}
    review = dimensions.get("review")
    if review is None:
        print(
            "merge-gate-and-pr coverage-gate: review dimension absent from "
            "gate.validate_invocable result.",
            file=sys.stderr,
        )
        return 0

    if review["verdict"] == "FAIL":
        print(f"merge-gate-and-pr coverage-gate: {review['detail']}", file=sys.stderr)
        print(f"merge-gate-and-pr coverage-gate: {_COVERAGE_GATE_ADVISORY_NOTE}", file=sys.stderr)
        return 1

    print(f"merge-gate-and-pr coverage-gate: {review['detail']}")
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

    p_cov = sub.add_parser("coverage-gate")
    p_cov.add_argument("--commit-range", default="main..HEAD")
    p_cov.set_defaults(func=cmd_coverage_gate)

    return parser


def main(argv: list[str]) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
