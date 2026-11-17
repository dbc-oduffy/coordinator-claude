"""Bench harness for the /learn-lessons phases.

Materializes the seeded 148-lesson fixture into a scratch repo, then reports wall seconds,
agent() spawns per phase label and total tokens (plus tokens per phase) for either a Workflow
run journal (--journal) or a timed driver run (argv after `--`). `--baseline` records the
engine emitter's projection for the fixture queue at the checked-out base without firing it.
Phases: prepare, synth, finalize, grind. The report's `within_bar` compares measured
total_tokens to the whole-backlog token bar in contract/ceremony-budget.json; a run with no
token measurement (driver-only) carries no total_tokens or within_bar; an agent that ran with no readable usage is never under the bar. `--enforce` turns any run
not measured under the bar into exit code 3.

Journal shape accepted (JSONL, a JSON list, or {"events": [...]}): one record per agent()
call, or a start/end pair sharing an `id`, carrying `phase`, `label`, optional `model` /
`agentType`, token usage (`usage.input_tokens` + `usage.output_tokens`, or `total_tokens` /
`tokens`) and `start`/`end` (epoch seconds, epoch ms, or ISO-8601). Records with no agent
marker are ignored, so non-agent runtime events do not inflate counts.

A real Workflow run directory holds journal.jsonl (launched/started/result events keyed by
`agentId`, no usage) beside agent-<agentId>.jsonl transcripts whose `message.usage` is the usage,
repeated per content block and deduped by `message.id`; cached reads and cache writes count. An
agent with no usage from the journal or its transcript is counted in `unmeasured_agents` and
forces `within_bar` false.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from types import ModuleType

SCHEMA = "lessons-bench-report/1"
PHASES = ("prepare", "synth", "finalize", "grind")
AGENT_KEYS = ("agentType", "agent_type", "agent", "agentId")
TOKEN_KEYS = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
START_KINDS = ("agent_start", "agent-start", "agent_spawn", "agent_call", "agent")
END_KINDS = ("agent_end", "agent-end", "agent_result", "agent_done")

HERE = Path(__file__).resolve().parent
COORDINATOR = HERE.parents[1]
FIXTURE_SCRIPT = HERE / "tests" / "fixtures" / "bench-148" / "make_fixture.py"
EMITTER = COORDINATOR / "bin" / "emit-dispatch-workflow.py"
BUDGET_CONTRACT = COORDINATOR / "contract" / "ceremony-budget.json"

# example-store-repo: 3 of 148 lessons closed for ~278k tokens, the observed per-lesson rate.
EXAMPLE_STUDIO_OBSERVATION = {"tokens": 278000, "lessons_closed": 3, "queue_lessons": 148}


def _no_console() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def whole_backlog_bar() -> int:
    """The whole-backlog token bar every ceremony slice must fit under."""
    return int(json.loads(BUDGET_CONTRACT.read_text(encoding="utf-8"))["whole_backlog_token_bar"])


def _fixture_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("lessons_bench_make_fixture", FIXTURE_SCRIPT)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load {FIXTURE_SCRIPT}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def materialize(workdir: Path, count: int | None = None, seed: int | None = None) -> list[str]:
    """Write the seeded lesson queue and wiki pages under workdir; return repo-relative lesson paths."""
    fx = _fixture_module()
    paths = fx.write_repo(workdir, count or fx.DEFAULT_COUNT, seed if seed is not None else fx.DEFAULT_SEED)
    return [p.relative_to(workdir).as_posix() for p in paths]


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
    """Input plus output (plus cache) tokens of one record; never output alone."""
    raw = rec.get("usage")
    usage: dict = raw if isinstance(raw, dict) else rec
    for key in ("total_tokens", "tokens"):
        if isinstance(usage.get(key), (int, float)):
            return int(usage[key])
    return sum(int(usage.get(k) or 0) for k in TOKEN_KEYS)


def transcript_tokens(path: Path) -> int | None:
    """Total of `message.usage` over one agent transcript, each `message.id` counted once at its largest;
    None when the file is absent or carries no usage."""
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


def _is_agent(rec: dict) -> bool:
    kind = str(rec.get("type") or rec.get("event") or rec.get("kind") or "")
    return kind in START_KINDS + END_KINDS or any(k in rec for k in AGENT_KEYS)


def parse_journal(path: Path) -> dict:
    """Fold a Workflow journal into spawn, per-phase token and wall-clock totals."""
    agents: dict[str, dict] = {}
    stamps: list[float] = []
    for n, rec in enumerate(_records(path)):
        for key in ("ts", "timestamp", "start", "end", "started_at", "ended_at"):
            t = _ts(rec.get(key))
            if t is not None:
                stamps.append(t)
        if not _is_agent(rec):
            continue
        slot = agents.setdefault(str(rec.get("agentId") or rec.get("id", f"#{n}")), {"tokens": 0})
        for key in ("phase", "label", "model"):
            if rec.get(key):
                slot[key] = rec[key]
        slot["tokens"] = max(slot["tokens"], _tokens(rec))
    for key, slot in agents.items():
        if Path(key).name == key:
            read = transcript_tokens(path.parent / f"agent-{key}.jsonl")
            if read is not None:
                slot["tokens"] = max(slot["tokens"], read)
    spawns: dict[str, int] = {p: 0 for p in PHASES}
    tokens: dict[str, int] = {p: 0 for p in PHASES}
    labels: dict[str, list[str]] = {}
    for slot in agents.values():
        phase = slot.get("phase", "unlabeled")
        spawns[phase] = spawns.get(phase, 0) + 1
        tokens[phase] = tokens.get(phase, 0) + slot["tokens"]
        labels.setdefault(phase, []).append(slot.get("label", ""))
    wall = round(max(stamps) - min(stamps), 3) if len(stamps) > 1 else None
    return {
        "agent_spawns_by_phase": spawns,
        "tokens_by_phase": tokens,
        "agent_labels_by_phase": {p: sorted(l) for p, l in sorted(labels.items())},
        "agent_spawns": len(agents),
        "unmeasured_agents": sum(1 for s in agents.values() if s["tokens"] == 0),
        "total_tokens": sum(s["tokens"] for s in agents.values()),
        "journal_wall_seconds": wall,
    }


def emitter_projection(workdir: Path, appetite: str = "standard") -> dict:
    """The engine emitter's projection for the queue in workdir; emits a script, never fires it."""
    out = workdir / "scratch" / "bench.workflow.mjs"
    argv = [sys.executable, str(EMITTER), "--queue", "state/lessons", "--profile", "lessons",
            "--appetite", appetite, "--repo", str(workdir), "--repo-root", str(workdir),
            "--out", str(out), "--force"]
    proc = subprocess.run(argv, capture_output=True, text=True, creationflags=_no_console())
    start = proc.stdout.find("{\n")
    if proc.returncode != 0 or start < 0:
        raise SystemExit(f"emitter refused (rc={proc.returncode}): {(proc.stderr or proc.stdout)[-800:]}")
    result, _ = json.JSONDecoder().raw_decode(proc.stdout[start:])
    fan = result.get("fanout") or {}
    startup = int(fan.get("startupTokensTotal") or 0)
    row_out = int(fan.get("rowOutputTokensTotal") or 0)
    receipt: dict = json.loads(Path(result["receipt"]).read_text(encoding="utf-8")) if result.get("receipt") else {}
    return {
        "source": "emit-dispatch-workflow --queue state/lessons --profile lessons --appetite " + appetite,
        "expected_agents": int(fan.get("expectedAgents") or 0),
        "startup_tokens_total": startup,
        "row_output_tokens_total": row_out,
        "projected_tokens": startup + row_out,
        "admitted_count": receipt.get("admitted_count"),
        "deferred": receipt.get("deferred"),
        "admitted_slice_projected_tokens": (receipt.get("budget") or {}).get("projected", {}).get("tokens"),
    }


def run_driver(argv: list[str], cwd: Path) -> dict:
    """Time one driver invocation; argv is a list, never a shell string."""
    start = time.perf_counter()
    proc = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, creationflags=_no_console())
    return {
        "driver_argv": argv,
        "driver_exit_code": proc.returncode,
        "driver_wall_seconds": round(time.perf_counter() - start, 3),
        "driver_stdout_tail": proc.stdout[-2000:],
        "driver_stderr_tail": proc.stderr[-2000:],
    }


def build_report(args: argparse.Namespace, driver_argv: list[str]) -> dict:
    workdir = Path(args.workdir or Path(args.report).parent / "bench-repo").resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    lessons = materialize(workdir, args.count, args.seed)
    bar = args.budget_tokens or whole_backlog_bar()
    report: dict = {
        "schema": SCHEMA, "label": args.label, "workdir": str(workdir),
        "lesson_count": len(lessons), "phases": list(PHASES), "budget_tokens": bar,
        "example_studio_observation": dict(EXAMPLE_STUDIO_OBSERVATION),
    }
    if args.baseline:
        report["emitter_projection"] = emitter_projection(workdir, args.appetite)
        report["total_tokens"] = report["emitter_projection"]["projected_tokens"]
        report["agent_spawns"] = report["emitter_projection"]["expected_agents"]
        report["token_source"] = "emitter-projection"
    if driver_argv:
        argv = [a.replace("{workdir}", str(workdir)) for a in driver_argv]
        report.update(run_driver(argv, workdir))
        report["wall_seconds"] = report["driver_wall_seconds"]
    if args.journal:
        journal = parse_journal(Path(args.journal))
        report.update(journal)
        report["token_source"] = "journal"
        report.setdefault("wall_seconds", args.wall_seconds if args.wall_seconds is not None
                          else journal["journal_wall_seconds"])
    elif driver_argv:
        report.update({"agent_spawns_by_phase": {p: 0 for p in PHASES}, "agent_spawns": 0,
                       "token_source": "driver-by-construction"})
    elif not (args.baseline or args.materialize_only):
        raise SystemExit("give --journal, --baseline, a driver argv after `--`, or --materialize-only")
    if "total_tokens" in report:
        report["within_bar"] = report["total_tokens"] < bar and not report.get("unmeasured_agents")
        grind = (report.get("tokens_by_phase") or {}).get("grind")
        if grind is not None and lessons:
            report["grind_tokens_per_row"] = round(grind / len(lessons), 1)
    return report


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    driver_argv: list[str] = []
    if "--" in raw:
        cut = raw.index("--")
        raw, driver_argv = raw[:cut], raw[cut + 1:]
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--report", required=True, help="bench report JSON output path")
    ap.add_argument("--workdir", help="scratch repo the fixture is written into (default: <report dir>/bench-repo)")
    ap.add_argument("--journal", help="Workflow run journal to fold into the report")
    ap.add_argument("--baseline", action="store_true", help="record the emitter projection for the fixture queue")
    ap.add_argument("--appetite", default="standard", choices=("hunt", "standard", "sweep"))
    ap.add_argument("--count", type=int, help="lessons to generate (default 148)")
    ap.add_argument("--seed", type=int, help="fixture seed")
    ap.add_argument("--budget-tokens", type=int, help="token bar (default: whole_backlog_token_bar)")
    ap.add_argument("--wall-seconds", type=float, help="wall seconds when the journal carries no timestamps")
    ap.add_argument("--label", default="run", help="before | after | free text")
    ap.add_argument("--materialize-only", action="store_true")
    ap.add_argument("--enforce", action="store_true", help="exit 3 when total_tokens is not under the bar")
    args = ap.parse_args(raw)
    report = build_report(args, driver_argv)
    out = Path(args.report)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: report.get(k) for k in (
        "label", "wall_seconds", "agent_spawns", "total_tokens", "unmeasured_agents", "within_bar")}))
    return 3 if args.enforce and report.get("within_bar") is not True else 0


if __name__ == "__main__":
    sys.exit(main())
