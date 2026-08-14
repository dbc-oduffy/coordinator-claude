# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
coordinator/bin/queue-triage — one CLI fronting the three queue-triage-terminus
ops (queue.cluster, queue.age_ping, handoff.scaffold_from_queue).

Purpose: extensionless entrypoint, naked Python, matching
coordinator-queue-append's shape (same noun family, same consumer). ONE CLI
with a `<leg>` argument (cluster | age-ping | scaffold-baton) rather than
three near-identical scripts, each leg taking a queue-family argument — the
sender's stated preference (docs/plans/2026-07-23-queue-triage-terminus-ops.md
§ C7). Cluster and age-ping route via `cc_invoke.route()` (compute-only);
scaffold-baton routes via `cc_invoke.route_mutation()` (mutating, and honors
the op's in-envelope exit_code/error refusal shape). Every leg prints the
op's ratified response envelope as JSON to stdout unchanged — this CLI adds
no rendering, no summarization, no second copy of any envelope shape.

Spec backlink: pln-queue-triage-terminus-ops-clus-043c40 § C7

Op keys (do not confuse the third with `queue.scaffold_baton` — the module
that registers it is `queue_scaffold_baton.py` by filename convention only;
the op KEY is `handoff.scaffold_from_queue`, since it writes
`state/handoffs/`, outside DR-213's queue-write carve-out):
    queue.cluster
    queue.age_ping
    handoff.scaffold_from_queue

The `<family>` positional is uniform across all three legs for CLI-shape
symmetry. `queue.cluster` and `queue.age_ping` forward it directly into their
params (`family` / `families=[family]`). `handoff.scaffold_from_queue` has no
`family` param at all — it derives family from each item's `path` — so here
`<family>` is used ONLY to expand a bare `--entry-path` filename into its
likely repo-relative location (`state/<family>/<filename>`); it is never
sent to that op and never branches on a specific family name (no second
queue-family map is authored here — see module Negative-spec below).

Negative-spec: this module authors no directory glob, no frontmatter parser,
no record loader, and no `if family == "...": ...` ladder — all three ops it
fronts already own that logic; this CLI only builds params dicts and prints
whatever comes back. It never validates family LEGITIMACY (whether the name
is a known queue family) itself (that is each op's job via
`coordinator_core.ops.queue_family`) — an unknown family surfaces as an
ordinary op-level error, not a CLI-side hard-fail. It DOES validate family's
CHARSET at parse time for scaffold-baton only (`_family_arg`) — that check
guards this CLI's own filesystem-path interpolation (`_entry_path_for`), not
family legitimacy, and is orthogonal to the op-level check.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path, PureWindowsPath
from typing import Any

_BIN_DIR = Path(__file__).resolve().parent
_LIB_DIR = str(_BIN_DIR / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from cc_invoke import (  # noqa: E402
    RouteMutationError,
    require_engine_on_path,
    route,
    route_mutation,
)

# The engine root must be on sys.path before any `coordinator_core` import: this
# file is also published into the claude-klabauter mirror, where coordinator_core
# is NOT pip-installed, so a bare import resolves nothing and the CLI dies at
# import time. Same bootstrap as coordinator/bin/lib/workday_ceremony_lib.py
# (landed in d2d4ec545 for the identical failure on /workday-start Step 0).
_ENGINE_ROOT = str(require_engine_on_path(__file__))

from coordinator_core.win_portability import no_console_creationflags  # noqa: E402

_OP_CLUSTER = "queue.cluster"
_OP_AGE_PING = "queue.age_ping"
_OP_SCAFFOLD = "handoff.scaffold_from_queue"

# Review: code-reviewer — Finding 1 (P1): scaffold-baton's `family` is
# interpolated into a filesystem path (`_entry_path_for`) with no parse-time
# guard, unlike `entry_path` (checked for separators before use). Charset-only
# allowlist, scoped to scaffold-baton's `family` alone — cluster/age-ping's
# `family` never touches a filesystem path (it goes straight into op params),
# so this is not a general family-legitimacy check (that stays the op's job).
# Mirrors coordinator-queue-append's `_validate_workstream_identifier` shape.
_FAMILY_ARG_RE = re.compile(r"^[a-z][a-z0-9-]*$")


def _legacy_fn(op: str):
    """No-bash-fallback marker — mirrors sweep-boot.py's big-bang-cutover shape.

    All three ops are assumed present (verified at plan-scout time, C1-C6 of
    this same plan). There is no per-op bash sweep left to strangle back to;
    a raised legacy_fn only fires if the native seam is genuinely absent,
    which `route`/`route_mutation` already treat identically to any other
    transport failure.
    """
    def _raise() -> Any:
        raise RuntimeError(
            f"queue-triage: native seam absent for {op!r} and no bash fallback "
            "remains — ensure coordinator_core is installed and importable."
        )
    return _raise


def _resolve_repo_root(explicit: str | None) -> str | None:
    """Resolve repo_root — `--repo-root` wins; else `git rev-parse --show-toplevel`."""
    if explicit:
        return explicit
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            **no_console_creationflags(),
        )
    except OSError:
        return None
    root = result.stdout.strip()
    if result.returncode != 0 or not root:
        return None
    return root


def _dispatch_read(op: str, params: dict, repo_root: str) -> tuple[Any, int]:
    """Cluster/age-ping dispatch — route() is compute-only, bare result on success.

    Returns (result, exit_code). Only a transport failure (RuntimeError) is
    possible here — route() never interprets an in-envelope exit_code/error
    the way route_mutation() does, by design (AC10).
    """
    try:
        result = route(op, params, repo_root, _legacy_fn(op))
    except RuntimeError as exc:
        print(f"queue-triage: {op} transport error: {exc}", file=sys.stderr)
        return None, 2
    return result, 0


def _dispatch_mutation(op: str, params: dict, repo_root: str) -> tuple[Any, int]:
    """scaffold-baton dispatch — route_mutation() honors the op's in-envelope refusal shape."""
    try:
        result = route_mutation(op, params, repo_root, _legacy_fn(op))
    except RouteMutationError as exc:
        print(f"queue-triage: {op} refused: {exc}", file=sys.stderr)
        return exc.result, 1
    except RuntimeError as exc:
        print(f"queue-triage: {op} transport error: {exc}", file=sys.stderr)
        return None, 2
    return result, 0


def _split_csv(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def _family_arg(value: str) -> str:
    """Parse-time validator for `family` — charset-only, path-injection guard.

    Rejects `family` values that would escape `state/<family>/` when
    interpolated by `_entry_path_for` (e.g. `../../etc`) or otherwise carry
    path separators. Applied uniformly to all three legs' `family` positional
    for CLI-shape symmetry (matching the module's stated uniform-positional
    convention), even though only scaffold-baton's `family` actually reaches
    a filesystem path today — a future leg reusing the same positional gets
    the guard for free rather than needing to remember to add it.
    """
    if not _FAMILY_ARG_RE.match(value):
        raise argparse.ArgumentTypeError(
            f"family must match {_FAMILY_ARG_RE.pattern!r} (lowercase letters, "
            f"digits, hyphens only — no path separators or '..' segments), "
            f"got {value!r}"
        )
    return value


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="queue-triage",
        description="Front the queue-triage-terminus ops: cluster, age-ping, scaffold-baton.",
        epilog=(
            "NOTE: --repo-root may appear before OR after the leg name "
            "(e.g. both `queue-triage --repo-root R cluster debt-backlog` and "
            "`queue-triage cluster debt-backlog --repo-root R` work)."
        ),
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="explicit repo root (default: `git rev-parse --show-toplevel`); "
        "may be given before or after the leg name",
    )
    sub = parser.add_subparsers(dest="leg", required=True)

    # Review: code-reviewer — Finding 2 (P2): argparse's subparsers action
    # (nargs=PARSER) consumes the subcommand token plus ALL remaining argv as
    # that subparser's own arguments, so `--repo-root` only worked when given
    # BEFORE the leg name. Carrying the same flag as a `parents=[...]` shared
    # parser on every subparser lets it work in either position — `default=
    # argparse.SUPPRESS` on the shared copy is load-bearing: without it, a
    # subparser parse with `--repo-root` omitted would still set its own
    # default and silently overwrite an already-populated top-level value
    # when the outer namespace is merged (see _SubParsersAction.__call__).
    _repo_root_parent = argparse.ArgumentParser(add_help=False)
    _repo_root_parent.add_argument("--repo-root", default=argparse.SUPPRESS)

    p_cluster = sub.add_parser(
        "cluster", parents=[_repo_root_parent], help="queue.cluster — signal-clustered candidates"
    )
    p_cluster.add_argument(
        "family", type=_family_arg, help="queue-family directory name, e.g. debt-backlog"
    )
    p_cluster.add_argument(
        "--signals", default=None, help="comma-separated subset of tag,directory,keyword"
    )
    p_cluster.add_argument("--min-cluster-size", type=int, default=None)
    p_cluster.add_argument("--where", default=None)
    p_cluster.add_argument("--since", default=None)
    p_cluster.add_argument("--limit", type=int, default=None)

    p_age = sub.add_parser(
        "age-ping",
        parents=[_repo_root_parent],
        help="queue.age_ping — parked entries past threshold",
    )
    p_age.add_argument(
        "family", type=_family_arg, help="queue-family directory name, e.g. bug-backlog"
    )
    p_age.add_argument("--threshold-days", type=int, default=None)
    p_age.add_argument(
        "--exclude-path",
        action="append",
        default=None,
        dest="exclude_paths",
        help="repo-relative path already dispositioned this cycle (repeatable)",
    )

    p_scaffold = sub.add_parser(
        "scaffold-baton",
        parents=[_repo_root_parent],
        help="handoff.scaffold_from_queue — turn a selection into a baton",
    )
    p_scaffold.add_argument(
        "family",
        type=_family_arg,
        help="queue-family directory name (used only to expand --entry-path)",
    )
    group = p_scaffold.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--entry-path",
        default=None,
        help="repo-relative path to a single queue row (solo shape); a bare "
        "filename is expanded to state/<family>/<filename>",
    )
    group.add_argument(
        "--cluster-json",
        default=None,
        help="path to a JSON file holding a queue.cluster envelope item "
        "(themed shape), or '-' to read it from stdin",
    )
    p_scaffold.add_argument("--title", default=None)
    p_scaffold.add_argument("--branch", default=None)
    p_scaffold.add_argument("--kind", default=None)
    p_scaffold.add_argument("--workstream", default=None)
    p_scaffold.add_argument("--body", default=None)
    p_scaffold.add_argument("--origin-plan-id", default=None, dest="origin_plan_id")
    p_scaffold.add_argument("--origin-goal-id", default=None, dest="origin_goal_id")
    p_scaffold.add_argument("--match-text", default=None, dest="match_text")

    return parser


def _entry_path_for(family: str, entry_path: str) -> str:
    """Expand a bare filename against `family`; leave an already-qualified path alone.

    Emitted as a POSIX-separated string regardless of platform -- the
    downstream `handoff.scaffold_from_queue` param contract carries
    repo-relative identifiers, not native filesystem paths, and Windows'
    `Path.__str__()` yields backslashes that would otherwise leak a
    host-specific separator into it.
    """
    if "/" in entry_path or "\\" in entry_path:
        # Review: code-reviewer P2, EM override — the bare-filename branch
        # below was POSIX-normalized but this already-qualified branch still
        # returned a caller-supplied path verbatim, backslashes included.
        # Normalize here too so both branches honour the same
        # repo-relative-identifier contract that `handoff.scaffold_from_queue`
        # expects.
        return PureWindowsPath(entry_path).as_posix()
    return "/".join(("state", family, entry_path))


def _load_cluster_json(cluster_json: str) -> dict:
    if cluster_json == "-":
        text = sys.stdin.read()
    else:
        with open(cluster_json, "r", encoding="utf-8") as fh:
            text = fh.read()
    return json.loads(text)


def _build_cluster_params(args: argparse.Namespace) -> dict:
    params: dict[str, Any] = {"family": args.family}
    signals = _split_csv(args.signals)
    if signals is not None:
        params["signals"] = signals
    if args.min_cluster_size is not None:
        params["min_cluster_size"] = args.min_cluster_size
    if args.where is not None:
        params["where"] = args.where
    if args.since is not None:
        params["since"] = args.since
    if args.limit is not None:
        params["limit"] = args.limit
    return params


def _build_age_ping_params(args: argparse.Namespace) -> dict:
    params: dict[str, Any] = {"families": [args.family]}
    if args.threshold_days is not None:
        params["threshold_days"] = args.threshold_days
    if args.exclude_paths is not None:
        params["exclude_paths"] = args.exclude_paths
    return params


def _build_scaffold_params(args: argparse.Namespace) -> dict:
    params: dict[str, Any] = {}
    if args.entry_path:
        params["entry"] = {"path": _entry_path_for(args.family, args.entry_path)}
    else:
        params["cluster"] = _load_cluster_json(args.cluster_json)
    if args.title is not None:
        params["title"] = args.title
    if args.branch is not None:
        params["branch"] = args.branch
    if args.kind is not None:
        params["kind"] = args.kind
    if args.workstream is not None:
        params["workstream"] = args.workstream
    if args.body is not None:
        params["body"] = args.body
    if args.origin_plan_id is not None:
        params["origin_plan_id"] = args.origin_plan_id
    if args.origin_goal_id is not None:
        params["origin_goal_id"] = args.origin_goal_id
    if args.match_text is not None:
        params["match_text"] = args.match_text
    return params


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    args = _build_parser().parse_args(argv)

    repo_root = _resolve_repo_root(args.repo_root)
    if not repo_root:
        print("queue-triage: cannot resolve git repo root", file=sys.stderr)
        return 2

    if args.leg == "cluster":
        result, exit_code = _dispatch_read(_OP_CLUSTER, _build_cluster_params(args), repo_root)
    elif args.leg == "age-ping":
        result, exit_code = _dispatch_read(_OP_AGE_PING, _build_age_ping_params(args), repo_root)
    else:
        result, exit_code = _dispatch_mutation(
            _OP_SCAFFOLD, _build_scaffold_params(args), repo_root
        )

    # Review: code-reviewer — Finding 7 (nit): gate printing on exit_code (2 ==
    # transport failure, no envelope produced) rather than `result is not
    # None` — a legitimate op result of JSON `null` on success (exit_code 0)
    # or a refusal envelope (exit_code 1) must still print verbatim, per the
    # "every leg prints the op's ratified envelope unchanged" contract.
    if exit_code != 2:
        print(json.dumps(result, indent=2))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
