"""Read-only spend analysis over one Claude Code session transcript.

Reads the main `<session>.jsonl` (the EM) and `<session>/subagents/agent-*.jsonl` (dispatched
workers) and reports per-role token totals, the EM share of the total, and the share of EM turns
that were product-file edits. Also reports which strict-dispatch behaviour the resolved engine's
`nudge_em_code_dispatch` hook has, so a run names the behaviour it measured.

Dollars appear only when a transcript row carries `costUSD` / `total_cost_usd`; there is no price
table, so tokens are the unit otherwise.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

TOKEN_FIELDS = (
    "input_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
    "output_tokens",
)
EDIT_TOOLS = frozenset({"Edit", "Write", "NotebookEdit", "MultiEdit"})
#: A path under one of these repo-relative prefixes is process work; everything else is product.
PROCESS_PREFIXES = (
    "state/",
    "docs/plans/",
    "docs/handoffs/",
    "scratch/",
    ".coordinator-local/",
    "archive/",
)
HOOK_RELPATH = Path("coordinator_core") / "hooks" / "nudge_em_code_dispatch.py"
_UNSIZED_USE = re.compile(r"\b(deny|context_only)\s*\(\s*[^,()]+,\s*_UNSIZED_ADVISORY\b")


def _num(value: object) -> int | float:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else 0


def _rows(path: Path):
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    for line in text.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            yield row


def is_product_path(file_path: str, cwd: str | None = None) -> bool:
    """True unless the path, relative to `cwd` when it lies under it, starts with a process prefix."""
    p = file_path.replace("\\", "/")
    if cwd:
        c = cwd.replace("\\", "/").rstrip("/") + "/"
        if p.startswith(c):
            p = p[len(c):]
    p = p.removeprefix("./")
    return not any(p.startswith(prefix) for prefix in PROCESS_PREFIXES)


def _blank() -> dict:
    return {"messages": 0, "tokens": {f: 0 for f in TOKEN_FIELDS}, "total_tokens": 0, "cost_usd": None}


def scan_transcript(path: Path) -> dict:
    """Per-transcript usage totals plus the EM-style edit/turn counters.

    A streamed assistant message can appear on several rows; the last row per
    (message id, request id) wins so its usage is counted once.
    """
    by_key: dict[tuple, dict] = {}
    cost: float | None = None
    for n, row in enumerate(_rows(path)):
        for field in ("costUSD", "total_cost_usd"):
            v = row.get(field)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                cost = (cost or 0.0) + v
        msg = row.get("message")
        if not isinstance(msg, dict) or msg.get("role") != "assistant":
            continue
        key = (msg.get("id") or f"row{n}", row.get("requestId"))
        by_key[key] = {"message": msg, "cwd": row.get("cwd")}
    out = _blank()
    out["cost_usd"] = cost
    out.update(turns=0, tool_calls=0, edits=0, product_edits=0, process_edits=0)
    for rec in by_key.values():
        msg = rec["message"]
        out["messages"] += 1
        out["turns"] += 1
        usage = msg.get("usage") if isinstance(msg.get("usage"), dict) else {}
        for f in TOKEN_FIELDS:
            out["tokens"][f] += int(_num(usage.get(f)))
        content = msg.get("content") if isinstance(msg.get("content"), list) else []
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            out["tool_calls"] += 1
            if block.get("name") not in EDIT_TOOLS:
                continue
            inp = block.get("input") if isinstance(block.get("input"), dict) else {}
            fp = inp.get("file_path") or inp.get("notebook_path") or inp.get("path")
            if not isinstance(fp, str):
                continue
            out["edits"] += 1
            if is_product_path(fp, rec["cwd"]):
                out["product_edits"] += 1
            else:
                out["process_edits"] += 1
    out["total_tokens"] = sum(out["tokens"].values())
    return out


def strict_dispatch_mode(engine_root: Path | str | None) -> str:
    """`advisory`, `deny` or `unknown`, read from the hook source's unsized-session branch."""
    if engine_root is None:
        return "unknown"
    try:
        src = (Path(engine_root) / HOOK_RELPATH).read_text(encoding="utf-8")
    except OSError:
        return "unknown"
    modes = {m.group(1) for m in _UNSIZED_USE.finditer(src)}
    if modes == {"context_only"}:
        return "advisory"
    if modes == {"deny"}:
        return "deny"
    return "unknown"


def _ratio(num: float, den: float) -> float | None:
    return round(num / den, 6) if den else None


def build_report(
    transcript: Path,
    engine_root: Path | str | None = None,
    provenance: tuple | list | None = None,
) -> dict:
    transcript = Path(transcript)
    em = scan_transcript(transcript)
    sub_dir = transcript.with_suffix("") / "subagents"
    sub = _blank()
    sub["agents"] = 0
    for f in sorted(sub_dir.glob("agent-*.jsonl")) if sub_dir.is_dir() else []:
        s = scan_transcript(f)
        sub["agents"] += 1
        sub["messages"] += s["messages"]
        sub["total_tokens"] += s["total_tokens"]
        for k in TOKEN_FIELDS:
            sub["tokens"][k] += s["tokens"][k]
        if s["cost_usd"] is not None:
            sub["cost_usd"] = (sub["cost_usd"] or 0.0) + s["cost_usd"]
    total = em["total_tokens"] + sub["total_tokens"]
    report = {
        "transcript": str(transcript),
        "unit": "tokens",
        "em": {k: em[k] for k in ("messages", "tokens", "total_tokens", "cost_usd")},
        "subagents": sub,
        "total_tokens": total,
        "em_share": _ratio(em["total_tokens"], total),
        "em_tool_calls": em["tool_calls"],
        "em_turns": em["turns"],
        "em_edit_calls": em["edits"],
        "em_product_edits": em["product_edits"],
        "em_process_edits": em["process_edits"],
        "product_edit_share": _ratio(em["product_edits"], em["turns"]),
        "strict_dispatch_mode": strict_dispatch_mode(engine_root),
        "engine_root": str(engine_root) if engine_root is not None else None,
        "engine_provenance": list(provenance) if provenance else None,
    }
    costs = [c for c in (em["cost_usd"], sub["cost_usd"]) if c is not None]
    if costs:
        report["cost_usd_total"] = sum(costs)
        if em["cost_usd"] is not None:
            report["em_cost_share"] = _ratio(em["cost_usd"], sum(costs))
    return report
