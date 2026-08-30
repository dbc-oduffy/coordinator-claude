"""
coordinator/bin/cartography.py — operator CLI seam for the `cartography.*` op family
(coordinator_core/ops/cartography_*.py).

Purpose: A8 — the cartography ops (tree, file_index, churn, symbols, edges,
count_references, stack, chunk_table, and any future addition) had no
`coordinator/bin/<verb>` operator surface. Every caller had to re-derive the
real invocation seam — `python3 -m coordinator_core.invoke <op> '<json>'
--repo <path>` — by reading a DR-215 retirement stub (docs/wiki/dr-215.md),
because the bash-era `coordinator/bin/` convention every other op family gets
had no cartography member. This is that member: a thin CLI trampoline over
`coordinator_core.invoke`'s command-type dispatch, reusing the shared
`cc_invoke_bare` transport (coordinator/bin/lib/cc_invoke.py) — the same
fail-closed timeout/nonzero-exit/empty-stdout ladder every other native
facade in this tree shares, not a bespoke reimplementation.

Op enumeration is NOT hardcoded: `_cartography_ops()` reads
`coordinator_core.ops._registry_map.OP_MODULE_MAP` at call time and filters
for the `cartography.` prefix, so a ninth op (or a tenth, ...) added to that
map needs zero edits here. This directly answers the brief's stated failure
mode — a hand-maintained op list (the budget-manifest gate) silently drifted
to five entries while the real family grew to eight, and a ninth
(`cartography.op_edges`) was mid-flight the same wave this verb was written.

Every `cartography.*` op is scope `"none"` (COMPUTE_ONLY, no implicit
repo-specific state — see e.g. cartography_file_index.py's classification
block) and is entirely targeted via its own `target_root` wire param, NOT via
`--repo`. `--repo` is refused loud (DR-279's shape,
docs/decisions/DR-279-repo-on-a-none-scoped-op-fails-loud.md): for a
scope="none" op, `cc_invoke_bare`'s own `_should_pass_repo` gate never
forwards `--repo` to the spawned `coordinator_core.invoke` argv, and the
spawn itself always runs `cwd=claude_klabauter_root` — a caller-computed root is
discarded before transmission regardless of how it was obtained, so this
file used to spend a git spawn (and `sys.exit(2)` outside a git tree)
resolving a value nothing downstream ever reads. `--target-root` is the
actual per-op targeting knob and is wired straight into the op's
`target_root` param.

Usage:
    cartography.py <op> --target-root <path> [--params '<json>']
    cartography.py --list

    <op> accepts either the bare op suffix (e.g. "file_index") or the fully
    qualified wire name ("cartography.file_index"); both resolve to the same
    dispatch. `--list` prints every currently-registered `cartography.*` op
    name (one per line) and exits 0, taking priority over a positional <op>.

    `--params` carries any wire params beyond `target_root` (e.g. `since` for
    churn, `files` for symbols/edges, `run_id`/`systems`/`chunk_size`/`emit`
    for chunk_table) as a single JSON object string, merged with
    `--target-root` (an explicit `target_root` key inside `--params` is
    overridden by `--target-root` when both are given). This file does not
    special-case any op's own params beyond `target_root` — that duplication
    lives in each op module already; a generic passthrough avoids a second,
    driftable copy of each op's params contract here.

Exit codes:
    0 — success; the op's bare JSON-RPC result printed to stdout via
        `json.dumps(result, ensure_ascii=False)` (bare, unindented, matching
        `cc_invoke_bare`'s own --bare/--params-file parse of
        `coordinator_core.invoke`'s bare success-path serialization).
    1 — client-side usage error (unknown op, missing --target-root, malformed
        --params JSON, no <op> and no --list, --repo passed (DR-279
        refusal)).
    2 — cc_invoke_bare transport/op failure (engine timeout, nonzero engine
        exit, malformed envelope) — see coordinator/bin/lib/cc_invoke.py's
        `cc_invoke_bare` docstring for the full fail-closed ladder this
        reuses verbatim.

Spec backlink: A8 (cartography operator-seam spinoff, 2026-08-06 wave)
DR-215 ref: docs/wiki/dr-215.md, docs/decisions/DR-215-coordinator-core-command-type-execution-model.md

Negative-spec: does NOT hand-maintain a list of cartography op names anywhere
in this file (see `_cartography_ops()`); does NOT spend a git spawn (or any
other resolution) on a transport repo root for this scope="none" op family —
`--repo` is refused loud instead (D3,
docs/plans/2026-08-20-a-refusal-cannot-exit-zero.md § C16) — this verb
instead gives `--target-root` the targeting meaning `--repo` does not have,
entirely at the CLI-trampoline layer.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

cc_invoke_bare = None  # type: ignore  # bound by _bootstrap_cc_invoke_bare()


def _bootstrap_cc_invoke_bare() -> None:
    """Import `cc_invoke_bare` and bind it at module scope, called from
    `main()` (module body stays inert on both the warm door and the
    un-bootstrapped settings-home forwarder load routes).

    Guarded on the current value of `cc_invoke_bare` itself, rather than a
    separate `_BOOTSTRAP_DONE` flag, so a caller's `mod.cc_invoke_bare =
    stub` monkeypatch set BEFORE the first `main()` call (the shape every
    `coordinator/bin/tests/` fixture here uses) is never clobbered by a
    same-process bootstrap that runs after it.
    """
    global cc_invoke_bare
    if cc_invoke_bare is not None:
        return

    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import cc_invoke_bare


def _cartography_ops() -> list[str]:
    """Return every registered `cartography.*` op name, sorted.

    Reads `coordinator_core.ops._registry_map.OP_MODULE_MAP` fresh on every
    call rather than caching a copy in this module — the whole point is that
    a newly-added op is visible here with zero edits to this file.
    """
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_colocated_engine_on_path

    require_colocated_engine_on_path(__file__)
    from coordinator_core.ops._registry_map import OP_MODULE_MAP

    return sorted(op for op in OP_MODULE_MAP if op.startswith("cartography."))


def _resolve_op_name(raw: str, known_ops: list[str]) -> str:
    """Accept either a bare op suffix ("file_index") or the full wire name
    ("cartography.file_index"); exits 1 with the known-op list on a miss.
    """
    if raw in known_ops:
        return raw
    qualified = f"cartography.{raw}"
    if qualified in known_ops:
        return qualified
    suffixes = ", ".join(op.split(".", 1)[1] for op in known_ops)
    print(
        f"cartography: unknown op {raw!r}. Known cartography ops: {suffixes}",
        file=sys.stderr,
    )
    sys.exit(1)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cartography",
        description=(
            "Operator CLI seam for the cartography.* op family "
            "(coordinator_core.invoke command-type dispatch)."
        ),
    )
    parser.add_argument(
        "op",
        nargs="?",
        help=(
            "cartography op name — bare suffix (e.g. file_index) or fully "
            "qualified (cartography.file_index). Not required with --list."
        ),
    )
    parser.add_argument(
        "--target-root",
        help=(
            "Root of the tree the op targets — wired verbatim into the op's "
            "own target_root wire param. This is the real per-op targeting "
            "knob; --repo below is transport-only."
        ),
    )
    parser.add_argument(
        "--params",
        default="{}",
        help=(
            "Extra op params beyond target_root, as a JSON object string "
            "(e.g. '{\"since\": \"7 days ago\"}' for churn). Merged with "
            "--target-root; --target-root wins on key collision."
        ),
    )
    parser.add_argument(
        "--repo",
        help=(
            "Refused: every cartography.* op is scope \"none\" (see "
            "docs/decisions/DR-279-repo-on-a-none-scoped-op-fails-loud.md) "
            "— it accesses no repo-specific state, so --repo would be "
            "meaningless. Passing it fails loud instead of silently "
            "no-opping. Use --target-root for per-op targeting."
        ),
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List every registered cartography.* op name and exit 0.",
    )
    return parser


def main(argv: list[str]) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    known_ops = _cartography_ops()

    if args.list:
        for op in known_ops:
            print(op)
        return 0

    if not args.op:
        parser.print_usage(sys.stderr)
        print("cartography: an <op> is required (or pass --list)", file=sys.stderr)
        return 1

    if args.repo:
        # Every cartography.* op is scope "none" (D3,
        # docs/plans/2026-08-20-a-refusal-cannot-exit-zero.md § C16):
        # cc_invoke_bare's _should_pass_repo() gate suppresses forwarding
        # --repo on argv for it, and the spawn itself always runs
        # cwd=claude_klabauter_root, so a caller-computed root is discarded before
        # transmission regardless of how it was obtained. Refuse loud
        # instead of resolving/validating a value nothing downstream reads.
        from cc_invoke import none_scoped_repo_refusal

        print(none_scoped_repo_refusal("cartography", "cartography.*"), file=sys.stderr)
        return 1

    op = _resolve_op_name(args.op, known_ops)

    try:
        extra_params = json.loads(args.params)
    except json.JSONDecodeError as exc:
        print(f"cartography: --params must be valid JSON: {exc}", file=sys.stderr)
        return 1
    if not isinstance(extra_params, dict):
        print("cartography: --params must decode to a JSON object", file=sys.stderr)
        return 1

    params: dict[str, object] = dict(extra_params)
    if args.target_root:
        params["target_root"] = args.target_root
    if "target_root" not in params or not params["target_root"]:
        print(
            "cartography: --target-root is required (or supply target_root "
            "inside --params)",
            file=sys.stderr,
        )
        return 1

    try:
        # Every cartography.* op is scope "none" — cc_invoke_bare's
        # _should_pass_repo() gate suppresses forwarding --repo for it, so
        # this empty string is never read; see the --repo refusal above.
        _bootstrap_cc_invoke_bare()

        result = cc_invoke_bare(op, params, "")
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
