# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""schema-drift-gate — thin CLI trampoline over coordinator_core's
"schema.drift_gate" op.

Purpose: gives the `schema.drift_gate` op (coordinator_core/ops/schema_drift_gate.py)
an invocable surface. The op reduces schema_drift_watch.scan_vendored_schema_drift()'s
report to a pass/fail verdict for the weekly release boundary (the one cadence point
where a divergent vendored schema actually escapes the repo), but until this CLI
existed nothing on any machine could call it — no generic op-runner lives in
coordinator/bin/, and DoE's ceremonies invoke claude-klabauter capabilities as concrete
executables under `coordinator/bin/` (`"${_mkb_bin}/<cli-name>"`).

Read-only op (no repo mutation, no params) — dispatched via `cc_invoke.route()`,
never `route_mutation()` (that helper is for ops whose in-envelope exit_code/failed/
error shape signals a MUTATION refusal; this op's `ok`/`status` fields are a domain
verdict, not a mutation-refusal signal, and inspecting them is this CLI's own job).

Exit codes:
    0   PASS   — status is MATCH, INDETERMINATE, or UNRESOLVED (op's ok=True).
                 INDETERMINATE/UNRESOLVED print an explicit "could not verify"
                 notice to stderr rather than a bare pass, so a green exit code
                 is never mistaken for "verified clean".
    1   BLOCK  — status is DRIFT (op's ok=False). Operator-facing message on
                 stdout names every drifted schema WITH its direction
                 (we-ahead / we-behind / both), taken verbatim from the op's
                 own response — this CLI never recomputes it.
    2   ERROR  — transport/engine failure (cc_invoke.route() raised, or the op
                 returned a malformed/non-dict result). Distinct from BLOCK: a
                 gate that cannot run is not the same claim as a gate that ran
                 and found drift.

Usage:
    schema-drift-gate

Spec backlink: cross-repo/inbox/2026-07-23-example-cockpit-repo-em-coordinator-doc-new-category-no-validation.md
Spec backlink: coordinator_core/ops/schema_drift_gate.py module docstring (op contract)
"""
from __future__ import annotations

import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(_SCRIPT_DIR, "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

import cc_invoke  # noqa: E402  (sys.path mutated above)

_OP = "schema.drift_gate"


def _resolve_repo_root() -> str | None:
    """Repo toplevel from cwd; None on any failure."""
    try:
        if cc_invoke.ensure_engine_on_path(__file__) is None:
            return None
        from coordinator_core.git.repo_root import show_toplevel

        return show_toplevel()
    except Exception:
        return None


def _legacy_fn() -> "NoReturn":  # type: ignore[name-defined]
    raise RuntimeError(
        "schema-drift-gate: coordinator_core seam absent — no bash fallback "
        "under the debash big-bang cutover. Install/repair coordinator_core "
        "(CLAUDE_KLABAUTER_ROOT) and retry."
    )


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in ("--help", "-h"):
        print("usage: schema-drift-gate")
        return 0
    if argv:
        print(f"schema-drift-gate: unexpected argument(s): {' '.join(argv)}", file=sys.stderr)
        return 2

    repo_root = _resolve_repo_root()
    if not repo_root:
        print("schema-drift-gate: cannot resolve git repo root", file=sys.stderr)
        return 2

    try:
        result = cc_invoke.route(_OP, {}, repo_root, _legacy_fn)
    except RuntimeError as exc:
        print(f"schema-drift-gate: engine could not compute a verdict ({exc})", file=sys.stderr)
        return 2

    if not isinstance(result, dict):
        print(
            f"schema-drift-gate: malformed result from cc_invoke: not a dict ({result!r})",
            file=sys.stderr,
        )
        return 2

    ok = result.get("ok")
    status = str(result.get("status") or "UNKNOWN")
    message = result.get("message")

    if ok is False:
        print(f"schema-drift-gate: BLOCK — status={status}", file=sys.stdout)
        print(message or "drift detected (op returned no message detail)", file=sys.stdout)
        return 1

    if ok is not True:
        print(
            f"schema-drift-gate: malformed result — 'ok' is neither True nor False ({ok!r}); "
            "treating as an engine error, not a verdict",
            file=sys.stderr,
        )
        return 2

    if status in ("INDETERMINATE", "UNRESOLVED"):
        print(
            f"schema-drift-gate: PASS (unverified) — status={status}: "
            f"{message or 'drift check could not be run on this machine'}",
            file=sys.stderr,
        )
    else:
        print(f"schema-drift-gate: PASS — status={status}", file=sys.stdout)

    return 0


if __name__ == "__main__":
    sys.exit(main())
