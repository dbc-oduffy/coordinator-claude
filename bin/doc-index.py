"""
coordinator/bin/doc-index.py — operator CLI seam for "docindex.emit"
(coordinator_core/ops/docindex_emit.py).

Purpose: a naked-Python operator command over the "docindex.emit" op — reports
by default and writes only when asked (AC9). Unlike coordinator/bin/cartography.py's
cc_invoke_bare-over-subprocess trampoline (a cross-process transport built for a
DoE-side caller reaching into claude-klabauter), this file is IN-PROCESS: claude-klabauter owns both
the op and this operator surface, so it imports and calls
coordinator_core.ops.docindex_emit's registered handler directly — no subprocess,
no second interpreter spawn, matching AC15's "no per-item process spawn" budget
(the op's own single `git ls-files` call is the only subprocess anywhere in this
invocation).

Usage:
    doc-index.py --target-root <path> [--index-path <repo-relative path>] [--write]

    --target-root <path>  Required. Root of the tree to resolve/discover
                           self-declared indexes under.
    --index-path <path>   Optional. Resolve exactly one index document
                           (repo-relative to --target-root) instead of
                           discovering every self-declared index under the
                           root.
    --write                Optional. Rewrite every resolved index whose
                           comparison is ordinary drift (never a hand-edit).
                           Default: report only, write nothing (AC9).

Output: `json.dumps(result, ensure_ascii=False)` — the bare "docindex.emit"
reply (target_root, results, refused — see docindex_emit.py's module
docstring "Reply fields").

Exit codes:
    0 — success, result printed to stdout.
    1 — client-side usage error (missing --target-root, unknown flag).
    2 — the op raised (target_root outside a git worktree, a refused index
        named in a raised IndexSpecError, `git ls-files` failure, ...); the
        exception message is printed to stderr.

Spec backlink:
  claude-klabauter: docs/plans/2026-08-14-registry-indexes-are-emitted-from-their-directory.md,
                  plan-spine id C3

Negative-spec: no shell trampoline (F16) — a Python entry point with the
`.cmd` sibling its `coordinator/bin/` neighbours carry
(`coordinator/bin/doc-index.cmd`), never a bash wrapper.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from coordinator_core.ops.docindex_emit import _docindex_emit  # noqa: E402


def _parse_argv(argv: list[str]) -> dict:
    params: dict = {}
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--target-root":
            i += 1
            if i >= len(argv):
                raise ValueError("--target-root requires a value")
            params["target_root"] = argv[i]
        elif arg == "--index-path":
            i += 1
            if i >= len(argv):
                raise ValueError("--index-path requires a value")
            params["index_path"] = argv[i]
        elif arg == "--write":
            params["write"] = True
        else:
            raise ValueError(f"unknown argument: {arg!r}")
        i += 1
    return params


def main(argv: list[str]) -> int:
    try:
        params = _parse_argv(argv)
    except ValueError as e:
        print(f"[doc-index] usage error: {e}", file=sys.stderr)
        return 1

    if not params.get("target_root"):
        print("[doc-index] usage error: --target-root is required", file=sys.stderr)
        return 1

    try:
        result = _docindex_emit(params, repo_root=None)
    except Exception as e:  # noqa: BLE001 — a client-facing CLI names any op failure
        print(f"[doc-index] docindex.emit failed: {e}", file=sys.stderr)
        return 2

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
