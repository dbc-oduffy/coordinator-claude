"""regenerate-unresolved-writers.py — the named regenerate entrypoint for
state/generator-provenance/unresolved-writers.json.

Spec backlink: state/sizings/2026-08-14-cut-the-unresolved-writer-population-and.yaml
spike_amendments § P2-ratchet.

WHY THIS EXISTS
    `coordinator_core.ops.generator_provenance.discover_generators` reports
    every module whose write target it could not statically resolve as
    `Verdict.WRITE_TARGET_UNRESOLVED`. Left unguarded that population regrows
    silently -- a new module joins it the same way the original 230 did, one
    write at a time, with nothing naming the addition as a reviewable event.
    This script is the ONE sanctioned path to touch the baseline: it wires
    directly to `discover_generators`, never re-derives the sweep itself, so
    the baseline and the live population can never independently drift.

WHAT IT DOES
    --check (default, no flag needed): derives the live
        WRITE_TARGET_UNRESOLVED module-path set via `discover_generators`,
        diffs it against the baseline's module-path KEYS, and reports drift
        (new unresolved writers not in the baseline; stale baseline entries
        no longer unresolved) WITHOUT writing anything. Exits 1 if drift is
        detected, 0 if the baseline matches the live sweep.
    --add-missing: same derivation, but for every newly-appeared module not
        already a baseline key, appends a stub entry (reason="TODO",
        owner="TODO", first_seen=today, review_by=+90d) and writes the file.
        This is the acknowledge-without-adjudicating path -- the ratchet
        test's "every entry has a non-empty reason and owner" gate keeps
        failing on a "TODO" reason/owner, deliberately: this command makes
        the gate acknowledge a new unresolved writer without silently
        rubber-stamping it as adjudicated. A human (or a dispatched executor
        doing the real adjudication) must still fill in reason/owner by hand.
    --write: rewrite the baseline from the live sweep, PRESERVING every
        existing entry's reason/owner/first_seen/review_by for modules still
        present. Never silently overwrites adjudicated text -- only adds
        newly-appeared modules (as TODO stubs, same as --add-missing) and
        drops modules no longer in the live unresolved population. Must be
        passed explicitly; a bare invocation never writes.
    --add-missing and --write are mutually exclusive.

NEGATIVE SPEC
    - Never invents a module-path population independently of
      `discover_generators` -- no re-implementation of the AST sweep here.
    - Never fills in reason/owner with a guess -- new entries always get
      "TODO" literals precisely so the ratchet's coverage gate keeps failing
      until a human acts.
    - Does not touch `generator_provenance.py`'s detection logic -- this
      script only maintains the baseline's bookkeeping layer; adjudication
      (writing a real reason/owner, or adding a `GENERATES` declaration at
      the site) is a separate, reviewed act.
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

_LIB_DIR = str(Path(__file__).resolve().parent / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = REPO_ROOT / "state" / "generator-provenance" / "unresolved-writers.json"
DEFAULT_TARGET_DESC = (
    "coordinator_core/ops/generator_provenance.py discover_generators() sweep, "
    "Verdict.WRITE_TARGET_UNRESOLVED population"
)
REVIEW_WINDOW_DAYS = 90

# Generator-provenance declaration (this repo's own contract) -- THIS file is
# the real writer (BASELINE_PATH.write_text below), never a shim delegating
# elsewhere, so `sources` names its own path.
GENERATES = [
    {
        "artifact": "state/generator-provenance/unresolved-writers.json",
        "stamp_key": "generated",
        "sources": ["coordinator/bin/regenerate-unresolved-writers.py"],
    },
]


def load_baseline(path: Path = BASELINE_PATH) -> dict:
    if not path.exists():
        return {
            "$schema_note": (
                "Regenerable data file, not prose. Regenerate via "
                "coordinator/bin/regenerate-unresolved-writers.py. Unit is the "
                "module-path SET, never a count and never a hash -- a count is "
                "gameable three ways (mark-to-satisfy, fix-one-break-one swap, "
                "host drift), and a hash tells you THAT something changed but "
                "never WHAT, so the only available response is regeneration. A "
                "per-module allowlist costs one line per entry and makes every "
                "addition a reviewable diff line."
            ),
            "target": DEFAULT_TARGET_DESC,
            "generated_by": "coordinator/bin/regenerate-unresolved-writers.py",
            "entries": {},
        }
    return json.loads(path.read_text(encoding="utf-8"))


def derive_unresolved_writers(repo_root: Path = REPO_ROOT) -> set[str]:
    """Shell out to nothing -- imports `discover_generators` directly, the
    ONE derivation this script trusts, never a re-implementation."""
    require_dispatch_engine_on_path()
    from coordinator_core.ops.generator_provenance import discover_generators
    from coordinator_core.ops.staleness_git import Verdict

    records = discover_generators(repo_root)
    return {r.generator for r in records if r.verdict == Verdict.WRITE_TARGET_UNRESOLVED}


def diff_baseline(baseline: dict, unresolved: set[str]) -> dict:
    baseline_keys = set(baseline.get("entries", {}).keys())
    return {
        "new_unresolved": sorted(unresolved - baseline_keys),
        "stale_baseline_entries": sorted(baseline_keys - unresolved),
    }


def _new_stub_entry(today: datetime.date) -> dict:
    review_by = (today + datetime.timedelta(days=REVIEW_WINDOW_DAYS)).isoformat()
    return {
        "reason": "TODO",
        "owner": "TODO",
        "first_seen": today.isoformat(),
        "review_by": review_by,
    }


def add_missing(baseline: dict, unresolved: set[str]) -> int:
    today = datetime.date.today()
    entries = baseline.setdefault("entries", {})
    added = 0
    for module_path in sorted(unresolved - set(entries.keys())):
        entries[module_path] = _new_stub_entry(today)
        added += 1
    return added


def rewrite_preserving_adjudicated(baseline: dict, unresolved: set[str]) -> tuple[int, int]:
    """Default mode: rebuild `entries` from the live set, keeping every
    existing entry's reason/owner/first_seen/review_by verbatim for modules
    still present, adding TODO stubs for new modules, and dropping modules no
    longer in the live unresolved population. Returns (added, dropped)."""
    today = datetime.date.today()
    old_entries = baseline.get("entries", {})
    new_entries: dict[str, dict] = {}
    added = 0
    for module_path in sorted(unresolved):
        if module_path in old_entries:
            new_entries[module_path] = old_entries[module_path]
        else:
            new_entries[module_path] = _new_stub_entry(today)
            added += 1
    dropped = len(set(old_entries.keys()) - unresolved)
    baseline["entries"] = new_entries
    return added, dropped


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="regenerate-unresolved-writers.py",
        description=(
            "The named regenerate entrypoint for "
            "state/generator-provenance/unresolved-writers.json."
        ),
    )
    group = p.add_mutually_exclusive_group()
    group.add_argument(
        "--add-missing",
        action="store_true",
        help="append TODO stub entries for newly-appeared unresolved writers and write the file",
    )
    group.add_argument(
        "--write",
        action="store_true",
        help=(
            "rewrite the baseline from the live sweep, preserving adjudicated "
            "entries and dropping stale ones. Bare invocation (no flag) never "
            "writes -- it is --check."
        ),
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    baseline = load_baseline()
    unresolved = derive_unresolved_writers()
    diff = diff_baseline(baseline, unresolved)

    changed = False
    if args.add_missing:
        added = add_missing(baseline, unresolved)
        if added:
            print(
                "[regenerate-unresolved-writers] added %d stub entries (owner=TODO, "
                "reason=TODO -- fill in before the coverage gate can pass)" % added,
                file=sys.stderr,
            )
            changed = True
    elif args.write:
        added, dropped = rewrite_preserving_adjudicated(baseline, unresolved)
        if added or dropped:
            print(
                "[regenerate-unresolved-writers] added %d stub entries, dropped %d "
                "stale entries (existing reason/owner/first_seen/review_by preserved)"
                % (added, dropped),
                file=sys.stderr,
            )
            changed = True

    if changed:
        baseline["generator"] = "coordinator/bin/regenerate-unresolved-writers.py"
        baseline["generated"] = datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        # DR-276: this CLI reads via `generator_provenance.discover_generators`
        # (a library function, not an op `main(argv)` -- no op entrypoint to
        # route through `run_op_main`) and writes the baseline itself. Wrapped
        # in `recording_declared_writes()` with an explicit `declare_write()`
        # at the write site, per cli_entry's documented carve-out for a CLI
        # that owns its own body (see gen-launcher-shim.py's `main()`).
        require_dispatch_engine_on_path()
        from coordinator_core.cli_entry import recording_declared_writes
        from coordinator_core.session.declared_writes import declare_write

        with recording_declared_writes():
            BASELINE_PATH.write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8", newline="\n")
            declare_write(BASELINE_PATH)

    print(json.dumps(diff, indent=2))
    if diff["new_unresolved"] or diff["stale_baseline_entries"]:
        print(
            "[regenerate-unresolved-writers] drift detected -- new_unresolved=%d "
            "stale_baseline_entries=%d"
            % (len(diff["new_unresolved"]), len(diff["stale_baseline_entries"])),
            file=sys.stderr,
        )
        return 1 if not changed else 0
    print(
        "[regenerate-unresolved-writers] baseline matches observed unresolved-writer set",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
