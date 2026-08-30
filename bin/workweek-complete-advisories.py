# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
coordinator/bin/workweek-complete-advisories.py — read-only advisory subcommands
for the DoE `/workweek-complete` ceremony (M3 chunk WWC-1 extirpation).

Ports FOUR genuine bash logic blocks out of DoE-claude's
`coordinator/commands/workweek-complete.md` — the resolve-claude-klabauter-bin resolver
boilerplate and `_cc_trusted`/`_cc_root` guard preambles that used to wrap each
block are NOT ported (that plumbing is the D1/D2 wave's concern; the DoE
ceremony resolves this CLI's own path via the existing resolver, then invokes
one of the subcommands below with an already-resolved path argument):

    tripwire-summary <fire-log-path>
        Step 3.5 (Runtime-Tripwire Fire-Log Triage) — summarize a TSV fire-log:
        total row count, per-fire_type counts, and any agentId firing >=3
        times. Oracle fence: workweek-complete.md:608-617.

    improvement-queue-depth <queue-dir>
        Step 4 (Improvement-Queue Triage) — count `*.yaml` entries in a
        structured-YAML improvement-queue directory and report the
        lexicographically-oldest filename (dated-filename convention).
        Oracle fence: workweek-complete.md:746-755.

    cruft-sweep-last-run <log-path>
        Cruft-sweep verification — parse the last row of the pipe-delimited
        `cruft-sweep-log.md` for its timestamp column. Oracle fence:
        workweek-complete.md:1037-1041 (Review: code-reviewer Slice C F5 —
        the log is pipe-delimited; a naive `awk '{print $1}'` returns "|" not
        the timestamp, so this parser field-splits on "|" first).

Negative-spec:
    - Does NOT resolve the engine root via the machine-local registry / .doe-root
      ladder, and does NOT probe `repos.claude_klabauter` — the DoE ceremony
      fence still owns that resolution (resolve-claude-klabauter-bin) and hands this
      CLI already-resolved path arguments.
    - Does NOT write, mutate, or delete any file — every subcommand is a
      read-only advisory scan; the caller ceremony decides whether/how to
      surface a triage trigger.

Spec backlink: DoE-claude coordinator/commands/workweek-complete.md
    (Step 3.5, Step 4, Cruft-sweep verification, Step 4c — see per-subcommand
    docstrings above for line-range oracle fences)
Port backlink: docs/plans/2026-07-23-m3-workweek-complete-extirpation.md § WWC-1
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# tripwire-summary — Step 3.5
# ---------------------------------------------------------------------------


def summarize_tripwire_fire_log(fire_log: Path) -> Optional[Dict[str, object]]:
    """Summarize a `runtime-tripwire-fire-log.tsv` file.

    Mirrors the two-awk oracle (workweek-complete.md:608-617): column layout is
    (timestamp, agentId, model, elapsed_min, fire_type), tab-separated, with a
    header row at line 1 (skipped, matching the oracle's `NR>1`).

    Returns None when `fire_log` does not exist (the oracle's
    "runtime-tripwire-fire-log.tsv absent — skipping." branch); otherwise a
    dict with:
        total_rows: int — data-row count (header excluded)
        fire_type_counts: dict[str, int] — count per fire_type (column 5)
        recurring_agents: list[tuple[str, int]] — (agentId, count) pairs with
            count >= 3, sorted by count descending (oracle: `sort -rn | head -20`)
    """
    if not fire_log.is_file():
        return None

    fire_type_counts: Dict[str, int] = {}
    agent_counts: Dict[str, int] = {}
    total_rows = 0

    with fire_log.open("r", encoding="utf-8", errors="replace") as fh:
        for lineno, line in enumerate(fh, start=1):
            if lineno == 1:
                continue  # header row — mirrors oracle's `NR>1`
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
    )[:20]  # oracle: `head -20`

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


# ---------------------------------------------------------------------------
# improvement-queue-depth — Step 4
# ---------------------------------------------------------------------------


def improvement_queue_depth(queue_dir: Path) -> Tuple[int, Optional[str]]:
    """Count `*.yaml` entries in a structured-YAML improvement-queue directory
    and report the lexicographically-oldest filename (dated-filename
    convention — mirrors `ls *.yaml | sort | head -1`, oracle
    workweek-complete.md:746-755).

    Returns (count, oldest_filename_or_None). count is 0 and oldest is None
    when `queue_dir` does not exist (oracle's "dir absent — 0 entries" branch).
    """
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


# ---------------------------------------------------------------------------
# cruft-sweep-last-run — Cruft-sweep verification
# ---------------------------------------------------------------------------


def cruft_sweep_last_run(log_path: Path) -> Optional[str]:
    """Parse the timestamp column of the last row of a pipe-delimited
    `cruft-sweep-log.md`.

    Review: code-reviewer — Slice C F5 (carried from the bash oracle,
    workweek-complete.md:1037-1041): the log is pipe-delimited
    (`<class> | <timestamp> | ...`), so a naive `awk '{print $1}'` split on
    whitespace returns the literal `"|"` separator, not the timestamp. This
    parser field-splits on `"|"` first, then strips surrounding whitespace
    from the second field (index 1) — the timestamp column.

    Returns None when the log is absent or empty (oracle's implicit
    `${LAST:-never}` fallback — the caller reports "never").
    """
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


# ---------------------------------------------------------------------------
# ubt-unresolved — Step 4c
# ---------------------------------------------------------------------------


def _cmd_ubt_unresolved(args: argparse.Namespace) -> int:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_colocated_engine_on_path

    try:
        require_colocated_engine_on_path(__file__)
    except RuntimeError as exc:
        print(f"workweek-complete-advisories.py: engine-root resolution failed: {exc}", file=sys.stderr)
        return 1

    from coordinator_core.ops.scan_unresolved_ubt_records import scan_unresolved_ubt_records

    unresolved = scan_unresolved_ubt_records(Path(args.repo_root))
    for path in unresolved:
        print(path)
    return 0


# ---------------------------------------------------------------------------
# CLI plumbing
# ---------------------------------------------------------------------------


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

    p_ubt = sub.add_parser("ubt-unresolved", help="List unresolved *.ubt-compile.pending.json markers")
    p_ubt.add_argument("repo_root", help="Repo root whose state/review-trail/ to scan")
    p_ubt.set_defaults(func=_cmd_ubt_unresolved)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
