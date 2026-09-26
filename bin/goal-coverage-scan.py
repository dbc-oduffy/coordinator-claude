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

Spec backlink: DoE-claude:pln-close-the-weekly-goal-loop-yam-d31316 § C5 (AC5);
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


# CURRENTLY WIRED: only `handoff` — handoff.schema.json declares
# FORWARD-LOOKING / INERT: `plan`, `debt`, `bug`, `improvement` are named in
COVERAGE_TYPES = ["handoff", "plan", "debt", "bug", "improvement"]


def compute_coverage(goals, lookup_coverage):
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


def _query_records(record_type, where_expr):
    import lib  # noqa: F401 — no-op via main()'s bootstrap; carries the direct-
    from records_query import query_records

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


def _parse_args(argv):
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


def _bootstrap_query_records() -> None:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    import records_query  # noqa: F401


def main(argv=None) -> int:
    _bootstrap_query_records()
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
