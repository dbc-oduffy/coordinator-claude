"""handoff-discharge-criteria — CLI trampoline over the engine-repo's
`handoff.discharge_criteria` op.

Invoke as `python3 coordinator/bin/handoff-discharge-criteria.py` (or via the
co-located `.cmd` launcher on Windows) — no shebang / exec bit on this file
(new-file zero-budget ratchet: env_shebang; see
`nudge-new-file-zero-budget-ratchets.py`).

Purpose: `coordinator_core/ops/handoff_discharge_criteria.py` is the
sanctioned way to tick (or split) one `## Acceptance criteria` checkbox on a
handoff — the resolution `coordinator:workstream-complete`'s consumed-handoff
completeness gate expects when it blocks a close on an unticked criterion,
and the op DR-274 § D3 sanctions as the second body-mutating verb alongside
`handoff.correct_body`. That op had no bareword `coordinator/bin/`
entrypoint: closing a spinoff had to import the handler and drive
`asyncio.run` by hand to reach it. This file is that trampoline — same house
shape as the sibling `handoff-backfill-claim-stamp.py` (argparse, a resolved
per-handoff repo root, `cc_invoke.route_mutation()`, matching `.cmd`
launcher).

Call shape (one checkbox per call, mirroring the op's own single-replacement
bound):

    handoff-discharge-criteria.py <handoff-path> \\
        (--criterion-id <AC-N> | --position <n>) \\
        [--met-text <text> --unmet-text <text>] \\
        [--override-reason <text>]

`--criterion-id` and `--position` are mutually exclusive; exactly one is
required (mirrors the op's own `criterion_id`/`position` XOR precondition —
AC17 in the op's module docstring). `--met-text`/`--unmet-text` are optional
and must be supplied together — when both are given the resolved checkbox is
SPLIT into a met (ticked) line and a still-unmet (unticked) line instead of a
plain tick; when the target carries a resolvable criterion_id, `--unmet-text`
must carry that same identity token or the op refuses (F4 in the op's own
docstring). `--override-reason` is forwarded verbatim and is consulted by
`handoff.correct_body` ONLY when the calling session is neither the claim
holder nor the authoring session of the target — this trampoline never
supplies a default for it (that would turn a deliberate possession gate into
a formality).

This trampoline validates the same required/mutual-exclusion preconditions
the op itself enforces (handoff-path required; exactly one of
--criterion-id/--position; --met-text and --unmet-text supplied together) as
CHEAP CLIENT-SIDE USAGE ERRORS, so a caller gets a clear message before any
dispatch — but the op remains the sole authority on the actual resolution,
possession gating, and write; this file never re-implements or weakens any
of it.

Repo root resolves from the target handoff's own directory
(`git -C <dirname(handoff_path)> rev-parse --show-toplevel`), not the process
cwd — same technique as `handoff-backfill-claim-stamp.py` /
`handoff-reconcile-close-terminal.py`.

Exit codes:
    0 — op reported `applied: True`; the JSON-RPC result printed to stdout,
        exactly as `json.dumps(result, ensure_ascii=False)`.
    1 — op-level refusal (`RouteMutationError` with a non-2 envelope
        `exit_code`, e.g. the target already ticked, ambiguous/absent
        criterion_id, out-of-range position, or the possession gate refusing
        without a satisfying `--override-reason`), a transport/engine
        failure, or an unresolvable repo root.
    2 — usage error: missing handoff-path, neither/both of
        --criterion-id/--position supplied, only one of
        --met-text/--unmet-text supplied, a non-integer --position, or the
        op's own usage refusal (envelope `exit_code == 2`, held open for
        parity with the sibling CLI though this op does not currently emit
        that shape).

Negative-spec:
    - Does NOT re-implement checkbox resolution, the possession/claim gate,
      archive-follow resolution, or the stamped correction note — all of
      that lives in `handoff_discharge_criteria.py` (and, by delegation,
      `handoff_correct_body.py`); this file only builds params and prints
      the result.
    - Does NOT default or synthesize `--override-reason` — an omitted flag
      means the param is simply not sent, exactly as the op's own docstring
      describes ("consulted only when...").
    - Does NOT open a UDS socket or read an auth token — routes through
      `cc_invoke.route_mutation()`, a command-type transport, same as every
      other bin/ CLI in this house style.
    - Does NOT batch — one checkbox per call, mirroring the op's own single-
      replacement bound.

Spec backlink: coordinator_core/ops/handoff_discharge_criteria.py — the
pickup/workstream-complete gate interaction its own module docstring
describes (claimed-body immutability vs. the consumed-handoff completeness
gate blocking a close on an unticked checkbox).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

_BIN_DIR = os.path.dirname(os.path.abspath(__file__))

PROG = "handoff-discharge-criteria.py"

_OP = "handoff.discharge_criteria"


_BOOTSTRAP_DONE = False

_BOOTSTRAPPED_NAMES = ("cc_invoke",)


def _bootstrap_cc_invoke() -> None:
    """Bind the `cc_invoke` module (coordinator/bin/lib's dispatch shim) as a
    module-level global, idempotent; safe to call more than once.

    Every function in this file already does its own local `import cc_invoke`
    at its use site — that pattern is unchanged and is what keeps the module
    body inert on both load routes (warm-serve invariant). This binder exists
    ONLY to serve `cc_invoke` as a module ATTRIBUTE via `__getattr__` below,
    for a caller that imports this module without calling `main()` (a test
    monkeypatching `_cli.cc_invoke.route_mutation`, e.g.) and therefore never
    triggers any of those local imports."""
    global _BOOTSTRAP_DONE
    if _BOOTSTRAP_DONE:
        return
    global cc_invoke
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    import cc_invoke as _cc_invoke

    cc_invoke = _cc_invoke
    _BOOTSTRAP_DONE = True


def __getattr__(name: str):
    """PEP 562 hook so a caller reading `cc_invoke` off this module BEFORE
    `main()` has run -- a test monkeypatching `_cli.cc_invoke.route_mutation`,
    or any consumer importing this module rather than executing it -- gets
    the real module lazily instead of an AttributeError.

    NEGATIVE SPEC -- the forced re-run is not belt-and-braces.
    `_bootstrap_cc_invoke()` short-circuits on `_BOOTSTRAP_DONE`, so a name
    that leaves `__dict__` AFTER the bootstrap has run is never rebound by a
    plain call. `mock.patch.object` does exactly that: it reads the name
    through this hook (so the value is not in `__dict__` at enter), sets its
    mock, and on exit `delattr`s rather than restoring -- then probes
    `hasattr`, which lands here with the flag already set. Without the reset
    that probe raises KeyError instead of returning the name."""
    if name in _BOOTSTRAPPED_NAMES:
        _bootstrap_cc_invoke()
        if name not in globals():
            global _BOOTSTRAP_DONE
            _BOOTSTRAP_DONE = False
            _bootstrap_cc_invoke()
        try:
            return globals()[name]
        except KeyError:
            raise AttributeError(
                f"module {__name__!r} has no attribute {name!r}"
            ) from None
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _no_console_kw() -> dict:
    """Lazily resolve the engine root onto sys.path (self-location-first via
    cc_invoke.ensure_engine_on_path), then splat the canonical
    no-console-window kwarg. ``{}`` on any resolution/import failure
    (fail-open). Mirrors handoff-backfill-claim-stamp.py's own helper."""
    try:
        import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
        import cc_invoke

        if cc_invoke.ensure_engine_on_path(__file__) is None:
            return {}
        from coordinator_core.win_portability import no_console_creationflags

        return no_console_creationflags()
    except Exception:
        return {}


def _no_fallback():
    raise RuntimeError(
        f"{PROG}: {_OP} requires the native seam (no bash fallback -- "
        "big-bang cutover); re-run the engine install step or verify "
        "CLAUDE_KLABAUTER_ROOT"
    )


def _resolve_repo_root(handoff_path: str) -> str | None:
    """Resolve repo root from the handoff's own directory, not the process
    cwd (mirrors handoff-backfill-claim-stamp.py::_resolve_repo_root)."""
    handoff_abs = os.path.abspath(handoff_path)
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    import cc_invoke

    if cc_invoke.ensure_engine_on_path(__file__) is None:
        return None
    from coordinator_core.git.repo_root import show_toplevel

    return show_toplevel(cwd=os.path.dirname(handoff_abs))


def cmd_discharge_criteria(
    handoff_path: str,
    criterion_id: str,
    position: str,
    met_text: str,
    unmet_text: str,
    override_reason: str,
) -> int:
    """Validate, dispatch, and print. Usage errors (client-side, cheap) are
    distinguished from op-level refusals and transport failures per the
    module docstring's exit-code contract."""
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    import cc_invoke

    if not handoff_path.strip():
        print(f"{PROG}: <handoff-path> is required", file=sys.stderr)
        return 2

    if bool(criterion_id.strip()) == bool(position.strip()):
        print(
            f"{PROG}: exactly one of --criterion-id or --position is required "
            "(mutually exclusive)",
            file=sys.stderr,
        )
        return 2

    position_value: int | None = None
    if position.strip():
        try:
            position_value = int(position.strip())
        except ValueError:
            print(f"{PROG}: --position must be an integer, got {position!r}", file=sys.stderr)
            return 2
        if position_value < 1:
            print(f"{PROG}: --position must be >= 1 (1-indexed)", file=sys.stderr)
            return 2

    if bool(met_text.strip()) != bool(unmet_text.strip()):
        print(
            f"{PROG}: --met-text and --unmet-text must be supplied together "
            "(only one was given)",
            file=sys.stderr,
        )
        return 2

    repo_root = _resolve_repo_root(handoff_path)
    if not repo_root:
        print(
            f"{PROG}: cannot resolve git repo root from {handoff_path!r}'s "
            "directory — no mutation attempted",
            file=sys.stderr,
        )
        return 1

    params: dict = {"handoff_path": handoff_path}
    if criterion_id.strip():
        params["criterion_id"] = criterion_id.strip()
    if position_value is not None:
        params["position"] = position_value
    if met_text.strip():
        params["met_text"] = met_text.strip()
        params["unmet_text"] = unmet_text.strip()
    if override_reason.strip():
        params["override_reason"] = override_reason.strip()

    try:
        result = cc_invoke.route_mutation(_OP, params, repo_root, _no_fallback)
    except cc_invoke.RouteMutationError as exc:
        envelope = getattr(exc, "result", None)
        if isinstance(envelope, dict) and envelope.get("exit_code") == 2:
            print(f"{PROG}: usage error from {_OP}: {exc}", file=sys.stderr)
            return 2
        print(f"{PROG}: {_OP} refused for {handoff_path!r} — {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(
            f"{PROG}: {_OP} failed for {handoff_path!r} — transport/engine "
            f"failure: {exc}",
            file=sys.stderr,
        )
        return 1

    if not isinstance(result, dict):
        print(
            f"{PROG}: {_OP} returned an unexpected non-dict result: {result!r}",
            file=sys.stderr,
        )
        return 1

    import json

    print(json.dumps(result, ensure_ascii=False))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=PROG)
    p.add_argument("handoff_path")
    p.add_argument(
        "--criterion-id",
        dest="criterion_id",
        default="",
        help="resolve the target checkbox by its AC-N-shaped identity token; "
        "mutually exclusive with --position",
    )
    p.add_argument(
        "--position",
        dest="position",
        default="",
        help="resolve the target checkbox by its 1-indexed ordinal within "
        "the '## Acceptance criteria' section; mutually exclusive with "
        "--criterion-id",
    )
    p.add_argument(
        "--met-text",
        dest="met_text",
        default="",
        help="supplied together with --unmet-text to SPLIT the resolved "
        "checkbox into a met (ticked) line and an unmet (unticked) line, "
        "instead of a plain tick",
    )
    p.add_argument(
        "--unmet-text",
        dest="unmet_text",
        default="",
        help="see --met-text; when the resolved criterion carries an "
        "identity token, this MUST carry that same token",
    )
    p.add_argument(
        "--override-reason",
        dest="override_reason",
        default="",
        help="forwarded verbatim to handoff.correct_body; consulted only "
        "when the calling session is neither the claim holder nor the "
        "authoring session of the target",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        args = _build_parser().parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 2

    return cmd_discharge_criteria(
        args.handoff_path,
        args.criterion_id,
        args.position,
        args.met_text,
        args.unmet_text,
        args.override_reason,
    )


if __name__ == "__main__":
    sys.exit(main())
