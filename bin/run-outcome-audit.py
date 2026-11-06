#!/usr/bin/env python3
"""run-outcome-audit.py -- per-run verdict audit over state/warp, pure file reads.

Prints one row per run directory: run id, terminal status, judge verdict with evidence, owed
(em-performed) rows, PM verbatim and exit criterion. Exits 1 when a committed or closed run has no
`met` judge backed by command output, 2 when <root>/state/warp is missing, else 0.

Source map: docs/research/run-outcome-verdict-sources/2026-11-04-run-outcome-verdict-sources/synthesis.md.
Stdlib only, no subprocess, no coordinator_core import. Distinct from example-game-repo likeness.census.

Legend:
  judge     inline_review.criterion.status of run-outcome.json ("none" = no judge record: the finding).
  backed    judge is met, observation is non-blank, and inline_review.tests passed with run > 0.
            The tests clause is this audit's tightening beyond completion_receipts.verdict.judge_verdict.
  RED       terminal committed|closed and (not backed, or applied_overstated). halted, live and unknown
            rows are never red.
  applied   applied_recorded: the run-outcome inline_review wave entries' `applied` (else `fixes`).
            applied_evidenced: `applied` rows of the wave sidecars' findings ledgers (out_of_ask excluded)
            whose `file` is in the run's recorded diff: edited/created in inline_review tests|reverify,
            else the manifest write_baseline paths. No recorded diff, no ledger or a row without a file
            evidences nothing. applied_overstated: recorded > evidenced.
  owed      manifest.json owed[] as <id>:<reason>. em_performed_row mirrors only the declared-field legs
            of em_only_act.row_is_em_performed; its body-parsing legs are not implemented here.
  OWED line  a persisted state/owed-legs row (run id, row id, reason, plan) whose plan row disposition is
            still open and whose id is not under em_discharged in the plan's evidence sidecar.
Default read narrows to committed/closed runs; --all reads every column for every run (slower).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

EM_OWNED_AGENT_TYPES = frozenset({"coordinator:em"})
_CLOSED_STATUSES = frozenset({"closed", "superseded"})
_HALTED_STATUSES = frozenset({"halted", "resumed"})
_LIVE_STAGES = frozenset({"staged", "minted"})


def em_performed_row(raw: dict) -> bool:
    """Declared-field legs of em_only_act.row_is_em_performed (performer, em_run, agent_type)."""
    return (
        raw.get("performer") == "em"
        or raw.get("em_run") is True
        or raw.get("agent_type") in EM_OWNED_AGENT_TYPES
    )


class _Unreadable(Exception):
    pass


def _load(path: str, name: str):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        raise _Unreadable(f"unreadable {name}") from exc
    if not isinstance(data, dict):
        raise _Unreadable(f"unreadable {name}")
    return data


def _terminal(run_path: str, names: set) -> tuple:
    """Return (terminal, halt_kind_or_reason) per synthesis section 2."""
    try:
        if "halted.json" in names:
            doc = _load(os.path.join(run_path, "halted.json"), "halted.json")
            status = doc.get("status")
            kind = doc.get("halted")
            kind = kind if isinstance(kind, str) else None
            if status == "landed":
                return "committed", kind
            if status in _CLOSED_STATUSES:
                closed = doc.get("closed")
                reason = closed.get("reason") if isinstance(closed, dict) else None
                return "closed", reason if isinstance(reason, str) else kind
            if status in _HALTED_STATUSES:
                return "halted", kind
            return "unknown", f"status {status!r}"
        if "run-stage.json" in names:
            stage = _load(os.path.join(run_path, "run-stage.json"), "run-stage.json").get("stage")
            if stage == "landed":
                return "committed", None
            if stage == "halted":
                return "halted", None
            if stage in _LIVE_STAGES:
                return "live", None
            return "unknown", f"stage {stage!r}"
    except _Unreadable as exc:
        return "unknown", str(exc)
    return "unknown", None


def _unquote(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
        quote = text[0]
        text = text[1:-1]
        if quote == "'":
            text = text.replace("''", "'")
    return text


def _scan_sizing(path: str) -> tuple:
    """Line-scan a sizing for (pm_verbatim, exit_criterion); None when absent."""
    pm = None
    crit = None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return "(sizing missing)", "(sizing missing)"
    n = len(lines)
    for i, line in enumerate(lines):
        if pm is None and line.startswith("pm_verbatims:"):
            for follow in lines[i + 1 : i + 8]:
                stripped = follow.strip()
                if stripped.startswith("text:"):
                    pm = _unquote(stripped[5:])
                    break
                if follow and not follow[0].isspace():
                    break
        elif crit is None and line.startswith("exit_criterion:"):
            if i + 1 < n and lines[i + 1].startswith("  statement:"):
                crit = _unquote(lines[i + 1][len("  statement:") :])
        if pm is not None and crit is not None:
            break
    return pm, crit


def _judge(outcome: dict) -> tuple:
    """Return (judge, evidence, backed) from a run-outcome.json document."""
    review = outcome.get("inline_review")
    criterion = review.get("criterion") if isinstance(review, dict) else None
    if not isinstance(criterion, dict):
        return "none", None, False
    status = criterion.get("status")
    judge = status if status in ("met", "not_met", "indeterminate") else "none"
    obs = criterion.get("observation")
    obs_ok = isinstance(obs, str) and bool(obs.strip())
    tests = review.get("tests")
    tests = tests if isinstance(tests, dict) else {}
    t_status = tests.get("status")
    t_run = tests.get("run")
    t_failed = tests.get("failed")
    tests_ok = t_status == "pass" and isinstance(t_run, int) and not isinstance(t_run, bool) and t_run > 0
    evidence = f"tests {t_status} run={t_run} failed={t_failed}"
    if obs_ok:
        evidence += "; " + " ".join(obs.split())[:80]
    return judge, evidence, judge == "met" and obs_ok and tests_ok


def _owed(manifest: dict) -> list:
    rows = manifest.get("owed")
    out = []
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict):
                out.append(f"{row.get('id')}:{row.get('reason')}")
    return out


def _read_optional(run_path: str, names: set, name: str):
    if name not in names:
        return None
    try:
        return _load(os.path.join(run_path, name), name)
    except _Unreadable:
        return None


_LEDGER_HEADING_RE = re.compile(r"(?m)^## Findings Ledger[ \t]*$")
_FENCE_RE = re.compile(r"(?m)^```[A-Za-z0-9_-]*[ \t]*\r?$")


def _int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _fold(path: str) -> str:
    """A path folded the way review_findings_ledger._run_diff_key folds it."""
    path = path.replace("\\", "/")
    while "//" in path:
        path = path.replace("//", "/")
    while path.startswith("./"):
        path = path[2:]
    return path


def _ledger_rows(text: str) -> list:
    """Row dicts of the first fenced JSON array after `## Findings Ledger`; [] when absent or unparseable."""
    heading = _LEDGER_HEADING_RE.search(text)
    if heading is None:
        return []
    rest = text[heading.start():]
    fences = list(_FENCE_RE.finditer(rest))
    if len(fences) < 2:
        return []
    try:
        rows = json.loads(rest[fences[0].end():fences[1].start()])
    except ValueError:
        return []
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def _recorded_diff(review: dict, manifest) -> set:
    """Folded paths of the run's recorded diff: edited/created lists on inline_review tests and reverify,
    else the manifest's write_baseline paths; empty when the run dir records neither."""
    paths = []
    for key in ("tests", "reverify"):
        block = review.get(key)
        if isinstance(block, dict):
            for field in ("edited", "created"):
                if isinstance(block.get(field), list):
                    paths.extend(block[field])
    if not paths and isinstance(manifest, dict) and isinstance(manifest.get("write_baseline"), dict):
        paths = list(manifest["write_baseline"])
    return {_fold(p) for p in paths if isinstance(p, str) and p.strip()}


def _applied_counts(root: str, review: dict, manifest) -> tuple:
    """`(recorded, evidenced)` review-wave applied counts; evidenced is read only when recorded > 0."""
    waves = [w["applied"] for w in review.get("wave_reviews") or [] if isinstance(w, dict) and _int(w.get("applied"))]
    recorded = sum(waves) if waves else (review["fixes"] if _int(review.get("fixes")) else 0)
    if recorded <= 0:
        return recorded, 0
    diff = _recorded_diff(review, manifest)
    sidecars = [p for p in review.get("wave_sidecar_paths") or [] if isinstance(p, str)]
    sidecars += [w["sidecar_path"] for w in review.get("wave_reviews") or [] if isinstance(w, dict) and isinstance(w.get("sidecar_path"), str)]
    evidenced = 0
    for rel in dict.fromkeys(sidecars):
        try:
            with open(rel if os.path.isabs(rel) else os.path.join(root, *rel.split("/")), "r", encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            continue
        for row in _ledger_rows(text):
            file_rel = row.get("file")
            if (
                (row.get("status") or "applied") == "applied"
                and row.get("out_of_ask") is not True
                and isinstance(file_rel, str)
                and file_rel.strip()
                and _fold(file_rel.strip()) in diff
            ):
                evidenced += 1
    return recorded, evidenced


def audit_run(root: str, run_name: str, run_path: str, names: set, sizing_cache: dict, read_all: bool) -> dict:
    terminal, detail = _terminal(run_path, names)
    row = {
        "run_id": run_name,
        "terminal": terminal,
        "halt_kind": detail,
        "sizing": None,
        "pm_verbatim": None,
        "exit_criterion": None,
        "judge": "-",
        "evidence": None,
        "backed": False,
        "owed": [],
        "applied_recorded": 0,
        "applied_evidenced": 0,
        "applied_overstated": False,
        "red": False,
    }
    if not (read_all or terminal in ("committed", "closed")):
        return row
    run_doc = _read_optional(run_path, names, "run.json")
    sizing_rel = run_doc.get("sizing_rel") if run_doc else None
    if isinstance(sizing_rel, str) and sizing_rel:
        row["sizing"] = sizing_rel
        if sizing_rel not in sizing_cache:
            sizing_cache[sizing_rel] = _scan_sizing(os.path.join(root, *sizing_rel.split("/")))
        row["pm_verbatim"], row["exit_criterion"] = sizing_cache[sizing_rel]
    outcome = _read_optional(run_path, names, "run-outcome.json")
    row["judge"], row["evidence"], row["backed"] = _judge(outcome) if outcome else ("none", None, False)
    manifest = _read_optional(run_path, names, "manifest.json")
    row["owed"] = _owed(manifest) if manifest else []
    review = outcome.get("inline_review") if outcome else None
    if isinstance(review, dict):
        row["applied_recorded"], row["applied_evidenced"] = _applied_counts(root, review, manifest)
        row["applied_overstated"] = row["applied_recorded"] > row["applied_evidenced"]
    row["red"] = terminal in ("committed", "closed") and (not row["backed"] or row["applied_overstated"])
    return row


def audit(root: str, read_all: bool = False) -> list:
    """Return one row dict per run directory under <root>/state/warp, in name order."""
    warp = os.path.join(root, "state", "warp")
    runs = []
    with os.scandir(warp) as it:
        for entry in it:
            if entry.name.startswith(".") or not entry.is_dir():
                continue
            runs.append((entry.name, entry.path))
    runs.sort()
    sizing_cache: dict = {}
    rows = []
    for name, path in runs:
        try:
            with os.scandir(path) as sub:
                names = {e.name for e in sub}
        except OSError:
            names = set()
        rows.append(audit_run(root, name, path, names, sizing_cache, read_all))
    return rows


def _flat_yaml(path: str) -> dict:
    """Top-level `key: value` pairs of a flat YAML file; {} when unreadable."""
    out: dict = {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh.read().splitlines():
                if line and not line[0].isspace() and ":" in line:
                    key, _, value = line.partition(":")
                    out[key.strip()] = _unquote(value)
    except OSError:
        return {}
    return out


def _plan_state(root: str, plan: str):
    """`(dispositions, em_discharged_ids)` for a plan by line scan, or None when unreadable.

    dispositions maps each `plan-tasks` row id to its `disposition` (default open); em_discharged_ids
    are the ids under `em_discharged:` in `<plan-stem>.evidence.yaml` beside the plan.
    """
    if not plan:
        return None
    plan_path = plan if os.path.isabs(plan) else os.path.join(root, *plan.split("/"))
    try:
        with open(plan_path, "r", encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return None
    dispositions: dict = {}
    in_block = False
    current = None
    for line in lines:
        if not in_block:
            in_block = line.strip().startswith("```yaml plan-tasks")
            continue
        if line.startswith("```"):
            break
        if line.startswith("- id:"):
            current = _unquote(line[len("- id:") :])
            dispositions[current] = "open"
        elif current is not None and line.startswith("  disposition:"):
            dispositions[current] = _unquote(line[len("  disposition:") :]) or "open"
    discharged = set()
    evidence = os.path.splitext(plan_path)[0] + ".evidence.yaml"
    try:
        with open(evidence, "r", encoding="utf-8") as fh:
            in_key = False
            for line in fh.read().splitlines():
                if line.startswith("em_discharged:"):
                    in_key = True
                elif in_key and line.startswith("  ") and not line.startswith("   ") and ":" in line:
                    discharged.add(_unquote(line.partition(":")[0]))
                elif in_key and line and not line[0].isspace():
                    in_key = False
    except OSError:
        pass
    return dispositions, discharged


def open_owed_legs(root: str) -> list:
    """Rows of `state/owed-legs/*.yaml` not discharged: the plan row's disposition is still open and
    its id is not under the evidence sidecar's `em_discharged`. An unreadable plan leaves the row open."""
    directory = os.path.join(root, "state", "owed-legs")
    try:
        names = sorted(n for n in os.listdir(directory) if n.endswith(".yaml"))
    except OSError:
        return []
    states: dict = {}
    rows = []
    for name in names:
        rec = _flat_yaml(os.path.join(directory, name))
        row_id = rec.get("id")
        if not row_id:
            continue
        plan = rec.get("plan", "")
        if plan not in states:
            states[plan] = _plan_state(root, plan)
        state = states[plan]
        if state is not None and (state[0].get(row_id, "open") != "open" or row_id in state[1]):
            continue
        rows.append(rec)
    return rows


def format_owed_leg(rec: dict) -> str:
    return f"OWED {rec.get('run_id')} {rec.get('id')} ({rec.get('reason')}) {rec.get('plan')}"


def _clip(text, width: int) -> str:
    if not text:
        return "-"
    text = " ".join(str(text).split())
    return text if width <= 0 or len(text) <= width else text[: width - 3] + "..."


def format_row(row: dict, width: int) -> str:
    mark = "RED " if row["red"] else "    "
    terminal = row["terminal"] + (f"({_clip(row['halt_kind'], 40)})" if row["halt_kind"] else "")
    judge = row["judge"] + (f" [{row['evidence']}]" if row["evidence"] else "")
    owed = ",".join(row["owed"]) or "-"
    applied = f" | OVERSTATED applied={row['applied_recorded']}/{row['applied_evidenced']}" if row["applied_overstated"] else ""
    return (
        f"{mark}{row['run_id']} | {terminal} | judge={_clip(judge, width)}{applied} | owed={owed}"
        f" | pm={_clip(row['pm_verbatim'], width)} | criterion={_clip(row['exit_criterion'], width)}"
    )


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description="Per-run verdict audit over state/warp (pure file reads).")
    ap.add_argument("--root", help="repo root (default: this script's repo)")
    ap.add_argument("--red-only", action="store_true", help="print only red rows")
    ap.add_argument("--all", action="store_true", help="read every column for every run (slower)")
    ap.add_argument("--width", type=int, default=100, help="clip width per text column; 0 = no clip")
    args = ap.parse_args(argv)
    root = os.path.abspath(args.root) if args.root else str(Path(__file__).resolve().parents[2])
    if not os.path.isdir(os.path.join(root, "state", "warp")):
        sys.stderr.write(f"run-outcome-audit: no state/warp under {root}\n")
        return 2
    rows = audit(root, args.all)
    red = sum(1 for r in rows if r["red"])
    out = [format_row(r, args.width) for r in rows if r["red"] or not args.red_only]
    out.extend(format_owed_leg(rec) for rec in open_owed_legs(root))
    out.append(f"runs={len(rows)} red={red} (RED = committed/closed without a met judge backed by command output, or applied above diff evidence)")
    sys.stdout.write("\n".join(out) + "\n")
    return 1 if red else 0


if __name__ == "__main__":
    sys.exit(main())
