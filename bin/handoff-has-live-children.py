# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""handoff-has-live-children.py — reverse-membership guard: is a handoff still a live parent?

Purpose: thin CLI veneer over the native `handoff.has_live_children` coordinator_core op,
spawned via cc_invoke.route(). Answers "is this candidate handoff still named as a
predecessor/additional_predecessor/forked_from parent by any OTHER live handoff?" so
callers (archival, review-coverage) can decide whether it is safe to archive.

Port of: handoff-has-live-children.sh (50ec0809, 2026-07-19) — Windows
de-bash campaign, W1b. That facade never carried
a bash legacy_fn fallback of its own (DR-215 already migrated it straight onto the
cc_invoke transport) — this port is a pure language change, same op, same contract, no
shell anywhere on the critical path. The `route()` legacy_fn here raises (big-bang
cutover, consistent with every other W-wave facade in this campaign): a seam-absent
install is a hard failure, not a silent fallback to a second liveness source.

Exit codes:
    0 — has live children (do NOT archive — candidate is still referenced by a live handoff)
    1 — safe to archive (no live handoff names this candidate as predecessor/
        additional_predecessor/forked_from, after all --exclude paths are dropped from the
        live set)
    2 — internal error / indeterminate (fail-closed): caller decides.
        Archival callers MUST treat {0,2} as do-not-archive (same conservative contract as
        the retired bash veneer).
        The review-coverage consumer MUST treat 2 as INDETERMINATE -> FAIL-THE-VERDICT
        (distinct from 0).

Fail-closed on ANY internal error / engine error / transport failure:
    -> exits 2 (indeterminate, do-not-archive) + diagnostic to stderr
    This script is wired into archival ceremonies and the review-coverage gate; fail-open
    would risk archiving a live merge-parent.

Single-liveness-source contract: the answer comes from the native op, NEVER a local grep
or a second live-set computation. The `--live-set-json` flag from the pre-DR-215 era is
retired; coordinator_core owns live-set resolution internally.

Spec backlink: DoE-claude:pln-wire-claude-klabauter-fleet-archive-prun-8fd552 § C6 / KD-5 / AC8
Spec backlink: docs/plans/2026-07-19-debash-coordinator-windows.md (Wave 1, unit W1b)

Usage:
    handoff-has-live-children.py [--exclude <path>]... [--edge-kinds <csv>] <candidate-handoff-path>

Negative-spec:
    - Does NOT open any UDS socket — the daemon and socket path are retired (DR-215);
      coordinator_core is command-type (fresh process per call via cc_invoke).
    - Does NOT read or require any auth token — the command path bypasses IPC auth.
    - Does NOT accept --live-set-json (retired per D5, pcore-03 plan).
    - Does NOT spawn a shell — cc_invoke.route() invokes coordinator_core.invoke via an
      argv-list subprocess.run(), never a shell string.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

_BIN_DIR = os.path.dirname(os.path.abspath(__file__))

PROG = "handoff-has-live-children.py"


def _no_console_kw() -> dict:
    """Lazily resolve the engine root onto sys.path (self-location-first via
    cc_invoke.ensure_engine_on_path — see that function's docstring), then
    splat the canonical no-console-window kwarg. ``{}`` on any resolution/
    import failure (fail-open)."""
    try:
        import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
        import cc_invoke

        if cc_invoke.ensure_engine_on_path(__file__) is None:
            return {}
        from coordinator_core.win_portability import no_console_creationflags

        return no_console_creationflags()
    except Exception:
        return {}


_DEFAULT_EDGE_KINDS = "predecessor,additional_predecessors,forked_from"


def _no_fallback():
    raise RuntimeError(
        f"{PROG}: native seam required (no bash fallback -- big-bang cutover); "
        "re-run coordinator:install or verify COORDINATOR_ENGINE_ROOT"
    )


def _resolve_repo_root(candidate_abs: str) -> str | None:
    """Resolve repo root from candidate's directory (git -C <candidate-parent>).

    Candidate-first discovery mirrors the retired bash veneer: production handoffs live
    in <repo>/state/handoffs/, so candidate-dir discovery always resolves the correct
    per-repo git root, and it also lets the test harness point candidates at fixture
    repos with their own .git.
    """
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    import cc_invoke

    if cc_invoke.ensure_engine_on_path(__file__) is None:
        return None
    from coordinator_core.git.repo_root import show_toplevel

    return show_toplevel(cwd=os.path.dirname(candidate_abs))


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=PROG, add_help=False)
    p.add_argument("--exclude", action="append", default=[], dest="exclude")
    p.add_argument("--edge-kinds", default=_DEFAULT_EDGE_KINDS, dest="edge_kinds")
    p.add_argument("candidate", nargs="?", default=None)
    return p


def main(argv: list[str] | None = None) -> int:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    import cc_invoke

    argv = sys.argv[1:] if argv is None else argv

    try:
        args = _build_parser().parse_args(argv)
    except SystemExit:
        # argparse's own usage-error path already wrote a message; normalize to the
        # veneer's fail-closed exit code (2), not argparse's default (2 happens to match,
        # but pin it explicitly rather than depending on that coincidence).
        return 2

    if not args.candidate:
        print(f"{PROG}: missing argument: <candidate-handoff-path>", file=sys.stderr)
        return 2

    candidate_abs = os.path.abspath(args.candidate)
    if not os.path.isfile(candidate_abs):
        print(f"{PROG}: candidate not found on disk: {args.candidate}", file=sys.stderr)
        return 2

    repo_root = _resolve_repo_root(candidate_abs)
    if not repo_root:
        print(f"{PROG}: cannot resolve git repo root from candidate dir", file=sys.stderr)
        print(f"  Candidate dir: {os.path.dirname(candidate_abs)}", file=sys.stderr)
        print("  Remediation: ensure candidate file is inside a git repository", file=sys.stderr)
        return 2

    exclude_abs = [os.path.abspath(p) for p in args.exclude]
    params = {
        "candidate": candidate_abs,
        "exclude": exclude_abs,
        "edge_kinds": args.edge_kinds,
    }

    try:
        result = cc_invoke.route("handoff.has_live_children", params, repo_root, _no_fallback)
    except Exception as exc:  # noqa: BLE001 — fail-closed on ANY transport/engine error
        print(f"{PROG}: engine error ({exc}) -- fail-closed; candidate retained", file=sys.stderr)
        return 2

    if not isinstance(result, dict):
        print(f"{PROG}: engine returned a non-object result -- fail-closed", file=sys.stderr)
        return 2

    # Frozen contract: print each live child path to stdout, one per line, mirroring the
    # retired bash veneer's per-path echo.
    for child in result.get("children", []) or []:
        print(child)

    try:
        exit_code = int(result.get("exit_code", 2))
    except (TypeError, ValueError):
        exit_code = 2
    if exit_code not in (0, 1, 2):
        exit_code = 2
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
