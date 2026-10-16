"""workflow-journal — read a run's journal.jsonl without a guard-blocked ad-hoc script.

WHY THIS EXISTS. `journal.jsonl` (the emitted `.workflow.mjs` script's own event
log, see `coordinator_core/workflow_watch/`) is the fastest way to see what a run
actually did, but a one-off `python3 <inline-script>` to parse it is exactly the
shape `block-subagent-raw-python-invoke`-class guards refuse, so the only route
left was `grep`ing raw JSON lines by hand -- unreadable, and blind to which agent
a truncated line belongs to. This is a tiny, permanent, naked-Python reader: one
line per agent label, its last-seen status, and the first line of its result (or
failure), reading the SAME event shape `coordinator_core/workflow_watch/render.py`
already renders incrementally for the live-follow case.

NOT a JournalRenderer reuse: this is a ONE-SHOT read over a (usually finished)
journal, printed as a per-agent summary table rather than a chronological event
stream -- a different question ("what did each agent end up doing") than
render.py's ("what happened, in order, as it happens"). Reading the whole file
once is fine here; there is no poll loop to make repeated re-parses expensive.

Journal event shape (one JSON object per line): `{"agentId": ..., "type":
"started"|"result"|"failed", "label": ..., "result": ...}`. A line that fails to
parse as JSON, or carries no `type`, is skipped -- never a crash.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_UNREADABLE = 3


def _first_line(text: str) -> str:
    if not isinstance(text, str):
        return ""
    return text.splitlines()[0] if text.splitlines() else ""


def summarize(journal_path: str) -> "dict[str, dict]":
    """Fold `journal_path`'s events into one summary per agentId, in
    first-seen order. Returns ``{agentId: {"label": str, "status": str,
    "result": str}}``. A malformed line is skipped, not fatal -- a
    partially-written journal (a run still in flight) still summarizes
    whatever landed so far."""
    agents: "dict[str, dict]" = {}
    with open(journal_path, "r", encoding="utf-8") as handle:
        for raw_line in handle:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                event = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            event_type = event.get("type")
            agent_id = event.get("agentId")
            if not isinstance(event_type, str):
                continue
            if not isinstance(agent_id, str) or not agent_id:
                # The single terminal-stamp line carries no agentId; it is a
                # run-level event, not a per-agent one -- out of scope for
                # this per-agent summary.
                continue
            entry = agents.setdefault(
                agent_id, {"label": agent_id, "status": "unknown", "result": ""}
            )
            label = event.get("label")
            if isinstance(label, str) and label:
                entry["label"] = label
            if event_type == "started":
                entry["status"] = "started"
            elif event_type == "result":
                entry["status"] = "result"
                result = event.get("result")
                entry["result"] = _first_line(result) if isinstance(result, str) else ""
            elif event_type == "failed":
                entry["status"] = "FAILED"
                result = event.get("result") or event.get("error")
                entry["result"] = _first_line(result) if isinstance(result, str) else ""
    return agents


def _int_field(usage: dict, key: str) -> int:
    value = usage.get(key)
    return value if isinstance(value, int) else 0


def _transcript_usage(path: Path) -> "tuple[int, int]":
    """(fresh+output, cache_read) summed over assistant records, one count per
    `message.id`: a message split across content blocks repeats its usage."""
    fresh, cache_read, _tools = _transcript_stats(path)
    return fresh, cache_read


def _transcript_stats(path: Path) -> "tuple[int, int, Counter]":
    """(fresh+output, cache_read, tool-name counts) from one read of the
    transcript. Usage counts once per `message.id`; a `tool_use` block counts
    once per block `id`, since a split message repeats its earlier blocks."""
    seen: "set[str]" = set()
    seen_tools: "set[str]" = set()
    tools: Counter = Counter()
    fresh = cache_read = 0
    with open(path, "r", encoding="utf-8") as handle:
        for raw_line in handle:
            if '"assistant"' not in raw_line:
                continue
            try:
                record = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict) or record.get("type") != "assistant":
                continue
            message = record.get("message")
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tool_id = block.get("id")
                        if isinstance(tool_id, str) and tool_id:
                            if tool_id in seen_tools:
                                continue
                            seen_tools.add(tool_id)
                        name = block.get("name")
                        tools[name if isinstance(name, str) and name else "(unnamed)"] += 1
            usage = message.get("usage")
            if not isinstance(usage, dict):
                continue
            message_id = message.get("id")
            if isinstance(message_id, str) and message_id:
                if message_id in seen:
                    continue
                seen.add(message_id)

            fresh += (_int_field(usage, "input_tokens") + _int_field(usage, "cache_creation_input_tokens")
                      + _int_field(usage, "output_tokens"))
            cache_read += _int_field(usage, "cache_read_input_tokens")
    return fresh, cache_read, tools


_LABEL_ID_SUFFIX = re.compile(r":[^:\s]*$")


def census(root: Path, since_days: "float | None" = None) -> "dict[str, dict]":
    """Fold every agent under `<root>/*/*/subagents/workflows/*/journal.jsonl`
    by label with `:<id>` suffixes stripped. Returns ``{label: {"runs": int,
    "fresh": int, "tool_calls": int, "tools": Counter}}``. A journal older than
    `since_days`, an unreadable journal, or an agent without a readable
    transcript is skipped."""
    cutoff = None if since_days is None else time.time() - since_days * 86400
    labels: "dict[str, dict]" = {}
    for journal in sorted(root.glob("*/*/subagents/workflows/*/journal.jsonl")):
        try:
            if cutoff is not None and journal.stat().st_mtime < cutoff:
                continue
            agents = summarize(str(journal))
        except OSError:
            continue
        for agent_id, entry in agents.items():
            try:
                fresh, _cache, tools = _transcript_stats(journal.with_name(f"agent-{agent_id}.jsonl"))
            except OSError:
                continue
            label = _LABEL_ID_SUFFIX.sub("", entry["label"]) or entry["label"]
            bucket = labels.setdefault(
                label, {"runs": 0, "fresh": 0, "tool_calls": 0, "tools": Counter()})
            bucket["runs"] += 1
            bucket["fresh"] += fresh
            bucket["tool_calls"] += sum(tools.values())
            bucket["tools"].update(tools)
    return labels


def _default_root() -> Path:
    config = os.environ.get("CLAUDE_CONFIG_DIR")
    return (Path(config) if config else Path.home() / ".claude") / "projects"


def _print_census(labels: "dict[str, dict]") -> None:
    for label, b in sorted(labels.items(), key=lambda kv: -kv[1]["runs"]):
        runs = b["runs"]
        tools = " ".join(f"{n}={c}" for n, c in b["tools"].most_common())
        print(f"{label}  runs={runs}  avg_tokens={b['fresh'] // runs}  "
              f"avg_tool_calls={b['tool_calls'] / runs:.1f}  tools: {tools or '-'}")


def phase_tokens(journal_path: str) -> "dict[str, dict]":
    """Per-phase token totals from the `agent-<id>.meta.json` / `.jsonl` pairs
    beside `journal_path`. Returns ``{phase: {"agents": int, "models": [str],
    "fresh": int, "cache_read": int}}``. A meta without a readable transcript,
    or an unreadable meta, is skipped."""
    phases: "dict[str, dict]" = {}
    for meta_path in sorted(Path(journal_path).resolve().parent.glob("agent-*.meta.json")):
        transcript = meta_path.with_name(meta_path.name[: -len(".meta.json")] + ".jsonl")
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            fresh, cache_read = _transcript_usage(transcript)
        except (OSError, ValueError):
            continue
        if not isinstance(meta, dict):
            continue
        phase = meta.get("workflowPhase")
        entry = phases.setdefault(
            phase if isinstance(phase, str) and phase else "(no phase)",
            {"agents": 0, "models": [], "fresh": 0, "cache_read": 0},
        )
        entry["agents"] += 1
        entry["fresh"] += fresh
        entry["cache_read"] += cache_read
        model = meta.get("model")
        if isinstance(model, str) and model and model not in entry["models"]:
            entry["models"].append(model)
    return phases


def _print_tokens(phases: "dict[str, dict]") -> None:
    print(f"{'phase':<28} {'agents':>6}  {'model':<16} {'fresh+output':>13} {'cache_read':>12}")
    for name, e in phases.items():
        print(f"{name:<28} {e['agents']:>6}  {','.join(e['models']):<16} "
              f"{e['fresh']:>13} {e['cache_read']:>12}")
    print(f"{'TOTAL':<28} {sum(e['agents'] for e in phases.values()):>6}  {'':<16} "
          f"{sum(e['fresh'] for e in phases.values()):>13} "
          f"{sum(e['cache_read'] for e in phases.values()):>12}")


def _transcript_span(path: Path) -> "tuple[float, float] | None":
    """(first, last) record timestamp in epoch seconds, or None when no record
    carries a parseable ISO `timestamp`."""
    first = last = None
    with open(path, "r", encoding="utf-8") as handle:
        for raw_line in handle:
            if '"timestamp"' not in raw_line:
                continue
            try:
                record = json.loads(raw_line)
                stamp = record["timestamp"]
                moment = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            except (ValueError, KeyError, TypeError, AttributeError):
                continue
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=timezone.utc)
            seconds = moment.timestamp()
            first = seconds if first is None else min(first, seconds)
            last = seconds if last is None else max(last, seconds)
    return None if first is None else (first, last)


def critical_path(journal_path: str) -> dict:
    """Leg count, critical-path depth and wall-clock span from the
    `agent-<id>.meta.json` / `.jsonl` pairs beside `journal_path`. Returns
    ``{"legs": int, "depth": int, "chain": [(label, phase)], "span": float,
    "unplaced": [label]}``. The chain is the longest run of agents each
    starting at or after the previous one's end; an agent with no readable
    timestamp is counted in `legs` and named in `unplaced`."""
    directory = Path(journal_path).resolve().parent
    try:
        labels = {aid: e["label"] for aid, e in summarize(journal_path).items()}
    except OSError:
        labels = {}
    placed: "list[tuple[float, float, str, str]]" = []
    unplaced: "list[str]" = []
    legs = 0
    for meta_path in sorted(directory.glob("agent-*.meta.json")):
        agent_id = meta_path.name[len("agent-"): -len(".meta.json")]
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = None
        legs += 1
        if not isinstance(meta, dict):
            meta = {}
        phase = meta.get("workflowPhase")
        phase = phase if isinstance(phase, str) and phase else "(no phase)"
        label = labels.get(agent_id, agent_id)
        try:
            span = _transcript_span(meta_path.with_name(f"agent-{agent_id}.jsonl"))
        except OSError:
            span = None
        if span is None:
            unplaced.append(label)
        else:
            placed.append((span[0], span[1], label, phase))
    placed.sort(key=lambda a: (a[0], a[1]))
    best: "list[list[int]]" = []
    for i, (start, _end, _l, _p) in enumerate(placed):
        chain = [i]
        for j in range(i):
            if placed[j][1] <= start and len(best[j]) + 1 > len(chain):
                chain = best[j] + [i]
        best.append(chain)
    longest = max(best, key=len, default=[])
    wall = (max(a[1] for a in placed) - min(a[0] for a in placed)) if placed else 0.0
    return {"legs": legs, "depth": len(longest),
            "chain": [(placed[i][2], placed[i][3]) for i in longest],
            "span": wall, "unplaced": unplaced}


def _print_critical_path(result: dict) -> None:
    print(f"agent legs: {result['legs']}")
    print(f"critical-path depth: {result['depth']}")
    for label, phase in result["chain"]:
        print(f"  {phase}: {label}")
    print(f"wall-clock span: {result['span']:.1f}s")
    if result["unplaced"]:
        print(f"unplaced (no readable timestamp): {', '.join(result['unplaced'])}")


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(
        prog="workflow-journal",
        description="Print each agent label's status and the first line of its result "
        "from a run's journal.jsonl.",
    )
    parser.add_argument("journal", nargs="?", default=None,
                        help="path to the run's journal.jsonl (not used with --census)")
    parser.add_argument(
        "--label", default=None, help="print only the agent whose label matches exactly"
    )
    parser.add_argument(
        "--tokens", action="store_true",
        help="print a per-phase token table from the agent transcripts beside the journal",
    )
    parser.add_argument(
        "--critical-path", action="store_true",
        help="print agent-leg count, critical-path depth and wall-clock span from the "
        "agent transcripts beside the journal",
    )
    parser.add_argument(
        "--census", action="store_true",
        help="per-label runs, average tokens, average tool calls and tool names across "
        "every journal under --root",
    )
    parser.add_argument("--root", default=None, help="projects dir for --census")
    parser.add_argument("--since", type=float, default=1.0,
                        help="--census: only journals modified within this many days "
                        "(default 1; cost scales with transcript bytes, ~5s per 7 days)")
    args = parser.parse_args(argv[1:])

    if args.census:
        root = Path(args.root) if args.root else _default_root()
        labels = census(root, args.since)
        if not labels:
            print("workflow-journal: no workflow agents found for --census", file=sys.stderr)
            return EXIT_OK
        _print_census(labels)
        return EXIT_OK
    if args.journal is None:
        parser.error("journal is required without --census")

    if args.critical_path:
        result = critical_path(args.journal)
        if not result["legs"]:
            print("workflow-journal: no agent transcripts beside this journal", file=sys.stderr)
            return EXIT_OK
        _print_critical_path(result)
        return EXIT_OK

    if args.tokens:
        phases = phase_tokens(args.journal)
        if not phases:
            print("workflow-journal: no agent transcripts beside this journal", file=sys.stderr)
            return EXIT_OK
        _print_tokens(phases)
        return EXIT_OK

    try:
        agents = summarize(args.journal)
    except OSError as exc:
        print(f"workflow-journal: cannot read {args.journal!r}: {exc}", file=sys.stderr)
        return EXIT_UNREADABLE

    if args.label is not None:
        agents = {aid: entry for aid, entry in agents.items() if entry["label"] == args.label}
        if not agents:
            print(f"workflow-journal: no agent labeled {args.label!r} in this journal",
                  file=sys.stderr)
            return EXIT_USAGE

    if not agents:
        print("workflow-journal: no per-agent events in this journal", file=sys.stderr)
        return EXIT_OK

    for entry in agents.values():
        line = f"{entry['label']}  {entry['status']}"
        if entry["result"]:
            line += f": {entry['result']}"
        print(line)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv))
