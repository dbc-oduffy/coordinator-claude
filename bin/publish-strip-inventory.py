"""coordinator/bin/publish-strip-inventory.py — print the per-publish-row
content-strip inventory.

The human-readable face of `coordinator/lib/percolate/content_strip_inventory.py`.
Answers, in one screen, the question nothing in this repo could answer before
state/bug-backlog/2026-09-01-nothing-enumerates-which-publish-rows-ca-5194901fbf52.yaml
was filed: which publish rows strip a marker-pair block from their published bytes,
and which publish every byte verbatim.

    publish-strip-inventory.py             table to stdout, exit 0
    publish-strip-inventory.py --json      machine-readable, same data
    publish-strip-inventory.py --check     exit 1 if any row is half-configured
                                           or absent from the store

`--check` is the CLI's fail-loud mode, and it is deliberately NARROWER than
`coordinator/tests/test_publish_row_content_strip_declared.py`: it checks the store
against itself (a strip that cannot fire, a row the store never heard of) and does
not read the declarations file. The declaration-vs-reality gate is the test's job,
because that comparison is a repo invariant, not something a person runs.

Negative-spec: prints declared state, resolves no machine-local path, spawns no
process, reads no destination tree, and never writes. A row shown as `strips` here
has a marker pair declared and its hook active — that is a claim about config, not
a measurement of published output; the measurement is an assertion over bytes and
lives elsewhere.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from coordinator.lib.percolate.content_strip_inventory import (  # noqa: E402
    STATE_MEANING,
    enumerate_strip_rows,
    orphan_store_targets,
)

_SETUP_DIR = _REPO_ROOT / "setup"


def _render_table(rows) -> str:
    name_width = max((len(row.name) for row in rows), default=4)
    state_width = max((len(row.state) for row in rows), default=5)
    lines = [
        f"{'ROW'.ljust(name_width)}  {'STATE'.ljust(state_width)}  HOOK   ENTRIES",
        f"{'-' * name_width}  {'-' * state_width}  -----  -------",
    ]
    for row in rows:
        hook = "on" if row.hook_active else "off"
        lines.append(
            f"{row.name.ljust(name_width)}  {row.state.ljust(state_width)}  "
            f"{hook.ljust(5)}  {row.entry_count}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if any row is half-configured or has no store section",
    )
    args = parser.parse_args(argv)

    rows = enumerate_strip_rows(_SETUP_DIR)
    orphans = orphan_store_targets(_SETUP_DIR)

    if args.json:
        print(
            json.dumps(
                {
                    "rows": [
                        {
                            "name": row.name,
                            "dest_sigil": row.dest_sigil,
                            "state": row.state,
                            "hook_active": row.hook_active,
                            "entry_count": row.entry_count,
                        }
                        for row in rows
                    ],
                    "orphan_store_targets": orphans,
                },
                indent=2,
            )
        )
    else:
        print(_render_table(rows))
        seen_states = sorted({row.state for row in rows})
        print()
        for state in seen_states:
            print(f"  {state}: {STATE_MEANING[state]}")
        if orphans:
            print(f"\n  orphan store targets (no publish row): {', '.join(orphans)}")

    if args.check:
        broken = [row for row in rows if row.misconfigured or not row.has_store_target]
        if broken or orphans:
            for row in broken:
                print(f"FAIL {row.name}: {row.state} — {STATE_MEANING[row.state]}", file=sys.stderr)
            for orphan in orphans:
                print(f"FAIL {orphan}: store target names no publish row", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
