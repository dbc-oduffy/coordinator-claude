"""query-work-state.py — native Python CLI entry routing session.work_state.

No shebang line: unlike this directory's generator-owned two-leg entrypoints
(a tracked `.cmd`/`.ps1` sibling pairs with a POSIX shebang leg via
`gen-launcher-shim.py`), this file is invoked as `python3
query-work-state.py`, never as a bare word — no exec-bit/shebang launch
path exists for it, so none is asserted here.

Purpose: REQUIRED FOR THE COCKPIT LEG, not a convenience. DR-215 retired the
live invoke transport, so a cross-language consumer (a Node/TS fleet-board
consumer) reaches a claude-klabauter read by SPAWNING this CLI, never by calling the
op directly. Modeled on `coordinator/bin/query-handoff-columns.py` (read
that file's own docstring first — this mirrors its shape byte-for-byte
where the two ops agree): resolve the repo root, route `session.work_state`
through `cc_invoke.route()` (not a direct handler import), print the result
as JSON to stdout, exit 0 on success and non-zero on failure.

`session.work_state` is a READ-ONLY op (C3) — this trampoline calls
`cc_invoke.route()`, not `route_mutation()`. `route()` returns the bare
result dict on transport success and raises on transport failure/seam-
absence; there is no in-envelope exit_code/failed ladder to inspect here.

PER-REPO BY CONSTRUCTION, same as `query-handoff-columns.py` — one
invocation answers the repo `--repo-root` (or cwd) resolves to, nothing
else. NO `--fleet`/multi-root flag — `query-handoff-columns.py`'s own
module docstring forbids exactly this shape by name, and this file
inherits that ruling rather than reversing it. A caller wanting the whole
fleet (Cockpit's fleet-board consumer included) loops this CLI once per
registered sibling repo root. `fleet.work_state` (C5) exists for
in-process/EM/agent callers that want the aggregate directly — it is not
exposed through this CLI.

`--repo-root` NOTE: unlike `query-handoff-columns.py`, which resolves its
repo root via `repo_identity.resolve_checked_repo_root` and surfaces a
MISMATCH verdict to stderr (DR-277), this flag takes the caller's path
directly and bypasses that check. This is acceptable here because
`cc_invoke.route()` already takes `repo_root` positionally with no wire
param needed, and `session.work_state`'s scope is `common_dir`-resolved
from that path inside the op itself (C3) rather than depending on the CLI
having independently verified it — the checked-resolver contract has
nothing further to add at this call site. Do not treat this as a
precedent for skipping DR-277 checks elsewhere; it holds specifically
because the op itself re-resolves.

Spec backlink: pln-a-pull-surface-for-cockpit-the-b8e2f3 § C7

Usage:
    python3 query-work-state.py
    python3 query-work-state.py --repo-root /path/to/repo

Exit codes:
    0 — success, `session.work_state` result printed to stdout as JSON.
    1 — op-level failure (transport failure, seam absent, or any other
        exception raised while routing the op).

Negative-spec: does NOT invoke bash, sh, or any shell — subprocess
spawning lives entirely inside cc_invoke.route() (sys.executable argv
list, never a shell string). Does NOT reimplement the work-state read;
that is engine-owned (C3) and reached solely through the
`session.work_state` op. Does NOT accept a `--fleet`/multi-root flag —
see the module docstring above for why that shape is refused here. Does
NOT emit a human-formatted table — output is JSON on stdout only.
"""
from __future__ import annotations

import json
import os
import sys


def _no_legacy() -> None:
    """State-1 fallback — the engine-repo control-plane seam is absent on disk.

    `session.work_state` has no bash predecessor and no fallback body; this
    raises unconditionally, and `cc_invoke.route()` wraps the raise in the
    standardized four-rung remediation message on State-1 (seam absent).
    """
    raise RuntimeError("query-work-state: native seam required (no bash fallback)")


def _parse_args(argv: list[str]) -> dict[str, object]:
    """Parse CLI args into (params, repo_root).

    `--repo-root <path>` is the only recognized flag (default: cwd) — see
    the module docstring's negative-spec for why no `--fleet` flag exists
    here. Any unrecognized token, or `--repo-root` given as the trailing
    token with no value, is a hard usage error (exit 1, message naming the
    offending token) rather than a silent drop.

    Returns a dict with key "repo_root" (str, possibly os.getcwd()) — this
    op takes no other params, so the returned dict is intentionally not the
    op's wire-params dict (unlike query-handoff-columns.py's _parse_args,
    which returns the wire params directly); main() reads "repo_root" back
    out and passes an empty params dict to the op.
    """
    repo_root = os.getcwd()
    i = 0
    n = len(argv)
    while i < n:
        if argv[i] == "--repo-root":
            if i + 1 >= n:
                print(
                    "query-work-state: --repo-root requires a value",
                    file=sys.stderr,
                )
                sys.exit(1)
            repo_root = argv[i + 1]
            i += 2
        else:
            print(
                f"query-work-state: unrecognized argument: {argv[i]!r}",
                file=sys.stderr,
            )
            sys.exit(1)
    return {"repo_root": repo_root}


def main(argv: list[str] | None = None) -> int:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    import cc_invoke

    argv = sys.argv[1:] if argv is None else argv
    parsed = _parse_args(argv)
    repo_root = parsed["repo_root"]

    try:
        result = cc_invoke.route("session.work_state", {}, repo_root, _no_legacy)
    except Exception as exc:  # noqa: BLE001
        # Review: staff-eng (Finding 10) -- widened from `except RuntimeError`
        # only: the module docstring's own exit-code table promises "1 —
        # op-level failure ... any other exception raised while routing the
        # op", but `main_worktree_root` (reached inside `session.work_state`
        # on the non-standard-layout arm) raises `ValueError`, not
        # `RuntimeError` -- a Node/TS fleet-board consumer spawning this CLI
        # would previously get an unhandled traceback instead of the
        # documented single stderr line.
        print(f"query-work-state: {exc}", file=sys.stderr)
        return 1

    # STDOUT PASSTHROUGH: the bare native result is re-emitted on stdout.
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
