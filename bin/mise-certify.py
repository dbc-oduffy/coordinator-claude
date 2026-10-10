#!/usr/bin/env python3
"""mise-certify -- Phase 0 fire-time certification, both legs, one command. Writes nothing.

Per plan, in the order `coordinator-content-repo coordinator/docs/wiki/lesson-triage/mise-prepped-attest.md`
§ "Fire-time revalidation is ONE step, not two" fixes:

  1. sha leg     `prep_gate.read_stamp` -- CERTIFIED / STALE / UNSTAMPED / MALFORMED, from the
                 recomputed `canonical_body_sha` against `mise_prepped_sha`. Spawn-free.
  2. census leg  `mise-census-revalidate`'s `revalidate`, run ONLY on a CERTIFIED plan: it spawns
                 per entry, and re-measuring the premises of a document that is no longer the
                 certified one spends the box on an answer nobody can use.

Exit status:
  0  nothing below fired (UNSTAMPED, UNDECIDABLE, REFUSED and UNRUNNABLE are reported, not failed)
  1  at least one STALE, MALFORMED, census DRIFT or a blocking seam finding
  2  the seam op errored (never a pass)
  3  usage

When at least one plan is CERTIFIED, a third leg runs once over the plans given:
`plan.seam_record` at `phase: fire`, `named_set: true`. Its result rides each row as `seam`.
"""

from __future__ import annotations

import argparse
import functools
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_REFUSED = 2
EXIT_USAGE = 3

#: Sha-leg states that fail the run. UNSTAMPED is not here: an unstamped plan was never claimed
#: certified, so it is a routing fact for the caller, not a broken certification.
_FAILING_SHA = frozenset({"STALE", "MALFORMED"})


def _prep_gate():
    own_dir = str(Path(__file__).resolve().parent)
    if own_dir not in sys.path:
        sys.path.insert(0, own_dir)
    import lib  # noqa: F401 -- bootstraps coordinator/bin/lib onto sys.path
    import cc_invoke

    cc_invoke.require_engine_on_path(__file__)
    from coordinator_core.roadmap import prep_gate

    return prep_gate


def _revalidator():
    """The census leg, loaded from its sibling file so the two commands share one executor."""
    path = Path(__file__).resolve().parent / "mise-census-revalidate.py"
    spec = importlib.util.spec_from_file_location("mise_census_revalidate", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@functools.cache
def _prep_run():
    """Sibling `mise-prep-run.py`, which owns the seam call and the finding rendering."""
    path = Path(__file__).resolve().parent / "mise-prep-run.py"
    spec = importlib.util.spec_from_file_location("mise_prep_run", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _seam_record(repo_root: Path, plans: list[str]) -> dict:
    """The one seam call: `plan.seam_record` at `fire` over the plans given. Raises `ValueError`
    on an op error."""
    return _prep_run()._seam_call(repo_root, plans, "fire", True, read_only=False)


def _repo_relative(plan: str, root: Path) -> str:
    try:
        return Path(plan).resolve().relative_to(root).as_posix()
    except ValueError:
        return plan


def _seam_leg(rows: list[dict], root: Path) -> None:
    """Attach `seam` to every row. Raises `ValueError` when the op errors."""
    pr = _prep_run()
    rel = {r["plan"]: _repo_relative(r["plan"], root) for r in rows}
    reply = _seam_record(root, list(rel.values()))
    for r in rows:
        key = rel[r["plan"]]
        implicated = pr._seam_implicated(reply, key)
        findings = pr._seam_findings_for(reply, key)
        r["seam"] = {
            "verdict": pr._seam_spell("REFUSED") if implicated else "CLEAN",
            "findings": findings,
            # `per_plan` alone decides: a plan named only as a counterpart is not implicated.
            "blocking": implicated,
        }


#: Lines of `git log` shown per drifted stamp; the rest are counted, not printed.
_ATTRIBUTION_SHOWN = 20
#: Hard cap on what one `git log` returns, so an old stamp cannot stream the whole history.
_ATTRIBUTION_FETCH = 500


def _git_log_since(repo_root: Path, since: str, timeout: int) -> list[str]:
    """`%h %s` lines for commits after `since`, newest first; empty when git cannot answer."""
    try:
        proc = subprocess.run(
            ["git", "log", f"--since={since}", f"--max-count={_ATTRIBUTION_FETCH}",
             "--format=%h %s"],
            cwd=repo_root, capture_output=True, text=True, timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    return proc.stdout.splitlines() if proc.returncode == 0 else []


def _attribution(repo_root: Path, since: str, timeout: int, cache: dict) -> list[str]:
    """Commits since the stamp, one `git log` per distinct stamp anchor across the whole run.

    The anchor is `mise_prepped_at`: `mise_prepped_sha` is a blob hash of the plan body, not a
    commit, so it cannot bound a log.
    """
    if since not in cache:
        lines = _git_log_since(repo_root, since, timeout)
        shown = lines[:_ATTRIBUTION_SHOWN]
        extra = len(lines) - len(shown)
        if extra:
            plus = "+" if len(lines) >= _ATTRIBUTION_FETCH else ""
            shown.append(f"... {extra}{plus} more omitted")
        cache[since] = shown
    return cache[since]


def certify(plan: Path, repo_root: Path, timeout: int, attribute: bool = False,
            cache: dict | None = None) -> dict:
    try:
        text = plan.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return {"plan": str(plan), "sha": "MALFORMED", "sha_detail": str(exc), "census": None,
                "seam": None}
    stamp = _prep_gate().read_stamp(text)
    row = {"plan": str(plan), "sha": stamp["state"], "census": None, "seam": None}
    if stamp["state"] == "STALE":
        row["sha_detail"] = f"recorded {stamp['recorded_sha']}, body {stamp['body_sha']}"
    elif stamp["state"] == "MALFORMED":
        row["sha_detail"] = f"stamp fields missing: {', '.join(stamp.get('missing') or [])}"
    if stamp["state"] == "CERTIFIED":
        row["census"] = _revalidator().revalidate(plan, repo_root, timeout)
        since = str(stamp.get("recorded_at") or "").strip()
        if attribute and since:
            cache = {} if cache is None else cache
            for e in row["census"]["entries"]:
                if e["state"] == "DRIFT":
                    e["attribution"] = list(_attribution(repo_root, since, timeout, cache))
    return row


def plan_state(row: dict) -> str:
    """The plan's one verdict: the sha state until CERTIFIED, then census DRIFT, a blocking
    seam, the census state. Without this the JSON row carried only `sha` and `census.state`."""
    if row["sha"] != "CERTIFIED":
        return row["sha"]
    census_state = (row["census"] or {}).get("state")
    if census_state == "DRIFT":
        return census_state
    if (row.get("seam") or {}).get("blocking"):
        return "SEAM_BLOCKED"
    return census_state or "CERTIFIED"


def _print(rows: list[dict]) -> None:
    for row in rows:
        print(Path(row["plan"]).name)
        print(f"  sha     {row['sha']}" + (f" -- {row['sha_detail']}" if row.get("sha_detail") else ""))
        census = row["census"]
        if census is None:
            print(f"  census  not run (sha leg {row['sha']})")
            _print_seam(row)
            continue
        print(f"  census  {census['state']}" + (f" -- {census['detail']}" if census.get("detail") else ""))
        for e in census["entries"]:
            if e["state"] == "MATCH":
                continue
            print(f"    {e['state']:12s} {e['command'][:110]}")
            if e.get("basis"):
                print(f"      basis    {e['basis']}")
            if e.get("detail"):
                print(f"      detail   {e['detail']}")
            for line in e.get("attribution") or []:
                print(f"      since    {line}")
        _print_seam(row)


def _print_seam(row: dict) -> None:
    seam = row.get("seam")
    if seam is None:
        return
    print(f"  seam    {seam['verdict']}")
    pr = _prep_run()
    for f in seam["findings"]:
        print(f"    {pr._seam_line(f)}")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="mise-certify")
    ap.add_argument("plans", nargs="+", help="plan paths, repo-relative or absolute")
    ap.add_argument("--repo-root", default=".", help="the repo the census commands run in (default: cwd)")
    ap.add_argument("--timeout", type=int, default=30, help="per census command, seconds")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--attribute", action="store_true",
                    help="on census DRIFT, list commits since the stamp (one git log per distinct stamp)")
    try:
        args = ap.parse_args(argv)
    except SystemExit as exc:
        return EXIT_USAGE if exc.code else EXIT_OK

    root = Path(args.repo_root).resolve()
    cache: dict = {}
    rows = [certify(Path(p) if Path(p).is_absolute() else root / p, root, args.timeout,
                    args.attribute, cache)
            for p in args.plans]
    try:
        _seam_leg(rows, root)
    except ValueError as exc:
        print(f"mise-certify: REFUSED — seam check: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    for r in rows:
        r["state"] = plan_state(r)
    if args.json:
        json.dump(rows, sys.stdout, indent=1)
        print()
    else:
        _print(rows)

    failed = any(r["sha"] in _FAILING_SHA or (r["census"] or {}).get("state") == "DRIFT"
                 or (r.get("seam") or {}).get("blocking")
                 for r in rows)
    return EXIT_FAILED if failed else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
