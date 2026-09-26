# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def summarize_tripwire_fire_log(fire_log: Path) -> Optional[Dict[str, object]]:
    if not fire_log.is_file():
        return None

    fire_type_counts: Dict[str, int] = {}
    agent_counts: Dict[str, int] = {}
    total_rows = 0

    with fire_log.open("r", encoding="utf-8", errors="replace") as fh:
        for lineno, line in enumerate(fh, start=1):
            if lineno == 1:
                continue
            line = line.rstrip("\n")
            if not line:
                continue
            cols = line.split("\t")
            total_rows += 1
            if len(cols) >= 2 and cols[1]:
                agent_counts[cols[1]] = agent_counts.get(cols[1], 0) + 1
            if len(cols) >= 5 and cols[4]:
                fire_type_counts[cols[4]] = fire_type_counts.get(cols[4], 0) + 1

    recurring_agents: List[Tuple[str, int]] = sorted(
        ((agent_id, count) for agent_id, count in agent_counts.items() if count >= 3),
        key=lambda pair: pair[1],
        reverse=True,
    )[:20]

    return {
        "total_rows": total_rows,
        "fire_type_counts": fire_type_counts,
        "recurring_agents": recurring_agents,
    }


def _cmd_tripwire_summary(args: argparse.Namespace) -> int:
    fire_log = Path(args.fire_log)
    summary = summarize_tripwire_fire_log(fire_log)
    if summary is None:
        print("runtime-tripwire-fire-log.tsv absent — skipping.")
        return 0

    print(summary["total_rows"])
    for fire_type in sorted(summary["fire_type_counts"]):
        print(f"{fire_type} {summary['fire_type_counts'][fire_type]}")
    for agent_id, count in summary["recurring_agents"]:
        print(f"{count} {agent_id}")
    return 0


def improvement_queue_depth(queue_dir: Path) -> Tuple[int, Optional[str]]:
    if not queue_dir.is_dir():
        return 0, None
    names = sorted(p.name for p in queue_dir.glob("*.yaml"))
    return len(names), (names[0] if names else None)


def _cmd_improvement_queue_depth(args: argparse.Namespace) -> int:
    queue_dir = Path(args.queue_dir)
    count, oldest = improvement_queue_depth(queue_dir)
    if not queue_dir.is_dir():
        print(f"Central improvement queue dir absent ({queue_dir}) — 0 entries.")
        return 0
    print(f"Central improvement queue: {count} entries; oldest (by dated filename): {oldest or 'none'}")
    return 0


def cruft_sweep_last_run(log_path: Path) -> Optional[str]:
    if not log_path.is_file():
        return None
    lines = [ln for ln in log_path.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
    if not lines:
        return None
    fields = lines[-1].split("|")
    if len(fields) < 2:
        return None
    return fields[1].strip()


def _cmd_cruft_sweep_last_run(args: argparse.Namespace) -> int:
    log_path = Path(args.log_path)
    last = cruft_sweep_last_run(log_path)
    print(f"Cruft-sweep last run: {last or 'never'}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="workweek-complete-advisories.py",
        description="Read-only advisory subcommands for the DoE /workweek-complete ceremony.",
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    p_tripwire = sub.add_parser("tripwire-summary", help="Summarize runtime-tripwire-fire-log.tsv")
    p_tripwire.add_argument("fire_log", help="Path to runtime-tripwire-fire-log.tsv")
    p_tripwire.set_defaults(func=_cmd_tripwire_summary)

    p_iq = sub.add_parser("improvement-queue-depth", help="Count + oldest entry of an improvement-queue dir")
    p_iq.add_argument("queue_dir", help="Path to a structured-YAML improvement-queue directory")
    p_iq.set_defaults(func=_cmd_improvement_queue_depth)

    p_cruft = sub.add_parser("cruft-sweep-last-run", help="Parse last-run timestamp from cruft-sweep-log.md")
    p_cruft.add_argument("log_path", help="Path to cruft-sweep-log.md")
    p_cruft.set_defaults(func=_cmd_cruft_sweep_last_run)


    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
