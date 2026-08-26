"""regenerate-known-red-registry.py — the named regenerate entrypoint for
state/bash-guards/known-red.json.

Spec backlink: pln-make-the-bash-guards-suite-a-g-2f81d6 § C8 (AC8e)

WHY THIS EXISTS
    Peers commit into `coordinator_core/bash_guards/tests/` continuously.
    A set-based registry with no sanctioned way to update it WILL be
    updated by hand, silently, the same way `docs/reference/test-tiers.md`'s
    prose numbers went stale twice. This script is the ONE sanctioned path:
    it wires directly to `coordinator/bin/red-set-report.py` (C1) rather
    than re-deriving the red set itself, so the registry and the census can
    never independently drift.

WHAT IT DOES
    --check (default): derives the live unmarked-red nodeid set via
        red-set-report.py, diffs it against the registry's node-id KEYS,
        and reports drift (new unmarked reds not in the registry; stale
        registry entries no longer red) WITHOUT writing anything.
    --add-missing: same derivation, but for every unmarked-red nodeid not
        already a registry key, appends a STUB entry (marker="pending_fix",
        owner="TODO", reason="TODO", first_seen=today, review_by=+30d) and
        writes the file. A stub entry still satisfies AC8(b)'s subset check
        by nodeid, but AC8(c)'s owner/reason-non-empty check FAILS on a
        "TODO" owner/reason -- deliberately: this command makes the gate
        acknowledge a new red cell without silently rubber-stamping it as
        adjudicated. A human (or a dispatched executor doing the real
        adjudication) must still fill in owner/reason by hand.
    --prune-green: removes registry entries whose nodeid is no longer in
        the live unmarked-red-OR-marked-failed set at all (i.e. the cell
        went green and its marker, if any, should be removed from the test
        too -- this only prunes the registry's bookkeeping, it does not
        touch test source).

NEGATIVE SPEC
    - Never invents a red-set number independently of red-set-report.py.
    - Never fills in owner/reason with a guess -- --add-missing writes
      "TODO" literals precisely so AC8(c) keeps failing until a human acts.
    - Does not touch coordinator_core/bash_guards/tests/*.py marker
      decorators -- this script only maintains the registry's bookkeeping
      layer, adjudication and marking are a separate, reviewed act.
"""
from __future__ import annotations

import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RED_SET_REPORT = Path(__file__).resolve().parent / "red-set-report.py"
REGISTRY_PATH = REPO_ROOT / "state" / "bash-guards" / "known-red.json"
DEFAULT_TARGET = "coordinator_core/bash_guards/tests/"
REVIEW_WINDOW_DAYS = 30

# Generator-provenance declaration (C2, generator_provenance.py's AST reader).
# THIS file is the real writer (REGISTRY_PATH.write_text below), not a shim
# delegating elsewhere, so `sources` names its own path -- unlike the bin/
# CLI trampolines this row's plan chunk also declares.
# `stamp_key` names the artifact-side `generator`/`generated` top-level keys
# added by this same chunk (see the write step in `main()` below): the
# registry's pre-existing `generated_by` is a command string with no
# timestamp and does not count as a usable stamp (plan C2 body).
GENERATES = [
    {
        "artifact": "state/bash-guards/known-red.json",
        "stamp_key": "generated",
        "sources": ["coordinator/bin/regenerate-known-red-registry.py"],
    },
]


def load_registry(path: Path = REGISTRY_PATH) -> dict:
    if not path.exists():
        return {
            "$schema_note": "Regenerable data file, not prose. Regenerate via "
            "coordinator/bin/regenerate-known-red-registry.py. Two provenance keys "
            "coexist deliberately: `generated_by` names the command that DERIVED the "
            "entries, `generator` names the module that EMITTED this file and pairs "
            "with `generated` as its staleness stamp.",
            "target": DEFAULT_TARGET,
            "generated_by": "coordinator/bin/red-set-report.py %s" % DEFAULT_TARGET,
            "entries": {},
        }
    return json.loads(path.read_text(encoding="utf-8"))


def _derive_report(target: str = DEFAULT_TARGET, workers: int | None = None) -> dict:
    """Shell out to red-set-report.py itself -- the ONE derivation this
    script trusts, never a re-implementation."""
    cmd = [sys.executable, str(RED_SET_REPORT), target]
    if workers is not None:
        cmd += ["--workers", str(workers)]
    proc = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return json.loads(proc.stdout)


def derive_unmarked_red(target: str = DEFAULT_TARGET, workers: int | None = None) -> set[str]:
    return set(_derive_report(target, workers)["unmarked_failed"])


def diff_registry(registry: dict, unmarked_red: set[str]) -> dict:
    registry_keys = set(registry.get("entries", {}).keys())
    return {
        "new_unmarked_red": sorted(unmarked_red - registry_keys),
        "stale_registry_entries": sorted(registry_keys - unmarked_red),
    }


def add_missing(registry: dict, unmarked_red: set[str]) -> int:
    today = datetime.date.today()
    review_by = (today + datetime.timedelta(days=REVIEW_WINDOW_DAYS)).isoformat()
    entries = registry.setdefault("entries", {})
    added = 0
    for nodeid in sorted(unmarked_red - set(entries.keys())):
        entries[nodeid] = {
            "marker": "pending_fix",
            "owner": "TODO",
            "reason": "TODO",
            "plan_id": "TODO",
            "group": "TODO",
            "first_seen": today.isoformat(),
            "review_by": review_by,
        }
        added += 1
    return added


def prune_green(registry: dict, still_red_or_marked_failed: set[str]) -> int:
    """`still_red_or_marked_failed` must be `unmarked_failed | marked_failed`
    -- a cell that is still red under its own marker (in `marked_failed`,
    not `unmarked_failed`) is NOT stale and must not be pruned. Passing
    `unmarked_failed` alone here would delete bookkeeping for a cell that is
    still legitimately marked+red, which is the opposite of the "conservative
    under-prune, not an over-prune" contract this function's docstring and
    caller both promise."""
    entries = registry.get("entries", {})
    stale = [k for k in entries if k not in still_red_or_marked_failed]
    for k in stale:
        del entries[k]
    return len(stale)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="regenerate-known-red-registry.py",
        description="The named regenerate entrypoint for state/bash-guards/known-red.json.",
    )
    p.add_argument("--target", default=DEFAULT_TARGET)
    p.add_argument("--workers", type=int, default=None)
    p.add_argument(
        "--add-missing",
        action="store_true",
        help="append TODO-owner stub entries for new unmarked-red nodeids and write the file",
    )
    p.add_argument(
        "--prune-green",
        action="store_true",
        help="remove registry entries whose nodeid is no longer red (unmarked or marked) at all",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    registry = load_registry()
    report = _derive_report(args.target, args.workers)
    unmarked_red = set(report["unmarked_failed"])
    diff = diff_registry(registry, unmarked_red)

    changed = False
    if args.add_missing:
        added = add_missing(registry, unmarked_red)
        if added:
            print("[regenerate-known-red-registry] added %d stub entries (owner=TODO, "
                  "reason=TODO -- fill in before AC8(c) can pass)" % added, file=sys.stderr)
            changed = True
    if args.prune_green:
        # A cell not currently unmarked-red may still be legitimately marked
        # and red under the marker (e.g. a still-broken pending_fix subject) --
        # pruning here only removes registry bookkeeping for cells no longer
        # in EITHER the unmarked-red or the marked-failed set, which is a
        # conservative under-prune, not an over-prune (fixed per review: this
        # previously unioned unmarked_red alone, deleting bookkeeping for
        # cells still legitimately marked+red).
        still_red_or_marked_failed = unmarked_red | set(report["marked_failed"])
        removed = prune_green(registry, still_red_or_marked_failed)
        if removed:
            print("[regenerate-known-red-registry] pruned %d entries no longer "
                  "in the observed unmarked-red set" % removed, file=sys.stderr)
            changed = True

    if changed:
        # Artifact-side stamp (C2, § Mechanism correction) -- top-level keys,
        # the shape natural to this artifact's JSON format, reusing
        # `docs/exec-summary.md`'s `generator`/`generated` key names verbatim
        # rather than minting new ones. Set at the write chokepoint only, so
        # a --check-only run (no `changed`) never claims a stamp for content
        # it did not write.
        registry["generator"] = "coordinator/bin/regenerate-known-red-registry.py"
        registry["generated"] = datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        REGISTRY_PATH.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8", newline="\n")

    print(json.dumps(diff, indent=2))
    if diff["new_unmarked_red"] or diff["stale_registry_entries"]:
        print(
            "[regenerate-known-red-registry] drift detected -- new_unmarked_red=%d "
            "stale_registry_entries=%d" % (len(diff["new_unmarked_red"]), len(diff["stale_registry_entries"])),
            file=sys.stderr,
        )
        return 1 if not changed else 0
    print("[regenerate-known-red-registry] registry matches observed unmarked-red set", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
