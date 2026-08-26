# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""archive-paper-trail.py — archive a research-session paper-trail workdir via fleet.archive_paper_trail.

Purpose: `coordinator/skills/staff-session/SKILL.md` Step 5 and
`coordinator/commands/notebooklm-research.md`'s paper-trail archive step both
name the `fleet.archive_paper_trail` op
(`coordinator_core/ops/fleet/archive_paper_trail.py`, `register_op
"fleet.archive_paper_trail"`) but, prior to this file, neither had a
bareword `coordinator/bin/` CLI trampoline to invoke it through — the op
module unifies the two call sites' formerly-separate `cp -r` / `git mv`
bodies (see that module's own docstring) but was itself uninvokable outside
a Python REPL. This file is that trampoline: single dispatch through
`coordinator/bin/lib/cc_invoke.py`'s `route()` — no shell, no bash re-exec,
no local mirror of the archive_and_commit git-mv mechanics (those live
entirely in `ops/fleet/_common.py`, reused unchanged by the op).

Usage:
    python3 archive-paper-trail.py --run-id <run-id> --topic-slug <topic-slug> \
        --dry-run {true|false} [<repo_root>]

    <repo_root>  Optional positional; defaults to `git rev-parse --show-toplevel`.

Single-call shape (NOT the two-call preview/act dance sweep-actioned-memos.py
and sweep-terminal-plans.py use for a self-discovered candidate set):
fleet.archive_paper_trail's caller already knows run_id/topic_slug up front
(the skill step that invokes it authored both), so there is no "discover
candidates" call to make first — dry_run is a caller-supplied flag on the
one call, mirroring the op's own preview/act contract.

Commit semantics: the op self-commits (archive_and_commit) on a successful
dry_run:false act — this trampoline MUST NOT stage/commit afterward.

Stdout contract: the op's own JSON result object
({archived, dest, already_archived}) is printed to stdout on success.

Exit codes (locally scoped to this CLI, NOT inherited from the op's own
{archived,dest,already_archived} response shape, which carries no error
signal of its own — see module docstring's Raises note):
    0 — OK, dispatch succeeded (dry-run preview OR a completed/no-op archive).
    2 — usage error (missing --run-id/--topic-slug/--dry-run, malformed
        --dry-run value, or repo_root unresolvable).
    3 — transport failure (the engine root unresolvable, coordinator_core.invoke
        seam absent, or the op itself raised — malformed run_id/topic_slug,
        wrong-typed dry_run reaching the op despite this CLI's own --dry-run
        validation, or repo_root/common_dir mismatch).
    4 — archive degraded: the op returned falsy `archived` alongside a
        non-empty additive `failed` key (per-file git-mv failures inside
        `_common.archive_and_commit` — see
        coordinator_core/ops/fleet/archive_paper_trail.py's `_handler`
        docstring). The op's frozen stdout JSON is still printed byte-for-byte
        (callers parse it); the failure reasons are surfaced separately, to
        stderr, since this CLI's transport dispatch does not raise for this
        case (it is a successful RPC call carrying a failure payload, not a
        transport-level exception).

Spec backlink: DoE-claude coordinator/skills/staff-session/SKILL.md § Step 5
Spec backlink: DoE-claude coordinator/commands/notebooklm-research.md (paper-trail archive step)
Spec backlink: claude-klabauter coordinator_core/ops/fleet/archive_paper_trail.py

Negative-spec: does NOT re-implement dest-path computation, collision
detection, or the atomic-rename mechanics — those are entirely the op's
(`_compute_dest`/`_find_existing_archive`/`_common.archive_and_commit`).
Does NOT fall back to a legacy `cp -r`/`git mv` body on seam-absent — the
op is the only implementation; a seam-absent install is a genuine
transport failure (exit 3), never silently routed to a retired shell body.
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
_ARCHIVE_DEGRADED = 4


def _resolve_repo_root(positional: str | None) -> str | None:
    """Repo root — accept as positional arg or resolve from git.

    Returns None (never raises) on resolution failure, mirroring
    sweep-actioned-memos.py's/sweep-terminal-plans.py's own posture.
    """
    if positional:
        return positional
    from coordinator_core.git.repo_root import show_toplevel

    return show_toplevel()


def _no_fallback() -> None:
    raise RuntimeError(
        "archive-paper-trail: native seam required (no legacy fallback -- "
        "fleet.archive_paper_trail is the only implementation, see module docstring)"
    )


def _parse_bool(tok: str) -> bool | None:
    if tok in ("true", "True", "1"):
        return True
    if tok in ("false", "False", "0"):
        return False
    return None


def _usage(prog: str) -> int:
    print(
        f"{prog}: usage: {prog} --run-id <run-id> --topic-slug <topic-slug> "
        "--dry-run {true|false} [<repo_root>]",
        file=sys.stderr,
    )
    return _USAGE_FAIL


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    prog = "archive-paper-trail"

    run_id = None
    topic_slug = None
    dry_run: bool | None = None
    positional: list[str] = []

    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok == "--run-id" and i + 1 < len(argv):
            run_id = argv[i + 1]
            i += 2
        elif tok == "--topic-slug" and i + 1 < len(argv):
            topic_slug = argv[i + 1]
            i += 2
        elif tok == "--dry-run" and i + 1 < len(argv):
            dry_run = _parse_bool(argv[i + 1])
            if dry_run is None:
                print(f"{prog}: --dry-run must be 'true' or 'false', got {argv[i + 1]!r}", file=sys.stderr)
                return _usage(prog)
            i += 2
        else:
            positional.append(tok)
            i += 1

    if not run_id or not topic_slug or dry_run is None:
        return _usage(prog)
    if len(positional) > 1:
        print(f"{prog}: unrecognized extra argument(s) {positional[1:]!r}", file=sys.stderr)
        return _usage(prog)

    repo_root = _resolve_repo_root(positional[0] if positional else None)
    if repo_root is None:
        print(f"{prog}: cannot resolve git repo root", file=sys.stderr)
        return _usage(prog)

    params = {"run_id": run_id, "topic_slug": topic_slug, "dry_run": dry_run}
    try:
        result = cc_invoke.route("fleet.archive_paper_trail", params, repo_root, _no_fallback)
    except RuntimeError as exc:
        print(f"{prog}: fleet.archive_paper_trail failed (transport error): {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL

    import json

    print(json.dumps(result, indent=2, sort_keys=True))

    # Review: code-reviewer F3 — apply the isinstance guard symmetrically; both
    # reads of `result` share the same dict-or-raise invariant from cc_invoke.route.
    failed = result.get("failed") if isinstance(result, dict) else None
    archived = result.get("archived") if isinstance(result, dict) else None
    if not archived and failed:
        for item in failed:
            print(
                f"{prog}: archive degraded — {item.get('id')}: {item.get('reason')}",
                file=sys.stderr,
            )
        return _ARCHIVE_DEGRADED

    return 0


if __name__ == "__main__":
    sys.exit(main())
