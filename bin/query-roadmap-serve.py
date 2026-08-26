"""query-roadmap-serve.py — declarative shim over `op_trampoline.run` routing `roadmap.serve`.

No shebang line: this file is invoked as `python3 query-roadmap-serve.py`, never
as a bare word — no exec-bit/shebang launch path exists for it, so none is
asserted here. No `.cmd`/`.ps1` shim is generated either: the newest exemplar
this repo mirrors (`query-handoff-columns.py`) deliberately ships neither, and
nothing sweeps for one; `coordinator/bin/gen-launcher-shim.py` exists if a
caller later needs bare-name invocation on Windows.

Purpose: a per-repo, one-process entry point a non-Python caller (the sibling
fleet-board consumer) can spawn to read one roadmap's roll-up scalars and
critical path over live handoff frontmatter, without linking against
`coordinator_core` or standing up a JSON-RPC client of its own. This file
supplies only the two pieces `coordinator/bin/lib/op_trampoline.py` (C0) does
not own — the op name and a `params_builder(argv)` parsing
`--roadmap-id <id>` into `{"roadmap_id": <id>}` — and delegates everything
else (repo-root resolution, the legacy-seam raise, the `cc_invoke.route`
call, JSON emission, the exit-code convention, the failure diagnostic) to
`op_trampoline.run`. Do NOT reimplement any of that inline; that hand-copying
is the exact defect `op_trampoline.py` exists to end.

Op contract (`roadmap.serve`, coordinator_core/ops/roadmap_serve.py) — already
verified, not re-derived here: takes exactly one param, `roadmap_id: str`;
`repo_root` is router-supplied, never a caller param. `roll_up` is a dict
`{total, by_status, pct_shipped}` where `pct_shipped` is null at
`total == 0`. `critical_path` is a list of `stub_id` strings — an unweighted
longest-blocks-chain by node count. It is NOT duration-weighted CPM; do not
describe it as CPM anywhere in this file's help text or docstrings.

Exit-code convention (owned by `op_trampoline.run`, cited here so the choice
reads as inherited): exit 1 for every non-success path (transport failure,
seam-absent, root-unresolvable) is the established majority — 3 of 4 existing
`query-*` CLIs already do this (`query-handoff-columns`, `query-completions`,
`query-session-hierarchy`). `query-records`' 2/3
split is a known, deliberately-not-normalised outlier here, not a competing
convention.

Usage:
    python3 query-roadmap-serve.py --roadmap-id <id>

Exit codes:
    0 — success, the routed `roadmap.serve` result printed to stdout as JSON
        (including `roll_up` and `critical_path`); also `--help`.
    1 — repo-root resolution failure, or op-level failure (transport failure,
        seam absent, or any other exception raised while routing the op) —
        `op_trampoline.run`'s exit convention, not reimplemented here.
    2 — usage error (missing/unrecognized argument) — `argparse`'s own
        convention, on a separate axis from `op_trampoline.run`'s exit 1;
        AC3 pins exit 1 for op-level transport failure only, and this CLI
        does not force argparse's usage exit onto that code.

Spec backlink: plan `2026-08-11-three-trampolines-and-the-bare-repo-producer.md` § C3

Negative-spec: does NOT reimplement the sys.path dance, `cc_invoke.route`
call, `_no_legacy` closure, JSON emission, or exit-code convention inline —
all of that is `op_trampoline.run`'s job (C0), reached here solely through
`run("roadmap.serve", params_builder, argv=...)`. Does NOT accept a generic
`<op> --param k=v` shape — `--roadmap-id` is the only recognized flag,
because a generic op-name/param dispatcher would leak this producer's internal
op namespace into a sibling repo's spawn contract (C0's own hard negative-spec).
Does NOT generate a `.cmd`/`.ps1` launcher shim. Does NOT describe
`critical_path` as duration-weighted CPM.
"""
from __future__ import annotations

import argparse
import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from op_trampoline import run  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(
        prog="query-roadmap-serve.py",
        description=(
            "Read-only CLI over the roadmap.serve op — one roadmap's "
            "roll-up scalars and critical path, computed live from handoff "
            "frontmatter."
        ),
    )


def params_builder(argv: list[str]) -> dict[str, object]:
    """Parse `--roadmap-id <id>` into `{"roadmap_id": <id>}`.

    Built on `argparse` — the per-CLI piece `op_trampoline.run` deliberately
    does not own (C0's body: "argparse shape (flags, filter grammar,
    `--help` honesty disclosures)"). `--roadmap-id` is `required=True`, so
    argparse itself supplies the missing-value, missing-argument, and
    unrecognized-token errors (exit 2, argparse's own usage-error
    convention — distinct from `op_trampoline.run`'s exit 1 for op-level
    failure) and answers `--help` (exit 0) — neither of which a hand-rolled
    argv scan gets for free.
    """
    parser = _build_parser()
    parser.add_argument("--roadmap-id", dest="roadmap_id", required=True)
    args = parser.parse_args(argv)
    return {"roadmap_id": args.roadmap_id}


if __name__ == "__main__":
    sys.exit(run("roadmap.serve", params_builder, argv=sys.argv[1:]))
