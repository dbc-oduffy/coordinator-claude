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
    from cc_invoke import _resolve_claude_klabauter_root, require_dispatch_engine_on_path

    try:
        claude_klabauter_root = require_dispatch_engine_on_path()
    except RuntimeError as exc:
        print(f"{cli_name}: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return 1
    return claude_klabauter_root


def run(
    op_name: str,
    params_builder: Callable[[list[str]], dict[str, object]],
    *,
    argv: list[str],
) -> int:
    """Route `op_name` through `cc_invoke.route_mutation`, print the result as
    JSON, return an exit code.

    `params_builder(argv)` is the one piece of per-CLI knowledge this
    function does not own -- argparse shape (flags, filter grammar,
    `--help` honesty disclosures) is inherently per-CLI.

    Uses `route_mutation`, not the bare `route`, so that an in-envelope
    refusal (build_setup_error_result's `{"exit_code": N, ...}`,
    build_act_result's partial/total `failed` list, or the completion_ops/
    plan_ops `{"error": "..."}` shape) is inspected and raised as
    `RouteMutationError` instead of being printed and exited 0 as if it were
    a success payload -- this trampoline is the documented anti-hand-copying
    seam (module docstring), so the first MUTATING op routed through it must
    not silently inherit the exit_code trap `route_mutation` exists to close.
    Read-only ops still route correctly: `route_mutation` only raises when
    the result dict carries a refusal-shaped `exit_code`/`failed`/`error`
    field, which a read-only op's result never does.

    Exit-code convention: 0 on success; 1 for every non-success path
    (transport failure, seam-absent, root-unresolvable, op-level refusal)
    -- the 4-of-5 majority among the pre-existing hand-copied CLIs.
    """
    params = params_builder(argv)

    repo_root = resolve_repo_root_or_exit()
    if isinstance(repo_root, int):
        return repo_root

    def _no_legacy() -> None:
        raise RuntimeError(f"{op_name}: native seam required (no bash fallback)")

    try:
        result = cc_invoke.route_mutation(op_name, params, repo_root, _no_legacy)
    except cc_invoke.RouteMutationError as exc:
        print(f"{op_name}: refused -- {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"{op_name}: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False))
    return 0

# by the same mechanism. The PUBLISHED engine and its CLIs are transformed on the
resolve_claude_klabauter_root_or_exit = resolve_claude_klabauter_root_or_exit
