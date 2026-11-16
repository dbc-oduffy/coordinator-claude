#!/usr/bin/env python3
"""fast-tier-budget.py -- record and rank the fast tier's wall clock against its 15-minute budget.

`record <junit.xml>` turns a fast-tier junit run into state/test-tiers/fast-tier-ledger.json;
`rank` lists the costliest test files and the saving needed to reach the target. The ratchet
(coordinator_core/tests/test_fast_tier_budget_ratchet.py) reads only the ledger, so enforcement
costs milliseconds and runs no clock.

Projection: measured_wall_s * cap / FLOOR_CAP, where cap is the worker count of the measuring run
and FLOOR_CAP the cap the fleet floor box (12c/24GB) derives. The projection uses the recorded cap,
never the host at read time.

`record --profile <json>` stores the fast_tier_profile plugin's overhead decomposition under
`profile.base|after` and adds `split`; check_ledger reads `split` only when a profile is present.

`moves` is derived on every record: each test file carrying pytest.mark.complete, with seconds
carried from the prior ledger's per_file (the base measurement) and kept across re-records.
"""

from __future__ import annotations

import argparse
import ast
import datetime as _dt
import json
import os
import sys
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

FLOOR_CAP = 6
BUDGET_S = 900
TARGET_S = 720
NEW_MARKER = "complete"
LEDGER_REL = "state/test-tiers/fast-tier-ledger.json"
_REPO = Path(__file__).resolve().parents[2]

import lib  # noqa: E402,F401 -- bootstraps coordinator/bin/lib onto sys.path
from cc_invoke import ensure_engine_on_path  # noqa: E402

ensure_engine_on_path(__file__)


def _is_complete_mark(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == NEW_MARKER
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "mark"
    )


def _carries_complete(tree: ast.AST) -> bool:
    """True when pytest.mark.complete decorates a def/class or is assigned to a `pytestmark`."""
    for node in ast.walk(tree):
        roots: list[ast.AST] = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            roots = list(node.decorator_list)
        elif isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets
        ):
            roots = [node.value]
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "pytestmark"
            and node.value is not None
        ):
            roots = [node.value]
        for root in roots:
            if any(_is_complete_mark(n) for n in ast.walk(root)):
                return True
    return False


def _testpaths(repo: Path) -> list[str]:
    cfg = tomllib.loads((repo / "pyproject.toml").read_text(encoding="utf-8"))
    return list(cfg.get("tool", {}).get("pytest", {}).get("ini_options", {}).get("testpaths", []))


def scan_complete_files(repo: Path) -> list[str]:
    """Repo-relative posix paths of test_*.py files under testpaths carrying pytest.mark.complete."""
    found: set[str] = set()
    for tp in _testpaths(repo):
        base = repo / tp
        if base.is_file():
            candidates = [base]
        else:
            candidates = []
            for dirpath, dirnames, filenames in os.walk(base):
                dirnames[:] = [d for d in dirnames if d not in ("__pycache__", ".git", "node_modules")]
                candidates.extend(Path(dirpath) / f for f in filenames if f.startswith("test_") and f.endswith(".py"))
        for path in candidates:
            try:
                raw = path.read_bytes()
            except OSError:
                continue
            if b"mark.complete" not in raw:
                continue
            try:
                tree = ast.parse(raw)
            except (SyntaxError, ValueError):
                continue
            if _carries_complete(tree):
                found.add(path.relative_to(repo).as_posix())
    return sorted(found)


def _file_for_classname(classname: str, repo: Path, cache: dict[str, str]) -> str:
    """Resolve a junit classname (dotted module path + optional class) to a repo-relative file."""
    if classname in cache:
        return cache[classname]
    parts = classname.split(".")
    resolved = classname
    for n in range(len(parts), 0, -1):
        rel = "/".join(parts[:n]) + ".py"
        if (repo / rel).is_file():
            resolved = rel
            break
    cache[classname] = resolved
    return resolved


def parse_junit(junit: Path, repo: Path) -> tuple[float, float, list[dict]]:
    """Return (measured_wall_s, sum_test_s, per_file) from a junit XML file."""
    root = ET.parse(junit).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    wall = sum(float(s.get("time", 0) or 0) for s in suites)
    per: dict[str, list] = {}
    cache: dict[str, str] = {}
    total = 0.0
    for case in root.iter("testcase"):
        secs = float(case.get("time", 0) or 0)
        total += secs
        f = case.get("file") or _file_for_classname(case.get("classname", ""), repo, cache)
        entry = per.setdefault(f, [0.0, 0])
        entry[0] += secs
        entry[1] += 1
    per_file = [
        {"file": f, "seconds": round(v[0], 3), "tests": v[1]}
        for f, v in sorted(per.items(), key=lambda kv: (-kv[1][0], kv[0]))
    ]
    return round(wall, 3), round(total, 3), per_file


def derive_moves(complete_files: list[str], prior: Optional[dict]) -> list[dict]:
    """One move per complete-marked file; seconds from the prior ledger's per_file, else the prior move."""
    seconds: dict[str, float] = {}
    if prior:
        for m in prior.get("moves", []):
            seconds[m["id"]] = m["seconds"]
        for p in prior.get("per_file", []):
            seconds[p["file"]] = p["seconds"]
    moves = [{"id": f, "seconds": seconds.get(f, 0.0), "new_marker": NEW_MARKER} for f in complete_files]
    return sorted(moves, key=lambda m: (-m["seconds"], m["id"]))


def _read_head_sha(repo: Path) -> Optional[str]:
    try:
        git = repo / ".git"
        if git.is_file():
            git = (repo / git.read_text().split(":", 1)[1].strip()).resolve()
        head = (git / "HEAD").read_text().strip()
        if not head.startswith("ref:"):
            return head
        ref = head.split(" ", 1)[1]
        ref_file = git / ref
        if ref_file.is_file():
            return ref_file.read_text().strip()
        common = git / "commondir"
        if common.is_file():
            ref_file = (git / common.read_text().strip() / ref).resolve()
            if ref_file.is_file():
                return ref_file.read_text().strip()
        for line in (git / "packed-refs").read_text().splitlines():
            if line.endswith(" " + ref):
                return line.split(" ", 1)[0]
    except (OSError, IndexError):
        pass
    return None


def _box(cap: Optional[int]) -> dict:
    sys.path.insert(0, str(_REPO))
    from coordinator_core.benchmarks.concurrency_probe import (
        compute_measured_cap,
        default_physical_cores,
        default_usable_ram_gb,
        read_measured_headroom,
    )

    cores, ram = default_physical_cores(), default_usable_ram_gb()
    return {
        "physical_cores": cores,
        "ram_gb": round(ram, 1),
        "cap": cap if cap is not None else compute_measured_cap(*read_measured_headroom()),
    }


def split_projection(ledger: dict) -> Optional[dict]:
    """Floor projection with the per-worker constant overhead held fixed, from the ledger's latest profile.

    (wall - constant) * cap / FLOOR_CAP + constant, where constant is the profile's
    session_setup_s + worker_tail_s: every worker pays it once, so it does not shrink with cap.
    None when the ledger carries no profile.
    """
    profile = ledger.get("profile") or {}
    latest = profile.get("after") or profile.get("base")
    if not latest:
        return None
    constant = latest["session_setup_s"] + latest["worker_tail_s"]
    wall, cap = ledger["measured_wall_s"], ledger["box"]["cap"]
    return {
        "constant_overhead_s": round(constant, 3),
        "projected_floor_wall_s": round((wall - constant) * cap / FLOOR_CAP + constant, 1),
    }


def build_ledger(
    junit: Path,
    repo: Path,
    box: dict,
    prior: Optional[dict],
    base_sha: Optional[str],
    measured_at: str,
    profile: Optional[dict] = None,
    profile_phase: Optional[str] = None,
) -> dict:
    wall, total, per_file = parse_junit(junit, repo)
    ledger = {
        "measured_at": measured_at,
        "base_sha": base_sha,
        "box": box,
        "measured_wall_s": wall,
        "sum_test_s": total,
        "projected_floor_wall_s": round(wall * box["cap"] / FLOOR_CAP, 1),
        "budget_s": BUDGET_S,
        "per_file": per_file,
        "moves": derive_moves(scan_complete_files(repo), prior),
    }
    profiles = dict((prior or {}).get("profile") or {})
    if profile is not None:
        profiles[profile_phase or ("after" if "base" in profiles else "base")] = profile
    if profiles:
        ledger["profile"] = profiles
        ledger["split"] = split_projection(ledger)
    return ledger


def reproject(ledger: dict, complete_files: list[str]) -> dict:
    """Ledger modeled as if the complete-marked files had left the fast tier of the base measurement.

    Each moved file's seconds leave per_file and sum_test_s; measured_wall_s drops by those seconds
    spread over the recorded cap. The model keeps the base run's collection/tail overhead, so a
    fresh `record` run replaces it with a measurement.
    """
    cap = ledger["box"]["cap"]
    moves = derive_moves(complete_files, ledger)
    moved = {m["id"] for m in moves}
    moved_s = sum(m["seconds"] for m in moves if m["id"] in {p["file"] for p in ledger["per_file"]})
    out = dict(ledger)
    out["per_file"] = [p for p in ledger["per_file"] if p["file"] not in moved]
    out["sum_test_s"] = round(ledger["sum_test_s"] - moved_s, 3)
    out["measured_wall_s"] = round(ledger["measured_wall_s"] - moved_s / cap, 3)
    out["projected_floor_wall_s"] = round(out["measured_wall_s"] * cap / FLOOR_CAP, 1)
    if out.get("profile"):
        out["split"] = split_projection(out)
    out["moves"] = moves
    out["projection_basis"] = "modeled: base measurement minus moved files' seconds over the recorded cap"
    return out


def check_ledger(ledger: dict, complete_files: list[str]) -> list[str]:
    """Ratchet violations: projection over BUDGET_S, or moves and complete-marked files disagreeing."""
    problems = []
    if ledger.get("budget_s") != BUDGET_S:
        problems.append(f"ledger budget_s {ledger.get('budget_s')!r} is not the {BUDGET_S}s budget")
    projected = (ledger.get("split") or {}).get("projected_floor_wall_s", ledger["projected_floor_wall_s"])
    if projected > BUDGET_S:
        problems.append(f"projected_floor_wall_s {projected} exceeds the {BUDGET_S}s fast-tier budget")
    listed = {m["id"] for m in ledger.get("moves", [])}
    for f in complete_files:
        if f not in listed:
            problems.append(f"{f} carries pytest.mark.complete but is absent from the ledger's moves")
    # tier_collect_skip drops every listed move from the fast tier, so an unmarked listed file
    # would run in no tier at all.
    marked = set(complete_files)
    for f in sorted(listed - marked):
        problems.append(f"{f} is in the ledger's moves but does not carry pytest.mark.complete")
    return problems


def rank(ledger: dict, top: Optional[int] = None) -> str:
    """Files by seconds, printed until the cumulative projected saving reaches the TARGET_S gap.

    Moving a file saves its test seconds spread over FLOOR_CAP workers on the floor box. `top`
    caps the rows printed; the last line is the row that reaches the gap (or a not-reached marker).
    The saving model ignores collection and tail overhead that no move removes, so a further
    move round may be needed after the after-run.
    """
    need = ledger["projected_floor_wall_s"] - TARGET_S
    header = (
        f"projected {ledger['projected_floor_wall_s']}s vs budget {ledger['budget_s']}s, target {TARGET_S}s; "
        f"saving needed {max(need, 0):.0f}s"
    )
    cap = ledger.get("box", {}).get("cap")
    if cap and "sum_test_s" in ledger and "measured_wall_s" in ledger:
        overhead = ledger["measured_wall_s"] - ledger["sum_test_s"] / cap
        header += (
            f"; model is optimistic: ~{overhead:.0f}s of collection/tail overhead is not removed by moves, "
            "so the after-run may need a further move round"
        )
    lines = [header]
    cum = 0.0
    reached = need <= 0
    rows = ledger["per_file"] if top is None else ledger["per_file"][:top]
    for row in rows:
        if reached:
            break
        cum += row["seconds"] / FLOOR_CAP
        reached = cum >= need
        mark = f"  <- {TARGET_S}s reached" if reached else ""
        lines.append(f"{row['seconds']:10.1f}s  cum_saving {cum:8.1f}s  {row['tests']:6d}  {row['file']}{mark}")
    if not reached:
        lines.append(f"-- {TARGET_S}s not reached: cum_saving {cum:.1f}s of {need:.1f}s over {len(lines) - 1} rows")
    return "\n".join(lines)


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(prog="fast-tier-budget")
    sub = ap.add_subparsers(dest="cmd", required=True)
    rec = sub.add_parser("record", help="write the ledger from a junit XML")
    rec.add_argument("junit", type=Path)
    rec.add_argument("--cap", type=int, default=None, help="worker cap of the measured run")
    rec.add_argument("--base-sha", default=None)
    rec.add_argument("--repo", type=Path, default=_REPO)
    rec.add_argument("--profile", type=Path, default=None, help="merged JSON from the fast_tier_profile plugin")
    rec.add_argument(
        "--profile-phase", choices=("base", "after"), default=None, help="default: base, else after once a base exists"
    )
    rp = sub.add_parser("reproject", help="model the ledger with complete-marked files removed from the fast tier")
    rp.add_argument("--repo", type=Path, default=_REPO)
    rk = sub.add_parser("rank", help="top files by seconds and cumulative projected saving")
    rk.add_argument("--top", type=int, default=None, help="cap on rows printed (default: until the target gap is reached)")
    rk.add_argument("--repo", type=Path, default=_REPO)
    args = ap.parse_args(argv)

    ledger_path = args.repo / LEDGER_REL
    prior = json.loads(ledger_path.read_text(encoding="utf-8")) if ledger_path.is_file() else None
    if args.cmd == "rank":
        if prior is None:
            print(f"fast-tier-budget: no ledger at {LEDGER_REL}; run `record` first", file=sys.stderr)
            return 2
        print(rank(prior, args.top))
        return 0

    if args.cmd == "reproject":
        if prior is None:
            print(f"fast-tier-budget: no ledger at {LEDGER_REL}; run `record` first", file=sys.stderr)
            return 2
        ledger = reproject(prior, scan_complete_files(args.repo))
        ledger_path.write_text(json.dumps(ledger, indent=1) + "\n", encoding="utf-8")
        print(f"projected {ledger['projected_floor_wall_s']}s at {FLOOR_CAP} workers (budget {BUDGET_S}s), modeled")
        return 0

    box = _box(args.cap)
    ledger = build_ledger(
        args.junit,
        args.repo,
        box,
        prior,
        args.base_sha or _read_head_sha(args.repo),
        _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        json.loads(args.profile.read_text(encoding="utf-8")) if args.profile else None,
        args.profile_phase,
    )
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps(ledger, indent=1) + "\n", encoding="utf-8")
    print(
        f"measured {ledger['measured_wall_s']}s on {box['cap']} workers; "
        f"projected {ledger['projected_floor_wall_s']}s at {FLOOR_CAP} workers (budget {BUDGET_S}s)"
    )
    if ledger.get("split"):
        print(
            f"split projection {ledger['split']['projected_floor_wall_s']}s "
            f"(constant overhead {ledger['split']['constant_overhead_s']}s)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
