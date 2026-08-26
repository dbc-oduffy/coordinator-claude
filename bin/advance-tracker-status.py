# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""advance-tracker-status.py — bareword CLI trampoline over tracker.advance_status.

Purpose: `coordinator/skills/enrich-and-review/SKILL.md` (Phase 2.5, 4.5, 6) names
"the advance-tracker-status op — claude-klabauter's `tracker.advance_status`
(`coordinator_core/ops/tracker/advance_status.py`, `register_op
"tracker.advance_status"`)" but, prior to this file, the op had no bareword
`coordinator/bin/` entrypoint to invoke it through — same shape gap
`archive-paper-trail.py`'s own module docstring describes for its op. This file is
that trampoline: single dispatch through `coordinator/bin/lib/cc_invoke.py`'s
`route()` — no shell, no bash re-exec, no local mirror of the tracker-row-resolution
mechanics (those live entirely in `coordinator_core/ops/tracker/advance_status.py`,
reused unchanged by the op).

Usage:
    python3 advance-tracker-status.py --tracker-path <repo-relative-path> \
        --stub-ids <id[,id...]> --to-status <status-text> [<repo_root>]

    --tracker-path  Path to the tracker README, resolved relative to <repo_root>
                     (or absolute, provided it resolves inside <repo_root>).
    --stub-ids      Comma-separated stub ids (e.g. "2A,2B"). At least one required.
    --to-status     Target status text. MUST NOT contain '|' or a newline.
    <repo_root>     Optional positional; defaults to `git rev-parse --show-toplevel`.

Single-call shape (NOT a preview/act dance): tracker.advance_status has no
dry_run — the ALL-OR-NONE per-row resolution IS the safety mechanism (see the op's
own module docstring), so there is nothing a separate preview call would add.

Commit semantics: the op does NOT self-commit (see
coordinator_core/ops/tracker/advance_status.py's "Provisional classification"
section for why) — this trampoline MUST NOT stage/commit either. Landing the
tracker-file change is the caller's (EM's) responsibility, same as every other
op that returns a raw filesystem write.

Exit codes (locally scoped to this CLI, NOT inherited from the op's own response
shape, which carries no error signal of its own on success):
    0 — OK, dispatch succeeded (at least the requested rows resolved; see stdout
        JSON for updated/unchanged/changed).
    2 — usage error (missing/malformed --tracker-path/--stub-ids/--to-status,
        unrecognized extra argument, or repo_root unresolvable).
    3 — transport failure (the engine root unresolvable, coordinator_core.invoke seam
        absent, or the op itself raised — not-found/ambiguous stub_id, tracker_path
        outside the worktree, missing tracker file, malformed to_status).

Spec backlink: DoE-claude coordinator/skills/enrich-and-review/SKILL.md § Phase 2.5/4.5/6
Spec backlink: claude-klabauter coordinator_core/ops/tracker/advance_status.py

Negative-spec: does NOT re-implement row resolution, markdown-table parsing, or the
atomic-write mechanics — those are entirely the op's (`advance_status()` /
`_resolve_targets()`). Does NOT fall back to a legacy shell body on seam-absent —
the op is the only implementation; a seam-absent install is a genuine transport
failure (exit 3), never silently routed to a retired shell body (there never was
one — see the op module docstring's "Prior-art gap" note).
"""
from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
import cc_invoke  # noqa: E402

cc_invoke.ensure_engine_on_path(__file__)

_USAGE_FAIL = 2
_TRANSPORT_FAIL = 3


def _resolve_repo_root(positional: str | None) -> str | None:
    """Repo root — accept as positional arg or resolve from git.

    Returns None (never raises) on resolution failure, mirroring
    archive-paper-trail.py's own posture.
    """
    if positional:
        return positional
    from coordinator_core.git.repo_root import show_toplevel

    return show_toplevel()


def _no_fallback() -> None:
    raise RuntimeError(
        "advance-tracker-status: native seam required (no legacy fallback -- "
        "tracker.advance_status is the only implementation, see module docstring)"
    )


def _usage(prog: str) -> int:
    print(
        f"{prog}: usage: {prog} --tracker-path <path> --stub-ids <id[,id...]> "
        "--to-status <status-text> [<repo_root>]",
        file=sys.stderr,
    )
    return _USAGE_FAIL


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    prog = "advance-tracker-status"

    tracker_path = None
    stub_ids_raw = None
    to_status = None
    positional: list[str] = []

    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok == "--tracker-path" and i + 1 < len(argv):
            tracker_path = argv[i + 1]
            i += 2
        elif tok == "--stub-ids" and i + 1 < len(argv):
            stub_ids_raw = argv[i + 1]
            i += 2
        elif tok == "--to-status" and i + 1 < len(argv):
            to_status = argv[i + 1]
            i += 2
        else:
            positional.append(tok)
            i += 1

    if not tracker_path or not stub_ids_raw or not to_status:
        return _usage(prog)
    if len(positional) > 1:
        print(f"{prog}: unrecognized extra argument(s) {positional[1:]!r}", file=sys.stderr)
        return _usage(prog)

    stub_ids = [s.strip() for s in stub_ids_raw.split(",") if s.strip()]
    if not stub_ids:
        print(f"{prog}: --stub-ids must contain at least one non-empty id", file=sys.stderr)
        return _usage(prog)

    repo_root = _resolve_repo_root(positional[0] if positional else None)
    if repo_root is None:
        print(f"{prog}: cannot resolve git repo root", file=sys.stderr)
        return _usage(prog)

    params = {"tracker_path": tracker_path, "stub_ids": stub_ids, "to_status": to_status}
    try:
        result = cc_invoke.route("tracker.advance_status", params, repo_root, _no_fallback)
    except RuntimeError as exc:
        print(f"{prog}: tracker.advance_status failed (transport error): {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL

    import json

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
