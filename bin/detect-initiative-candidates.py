# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""detect-initiative-candidates — Read-only graduation-gate detector.

Groups the unattached record set (from `query-records --unattached`, or its
native equivalent — see § Self-query below) by shared signal (topic/tag/
co-citation/directory) and emits CANDIDATE clusters with a suggested label.
Explicitly a surface, never a writer — accepts no output-path argument and
opens no write handles.

Floor: DR-209's ≥3-items-per-cluster threshold. A cluster below 3 unattached
items does not surface as a candidate.

Spec backlink: docs/plans/2026-07-04-initiative-govern-sweep-prioritize-doe-d.md § C4 (AC5)

Usage:
    detect-initiative-candidates [--format text|json] [--root <path>]

    Input: reads JSON from stdin when piped (query-records --unattached
    --format json | detect-initiative-candidates), otherwise self-queries
    the native records surface (see § Self-query).

Self-query (naked-Python port, 2026-07-22 depolyglot campaign; collapsed to
the native `unattached` lens the same day once claude-klabauter shipped it):
    The retired node original self-queried by execFileSync-ing
    `query-records.js --unattached --format json`. At initial port time
    `--unattached` had no native counterpart, so `_query_unattached_all()`
    reproduced query-records.js's `queryUnattachedAll()` (multi-type union +
    `_type` tag) as a 6-call loop over a client-side UNATTACHED_TYPES list,
    one native `records_query.query_records()` call per type, using the
    null-FK `where "initiative="` predicate as a workaround.

    claude-klabauter has since landed a native `unattached` union lens (commit
    5709969b) and the trampoline (coordinator/bin/lib/records_query.py,
    commit 177f94b1) now exposes it as `query_records("", "", unattached=True,
    limit=0)`. `_query_unattached_all()` below is a single call to that lens:
    the engine assembles the union across its own engine-owned unattached
    type set and tags each record with `_type` itself — this port no longer
    supplies the type list or the null-FK predicate. `limit=0` is REQUIRED
    (not optional) — the op treats an omitted limit as its own default cap
    of 50 records, which would silently truncate a 500+-record union; this
    is exactly the trap records_query.py's own docstring warns about, and
    was in fact live in this file's pre-collapse loop (each per-type call
    below omitted `limit` and was therefore itself silently capped at 50 per
    type — see the git history of this docstring / the collapse commit for
    the before/after count).

Negative-spec:
    - Does NOT accept an --output or --out argument (read-only surface, hard error if passed).
    - Does NOT open any write handles.
    - Does NOT auto-create initiatives (surface-and-confirm; human authors the cut).
    - Does NOT spawn node or any query-records.js subprocess — the self-query
      path is an in-process native records_query.query_records() loop.
"""
from __future__ import annotations

import json
import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_SCRIPT_DIR))

_BOOTSTRAP_DONE = False


def _bootstrap_engine() -> None:
    """Put the repo root on ``sys.path`` before ``records_query`` is imported.

    Idempotent; safe to call more than once. Moved out of module scope
    (2026-08-28) -- unconditionally mutating `sys.path` at import time made
    every import of this file mutate the `sys.path` of a warm server ~50
    sessions share. Only the trigger moved; the effect is byte-for-byte the
    same.
    """
    global _BOOTSTRAP_DONE
    if _BOOTSTRAP_DONE:
        return
    if _REPO_ROOT not in sys.path:
        sys.path.insert(0, _REPO_ROOT)
    _BOOTSTRAP_DONE = True

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# NOTE: no longer the query driver. `_query_unattached_all()` now issues a
# single native `unattached=True` call (see module docstring § Self-query)
# and the engine owns the authoritative FK-carrying type set (DR-226 —
# holding a client-side copy of engine-owned schema knowledge goes stale the
# moment a new FK-carrying type is added, with no signal to this copy).
#
# Retained only because coordinator/tests/test_detect_initiative_candidates_port.py
# still iterates it to assert per-type parity between the union and a direct
# per-type `query_records()` call — it documents the type set this module
# was historically responsible for spanning, not a set this module computes
# or drives queries from any more.
#
# Spec backlink: docs/plans/2026-07-04-initiative-govern-sweep-prioritize-doe-d.md § C3 (AC4)
UNATTACHED_TYPES = ["bug", "debt", "improvement", "roadmap", "handoff", "plan"]

# ---------------------------------------------------------------------------
# Core clustering logic
# ---------------------------------------------------------------------------
#
# detect_candidates() and its STOP_WORDS/_extract_keywords/_normalize_tags/
# _parent_dir/_dedupe_preserve_order/_humanize/_item helpers moved to
# coordinator_core/clustering/candidates.py (2026-07-23 C2 extraction) —
# this module now only imports detect_candidates/MIN_CLUSTER_SIZE (see the
# import block above) and calls it from _emit() below; it is no longer a
# clustering-logic owner.

# ---------------------------------------------------------------------------
# Native self-query — multi-type unattached union lens
# ---------------------------------------------------------------------------


def _query_unattached_all(root: str | None) -> list[dict]:
    """Native `unattached` union lens: single call to
    records_query.query_records(unattached=True) — the engine assembles the
    union across its own engine-owned unattached type set and tags each
    returned record with `_type` itself.

    Returns every record whose initiative FK is null/absent, spanning queues
    (bug/debt/improvement) + roadmap spinoff-stubs + handoffs + plans — the
    same observable set the retired 6-call per-type loop assembled by hand
    (see module docstring § Self-query for the collapse history).

    `limit=0` is passed explicitly and is load-bearing: the op treats an
    omitted limit as its own default cap of 50 records, which would silently
    truncate the union for any type contributing more than 50 records (e.g.
    `improvement`/`plan` at time of writing). This function issues no
    --sort (detect-initiative-candidates never passes one), so no post-union
    sort step is needed to preserve prior observable behavior for this
    caller.

    Args:
        root: optional repo root override. query_records() resolves its repo
            root from cwd (git rev-parse --show-toplevel), not a parameter —
            an explicit --root is honored by temporarily chdir-ing for the
            duration of the call, then restoring cwd.

    Error handling: with a single call there is no per-type granularity left
    to tolerate a bad type and continue (the retired per-type loop could
    skip one bad type and still return the rest; this call cannot). Any
    failure here propagates to the caller rather than being swallowed into
    an empty/partial list — a false-empty result would make the CLI report
    "no candidates" when the truth is "the engine broke", which is worse
    than a loud failure. `main()`'s self-query branch catches this and exits
    1 with a diagnostic (see below).

    Spec backlink: docs/plans/2026-07-04-initiative-govern-sweep-prioritize-doe-d.md § C3 (AC4)
    """
    _bootstrap_engine()
    from records_query import query_records  # noqa: E402  (sys.path-dependent)

    prior_cwd = os.getcwd()
    if root:
        os.chdir(root)
    try:
        raw = query_records("", "", format_="json", limit=0, unattached=True)
        return json.loads(raw)
    finally:
        if root:
            os.chdir(prior_cwd)


# ---------------------------------------------------------------------------
# CLI argument parser
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str]) -> dict:
    """Parse CLI arguments. Hard-errors on any --output / --out flag to enforce the
    read-only contract structurally.
    """
    opts = {"format": "text", "root": None}
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--format" and i + 1 < len(argv):
            opts["format"] = argv[i + 1]
            i += 2
        elif arg.startswith("--format="):
            opts["format"] = arg[len("--format="):]
            i += 1
        elif arg == "--root" and i + 1 < len(argv):
            opts["root"] = argv[i + 1]
            i += 2
        elif arg.startswith("--root="):
            opts["root"] = arg[len("--root="):]
            i += 1
        elif arg.startswith("--output") or arg.startswith("--out=") or arg == "--out":
            # Structural backstop: reject any attempt to specify an output path.
            sys.stderr.write(
                "ERROR: detect-initiative-candidates is a read-only surface — --output is not supported.\n"
                "       Output is written to stdout only.\n"
            )
            sys.exit(2)
        else:
            i += 1
    return opts


# ---------------------------------------------------------------------------
# Text renderer
# ---------------------------------------------------------------------------


def _render_text(candidates: list[dict]) -> str:
    """Render candidate clusters as human-readable text.
    Each cluster is printed as a CANDIDATE block followed by its item list.
    """
    if not candidates:
        return "No initiative candidates detected (all clusters below ≥3 threshold).\n"
    lines: list[str] = []
    for cluster in candidates:
        lines.append("CANDIDATE: %s" % cluster["suggestedLabel"])
        lines.append("  signal: %s/%s" % (cluster["signal"], cluster["value"]))
        lines.append("  items: %d" % len(cluster["items"]))
        for item in cluster["items"]:
            label = " (%s)" % item["title"] if item["title"] else ""
            lines.append("  - %s%s" % (item["path"], label))
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _emit(records: list[dict], format_: str) -> None:
    _bootstrap_engine()
    from coordinator_core.clustering.candidates import detect_candidates

    candidates = detect_candidates(records)
    if format_ == "json":
        sys.stdout.write(json.dumps(candidates, indent=2) + "\n")
    else:
        sys.stdout.write(_render_text(candidates))


def main(argv: "list[str] | None" = None) -> int:
    # argv threading: this CLI reads sys.argv at depth (argparse and helpers),
    # so the warm-call path swaps it for the duration rather than rewriting every read.
    # NOT re-entrant: a threaded server must serialise calls into this entrypoint.
    _bootstrap_engine()
    _prev_argv = sys.argv
    if argv is not None:
        sys.argv = [sys.argv[0], *argv]
    try:
        argv = sys.argv[1:]
        if "--help" in argv or "-h" in argv:
            # Handled before any stdin touch (§ entrypoint gate contract: every
            # scanned entrypoint is launched with `--help` and stdin=DEVNULL —
            # `sys.stdin.isatty()` is False for DEVNULL too, so without this
            # early exit `--help` would fall through to the stdin-pipe branch
            # below and fail on an empty read, misreporting a clean-launch CLI
            # as broken). No prior code path in this file handled `--help` at
            # all; this closes that gap the same way every other CLI here does.
            sys.stdout.write(__doc__ or "")
            return 0
    
        opts = _parse_args(argv)
    
        # Determine input source: stdin pipe or direct native self-query.
        stdin_is_pipe = not sys.stdin.isatty()
    
        if stdin_is_pipe:
            # Read JSON from stdin (supports: query-records --unattached | detect-initiative-candidates)
            buf = sys.stdin.read()
            try:
                records = json.loads(buf)
            except json.JSONDecodeError as e:
                sys.stderr.write("ERROR: failed to parse JSON from stdin: %s\n" % e)
                return 1
            _emit(records, opts["format"])
        else:
            # Self-query the native records surface directly (see module docstring § Self-query).
            try:
                records = _query_unattached_all(opts["root"])
            except Exception as e:  # noqa: BLE001 — CLI boundary: any failure -> diagnostic + exit 1
                sys.stderr.write("ERROR: records.query invocation failed: %s\n" % e)
                return 1
            _emit(records, opts["format"])
    
        return 0
    finally:
        sys.argv = _prev_argv


if __name__ == "__main__":
    sys.exit(main())
