"""query-routine-signals.py -- the porter over `routine_signals.collect`.

No shebang line, no exec bit: this is only ever spawned as `python3
query-routine-signals.py`, never as a bare word -- no launch path via
`gen-launcher-shim.py` is generated or asserted here (same posture as
`query-roadmap-serve.py`).

Purpose: a per-repo, one-process entry point a non-Python caller (the
sibling fleet-board consumer) can spawn to read the six computed
RoutineSignal records (`weekly`, `docs`, `arch-audit`, `bug-sweep`,
`dormant-repo`, `distill-backlog`) for the invoking repo, without linking
against `coordinator_core` or standing up a JSON-RPC client of its own.

`routine_signals.collect` has NO registered op behind it -- it is an emit
*section*, a plain in-process function, not something `cc_invoke.route`
can dispatch. This file therefore does NOT use `coordinator/bin/lib/
op_trampoline.py`'s `run()` (that entrypoint exists to route a *named op*;
there is no op name here, and minting one would be exactly the engine
change this porter's plan explicitly rules out). It DOES reuse
`op_trampoline.resolve_repo_root_or_exit()` and
`op_trampoline.resolve_claude_klabauter_root_or_exit()` -- the two pieces of the
Shape-A recipe that apply unchanged -- and hand-implements the same exit-1
failure-diagnostic convention around its own `collect(ctx)` call, so the
two shapes do not drift on day one. See `coordinator/bin/lib/
op_trampoline.py`'s module docstring and its C0 plan chunk's "C4
divergence" paragraph for the full reasoning.

Two honesty disclosures a consumer of this CLI needs and must not lose:

  1. `dormant-repo` is a HARDCODED "unknown" placeholder. The cross-repo
     commit-scan connector (tc-4) this signal needs does not exist yet.
     Treat `dormant-repo`'s `computed_state` as "not yet computed," never
     as a genuine fresh/mild/stale verdict.
  2. `collect()` is NOT CHEAP. One invocation runs two in-process
     staleness `main()` calls, two `git log --all --grep` subprocesses
     (60s timeout each), and a full walk of `archive/completed` reading
     every wiki `.md` file into one corpus string. Callers should not
     poll this CLI on a tight interval.

Usage:
    python3 query-routine-signals.py
    python3 query-routine-signals.py --help

Exit codes:
    0 -- success, the six-signal list printed to stdout as JSON.
    1 -- repo-root resolution failure, or any exception raised while
         building the context or calling `collect()`.
    2 -- unrecognized argument (this CLI takes no flags besides the
         automatic -h/--help; argparse's own usage-error convention,
         matching `query-roadmap-serve.py`'s "usage errors at 2" axis).

Spec backlink: plan `2026-08-11-three-trampolines-and-the-bare-repo-producer.md` § C4

Negative-spec: does NOT add filtering, caching, or any signals-abstraction
layer -- this porter is a read-only trampoline over `collect(ctx)` in the
shape of this directory's other `query-*` CLIs, not a signals API. Does
NOT mint a registered op for `routine_signals.collect` -- that would be
the engine change the plan's `## Problem` section rules out. Does NOT
"optimise" `collect()`'s known subprocess/staleness cost -- that cost is
documented, not a defect to fix in this porter. Does NOT edit
`coordinator_core/ops/emit/sections/routine_signals.py` -- that file is
READ-ONLY to this chunk (a peer session holds a live path-touch claim on
it). Does NOT generate a `.cmd`/`.ps1` shim.
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
    """Import `coordinator/bin/lib/op_trampoline.py`'s two Shape-A
    resolvers into this module's globals, deferred out of module scope so
    a warm-serve import of this file stays inert until `main()` runs.
    Idempotent by construction: each name is published via
    `globals().setdefault(...)`, so a name a caller already bound (e.g. a
    `mock.patch.object` of just one of the two resolvers) is left alone
    rather than clobbered when the other name is still missing."""
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
    """PEP 562 hook serving the two op_trampoline resolvers to a test or
    sibling importer that reads them off this module without calling
    `main()` first (e.g. `mock.patch.object(mod,
    "resolve_repo_root_or_exit", ...)`).

    Negative-spec: does NOT serve any other name -- an unrelated
    AttributeError still raises normally.
    """
    if name in _BOOTSTRAPPED_NAMES:
        _bootstrap_op_trampoline()
        try:
            return globals()[name]
        except KeyError:
            raise AttributeError(
                f"module {__name__!r} has no attribute {name!r}"
            ) from None
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")



_HONESTY_DISCLOSURES = """\
Two honesty disclosures a consumer of this CLI needs and must not lose:

  1. `dormant-repo` is a HARDCODED "unknown" placeholder. The cross-repo
     commit-scan connector (tc-4) this signal needs does not exist yet.
     Treat `dormant-repo`'s `computed_state` as "not yet computed," never
     as a genuine fresh/mild/stale verdict.
  2. `collect()` is NOT CHEAP. One invocation runs two in-process
     staleness `main()` calls, two `git log --all --grep` subprocesses
     (60s timeout each), and a full walk of `archive/completed` reading
     every wiki `.md` file into one corpus string. Callers should not
     poll this CLI on a tight interval."""


def build_parser() -> argparse.ArgumentParser:
    """No flags beyond the automatic -h/--help -- this CLI takes no
    arguments (see module docstring's Negative-spec: no filtering, no
    caching, no signals-abstraction layer)."""
    return argparse.ArgumentParser(
        prog="query-routine-signals.py",
        description=_HONESTY_DISCLOSURES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )


def main(argv: list[str] | None = None) -> int:
    if any(n not in globals() for n in _BOOTSTRAPPED_NAMES):
        _bootstrap_op_trampoline()
    resolve_claude_klabauter_root_or_exit = globals()["resolve_claude_klabauter_root_or_exit"]
    resolve_repo_root_or_exit = globals()["resolve_repo_root_or_exit"]

    argv = sys.argv[1:] if argv is None else argv
    parser = build_parser()
    parser.parse_args(argv)  # exits 2 on any unrecognized argument

    repo_root = resolve_repo_root_or_exit()
    if isinstance(repo_root, int):
        return repo_root

    claude_klabauter_root = resolve_claude_klabauter_root_or_exit("query-routine-signals")
    if isinstance(claude_klabauter_root, int):
        return claude_klabauter_root

    try:
        from coordinator_core.ops.emit.resolvers import resolve_context
        from coordinator_core.ops.emit.sections import routine_signals
    except ImportError as exc:
        print(f"query-routine-signals: coordinator_core not importable: {exc}", file=sys.stderr)
        return 1

    try:
        ctx = resolve_context(Path(repo_root))
        signals, _malformed = routine_signals.collect(ctx)
    except Exception as exc:  # noqa: BLE001 -- any failure on this path is exit 1
        print(f"query-routine-signals: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(signals, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
