"""coordinator/bin/percolate-sweep-scope-probe.py — read-only sweep-scope counter.

Measures how much content-transform sweep volume a klabauter publish actually
pays for, settling the "~7x full-mirror passes per publish" premise in
state/handoffs/2026-08-07-percolate-performance-delta-sweep.md with a real
count instead of a reading of the row list.

Reuses `coordinator/bin/publish.py`'s own row-resolution and target-parsing
code (`load_targets`, `parse_target_row`, `_import_claude_klabauter_percolate`,
`locate_percolate_store`, `assert_percolate_store_ready`, `_dest_repo_root`)
via `importlib` — this probe does not re-implement row parsing or
`target_root` resolution, so it cannot drift from the real publish path (§
handoff "What to build" item 1).

Negative-spec: mutates nothing. No writes to the destination mirror, no
publish, no engine phase dispatch (`run_percolate`/`run_inject_for_section`
are imported but never called) — only `iter_surface_files` (a pure `os.walk`
read) runs per row. Exits non-zero with a clear message, fabricating no
counts, if the destination mirror is absent.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from collections import Counter
from pathlib import Path
from typing import List, Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PUBLISH_PY = _REPO_ROOT / "coordinator" / "bin" / "publish.py"


def _import_publish_module():
    """Import `coordinator/bin/publish.py` in-process, same idiom that module
    itself uses to import `cc_invoke.py` (`_import_claude_klabauter_percolate`) — a
    file-path import via `importlib.util`, since `coordinator/bin` is not a
    package."""
    spec = importlib.util.spec_from_file_location("_percolate_sweep_scope_probe_publish", _PUBLISH_PY)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not build a module spec for {_PUBLISH_PY}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target",
        default=None,
        help="Comma-separated target name filter (default: all claude-klabauter* rows).",
    )
    args = parser.parse_args(argv)

    publish = _import_publish_module()

    percolate_root, _rung = publish._resolve_percolate_root_and_rung()
    setup_dir = percolate_root / "setup"

    try:
        rows = publish.load_targets(setup_dir, target_filter=args.target)
    except publish.TargetsError as exc:
        print(f"percolate-sweep-scope-probe: FATAL loading targets: {exc.message}", file=sys.stderr)
        return 1

    targets = [publish.parse_target_row(row) for row in rows]
    if args.target:
        requested = {n.strip() for n in args.target.split(",") if n.strip()}
        targets = [t for t in targets if t.name in requested]
    else:
        targets = [t for t in targets if t.name.startswith("claude-klabauter")]

    if not targets:
        print("percolate-sweep-scope-probe: no matching targets resolved.", file=sys.stderr)
        return 1

    try:
        claude_klabauter_pct = publish._import_claude_klabauter_percolate()
    except publish.EngineUnavailableError as exc:
        print(f"percolate-sweep-scope-probe: FATAL — percolate engine unavailable: {exc}", file=sys.stderr)
        return 1

    percolate_store_path = publish.locate_percolate_store(setup_dir)
    try:
        store = publish.assert_percolate_store_ready(claude_klabauter_pct, percolate_store_path)
    except Exception as exc:  # noqa: BLE001 - fail-closed, mirrors publish.py's own main()
        print(f"percolate-sweep-scope-probe: FATAL — percolate store not ready: {exc}", file=sys.stderr)
        return 1

    missing_dest = [t for t in targets if not t.dest_dir.exists()]
    if missing_dest:
        print(
            "percolate-sweep-scope-probe: FATAL — destination mirror absent, refusing to "
            "fabricate counts. Missing dest_dir(s):",
            file=sys.stderr,
        )
        for t in missing_dest:
            print(f"  {t.name}: {t.dest_dir}", file=sys.stderr)
        return 1

    per_row_files: "dict[str, set[Path]]" = {}
    per_row_counts: "dict[str, int]" = {}
    for target in targets:
        section = claude_klabauter_pct.resolve_target(store, target.name)
        file_surface_params = section.get("file_surface") or {}
        visited = set(claude_klabauter_pct.iter_surface_files(target.dest_dir, **file_surface_params))
        per_row_files[target.name] = visited
        per_row_counts[target.name] = len(visited)

    union: "set[Path]" = set()
    for files in per_row_files.values():
        union |= files
    union_count = len(union)

    total_visited = sum(per_row_counts.values())
    multiplier = (total_visited / union_count) if union_count else 0.0

    overlap = Counter()
    for files in per_row_files.values():
        for f in files:
            overlap[f] += 1
    top_overcounted = [(path, n) for path, n in overlap.items() if n > 1]
    top_overcounted.sort(key=lambda pair: pair[1], reverse=True)

    print("percolate-sweep-scope-probe — per-row in-surface file counts")
    print(f"  {'target':<40} {'target_root':<60} {'in_surface_count':>16}")
    for target in targets:
        print(f"  {target.name:<40} {str(target.dest_dir):<60} {per_row_counts[target.name]:>16}")
    print("")
    print(f"Union across all rows: {union_count}")
    print(f"Total visited-file count (sum over rows): {total_visited}")
    print(f"Multiplier (total / union): {multiplier:.3f}")
    print("")
    print(f"Top over-counted files (visited by >1 row), {len(top_overcounted)} total:")
    for path, n in top_overcounted[:20]:
        print(f"  {n:>2} rows: {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
