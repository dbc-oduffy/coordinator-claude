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
forwarder; see that file. The engine root is resolved via cc_invoke's
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

def _bootstrap_repo_root() -> Path:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_colocated_engine_on_path

    try:
        return Path(require_colocated_engine_on_path(__file__))
    except RuntimeError as _exc:
        print(f"{Path(__file__).name}: engine-root resolution failed: {_exc}", file=sys.stderr)
        sys.exit(1)


def _sha_shaped_realized_by_values(candidate_paths: list[Path]) -> set[str]:
    from coordinator_core.distill import delete_guard as _delete_guard

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
    repo_root_default = _bootstrap_repo_root()
    from coordinator_core.distill import delete_guard as _delete_guard
    from coordinator_core.distill.delete_guard import DeleteCandidate, evaluate_candidate

    parser = argparse.ArgumentParser(
        description="Run the mechanical delete-safety guards against one or more candidates."
    )
    parser.add_argument("candidates", nargs="+", help="Path(s) to candidate file(s) to evaluate.")
    parser.add_argument(
        "--repo-root",
        type=str,
        default=str(repo_root_default),
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

    candidate_paths = [Path(candidate_arg) for candidate_arg in args.candidates]
    for candidate_path in candidate_paths:
        if not candidate_path.is_file():
            print(f"error: not a file: {candidate_path}", file=sys.stderr)
            return 1

    # `existence_map` (an OPTIONAL parameter on `resolve_realized_by` and its
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
