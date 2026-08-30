# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""close-origin-stub-on-ship.py — close the origin spinoff/spinoff-roadmap stub
whose work just shipped, joining on (roadmap_id, stub_id) from the governing
plan / consumed handoff.

Purpose: a `kind: spinoff-roadmap` (or `spinoff`) origin stub in
state/handoffs/ is authored `deployment_state: ready_to_fire` and its work
is often executed through a SEPARATE plan/baton — the origin stub's own
frontmatter is never touched again, so after the work ships the origin stub
is left ready_to_fire forever, wrongly advertising shipped work as a live
pickup-able target. This helper closes that stub at /workstream-complete
time by joining on the (roadmap_id, stub_id) pair the governing plan (or
consumed handoff) already carries in its own frontmatter.

NATIVE TRAMPOLINE (2026-07-19 Windows de-bash campaign, W1b): a per-op
Python entry (shape-(b) per docs/plans/2026-07-19-debash-coordinator-windows.md)
that subprocess-spawns `coordinator_core.invoke` via `cc_invoke.route_mutation`
to reach claude-klabauter's `handoff.close_origin_stub` op — the join+scan+stamp logic
itself lives there, not here. This replaces the retired bash veneer
(DR-059 THIN OP-VENEER) with a pure-Python call: no `#!/bin/sh` polyglot
header, no bash re-wrap, no legacy fallback under big-bang cutover
(`_legacy_fn` raises).

Spec backlinks:
  cross-repo/inbox/2026-07-08-example-cockpit-repo-em-spinoff-roadmap-lifecycle-never-closed.md
  state/handoffs/2026-07-08_205600_roadmap-lvv-09.md (C9/lvv-09 — sibling cadence backstop)
  cross-repo/archive/2026-07-14-claude-klabauter-em-dr059-portship-handshake-contract.md
    (DR-059 — claude-klabauter's handoff.close_origin_stub op contract this trampoline routes to)
  docs/plans/2026-07-19-debash-coordinator-windows.md (Wave 1b — B-facade repoint)

Negative-spec: this is the PROACTIVE close-on-ship path, run inline from
/workstream-complete Step 2.7b. The cadence-sweep backstop (lvv-09) is a
SEPARATE, deferred mechanism that walks non-terminal stubs on a cadence and
rolls them up via deliverable-id derivation — do NOT implement roll-up
logic here; this script only ever closes via the exact (roadmap_id,
stub_id) join surfaced at ship time.

Trust boundary (carried over from the retired bash veneer): this helper
trusts the governing plan's/handoff's self-asserted `roadmap_id`/`stub_id`
as an honest, complete claim that the plan realized the stub's promised
scope. It does NOT verify the plan actually completed the stub's
acceptance criteria. A premature close (multi-plan stub, first plan
completing) is a bounded, self-correcting harm: a later re-pickup of the
still-open work reopens the stub.

Usage:
    close-origin-stub-on-ship.py [--plan <plan-path>] [--handoff <handoff-path>] [--sha <sha>]

At least one of --plan / --handoff must be given.

--sha <sha>: optional shipping SHA, passed through to the op's `sha` param
for the `shipped_in` stamp. Never invented / defaulted to a branch tip —
absent means the op skips the shipped_in stamp (graceful).

Exit: 0 on op success (a declined stamp, an ambiguous match, or a no-op
join are all non-fatal, surfaced states inside a 0 exit — the op itself
decides what counts as "handled"). 1 on any op failure (transport failure,
op-level refusal via RouteMutationError). Usage errors (exit 2) are
validated BEFORE any op routing and never reach cc_invoke.
"""
from __future__ import annotations

import argparse
import os
import sys

_BOOTSTRAPPED_NAMES = ("resolve_checked_repo_root",)


def _bootstrap_cos() -> None:
    """Bind `resolve_checked_repo_root` at module scope, guarded so a caller
    that already set the name on this module (a test's `mock.patch.object`)
    is never clobbered by a later real import."""
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path

    global resolve_checked_repo_root
    if "resolve_checked_repo_root" not in globals():
        from repo_identity import resolve_checked_repo_root as _rcr

        resolve_checked_repo_root = _rcr


def __getattr__(name: str):
    """PEP 562 hook so a caller reaching for `resolve_checked_repo_root`
    before `main()`/`_repo_root()` has run -- a test monkeypatching this
    module -- triggers `_bootstrap_cos()` lazily instead of finding the name
    absent.

    NEGATIVE SPEC -- `_bootstrap_cos()` guards on the single name's own
    presence, so this hook never needs a forced re-run: a name missing from
    `__dict__` is always filled by the plain call above.
    """
    if name in _BOOTSTRAPPED_NAMES:
        _bootstrap_cos()
        try:
            return globals()[name]
        except KeyError:
            raise AttributeError(
                f"module {__name__!r} has no attribute {name!r}"
            ) from None
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _legacy_fn():
    """Big-bang cutover: no bash fallback. Always raises.

    Mirrors the plan's pinned pattern (`docs/plans/2026-07-19-debash-coordinator-windows.md`
    § Canonical native call shape): "Under big-bang the legacy_fn RAISES (no bash
    fallback)". The retired bash veneer this replaces was itself already the SOLE
    path (its own legacy join+scan+stamp engine had already been removed) — this
    preserves that same fail-loud-only contract at the Python layer.
    """
    raise RuntimeError(
        "close-origin-stub-on-ship.py: handoff.close_origin_stub has no legacy "
        "fallback under big-bang de-bash cutover — the native op transport must "
        "succeed"
    )


def _repo_root() -> str:
    """Resolve the repo root via the checked resolver (repo_identity).

    READER classification (DR-277 / plan C5): MISMATCH is advisory only --
    warn to stderr and proceed with the resolved root; UNRESOLVED never
    refuses (AC4). Falls back to os.getcwd() when no root at all resolves,
    preserving this script's pre-existing best-effort behavior.
    """
    _bootstrap_cos()

    root, verdict = resolve_checked_repo_root(explicit_root=None)
    if verdict["verdict"] == "MISMATCH":
        print(verdict["message"], file=sys.stderr)
    return root or os.getcwd()


def main(argv: list[str] | None = None) -> int:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import RouteMutationError, route_mutation

    parser = argparse.ArgumentParser(
        prog="close-origin-stub-on-ship.py",
        description=(
            "Close the origin spinoff/spinoff-roadmap stub whose work just shipped, "
            "joining on (roadmap_id, stub_id)."
        ),
    )
    parser.add_argument("--plan", dest="plan_path", default=None, help="governing plan path")
    parser.add_argument("--handoff", dest="handoff_path", default=None, help="consumed handoff path")
    parser.add_argument("--sha", dest="sha", default=None, help="shipping SHA for the shipped_in stamp")
    args = parser.parse_args(argv)

    if not args.plan_path and not args.handoff_path:
        print(
            "close-origin-stub-on-ship.py: usage: close-origin-stub-on-ship.py "
            "[--plan <plan-path>] [--handoff <handoff-path>] [--sha <sha>]",
            file=sys.stderr,
        )
        print(
            "close-origin-stub-on-ship.py: at least one of --plan / --handoff must be given",
            file=sys.stderr,
        )
        return 2

    params = {
        "plan_path": args.plan_path,
        "handoff_path": args.handoff_path,
        "sha": args.sha,
    }
    repo_root = _repo_root()

    try:
        result = route_mutation("handoff.close_origin_stub", params, repo_root, _legacy_fn)
    except RouteMutationError as exc:
        print(
            f"close-origin-stub-on-ship.py: handoff.close_origin_stub op reported failure: {exc}",
            file=sys.stderr,
        )
        return 1
    except RuntimeError as exc:
        print(
            f"close-origin-stub-on-ship.py: handoff.close_origin_stub op failed (transport): {exc}",
            file=sys.stderr,
        )
        return 1

    # Success — print a concise summary from the op's result.
    # {"exit_code":0,"closed":[{"stub_path","roadmap_id","stub_id","join_source",
    #  "close_basis"}],"skipped":[...],"pairs_resolved":int,"message":str}
    closed = result.get("closed", []) if isinstance(result, dict) else []
    skipped = result.get("skipped", []) if isinstance(result, dict) else []
    message = result.get("message", "") if isinstance(result, dict) else ""
    pairs_resolved = result.get("pairs_resolved", "?") if isinstance(result, dict) else "?"

    print(
        "close-origin-stub-on-ship.py: handoff.close_origin_stub — closed=%d skipped=%d "
        "pairs_resolved=%s%s"
        % (len(closed), len(skipped), pairs_resolved, (" — " + message) if message else "")
    )
    for c in closed:
        print(
            "close-origin-stub-on-ship.py: closed origin stub %s (stub_id %s)"
            % (c.get("stub_path", "?"), c.get("stub_id", "?"))
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
