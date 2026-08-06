#!/usr/bin/env python3
# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""coordinator-write-review-trail.py — native review_trail.write trampoline (DR-216 strang-10).

Purpose: routes review_trail.write unconditionally through the claude-klabauter native op
(coordinator_core/ops/review_trail_write.py) via cc_invoke.route_mutation() —
shape-(b) per-op Python trampoline (Windows de-bash campaign, 2026-07-19).
FINISH-STRANGLER: no bash legacy_fn fallback — a missing/broken seam raises
(RouteMutationError or RuntimeError), never falls back to a legacy write.

Same CLI contract, same exit-code contract, pure
Python entry (`python coordinator-write-review-trail.py ...`), no
`#!/bin/sh` polyglot header, no bash re-wrap.

Spec backlink: docs/plans/2026-07-06-dr215-fleet-ops-ceremony-wiring.md (strang-10 C5)
Spec backlink: docs/plans/2026-07-15-bash-to-naked-python-engine-migration.md § T2 (AC4)
Spec backlink: docs/plans/2026-07-19-debash-coordinator-windows.md (Wave 1b, shape-(b))

Usage (unchanged from the bash facade — zero caller-contract drift):
    python coordinator-write-review-trail.py \\
        --sha-range A..B \\
        --reviewer code-reviewer|the Staff Engineer|code-reviewer+the Staff Engineer|waived|ubt-compile|wsc-auto-adjudication \\
        --scope chain|session|workstream-close-auto \\
        --verdict ok|warn|blocked|waived|pending \\
        --diff-loc <integer> \\
        [--scope-kind diff|plan|integration] \\
        [--workstream <slug>]

    ``--workstream`` (2026-07-27, § C4) states the workstream explicitly, taking
    precedence over ``COORDINATOR_REVIEW_WORKSTREAM`` and the op's own
    claimed-handoff scan; omit it to fall back to those, and ultimately to null.

Exit codes:
    0 — success (native op succeeded; bare result JSON printed to stdout)
    1 — missing required arg (facade-side presence gate, unchanged from the bash oracle),
        or an incoherent reviewer/verdict pair (§ C14 cross-field gate below —
        reviewer='waived' XOR verdict='waived')
    2 — native op: post-spawn transport failure or op-level refusal (fail-closed,
        including seam-absent — there is no legacy fallback)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR / "lib"))

import cc_invoke  # noqa: E402  (path insert above must precede this import)


def _resolve_repo_root() -> str:
    """Resolve the git repo root from cwd — parity with the bash oracle's
    ``git -C "$PWD" rev-parse --show-toplevel``.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", os.getcwd(), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired):
        proc = None
    if proc is None or proc.returncode != 0 or not proc.stdout.strip():
        print(
            f"coordinator-write-review-trail.py: cannot resolve git repo root from {os.getcwd()}",
            file=sys.stderr,
        )
        sys.exit(1)
    return proc.stdout.strip()


_PLAN_REVIEW_PATH_PREFIXES = (
    "docs/plans/", "docs/research/", "docs/problems/",
    "state/plan-sidecars/", "state/subagent-share/",
)
_PLAN_REVIEW_MARKER_PREFIXES = ("docs/plans/", "docs/research/", "docs/problems/", "state/plan-sidecars/")


def _diff_touched_paths(sha_range: str, repo_root: str) -> list[str] | None:
    """Return the paths touched by *sha_range*, or ``None`` on any git failure
    (unresolvable/synthetic range — e.g. unit-test fixture shas). ``None`` is
    the caller's cue to fall back to the pre-existing default, never raise.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", repo_root, "diff", "--name-only", sha_range],
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    paths = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    return paths


def _is_plan_review_integration(sha_range: str, repo_root: str) -> bool:
    """AC9's producer predicate — the review-integration path already writes
    ``state/plan-sidecars/<slug>.*.md`` (and ``state/subagent-share/*``)
    alongside the plan's own ``docs/plans/<slug>.md``, or planning/research
    prose under ``docs/research/`` or ``docs/problems/``; a commit whose full
    diff lives inside that surface, touching at least one plan-review marker
    path, is a plan-review integration rather than a code commit.

    Marker prefixes are kept on parity with the coverage-gate classifier's
    ``_PLANNING_ARTIFACT_PATH_PREFIXES`` (coordinator_core/coverage.py) —
    docs/plans/, docs/research/, docs/problems/, state/plan-sidecars/ all
    mark a commit as planning; ``state/subagent-share/`` stays envelope-only
    (allowed in the diff, never a marker by itself) so a subagent-share-only
    commit still falls through to the pre-existing ``diff`` default.

    Negative spec: a mixed commit that also touches code paths is NOT a plan
    review by this predicate — it falls through to the pre-existing default
    (``diff``), same as before this producer existed. This predicate is
    deliberately narrower than C2's classifier (out of scope here, § C9
    dispatch brief) — it exists only to gate this facade's own auto-default,
    not to relabel the coverage gate's partition.
    """
    paths = _diff_touched_paths(sha_range, repo_root)
    if not paths:
        return False
    if not all(p.startswith(_PLAN_REVIEW_PATH_PREFIXES) for p in paths):
        return False
    return any(p.startswith(_PLAN_REVIEW_MARKER_PREFIXES) for p in paths)


def _plan_scope_kind_already_recorded(sha_range: str, repo_root: str) -> bool:
    """Idempotency guard: dedupe on the (scope_kind=plan, sha_range) pair.

    Re-integrating the same plan review must not mint a second credit
    record — scans the on-disk trail directly (the native op has no
    "does this already exist" query surface) rather than re-deriving state
    this facade does not own.
    """
    trail_dir = Path(repo_root) / "state" / "review-trail"
    if not trail_dir.is_dir():
        return False
    # Review: code-reviewer — skip dotfiles (e.g. `.weekly-reviewer-scopes.json`)
    # explicitly: pathlib's `*.json` glob, unlike a shell glob, DOES match
    # leading-dot names, so every non-record sidecar in this dir was being
    # read+json.loads'd on every dedupe check for no benefit (its
    # `.get("scope_kind")` never matches `"plan"`). Correctness was already
    # fine; this bounds the scan cost to actual review-trail records as the
    # directory grows unboundedly per the repo's own review cadence.
    for entry in trail_dir.glob("*.json"):
        if entry.name.startswith("."):
            continue
        try:
            record = json.loads(entry.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if record.get("scope_kind") == "plan" and record.get("sha_range") == sha_range:
            return True
    return False


def _validate_reviewer_verdict_coherence(reviewer: str, verdict: str) -> None:
    """Cross-field coherence gate (docs/plans/2026-08-05-coverage-gate-planning-
    artifact-class.md § C14, folded from the doe-claude-em memo): `reviewer` and
    `verdict` agree on whether this record is waived, or neither field alone tells
    the truth. The incident record —
    `{"reviewer":"waived","verdict":"pending",...}` — reads as BOTH "no reviewer is
    coming" and "a review is open and will close," a loop nothing will ever close.
    The invariant: `reviewer == 'waived'` iff `verdict == 'waived'` — the only
    coherent shapes are waived/waived, or a real (non-waived) reviewer paired with
    any other verdict, including `pending` (a real reviewer with an open review IS
    a loop that closes when that reviewer reports back — see this module's
    docstring for why `pending` stays writable at all).

    Fails loud (`ValueError`) rather than coercing either field toward the other —
    silently rewriting `pending` to `waived` would mint a waiver nobody decided on,
    which is worse than the mixed record it replaced. Mirrors
    `build_write_review_trail_directive`'s existing `sha_range` guard (same
    fail-loud-not-coerce shape) in
    `coordinator_core/workstream_complete/directives_review.py`.
    """
    if (reviewer == "waived") != (verdict == "waived"):
        raise ValueError(
            f"incoherent reviewer/verdict pair: reviewer={reviewer!r}, verdict={verdict!r} — "
            "reviewer='waived' requires verdict='waived', and verdict='pending' (or any "
            "non-waived verdict) requires a real, non-waived reviewer"
        )


def _no_fallback() -> None:
    """Big-bang cutover: no bash legacy body remains — seam-absent fails loud."""
    raise RuntimeError(
        "review_trail.write: native seam required (no legacy fallback — finish-strangler cutover)"
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="coordinator-write-review-trail.py",
        add_help=False,  # -h left unclaimed, mirrors the bash oracle (no --help handling)
    )
    parser.add_argument("--sha-range", dest="sha_range", default="")
    parser.add_argument("--reviewer", dest="reviewer", default="")
    parser.add_argument("--scope", dest="scope", default="")
    parser.add_argument("--verdict", dest="verdict", default="")
    parser.add_argument("--diff-loc", dest="diff_loc", default="")
    # default=None (not "diff") — a caller that omits --scope-kind entirely
    # gets the auto-detected producer default below; a caller that passes
    # --scope-kind explicitly (including "diff") is honored verbatim and
    # skips auto-detection/dedup entirely (unchanged pre-producer contract).
    parser.add_argument("--scope-kind", dest="scope_kind", default=None)
    parser.add_argument("--workstream", dest="workstream", default=None)
    # The path set the review ACTUALLY covered (e.g. from `freeze-review-diff.py
    # --paths`), so a scope_kind:diff record attests its coverage instead of
    # implying it from the sha_range time window. Without this flag the
    # `reviewed_paths` key the writer and schema both support has no caller that
    # can populate it. Spec: docs/plans/2026-07-27-review-trail-scope-guard.md § C9.
    parser.add_argument(
        "--reviewed-paths", dest="reviewed_paths", nargs="*", default=None,
    )
    args, _unknown = parser.parse_known_args(argv)

    # Required-arg presence gate: exit 1 on any missing required arg (unchanged
    # facade-side contract — enum validation is delegated to the native op).
    missing = []
    if not args.sha_range:
        missing.append("--sha-range")
    if not args.reviewer:
        missing.append("--reviewer")
    if not args.scope:
        missing.append("--scope")
    if not args.verdict:
        missing.append("--verdict")
    if not args.diff_loc:
        missing.append("--diff-loc")
    if missing:
        print(
            f"coordinator-write-review-trail: missing required args: {' '.join(missing)}",
            file=sys.stderr,
        )
        return 1

    try:
        _validate_reviewer_verdict_coherence(args.reviewer, args.verdict)
    except ValueError as exc:
        print(f"coordinator-write-review-trail.py: {exc}", file=sys.stderr)
        return 1

    workstream = args.workstream or os.environ.get("COORDINATOR_REVIEW_WORKSTREAM", "") or None

    repo_root = _resolve_repo_root()

    # AC9 producer (docs/plans/2026-08-05-coverage-gate-planning-artifact-class.md
    # § C9): an explicit --scope-kind is honored verbatim, unchanged from the
    # pre-producer contract. Only the OMITTED case is newly auto-derived —
    # a plan-review-integration diff now defaults to "plan" instead of
    # always falling to "diff"; a duplicate plan-review sha_range is a
    # deliberate no-op (idempotent — no second credit record minted).
    scope_kind = args.scope_kind
    if scope_kind is None:
        if _is_plan_review_integration(args.sha_range, repo_root):
            if _plan_scope_kind_already_recorded(args.sha_range, repo_root):
                print(json.dumps({
                    "skipped": True,
                    "reason": "scope_kind=plan trail record already exists for this sha_range",
                    "sha_range": args.sha_range,
                }))
                return 0
            scope_kind = "plan"
        else:
            scope_kind = "diff"

    params = {
        "sha_range": args.sha_range,
        "reviewer": args.reviewer,
        "scope": args.scope,
        "verdict": args.verdict,
        "diff_loc": args.diff_loc,
        "scope_kind": scope_kind,
        "workstream": workstream,
    }
    if args.reviewed_paths is not None:
        params["reviewed_paths"] = args.reviewed_paths

    try:
        result = cc_invoke.route_mutation(
            "review_trail.write", params, repo_root, _no_fallback
        )
    except cc_invoke.RouteMutationError as exc:
        payload = exc.result if isinstance(exc.result, dict) else {"error": str(exc)}
        print(json.dumps(payload), file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"coordinator-write-review-trail.py: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
