#!/usr/bin/env python3
"""bug-backlog-reap — run every open tf backlog row's member tests and close the green rows.

Usage: `bug-backlog-reap --repo <root> [--budget SECONDS]`. Runs no model: batched pytest over the
member tests, closes all-green rows (`closed_by: bug-backlog-reap`), rewrites the reap record after
every chunk, and prints one line: `closed N, red M, unrun K, <record path>`. A rerun at the same
HEAD skips rows already verdicted; `--budget` (default 420) stops between chunks and records the
remaining rows unrun `budget`. Exit: 0 on a written record, 1 otherwise, 2 usage.
"""
from __future__ import annotations

import math
import sys


def _import_reap():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    require_dispatch_engine_on_path()
    from coordinator_core.bug_blitz.reap_green import main

    return main


def _parse(args: "list[str]") -> "tuple[str, str | None] | None":
    """(repo, budget text or None) from `--repo R` / `--repo=R` and optional `--budget S` / `--budget=S`."""
    values: dict[str, str] = {}
    rest = list(args)
    while rest:
        arg = rest.pop(0)
        name, eq, value = arg.partition("=")
        if name not in ("--repo", "--budget"):
            return None
        if not eq:
            if not rest:
                return None
            value = rest.pop(0)
        values[name] = value
    repo = values.get("--repo")
    return (repo, values.get("--budget")) if repo else None


def main(argv: "list[str] | None" = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if any(a in ("-h", "--help") for a in args):
        print((__doc__ or "").strip())
        return 0
    parsed = _parse(args)
    if parsed is None:
        print("usage: bug-backlog-reap --repo <root> [--budget SECONDS]", file=sys.stderr)
        return 2
    repo, budget = parsed
    if budget is not None:
        try:
            finite = math.isfinite(float(budget)) and float(budget) >= 0
        except ValueError:
            finite = False
        if not finite:
            print("usage: bug-backlog-reap --repo <root> [--budget SECONDS]", file=sys.stderr)
            return 2
    try:
        run = _import_reap()
    except (RuntimeError, ImportError) as exc:
        print(f"bug-backlog-reap: engine unavailable: {exc}", file=sys.stderr)
        return 1
    try:
        return run([repo] if budget is None else [repo, "--budget", budget])
    except Exception as exc:  # noqa: BLE001 — any failure is exit 1; rows finished before it stay recorded
        print(f"bug-backlog-reap: failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
