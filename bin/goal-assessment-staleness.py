#!/usr/bin/env python3
"""goal-assessment-staleness — the missing reader for the never-assessed rule.

Ported from DoE-claude `coordinator/bin/goal-assessment-staleness.py` (W2-C6,
`docs/plans/2026-09-18-doe-holds-no-scripts.md`) — mechanical move, no behavioural change. This
module's `_repo_root()` was already "engine" class (§ Path resolution): `Path(__file__).resolve()
.parents[2]` names the repo root from this module's own tree whether it lives in DoE-claude's
`coordinator/bin/` or here, so nothing about the resolution changes on arrival.

WHY THIS EXISTS. `/workweek-complete` Step 1 reads a goal's `status` directly; Step 5's KR
re-assessment carries the negative-spec that it never auto-sets `status:`. Each is correct alone.
Together they mean the only writer of a terminal KR status is a human, and nothing anywhere reads
whether the human wrote — so `active` + `not-started` after the period closes is indistinguishable
from nobody having done the work. This module is the artifact that discharges the
achieved/missed/never-assessed doctrine, per `docs/wiki/invisible-doctrine.md`'s discharge test.

WHY `yaml.safe_load`, NOT A HAND-ROLLED SCRAPE. A goal artifact routinely carries inline enum
comments (see every `key_results[].status` line in `state/goals/*.yaml`: `status: not-started  #
not-started | in-progress | met | at-risk`), so a line scrape would reproduce a defect DoE-claude
already hit and fixed once (`0dfa4d2d6a`). `yaml.safe_load` discards comments by definition and is
already an in-tree dependency of several `coordinator/bin` scripts (e.g. `baton-chain-closure.py`).
Do not "simplify" this back to a line scrape.

THE PREDICATE — both legs, conjunction, `any` not `every` — one stamped KR must not hide the rest:

  - PERIOD CLOSED — `period_value` ("2026-W34") compared against the current ISO week via
    `datetime.date.isocalendar()`. Strictly BEFORE the current (year, week); the current week
    itself is not yet closed.
  - UNASSESSED — ANY `key_results[].status == "not-started"`, OR (the goal carries NO key results
    at all AND `status: active`). The `status: active` clause is the fallback for a goal record
    with an EMPTY `key_results` list, where `any(...)` over zero KRs is vacuously `False` and would
    otherwise silently pass a KR-less stale goal.
  - NEVER-ASSESSED = PERIOD CLOSED and UNASSESSED, and ONLY for a goal whose own `status` is
    `active`. Neither leg alone is reported, and a non-`active` goal (terminal) is routed to its
    own bucket below rather than into this one.

TERMINAL BUCKET. A goal whose `status` is anything other than `active` (`abandoned`, `superseded`,
`achieved`, `missed`, ...) that still carries an unstamped (`not-started`) KR is a genuine finding
but is advisory, not release-blocking: the goal already received *some* disposition, so this is
reported in its own bucket and does not affect the exit code when it is the only finding. Findings
never print silently on a green exit.

UNSUPPORTED-PERIOD BUCKET. A goal whose `period` is not `week` (`day | repo | quarter | year`) is
never silently skipped — a silent skip reintroduces exactly the gap this instrument exists to
close. It is reported in an explicit bucket naming the `period` value, and contributes no verdict
either way on the never-assessed conjunction.

ENUMERATION vs `goal-coverage-scan` (engine-resident, `bin/goal-coverage-scan.py`). That sweep
reads ONLY active goals plus any `origin_goal_id`-tagged artifact, to flag zero-coverage active
goals — a different question (is anyone working this?) that has no reason to look at a terminal
goal at all. This module enumerates EVERY `*.yaml` under the goals directory regardless of
`status`, because the terminal bucket above is exactly the case `goal-coverage-scan` structurally
cannot see. The two scans' surfaces do not merge.

Exit codes: 0 = no never-assessed goal (terminal-bucket-only findings, or none at all, are both
still 0 — advisory never blocks). 1 = at least one never-assessed goal. 2 = the instrument could
not answer at all — `goals_dir` absent/unreadable, or one or more goal artifacts failed to parse
(`unknown`/`parse_failures`). Exit 2 is a distinct fact from exit 0: "could not read" is never
folded into "read and clean".

Zero subprocess, stdlib + PyYAML only — no shell, no `date` call, no drive letters, no hardcoded
separators. `--goals-dir` overrides the default `state/goals` for fixtures; `--json` for ceremony
consumption.
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

_SUPPORTED_PERIOD = "week"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_goals_dir(repo_root: Path) -> Path:
    return repo_root / "state" / "goals"


def _load_goal(path: Path):
    """`(dict, None)` on success, or `(None, reason)` on an unreadable/malformed artifact.

    NEGATIVE-SPEC: a goal that fails to parse is never silently dropped from consideration in a
    way that could read as "checked and clean" — it is named on stderr AND carried in the
    returned `parse_failures` list, so a genuinely stale goal hiding behind a YAML error does not
    vanish from the sweep unremarked, and a non-empty `parse_failures` list forces exit code 2
    rather than folding into a clean exit 0.
    """
    import yaml

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        reason = exc.__class__.__name__
        print(f"  skipped: {path} ({reason})", file=sys.stderr)
        return None, reason
    try:
        data = yaml.load(text, Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader))
    except yaml.YAMLError as exc:
        reason = f"YAMLError: {exc}"
        print(f"  skipped: {path} ({reason})", file=sys.stderr)
        return None, reason
    if not isinstance(data, dict):
        reason = "not a mapping"
        print(f"  skipped: {path} ({reason})", file=sys.stderr)
        return None, reason
    return data, None


def _parse_iso_week(period_value) -> "tuple[int, int] | None":
    """(iso_year, iso_week) from a `period_value` like `2026-W34`, or None if unparseable."""
    # case-insensitive `-W`/`-w` separator; a lowercase-authored period_value is a typo, not a
    # different period kind.
    text = str(period_value or "").strip()
    upper = text.upper()
    if "-W" not in upper:
        return None
    year_part, _, week_part = upper.partition("-W")
    try:
        return int(year_part), int(week_part)
    except ValueError:
        return None


def _is_closed(period_value, today: datetime.date) -> "bool | None":
    """True/False once `period_value` parses; None when it does not (caller reports separately)."""
    parsed = _parse_iso_week(period_value)
    if parsed is None:
        return None
    current_year, current_week, _ = today.isocalendar()
    return parsed < (current_year, current_week)


def _has_unstamped_kr(key_results) -> bool:
    if not isinstance(key_results, list):
        return False
    return any(
        isinstance(kr, dict) and kr.get("status") == "not-started" for kr in key_results
    )


def assess(goals_dir: Path, today: "datetime.date | None" = None) -> dict:
    """The three buckets plus the overall verdict, over every `*.yaml` in `goals_dir`.

    Returns a dict: `never_assessed`, `terminal_unstamped`, `unsupported_period`, `unknown`,
    `parse_failures` — the first three lists of `{goal_id, title, path, ...}`, `unknown` a list of
    `{path, reason}` for an absent/unreadable `goals_dir`, `parse_failures` a list of
    `{path, reason}` for goal artifacts that failed to parse — and `exit_code` (0, 1, or 2). Never
    anchored to a printed count: callers assert on these lists directly.
    """
    today = today or datetime.date.today()
    never_assessed: list = []
    terminal_unstamped: list = []
    unsupported_period: list = []
    unknown: list = []
    parse_failures: list = []

    if not goals_dir.is_dir():
        unknown.append(
            {
                "path": str(goals_dir),
                "reason": "absent or not a directory",
            }
        )
        return {
            "never_assessed": never_assessed,
            "terminal_unstamped": terminal_unstamped,
            "unsupported_period": unsupported_period,
            "unknown": unknown,
            "parse_failures": parse_failures,
            "exit_code": 2,
        }

    try:
        paths = sorted(goals_dir.glob("*.yaml"))
    except OSError as exc:
        unknown.append(
            {
                "path": str(goals_dir),
                "reason": f"unreadable: {exc.__class__.__name__}",
            }
        )
        return {
            "never_assessed": never_assessed,
            "terminal_unstamped": terminal_unstamped,
            "unsupported_period": unsupported_period,
            "unknown": unknown,
            "parse_failures": parse_failures,
            "exit_code": 2,
        }

    for path in paths:
        goal, reason = _load_goal(path)
        if goal is None:
            parse_failures.append({"path": str(path), "reason": reason})
            continue

        period = str(goal.get("period") or "").strip()
        title = goal.get("title") or goal.get("id") or path.stem
        goal_id = goal.get("goal_id") or goal.get("id") or path.stem
        status = goal.get("status")
        key_results = goal.get("key_results") or []

        if period != _SUPPORTED_PERIOD:
            unsupported_period.append(
                {
                    "goal_id": goal_id,
                    "title": title,
                    "path": str(path),
                    "period": period or "(absent)",
                }
            )
            continue

        closed = _is_closed(goal.get("period_value"), today)
        if closed is None:
            unsupported_period.append(
                {
                    "goal_id": goal_id,
                    "title": title,
                    "path": str(path),
                    "period": f"week (unparseable period_value={goal.get('period_value')!r})",
                }
            )
            continue

        unstamped = _has_unstamped_kr(key_results)

        if status != "active":
            if unstamped:
                terminal_unstamped.append(
                    {
                        "goal_id": goal_id,
                        "title": title,
                        "path": str(path),
                        "status": status,
                    }
                )
            continue

        no_krs_stale = not key_results
        if closed and (unstamped or no_krs_stale):
            never_assessed.append(
                {
                    "goal_id": goal_id,
                    # The goal's own `id` field, distinct from `goal_id` above (which prefers the
                    # goal's `goal_id` hash) -- carried here so a downstream reader
                    # (goal-kr-evidence.py) does not have to re-read this same file by path just
                    # to recover it.
                    "id": goal.get("id"),
                    "title": title,
                    "path": str(path),
                    "period_value": goal.get("period_value"),
                    "key_results": key_results,
                }
            )

    if unknown or parse_failures:
        exit_code = 2
    elif never_assessed:
        exit_code = 1
    else:
        exit_code = 0
    return {
        "never_assessed": never_assessed,
        "terminal_unstamped": terminal_unstamped,
        "unsupported_period": unsupported_period,
        "unknown": unknown,
        "parse_failures": parse_failures,
        "exit_code": exit_code,
    }


def _print_bucket(label: str, rows: list, field: str = "title") -> None:
    print(f"\n{label} ({len(rows)}):")
    for row in rows:
        print(f"  {row['goal_id']}: {row[field]}  [{row['path']}]")


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        prog="goal-assessment-staleness",
        description="Report goals whose closed-week KRs were never stamped — the never-assessed rule's instrument.",
    )
    parser.add_argument(
        "--goals-dir",
        help="override the default state/goals directory (fixtures use this)",
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args(argv)

    repo_root = _repo_root()
    goals_dir = Path(args.goals_dir).resolve() if args.goals_dir else _default_goals_dir(repo_root)

    result = assess(goals_dir)

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return result["exit_code"]

    if result["unknown"]:
        print("\nUNKNOWN — could not read the goals directory (this is NOT a clean result):")
        for row in result["unknown"]:
            print(f"  {row['path']}: {row['reason']}")

    if result["parse_failures"]:
        print("\nPARSE FAILURES — could not read the following goal artifacts (NOT a clean result):")
        for row in result["parse_failures"]:
            print(f"  {row['path']}: {row['reason']}")

    if result["never_assessed"]:
        _print_bucket("NEVER-ASSESSED", result["never_assessed"])
    if result["terminal_unstamped"]:
        _print_bucket("TERMINAL, unstamped KRs (advisory)", result["terminal_unstamped"])
    if result["unsupported_period"]:
        _print_bucket("unsupported-period (advisory)", result["unsupported_period"], field="period")

    if result["unknown"] or result["parse_failures"]:
        pass  # already reported above; never print the all-clear line alongside these.
    elif not (result["never_assessed"] or result["terminal_unstamped"] or result["unsupported_period"]):
        print("No never-assessed goals.")
    elif not result["never_assessed"]:
        print("\nNo never-assessed goals (findings above are advisory-only).")

    return result["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
