"""learn-lessons-age-sweep.py — completed-central-run cutoff derivation +
routed-id/orphan-strip-list cross-check for the coordinator:learn-lessons skill.

Two independent, self-contained subcommands ported from embedded bash/inline-Python
fences in `coordinator/skills/learn-lessons/SKILL.md` (coordinator doctrine repo) so the skill can
call a real, unit-tested script by name instead of hand-composing shell/heredoc logic
in prose:

  cutoff              Phase 4.5 (Local-Mode Age-Sweep) cutoff derivation: scan a
                       `learn-lessons-YYYY-MM-DD/` run-dir tree for the most recent
                       dir carrying a `COMPLETE` sentinel (a dir WITHOUT one is
                       in-progress or aborted and MUST NOT become the cutoff — a
                       half-finished central run never promoted its entries, so
                       sweeping against it would archive un-promoted universals).
                       Skip-loud (nonzero exit, message on stderr, nothing on
                       stdout) when no completed run is reachable — a globless skip
                       must be distinguishable from "ran, found nothing swept".

  check-strip-orphans Phase 5 § Strip-list orphan-rejection: every `id` in a
                       strip-list MUST correspond to a record in `records.yaml`
                       whose `change_kind` routes to a real destination (i.e. is
                       set and is not `discard`). A strip-line with no routed
                       sibling is the 2026-06-14-shape mistake — strip without
                       route, doctrine loss.

Spec backlink: coordinator/skills/learn-lessons/SKILL.md (coordinator doctrine repo)
  § Phase 4.5 — Local-Mode Age-Sweep (Bound the File) [cutoff subcommand]
  § Phase 5 — Authorization and Apply § Strip-list orphan-rejection
    [check-strip-orphans subcommand]

Self-resolving: no cwd dependence, no coordinator_core import — this port is pure
stdlib + PyYAML logic lifted verbatim from the skill's inline-Python fences, not a
call into the claude-klabauter engine.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def derive_cutoff(runs_dir: Path) -> str | None:
    """Scan `<runs_dir>/learn-lessons-20*/` for dirs carrying a `COMPLETE` sentinel.

    Returns the YYYY-MM-DD date portion of the lexically-latest completed run-dir
    name, or None if no completed run is reachable. Lexical sort is correct here
    because run-dir names embed a YYYY-MM-DD suffix (ISO date strings sort
    lexically in date order).
    """
    if not runs_dir.is_dir():
        return None

    completed_dates: list[str] = []
    for d in sorted(runs_dir.glob("learn-lessons-20*")):
        if not d.is_dir():
            continue
        if not (d / "COMPLETE").is_file():
            continue
        name = d.name
        prefix = "learn-lessons-"
        if name.startswith(prefix):
            completed_dates.append(name[len(prefix):])

    if not completed_dates:
        return None
    return sorted(completed_dates)[-1]


def _cmd_cutoff(args: argparse.Namespace) -> int:
    cutoff = derive_cutoff(args.runs_dir)
    if cutoff is None:
        # Loud, not silent: a globless skip is indistinguishable from a sweep
        # that ran and found nothing unless it's reported as a skip.
        print(
            "age-sweep: no completed central run reachable "
            "(no run-dir COMPLETE sentinel found) — skipping",
            file=sys.stderr,
        )
        return 1
    print(cutoff)
    return 0


def find_strip_orphans(records: list[dict], strip_list: list[dict]) -> list[str]:
    """Return strip-list ids that have no routed sibling in `records`.

    A record is "routed" iff it has a `change_kind` and that change_kind is not
    `discard`. Reject any strip-line whose id is not among the routed ids.
    """
    routed_ids = {
        r.get("id")
        for r in records
        if r.get("change_kind") and r["change_kind"] != "discard"
    }
    orphans: list[str] = []
    for s in strip_list:
        sid = s.get("id")
        if sid not in routed_ids:
            orphans.append(sid)
    return orphans


def _cmd_check_strip_orphans(args: argparse.Namespace) -> int:
    import yaml  # PyYAML — available in coordinator venv

    try:
        records_doc = yaml.safe_load(args.records.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        print(f"error: records file not found: {args.records}", file=sys.stderr)
        return 2
    try:
        strip_doc = yaml.safe_load(args.strip_list.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        print(f"error: strip-list file not found: {args.strip_list}", file=sys.stderr)
        return 2

    records = records_doc.get("records", []) or []
    strip_list = strip_doc.get("strip", []) or []

    orphans = find_strip_orphans(records, strip_list)
    if orphans:
        print("STRIP-ORPHAN-REJECT:", file=sys.stderr)
        for sid in orphans:
            print(f"  {sid} — in strip-list, no routed record", file=sys.stderr)
        return 1

    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="subcommand", required=True)

    p_cutoff = sub.add_parser(
        "cutoff",
        help="derive the age-sweep cutoff from the most recent COMPLETE-sentinel run-dir",
    )
    p_cutoff.add_argument(
        "runs_dir",
        type=Path,
        help="directory containing learn-lessons-YYYY-MM-DD/ run-dirs "
        "(e.g. ${CLAUDE_HOME:-$HOME}/.claude/tasks)",
    )
    p_cutoff.set_defaults(func=_cmd_cutoff)

    p_orphans = sub.add_parser(
        "check-strip-orphans",
        help="reject strip-list ids with no routed sibling in records.yaml",
    )
    p_orphans.add_argument("records", type=Path, help="path to records.yaml")
    p_orphans.add_argument("strip_list", type=Path, help="path to strip-list.yaml")
    p_orphans.set_defaults(func=_cmd_check_strip_orphans)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
