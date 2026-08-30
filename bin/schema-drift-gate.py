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
shell-doc-ok: that expansion is the generated shell forwarder's own text.

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

_OP = "schema.drift_gate"

_BOOTSTRAPPED_NAMES = ("cc_invoke",)


def _bootstrap_cc_invoke() -> None:
    """Import `cc_invoke` into this module's globals, deferred out of
    module scope so a warm-serve import of this file stays inert until
    `main()` runs."""
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    import cc_invoke

    globals()["cc_invoke"] = cc_invoke


def __getattr__(name: str):
    """PEP 562 hook serving `cc_invoke` to a test that reads/replaces it
    off this module without calling `main()` first (e.g.
    `mod.cc_invoke.route = fake_route`).

    Negative-spec: does NOT serve any other name -- an unrelated
    AttributeError still raises normally.
    """
    if name in _BOOTSTRAPPED_NAMES:
        _bootstrap_cc_invoke()
        try:
            return globals()[name]
        except KeyError:
            raise AttributeError(
                f"module {__name__!r} has no attribute {name!r}"
            ) from None
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _legacy_fn() -> "NoReturn":  # type: ignore[name-defined]
    raise RuntimeError(
        "schema-drift-gate: coordinator_core seam absent — no bash fallback "
        "under the debash big-bang cutover. Install/repair coordinator_core "
        "(the engine root) and retry."
    )


def main(argv: list[str] | None = None) -> int:
    if any(n not in globals() for n in _BOOTSTRAPPED_NAMES):
        _bootstrap_cc_invoke()
    cc_invoke = globals()["cc_invoke"]

    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in ("--help", "-h"):
        print("usage: schema-drift-gate")
        return 0
    if argv:
        print(f"schema-drift-gate: unexpected argument(s): {' '.join(argv)}", file=sys.stderr)
        return 2

    try:
        # schema.drift_gate is scoped "none" (D4,
        # docs/plans/2026-08-20-a-refusal-cannot-exit-zero.md § C16):
        # cc_invoke's own _should_pass_repo() gate suppresses forwarding a
        # repo root on argv for it, and the underlying spawn always runs
        # cwd=claude_klabauter_root — a caller-resolved root is discarded before
        # transmission regardless of how it was obtained. This used to
        # spawn git to resolve one anyway (and exit 2 outside a git tree)
        # for a value nothing downstream ever read; "" is never read either.
        result = cc_invoke.route(_OP, {}, "", _legacy_fn)
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
