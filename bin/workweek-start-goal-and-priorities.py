"""workweek-start-goal-and-priorities.py — imperative logic ported OUT of
DoE-claude's coordinator/commands/workweek-start.md Step 5/6/6.5 bash fences
(M3 chunk C-WWS, 2026-07 bash-kill campaign).

Self-contained, self-resolving (Path(__file__)-relative — never cwd-dependent)
naked-Python CLI, co-located with (and shelling out to) its sibling bin/
CLIs — coordinator-doc-new, append-goal-event.py, coordinator-current-branch.py,
coordinator-ceremony-hook.py — via Path(__file__).parent, so it needs NO
resolve-claude-klabauter-bin ladder of its own (that ladder stays on the DoE-side calling
fence, whose job is to locate THIS script; once invoked, this script already
knows where its own siblings live).

Subcommands (one per ported concern — see each function's docstring for the
DoE-side bash fence it replaces):
    scaffold-goal        — Step 5: author a period=week goal .yaml via
                            coordinator-doc-new, then fill the scaffolder's
                            placeholder gap (period_value/weekly_perceptible/
                            objective) and the goal_id facet-key hash.
    emit-goal-event      — Step 6 (both the reset AND update-in-place
                            branches — byte-identical logic, deduplicated into
                            one subcommand rather than ported twice): YAML-aware
                            extraction of period_value/objective from an
                            authored goal artifact, then append-goal-event.py.
    commit-priorities     — Step 6 "In both cases": session-scoped git add +
                            commit + push of HEADER.md, this session's
                            priorities fragment, and this session's authored
                            goal artifacts (SID-disambiguated glob).
    commit-archive-reset  — Step 6 full-reset branch: git add + commit + push
                            of the archived week-changelog directory.
    ceremony-hook         — Step 6.5: run coordinator-ceremony-hook.py
                            workweek-start, non-blocking on failure.

NEGATIVE SPEC — do NOT port here (stays on the DoE-side calling fence, per the
M3 C-WWS dispatch brief): the resolve-claude-klabauter-bin resolver block, the
_cc_trusted/_cc_root guard preamble, the _cc_claude_klabauter CLAUDE_KLABAUTER_ROOT resolution
ladder, or any thin single-CLI-invocation fence. Those are D1/D2's concern.

Spec backlink: DoE-claude coordinator/commands/workweek-start.md §§ Step 5,
Step 6 (Reset-or-Update Decision), Step 6.5 (Project Post-Ceremony Command Hook).
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - venv-resident dep, see install-surface-completeness.md
    yaml = None

_HERE = Path(__file__).resolve().parent
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Generator-provenance declaration (generator_provenance.py).
# cmd_scaffold_goal writes state/goals/<date>-<slug>-<sid>.yaml;
# cmd_commit_priorities/cmd_commit_archive_reset commit
# state/week-changelog/HEADER*.md and archive/week-changelogs/<prior-week>/ --
# a data-dependent per-session/per-week target set, not a fixed artifact.
MUTATES = [
    "state/goals/*.yaml",
    "state/week-changelog/*.md",
    "archive/week-changelogs/**",
]


def _no_console_passthrough_kw() -> dict:
    """Local twin of `coordinator_core.win_portability.no_console_passthrough_kwargs`.

    DELIBERATE DUPLICATION, same reason as `_resolve_claude_klabauter._is_executable`:
    this script imports stdlib + yaml only and must keep running without
    coordinator_core importable. Keep the two in sync by hand.

    Why the fds are needed at all: `creationflags=CREATE_NO_WINDOW` with no
    stdout=/stderr= makes CPython omit STARTF_USESTDHANDLES, so the child
    binds its handles to the fresh window-less console the flag allocates
    instead of inheriting this process's -- and its output is lost. Gate:
    coordinator_core/tests/test_no_output_swallowing_no_console_spawn.py.
    """
    kwargs: dict = {"creationflags": _NO_WINDOW}
    for key, stream in (("stdout", sys.stdout), ("stderr", sys.stderr)):
        try:
            fd = stream.fileno()
        except (AttributeError, ValueError, OSError):
            continue
        if fd >= 0:
            kwargs[key] = fd
    return kwargs


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _require_yaml() -> None:
    if yaml is None:
        print(
            "workweek-start-goal-and-priorities.py: PyYAML is not importable "
            "(venv-resident dep — see docs/wiki/install-surface-completeness.md).",
            file=sys.stderr,
        )
        sys.exit(2)


def _slug_from_title(title: str) -> str:
    """Mirror coordinator-doc-new's _slug_from_title / the bash pipeline this
    replaces (`tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+//;
    s/-+$//' | cut -c1-40`): lowercase, non-alphanumeric collapsed to a single
    dash, leading/trailing dashes stripped, clamped to 40 chars.

    Review: code-reviewer F4 (workweek-start.md) — slug uniqueness itself is
    not load-bearing here; the caller's SID_SHORT is the collision-breaker for
    concurrent same-week sessions. This formula is for readability/consistency
    with the scaffolder's own `id:` slug, not to guarantee filename uniqueness
    on its own.
    """
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug[:40]


def _iso_week(now: datetime | None = None) -> str:
    """Mirror `date -u +%G-W%V` (ISO 8601 week-numbering year + zero-padded week)."""
    now = now or datetime.now(timezone.utc)
    iso_year, iso_week, _ = now.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def _today(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%d")


def _repo_slug() -> str:
    """Mirror `git remote get-url origin | sed -E 's#.*github.com[/:]##;
    s#\\.git$##'`; falls back to 'local' when no origin is configured (same
    fallback the bash fence used: `[ -n "$_REPO" ] || _REPO="local"`)."""
    try:
        proc = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=False,
            creationflags=_NO_WINDOW,
        )
    except OSError:
        proc = None
    url = proc.stdout.strip() if proc is not None and proc.returncode == 0 else ""
    if not url:
        return "local"
    repo = re.sub(r"^.*github\.com[/:]", "", url)
    repo = re.sub(r"\.git$", "", repo)
    return repo or "local"


def _resolve_branch() -> str:
    """Shell out to the co-located coordinator-current-branch.py rather than
    re-deriving branch-name canonicalization here — one owner for the
    Windows case-sensitivity hazard that script exists to fix."""
    target = _HERE / "coordinator-current-branch.py"
    try:
        proc = subprocess.run(
            [os.environ.get("COORDINATOR_PYTHON", sys.executable), str(target)],
            capture_output=True,
            text=True,
            check=False,
            creationflags=_NO_WINDOW,
        )
    except OSError as exc:
        print(f"workweek-start-goal-and-priorities.py: cannot resolve branch: {exc}", file=sys.stderr)
        return ""
    return proc.stdout.strip()


def _git(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        check=False,
        creationflags=_NO_WINDOW,
    )


# ---------------------------------------------------------------------------
# scaffold-goal — Step 5 goal-artifact scaffolding
# ---------------------------------------------------------------------------


def _fill_goal_placeholders(path: Path, iso_week: str, objective_prose: str) -> None:
    """Fill the coordinator-doc-new `--type goal` scaffolder's placeholder gap:
    period_value + weekly_perceptible + objective.

    Review: code-reviewer F2 (workweek-start.md) — objective is written FIRST,
    before the goal_id hash is computed, and the hash input's _TEXT is then
    read BACK from the artifact (see `_read_objective`) rather than retyped —
    this guarantees the hash input and the on-disk objective are byte-identical
    instead of relying on the caller to match free text across two separate
    steps.

    Divergence from the bash oracle: the bash heredoc emitted
    `objective: "{objective_prose}"` via bare string interpolation, which
    corrupts the YAML document if `objective_prose` itself contains a double
    quote. This port uses `json.dumps` (a valid YAML double-quoted-scalar
    escaping, since YAML's double-quoted flow scalar syntax is a superset of
    JSON string syntax) instead, closing that latent quoting bug without
    changing the emitted shape for the common case.
    """
    import json

    lines = path.read_text(encoding="utf-8").splitlines()
    out = []
    for line in lines:
        if line.startswith("period_value:"):
            out.append(f'period_value: "{iso_week}"')
        elif line.strip().startswith("# weekly_perceptible: true"):
            out.append("weekly_perceptible: true")
        elif line.startswith("objective:"):
            out.append(f"objective: {json.dumps(objective_prose)}")
        else:
            out.append(line)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def _read_objective(path: Path) -> str:
    _require_yaml()
    with path.open(encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    return (doc or {}).get("objective", "") or ""


def _fill_goal_id(path: Path, goal_id: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    out = []
    for line in lines:
        if line.strip().startswith("# goal_id:"):
            out.append(f'goal_id: "{goal_id}"')
        else:
            out.append(line)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def _compute_goal_id(iso_week: str, text: str) -> str:
    """Review: code-reviewer F1 (workweek-start.md) — this authored goal_id is
    the structured-records (C15) facet key, computed the same way
    append-goal-event.py:231 computes ITS OWN wire goal_id, but the two are
    NOT guaranteed to match: append-goal-event.py independently re-derives
    its own hash inputs (REPO via its own git-ops-root resolution, TEXT via
    its own extraction) rather than consuming this value. --goal-id is
    accepted by append-goal-event.py for forward-compat only and is NOT
    substituted for the wire goal_id. Treat this field as a facet key/hint,
    distinct from the wire goal_id emitted by `emit-goal-event`.

    Hash formula (for this facet key only):
        sha1("<repo>|<root>|week|<period_value>|<text>")[:12]
    """
    repo = _repo_slug()
    root = "."
    hash_input = f"{repo}|{root}|week|{iso_week}|{text}"
    return hashlib.sha1(hash_input.encode("utf-8")).hexdigest()[:12]


def cmd_scaffold_goal(args: argparse.Namespace) -> int:
    _require_yaml()
    iso_week = args.iso_week or _iso_week()
    slug = _slug_from_title(args.title)
    out_path = Path(args.out) if args.out else Path(
        f"state/goals/{_today()}-{slug}-{args.sid_short}.yaml"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    doc_new = _HERE / "coordinator-doc-new.py"
    proc = subprocess.run(
        [
            os.environ.get("COORDINATOR_PYTHON", sys.executable),
            str(doc_new),
            "--type",
            "goal",
            "--title",
            args.title,
            "--out",
            str(out_path),
        ],
        capture_output=True,
        text=True,
        check=False,
        creationflags=_NO_WINDOW,
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        print(
            f"workweek-start-goal-and-priorities.py: scaffold-goal: coordinator-doc-new "
            f"exited {proc.returncode}",
            file=sys.stderr,
        )
        return proc.returncode

    # objective is authored FIRST; the hash input is read back from disk below
    # (byte-identical hash-input guarantee — see _fill_goal_placeholders docstring).
    objective_prose = args.objective if args.objective is not None else args.title
    _fill_goal_placeholders(out_path, iso_week, objective_prose)

    text = _read_objective(out_path)
    goal_id = _compute_goal_id(iso_week, text)
    _fill_goal_id(out_path, goal_id)

    print(str(out_path))
    return 0


# ---------------------------------------------------------------------------
# emit-goal-event — Step 6 reset + update-in-place paths (identical logic,
# deduplicated into one subcommand invoked from both branches)
# ---------------------------------------------------------------------------


def cmd_emit_goal_event(args: argparse.Namespace) -> int:
    """Review: code-reviewer F3 (workweek-start.md) — YAML-aware extraction
    (not grep+sed line-matching): goals-okr-system.md sanctions
    `objective: >-` as a multi-line folded block scalar, which a
    `grep '^objective:'` + sed one-liner cannot parse (yields an
    empty/garbage value, which then hard-errors append-goal-event.py's
    --text requirement). yaml.safe_load tolerates whatever shape
    objective/period_value legitimately take.

    Review: A-F9 (workweek-start.md) — single-emission point per goal
    artifact: the DoE-side caller invokes this subcommand exactly once per
    priority, from either the reset branch or the update-in-place branch
    (never both), so no double-emit guard is needed here.

    Review: A-F13 (workweek-start.md) — absolute/repo-relative path required;
    /workweek-start runs from arbitrary cwd.
    """
    _require_yaml()
    goal_path = Path(args.goal)
    with goal_path.open(encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    doc = doc or {}
    period_value = doc.get("period_value", "") or ""
    text = doc.get("objective", "") or ""

    append_goal_event = _HERE / "append-goal-event.py"
    proc = subprocess.run(
        [
            os.environ.get("COORDINATOR_PYTHON", sys.executable),
            str(append_goal_event),
            "--period",
            "week",
            "--period-value",
            period_value,
            "--text",
            text,
        ],
        text=True,
        check=False,
        **_no_console_passthrough_kw(),
    )
    return proc.returncode


# ---------------------------------------------------------------------------
# commit-priorities — Step 6 "In both cases" session-scoped commit+push
# ---------------------------------------------------------------------------


def cmd_commit_priorities(args: argparse.Namespace) -> int:
    """Stage only THIS session's own fragment and THIS session's own goal
    artifacts — never a sibling collaborator's fragment file or goal artifact
    (both are SID-disambiguated, so the glob below is inherently
    session-scoped)."""
    sid = args.sid_short
    header = Path("state/week-changelog/HEADER.md")
    fragment = Path(f"state/week-changelog/HEADER.priorities.{sid}.md")
    goal_artifacts = [Path(p) for p in glob.glob(f"state/goals/*-{sid}.yaml")]

    paths = [p for p in [header, fragment, *goal_artifacts] if p.exists()]
    missing = [p for p in [header, fragment] if not p.exists()]
    for p in missing:
        print(f"workweek-start-goal-and-priorities.py: commit-priorities: WARN missing {p}", file=sys.stderr)
    if not paths:
        print("workweek-start-goal-and-priorities.py: commit-priorities: nothing to stage", file=sys.stderr)
        return 1

    str_paths = [str(p) for p in paths]
    add_proc = _git(["add", "--", *str_paths])
    if add_proc.returncode != 0:
        sys.stderr.write(add_proc.stderr)
        return add_proc.returncode

    message = args.message or f"chore(workweek-start): set week priorities {_today()}"
    commit_proc = _git(["commit", "-m", message])
    if commit_proc.returncode != 0:
        sys.stderr.write(commit_proc.stderr)
        return commit_proc.returncode

    branch = _resolve_branch()
    if not branch:
        print("workweek-start-goal-and-priorities.py: commit-priorities: no current branch to push", file=sys.stderr)
        return 1
    push_proc = _git(["push", "origin", branch])
    if push_proc.returncode != 0:
        sys.stderr.write(push_proc.stderr)
        return push_proc.returncode
    return 0


# ---------------------------------------------------------------------------
# commit-archive-reset — Step 6 full-reset branch commit+push
# ---------------------------------------------------------------------------


def cmd_commit_archive_reset(args: argparse.Namespace) -> int:
    week_dir = Path("state/week-changelog/")
    archive_dir = Path(f"archive/week-changelogs/{args.prior_week_start}/")

    paths = [p for p in [week_dir, archive_dir] if p.exists()]
    if not paths:
        print("workweek-start-goal-and-priorities.py: commit-archive-reset: nothing to stage", file=sys.stderr)
        return 1

    add_proc = _git(["add", "--", *[str(p) for p in paths]])
    if add_proc.returncode != 0:
        sys.stderr.write(add_proc.stderr)
        return add_proc.returncode

    message = args.message or f"chore(workweek-start): archive prior week, reset changelog {_today()}"
    commit_proc = _git(["commit", "-m", message])
    if commit_proc.returncode != 0:
        sys.stderr.write(commit_proc.stderr)
        return commit_proc.returncode

    branch = _resolve_branch()
    if not branch:
        print("workweek-start-goal-and-priorities.py: commit-archive-reset: no current branch to push", file=sys.stderr)
        return 1
    push_proc = _git(["push", "origin", branch])
    if push_proc.returncode != 0:
        sys.stderr.write(push_proc.stderr)
        return push_proc.returncode
    return 0


# ---------------------------------------------------------------------------
# ceremony-hook — Step 6.5 post-ceremony hook (non-blocking)
# ---------------------------------------------------------------------------


def cmd_ceremony_hook(args: argparse.Namespace) -> int:
    """Review: code-reviewer F1 (workweek-start.md) — the guard below is
    defensive-only against the helper-script-absent (install-drift) case; the
    helper itself is contracted always-exit-0 (see coordinator-ceremony-hook.py's
    own module docstring), so this failure path fires only if the interpreter
    itself can't find/exec the script."""
    hook = _HERE / "coordinator-ceremony-hook.py"
    try:
        proc = subprocess.run(
            [os.environ.get("COORDINATOR_PYTHON", sys.executable), str(hook), args.ceremony],
            capture_output=True,
            text=True,
            check=False,
            creationflags=_NO_WINDOW,
        )
    except OSError as exc:
        print(f"[{args.ceremony}] WARN: ceremony-hook failed to launch (non-blocking): {exc}", file=sys.stderr)
        return 0

    if proc.returncode != 0:
        print(f"[{args.ceremony}] WARN: ceremony-hook exited non-zero (non-blocking)", file=sys.stderr)
    if proc.stderr:
        sys.stderr.write(proc.stderr)

    hook_out = proc.stdout.strip()
    if hook_out:
        print(hook_out)
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="workweek-start-goal-and-priorities.py",
        description="Ported imperative logic from /workweek-start Steps 5, 6, 6.5.",
    )
    sub = p.add_subparsers(dest="subcommand", required=True)

    sg = sub.add_parser("scaffold-goal", help="Step 5: author + fill a period=week goal artifact")
    sg.add_argument("--title", required=True, help="priority title (also the objective prose unless --objective given)")
    sg.add_argument("--objective", default=None, help="override objective prose (defaults to --title)")
    sg.add_argument("--sid-short", required=True, help="session-id short (first 8 chars) — the collision-breaker for the default --out path")
    sg.add_argument("--iso-week", default=None, help="ISO week e.g. 2026-W29 (default: computed via UTC now)")
    sg.add_argument("--out", default=None, help="output path (default: state/goals/<date>-<slug>-<sid-short>.yaml)")
    sg.set_defaults(func=cmd_scaffold_goal)

    eg = sub.add_parser("emit-goal-event", help="Step 6 (reset + update-in-place): extract + emit a goal event")
    eg.add_argument("--goal", required=True, help="path to the authored goal artifact (Step 5's --out)")
    eg.set_defaults(func=cmd_emit_goal_event)

    cp = sub.add_parser("commit-priorities", help='Step 6 "In both cases": session-scoped priorities commit+push')
    cp.add_argument("--sid-short", required=True)
    cp.add_argument("--message", default=None)
    cp.set_defaults(func=cmd_commit_priorities)

    car = sub.add_parser("commit-archive-reset", help="Step 6 full-reset branch: archived changelog commit+push")
    car.add_argument("--prior-week-start", required=True, help="YYYY-MM-DD prior week start date (archive dir name)")
    car.add_argument("--message", default=None)
    car.set_defaults(func=cmd_commit_archive_reset)

    ch = sub.add_parser("ceremony-hook", help="Step 6.5: run the post-ceremony command hook (non-blocking)")
    ch.add_argument("--ceremony", default="workweek-start")
    ch.set_defaults(func=cmd_ceremony_hook)

    return p


def main(argv: list[str]) -> int:
    args = _build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
