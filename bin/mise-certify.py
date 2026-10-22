"""mise-certify -- Phase 0 fire-time certification, one command. Writes nothing.

Per plan, ONE `plan.mise_certify_probe` op (a client loop, so a full set is N short ops), in the
order `coordinator-content-repo coordinator/docs/wiki/lesson-triage/mise-prepped-attest.md`
§ "Fire-time revalidation is ONE step, not two" fixes:

  1. sha leg     CERTIFIED / STALE / UNSTAMPED / MALFORMED, from the recomputed
                 `canonical_body_sha` against `mise_prepped_sha`. Spawn-free.
  2. census      NOT-RUN: no census re-runs at certify (the revalidation leg was deleted under the
                 DR-344 kill bar). The row carries the op's NOT-RUN outcome unchanged; it is never
                 PASS, MATCH or the plan verdict.

Exit status:
  0  nothing below fired (UNSTAMPED is reported, not failed)
  1  at least one STALE, MALFORMED or a blocking seam finding
  2  the seam op errored (never a pass)
  3  usage

The seam leg runs once over the FIRE SET only (sha CERTIFIED):
`plan.seam_record` at `phase: fire`, `named_set: true`. Its result rides each row as `seam`; a
row outside the set carries verdict NOT-RUN, and an empty fire set issues no op. Checking
unstamped or stale plans spends the seam op on plans nobody is about to fire.
"""

from __future__ import annotations

import argparse
import functools
import importlib.util
import json
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_REFUSED = 2
EXIT_USAGE = 3

#: Sha-leg states that fail the run. UNSTAMPED is not here: an unstamped plan was never claimed
#: certified, so it is a routing fact for the caller, not a broken certification.
_FAILING_SHA = frozenset({"STALE", "MALFORMED"})


def _bootstrap_engine() -> None:
    """Put the engine on `sys.path` (env-first) before the in-tree fallback transport runs."""
    own_dir = str(Path(__file__).resolve().parent)
    if own_dir not in sys.path:
        sys.path.insert(0, own_dir)
    import lib  # noqa: F401 -- bootstraps coordinator/bin/lib onto sys.path
    import cc_invoke

    cc_invoke.require_engine_on_path(__file__)


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


def _in_fire_set(row: dict) -> bool:
    return row["sha"] == "CERTIFIED"


def _seam_leg(rows: list[dict], root: Path) -> None:
    """Attach `seam` to every row; the op sees the fire set only. Raises `ValueError` when the
    op errors."""
    pr = _prep_run()
    fire = [r for r in rows if _in_fire_set(r)]
    for r in rows:
        if not _in_fire_set(r):
            r["seam"] = {"verdict": "NOT-RUN", "findings": [], "blocking": False,
                         "reason": f"not in fire set (sha {r['sha']})"}
    if not fire:
        return
    rel = {r["plan"]: _repo_relative(r["plan"], root) for r in fire}
    reply = _seam_record(root, list(rel.values()))
    for r in fire:
        key = rel[r["plan"]]
        implicated = pr._seam_implicated(reply, key)
        findings = pr._seam_findings_for(reply, key)
        r["seam"] = {
            "verdict": pr._seam_spell("REFUSED") if implicated else "CLEAN",
            "findings": findings,
            # `per_plan` alone decides: a plan named only as a counterpart is not implicated.
            "blocking": implicated,
        }


def certify(plan: Path, repo_root: Path) -> dict:
    """One `plan.mise_certify_probe` for `plan`; the row carries the op's census outcome as-is."""
    try:
        reply = _prep_run()._invoke(
            repo_root, "plan.mise_certify_probe",
            {"plan": _repo_relative(str(plan), repo_root)})
    except ValueError as exc:
        return {"plan": str(plan), "sha": "MALFORMED", "sha_detail": str(exc), "census": None,
                "seam": None}
    row = {"plan": str(plan), "sha": reply["sha"], "census": reply.get("census"), "seam": None}
    if reply.get("sha_detail"):
        row["sha_detail"] = reply["sha_detail"]
    if reply.get("process_ms") is not None:
        row["processMs"] = reply["process_ms"]
    return row


def plan_state(row: dict) -> str:
    """The plan's one verdict: the sha state until CERTIFIED, then a blocking seam, else
    CERTIFIED. The census outcome never enters it."""
    if row["sha"] != "CERTIFIED":
        return row["sha"]
    if (row.get("seam") or {}).get("blocking"):
        return _prep_run()._seam_spell("REFUSED")
    return "CERTIFIED"


def _print(rows: list[dict]) -> None:
    for row in rows:
        print(Path(row["plan"]).name)
        print(f"  sha     {row['sha']}" + (f" -- {row['sha_detail']}" if row.get("sha_detail") else ""))
        census = row["census"] or {"state": _prep_run()._NOT_RUN, "detail": f"sha leg {row['sha']}"}
        print(f"  census  {census['state']}" + (f" -- {census['detail']}" if census.get("detail") else ""))
        _print_seam(row)


def _print_seam(row: dict) -> None:
    seam = row.get("seam")
    if seam is None:
        return
    if seam["verdict"] == "NOT-RUN":
        print(f"  seam    not run ({seam['reason']})")
        return
    print(f"  seam    {seam['verdict']}")
    pr = _prep_run()
    for f in seam["findings"]:
        print(f"    {pr._seam_line(f)}")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="mise-certify")
    ap.add_argument("plans", nargs="+", help="plan paths, repo-relative or absolute")
    ap.add_argument("--repo-root", default=".", help="the repo the plans live in (default: cwd)")
    ap.add_argument("--json", action="store_true")
    try:
        args = ap.parse_args(argv)
    except SystemExit as exc:
        return EXIT_USAGE if exc.code else EXIT_OK

    _bootstrap_engine()
    root = Path(args.repo_root).resolve()
    rows = [certify(Path(p) if Path(p).is_absolute() else root / p, root) for p in args.plans]
    try:
        _seam_leg(rows, root)
    except ValueError as exc:
        print(f"mise-certify: REFUSED — seam check: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    rows = [{"plan": r["plan"], "state": plan_state(r), **r} for r in rows]
    if args.json:
        json.dump(rows, sys.stdout, indent=1)
        print()
    else:
        _print(rows)

    failed = any(r["sha"] in _FAILING_SHA or (r.get("seam") or {}).get("blocking") for r in rows)
    return EXIT_FAILED if failed else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
