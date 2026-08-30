"""query-commit-closures.py -- the porter over `sections/commit_closures.py:collect(ctx)`.

No shebang line, no exec bit. The `.cmd`/`.ps1` siblings beside this file
ARE generated, by `gen-launcher-shim.py`, exactly as `query-goals.py` and
`query-routine-signals.py` do -- both of which ship all three files.

An earlier version of this docstring claimed the opposite and cited those
two porters as precedent for shipping no shim. That citation was false on
its face: the two files it named contradict it. The plan's own C4
negative-spec inherited the same error. Example-cockpit-repo caught it against
this tree, and it was not cosmetic -- their house CLI spawner prefers the
`.cmd` twin on win32 by rule, because Node cannot `execFileSync` a `.py`
or a `.cmd` without `shell: true`. The missing shim blocked the one caller
this porter was built for.

Purpose: a per-repo, one-process entry point a non-Python caller (project-
Cockpit) can spawn to read this repo's `commit_closures` records -- the
per-(sha, item_id) closure/revert fact recovered from the commit ledger --
without linking against `coordinator_core` or standing up a JSON-RPC
client of its own.

`sections/commit_closures.py:collect` has NO registered op behind it -- it
is an emit *section*, a plain in-process function, not something
`cc_invoke.route` can dispatch. This file therefore does NOT use
`coordinator/bin/lib/op_trampoline.py`'s `run()` (that entrypoint exists
to route a *named op*; there is no op name here, and minting one would be
an engine change no plan behind this porter asks for). It DOES reuse
`op_trampoline.resolve_repo_root_or_exit()` and
`op_trampoline.resolve_claude_klabauter_root_or_exit()` -- the two pieces of the
Shape-A recipe that apply unchanged -- and hand-implements the same exit-1
failure-diagnostic convention around its own `collect(ctx)` call, so the
two shapes do not drift. See `query-goals.py`'s module docstring for the
fuller version of this reasoning; both porters are the same shape over a
different section.

**No lazy-ops arming, because there is no longer a channel to arm.** This
porter shipped with `os.environ.setdefault("COORDINATOR_CORE_LAZY_OPS",
"1")` ahead of its first `coordinator_core` import, against a measured
312.5ms / 743 modules default versus 0.0ms / 46 modules armed. That
deviation was correct when written and is now dead: `dlv-the-lazy-ops-
flag-is-an-apparatus-around-ae432a` landed the retirement, and
`coordinator_core/ops/__init__.py` records that lazy is the only mode --
`_lazy_ops_requested`, the env var, and the in-process attribute are all
gone, so importing the bare package never eagerly registers anything. The
saving this porter used to buy for itself is now the baseline every caller
gets, and the arming line was removed rather than left inert so a future
reader does not take it for a live mechanism. Do not restore it; there is
nothing on the other end.

The other three section porters (`query-goals.py`, `query-routine-
signals.py`, `query-completion-rollups.py`) get the same baseline for the
same reason, and need no per-file change either.

Otherwise no deviation from `query-goals.py`: a straight
`collect()`-and-print. `commit_closures.collect(ctx)` resolves the
tri-state `reachable_on_default_branch` and the close/revert distinction
itself; nothing is reshaped, filtered, or renamed in `bin/`.

Usage:
    python3 query-commit-closures.py
    python3 query-commit-closures.py --help

Exit codes:
    0 -- success, `commit_closures.collect(ctx)`'s records list printed to
         stdout as JSON.
    1 -- repo-root resolution failure, or any exception raised while
         building the context or calling `collect()`.
    2 -- unrecognized argument (this CLI takes no flags besides the
         automatic -h/--help; argparse's own usage-error convention,
         matching `query-goals.py`).

Spec backlink: plan `2026-08-22-the-commit-closure-pipe-carries-rows.md` § C4

Negative-spec: does NOT add filtering, caching, or any commit-closure
abstraction layer -- this porter is a read-only trampoline over
`collect(ctx)` in the shape of this directory's other `query-*` CLIs, not
a commit-closure API. Does NOT mint a registered op for `commit_closures.
collect`. Does NOT edit `coordinator_core/ops/emit/sections/
commit_closures.py` -- that file is READ-ONLY to this porter. Does NOT
reshape, rename, or filter fields out of the emitted records -- the
output is `commit_closures.collect(ctx)`'s existing shape verbatim,
including the honesty-disclosure coverage limits named in `_HONESTY_
DISCLOSURES` below.
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
THREE coverage limits a consumer of this CLI must not lose:

  Rows exist from C1's landing forward -- history is not backfilled. A
  commit that landed before the commit-ledger closure/revert stamping
  went live produces no `commit_closures` row, regardless of whether its
  message would have closed or reverted anything.

  The going-forward set itself is 33.5% of commits since 2026-08-19
  (931/2,779) -- gated by which commits actually route through the
  ledger-writing producer and which baton owns them, not every commit
  since that date.

  A hand-authored revert with no git-generated `This reverts commit
  <sha>` line produces no revert row (DR-318 Section D4's measured
  ~50% coverage) -- this boundary fails safe: a miss here is "not a
  revert", never a wrong retract."""


def build_parser() -> argparse.ArgumentParser:
    """No flags beyond the automatic -h/--help -- this CLI takes no
    arguments (see module docstring's Negative-spec: no filtering, no
    caching, no commit-closure-abstraction layer)."""
    return argparse.ArgumentParser(
        prog="query-commit-closures.py",
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

    claude_klabauter_root = resolve_claude_klabauter_root_or_exit("query-commit-closures")
    if isinstance(claude_klabauter_root, int):
        return claude_klabauter_root

    try:
        from coordinator_core.ops.emit.resolvers import resolve_context
        from coordinator_core.ops.emit.sections import commit_closures
    except ImportError as exc:
        print(f"query-commit-closures: coordinator_core not importable: {exc}", file=sys.stderr)
        return 1

    try:
        ctx = resolve_context(Path(repo_root))
        records, _malformed = commit_closures.collect(ctx)
    except Exception as exc:  # noqa: BLE001 -- any failure on this path is exit 1.
        print(f"query-commit-closures: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(records, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
