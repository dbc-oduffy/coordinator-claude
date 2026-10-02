"""query-completion-receipts.py -- the porter over `completion_receipts.collect`.

No shebang line, no exec bit: this is only ever spawned as `python3
query-completion-receipts.py`, never as a bare word (same posture as
`query-completion-rollups.py`).

Purpose: a per-repo, one-process entry point a non-Python caller (project-
Cockpit) can spawn to read the CompletionReceipt records of the invoking
repo, without linking against `coordinator_core`.

`completion_receipts.collect` is an emit *section*, a plain in-process
function with NO registered op behind it, so this file does not use
`op_trampoline.run()`; it reuses `resolve_repo_root_or_exit()` and
`resolve_claude_klabauter_root_or_exit()` and hand-implements the exit-1 diagnostic
convention around its own `collect(ctx)` call.

Every receipt is emitted, superseded ones included (`superseded` is derived
by the reader). A receipt failing the CompletionReceipt entity model is
dropped from the output (the malformed list is not reported, as in
`query-completion-rollups.py`).

Usage:
    python3 query-completion-receipts.py
    python3 query-completion-receipts.py --help

Exit codes:
    0 -- success, the receipt list printed to stdout as JSON.
    1 -- repo-root resolution failure, or any exception raised while
         building the context or calling `collect()`.
    2 -- unrecognized argument (argparse usage error).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_BIN_DIR = os.path.dirname(os.path.abspath(__file__))


_BOOTSTRAPPED_NAMES = ("resolve_claude_klabauter_root_or_exit", "resolve_repo_root_or_exit")


def _bootstrap_op_trampoline() -> None:
    if all(n in globals() for n in _BOOTSTRAPPED_NAMES):
        return

    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from op_trampoline import (
        resolve_claude_klabauter_root_or_exit as _resolve_claude_klabauter_root_or_exit,
        resolve_repo_root_or_exit as _resolve_repo_root_or_exit,
    )

    for _name, _value in (
        ("resolve_claude_klabauter_root_or_exit", _resolve_claude_klabauter_root_or_exit),
        ("resolve_repo_root_or_exit", _resolve_repo_root_or_exit),
    ):
        globals().setdefault(_name, _value)


def __getattr__(name: str):
    if name in _BOOTSTRAPPED_NAMES:
        _bootstrap_op_trampoline()
        try:
            return globals()[name]
        except KeyError:
            raise AttributeError(
                f"module {__name__!r} has no attribute {name!r}"
            ) from None
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


_DESCRIPTION = """\nEmits one CompletionReceipt per parseable state/completion-receipts file,
superseded receipts included (`superseded` is derived from a later
receipt's `supersedes`). Receipts failing the entity model are dropped."""


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(
        prog="query-completion-receipts.py",
        description=_DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )


def main(argv: list[str] | None = None) -> int:
    if any(n not in globals() for n in _BOOTSTRAPPED_NAMES):
        _bootstrap_op_trampoline()
    resolve_claude_klabauter_root_or_exit = globals()["resolve_claude_klabauter_root_or_exit"]
    resolve_repo_root_or_exit = globals()["resolve_repo_root_or_exit"]

    argv = sys.argv[1:] if argv is None else argv
    parser = build_parser()
    parser.parse_args(argv)

    repo_root = resolve_repo_root_or_exit()
    if isinstance(repo_root, int):
        return repo_root

    claude_klabauter_root = resolve_claude_klabauter_root_or_exit("query-completion-receipts")
    if isinstance(claude_klabauter_root, int):
        return claude_klabauter_root

    try:
        from coordinator_core.ops.emit.resolvers import resolve_context
        from coordinator_core.ops.emit.sections import completion_receipts
    except ImportError as exc:
        print(f"query-completion-receipts: coordinator_core not importable: {exc}", file=sys.stderr)
        return 1

    try:
        ctx = resolve_context(Path(repo_root))
        records, _malformed = completion_receipts.collect(ctx)
    except Exception as exc:  # noqa: BLE001 -- any failure on this path is exit 1
        print(f"query-completion-receipts: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(records, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
