"""engine-provenance-inventory.py — the per-carrier divergence inventory,
built from C6's counter and a fresh static scan.

Spec backlink: docs/plans/2026-08-26-the-seam-reports-what-it-got.md § C7

WHY THIS EXISTS
    The spike (`docs/research/spike-verdicts/2026-08-26-a-parameterized-
    provenance-query-at-the-front-insert-seam.md`) measured 201 CLIs under
    `coordinator/bin` carrying the dispatch bootstrap, 15 of them confirmed
    divergent by reading: a module-level import of one of four binder
    modules (`repo_identity`, `records_query`, `machine_local_resolve`,
    `coordinator_core.win_portability`) appearing textually before the
    bootstrap call, in a file where the bootstrap runs from inside a
    function. This script turns that reading into a script two ways:

    1. STATIC re-derivation of the same shape, live against the tree this
       script runs against -- never a hardcoded list of 15 filenames. This
       repo's own convention (`red-set-report.py`'s docstring) is that a
       hand-maintained prose figure goes stale; the fix is deriving, not
       transcribing. The spike's own 15/201 figures are cited here as the
       historical measurement they are, not asserted as this run's answer.
    2. RUNTIME aggregation of `state/engine-provenance-counts.jsonl` (C6's
       sink), grouped by wrapper name (the record's `caller` field -- see
       that module's docstring: this is the WRAPPER name
       `ensure_engine_on_path` / `require_engine_on_path` /
       `require_colocated_engine_on_path` / `require_dispatch_engine_on_path`
       / `_seam_present`, not a per-CLI identity) and axis/verdict.

    Absorbed from a deferral (the Staff Engineer's Finding 2, cited in the plan):
    divergence INCIDENCE and DEPENDENCE are orthogonal. This script answers
    neither by itself -- it narrows the population C8 inspects for
    dependence, and says so in its own output.

WHY THE TWO VIEWS ARE NOT JOINED
    C6's counter record carries no CLI-file identity -- only the wrapper
    name, axis, verdict, and the imported/engine root paths (see
    `coordinator_core/engine_provenance_counter.py`'s own docstring, "NOT
    widened past caller/axis/verdict/imported_file/engine_root"). There is
    therefore no key this script can use to say "carrier X's own call fired
    a `divergent` verdict" -- only "wrapper W fired divergent N times,
    somewhere across every CLI that calls it". Reconciling the two views
    into one per-carrier row would silently manufacture a join the data
    does not support. This script reports them side by side instead, and a
    carrier present in the static set with zero corroborating runtime
    divergence for its wrapper is a real finding about invocation
    frequency (it may simply not have run since the counter existed), not
    a bug in either measurement.

WHAT IT EMITS
    A JSON object on stdout (`static`, `runtime`, `note`) plus one
    human-readable summary line on stderr.

NEGATIVE SPEC
    - Does not claim to answer carrier DEPENDENCE on the working tree --
      that is C8.
    - Does not join the static and runtime views by carrier identity; see
      WHY THE TWO VIEWS ARE NOT JOINED above.
    - Does not mutate `state/engine-provenance-counts.jsonl` -- read-only
      consumer, a separate process from C6's append-only writer (per that
      module's own concurrency note).
    - Does not import `coordinator_core.engine_provenance_counter` or any
      other engine module to do its static scan -- the scan is a plain
      `ast` read of `coordinator/bin/*.py` source text, so this script
      itself never needs a resolved engine root to answer the question.
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BIN_DIR = REPO_ROOT / "coordinator" / "bin"
COUNTS_PATH = REPO_ROOT / "state" / "engine-provenance-counts.jsonl"

#: The four `*_on_path` wrappers `_front_insert_on_path` funnels through.
#: `_seam_present` deliberately excluded here -- the spike's static
#: order-hazard shape is specific to these four (its own bootstrap call is
#: what the "runs from inside a function" check below looks for);
#: `_seam_present` is a fifth, separately-reported call site (see the
#: spike's Addendum) that this script's runtime aggregation still counts
#: by wrapper name via C6's counter records. A file whose ONLY
#: bootstrap-shaped call is `_seam_present()` is therefore invisible to
#: `classify_carrier` (no match in `BOOTSTRAP_WRAPPER_NAMES` -> no
#: bootstrap_calls -> returns None, out of `static`'s population) even
#: though C6 still counts its calls at runtime -- see NOTE below, which
#: discloses this so `static.total_carriers` is not read as comparable to
#: the spike's 201 without this caveat.
BOOTSTRAP_WRAPPER_NAMES = (
    "ensure_engine_on_path",
    "require_engine_on_path",
    "require_colocated_engine_on_path",
    "require_dispatch_engine_on_path",
)

BINDER_MODULES = (
    "repo_identity",
    "records_query",
    "machine_local_resolve",
    "coordinator_core.win_portability",
)

SPIKE_MEASURED_TOTAL_CARRIERS = 201
SPIKE_MEASURED_DIVERGENT_CARRIERS = 15


def _imported_module_names(node: ast.Import | ast.ImportFrom) -> list[str]:
    """Dotted module name(s) an `import`/`from...import` statement binds,
    in the form `BINDER_MODULES` entries are spelled -- so `import
    coordinator_core.win_portability`, `from coordinator_core import
    win_portability`, and `import win_portability` are all recognized by
    the same membership check regardless of which import form a carrier
    happens to use.
    """
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    names = []
    module = node.module or ""
    if module:
        names.append(module)
    for alias in node.names:
        if module:
            names.append(f"{module}.{alias.name}")
        names.append(alias.name)
    return names


def _module_level_binder_imports(tree: ast.Module) -> dict[str, int]:
    found: dict[str, int] = {}

    def _walk(stmts: list[ast.stmt]) -> None:
        for stmt in stmts:
            if isinstance(stmt, (ast.Import, ast.ImportFrom)):
                for name in _imported_module_names(stmt):
                    if name in BINDER_MODULES:
                        if name not in found or stmt.lineno < found[name]:
                            found[name] = stmt.lineno
            elif isinstance(stmt, ast.If):
                _walk(stmt.body)
                _walk(stmt.orelse)
            elif isinstance(stmt, ast.Try):
                _walk(stmt.body)
                for handler in stmt.handlers:
                    _walk(handler.body)
                _walk(stmt.orelse)
                _walk(stmt.finalbody)

    _walk(tree.body)
    return found


def _bootstrap_calls(tree: ast.Module) -> list[tuple[int, bool]]:
    """`[(lineno, in_function)]` for every call to one of
    `BOOTSTRAP_WRAPPER_NAMES` anywhere in the file, tracking whether the
    call sits inside a `FunctionDef`/`AsyncFunctionDef` (vs. bare at module
    level) -- the spike's shape requires the bootstrap to run from inside a
    function for the ordering hazard to exist at all (a module-level call
    runs at import time, before any later module-level import could apply).
    """
    calls: list[tuple[int, bool]] = []

    class _Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.depth = 0

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self.depth += 1
            self.generic_visit(node)
            self.depth -= 1

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Call(self, node: ast.Call) -> None:
            func = node.func
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            else:
                name = None
            if name in BOOTSTRAP_WRAPPER_NAMES:
                calls.append((node.lineno, self.depth > 0))
            self.generic_visit(node)

    # Negative spec: a bootstrap call reached only via a *function-level*
    # alias (`from cc_invoke import require_dispatch_engine_on_path as
    # bootstrap; bootstrap()`) is invisible here -- `func.id` resolves to
    # the aliased name, not a `BOOTSTRAP_WRAPPER_NAMES` member, and this
    # scan does not resolve `ast.alias.asname` bindings back to their
    # original name. Accepted limitation, same class as the
    # `importlib.import_module(...)` gap: a candidate scan over the static
    # shapes the spike named, not an exhaustive resolver of every runtime
    # binding.

    _Visitor().visit(tree)
    return calls


def classify_carrier(path: Path) -> dict | None:
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (OSError, SyntaxError, UnicodeDecodeError, ValueError):
        return None

    bootstrap_calls = _bootstrap_calls(tree)
    if not bootstrap_calls:
        return None

    earliest_bootstrap = min((line for line, _ in bootstrap_calls), default=None)
    binder_imports = _module_level_binder_imports(tree)

    order_hazard_binders = sorted(
        module
        for module, import_line in binder_imports.items()
        if earliest_bootstrap is not None and import_line < earliest_bootstrap
    )

    try:
        carrier_name = str(path.relative_to(REPO_ROOT))
    except ValueError:
        carrier_name = str(path)

    return {
        "carrier": carrier_name,
        "carries_bootstrap": True,
        "earliest_bootstrap_line": earliest_bootstrap,
        "order_hazard_candidate": bool(order_hazard_binders),
        "binder_modules": order_hazard_binders,
    }


def static_scan(bin_dir: Path = BIN_DIR, paths: list[Path] | None = None) -> dict:
    """Classify carriers under `bin_dir`, or only `paths` when given.

    A full-tree scan is ~390ms process time, over the 200ms per-process rule;
    a caller that only needs the files a change touches passes `paths` and
    pays O(len(paths)). `total_carriers` then counts the scoped set, not the
    tree -- `scoped` says which denominator the figure is.
    """
    candidates = sorted(bin_dir.glob("*.py")) if paths is None else sorted(paths)
    carriers = []
    for path in candidates:
        result = classify_carrier(path)
        if result is not None:
            carriers.append(result)

    hazard_candidates = [c for c in carriers if c["order_hazard_candidate"]]
    return {
        "scoped": paths is not None,
        "total_carriers": len(carriers),
        "order_hazard_candidates": hazard_candidates,
        "order_hazard_candidate_count": len(hazard_candidates),
        "spike_measured_total_carriers": SPIKE_MEASURED_TOTAL_CARRIERS,
        "spike_measured_divergent_carriers": SPIKE_MEASURED_DIVERGENT_CARRIERS,
    }


def _read_counter_records(counts_path: Path = COUNTS_PATH) -> list[dict]:
    if not counts_path.exists():
        return []
    records = []
    with counts_path.open(encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def _last_written_utc(counts_path: Path) -> str | None:
    """ISO-8601 UTC mtime of the counter file, or None when it does not exist.

    The sink is append-only, so the mtime is the last successful write. A
    healthy carrier runs its bootstrap before `coordinator_core` binds and
    writes nothing, so an empty or old counter is also what a dead sink looks
    like; only "the file was never created" and "the file was last touched
    long ago" are visible here, and the reader must weigh them against how
    recently any carrier is known to have run.
    """
    try:
        mtime = counts_path.stat().st_mtime
    except OSError:
        return None
    return datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat(timespec="seconds")


def runtime_aggregate(counts_path: Path = COUNTS_PATH) -> dict:
    records = _read_counter_records(counts_path)
    tally: Counter[tuple[str, str, str]] = Counter()
    for record in records:
        key = (
            record.get("caller", "unknown"),
            record.get("axis", "unknown"),
            record.get("verdict", "unknown"),
        )
        tally[key] += 1

    by_wrapper_axis_verdict = [
        {"caller": caller, "axis": axis, "verdict": verdict, "count": count}
        for (caller, axis, verdict), count in sorted(tally.items())
    ]
    divergent_total = sum(
        count
        for (_, _, verdict), count in tally.items()
        if verdict == "divergent"
    )
    try:
        counts_display = str(counts_path.relative_to(REPO_ROOT))
    except ValueError:
        counts_display = str(counts_path)

    last_written_utc = _last_written_utc(counts_path)
    return {
        "counts_path": counts_display,
        "counts_file_exists": last_written_utc is not None,
        "last_written_utc": last_written_utc,
        "total_records": len(records),
        "divergent_record_total": divergent_total,
        "by_wrapper_axis_verdict": by_wrapper_axis_verdict,
    }


NOTE = (
    "STATIC ROWS ARE CANDIDATES, NOT VERDICTS. The static view keys on "
    "textual order alone -- a module-level binder import appearing before "
    "the earliest bootstrap call -- which is a necessary but NOT sufficient "
    "condition. Whether that import actually binds coordinator_core in a "
    "given process depends on state no AST can see, so this view "
    "over-reports: measured 2026-08-26, six carriers flagged here raised "
    "nothing when actually invoked. Treat a row as a candidate to inspect, "
    "never as evidence a carrier is broken; the runtime counter is the only "
    "ground truth, and an empty runtime view means nothing has been observed "
    "yet, not that nothing diverges -- and it is byte-identical to the view a "
    "dead sink produces, because a correctly-ordered carrier writes nothing. "
    "`runtime.counts_file_exists` and `runtime.last_written_utc` are the only "
    "liveness evidence this view carries: a counter file that was never "
    "created, or whose last write predates the sink's wiring, is a sink to "
    "suspect, not reassurance. The field is named "
    "`order_hazard_candidate` for exactly this reason -- it names the "
    "static shape detected, not a confirmed runtime fact. "
    "`static.total_carriers` also excludes any file whose ONLY "
    "bootstrap-shaped call is `_seam_present()` -- that wrapper is out of "
    "`BOOTSTRAP_WRAPPER_NAMES` by design (see that constant's own "
    "comment), so such a carrier is invisible to this static population "
    "even though C6's runtime counter still counts its calls; do not "
    "compare `static.total_carriers` against the spike's 201 as if the "
    "two denominators covered the same set of wrappers. "
    "The static and runtime views below are deliberately NOT joined by "
    "carrier identity -- C6's counter record carries only the wrapper "
    "name (caller), axis, and verdict, never a per-CLI identity, so there "
    "is no key to join a specific static-order-hazard-candidate carrier "
    "against a specific runtime record. A carrier present in `static` "
    "with no corroborating `divergent` runtime record for its wrapper is "
    "a finding about invocation frequency (it may not have run since the "
    "counter existed), not a bug in either measurement. This script "
    "answers divergence INCIDENCE only -- whether a carrier's own import "
    "order is a static hazard candidate, and whether the counter has ever "
    "recorded a divergent verdict for the wrapper it calls -- never "
    "DEPENDENCE (whether that carrier's behaviour actually differs "
    "because of it). That question is C8's."
)


def build_report(
    bin_dir: Path = BIN_DIR,
    counts_path: Path = COUNTS_PATH,
    paths: list[Path] | None = None,
) -> dict:
    return {
        "static": static_scan(bin_dir, paths),
        "runtime": runtime_aggregate(counts_path),
        "note": NOTE,
    }


def human_summary_line(report: dict) -> str:
    static = report["static"]
    runtime = report["runtime"]
    return (
        f"[engine-provenance-inventory] static: {static['order_hazard_candidate_count']} "
        f"order-hazard candidate(s) / {static['total_carriers']} carriers "
        f"(spike measured {static['spike_measured_divergent_carriers']} / "
        f"{static['spike_measured_total_carriers']}) -- "
        f"runtime: {runtime['divergent_record_total']} divergent record(s) of "
        f"{runtime['total_records']} total in {runtime['counts_path']} "
        f"({_liveness_phrase(runtime)})"
    )


def _liveness_phrase(runtime: dict) -> str:
    if not runtime["counts_file_exists"]:
        return (
            "WARNING: counter file absent, the sink has never written; "
            "a quiet detector and a dead sink both look empty"
        )
    written = f"counter last written {runtime['last_written_utc']}"
    if runtime["total_records"] == 0:
        return (
            f"WARNING: counter empty, {written}; "
            "a quiet detector and a dead sink both look empty"
        )
    return written


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="engine-provenance-inventory.py",
        description=(
            "Build the per-carrier engine-provenance divergence inventory: a "
            "fresh static scan of coordinator/bin alongside C6's runtime "
            "counter, reported side by side and never reconciled into one "
            "per-carrier row."
        ),
    )
    p.add_argument(
        "--bin-dir",
        type=Path,
        default=BIN_DIR,
        help="directory to statically scan (default: coordinator/bin)",
    )
    p.add_argument(
        "--counts-path",
        type=Path,
        default=COUNTS_PATH,
        help="C6's counter file (default: state/engine-provenance-counts.jsonl)",
    )
    p.add_argument(
        "--paths",
        type=Path,
        nargs="+",
        default=None,
        help=(
            "classify only these files (diff-scoped, O(len(paths))) instead of "
            "the whole --bin-dir; total_carriers then counts this set"
        ),
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_report(args.bin_dir, args.counts_path, args.paths)
    print(json.dumps(report, indent=2))
    print(human_summary_line(report), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
