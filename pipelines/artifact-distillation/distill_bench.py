#!/usr/bin/env python3
"""Bench harness for the /distill mechanical phases.

Materializes the fixed fixture set into a scratch repo, then reports wall seconds, agent()
spawns per phase label and total tokens for either a Workflow run journal (--journal) or a
timed driver run (argv after `--`). Run it once before and once after the driver lands and
compare the two reports.

Journal shape accepted (JSONL, a JSON list, or {"events": [...]}): one record per agent()
call, or a start/end pair sharing an `id`, carrying `phase`, `label`, optional `model` /
`agentType`, token usage (`usage.input_tokens` + `usage.output_tokens`, or `total_tokens` /
`tokens`) and `start`/`end` (epoch seconds, epoch ms, or ISO-8601) or `duration_ms`.
Records with no agent marker are ignored, so non-agent runtime events do not inflate counts.
A real Workflow journal carries `agentId` events with no usage; tokens then come from the
sibling `agent-<agentId>.jsonl` transcripts (`message.usage`, deduped by `message.id`), and
`usage_unread` is true when agents ran but no usage was readable (a zero is then not a measure).

A driver run reports spawns from the journal when one is supplied; with none, spawns are 0
by construction (`spawn_source: driver-by-construction`) because a driver cannot spawn one.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

SCHEMA = "distill-bench-report/1"

# Phases the driver takes over; an agent() spawn under one of these is a mechanical spawn.
MECHANICAL_PHASES = (
    "load", "harvest", "cluster", "consolidate", "source-hash", "candidates",
    "promote", "verify-citations", "archive", "scratch", "index",
)
AGENT_KEYS = ("agentType", "agent_type", "agent")
START_KINDS = ("agent_start", "agent-start", "agent_spawn", "agent_call", "agent")
END_KINDS = ("agent_end", "agent-end", "agent_result", "agent_done")


def _no_console() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def load_fixture(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != "distill-bench-set/1" or not data.get("artifacts"):
        raise SystemExit(f"{path}: not a distill-bench-set/1 fixture with artifacts")
    return data


def materialize(fixture: dict, workdir: Path) -> list[str]:
    """Write the fixture artifacts and an empty distillation log under workdir; return the paths."""
    written = []
    for art in fixture["artifacts"]:
        rel = Path(art["path"])
        if rel.is_absolute() or ".." in rel.parts:
            raise SystemExit(f"fixture path escapes the workdir: {art['path']}")
        target = workdir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(art["content"], encoding="utf-8", newline="\n")
        written.append(rel.as_posix())
    log = workdir / "state" / "distillation-log.md"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(fixture.get("log_header", "# Distillation Log\n"), encoding="utf-8", newline="\n")
    (workdir / "docs" / "wiki").mkdir(parents=True, exist_ok=True)
    return written


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
        return [r for r in (json.loads(l) for l in text.splitlines() if l.strip()) if isinstance(r, dict)]


def _ts(value) -> float | None:
    if isinstance(value, (int, float)):
        return value / 1000.0 if value > 1e11 else float(value)
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None


def _tokens(rec: dict) -> int:
    usage = rec.get("usage") if isinstance(rec.get("usage"), dict) else rec
    for key in ("total_tokens", "tokens"):
        if isinstance(usage.get(key), (int, float)):
            return int(usage[key])
    return sum(int(usage.get(k) or 0) for k in (
        "input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))


def _is_agent(rec: dict) -> bool:
    kind = str(rec.get("type") or rec.get("event") or rec.get("kind") or "")
    return (kind in START_KINDS + END_KINDS or any(k in rec for k in AGENT_KEYS)
            or bool(rec.get("agentId")))


def transcript_tokens(journal: Path, agent_id: str) -> int | None:
    """Sum message.usage in `<journal dir>/agent-<agent_id>.jsonl`, once per message.id.

    A real Workflow journal carries launched/started/result events with agentId and no usage;
    the usage lives in the sibling transcript, repeated once per content block of a message.
    Returns None when the transcript is absent or holds no usage.
    """
    safe = Path(agent_id).name
    path = journal.parent / f"agent-{safe}.jsonl"
    if safe != agent_id or not path.is_file():
        return None
    seen: dict[str, int] = {}
    anon = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = rec.get("message") if isinstance(rec, dict) else None
        if not isinstance(msg, dict) or not isinstance(msg.get("usage"), dict):
            continue
        total = sum(int(msg["usage"].get(k) or 0) for k in (
            "input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens"))
        mid = msg.get("id")
        if not mid:
            anon += 1
            mid = f"#anon{anon}"
        seen[mid] = max(seen.get(mid, 0), total)
    return sum(seen.values()) if seen else None


def parse_journal(path: Path) -> dict:
    """Fold a Workflow journal into spawn, token and wall-clock totals."""
    agents: dict[str, dict] = {}
    stamps: list[float] = []
    for n, rec in enumerate(_records(path)):
        for key in ("ts", "timestamp", "start", "end", "started_at", "ended_at"):
            t = _ts(rec.get(key))
            if t is not None:
                stamps.append(t)
        if not _is_agent(rec):
            continue
        agent_id = rec.get("agentId")
        slot = agents.setdefault(str(rec.get("id") or agent_id or f"#{n}"), {"tokens": 0})
        if agent_id:
            slot["agent_id"] = str(agent_id)
        for key in ("phase", "label", "model"):
            if rec.get(key):
                slot[key] = rec[key]
        agent_type = next((rec[k] for k in AGENT_KEYS if isinstance(rec.get(k), str)), None)
        if agent_type:
            slot["agent_type"] = agent_type
        slot["tokens"] = max(slot["tokens"], _tokens(rec))
    for slot in agents.values():
        if slot.get("agent_id"):
            from_transcript = transcript_tokens(path, slot["agent_id"])
            if from_transcript is not None:
                slot["tokens"] = max(slot["tokens"], from_transcript)
    by_phase: dict[str, int] = {}
    by_model: dict[str, int] = {}
    labels: dict[str, list[str]] = {}
    for slot in agents.values():
        phase = slot.get("phase", "unlabeled")
        by_phase[phase] = by_phase.get(phase, 0) + 1
        by_model[slot.get("model", "unspecified")] = by_model.get(slot.get("model", "unspecified"), 0) + 1
        labels.setdefault(phase, []).append(slot.get("label", ""))
    wall = round(max(stamps) - min(stamps), 3) if len(stamps) > 1 else None
    return {
        "agent_spawns_by_phase": dict(sorted(by_phase.items())),
        "agent_spawns_by_model": dict(sorted(by_model.items())),
        "agent_labels_by_phase": {p: sorted(l) for p, l in sorted(labels.items())},
        "agent_spawns_total": len(agents),
        "mechanical_spawns": sum(c for p, c in by_phase.items() if p in MECHANICAL_PHASES),
        "judgment_spawns": sum(c for p, c in by_phase.items() if p not in MECHANICAL_PHASES),
        "total_tokens": sum(s["tokens"] for s in agents.values()),
        "usage_unread": bool(agents) and not any(s["tokens"] for s in agents.values()),
        "journal_wall_seconds": wall,
    }


def run_driver(argv: list[str], cwd: Path) -> dict:
    """Time one driver invocation; argv is a list, never a shell string."""
    start = time.perf_counter()
    proc = subprocess.run(argv, cwd=cwd, capture_output=True, text=True,
                          creationflags=_no_console())
    return {
        "driver_argv": argv,
        "driver_exit_code": proc.returncode,
        "driver_wall_seconds": round(time.perf_counter() - start, 3),
        "driver_stdout_tail": proc.stdout[-2000:],
        "driver_stderr_tail": proc.stderr[-2000:],
    }


def build_report(args: argparse.Namespace, driver_argv: list[str]) -> dict:
    fixture = load_fixture(Path(args.fixture))
    workdir = Path(args.workdir or Path(args.report).parent / "bench-repo").resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    paths = materialize(fixture, workdir)
    report: dict = {
        "schema": SCHEMA, "label": args.label, "fixture": args.fixture,
        "run_id": fixture["run_id"], "artifact_count": len(paths), "workdir": str(workdir),
        "mechanical_phases": list(MECHANICAL_PHASES),
    }
    if driver_argv:
        argv = [a.replace("{workdir}", str(workdir)).replace("{run_id}", fixture["run_id"])
                for a in driver_argv]
        report.update(run_driver(argv, workdir))
        report["wall_seconds"] = report["driver_wall_seconds"]
    if args.journal:
        journal = parse_journal(Path(args.journal))
        report.update(journal)
        report["spawn_source"] = "journal"
        if "wall_seconds" not in report:
            report["wall_seconds"] = args.wall_seconds if args.wall_seconds is not None \
                else journal["journal_wall_seconds"]
    elif driver_argv:
        report.update({"agent_spawns_by_phase": {}, "agent_spawns_total": 0,
                       "mechanical_spawns": 0, "judgment_spawns": 0, "total_tokens": 0,
                       "spawn_source": "driver-by-construction"})
    elif not args.materialize_only:
        raise SystemExit("give --journal, a driver argv after `--`, or --materialize-only")
    return report


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    driver_argv: list[str] = []
    if "--" in raw:
        cut = raw.index("--")
        raw, driver_argv = raw[:cut], raw[cut + 1:]
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fixture", required=True, help="bench-set.json path")
    ap.add_argument("--report", required=True, help="bench report JSON output path")
    ap.add_argument("--workdir", help="scratch repo the fixture is written into (default: <report dir>/bench-repo)")
    ap.add_argument("--journal", help="Workflow run journal to fold into the report")
    ap.add_argument("--wall-seconds", type=float, help="wall seconds when the journal carries no timestamps")
    ap.add_argument("--label", default="run", help="before | after | free text")
    ap.add_argument("--materialize-only", action="store_true")
    args = ap.parse_args(raw)
    report = build_report(args, driver_argv)
    out = Path(args.report)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: report.get(k) for k in (
        "label", "wall_seconds", "agent_spawns_total", "mechanical_spawns", "total_tokens")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
