"""query-record-history.py — CLI trampoline over the records.history engine op.

No shebang line: like this directory's other generator-owned two-leg
entrypoints (a tracked `.cmd`/`.ps1` sibling pair via
`coordinator/bin/gen-launcher-shim.py`), this file is invoked as
`python3 query-record-history.py`, never as a bare word — no exec-bit/shebang
launch path exists for it, so none is asserted here.

Purpose: the operator/consumer route to `records.history` (AC7,
`coordinator_core/ops/record_history.py`) — a git-derived transition history
for one record type. Shape-matches `query-work-state.py` / `query-records.py`:
same flag vocabulary (`--type`, `--format`, `--root`, `--limit`), same
empty-result exit-code contract (an empty result set exits 0, not a
failure), same trampoline posture (resolve repo root, route the op through
`cc_invoke`, print to stdout, exit 0 on success and non-zero on failure).

`records.history` is a READ-ONLY, COMPUTE_ONLY op (DR-215's command-type,
spawn-per-call execution model — the resident daemon this trampoline would
otherwise imply was retired by that decision's § 2, not its § 1 client-
behaviour context, which a prior-art review challenge mistook it for and
which was checked at source and upheld; see this plan's C3 body). This
trampoline therefore calls `cc_invoke.route()`, not `route_mutation()` —
`route()` returns the bare result dict on transport success and raises on
transport failure/seam-absence; there is no in-envelope exit_code/failed
ladder to inspect here.

`--limit` is trampoline-side sugar, NOT an op param — `records.history`
takes only `record_type`/`root` (per its own module docstring's
Anti-scope: no cache, no stored derivation, no extra query grammar). This
file slices the fetched `records` list to the first N entries client-side,
mirroring `query-records.py`'s own `is not None` (not truthiness) guard so
`--limit 0` is distinguishable from "no --limit given" — here, `--limit 0`
means "return zero records" (an explicit, not a default-restoring, ask),
since there is no server-side default to fall back to.

`--format json` (AC7's tested shape) emits a bare JSON array of records on
stdout — NOT the full `{"record_type", "root", "records"}` envelope; a
consumer wants the array, and `record_type`/`root` are already the
consumer's own input, not new information. `--format markdown-list` (the
default, matching `query-records.py`'s own default) emits one heading line
per record (`path`, `created_at`, `created_by`) followed by one line per
event (`sha`, `committed_at`, `author`, `changes`).

Spec backlink: docs/plans/2026-08-20-a-time-axis-for-any-record-type.md § C3 (AC7)

Usage:
    python3 query-record-history.py --type sizing-object
    python3 query-record-history.py --type decision --format json
    python3 query-record-history.py --type decision --format json --limit 5
    python3 query-record-history.py --type decision --root /path/to/repo

Exit codes:
    0 — success, result printed to stdout (including an empty result set).
    2 — `--type` absent or unknown, or the op invocation failed; stderr names
        the supported record type set where available.

Negative-spec: does NOT invoke bash, sh, or any shell — subprocess spawning
lives entirely inside `cc_invoke.route()`. Does NOT reimplement the git-log
derivation; that is engine-owned (`coordinator_core/ops/record_history.py`)
and reached solely through the `records.history` op. Does NOT cache or
snapshot a derived copy — every invocation re-derives from live git history.
"""
from __future__ import annotations

import argparse
import json
import os
import sys


def _no_legacy() -> None:
    """State-1 fallback — `records.history` has no bash predecessor.

    Raises unconditionally; `cc_invoke.route()` wraps the raise in the
    standardized four-rung remediation message on State-1 (seam absent).
    """
    raise RuntimeError("query-record-history: native seam required (no bash fallback)")


def _supported_types_hint() -> str:
    """Best-effort supported-type listing for an error message.

    Imports `coordinator_core.ops.record_history` in-process (same
    precedent `query-records.py::_list_schemas` already establishes for
    reaching engine-side metadata from a CLI). Returns an empty string
    (never raises) if the seam is unavailable — the caller's own error
    message still stands on its own without this hint.
    """
    try:
        from cc_invoke import require_dispatch_engine_on_path

        require_dispatch_engine_on_path()
        from coordinator_core.ops.record_history import supported_record_types

        return ", ".join(sorted(supported_record_types()))
    except Exception:  # noqa: BLE001 - best-effort hint only
        return ""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="query-record-history.py")
    parser.add_argument(
        "--type",
        dest="type_",
        default=None,
        help=(
            "Record type to derive history for (e.g. sizing-object, decision). "
            "Required. Run with a missing/invalid value to see the supported set."
        ),
    )
    parser.add_argument(
        "--format",
        dest="format_",
        default="markdown-list",
        help=(
            "Output shape: 'markdown-list' (default; one heading per record, "
            "one line per event) or 'json' (a bare JSON array of records)."
        ),
    )
    parser.add_argument(
        "--root",
        dest="root",
        default=None,
        help="Worktree root to derive history against. Default: the resolved repo root.",
    )
    parser.add_argument(
        "--limit",
        dest="limit",
        type=int,
        default=None,
        help=(
            "Return at most N records (client-side slice, applied after the op "
            "returns). 0 means zero records, not 'no limit'."
        ),
    )
    return parser


def _format_markdown_list(records: list[dict]) -> str:
    lines: list[str] = []
    for record in records:
        lines.append(
            f"## {record.get('path')} "
            f"(created_at={record.get('created_at')} created_by={record.get('created_by')})"
        )
        events = record.get("events") or []
        if not events:
            lines.append("  (no events)")
            continue
        for event in events:
            lines.append(
                f"  - {event.get('committed_at')} {event.get('sha')} "
                f"{event.get('author')} {event.get('changes')}"
            )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    import cc_invoke

    cc_invoke.require_dispatch_engine_on_path()
    # LOAD-BEARING, NOT DEAD. Do not delete on an unused-import sweep: this line is
    # what BINDS coordinator_core, and binding it HERE is the whole fix.
    # require_dispatch_engine_on_path() above only mutates sys.path -- it imports
    # nothing. Without this line the next import below (a binder module that
    # resolves on the LOCATOR axis) wins the race and binds coordinator_core off
    # the working tree instead of the dispatch root, and no later sys.path insert
    # can rebind an already-imported package. Removing it restores a silent
    # wrong-tree divergence that require_dispatch_engine_on_path now raises on.
    # Why: docs/plans/2026-08-26-the-seam-reports-what-it-got.md C9,
    # docs/research/engine-provenance-carrier-dependence.md
    import coordinator_core  # noqa: F401

    from records_query import _resolve_repo_root

    effective_argv = list(argv) if argv is not None else sys.argv[1:]

    parser = _build_parser()
    args = parser.parse_args(effective_argv)

    if not args.type_:
        hint = _supported_types_hint()
        msg = "query-record-history: --type is required"
        if hint:
            msg += f"; supported: {hint}"
        print(msg, file=sys.stderr)
        return 2

    repo_root = os.path.abspath(args.root) if args.root else _resolve_repo_root()

    params: dict[str, object] = {"record_type": args.type_, "root": repo_root}

    try:
        result = cc_invoke.route("records.history", params, repo_root, _no_legacy)
    except Exception as exc:  # noqa: BLE001 - CLI boundary: any failure -> diagnostic + exit 2
        msg = f"query-record-history: records.history invocation failed: {exc}"
        # The op raises UnsupportedRecordTypeError across the seam as a bare
        # -32603, so the supported set the exception itself carries never
        # reaches stderr. Re-derive it here rather than let an unknown --type
        # read as a transport failure.
        hint = _supported_types_hint()
        if hint and args.type_ not in hint.split(", "):
            msg += f"\nquery-record-history: --type {args.type_!r} is not a supported type; supported: {hint}"
        print(msg, file=sys.stderr)
        return 2

    records = result.get("records", []) if isinstance(result, dict) else []
    # `is not None`, NOT truthiness — `--limit 0` is an explicit "zero
    # records", distinguishable from "no --limit given" (no server-side
    # default exists here to silently restore). Mirrors query-records.py's
    # own `is not None` guard.
    if args.limit is not None:
        records = records[: args.limit]

    if args.format_ == "json":
        sys.stdout.write(json.dumps(records))
        sys.stdout.write("\n")
        return 0

    out = _format_markdown_list(records)
    if out and not out.endswith("\n"):
        out += "\n"
    sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
