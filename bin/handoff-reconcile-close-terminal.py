"""handoff-reconcile-close-terminal — CLI trampoline over the engine-repo's
`handoff.reconcile_close_terminal` op.

Invoke as `python3 coordinator/bin/handoff-reconcile-close-terminal.py` (or
via the co-located `.cmd` launcher on Windows) — no shebang / exec bit on
this file (new-file zero-budget ratchet: env_shebang; see
`nudge-new-file-zero-budget-ratchets.py`).

Purpose: that op has been registered (`register_op`, `OpClass.MUTATING`,
scoped `common_dir`) since it landed, but carried NO `bin/` forwarder under
any `*reconcile-close*` / `*close-terminal*` naming, so no skill could reach
it — the reconcile-to-terminal ceremony that is its own documented ACTING
CALLER (see the op module's docstring) had to hand-author the stamp instead,
which is exactly the transcription-relocation the north star forbids. This
file is that missing seam.

Call shape (one handoff per call, mirroring the op's own single-handoff
contract):

    handoff-reconcile-close-terminal.py <handoff-path> --reason displaced
        [--exclude <path>]...

`--reason` is threaded verbatim to the op, which validates it against
`handoff_transition._CLOSED_REASONS` ("cancelled" | "displaced" | "stale").
The enum is deliberately NOT re-declared here: a second copy would drift, and
the op's own usage refusal (exit_code 2) is surfaced as this CLI's exit 2, so
a bad value still reads as a usage error at the shell rather than a generic
failure.

Self-verification (same contract as the sibling
`handoff-archive-transition.py`'s `cmd_supersede`/`cmd_chain`): a mutation
CLI that cannot confirm its own write must never exit 0. After the op reports
success, this re-reads the target's frontmatter FROM DISK — following the
file into `archive/handoffs/YYYY-MM/` when the archival move happened — and
asserts `deployment_state: closed` actually landed before returning 0. The
op's `closed: True` self-report alone is not taken as proof.

Repo root resolves from the target handoff's own directory
(`git -C <dirname(handoff_path)> rev-parse --show-toplevel`), not the process
cwd — same technique as `handoff-archive-transition.py::_resolve_repo_root`.

Exit codes:
    0 — `deployment_state: closed` confirmed on disk, whether the archival
        move landed, was retained by the live-children guard (retention is
        NOT failure — the status flip is not gated on it), or the call was an
        idempotent replay against an already-closed+archived handoff.
    1 — op-level refusal (RouteMutationError with a non-2 envelope), a
        transport/engine failure, an unresolvable repo root, or a post-write
        re-read that does NOT show `deployment_state: closed`.
    2 — usage error: missing handoff-path or --reason, or the op's own
        usage refusal (envelope exit_code 2, e.g. a `reason` outside
        `_CLOSED_REASONS`).

Negative-spec:
    - Does NOT decide whether the baton's next-steps are genuinely closed
      elsewhere — that judgment stays with the caller, exactly as the op's
      own negative-spec states. This CLI supplies no default `--reason`.
    - Does NOT open a UDS socket or read an auth token — routes through
      `cc_invoke.route_mutation()`, a command-type transport, same as every
      other bin/ CLI in this house style.
    - Does NOT re-declare `_CLOSED_REASONS` (see above), and does NOT
      pre-validate `reason` against a local copy.
    - Does NOT batch — one handoff per call.

Spec backlink: the two cross-repo memos under `cross-repo/inbox/` reporting
this gap — 2026-08-05 "reconcile-close-terminal has no forwarder" and
2026-08-08 "handoff seam coverage directive gaps" § "Separate, break-class".
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

PROG = "handoff-reconcile-close-terminal.py"

_OP = "handoff.reconcile_close_terminal"


def _no_console_kw() -> dict:
    """Lazily resolve the engine root onto sys.path (self-location-first via
    cc_invoke.ensure_engine_on_path), then splat the canonical
    no-console-window kwarg. ``{}`` on any resolution/import failure
    (fail-open). Mirrors handoff-archive-transition.py's own helper."""
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
        "cutover); re-run coordinator:install or verify CLAUDE_KLABAUTER_ROOT"
    )


def _resolve_repo_root(handoff_path: str) -> str | None:
    """Resolve repo root from the handoff's own directory, not the process cwd
    (mirrors handoff-archive-transition.py::_resolve_repo_root)."""
    handoff_abs = os.path.abspath(handoff_path)
    if cc_invoke.ensure_engine_on_path(__file__) is None:
        return None
    from coordinator_core.git.repo_root import show_toplevel

    return show_toplevel(cwd=os.path.dirname(handoff_abs))


def _locate_after_archive_move(handoff_path: str, repo_root: str | None) -> str:
    """Where to re-read frontmatter from after a transition that may have
    git-mv'd the handoff into archive/: `handoff_path` itself when the move
    did not happen, or the derived archive/handoffs/YYYY-MM/ destination when
    it did. Falls back to `handoff_path` verbatim when `repo_root` is falsy —
    the re-read then fails closed via `_reread_deployment_state`'s own OSError
    handling, not via a path this function guesses at.

    Same shape as handoff-archive-transition.py's helper of this name and
    `coordinator_core.archive_stamp._locate_after_supersede`."""
    if os.path.exists(handoff_path) or not repo_root:
        return handoff_path
    from coordinator_core.ops.fleet._common import handoff_archive_dest

    dest = handoff_archive_dest(Path(repo_root), Path(handoff_path))
    return str(dest) if dest.exists() else handoff_path


def _reread_deployment_state(current_path: str) -> str | None:
    """Read `deployment_state` straight off disk at `current_path` — the
    independent-of-the-envelope confirmation this CLI's exit 0 rests on.
    Returns None when the file is unreadable or carries no frontmatter; that
    shape reads as a verification failure to the caller, never a silent pass."""
    from coordinator_core.frontmatter.primitives import read_fm_field_unquoted, split_frontmatter

    try:
        text = Path(current_path).read_text(encoding="utf-8")
    except OSError:
        return None
    split = split_frontmatter(text)
    if split is None:
        return None
    return read_fm_field_unquoted(split.fm_text, "deployment_state")


def cmd_reconcile_close(handoff_path: str, reason: str, exclude: list[str]) -> int:
    """Dispatch + confirm. Every return is a promise about the mutation: 0
    means `deployment_state: closed` is CONFIRMED on disk; non-zero means it
    is not, whatever the op envelope claimed.

    The archival move is deliberately NOT part of that promise — the op's
    live-children guard legitimately retains it (`retained: True`) while the
    close still applies, and the idempotent-replay branch reports both as
    already-done. Gating exit 0 on `archived` would turn a correct retention
    into a reported failure, the inverse of the sibling CLI's own
    "retention is NOT failure" negative-spec."""
    if not handoff_path.strip():
        print(f"{PROG}: <handoff-path> is required", file=sys.stderr)
        return 2
    if not reason.strip():
        print(
            f"{PROG}: --reason is required (one of the op's own "
            "handoff_transition._CLOSED_REASONS; 'displaced' is the expected "
            "value for a no-successor reconcile-to-terminal)",
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

    params: dict = {"handoff_path": handoff_path, "reason": reason}
    if exclude:
        params["exclude"] = list(exclude)

    try:
        result = cc_invoke.route_mutation(_OP, params, repo_root, _no_fallback)
    except cc_invoke.RouteMutationError as exc:
        envelope = getattr(exc, "result", None)
        # The op's own usage refusal (a `reason` outside _CLOSED_REASONS, a
        # missing handoff_path) surfaces as exit 2 at the shell rather than a
        # generic failure — that discrimination is why the enum is not
        # re-declared in this file (see module docstring).
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

    # Never trust the envelope alone (sibling CLI's AC3 precedent): re-read
    # from disk, following the file into archive/ when the move landed.
    current = _locate_after_archive_move(handoff_path, repo_root)
    landed_state = _reread_deployment_state(current)
    if landed_state != "closed":
        print(
            f"{PROG}: {handoff_path}: expected deployment_state='closed' after "
            f"{_OP} (envelope said closed={result.get('closed')!r}), re-read "
            f"{current} and found deployment_state={landed_state!r} — the "
            "close did not land",
            file=sys.stderr,
        )
        return 1

    print(f"{PROG}: {result.get('message') or f'closed {handoff_path} (reason: {reason})'}",
          file=sys.stderr)
    if result.get("retained"):
        print(
            f"{PROG}: archival retained — {result.get('retain_reason') or 'live-children guard'} "
            "(the close still applied)",
            file=sys.stderr,
        )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=PROG)
    p.add_argument("handoff_path")
    p.add_argument(
        "--reason",
        dest="reason",
        default="",
        help=(
            "closed_reason, validated by the op against "
            "handoff_transition._CLOSED_REASONS ('cancelled' | 'displaced' | "
            "'stale'); 'displaced' is the expected value for a no-successor "
            "reconcile-to-terminal"
        ),
    )
    p.add_argument("--exclude", action="append", default=[], dest="exclude")
    return p


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        args = _build_parser().parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 2

    return cmd_reconcile_close(args.handoff_path, args.reason, args.exclude)


if __name__ == "__main__":
    sys.exit(main())
