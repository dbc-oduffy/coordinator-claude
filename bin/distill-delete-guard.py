# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
coordinator/bin/distill-delete-guard.py — thin CLI wrapper over
coordinator_core.distill.delete_guard.

Purpose: mechanical implementation of the CLASS-KEYED handoff / cross-repo-memo
delete-safety guards (shipped_in present [handoff-only], status: actioned [memo-only],
active-reference ripgrep, commitment-closure vs state/cross-repo-commitments,
realized_by resolves-on-disk) plus the #12 memory-pointer exclusion. Emits
`{"eligible": bool, "artifact_class": "memo"|"handoff"|null, "blocked_by":
[<guard>, ...]}` per candidate on stdout — the LLM consumer writes the prose
delete-reason; this script never does.

Usage:
    coordinator/bin/distill-delete-guard.py <candidate-path> [<candidate-path> ...]
        [--repo-root <path>] [--basis-ref <ref> [--basis-ref <ref> ...]]

`--basis-ref` may be repeated; it applies to ALL candidates in the invocation (the
one-candidate-per-invocation case is the common shape for this flag). For a batch of
candidates with per-candidate basis refs, invoke once per candidate.

Output (stdout, JSON): a single object when one candidate is given, else a list of
per-candidate objects each carrying its source `path`.

Negative-spec: no LLM calls, no writes — pure mechanical guard evaluation. All logic
lives in coordinator_core.distill.delete_guard; this file is argv/stdout plumbing only.

Relocated from bin/distill-delete-guard.py (DEC-3, 2026-07-23
Claude-klabauter-driven-ceremony-redesign) to coordinator/bin/ conventions — discoverability
(fleet `resolve-claude-klabauter-bin` machinery points at coordinator/bin, not top-level bin/)
plus Windows `.cmd` twin coverage. The old bin/ path is now a thin deprecation
forwarder; see that file. CLAUDE_KLABAUTER_ROOT is resolved via cc_invoke's
resolve_colocated_claude_klabauter_root ladder: this file's own coordinator/bin/ parent-of-
parent location is tried FIRST (self-location, zero external dependency, cannot be
unset) and accepted once it probes as a real claude-klabauter checkout; the machine-local
registry lookup is a fallback reached only if that probe misses (this file has been
published/vendored to a location outside the claude-klabauter checkout).

Spec backlink: pln-distill-ceremony-mechanical-su-1bcb38 § C3
Spec backlink: pln-claude-klabauter-driven-ceremony-redesig-c7fe9a § C6
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_LIB_DIR = str(Path(__file__).resolve().parent / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_colocated_engine_on_path  # noqa: E402

try:
    _REPO_ROOT = Path(require_colocated_engine_on_path(__file__))
except RuntimeError as _exc:
    print(f"{Path(__file__).name}: CLAUDE_KLABAUTER_ROOT resolution failed: {_exc}", file=sys.stderr)
    sys.exit(1)

from coordinator_core.distill import delete_guard as _delete_guard
from coordinator_core.distill.delete_guard import DeleteCandidate, evaluate_candidate


def _sha_shaped_realized_by_values(candidate_paths: list[Path]) -> set[str]:
    """Pre-scan every candidate's `realized_by:` value and return the SHA-shaped
    subset (lower-cased), mirroring `resolve_realized_by`'s own shape dispatch
    (inline sentinel -> skip, SHA-shaped -> collect, path-shaped -> skip) WITHOUT
    re-deriving its resolution semantics — this only classifies shape so the
    batched `_git_objects_exist` primitive (C29) can be warmed with the exact
    set `resolve_realized_by` would otherwise resolve one spawn at a time.

    A candidate that fails to read/parse is silently skipped here (not
    resolved as a SHA) — `evaluate_candidate` re-reads the file itself during
    the real evaluation pass below and is the sole source of truth for
    outcomes; this function only feeds the batch-warm cache."""
    shas: set[str] = set()
    for path in candidate_paths:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        fm_split = _delete_guard.split_frontmatter(text)
        frontmatter_text = fm_split.fm_text if fm_split is not None else ""
        value = _delete_guard.read_fm_field_unquoted(frontmatter_text, "realized_by")
        if not value:
            continue
        value = value.strip()
        if value in _delete_guard._INLINE_SENTINELS:
            continue
        lowered = value.lower()
        if _delete_guard._FULL_SHA_RE.match(lowered) or _delete_guard._SHORT_SHA_RE.match(lowered):
            shas.add(lowered)
    return shas


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the mechanical delete-safety guards against one or more candidates."
    )
    parser.add_argument("candidates", nargs="+", help="Path(s) to candidate file(s) to evaluate.")
    parser.add_argument(
        "--repo-root",
        type=str,
        default=str(_REPO_ROOT),
        help="Repo root for active-reference scope, commitment-closure, and git resolution (default: this repo).",
    )
    parser.add_argument(
        "--basis-ref",
        action="append",
        default=[],
        help="A delete-eligibility basis reference (repeatable). Applied to all candidates.",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    basis_refs = tuple(args.basis_ref)

    # Review: code-reviewer (Finding 8, 2026-07-12) — validate ALL candidate paths
    # up front, before running any guard. Previously a bad path at position k>1
    # discarded already-computed results for candidates 1..k-1 (the function
    # returned before reaching json.dump). Validating up front means one typo'd
    # path in a batch never throws away already-computed work.
    candidate_paths = [Path(candidate_arg) for candidate_arg in args.candidates]
    for candidate_path in candidate_paths:
        if not candidate_path.is_file():
            print(f"error: not a file: {candidate_path}", file=sys.stderr)
            return 1

    # Batch-warm the git-object-existence prefetch: one `git cat-file --batch-check`
    # spawn (C29's `_git_objects_exist`) for the SHA-shaped `realized_by:` subset
    # across ALL candidates, instead of one `_git_object_exists` spawn per
    # candidate inside `resolve_realized_by`. Inline sentinels and path-shaped
    # values never spawn git either way (see the docstring on
    # `_sha_shaped_realized_by_values`) — this only reduces the SHA-shaped
    # subset, conditionally, per candidate corpus composition. Passed down as
    # `existence_map` (an OPTIONAL parameter on `resolve_realized_by` and its
    # callers, C31) — a miss in the map still falls through to the scalar
    # `_git_object_exists`, never treated as "does not exist" (see that
    # function's docstring for the fail-closed-on-miss contract).
    shas = _sha_shaped_realized_by_values(candidate_paths)
    existence_map = _delete_guard._git_objects_exist(list(shas), repo_root)

    results = []
    for candidate_path in candidate_paths:
        candidate = DeleteCandidate(
            path=candidate_path,
            repo_root=repo_root,
            basis_refs=basis_refs,
        )
        outcome = evaluate_candidate(candidate, existence_map=existence_map)
        outcome["path"] = str(candidate_path)
        results.append(outcome)

    payload = results[0] if len(results) == 1 else results
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
