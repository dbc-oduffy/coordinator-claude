#!/usr/bin/env python3
"""plan-completeness — the plan-level completeness ledger CLI: `generate` and `status`.

WHAT IT ANSWERS. "What is complete out of this plan?" straight off disk, no dispatched agent:
which `## Tasks` spine rows are resolved, which dispatched chunks belong to each row, and
whether the plan's own `status` claims more completion than the computed state supports. This is
a thin argparse trampoline over `coordinator/bin/lib/plan_completeness.py`; the
reading/joining/predicate logic lives there, not here.

NEGATIVE SPEC.
  - `generate` writes to exactly one place: `machinery_paths.plan_sidecars_dir(repo_root)/
    <plan-stem>.completeness.md` (the gitignored, derived, UNREAPED-by-design plan-sidecars
    bucket). It has no write path to `docs/plans/` and no other write target.
  - `status` never writes. It prints one rollup line to stdout (plus an optional
    `CONTRADICTION: ` line), and nothing else to stdout — human residue (errors, diagnostics)
    goes to stderr.
  - Accepts a plan path outside `docs/plans/` (the retrospective corpus is archived) — this tool
    never writes the plan, so there is nothing to protect by refusing an archived path.

Arrived from DoE-claude coordinator/bin/plan-completeness.py — plan-completeness was never
ported when its sibling reader `plan-spine-check` was; this mirrors that arrival's registration.
Requirement-restated, not carried verbatim: module scope here carries stdlib imports ONLY (never
the `coordinator/bin/lib` sys.path mutation DoE's copy performed at import time) — the lib
directory and `coordinator_core` are both resolved lazily, inside `_lib()`, the same
inertness-preserving shape `plan-spine-check.py`'s own `_ensure_engine_on_path` uses. A bin
CLI's module body must stay a pure import at warm-door load time (~50 concurrent sessions share
that process); DoE's copy lived outside the engine and carried no such constraint.
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_INCOMPLETE = 1
EXIT_UNREADABLE = 2

#: `TERMINAL_STATUS -> stderr label`, mirroring `plan-spine-check.py`'s two-class verdicts.
_TERMINAL_LABEL = {"no-spine": "NO-SPINE", "unreadable": "UNREADABLE"}


def _lib():
    """The `plan_completeness` lib module, lazily bound — never at module scope (see module
    docstring). Mirrors `plan-spine-check.py::_ensure_engine_on_path`'s lazy-bootstrap shape:
    `import lib` puts `coordinator/bin/lib` on `sys.path` (idempotently, via that package's own
    `__init__.py`), then the sibling module resolves by bare name."""
    import lib  # noqa: F401 -- bootstraps coordinator/bin/lib onto sys.path

    import plan_completeness as _pc

    return _pc


def _chunks_segment(chunks_total, chunks_reported: int) -> str:
    """The `chunks ...` status-line segment (plan's § C3 body, verbatim forms)."""
    if chunks_total is not None:
        return f"chunks {chunks_reported} of {chunks_total} reported"
    if chunks_reported == 0:
        return "chunks UNKNOWN (no emitted workflow)"
    return f"chunks {chunks_reported} reported of UNKNOWN (no emitted workflow)"

def _status_line(rollup: dict) -> str:
    """The one-line rollup (plan's § C3 body). Zero-valued optional segments — non-conformant,
    ambiguous, orphan, `K unapproved closures`, `K out-of-enum dispositions` — are omitted.
    `... diverged` is never omitted, even at zero (the plan's own worked examples show `0
    diverged` unconditionally)."""
    segments = [
        f"{rollup['rows_resolved']} of {rollup['rows_total']} rows resolved",
        _chunks_segment(rollup["chunks_total"], rollup["chunks_reported"]),
        f"{rollup['diverged_count']} diverged",
    ]
    if rollup["non_conformant_divergence_count"]:
        segments.append(f"{rollup['non_conformant_divergence_count']} non-conformant")
    if rollup["ambiguous_chunk_count"]:
        segments.append(f"{rollup['ambiguous_chunk_count']} ambiguous")
    if rollup["orphan_labels"]:
        segments.append(f"{len(rollup['orphan_labels'])} orphan")
    if rollup["unapproved_closure_count"]:
        segments.append(f"{rollup['unapproved_closure_count']} unapproved closures")
    if rollup["out_of_enum_disposition_count"]:
        segments.append(f"{rollup['out_of_enum_disposition_count']} out-of-enum dispositions")
    return " | ".join(segments)


def _contradiction_line(contradiction) -> str:
    """The stable `CONTRADICTION: ` token (plan's § CONTRADICTION predicate)."""
    return f"CONTRADICTION: {contradiction['claim']} — {contradiction['reason']}"


def _status_exit_code(rollup: dict) -> int:
    """Plan's § CONTRADICTION predicate exit table, rows 0/1 (row 2 — NO-SPINE/unreadable —
    is handled by the caller before a rollup exists)."""
    if rollup["rows_resolved"] == rollup["rows_total"] and rollup["contradiction"] is None:
        return EXIT_OK
    return EXIT_INCOMPLETE


def _plan_and_repo(plan_arg: str) -> "tuple[Path, Path] | None":
    """The plan's absolute path and the repo it lives in, or None after naming the miss on stderr.

    Trap: the repo root is the PLAN's, never this script's. The published plugin installs this
    file outside any consumer repo, so an install-relative root reads every consumer plan as
    missing and writes sidecars where nothing reads them (claude-klabauter#78). A relative path
    resolves against cwd, as every sibling ceremony CLI does. The walk looks for `.git` (a dir,
    or a file in a worktree/submodule) instead of spawning git.
    """
    plan = Path(plan_arg)
    if not plan.is_absolute():
        plan = Path.cwd() / plan
    plan = plan.resolve()
    if not plan.is_file():
        print(f"plan-completeness: NOT FOUND — {plan}", file=sys.stderr)
        return None
    for candidate in plan.parents:
        if (candidate / ".git").exists():
            return plan, candidate
    print(f"plan-completeness: NO REPO — no .git above {plan}", file=sys.stderr)
    return None


def cmd_generate(args: argparse.Namespace) -> int:
    resolved = _plan_and_repo(args.plan_path)
    if resolved is None:
        return EXIT_UNREADABLE
    plan, root = resolved
    pc = _lib()
    repo_root = str(root)
    result = pc.build_ledger(repo_root, str(plan))
    if result.status != "located":
        label = _TERMINAL_LABEL.get(result.status, result.status.upper())
        print(f"plan-completeness: {label} — {plan}", file=sys.stderr)
        return EXIT_UNREADABLE

    document = result.document
    document["generated_at"] = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    try:
        pc.ensure_engine_on_path()
        from coordinator_core.session.machinery_paths import plan_sidecars_dir
    except pc.EngineUnreachableError as exc:
        print(f"plan-completeness: {exc}", file=sys.stderr)
        return EXIT_UNREADABLE

    plan_stem = Path(document["plan"]).name
    if plan_stem.endswith(".md"):
        plan_stem = plan_stem[: -len(".md")]
    out_dir = Path(plan_sidecars_dir(repo_root))
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{plan_stem}.completeness.md"
    out_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")

    print(f"plan-completeness: wrote {out_path}", file=sys.stderr)
    return EXIT_OK


def cmd_status(args: argparse.Namespace) -> int:
    resolved = _plan_and_repo(args.plan_path)
    if resolved is None:
        return EXIT_UNREADABLE
    plan, root = resolved
    pc = _lib()
    try:
        result = pc.build_ledger(str(root), str(plan))
    except pc.EngineUnreachableError as exc:
        print(f"plan-completeness: {exc}", file=sys.stderr)
        return EXIT_UNREADABLE

    if result.status != "located":
        label = _TERMINAL_LABEL.get(result.status, result.status.upper())
        print(f"plan-completeness: {label} — {plan}", file=sys.stderr)
        return EXIT_UNREADABLE

    document = result.document
    rollup = document["rollup"]

    if args.format == "json":
        document["generated_at"] = datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        print(json.dumps(document, indent=2))
    else:
        print(_status_line(rollup))
        if rollup["contradiction"] is not None:
            print(_contradiction_line(rollup["contradiction"]))

    return _status_exit_code(rollup)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="plan-completeness",
        description=(
            "Answer 'what is complete out of this plan?' from disk alone. Mirrors "
            "query-completions' CLI shape without extending it."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate_parser = subparsers.add_parser(
        "generate",
        help="Write the ledger sidecar for a plan (its only write target).",
    )
    generate_parser.add_argument("plan_path", help="path to the plan (need not be under docs/plans/)")
    generate_parser.set_defaults(func=cmd_generate)

    status_parser = subparsers.add_parser(
        "status",
        help="Print the one-line rollup (plus a CONTRADICTION line, when it fires) to stdout.",
    )
    status_parser.add_argument("plan_path", help="path to the plan (need not be under docs/plans/)")
    status_parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="text (default): the human rollup line(s). json: exactly one JSON document matching "
        "the C1 ledger schema, nothing else on stdout.",
    )
    status_parser.set_defaults(func=cmd_status)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
