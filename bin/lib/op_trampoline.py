"""op_trampoline.py -- the extracted Shape-A CLI recipe.

Purpose: six of this directory's `query-*` CLIs each hand-copied the same
recipe -- resolve the repo root via the checked resolver, route a named op
through `cc_invoke`, print the routed result as JSON to stdout, exit 1 on
any failure. Extract-on-third-use passed long ago (this is the sixth and
seventh copy, C3 and C4); this module gives that recipe one authored home
instead of a "read that file first and mirror it" instruction repeated in
every new CLI's own docstring.

`run(op_name, params_builder, *, argv)` is the entrypoint for a CLI whose
work IS routing a registered op through `cc_invoke.route`. `resolve_repo_
root_or_exit()` is exposed separately, at module level, for a CLI that
cannot use `run()` at all -- C4's `routine_signals.collect(ctx)` has no
registered op behind it, calls into `routine_signals` in-process instead of
through `cc_invoke.route`, and so can only share the repo-root-resolution
and exit-code pieces, not the whole recipe.

`resolve_claude_klabauter_root_or_exit(cli_name)` is the third module-level helper --
the CLAUDE_KLABAUTER_ROOT-resolution sub-recipe (`from cc_invoke import
_resolve_claude_klabauter_root`, try/except RuntimeError, diagnostic naming the
calling CLI, `sys.path.insert` if not already present) that `query-file-
attribution.py` and `query-routine-signals.py` each hand-copied before this
extraction. `cli_name` is a required parameter, not a shared constant --
each caller's diagnostic keeps naming its own CLI, since a consumer reading
stderr needs to know which one failed.

Reference implementation this was extracted FROM: `coordinator/bin/query-
handoff-columns.py`'s `_resolve_repo_root`, `_no_legacy`, and the body of
`main` (route call, JSON emission, exit convention). `_parse_args` is the
one piece that does NOT generalize here -- argparse shape is inherently
per-CLI -- and stays the caller-supplied `params_builder`.

`op_trampoline.run` is producer-internal. The sibling fleet-board consumer
spawns named per-repo CLIs (`query-roadmap-serve.py`, `query-routine-
signals.py`, etc.); those entrypoints, names, and argv shapes are exactly
what C3/C4 specify, and nothing in that consumer's spawn contract
references this module.

Spec backlink: plan `2026-08-11-three-trampolines-and-the-bare-repo-producer.md` § C0

Negative-spec: does NOT build a generic `query.py <op> --param k=v`
dispatcher, or any spawnable CLI that takes an op name as an argument --
that would leak claude-klabauter's internal op namespace into a sibling repo's spawn
contract, a consumer-visible surface this repo would then owe forever.
`run()` is a shared internal implementation called from named, per-purpose
CLI files; it is never itself spawned by anything outside this repo. Does
NOT call `sys.exit` and has no `__main__` block -- it stays a plain,
importable, test-without-process-exit-side-effects library module; `if
__name__ == "__main__": sys.exit(run(...))` stays in the calling CLI.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Callable

import cc_invoke  # noqa: E402
from repo_identity import resolve_checked_repo_root  # noqa: E402


def resolve_repo_root_or_exit() -> str | int:
    """Resolve the repo root via the checked resolver.

    Moved verbatim from `query-handoff-columns.py::_resolve_repo_root` and
    given a name reusable outside `run()` (C4 divergence -- see module
    docstring). READER (DR-277): a MISMATCH verdict is warned to stderr and
    the resolved root used anyway -- never refused. UNRESOLVED never
    refuses either.

    Returns the resolved repo root (`str`) on success. On an unresolvable
    root, prints a diagnostic naming the cwd to stderr and returns `1`
    (the exit code the caller should return/exit with) instead of raising
    or calling `sys.exit` itself -- this module never exits the process.
    """
    repo_root, verdict = resolve_checked_repo_root(explicit_root=None)
    if repo_root is None:
        print(
            f"op_trampoline: cannot resolve git repo root from {os.getcwd()}",
            file=sys.stderr,
        )
        return 1
    if verdict["verdict"] == "MISMATCH":
        print(verdict["message"], file=sys.stderr)
    return repo_root


def resolve_claude_klabauter_root_or_exit(cli_name: str) -> str | int:
    """Resolve CLAUDE_KLABAUTER_ROOT via the checked ladder and put it on sys.path.

    Extracted from `query-file-attribution.py::_resolve_repo_name_or_exit`
    and `query-routine-signals.py::_resolve_claude_klabauter_root` -- both hand-rolled
    this identical sub-recipe. `cli_name` is stamped into the failure
    diagnostic so a consumer reading stderr can tell which CLI failed;
    callers must NOT be collapsed onto one shared generic message.

    Returns the resolved CLAUDE_KLABAUTER_ROOT (`str`) on success, with `sys.path`
    already updated if it was not already present. On an unresolvable root,
    prints a diagnostic naming `cli_name` and the underlying error to
    stderr and returns `1` (the exit code the caller should return/exit
    with) instead of raising or calling `sys.exit` itself -- this module
    never exits the process.
    """
    from cc_invoke import _resolve_claude_klabauter_root

    try:
        claude_klabauter_root = _resolve_claude_klabauter_root()
    except RuntimeError as exc:
        print(f"{cli_name}: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return 1
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    return claude_klabauter_root


def run(
    op_name: str,
    params_builder: Callable[[list[str]], dict[str, object]],
    *,
    argv: list[str],
) -> int:
    """Route `op_name` through `cc_invoke.route`, print the result as JSON,
    return an exit code.

    `params_builder(argv)` is the one piece of per-CLI knowledge this
    function does not own -- argparse shape (flags, filter grammar,
    `--help` honesty disclosures) is inherently per-CLI.

    Exit-code convention: 0 on success; 1 for every non-success path
    (transport failure, seam-absent, root-unresolvable) -- the 4-of-5
    majority among the pre-existing hand-copied CLIs.
    """
    params = params_builder(argv)

    repo_root = resolve_repo_root_or_exit()
    if isinstance(repo_root, int):
        return repo_root

    def _no_legacy() -> None:
        raise RuntimeError(f"{op_name}: native seam required (no bash fallback)")

    try:
        result = cc_invoke.route(op_name, params, repo_root, _no_legacy)
    except RuntimeError as exc:
        # Transport failure (State-3) or legacy-seam-absent raise (State-1).
        print(f"{op_name}: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False))
    return 0
