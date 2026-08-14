"""query-handoff-columns.py — native Python CLI entry routing handoff.columns.

No shebang line: unlike this directory's generator-owned two-leg entrypoints
(a tracked `.cmd`/`.ps1` sibling pairs with a POSIX shebang leg via
`gen-launcher-shim.py`), this file is invoked as `python3
query-handoff-columns.py`, never as a bare word — no exec-bit/shebang launch
path exists for it, so none is asserted here.

Purpose: a per-repo, one-process entry point a non-Python caller (a Node/TS
fleet-board consumer) can spawn to read the five computed handoff columns
(`status`, `deployment_state`, `predecessor`, `shipped_in`, `baton_class`)
over live plus archived handoffs, without linking against `coordinator_core`
or standing up a JSON-RPC client of its own. Mirrors `coordinator/bin/emit-cockpit-
snapshot.py`'s shape: resolve the repo root via the checked resolver
(`coordinator/bin/lib/repo_identity.resolve_checked_repo_root`), route the op
through `cc_invoke` (`coordinator/bin/lib/cc_invoke.py`), print the result as
JSON to stdout, exit 0 on success and non-zero on failure.

`handoff.columns` is a READ-ONLY op (C3, coordinator_core/ops/
handoff_columns_query.py) — this trampoline calls `cc_invoke.route()`, not
`route_mutation()`. `route()` returns the bare result dict on transport
success and raises on transport failure/seam-absence; there is no in-envelope
exit_code/failed ladder to inspect here the way a mutation op would have
(contrast `wsc-tail.py`'s route() usage, which reads a soft-fail payload —
this op has no such shape, so a returned dict is unconditionally success).

PER-REPO BY CONSTRUCTION — same as `emit-cockpit-snapshot.py` and every other
entry in this directory: one invocation answers the repo CWD resolves to,
nothing else. There is no fleet-wide mode and none is planned here — a caller
that wants the whole fleet (e.g. a cross-repo fleet board) loops over sibling
repo roots and invokes this once per root. A one-invocation-refreshes-the-
whole-fleet assumption was raised once already for this exact shape (the
sibling emission-consumer read) and does not hold; don't add a
`--fleet`/multi-root flag to "fix" this — loop the caller instead.

Spec backlink: pln-a-pull-surface-for-cockpit-the-b8e2f3 § C4

Archive coverage DEFAULTS ON for this CLI — a bare invocation returns live
plus archived handoffs (Review: this op has exactly one intended consumer,
Cockpit's fleet board, whose whole purpose is showing shipped work; there
are no existing callers whose result sets must stay live-only, unlike
`records.query`, whose `include_archived` stays default-off). Pass
`--no-archive` to opt OUT and see live handoffs only.

Usage:
    python3 query-handoff-columns.py
    python3 query-handoff-columns.py --where "status=open"
    python3 query-handoff-columns.py --since 2026-08-01 --no-archive

Exit codes:
    0 — success, `handoff.columns` result printed to stdout as JSON.
    1 — repo-root resolution failure, or op-level failure (transport failure,
        seam absent, or any other exception raised while routing the op).

Negative-spec: does NOT invoke bash, sh, or any shell — subprocess spawning
lives entirely inside cc_invoke.route() (sys.executable argv list, never a
shell string). Does NOT reimplement the column computation or the archive-
coverage flag; both are engine-owned (C1, C2, C3) and reached solely through
the `handoff.columns` op.
"""
from __future__ import annotations

import json
import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
import cc_invoke  # noqa: E402
from repo_identity import resolve_checked_repo_root  # noqa: E402


def _no_legacy() -> None:
    """State-1 fallback — the engine-repo control-plane seam is absent on disk.

    `handoff.columns` has no bash predecessor and no fallback body; this
    raises unconditionally, and `cc_invoke.route()` wraps the raise in the
    standardized four-rung remediation message on State-1 (seam absent).
    """
    raise RuntimeError("query-handoff-columns: native seam required (no bash fallback)")


def _resolve_repo_root() -> str:
    """Resolve the repo root via the checked resolver (`repo_identity.
    resolve_checked_repo_root`) — mirrors emit-cockpit-snapshot.py's own
    migrated `_resolve_repo_root`. READER (AC10): a MISMATCH verdict is
    warned to stderr and the resolved root used anyway (DR-277); UNRESOLVED
    never refuses either (AC4)."""
    repo_root, verdict = resolve_checked_repo_root(explicit_root=None)
    if repo_root is None:
        print(
            f"query-handoff-columns: cannot resolve git repo root from {os.getcwd()}",
            file=sys.stderr,
        )
        sys.exit(1)
    if verdict["verdict"] == "MISMATCH":
        print(verdict["message"], file=sys.stderr)
    return repo_root


def _parse_args(argv: list[str]) -> dict[str, object]:
    """Build the `handoff.columns` params dict from CLI args.

    `--where` and `--since` pass through as the op's existing `records.query`
    filter grammar (reused, not reinvented — C3's own constraint).
    `--no-archive` is a bare boolean flag OPTING OUT of archive coverage
    (default is ON — see module docstring); omitted means the op's own
    default (archive coverage on) applies.

    Any unrecognized token, or `--where`/`--since` given as the trailing
    token with no value, is a hard usage error (exit 1, message naming the
    offending token) rather than a silent drop — a dropped filter returns
    the unfiltered superset with exit 0, which reads as healthy and is
    worse than a hard failure. Mirrors `records_query.py`'s
    `_KNOWN_PARAM_KEYS` unknown-param guard.
    """
    params: dict[str, object] = {}
    i = 0
    n = len(argv)
    while i < n:
        if argv[i] == "--where":
            if i + 1 >= n:
                print(
                    "query-handoff-columns: --where requires a value",
                    file=sys.stderr,
                )
                sys.exit(1)
            params["where"] = argv[i + 1]
            i += 2
        elif argv[i] == "--since":
            if i + 1 >= n:
                print(
                    "query-handoff-columns: --since requires a value",
                    file=sys.stderr,
                )
                sys.exit(1)
            params["since"] = argv[i + 1]
            i += 2
        elif argv[i] == "--no-archive":
            params["archive"] = False
            i += 1
        else:
            print(
                f"query-handoff-columns: unrecognized argument: {argv[i]!r}",
                file=sys.stderr,
            )
            sys.exit(1)
    return params


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    params = _parse_args(argv)
    repo_root = _resolve_repo_root()

    try:
        result = cc_invoke.route("handoff.columns", params, repo_root, _no_legacy)
    except RuntimeError as exc:
        # Transport failure (State-3) or legacy-seam-absent raise (State-1).
        print(f"query-handoff-columns: {exc}", file=sys.stderr)
        return 1

    # STDOUT PASSTHROUGH: the bare native result is re-emitted on stdout.
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
