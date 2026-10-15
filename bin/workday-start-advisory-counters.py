# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""Workday-start advisory counters: tallies recurring-item YAML entries per scope.

Non-blocking -- emits counts for the operator's own awareness at session
start, never fails the ceremony on a missing or malformed directory.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

def _ensure_engine_on_path() -> None:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_colocated_engine_on_path

    try:
        require_colocated_engine_on_path(__file__)
    except RuntimeError as exc:
        print(f"{Path(__file__).name}: engine-root resolution failed: {exc}", file=sys.stderr)
        sys.exit(1)


def _import_yaml():
    try:
        import yaml
    except ImportError:  # pragma: no cover — yaml is a standing project dependency
        return None
    return yaml


def _count_yaml_entries(directory: Path) -> tuple[int, list[Path]]:
    if not directory.is_dir():
        return 0, []
    files = sorted(directory.glob("*.yaml"))
    return len(files), files


def _scan_recurring(scope: str, files: list[Path]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    yaml = _import_yaml()
    if yaml is None:
        return hits
    for path in files:
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        recurring = data.get("recurring")
        if isinstance(recurring, bool):
            continue
        if isinstance(recurring, (int, float)) and recurring >= 3:
            hits.append(
                {
                    "scope": scope,
                    "file": path.name,
                    "title": data.get("title"),
                    "recurring": recurring,
                }
            )
    return hits


def _cross_repo_commitments(repo_root: Path) -> dict[str, Any]:
    commitments_dir = repo_root / "state" / "cross-repo-commitments"
    yaml = _import_yaml()
    if not commitments_dir.is_dir() or yaml is None:
        return {"present": False, "open_count": 0, "oldest_days": None}

    open_dates: list[date] = []
    for entry in sorted(commitments_dir.glob("*.yaml")):
        try:
            data = yaml.safe_load(entry.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict) or data.get("status") != "open":
            continue
        observed = data.get("observed")
        if isinstance(observed, str):
            try:
                open_dates.append(datetime.strptime(observed, "%Y-%m-%d").date())
            except ValueError:
                pass
        elif isinstance(observed, date):
            open_dates.append(observed)

    if not open_dates:
        return {"present": True, "open_count": 0, "oldest_days": None}

    oldest = min(open_dates)
    oldest_days = (date.today() - oldest).days
    return {"present": True, "open_count": len(open_dates), "oldest_days": oldest_days}


def cmd_improvement_queue(repo_root: Path) -> dict[str, Any]:
    from coordinator_core.state_root import coordinator_state_root_central

    central: dict[str, Any] = {
        "resolved": False,
        "state_root": None,
        "dir": None,
        "count": 0,
        "oldest": None,
        "error": None,
    }
    central_root = coordinator_state_root_central()
    if not central_root:
        central["error"] = (
            "central state root unresolved — improvement-queue depth NOT checked "
            "(coordinator_state_root(central=True) resolver failed or misconfigured). "
            "Surface to PM; do not report the queue as empty."
        )
    else:
        iq_dir = Path(central_root) / "improvement-queue"
        count, files = _count_yaml_entries(iq_dir)
        central.update(
            {
                "resolved": True,
                "state_root": central_root,
                "dir": str(iq_dir),
                "count": count,
                "oldest": files[0].name if files else None,
            }
        )

    recurring: list[dict[str, Any]] = []
    if central["resolved"]:
        recurring.extend(_scan_recurring("central", files))

    local_iq_dir = repo_root / "state" / "improvement-queue"
    local_count, local_files = _count_yaml_entries(local_iq_dir)
    local = {
        "dir": str(local_iq_dir),
        "present": local_iq_dir.is_dir(),
        "count": local_count,
    }
    recurring.extend(_scan_recurring("local", local_files))

    return {
        "central": central,
        "local": local,
        "recurring": recurring,
        "commitments": _cross_repo_commitments(repo_root),
    }


def cmd_push_failures(repo_root: Path) -> dict[str, Any]:
    from coordinator_core.ops.workday_surface_auto_push_failure_stats import (
        PushFailureStatsError,
        surface_auto_push_failure_stats,
    )

    try:
        stats = surface_auto_push_failure_stats(str(repo_root))
    except PushFailureStatsError as exc:
        return {"total": 0, "recent_24h": 0, "last_line": None, "error": str(exc)}
    stats = dict(stats)
    stats.setdefault("error", None)
    return stats


def cmd_stale_stashes(repo_root: Path, threshold_days: int) -> dict[str, Any]:
    from coordinator_core.ops.workday_surface_stale_stash_entries import (
        StaleStashEntriesError,
        surface_stale_stash_entries,
    )

    try:
        return surface_stale_stash_entries(str(repo_root), threshold_days=threshold_days)
    except StaleStashEntriesError as exc:
        return {
            "threshold_days": threshold_days,
            "total": 0,
            "stale": [],
            "advice": None,
            "error": str(exc),
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="workday-start-advisory-counters.py",
        description=(
            "Advisory counters for the coordinator doctrine repo's /workday-start ceremony: "
            "improvement-queue depth, push-failure log stats, "
            "stale stashes. Each subcommand prints one line of JSON and always "
            "exits 0."
        ),
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    iq = sub.add_parser(
        "improvement-queue", help="Central + local improvement-queue depth, recurring flags, cross-repo commitments."
    )
    iq.add_argument("--repo-root", default=".", help="Calling repo's working-tree root (default: cwd).")

    pf = sub.add_parser("push-failures", help="`.git/push-failures.log` total / recent-24h / last-line stats.")
    pf.add_argument("--repo-root", default=".", help="Calling repo's working-tree root (default: cwd).")

    ss = sub.add_parser("stale-stashes", help="Surface `git stash` entries older than --threshold-days.")
    ss.add_argument("--repo-root", default=".", help="Calling repo's working-tree root (default: cwd).")
    ss.add_argument(
        "--threshold-days",
        type=int,
        default=7,
        help="Age in days at/after which a stash entry is reported as stale (default: 7).",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    _ensure_engine_on_path()
    parser = build_parser()
    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).resolve()

    try:
        if args.subcommand == "improvement-queue":
            payload = cmd_improvement_queue(repo_root)
        elif args.subcommand == "push-failures":
            payload = cmd_push_failures(repo_root)
        elif args.subcommand == "stale-stashes":
            payload = cmd_stale_stashes(repo_root, threshold_days=args.threshold_days)
        else:  # pragma: no cover — argparse `required=True` makes this unreachable
            parser.error(f"unknown subcommand {args.subcommand!r}")
            return 2
    except Exception as exc:  # noqa: BLE001 — advisory-only: never let an
        payload = {"error": f"{type(exc).__name__}: {exc}"}

    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
