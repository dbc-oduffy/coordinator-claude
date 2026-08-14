"""prune-closed-improvements.py — archive closed improvement-queue entries via
fleet.archive_queue_entry.

Sibling of prune-closed-bugs.py, same ceremony shape, adapted for the ONE
structural difference between the two YAML-era ops: fleet.archive_queue_entry
(unlike fleet.prune_closed_bugs) does NOT self-select candidates by
terminality — the caller names every entry to archive (see
ops/fleet/archive_queue_entry.py's own Negative-spec). This script is
therefore the candidate-discovery half fleet.prune_closed_bugs performs
in-process, moved client-side: it reads state/improvement-queue/*.yaml via the
shared queue-family read seam (coordinator_core.ops.queue_family.load_family_records
— never a raw Path.glob/yaml.safe_load, per that module's own Negative-spec) to
find `status: closed` entries, then dispatches the batch form of
fleet.archive_queue_entry (params.entry_paths — see that op's module docstring
§ Batch addition) over the whole set.

Two-call-BATCH shape (2026-08-06, F9 fix — replaces a prior two-call-PER-
CANDIDATE shape that committed once per entry: a 36-entry sweep was 36 commits
racing anything else touching HEAD on this shared worktree, and lost one to
`cannot lock ref 'HEAD': is at ... but expected ...` — see
state/handoffs/2026-08-06-claude-klabauter-dogfood-engine-fixes.md § D):
    Call 1 (whole set): dry_run:true, entry_paths=<every candidate> — preview
        (dest computed per item, no mutation). An item whose preview carries
        an error (path-traversal escape) is dropped with a WARN, never
        silently carried into Call 2.
    Call 2 (previewed set, act mode only): dry_run:false, entry_paths=<the
        previewed subset> — ONE archive_and_commit call for the whole set
        (ONE commit per sweep, not one per entry). Empty candidate set ->
        "nothing to prune", exit 0.

Usage:
    python3 prune-closed-improvements.py [--dry-run] [--repo-root <path>]

    --dry-run    preview only (Call 1 results reported; Call 2 skipped, no git-mv).
    --repo-root  explicit repo root for both the read seam and the git-mv +
                 self-commit (default: the checked resolver's answer,
                 `lib.repo_identity.resolve_checked_repo_root`, from the
                 CALLING process's cwd, falling back to cwd itself) — same
                 data-loss-risk rationale as prune-closed-bugs.py's --repo-root
                 (this op also git-mv's + deletes on the caller's behalf).

Exit codes:
    0 — discovery found nothing to prune, discovery itself failed (transport-
        level, before any mutation was attempted), or every selected entry
        archived cleanly.
    1 — at least one selected entry failed to archive (Call 1 preview error,
        Call 2 per-item failure, or the batch commit itself failing — e.g. a
        `cannot lock ref 'HEAD'` collision) — NEVER swallowed into a WARN-only
        exit 0; the caller must be able to branch on this (F9 fix, second
        half). update-docs-probes.py's queue-prune-sweep leg does not
        currently inspect this process's return code either way (see its
        `_cmd_queue_prune_sweep`), so this change does not newly hard-gate
        /update-docs Phase 11i — it only makes the exit code honest for any
        OTHER caller that does branch on it.

Big-bang cutover (2026-07-19 Windows de-bash campaign, Wave F1 convention):
no legacy bash fallback — the op is assumed present; a genuinely seam-absent
install surfaces as a transport failure (RuntimeError), caught below and
logged, never propagated.

Spec backlink: coordinator/commands/update-docs.md (DoE-claude) § Phase 11i
Spec backlink: docs/decisions/DR-115-queue-shape-is-a-scope-collision-not-a-staleness.md
  (names this exact repoint as "one engine-plane wiring row")
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
import cc_invoke  # noqa: E402
from cc_invoke import route  # noqa: E402
from repo_identity import resolve_checked_repo_root  # noqa: E402

# coordinator_core is co-located in this same repo (the engine plane) --
# resolvable only from the repo root, which is not on sys.path when this
# file is run directly (only its own dir and lib/ are). cc_invoke (imported
# above) already arms sys._coordinator_core_lazy_ops as an import side effect
# (unless an operator explicitly set COORDINATOR_CORE_LAZY_OPS), so the
# queue_family import below skips coordinator_core.ops's ~70ms eager
# op-registration sweep it does not need (it only wants the read seam).
_REPO_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
from coordinator_core.ops.queue_family import load_family_records  # noqa: E402


def _no_fallback() -> None:
    raise RuntimeError(
        "fleet.archive_queue_entry: native seam required (no bash fallback -- big-bang cutover)"
    )


def _resolve_repo_root() -> str:
    """Resolve the repo root via the checked resolver (repo_identity).

    READER classification (DR-277 / plan C5): MISMATCH is advisory only --
    warn to stderr and proceed with the resolved root; UNRESOLVED never
    refuses (AC4). Falls back to os.getcwd() when no root at all resolves,
    preserving this script's pre-existing best-effort behavior.
    """
    root, verdict = resolve_checked_repo_root(explicit_root=None)
    if verdict["verdict"] == "MISMATCH":
        print(verdict["message"], file=sys.stderr)
    return root or os.getcwd()


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    dry_run_only = False
    explicit_repo_root: str | None = None
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--dry-run":
            dry_run_only = True
            i += 1
        elif arg == "--repo-root":
            if i + 1 >= len(argv):
                print("prune-closed-improvements.py: --repo-root requires a value", file=sys.stderr)
                return 0
            explicit_repo_root = argv[i + 1]
            i += 2
        else:
            print(f"prune-closed-improvements.py: unknown arg: {arg}", file=sys.stderr)
            i += 1

    repo_root = explicit_repo_root or _resolve_repo_root()

    try:
        records = load_family_records(
            "improvement-queue", Path(repo_root), where="status = closed"
        )
    except Exception as exc:  # noqa: BLE001 - best-effort ceremony, never propagate
        print(
            f"prune-closed-improvements.py: WARN: closed-entry discovery failed: {exc}",
            file=sys.stderr,
        )
        print("prune-closed-improvements.py: skipping (non-blocking)")
        return 0

    candidate_paths = sorted(
        r["path"] for r in records if isinstance(r, dict) and isinstance(r.get("path"), str)
    )

    if not candidate_paths:
        print("prune-closed-improvements.py: no closed improvement-queue entries found -- nothing to prune")
        return 0

    # ---- Call 1 (whole set): dry_run:true batch preview ----
    try:
        preview = route(
            "fleet.archive_queue_entry",
            {"repo_root": repo_root, "entry_paths": candidate_paths, "dry_run": True},
            repo_root, _no_fallback,
        )
    except RuntimeError as exc:
        print(f"prune-closed-improvements.py: WARN: batch preview failed: {exc}", file=sys.stderr)
        print("prune-closed-improvements.py: skipping (non-blocking)")
        return 0

    preview_items = preview.get("items") if isinstance(preview, dict) else None
    if not preview_items:
        print("prune-closed-improvements.py: WARN: batch preview returned no items", file=sys.stderr)
        return 0

    previewed: list[str] = []
    for item in preview_items:
        if not isinstance(item, dict):
            continue
        if item.get("error"):
            print(
                f"prune-closed-improvements.py: WARN: preview failed for {item.get('id')}: {item['error']}",
                file=sys.stderr,
            )
            continue
        previewed.append(item["id"])

    if not previewed:
        print("prune-closed-improvements.py: all preview items failed -- nothing archived")
        return 0

    if dry_run_only:
        print(
            f"prune-closed-improvements.py: {len(previewed)} closed improvement(s) selected for prune "
            "(--dry-run: no changes made)"
        )
        return 0

    print(f"prune-closed-improvements.py: {len(previewed)} closed improvement(s) selected for prune")

    # ---- Call 2 (previewed set, act mode): dry_run:false batch archive,
    # ONE archive_and_commit call/commit for the whole set (F9 fix). ----
    try:
        act = route(
            "fleet.archive_queue_entry",
            {"repo_root": repo_root, "entry_paths": previewed, "dry_run": False},
            repo_root, _no_fallback,
        )
    except RuntimeError as exc:
        print(f"prune-closed-improvements.py: WARN: batch archive dispatch failed: {exc}", file=sys.stderr)
        print("prune-closed-improvements.py: fleet.archive_queue_entry completed -- 0 entr(ies) archived")
        return 1

    act_items = act.get("items") if isinstance(act, dict) else None
    archived = 0
    failures: list[tuple[str, str]] = []
    for item in act_items or []:
        if not isinstance(item, dict):
            continue
        if item.get("archived"):
            archived += 1
        elif item.get("error"):
            failures.append((item.get("id"), str(item["error"])))
        # archived:False with no error is an idempotent no-op (already
        # archived / concurrent replay) -- not a failure, per
        # archive_queue_entry's own Idempotency (AC7) contract.

    if failures:
        print(
            f"prune-closed-improvements.py: WARN: {len(failures)} entr(ies) failed to archive -- check claude-klabauter logs",
            file=sys.stderr,
        )
        for path, reason in failures:
            print(f"  {path}: {reason}", file=sys.stderr)

    print(f"prune-closed-improvements.py: fleet.archive_queue_entry completed -- {archived} entr(ies) archived")
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # pragma: no cover - best-effort ceremony, never propagate
        print(f"prune-closed-improvements.py: WARN: prune dispatch crashed unexpectedly (non-blocking): {exc}", file=sys.stderr)
        sys.exit(0)
