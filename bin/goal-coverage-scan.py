#!/usr/bin/env python3
# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""goal-coverage-scan.py — Read-only backward-teeth detector for active goals.

Naked-Python port of the retired node original `coordinator/bin/goal-coverage-
scan` (2026-07-19 Windows de-bash campaign). Enumerates active goals
(state/goals/*.yaml via the native `records.query` op, type=goal) and, for
each, counts artifacts tagged `origin_goal_id: [<goal>]` via a
`origin_goal_id in (<goal>)` where-clause query per COVERAGE_TYPES below.
Only `handoff` currently has a schema-declared origin_goal_id field — the
scan also queries plan/debt/bug/improvement, but those four legs are
forward-looking/inert until their schemas declare the field (see the
COVERAGE_TYPES docstring for detail). Emits per-goal coverage counts and
flags zero-coverage active goals so a human can decide whether to spin off a
stub — mirrors detect-initiative-candidates' surface-and-confirm shape one
cadence-step over (the initiative-govern sweep).

Spec backlink: docs/plans/2026-07-13-close-weekly-goal-loop.md § C5 (AC5);
state/review-trail/findings/2026-07-22-goal-coverage-scan-port-blocked.md
(the blocked-then-cleared port attempt this file completes — the native
records.query op's `goal` type-coverage gap that blocked the original port
is confirmed closed as of 2026-07-22).

Usage:
    goal-coverage-scan.py [--format text|json] [--root <path>]

    Input: routes through records_query.query_records() to enumerate active
    goals (type=goal, where=status=active), then per goal per
    COVERAGE_TYPES, queries `origin_goal_id in (<goal-id>)` to count tagged
    artifacts. Never shells out to node.

    --root is recognised for CLI back-compat with the retired node original
    but is explicitly REJECTED (hard error, non-zero exit) rather than
    silently ignored: records_query.query_records() has no root-override
    parameter — it self-resolves the repo root via `git rev-parse
    --show-toplevel` from cwd (see records_query.py's _resolve_repo_root()).
    A caller passing --root would otherwise get an answer for the wrong
    repo while believing they scanned the one they named — the exact
    wrong-answer-quiet failure shape this backward-teeth detector exists to
    prevent — so the flag fails loud instead. Callers should `cd` to the
    target repo and re-run without --root.

Negative-spec:
    - Does NOT accept an --output or --out argument (read-only surface, hard
      error if passed).
    - Does NOT open any write handles.
    - Does NOT auto-create spinoff stubs (surface-and-confirm; human authors
      the cut).
    - Does NOT auto-tag existing artifacts with origin_goal_id.
    - Does NOT shell out to node or the retired query-records.js — routes
      exclusively through records_query.query_records() (native
      coordinator_core.invoke records.query).
    - An empty or errored goal enumeration is a FAIL LOUD condition (non-zero
      exit + stderr), never rendered as a clean "no active goals" report —
      this tool's entire job is flagging zero-coverage active goals, so a
      silent empty result would be indistinguishable from a healthy all-clear
      (the worst possible failure shape for this specific tool).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(_SCRIPT_DIR, "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

# Review: code-reviewer -- Finding 1, 2026-07-22. Hoisted to module level
# (was a per-call import inside _query_records) so a genuine import failure
# (missing records_query.py, wrong _LIB_DIR, a transitive import error) fails
# loudly and legibly once at process start, rather than escaping as a raw
# unhandled traceback mid-scan on an arbitrary call -- the per-call import sat
# outside _query_records' try/except, so it bypassed the documented
# warn-to-stderr/continue-scanning contract for that one failure mode.
from records_query import query_records  # noqa: E402  (sys.path-dependent)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Record types that may carry origin_goal_id (the work->goal edge).
#
# CURRENTLY WIRED: only `handoff` — handoff.schema.json declares
# origin_goal_id (array<string>|null). This is the only leg that returns
# real coverage data today.
#
# FORWARD-LOOKING / INERT: `plan`, `debt`, `bug`, `improvement` are named in
# the plan's DEC-3/AC4 as intended origin_goal_id bearers, but their schemas
# do not yet declare an origin_goal_id field — nothing on the current
# producer surface writes one onto those types, so these four legs of the
# coverage scan always return [] until their schemas are extended. Included
# here so the scan is ready to pick up real data the moment those schemas
# are wired, at the cost of four no-op query calls per goal in the meantime.
#
# Spec backlink: docs/plans/2026-07-13-close-weekly-goal-loop.md § C4/AC4, § C5/DEC-3
COVERAGE_TYPES = ["handoff", "plan", "debt", "bug", "improvement"]


# ---------------------------------------------------------------------------
# Core coverage logic
# ---------------------------------------------------------------------------


def compute_coverage(goals, lookup_coverage):
    """Compute per-goal coverage for a set of active goals.

    Purpose: backward-teeth surface — given an active goal, checks whether
    any current handoff/plan/queue-entry actually advances it, and flags
    zero-coverage goals so a human can spin off a stub. Never writes
    anything.

    goals: list of {"path": str, "frontmatter": dict} active goal records
        (status=active).
    lookup_coverage: callable(goal_id) -> either a bare list (legacy shape —
        query_errors defaults to 0) or {"items": [...], "queryErrors": int}
        (queryErrors is a count of per-type query failures encountered while
        gathering items). Both shapes are accepted so existing unit tests
        passing a bare-list lookup_coverage keep working.

    Returns a list of dicts, one per active goal, ordered as given:
        {goalId, title, path, count, zeroCoverage, items, queryErrors}
    zeroCoverage is True when count == 0. queryErrors is threaded through so
    a scan-level query-error count can distinguish "confirmed zero
    coverage" from "coverage query degraded" in the rendered output, rather
    than silently collapsing both to the same zeroCoverage=True signal.
    """
    results = []
    for goal in goals:
        frontmatter = goal.get("frontmatter") or {}
        goal_id = frontmatter.get("id") or ""
        title = frontmatter.get("title") or ""
        raw_result = lookup_coverage(goal_id) if goal_id else []
        is_legacy_array_shape = isinstance(raw_result, list)
        items = raw_result if is_legacy_array_shape else (raw_result.get("items") or [])
        query_errors = 0 if is_legacy_array_shape else (raw_result.get("queryErrors") or 0)
        results.append(
            {
                "goalId": goal_id,
                "title": title,
                "path": goal.get("path", ""),
                "count": len(items),
                "zeroCoverage": len(items) == 0,
                "items": [
                    {"path": item.get("path", ""), "type": item.get("_type") or ""}
                    for item in items
                ],
                "queryErrors": query_errors,
            }
        )
    return results


# ---------------------------------------------------------------------------
# records.query invocation helpers
# ---------------------------------------------------------------------------


def _query_records(record_type, where_expr):
    """Invoke records_query.query_records(type, where, format="json") and
    return the parsed record list. Errors are surfaced to stderr and treated
    as an empty result set for that type (a missing/misconfigured type must
    not abort the whole scan — other goals/types may still be scannable).

    Returns {"records": list, "failed": bool} — `failed: True` on a
    swallowed query error (records is [] in that case) — lets callers that
    need to distinguish "confirmed zero coverage" from "coverage query
    degraded" thread that signal through. Callers that don't care (e.g. goal
    enumeration) just read ["records"].
    """
    try:
        raw = query_records(record_type, where_expr, format_="json")
        parsed = json.loads(raw) if raw else []
        for record in parsed:
            record["_type"] = record_type
        return {"records": parsed, "failed": False}
    except Exception as exc:  # noqa: BLE001 - swallow per-type; scan continues
        sys.stderr.write(f"WARNING: records.query --type {record_type} failed: {exc}\n")
        return {"records": [], "failed": True}


def _fetch_active_goals():
    """Fetch all active goals (status=active) via records.query type=goal.

    Raises RuntimeError when the query fails outright OR returns zero
    goals — this tool's entire job is flagging zero-coverage active goals,
    so a silently-empty enumeration is indistinguishable from a healthy
    all-clear and must FAIL LOUD instead (see module docstring negative-
    spec).
    """
    result = _query_records("goal", "status=active")
    if result["failed"]:
        raise RuntimeError(
            "goal-coverage-scan: records.query --type goal failed — refusing "
            "to render a false all-clear. See the WARNING above for the "
            "underlying transport/op error."
        )
    if not result["records"]:
        raise RuntimeError(
            "goal-coverage-scan: records.query --type goal returned ZERO "
            "active goals. This is a backward-teeth detector — a silently "
            "empty result is indistinguishable from a healthy all-clear and "
            "is refused rather than rendered. If there really are zero "
            "active goals, that is itself notable and should be confirmed "
            "out-of-band, not silently reported by this tool."
        )
    return result["records"]


def _fetch_coverage_for_goal(goal_id):
    """Fetch origin_goal_id-tagged coverage records for one goal id, unioned
    across all COVERAGE_TYPES.

    Returns {"items": list, "queryErrors": int} — items (unioned records)
    plus a count of per-type query failures (distinguishes "confirmed zero
    coverage" from "coverage query degraded" for the caller/renderer).
    """
    where_expr = f"origin_goal_id in ({goal_id})"
    items = []
    query_errors = 0
    for record_type in COVERAGE_TYPES:
        result = _query_records(record_type, where_expr)
        items.extend(result["records"])
        if result["failed"]:
            query_errors += 1
    return {"items": items, "queryErrors": query_errors}


# ---------------------------------------------------------------------------
# CLI argument parser
# ---------------------------------------------------------------------------


def _parse_args(argv):
    """Parse CLI arguments. Hard-errors on any --output / --out flag to
    enforce the read-only contract structurally. Also hard-errors on --root
    (either spelling): the native records.query op self-resolves the repo
    root from cwd and has no root-override parameter, so honouring --root
    is not possible — recognising the flag only to silently no-op it would
    be the exact wrong-answer-quiet failure shape this tool exists to flag
    (see module docstring negative-spec), so it fails loud instead.

    Review: code-reviewer -- Finding 6, 2026-07-22. --format is hard-error
    validated the same way (same exit code, same stderr-then-exit shape) as
    --root/--output: a missing value (--format as the last argv token) or an
    unrecognized value (--format quux) previously fell through silently to
    the "text" default rather than erroring, the one flag in this parser
    without input validation. Valid values text/json are unaffected --
    byte-parity on normal runs is preserved.
    """
    fmt = "text"
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--format":
            if i + 1 >= len(argv):
                sys.stderr.write(
                    "ERROR: --format requires a value (text or json).\n"
                )
                sys.exit(2)
            fmt = argv[i + 1]
            i += 2
            continue
        if arg.startswith("--format="):
            fmt = arg[len("--format="):]
            i += 1
            continue
        if arg == "--root" or arg.startswith("--root="):
            sys.stderr.write(
                "ERROR: goal-coverage-scan does not support --root — the native "
                "records.query op self-resolves the repo root from cwd and has no "
                "root-override parameter, so this flag cannot be honoured.\n"
                "       cd to the target repo and re-run without --root.\n"
            )
            sys.exit(2)
        if arg.startswith("--output") or arg.startswith("--out=") or arg == "--out":
            # Structural backstop: reject any attempt to specify an output path.
            sys.stderr.write(
                "ERROR: goal-coverage-scan is a read-only surface — --output is not supported.\n"
                "       Output is written to stdout only.\n"
            )
            sys.exit(2)
        i += 1
    if fmt not in ("text", "json"):
        sys.stderr.write(
            f"ERROR: --format must be 'text' or 'json' (got: {fmt!r}).\n"
        )
        sys.exit(2)
    return {"format": fmt}


# ---------------------------------------------------------------------------
# Text renderer
# ---------------------------------------------------------------------------


def render_text(coverage):
    """Render per-goal coverage as human-readable text, for a ceremony to
    surface and a PM to action. Zero-coverage goals are flagged distinctly
    so they stand out from covered goals in the output. Goals with
    queryErrors > 0 are flagged distinctly (DEGRADED, not ZERO COVERAGE) and
    a scan-level total is printed so an operator can tell "confirmed zero
    coverage" from "coverage query degraded".
    """
    if not coverage:
        return "No active goals found (state/goals/*.yaml).\n"

    lines = []
    zero_coverage_goals = [c for c in coverage if c["zeroCoverage"] and not c["queryErrors"]]
    degraded_goals = [c for c in coverage if c["queryErrors"]]
    total_query_errors = sum(c.get("queryErrors") or 0 for c in coverage)

    for c in coverage:
        if c["queryErrors"]:
            n = c["queryErrors"]
            flag = f" [DEGRADED — {n} coverage-type quer{'y' if n == 1 else 'ies'} failed]"
        elif c["zeroCoverage"]:
            flag = " [ZERO COVERAGE]"
        else:
            flag = ""
        lines.append(f"GOAL: {c['title'] or c['goalId']}{flag}")
        lines.append(f"  id: {c['goalId']}")
        lines.append(f"  path: {c['path']}")
        lines.append(f"  coverage: {c['count']}")
        for item in c["items"]:
            lines.append(f"  - {item['path']} ({item['type']})")
        lines.append("")

    if zero_coverage_goals:
        lines.append(f"{len(zero_coverage_goals)} zero-coverage active goal(s):")
        for c in zero_coverage_goals:
            lines.append(
                f"  - {c['title'] or c['goalId']} ({c['goalId']}) — no in-flight work. "
                "Spin off a stub? (routes to /spinoff or /roadmap-planning)"
            )
        lines.append("")

    if degraded_goals:
        lines.append(
            f"{len(degraded_goals)} goal(s) with degraded coverage queries "
            "(do NOT treat as confirmed zero-coverage):"
        )
        for c in degraded_goals:
            lines.append(
                f"  - {c['title'] or c['goalId']} ({c['goalId']}) — {c['queryErrors']} of "
                f"{len(COVERAGE_TYPES)} coverage-type queries failed; see stderr WARNINGs."
            )
        lines.append("")

    if total_query_errors > 0:
        lines.append(f"Scan-level query errors: {total_query_errors} (see stderr WARNINGs above).")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main(argv=None) -> int:
    opts = _parse_args(sys.argv[1:] if argv is None else argv)

    try:
        goals = _fetch_active_goals()
    except RuntimeError as exc:
        sys.stderr.write(f"{exc}\n")
        return 1

    coverage = compute_coverage(goals, _fetch_coverage_for_goal)

    if opts["format"] == "json":
        sys.stdout.write(json.dumps(coverage, indent=2, ensure_ascii=False) + "\n")
    else:
        sys.stdout.write(render_text(coverage))
    return 0


if __name__ == "__main__":
    sys.exit(main())
