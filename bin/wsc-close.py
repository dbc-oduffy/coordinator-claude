#!/usr/bin/env python3
# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""wsc-close.py — small `/workstream-complete` Step 3/3.5 mechanics the
`ceremony.wsc_tail` op does not own: caller-side CLI-flag assembly for the
`wsc-tail.py` trampoline call, and the post-commit session-scope archive.

Subcommands
-----------
tail-args
    Assemble the OPTIONAL `--deleted-paths` / `--kept-entries` /
    `--review-*` flags for the `wsc-tail.py` Step 3 call, omitting a flag
    entirely when its backing value is empty/absent. This mirrors bash
    conditional-array logic the DoE-claude `workstream-complete/SKILL.md`
    used to inline (`_deleted_paths_flag` / `_kept_entries_flag` /
    `_review_trail_flags`) — genuinely necessary because `wsc-tail.py`'s own
    `--deleted-paths`/`--kept-entries` argparse flags are `nargs="+"`
    (`coordinator/bin/wsc-tail.py:262-275`): passing the flag bare with zero
    values is an argparse error, not a harmless no-op, so the *caller* must
    omit the flag rather than pass it empty. The five `--review-*` flags are
    all-or-nothing on the caller's own side too (`wsc-tail.py`'s own
    `_missing_review_trail_fields` refuses a partial set at the trampoline
    layer) — `tail-args` mirrors that all-or-nothing composition rather than
    re-deriving it, so a partial `--review-*` supply here fails loud instead
    of silently forwarding a set `wsc-tail.py` would itself reject.

    Emits one argv token per line on stdout, in the order `wsc-tail.py`
    expects them spliced into its own argv (flag name, then its value(s)).
    Newline-delimited rather than NUL-delimited: every value in play here is
    a path, session id, sha range, reviewer name, or verdict — none of which
    is spec'd to legitimately contain a literal newline in this pipeline —
    so plain newline-per-token keeps the caller-side consumption a simple
    `read -r` loop / `$(...)` command-substitution collection without
    requiring the newer `readarray -d ''` bash 4.4+ idiom. This is a
    caller-ergonomics decision, not a security boundary: a path containing
    an embedded newline would misparse and is out of scope for this ceremony
    step's own inputs.

archive-session
    Archive this session's claim directory (`coordinator_core.session.scope
    .archive(sid)`), lifting the `python3 -c` heredoc the SKILL.md's Step 3.5
    used to inline. Idempotent (a missing session dir is treated as
    already-archived) and non-fatal-by-design: a failure here prints a
    diagnostic to stderr but the subcommand exits `0` regardless. `--sid` is
    required (the op's own ``archive()`` raises ``ValueError`` on an empty
    sid; this CLI checks the same precondition before the call so the error
    message names the CLI, not a bare Python traceback).

    Caller: DoE-claude's SessionEnd hook,
    `coordinator/hooks/scripts/sessionend-archive-session.py` (wired via
    `hooks.json`) — the SOLE archival occasion in the system as of
    `e510140a` (`ceremony.wsc_tail`'s own `tail_ops.cs_archive` call site
    was removed; a 24h live-excluding reap in `ops/session/reap.py` is the
    backstop). The `/workstream-complete` Step 3.5 mid-session invocation
    this docstring used to describe no longer exists — do NOT call this
    subcommand mid-session; it must fire only at SessionEnd, after the
    session's own work (including receipt emit and sentinel clear) is done.

Spec backlink: docs/plans/2026-07-23-wsc-tail-slim-down.md (WSC-3 chunk —
port residual bash logic OUT of DoE-claude's `workstream-complete/SKILL.md`
Step 3/3.5 into a naked-Python CLI here).
Spec backlink (source bash this ports): DoE-claude
`coordinator/skills/workstream-complete/SKILL.md` lines ~2085-2099 (tail-arg
assembly) and ~2350-2358 (session-scope archive-on-exit).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_LIB_DIR = str(Path(__file__).resolve().parent / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import resolve_colocated_claude_klabauter_root  # noqa: E402

_REVIEW_TRAIL_FLAGS = (
    "--review-sha-range",
    "--review-reviewer",
    "--review-scope",
    "--review-verdict",
    "--review-diff-loc",
)


def _build_tail_args(
    deleted_paths: list[str] | None,
    kept_entries: list[str] | None,
    review_sha_range: str | None,
    review_reviewer: str | None,
    review_scope: str | None,
    review_verdict: str | None,
    review_diff_loc: str | None,
    review_scope_kind: str | None = None,
) -> list[str]:
    """Pure assembly — no I/O — so the unit test can exercise every branch
    without argv/stdout plumbing. Returns the ordered list of extra argv
    tokens for the `wsc-tail.py` call; raises ValueError on a partial
    `--review-*` supply (see module docstring)."""
    args: list[str] = []

    if deleted_paths:
        args.append("--deleted-paths")
        args.extend(deleted_paths)

    if kept_entries:
        args.append("--kept-entries")
        args.extend(kept_entries)

    review_values = (
        review_sha_range,
        review_reviewer,
        review_scope,
        review_verdict,
        review_diff_loc,
    )
    supplied = [v for v in review_values if v]
    if supplied and len(supplied) != len(review_values):
        missing = [
            flag
            for flag, val in zip(_REVIEW_TRAIL_FLAGS, review_values)
            if not val
        ]
        raise ValueError(
            "partial --review-* supply — all five are required together "
            f"(missing: {', '.join(missing)})"
        )
    if supplied:
        args.extend(["--review-sha-range", review_sha_range])  # type: ignore[list-item]
        args.extend(["--review-reviewer", review_reviewer])  # type: ignore[list-item]
        args.extend(["--review-scope", review_scope])  # type: ignore[list-item]
        args.extend(["--review-verdict", review_verdict])  # type: ignore[list-item]
        args.extend(["--review-diff-loc", review_diff_loc])  # type: ignore[list-item]
        # Optional sixth flag, deliberately OUTSIDE the all-or-nothing five
        # above: `wsc-tail.py` declares it an optional passthrough, so its
        # absence must never trip the partial-supply ValueError.
        if review_scope_kind:
            args.extend(["--review-scope-kind", review_scope_kind])

    return args


def _cmd_tail_args(args: argparse.Namespace) -> int:
    try:
        tokens = _build_tail_args(
            deleted_paths=args.deleted_paths,
            kept_entries=args.kept_entries,
            review_sha_range=args.review_sha_range,
            review_reviewer=args.review_reviewer,
            review_scope=args.review_scope,
            review_verdict=args.review_verdict,
            review_diff_loc=args.review_diff_loc,
            review_scope_kind=args.review_scope_kind,
        )
    except ValueError as exc:
        print(f"wsc-close.py tail-args: {exc}", file=sys.stderr)
        return 1
    for token in tokens:
        print(token)
    return 0


def _cmd_archive_session(args: argparse.Namespace) -> int:
    if not args.sid:
        print("wsc-close.py archive-session: --sid required", file=sys.stderr)
        return 1

    try:
        claude_klabauter_root = resolve_colocated_claude_klabauter_root(__file__)
    except RuntimeError as exc:
        print(
            f"wsc-close.py archive-session: CLAUDE_KLABAUTER_ROOT resolution failed: {exc} "
            "(non-fatal — skipping, per module docstring)",
            file=sys.stderr,
        )
        return 0

    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)

    try:
        from coordinator_core.session.scope import archive
    except ImportError as exc:
        print(
            f"wsc-close.py archive-session: coordinator_core.session.scope not "
            f"importable: {exc} (non-fatal — skipping, per module docstring)",
            file=sys.stderr,
        )
        return 0

    try:
        ok = archive(args.sid)
    except Exception as exc:  # noqa: BLE001 — non-fatal by design, see docstring
        print(
            f"wsc-close.py archive-session: archive({args.sid!r}) raised {exc!r} "
            "(non-fatal — reported, not raised)",
            file=sys.stderr,
        )
        return 0

    if not ok:
        print(
            f"wsc-close.py archive-session: archive({args.sid!r}) returned False "
            "(non-fatal — 24h reaper is the backstop)",
            file=sys.stderr,
        )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wsc-close.py",
        description="workstream-complete Step 3/3.5 mechanics: tail-arg assembly + session-scope archive.",
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    tail_args_p = subparsers.add_parser(
        "tail-args",
        help="Assemble optional --deleted-paths/--kept-entries/--review-* flags for wsc-tail.py.",
    )
    tail_args_p.add_argument("--deleted-paths", dest="deleted_paths", nargs="*", default=None)
    tail_args_p.add_argument("--kept-entries", dest="kept_entries", nargs="*", default=None)
    tail_args_p.add_argument("--review-sha-range", dest="review_sha_range", default=None)
    tail_args_p.add_argument("--review-reviewer", dest="review_reviewer", default=None)
    tail_args_p.add_argument("--review-scope", dest="review_scope", default=None)
    tail_args_p.add_argument("--review-verdict", dest="review_verdict", default=None)
    tail_args_p.add_argument("--review-diff-loc", dest="review_diff_loc", default=None)
    tail_args_p.add_argument("--review-scope-kind", dest="review_scope_kind", default=None)
    tail_args_p.set_defaults(func=_cmd_tail_args)

    archive_session_p = subparsers.add_parser(
        "archive-session",
        help="Archive this session's claim directory (idempotent, non-fatal).",
    )
    archive_session_p.add_argument("--sid", required=True, help="Session id to archive.")
    archive_session_p.set_defaults(func=_cmd_archive_session)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
