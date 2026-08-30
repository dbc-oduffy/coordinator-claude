# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""prune-closed-bugs.py — archive closed bug-backlog entries via fleet.prune_closed_bugs.

Port of: prune-closed-bugs.sh (DoE f703efad, 2026-07-21). Daily ceremony wrapper — dispatches
fleet.prune_closed_bugs, which self-enumerates state/bug-backlog/*.yaml
with status: closed and owns the git-mv + self-commit. Best-effort: errors
are logged and this script always exits 0 so it never hard-gates
/workday-complete.

Two-call shape (KD-4 self-preview; the ACT call's dispatch verb now mirrors
sweep-terminal-plans.py -- route() + manual exit_code inspection, not
route_mutation() -- see Review note above the ACT call below):
    Call 1: dry_run:true  — op self-selects candidate IDs (status: closed
             only; wontfix/deferred are retained — see
             coordinator/docs/wiki/bug-backlog-schema.md § Status enum).
    Call 2: dry_run:false — op performs git-mv + self-commit for those IDs.
    Empty candidates -> report "nothing to prune", skip Call 2, exit 0.

Usage:
    python3 prune-closed-bugs.py [--dry-run] [--repo-root <path>]

    --dry-run    preview only (Call 1 result reported; Call 2 skipped, no git-mv).
    --repo-root  explicit repo root for the git-mv + self-commit (default: the
                 checked resolver's answer, `lib.repo_identity.
                 resolve_checked_repo_root`, from the CALLING process's cwd,
                 falling back to cwd itself). This op self-selects candidates AND deletes
                 (git-mv) — a cwd-derived root under an in-process ceremony
                 dispatch (no subprocess, no `-C`) silently targets whatever
                 directory the caller happened to be standing in, which for a
                 destructive op is a data-loss risk, not a cosmetic one
                 (2026-07-26 arg-mismatch audit, class (d): named as one of only
                 two data-loss-capable directives in the whole consumes-manifest).

Exit codes:
    0 — best-effort; transport/resolution failures are logged to stderr,
        never propagated as non-zero.
    1 — the act call returned a recognized-refusal or unrecognized exit_code
        (anything other than 0/None/2) — a setup-error shape, not a healthy
        prune.

Big-bang cutover (2026-07-19 Windows de-bash campaign, Wave F1): no legacy
bash fallback — the op is assumed present; a genuinely seam-absent install
surfaces as a transport failure (RuntimeError), caught below and logged,
never propagated.

Spec backlink: DoE-claude:pln-wire-claude-klabauter-fleet-archive-prun-8fd552 § KD-4 / AC6
Spec backlink: docs/plans/2026-07-19-debash-coordinator-windows.md § Wave F1 (facade collapse)
"""
from __future__ import annotations

import os
import sys

_BOOTSTRAPPED_NAMES = (
    "cc_invoke",
    "RouteMutationError",
    "is_timeout_error",
    "route_mutation",
    "resolve_checked_repo_root",
)


def _bootstrap_pcb() -> None:
    """Bind the deferred cc_invoke/repo_identity names this module's own
    functions read as globals, each guarded independently so a caller (this
    file's own test suite, which does plain `mod.route_mutation =
    fake_route_mutation` / `mod._resolve_repo_root = fake_resolver`
    assignments, or `mock.patch.object(mod, "resolve_checked_repo_root",
    ...)`, ahead of calling `mod.main()`) that has already set one of these
    names on the module is never clobbered by a later real import -- only a
    name still absent from `__dict__` is bound. Per-name (not a single
    flag/sentinel) because a test may stub `route_mutation` while leaving
    `cc_invoke` for this bootstrap to still provide (`mod.cc_invoke` is read
    directly by `_install_route()`-shaped test helpers)."""
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path

    global cc_invoke, RouteMutationError, is_timeout_error, route_mutation
    if "cc_invoke" not in globals():
        import cc_invoke as _cc_invoke_mod

        cc_invoke = _cc_invoke_mod
    if (
        "RouteMutationError" not in globals()
        or "is_timeout_error" not in globals()
        or "route_mutation" not in globals()
    ):
        from cc_invoke import (
            RouteMutationError as _RME,
            is_timeout_error as _ITE,
            route_mutation as _RM,
        )

        if "RouteMutationError" not in globals():
            RouteMutationError = _RME
        if "is_timeout_error" not in globals():
            is_timeout_error = _ITE
        if "route_mutation" not in globals():
            route_mutation = _RM

    global resolve_checked_repo_root
    if "resolve_checked_repo_root" not in globals():
        from repo_identity import resolve_checked_repo_root as _rcr

        resolve_checked_repo_root = _rcr


def __getattr__(name: str):
    """PEP 562 hook so a caller reaching for one of `_BOOTSTRAPPED_NAMES`
    before `main()`/`_resolve_repo_root()` has run -- a test monkeypatching
    this module, or any consumer importing it rather than executing it --
    triggers `_bootstrap_pcb()` lazily instead of finding the name absent.

    NEGATIVE SPEC -- `_bootstrap_pcb()` guards each name independently (no
    single flag/sentinel), so this hook never needs a forced re-run: a name
    missing from `__dict__` is always filled by the plain call above, and a
    name a caller already set (test stub, `mock.patch.object`) is never
    clobbered by it.
    """
    if name in _BOOTSTRAPPED_NAMES:
        _bootstrap_pcb()
        try:
            return globals()[name]
        except KeyError:
            raise AttributeError(
                f"module {__name__!r} has no attribute {name!r}"
            ) from None
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _no_fallback() -> None:
    raise RuntimeError(
        "fleet.prune_closed_bugs: native seam required (no bash fallback -- big-bang cutover)"
    )


def _resolve_repo_root() -> str:
    """Resolve the repo root via the checked resolver (repo_identity).

    READER classification (DR-277 / plan C5): MISMATCH is advisory only --
    warn to stderr and proceed with the resolved root; UNRESOLVED never
    refuses (AC4). Falls back to os.getcwd() when no root at all resolves,
    preserving this script's pre-existing best-effort behavior.
    """
    _bootstrap_pcb()

    root, verdict = resolve_checked_repo_root(explicit_root=None)
    if verdict["verdict"] == "MISMATCH":
        print(verdict["message"], file=sys.stderr)
    return root or os.getcwd()


def main(argv: list[str] | None = None) -> int:
    _bootstrap_pcb()

    argv = sys.argv[1:] if argv is None else argv
    dry_run_only = False
    explicit_repo_root: str | None = None
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--dry-run":
            dry_run_only = True
            i += 1
        elif arg == "--repo-root":
            if i + 1 >= len(argv):
                print("prune-closed-bugs.py: --repo-root requires a value", file=sys.stderr)
                return 0
            explicit_repo_root = argv[i + 1]
            i += 2
        else:
            print(f"prune-closed-bugs.py: unknown arg: {arg}", file=sys.stderr)
            i += 1

    repo_root = explicit_repo_root or _resolve_repo_root()

    dry_params = {"mode": "already-terminal", "dry_run": True, "candidate_ids": []}
    try:
        dry_result = route_mutation("fleet.prune_closed_bugs", dry_params, repo_root, _no_fallback)
    except (RouteMutationError, RuntimeError) as exc:
        print(f"prune-closed-bugs.py: WARN: fleet.prune_closed_bugs dry-run failed: {exc}", file=sys.stderr)
        print("prune-closed-bugs.py: skipping (non-blocking)")
        return 0

    candidates = dry_result.get("candidates", []) if isinstance(dry_result, dict) else []
    ids = [c["id"] for c in candidates if isinstance(c, dict) and isinstance(c.get("id"), str)]

    if not ids:
        print("prune-closed-bugs.py: no closed bug entries found -- nothing to prune")
        return 0

    if dry_run_only:
        print(f"prune-closed-bugs.py: {len(ids)} closed bug(s) selected for prune (--dry-run: no changes made)")
        return 0

    print(f"prune-closed-bugs.py: {len(ids)} closed bug(s) selected for prune")

    # Review: code-reviewer (Finding 1) -- route() + manual exit_code inspection, NOT
    # route_mutation(), on the ACT call. fleet.prune_closed_bugs's act response is a
    # DETERMINATE-PARTIAL shape (build_act_result): exit_code=2 means some candidates
    # failed, but acted[] still lists the ones that succeeded -- and those were already
    # git-mv'd and committed. route_mutation() treats ANY non-zero exit_code (including
    # this legitimate partial-success shape) as a hard refusal and raises before the
    # per-item acted[] detail can be inspected, mischaracterizing a real partial success
    # as "not archived (transport error)" for every requested id. Mirrors
    # sweep-terminal-plans.py's ACT-call pattern (route() + acted/exit_code inspection).
    act_params = {"mode": "already-terminal", "dry_run": False, "candidate_ids": ids}
    try:
        act_result = cc_invoke.route("fleet.prune_closed_bugs", act_params, repo_root, _no_fallback)
    except RuntimeError as exc:
        print(f"prune-closed-bugs.py: WARN: fleet.prune_closed_bugs act call failed: {exc}", file=sys.stderr)
        if is_timeout_error(exc):
            # CLAUDE.md § Load norm: a timeout is a SLOW op, not a stopped one -- the
            # act call may be mid-git-mv+commit and about to succeed. Reporting a
            # completed/absent count here would be a false negative that re-dispatches
            # the same ids on the next sweep.
            print(
                f"prune-closed-bugs.py: {len(ids)} candidate(s) selected -- archive status "
                "indeterminate (engine timeout, op may still complete)"
            )
        else:
            print(f"prune-closed-bugs.py: {len(ids)} candidate(s) selected but not archived (transport error)")
        return 0

    acted = act_result.get("acted", []) if isinstance(act_result, dict) else []
    count = len(acted) if isinstance(acted, list) else 0
    act_exit = act_result.get("exit_code", 0) if isinstance(act_result, dict) else 0
    if act_exit == 2:
        print(
            f"prune-closed-bugs.py: WARN: fleet.prune_closed_bugs partial (exit_code=2, acted={count}) -- check claude-klabauter logs",
            file=sys.stderr,
        )
    elif act_exit not in (0, None):
        print(
            f"prune-closed-bugs.py: fleet.prune_closed_bugs act call refused (exit_code={act_exit}) -- not archived",
            file=sys.stderr,
        )
        return 1
    print(f"prune-closed-bugs.py: fleet.prune_closed_bugs completed -- {count} entr(ies) archived")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # pragma: no cover - best-effort ceremony, never propagate
        print(f"prune-closed-bugs.py: WARN: prune dispatch crashed unexpectedly (non-blocking): {exc}", file=sys.stderr)
        sys.exit(0)
