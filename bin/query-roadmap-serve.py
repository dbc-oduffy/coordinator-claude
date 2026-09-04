"""query-roadmap-serve.py -- the porter over `ops/roadmap_dag.py:assemble_roadmap_dag`.

No shebang line, no exec bit. The `.cmd`/`.ps1` siblings beside this file ARE
generated, by `gen-launcher-shim.py`, and shipping them is not optional:
Example-cockpit-repo's house CLI spawner prefers the `.cmd` twin on win32 by rule,
because Node cannot `execFileSync` a `.py` without `shell: true`. A missing
shim blocked `query-commit-closures` from the one caller it was built for --
see that porter's module docstring for the full account. Do not ship this file
without its two siblings.

Purpose: a per-repo, one-process entry point a non-Python caller (project-
Cockpit) can spawn to read ONE roadmap's DAG and roll-up -- the per-stub node
set, the blocks-edges between them, and the completion roll-up derived from
them -- without linking against `coordinator_core` or standing up a JSON-RPC
client of its own.

NOT A PORT OF THE KILLED MODULE. `coordinator_core/ops/roadmap_serve.py` and
its CLI were deleted 2026-08-27 as K-107, at 406.2ms process p50 over 585
samples, and kill means kill forever -- neither was read to write this file.
The producer underneath here, `ops/roadmap_dag.py :: assemble_roadmap_dag`, is
a DIFFERENT module that was never killed: it predates the kill, has a live
caller in `ops/emit/context.py :: assembler_dag`, and already returns this
CLI's entire wire shape. The 406.2ms was a corpus scan for stubs whose recorded
paths had gone stale, multiplied by one process per id for want of a list mode;
it was not the cost of the read this file performs.

Why this exists at all: the two channels that ever carried `roll_up` and the
DAG tables to cockpit are both dead. The emission was deleted 2026-08-22 under
DR-351, and the CLI was killed as K-107 on 2026-08-27. Their ingest code is
live on both legs and has had nothing to ingest since.

Usage:
    python3 query-roadmap-serve.py --roadmap-id sedge-2026-08-06

Wire shape -- exactly ONE JSON OBJECT on stdout, no `{"records": [...]}`
envelope (example-cockpit-repo `src/lib/store/roadmaps-acquisition.ts ::
fetchRoadmapServe`, read at `origin/main` @ `abcc06ad9`, parses stdout as the
record itself):

    {roadmap_id, nodes[], edges[], roll_up, critical_path[],
     scan_incomplete, scan_errors[]}

A ZERO WE CANNOT SUBSTANTIATE IS NOT EXPRESSIBLE. `roll_up` is served as
`null`, never as `{"total": 0, ...}`, when the stub corpus could not be
scanned AND no nodes were found -- i.e. when `scan_incomplete` is true and
`roll_up.total` is 0. A roadmap that genuinely has no stubs keeps its real
`{"total": 0}`; a roadmap whose identity source we could not read reports
`null` alongside `scan_incomplete: true`, so the two are distinguishable on
the wire. Committed to cockpit in
`docs/research/spike-verdicts/2026-09-02-roadmap-serve-v2-read-shape.md`, and
their storage layer already admits it (`schema.ts:345` declares `roll_up TEXT`
nullable; their acquisition coerces a null to SQL NULL). A partial scan that
DID find nodes keeps its roll-up -- the count is real, and `scan_incomplete`
is the flag that says it may be short.

`critical_path` IS SERVED, deviating from the spike verdict's "drop it".
The verdict's reasoning was about cockpit's STORAGE -- no column, no
migration, no consumer -- and that reasoning still holds; nothing persists it.
But their WIRE type declares it (`RoadmapServeRecord.critical_path`) and their
tests pin it round-tripping onto the record
(`roadmaps-acquisition.test.ts:91/98/142`, `origin/main`). `assemble_roadmap_dag`
computes it either way, so serving it costs nothing and dropping it would turn
their suite red for no gain. A separate, earlier claim of mine -- that
`critical_path` is unconsumed on both sides and droppable outright -- was too
broad and was corrected to cockpit by memo on 2026-09-02: it is a required
field of the frozen `RoadmapSummary` contract on the emission channel.

Negative-spec: does NOT add a list/batch/`--all` mode. The committed consumer
spawns this CLI once per roadmap id with `--roadmap-id` and enumerates ids from
its own store; a batch mode has no adopter and would be speculative generality
(overengineering-reviewer finding 3, 2026-09-02, disposition SURVIVES -- ship
the invocation contract the actual caller uses). Twelve ids in one process was
measured at 3.5ms over one id, so the mode is cheap to add IF a consumer ever
commits to it -- it is not a launch requirement. Does NOT mint a registered op:
`assemble_roadmap_dag` is a plain in-process function, not something
`cc_invoke.route` can dispatch, and minting an op name is an engine change no
requirement here asks for (same call `query-commit-closures.py` makes over its
own section). Does NOT edit `coordinator_core/ops/roadmap_dag.py` -- that file
is READ-ONLY to this porter. Does NOT reshape, rename, filter, or re-derive any
field: the output is `assemble_roadmap_dag`'s existing shape verbatim, plus the
`roadmap_id` echo the wire shape requires and the null-roll_up rule above.

Exit codes:
    0 -- success, the single record printed to stdout as JSON.
    1 -- repo-root or engine-root resolution failure, `coordinator_core` not
         importable, or any exception raised while assembling the DAG.
    2 -- missing or unrecognized argument (argparse's own usage-error
         convention, matching `query-commit-closures.py`).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_BIN_DIR = os.path.dirname(os.path.abspath(__file__))

_BOOTSTRAPPED_NAMES = ("resolve_claude_klabauter_root_or_exit", "resolve_repo_root_or_exit")


def _bootstrap_op_trampoline() -> None:
    """Import `coordinator/bin/lib/op_trampoline.py`'s two Shape-A resolvers
    into this module's globals, deferred out of module scope so a warm-serve
    import of this file stays inert until `main()` runs. Idempotent by
    construction: each name is published via `globals().setdefault(...)`, so a
    name a caller already bound (e.g. a `mock.patch.object` of just one of the
    two resolvers) is left alone rather than clobbered when the other name is
    still missing."""
    if all(n in globals() for n in _BOOTSTRAPPED_NAMES):
        return

    import lib  # noqa: F401 -- bootstraps coordinator/bin/lib onto sys.path
    from op_trampoline import (
        resolve_claude_klabauter_root_or_exit as _resolve_claude_klabauter_root_or_exit,
        resolve_repo_root_or_exit as _resolve_repo_root_or_exit,
    )

    for _name, _value in (
        ("resolve_claude_klabauter_root_or_exit", _resolve_claude_klabauter_root_or_exit),
        ("resolve_repo_root_or_exit", _resolve_repo_root_or_exit),
    ):
        globals().setdefault(_name, _value)


def __getattr__(name: str):
    """PEP 562 hook serving the two op_trampoline resolvers to a test or
    sibling importer that reads them off this module without calling `main()`
    first (e.g. `mock.patch.object(mod, "resolve_repo_root_or_exit", ...)`).

    Negative-spec: does NOT serve any other name -- an unrelated AttributeError
    still raises normally.
    """
    if name in _BOOTSTRAPPED_NAMES:
        _bootstrap_op_trampoline()
        try:
            return globals()[name]
        except KeyError:
            raise AttributeError(
                f"module {__name__!r} has no attribute {name!r}"
            ) from None
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


_HONESTY_DISCLOSURES = """\
TWO coverage limits a consumer of this CLI must not lose:

  `scan_incomplete` is not decoration. True means a live- or archived-handoff
  subtree could not be read, so the node set may be SHORT and the roll-up
  derived from it correspondingly low. It is never "these are genuinely all
  the stubs". When it is true and no nodes were found at all, `roll_up` is
  served as null rather than a zero this CLI cannot substantiate.

  `status` on each node is the raw `deployment_state` frontmatter value, NOT
  the baton lifecycle `status` field. Reading the latter reports 0% shipped
  for every roadmap -- the two carry different vocabularies and only
  `deployment_state` carries `shipped`."""


def build_parser() -> argparse.ArgumentParser:
    """One required flag, `--roadmap-id`. No list/batch mode -- see the module
    docstring's Negative-spec."""
    parser = argparse.ArgumentParser(
        prog="query-roadmap-serve.py",
        description=_HONESTY_DISCLOSURES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--roadmap-id",
        required=True,
        metavar="ID",
        help="roadmap identifier to assemble the DAG and roll-up for",
    )
    return parser


def _apply_unsubstantiated_zero_rule(payload: dict) -> dict:
    """Null out a `roll_up` whose zero we cannot substantiate.

    See the module docstring: a scan that failed AND found nothing cannot tell
    an empty roadmap from an unreadable one, so it reports `null`. A scan that
    failed but still found nodes keeps its (real, possibly short) roll-up --
    `scan_incomplete` is what flags that.
    """
    roll_up = payload.get("roll_up")
    if (
        payload.get("scan_incomplete")
        and isinstance(roll_up, dict)
        and not roll_up.get("total")
    ):
        payload["roll_up"] = None
    return payload


def main(argv: list[str] | None = None) -> int:
    if any(n not in globals() for n in _BOOTSTRAPPED_NAMES):
        _bootstrap_op_trampoline()
    resolve_claude_klabauter_root_or_exit = globals()["resolve_claude_klabauter_root_or_exit"]
    resolve_repo_root_or_exit = globals()["resolve_repo_root_or_exit"]

    argv = sys.argv[1:] if argv is None else argv
    parser = build_parser()
    args = parser.parse_args(argv)  # exits 2 on a missing/unrecognized argument

    repo_root = resolve_repo_root_or_exit()
    if isinstance(repo_root, int):
        return repo_root

    claude_klabauter_root = resolve_claude_klabauter_root_or_exit("query-roadmap-serve")
    if isinstance(claude_klabauter_root, int):
        return claude_klabauter_root

    try:
        from coordinator_core.ops.emit.resolvers import resolve_context
        from coordinator_core.ops.roadmap_dag import assemble_roadmap_dag
    except ImportError as exc:
        print(f"query-roadmap-serve: coordinator_core not importable: {exc}", file=sys.stderr)
        return 1

    try:
        # `central_state_root.parent` is the SAME worktree root the live
        # producer resolves in `ops/emit/context.py :: assembler_dag`. Resolved
        # through `resolve_context` rather than re-derived here so the two
        # callers cannot drift, and so a raw `common_dir`/.git path is never
        # reachable (lesson: common-dir-keyed-ops-must-derive-the-wor).
        ctx = resolve_context(Path(repo_root))
        dag = assemble_roadmap_dag(args.roadmap_id, worktree_root=ctx.central_state_root.parent)
    except Exception as exc:  # noqa: BLE001 -- any failure on this path is exit 1.
        print(f"query-roadmap-serve: {exc}", file=sys.stderr)
        return 1

    payload = _apply_unsubstantiated_zero_rule({"roadmap_id": args.roadmap_id, **dag})
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
