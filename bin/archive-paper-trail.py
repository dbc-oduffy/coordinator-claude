# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
from __future__ import annotations

import os
import sys

_USAGE_FAIL = 2
_TRANSPORT_FAIL = 3
_ARCHIVE_DEGRADED = 4


def _resolve_repo_root(positional: str | None) -> str | None:
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
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    import cc_invoke

    cc_invoke.ensure_engine_on_path(__file__)

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
