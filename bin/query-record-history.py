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
takes `record_type`/`root`/`since` (per its own module docstring's
Anti-scope: no cache, no stored derivation, no extra query grammar beyond
that). This file slices the fetched `records` list to the first N entries
client-side, mirroring `query-records.py`'s own `is not None` (not
truthiness) guard so `--limit 0` is distinguishable from "no --limit
given" — here, `--limit 0` means "return zero records" (an explicit, not a
default-restoring, ask), since there is no server-side default to fall
back to.

`--type` takes a COMMA-SPLIT multi-value (`--type handoff,sizing-object`),
not a repeatable flag — one split at the CLI boundary is the whole adapter
onto the op's `record_type: str | Sequence[str]` param. A single value with
no comma is passed through as a bare string, keeping the existing
single-type response envelope byte-for-byte (P083-C4 R3); two or more
comma-split values switch the envelope to the multi-type shape (per-record
`record_type`, `untracked` grouped per type). Each member still validates
through the op's own `_require_supported`, so an unsupported member in a
multi-value list keeps this file's own unsupported-type diagnostic below.

`--since` takes an ISO date (`YYYY-MM-DD`), validated HERE at the CLI
boundary (not deep in the derivation — the op's own `since` bounds EVENTS
only, never the walk; see `record_history.py`'s module docstring). Passed
through to the op unchanged.

`--format json` (AC7's tested shape) emits a bare JSON array of records on
stdout — NOT the full envelope; a consumer wants the array, and
`record_type`/`root` are already the consumer's own input, not new
information. `--format markdown-list` (the default, matching
`query-records.py`'s own default) emits one heading line per record
(`path`, `created_at`, `created_by`) followed by one line per event (`sha`,
`committed_at`, `author`, `changes`).

Spec backlink: docs/plans/2026-08-20-a-time-axis-for-any-record-type.md § C3 (AC7)
  P083-C4: docs/plans/2026-09-11-roadmap-audits-readiness-views-and-recor.md

Usage:
    python3 query-record-history.py --type sizing-object
    python3 query-record-history.py --type decision --format json
    python3 query-record-history.py --type decision --format json --limit 5
    python3 query-record-history.py --type decision --root /path/to/repo
    python3 query-record-history.py --type handoff,sizing-object --since 2026-09-01

Exit codes:
    0 — success, result printed to stdout (including an empty result set).
    1 — the op invocation failed (a supported-looking call that errored
        upstream; may be transient).
    2 — usage error: `--type` absent, an unknown/unsupported type (named
        member of a multi-value list included), or a malformed `--since`.

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
import re
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
            "Record type(s) to derive history for (e.g. sizing-object, decision), "
            "comma-split for more than one (e.g. handoff,sizing-object). "
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
    parser.add_argument(
        "--since",
        dest="since",
        default=None,
        help=(
            "Only report events at or after this ISO date (YYYY-MM-DD). Bounds "
            "events only, never created_at/untracked classification."
        ),
    )
    return parser


_SINCE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _format_markdown_list(records: list[dict]) -> str:
    lines: list[str] = []
    for record in records:
        type_suffix = (
            f" [{record['record_type']}]" if "record_type" in record else ""
        )
        lines.append(
            f"## {record.get('path')}{type_suffix} "
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

    if args.since is not None and not _SINCE_RE.match(args.since):
        print(
            f"query-record-history: --since {args.since!r} is not an ISO date "
            "(YYYY-MM-DD)",
            file=sys.stderr,
        )
        return 2

    # Comma-split multi-value (`--type a,b`), not a repeatable flag. A single
    # value with no comma passes through as a bare string so the op's
    # existing single-type response envelope stays byte-for-byte (P083-C4 R3).
    type_members = [t for t in args.type_.split(",") if t]
    record_type: str | list[str] = type_members[0] if len(type_members) == 1 else type_members

    repo_root = os.path.abspath(args.root) if args.root else _resolve_repo_root()

    params: dict[str, object] = {"record_type": record_type, "root": repo_root}
    if args.since is not None:
        params["since"] = args.since

    try:
        result = cc_invoke.route("records.history", params, repo_root, _no_legacy)
    except Exception as exc:  # noqa: BLE001 - CLI boundary: any failure -> diagnostic + exit 2
        msg = f"query-record-history: records.history invocation failed: {exc}"
        # The op raises UnsupportedRecordTypeError across the seam as a bare
        # -32603, so the supported set the exception itself carries never
        # reaches stderr. Re-derive it here rather than let an unknown --type
        # read as a transport failure.
        hint = _supported_types_hint()
        hint_set = hint.split(", ") if hint else []
        unsupported_type = bool(hint) and any(t not in hint_set for t in type_members)
        if unsupported_type:
            msg += f"\nquery-record-history: --type {args.type_!r} is not a supported type; supported: {hint}"
        print(msg, file=sys.stderr)
        # 2 = usage error (fix the call), 1 = op failure (may be transient).
        # These were both 2, which cost a consumer a distinction it acts on:
        # example-cockpit-repo's cache classifies an unknown type as
        # `not-configured` and an op failure as `upstream`, and a single 2
        # forced it to parse stderr prose to tell them apart — which is not a
        # contract (cross-repo/inbox/2026-08-20-example-cockpit-repo-em-record-
        # history-four-consumer-asks.md, ask 3). The collapse was an
        # acknowledged outlier in this file's own docstring, never a ruling.
        return 2 if unsupported_type else 1

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
