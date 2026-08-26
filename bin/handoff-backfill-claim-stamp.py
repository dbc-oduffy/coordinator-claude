"""handoff-backfill-claim-stamp — CLI trampoline over the engine-repo's
`handoff.backfill_claim_stamp` op.

Invoke as `python3 coordinator/bin/handoff-backfill-claim-stamp.py` (or via
the co-located `.cmd` launcher on Windows) — no shebang / exec bit on this
file (new-file zero-budget ratchet: env_shebang; see
`nudge-new-file-zero-budget-ratchets.py`).

Purpose: forwarder for the operator verb that reconstructs a missing claim
stamp (`claimed_at`/`claimed_by`) on a handoff that was worked but never
formally claimed — see the op module's own docstring
(`coordinator_core/ops/handoff_backfill_claim_stamp.py`) and
docs/plans/2026-08-11-a-claim-stamp-backfill-verb-and-the-lega.md for the
full gap this closes. Windows is first-class here, same as every other
`handoff-*` entry point in this directory: this file ships with a co-located
`.cmd` launcher.

Call shape (one handoff per call, mirroring the sibling
`handoff-reconcile-close-terminal.py`'s single-handoff contract):

    handoff-backfill-claim-stamp.py <handoff-path> \\
        --evidence-commit <sha> [--evidence-commit <sha>]... \\
        [--attested-by <session-id>]

`--evidence-commit` is required at least once; the op verifies every SHA
resolves in this repo (`git cat-file -e`) and refuses with no write on any
that does not. `--attested-by` defaults to the op's own session resolution
when omitted.

Self-verification (same contract as the sibling
`handoff-reconcile-close-terminal.py`'s post-write re-read): a mutation CLI
that cannot confirm its own write must never exit 0. After the op reports
success (and unless this call landed the AC4 idempotent no-op), this
re-reads `claimed_at`/`claimed_by` FROM DISK and asserts both are now
non-empty before returning 0 — the op's `applied: True` self-report alone is
not taken as proof.

Repo root resolves from the target handoff's own directory
(`git -C <dirname(handoff_path)> rev-parse --show-toplevel`), not the
process cwd — same technique as `handoff-reconcile-close-terminal.py`.

Exit codes:
    0 — `claimed_at`/`claimed_by` confirmed non-empty on disk after a fresh
        write, OR the call was the AC4 idempotent no-op (already
        claimed-or-shipped).
    1 — op-level refusal (RouteMutationError with a non-2 envelope), a
        transport/engine failure, an unresolvable repo root, or a post-write
        re-read that does NOT show both fields populated.
    2 — usage error: missing handoff-path or --evidence-commit, or the op's
        own usage refusal (envelope exit_code 2, e.g. an unresolvable
        --attested-by).

Negative-spec:
    - Does NOT write a claim-ledger entry — the op it forwards to is
      frontmatter-only by design (see that module's own negative-spec).
    - Does NOT introduce a new frontmatter key — the op writes only
      `claimed_at`/`claimed_by`/`status_reason` (an existing schema field).
    - Does NOT open a UDS socket or read an auth token — routes through
      `cc_invoke.route_mutation()`, a command-type transport, same as every
      other bin/ CLI in this house style.
    - Does NOT batch — one handoff per call.

Spec backlink: pln-a-claim-stamp-backfill-verb-an-a345d2,
chunk C1.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

_BIN_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(_BIN_DIR, "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
import cc_invoke  # noqa: E402

PROG = "handoff-backfill-claim-stamp.py"

_OP = "handoff.backfill_claim_stamp"


def _no_console_kw() -> dict:
    """Lazily resolve the engine root onto sys.path (self-location-first via
    cc_invoke.ensure_engine_on_path), then splat the canonical
    no-console-window kwarg. ``{}`` on any resolution/import failure
    (fail-open). Mirrors handoff-reconcile-close-terminal.py's own helper."""
    try:
        if cc_invoke.ensure_engine_on_path(__file__) is None:
            return {}
        from coordinator_core.win_portability import no_console_creationflags

        return no_console_creationflags()
    except Exception:
        return {}


def _no_fallback():
    raise RuntimeError(
        f"{PROG}: {_OP} requires the native seam (no bash fallback -- big-bang "
        "cutover); re-run the engine install step or verify COORDINATOR_ENGINE_ROOT"
    )


def _resolve_repo_root(handoff_path: str) -> str | None:
    """Resolve repo root from the handoff's own directory, not the process
    cwd (mirrors handoff-reconcile-close-terminal.py::_resolve_repo_root)."""
    handoff_abs = os.path.abspath(handoff_path)
    if cc_invoke.ensure_engine_on_path(__file__) is None:
        return None
    from coordinator_core.git.repo_root import show_toplevel

    return show_toplevel(cwd=os.path.dirname(handoff_abs))


def _reread_claim_fields(handoff_path: str) -> "tuple[str | None, str | None]":
    """Read `claimed_at`/`claimed_by` straight off disk — the independent-of-
    the-envelope confirmation this CLI's exit 0 rests on. Returns
    `(claimed_at, claimed_by)`, either/both None when unreadable, absent, or
    carrying no frontmatter."""
    from coordinator_core.frontmatter.primitives import read_fm_field_unquoted, split_frontmatter

    try:
        text = Path(handoff_path).read_text(encoding="utf-8")
    except OSError:
        return None, None
    split = split_frontmatter(text)
    if split is None:
        return None, None
    return (
        read_fm_field_unquoted(split.fm_text, "claimed_at"),  # dr084: confirms THIS CLI's own new-vocabulary write, not a mixed-corpus dual-read
        read_fm_field_unquoted(split.fm_text, "claimed_by"),  # dr084: confirms THIS CLI's own new-vocabulary write, not a mixed-corpus dual-read
    )


def cmd_backfill_claim_stamp(
    handoff_path: str, evidence_commits: list[str], attested_by: str
) -> int:
    """Dispatch + confirm. Every return is a promise about the mutation: 0
    means `claimed_at`/`claimed_by` are CONFIRMED non-empty on disk (or the
    call was the AC4 idempotent no-op); non-zero means it is not, whatever
    the op envelope claimed."""
    if not handoff_path.strip():
        print(f"{PROG}: <handoff-path> is required", file=sys.stderr)
        return 2
    if not evidence_commits:
        print(
            f"{PROG}: at least one --evidence-commit <sha> is required",
            file=sys.stderr,
        )
        return 2

    repo_root = _resolve_repo_root(handoff_path)
    if not repo_root:
        print(
            f"{PROG}: cannot resolve git repo root from {handoff_path!r}'s "
            "directory — no mutation attempted",
            file=sys.stderr,
        )
        return 1

    params: dict = {"handoff_path": handoff_path, "evidence_commit": list(evidence_commits)}
    if attested_by.strip():
        params["attested_by"] = attested_by.strip()

    try:
        result = cc_invoke.route_mutation(_OP, params, repo_root, _no_fallback)
    except cc_invoke.RouteMutationError as exc:
        envelope = getattr(exc, "result", None)
        if isinstance(envelope, dict) and envelope.get("exit_code") == 2:
            print(f"{PROG}: usage error from {_OP}: {exc}", file=sys.stderr)
            return 2
        print(f"{PROG}: {_OP} refused for {handoff_path!r} — {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(
            f"{PROG}: {_OP} failed for {handoff_path!r} — transport/engine "
            f"failure: {exc}",
            file=sys.stderr,
        )
        return 1

    if not isinstance(result, dict):
        print(
            f"{PROG}: {_OP} returned an unexpected non-dict result: {result!r}",
            file=sys.stderr,
        )
        return 1

    if result.get("already_claimed_or_shipped"):
        print(
            f"{PROG}: {result.get('message') or f'{handoff_path} already claimed_or_shipped — no-op'}",
            file=sys.stderr,
        )
        return 0

    # Never trust the envelope alone: re-read from disk.
    claimed_at, claimed_by = _reread_claim_fields(handoff_path)
    if not claimed_at or not claimed_by:
        print(
            f"{PROG}: {handoff_path}: expected claimed_at/claimed_by to be "
            f"populated after {_OP} (envelope said applied={result.get('applied')!r}), "
            f"re-read found claimed_at={claimed_at!r} claimed_by={claimed_by!r} — "
            "the backfill did not land",
            file=sys.stderr,
        )
        return 1

    print(
        f"{PROG}: {result.get('message') or f'backfilled claim stamp on {handoff_path}'}",
        file=sys.stderr,
    )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=PROG)
    p.add_argument("handoff_path")
    p.add_argument(
        "--evidence-commit",
        action="append",
        default=[],
        dest="evidence_commit",
        help="a commit SHA the op will verify resolves in this repo "
        "(git cat-file -e); repeatable, at least one required",
    )
    p.add_argument(
        "--attested-by",
        dest="attested_by",
        default="",
        help="session id to record as the attesting session; defaults to "
        "the op's own session resolution when omitted",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        args = _build_parser().parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 2

    return cmd_backfill_claim_stamp(args.handoff_path, args.evidence_commit, args.attested_by)


if __name__ == "__main__":
    sys.exit(main())
