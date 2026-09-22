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

  pr-body --ship-verdict <text> --release-notes <text> [--summary <text>]
           [--verification <text>] [--risk <text>] [--demo-path <text>]
           [--links <text>] [--commit-range <range>]
      Composes the PR body in the fleet PR template's section order (DoE-claude
      coordinator/templates/github-pull-request-template.md): the
      `**Ship verdict:**` line, ## Summary, ## Release notes, ## Verification,
      ## Risk and rollback, ## Demo path (only when given), ## Links, then a
      collapsed commit log. An absent optional section renders the template's
      guidance comment. `--summary`/`--verification`/`--risk`/`--links` are
      optional because `merge_assemble`'s d4 directive composes this call
      without them. Prints the composed body to stdout.

  active-branch-guard --pr <PR> [--force]
      SKILL.md Step 4 "Pre-merge quiet check (5-minute activity gate)": reads
      the PR's newest commit timestamp via `gh pr view --json commits` and
      halts (exit 1) if it is younger than 300 seconds, unless --force is
      given (mirrors the skill's `--force-merge-active-branch` escape hatch).

  coverage-gate [--commit-range <range>]
      Invokes `gate.validate_invocable`'s "review" dimension over the changed
      files in `--commit-range` (default "main..HEAD") and refuses (exit 1)
      on anything short of an earned PASS — the same whitelist
      `post_coverage_status.compute_status` applies (C4,
      docs/plans/2026-09-11-the-merge-gate-proves-receipt-coverage.md § C4,
      AC1): FAIL (an uncovered commit), UNAVAILABLE/ERROR, an absent review
      dimension, or an empty changed-file set (`_changed_files` cannot tell
      that apart from a `git diff` failure, since it folds the rc into empty
      stdout). Relays the review dimension's detail verbatim on FAIL, which
      names an example uncovered sha and groups the rest by authoring
      Session-Id, plus one line naming each named session live or ended (see
      `gate_dimension_review`'s AC7 docstring note) and the "review coverage
      is checked at merge, not at session close" proximity. This call site
      is fast feedback only; it does not enforce at the git-push layer, and
      its refusal message says so rather than implying otherwise (see
      docs/wiki/guard-messaging.md § Register).

  coverage-gate --post-status --sha <sha> [--owner O --repo R] [--commit-range <range>]
      The PR-route gap (C5, docs/plans/2026-09-11-the-merge-gate-proves-
      receipt-coverage.md § C5): `post_coverage_status`'s only production
      caller is push.py's GH013 recovery, so a `gh pr merge` under the
      ruleset finds no status and is refused regardless of coverage. This
      delegates to `coordinator_core.ops.post_coverage_status.post_coverage_status`,
      which computes the verdict itself (nothing is computed twice), and
      prints the `PostResult` JSON. Exits 0 ONLY when `posted` and
      `state == "success"`. `--owner`/`--repo` are optional; when omitted
      they are resolved from the origin remote via
      `coordinator_core.ops.ceremony.push._resolve_github_owner_repo`. No
      token resolving, or no resolvable owner/repo, fails closed: posts
      nothing, exits 1, and names the alternative (env var or flag).

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
  coverage-gate         — 0 ONLY on an earned review-dimension PASS; 1 on
                          FAIL, UNAVAILABLE/ERROR, an absent review
                          dimension, or an empty changed-file set; 2 on
                          usage error (C4, AC1 — no production caller relied
                          on the old fail-open exits, so this is a straight
                          tightening, not a compat break)
  coverage-gate
    --post-status         — 0 ONLY when the status POSTed with
                             state=="success"; 1 on any unpostable case (no
                             token, no resolvable owner/repo) or a posted
                             non-success state; 2 on usage error (C5)
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


#: The fleet PR template's heading contract (DoE-claude
#: coordinator/templates/github-pull-request-template.md), in order, as
#: (heading, argparse dest, guidance comment). `gh pr create --body` bypasses
#: GitHub's own template fill, so this composer is what carries the template
#: to agent PRs. A section whose flag is absent renders its heading plus the
#: template's guidance comment verbatim — the body keeps the template's shape
#: and the gap reads as unfilled, not as omitted. Demo path is the one
#: section the template deletes when nothing is user-visible, so it renders
#: only when given. Parity with the template file:
#: tests/test_merge_gate_and_pr.py :: test_pr_body_sections_match_fleet_template.
_SHIP_VERDICT_PREFIX = "**Ship verdict:**"
_PR_BODY_SECTIONS: tuple[tuple[str, str, str | None], ...] = (
    ("Summary", "summary",
     "<!-- 1–3 bullets: what changed, and why it was needed. -->"),
    ("Release notes", "release_notes",
     "<!-- Group by impact: Added / Changed / Fixed / Deps / Internal. Omit empty groups. -->"),
    ("Verification", "verification",
     "<!-- What you actually ran and what it returned. Name the tests covering this change's surface,\n"
     "and say plainly what you did not run. -->"),
    ("Risk and rollback", "risk",
     "<!-- What could break and where, and how to back it out. \"Low — docs only\" is a real answer. -->"),
    ("Demo path", "demo_path", None),
    ("Links", "links",
     "<!-- Plan, sizing, handoff, memo, issue. `Closes #N` closes the issue on merge. -->"),
)


def cmd_pr_body(args: argparse.Namespace) -> int:
    verdict = args.ship_verdict.strip()
    if not verdict.startswith(_SHIP_VERDICT_PREFIX):
        verdict = f"{_SHIP_VERDICT_PREFIX} {verdict}"
    parts = [verdict]
    for heading, dest, guidance in _PR_BODY_SECTIONS:
        text = (getattr(args, dest) or "").strip("\n")
        if not text.strip():
            if guidance is None:
                continue
            text = guidance
        parts += ["", f"## {heading}", "", text]
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
    "not enforced at the git-push layer: a raw `git push origin main` still "
    "reaches the remote unchecked."
)


def _changed_files(commit_range: str) -> list[str]:
    """Batched, single-spawn changed-file listing for `commit_range` — the
    ONLY git call this subcommand issues itself. Per-commit review coverage
    is computed downstream by `gate_dimension_review`'s already-batched
    reads of `review_trail.reviewed_set.read_reviewed_set` plus
    `review_trail.receipt_credit`; this function must never be extended to
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


def _sessions_named_in_detail(detail: str) -> list[str]:
    """Pulls the Session-Id tokens `gate_dimension_review`'s FAIL detail
    grouped uncovered SHAs under (AC7) back out of the rendered string, so
    this CLI can mark each live/ended without a second coverage computation.
    The `  <token>: ` line shape (two leading spaces, then the token, then
    `: `) is the parse this depends on — see that module's
    `_uncovered_by_session_detail` docstring, which owns the shape.
    `_NO_SESSION_ID_LABEL` is skipped: it names no real session to check
    liveness for."""
    from coordinator_core.ops import gate_dimension_review

    sessions: list[str] = []
    for line in detail.splitlines():
        if not line.startswith("  "):
            continue
        token, sep, _rest = line[2:].partition(": ")
        if not sep or token == gate_dimension_review._NO_SESSION_ID_LABEL:
            continue
        sessions.append(token)
    return sessions


def _resolve_owner_repo_for_post_status(
    args: argparse.Namespace, repo_root: str
) -> tuple[str, str] | None:
    """Returns `(owner, repo)` or None (never guesses). Explicit
    `--owner`/`--repo` win; otherwise resolved from the origin remote via
    `push._resolve_github_owner_repo`, in-process, no subprocess beyond the
    one git call that function already makes."""
    if args.owner and args.repo:
        return args.owner, args.repo

    from pathlib import Path

    from coordinator_core.ops.ceremony import push

    return push._resolve_github_owner_repo(Path(repo_root))


def _cmd_coverage_gate_post_status(args: argparse.Namespace, repo_root: str) -> int:
    """`coverage-gate --post-status`: posts the review-dimension verdict as a
    commit status on `args.sha`. Delegates the verdict computation entirely
    to `post_coverage_status.post_coverage_status` — this function computes
    nothing itself, per C5's "nothing is computed twice" constraint."""
    import json

    from coordinator_core.ops import post_coverage_status

    owner_repo = _resolve_owner_repo_for_post_status(args, repo_root)
    if owner_repo is None:
        print(
            "merge-gate-and-pr coverage-gate --post-status: could not resolve "
            "owner/repo from the origin remote — pass --owner/--repo",
            file=sys.stderr,
        )
        return 1
    owner, repo = owner_repo

    if getattr(sys.modules.get("__main__"), "__file__", None) == os.path.abspath(__file__):
        post_coverage_status._merge_gate_mod = sys.modules["__main__"]

    result = post_coverage_status.post_coverage_status(
        owner, repo, args.sha, args.commit_range, repo_root=repo_root
    )
    print(json.dumps(result.to_json()))
    return 0 if (result.posted and result.state == "success") else 1


def cmd_coverage_gate(args: argparse.Namespace) -> int:
    repo_root = os.getcwd()
    if args.post_status:
        return _cmd_coverage_gate_post_status(args, repo_root)
    changed_files = _changed_files(args.commit_range)
    if not changed_files:
        print(
            "merge-gate-and-pr coverage-gate: no changed files in "
            f"{args.commit_range!r} — indistinguishable here from a `git diff` "
            "failure, refusing rather than assuming covered.",
            file=sys.stderr,
        )
        return 1

    result = _run_gate_validate_invocable(changed_files, args.commit_range, repo_root)
    dimensions = {d["dimension"]: d for d in result.get("dimensions", [])}
    review = dimensions.get("review")
    if review is None:
        print(
            "merge-gate-and-pr coverage-gate: review dimension absent from "
            "gate.validate_invocable result.",
            file=sys.stderr,
        )
        return 1

    if review["verdict"] == "PASS":
        print(f"merge-gate-and-pr coverage-gate: {review['detail']}")
        return 0

    print(f"merge-gate-and-pr coverage-gate: {review['detail']}", file=sys.stderr)
    if review["verdict"] == "FAIL":
        print(f"merge-gate-and-pr coverage-gate: {_COVERAGE_GATE_ADVISORY_NOTE}", file=sys.stderr)
        print(
            "merge-gate-and-pr coverage-gate: review coverage is checked at "
            "merge, not at session close, and these sessions closed with no "
            "reviewer receipt covering the commits listed.",
            file=sys.stderr,
        )
        from coordinator_core.session.liveness import session_live

        for session_id in _sessions_named_in_detail(review["detail"]):
            if session_live(session_id, cwd=repo_root):
                print(
                    f"merge-gate-and-pr coverage-gate: session {session_id} is "
                    "live — dispatch a reviewer from it.",
                    file=sys.stderr,
                )
            else:
                print(
                    f"merge-gate-and-pr coverage-gate: session {session_id} has "
                    "ended — no remediation route exists yet; the ruleset must "
                    "stay off for that commit.",
                    file=sys.stderr,
                )
    return 1


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
    p_body.add_argument("--summary", default=None)
    p_body.add_argument("--release-notes", required=True)
    p_body.add_argument("--verification", default=None)
    p_body.add_argument("--risk", default=None)
    p_body.add_argument("--demo-path", default=None)
    p_body.add_argument("--links", default=None)
    p_body.add_argument("--commit-range", default="main..HEAD")
    p_body.set_defaults(func=cmd_pr_body)

    p_guard = sub.add_parser("active-branch-guard")
    p_guard.add_argument("--pr", required=True)
    p_guard.add_argument("--force", action="store_true")
    p_guard.set_defaults(func=cmd_active_branch_guard)

    p_cov = sub.add_parser("coverage-gate")
    p_cov.add_argument("--commit-range", default="main..HEAD")
    p_cov.add_argument("--post-status", action="store_true")
    p_cov.add_argument("--sha", default=None)
    p_cov.add_argument("--owner", default=None)
    p_cov.add_argument("--repo", default=None)
    p_cov.set_defaults(func=cmd_coverage_gate)

    return parser


def main(argv: list[str]) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "post_status", False) and not args.sha:
        parser.error("coverage-gate --post-status requires --sha")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
