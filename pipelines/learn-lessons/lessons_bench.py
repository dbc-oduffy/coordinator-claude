#!/usr/bin/env python3
"""Bench for /learn-lessons: tokens one default run (or several) cost over a lesson queue.

Reads one or more Workflow run journals (--journal, repeatable) and prints
{total_tokens, spawns, budget_stop, deferred, queued, queue_size, bar, under_bar}.

A real Workflow run directory holds journal.jsonl (launched/started/result events keyed by
`agentId`, no usage) beside agent-<agentId>.jsonl transcripts whose `message.usage` is the
usage, repeated per content block and deduped by `message.id`. An agent with no usage from the
journal or its transcript is counted in `unmeasured_agents` and forces under_bar false.

Journal shape (JSONL, a JSON list, or {"events": [...]}): one record per agent() call, or a
start/end pair sharing an `id`, carrying token usage (`usage.input_tokens` + `output_tokens` +
cache classes, or `total_tokens` / `tokens`). Records with no agent marker add no tokens or spawns.
Any record may also carry the run result fields `budget_stop` (bool), `deferred` (int) or
`deferred_ids` (list) and `queued` (int) or `queued_ids` (list).

total_tokens is the `total` class: cached reads and cache writes count with uncached input and
output, summed over every journal so a queue that needs several runs is measured whole.
budget_stop is true if any run stopped on budget; deferred is the last journal's remaining count
(a later run clears an earlier run's deferral); queued sums across journals.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCHEMA = "lessons-bench-report/1"
AGENT_KEYS = ("agentType", "agent_type", "agent", "agentId")
AGENT_KINDS = ("agent_start", "agent-start", "agent_spawn", "agent_call", "agent",
               "agent_end", "agent-end", "agent_result", "agent_done")
TOKEN_KEYS = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
CONTRACT = Path(__file__).resolve().parents[2] / "contract" / "ceremony-budget.json"


def whole_backlog_bar(contract: Path = CONTRACT) -> int:
    """The whole-backlog token bar from the ceremony-budget contract."""
    return int(json.loads(contract.read_text(encoding="utf-8"))["whole_backlog_token_bar"])


def _records(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            data = data.get("events", data.get("journal", [data]))
        return [r for r in data if isinstance(r, dict)]
    except json.JSONDecodeError:
        return [r for r in (json.loads(ln) for ln in text.splitlines() if ln.strip()) if isinstance(r, dict)]


def _tokens(rec: dict) -> int:
    usage = rec.get("usage") if isinstance(rec.get("usage"), dict) else rec
    for key in ("total_tokens", "tokens"):
        if isinstance(usage.get(key), (int, float)):
            return int(usage[key])
    return sum(int(usage.get(k) or 0) for k in TOKEN_KEYS)


def _is_agent(rec: dict) -> bool:
    kind = str(rec.get("type") or rec.get("event") or rec.get("kind") or "")
    return kind in AGENT_KINDS or any(k in rec for k in AGENT_KEYS)


def _count(rec: dict, count_key: str, ids_key: str) -> int | None:
    if isinstance(rec.get(count_key), (int, float)) and not isinstance(rec.get(count_key), bool):
        return int(rec[count_key])
    if isinstance(rec.get(ids_key), list):
        return len(rec[ids_key])
    return None


def transcript_tokens(path: Path) -> int | None:
    """Total of `message.usage` over one agent transcript, each `message.id` counted once.

    A message's usage repeats on every content block of that message, so the largest
    sighting of an id stands, as in distill_bench. Returns None when the file is absent or carries no usage.
    artifact-distillation/distill_bench.py keeps a parallel reader with the same dedupe; keep the two in step.
    """
    if not path.is_file():
        return None
    seen: dict[str, int] = {}
    for n, rec in enumerate(_records(path)):
        msg = rec.get("message") if isinstance(rec.get("message"), dict) else rec
        if not isinstance(msg.get("usage"), dict):
            continue
        mid = str(msg.get("id", f"#{n}"))
        seen[mid] = max(seen.get(mid, 0), sum(int(msg["usage"].get(k) or 0) for k in TOKEN_KEYS))
    return sum(seen.values()) if seen else None


def parse_journal(path: Path) -> dict:
    """Fold one journal into token, spawn and run-result totals.

    An agent keyed by `agentId` also reads `agent-<agentId>.jsonl` beside the journal; its
    transcript total replaces a smaller inline figure. An agent with no usage from either
    source is `unmeasured`.
    """
    agents: dict[str, int] = {}
    stop, deferred, queued = False, 0, 0
    for n, rec in enumerate(_records(path)):
        if rec.get("budget_stop") is True:
            stop = True
        d = _count(rec, "deferred", "deferred_ids")
        if d is not None:
            deferred = d
        q = _count(rec, "queued", "queued_ids")
        if q is not None:
            queued = q
        if _is_agent(rec):
            key = str(rec.get("agentId") or rec.get("id", f"#{n}"))
            agents[key] = max(agents.get(key, 0), _tokens(rec))
    for key in agents:
        if Path(key).name != key:
            continue
        read = transcript_tokens(path.parent / f"agent-{key}.jsonl")
        if read is not None:
            agents[key] = max(agents[key], read)
    return {"tokens": sum(agents.values()), "spawns": len(agents),
            "unmeasured": sum(1 for v in agents.values() if v == 0),
            "budget_stop": stop, "deferred": deferred, "queued": queued}


def build_report(journals: list[Path], queue_size: int | None, bar: int | None = None) -> dict:
    """Sum every journal; under_bar needs tokens below the bar, no budget stop and nothing deferred."""
    folded = [parse_journal(p) for p in journals]
    bar = whole_backlog_bar() if bar is None else bar
    total = sum(f["tokens"] for f in folded)
    stop = any(f["budget_stop"] for f in folded)
    unmeasured = sum(f["unmeasured"] for f in folded)
    deferred = folded[-1]["deferred"] if folded else 0
    return {
        "schema": SCHEMA,
        "total_tokens": total,
        "spawns": sum(f["spawns"] for f in folded),
        "budget_stop": stop,
        "deferred": deferred,
        "queued": sum(f["queued"] for f in folded),
        "queue_size": queue_size,
        "runs": len(folded),
        "bar": bar,
        "unmeasured_agents": unmeasured,
        "under_bar": total < bar and not stop and deferred == 0 and unmeasured == 0,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--queue-size", type=int, help="lessons in the queue being cleared")
    ap.add_argument("--journal", action="append", required=True, type=Path,
                    help="run journal; repeat for every run the queue needed")
    ap.add_argument("--bar", type=int, help="override the ceremony-budget whole_backlog_token_bar")
    ap.add_argument("--report", type=Path, help="also write the report JSON here")
    ap.add_argument("--require-bar", action="store_true", help="exit 1 unless under_bar")
    args = ap.parse_args(argv)
    report = build_report(args.journal, args.queue_size, args.bar)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(report))
    return 1 if args.require_bar and not report["under_bar"] else 0


if __name__ == "__main__":
    sys.exit(main())
