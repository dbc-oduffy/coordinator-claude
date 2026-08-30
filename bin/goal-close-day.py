# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""goal-close-day.py — CLI trampoline over claude-klabauter's goal.close_day_apply op
(coordinator_core/ops/goal_close_day.py).

Purpose: the `coordinator/bin/` door the `/workday-complete` day-goal
close-out directive (`d_goal_close_day`,
`coordinator_core.workday_complete.brief`'s `CONSUMES_MANIFEST`, C4)
dispatches through — `goal_close_day.py` is an OP, not a bin CLI, and
nothing in C1-C3 created this door. This is a thin door only: it parses
`--decisions <json>` into the op's params dict and spawns the op via
`coordinator/bin/lib/cc_invoke.py`'s `cc_invoke()` (same non-bare
envelope-unwrap transport `set-goal-kr-status.py`/`reassess-goal-krs`
use) — it does NOT reimplement the read-and-collapse, the re-append, or
the runtime-postcondition supersession check. Exactly one implementation
of the close-out write algorithm exists in the repo:
`coordinator_core.ops.goal_close_day.close_day_goals`.

Usage:
    goal-close-day.py --decisions <json>

Options:
    --decisions <json>  A JSON object `{goal_id: "done"|"dropped"|...}`
                         (DEC-1: any value other than exactly "done" closes
                         "dropped" — enforced by the op, not this door).
                         Optional; an absent or empty `{}` decisions map
                         writes NOTHING (DEC-2) — the op returns
                         `{"closed": []}` before touching disk rather than
                         this door special-casing the empty case itself.

Exit codes:
    0 — success; the op's bare result (`{"closed": [...]}`) printed to
        stdout as JSON.
    1 — client-side argument error (malformed `--decisions` JSON).
    2 — everything else: unresolvable git repo root for the cc_invoke
        spawn, any cc_invoke transport/op failure (op-level ValueError
        such as a goal_id with no open in-scope wire row,
        GoalCloseDayLostSupersession on a lost clock-skew collapse, or a
        malformed envelope), or an in-envelope refusal (non-zero
        'exit_code' / non-empty 'error') that cc_invoke's transport-only
        ladder returns as an ordinary bare result rather than raising —
        inspected here via cc_invoke.mutation_refusal_message() (DR-215
        exit_code trap).

Spec backlink: pln-day-scoped-goal-close-out-life-69a25c § C4
"""

from __future__ import annotations

import json
import os
import sys

def _parse_args(argv: list[str]) -> dict:
    decisions_raw = ""

    i = 0
    n = len(argv)
    while i < n:
        arg = argv[i]
        if arg == "--decisions":
            if i + 1 >= n:
                print("ERROR: --decisions requires an argument", file=sys.stderr)
                sys.exit(1)
            decisions_raw = argv[i + 1]
            i += 2
        elif arg in ("--help", "-h"):
            sys.stdout.write(__doc__ or "")
            sys.exit(0)
        else:
            print(f"ERROR: Unknown argument: {arg}", file=sys.stderr)
            sys.exit(1)

    decisions: dict = {}
    if decisions_raw:
        try:
            parsed = json.loads(decisions_raw)
        except json.JSONDecodeError as exc:
            print(f"ERROR: --decisions is not valid JSON: {exc}", file=sys.stderr)
            sys.exit(1)
        if not isinstance(parsed, dict):
            print("ERROR: --decisions must be a JSON object", file=sys.stderr)
            sys.exit(1)
        decisions = parsed

    return {"decisions": decisions}


_BOOTSTRAP_NAMES = ("cc_invoke", "mutation_refusal_message", "resolve_checked_repo_root")


def _bootstrap_imports() -> None:
    """Bind every non-stdlib dependency this door needs at module scope
    (C6k import-motion: the module body stays inert on both the warm door
    and the un-bootstrapped settings-home forwarder load routes). Idempotent
    by construction: a name already bound (via a prior call, or a test
    reaching for `mod.cc_invoke` ahead of calling `main()`) is left alone
    rather than clobbered by a real import.
    """
    if all(n in globals() for n in _BOOTSTRAP_NAMES):
        return

    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import cc_invoke as _cc_invoke, mutation_refusal_message as _mrm
    from repo_identity import resolve_checked_repo_root as _rccr

    for _name, _value in (
        ("cc_invoke", _cc_invoke),
        ("mutation_refusal_message", _mrm),
        ("resolve_checked_repo_root", _rccr),
    ):
        globals().setdefault(_name, _value)


def __getattr__(name: str):
    """PEP 562 hook so a caller reaching for a bootstrapped name (`cc_invoke`,
    `mutation_refusal_message`, `resolve_checked_repo_root`) before `main()`
    has run -- this file's own test suite patches these as module attributes
    ahead of calling `mod.main()` -- triggers `_bootstrap_imports()` lazily
    rather than finding the name absent.

    NEGATIVE SPEC -- the bootstrap guard checks ALL of `_BOOTSTRAP_NAMES`,
    not a single sentinel: a caller's `mock.patch.object` of just one
    bootstrapped name (e.g. `cc_invoke`) leaves the others unbound, and the
    all-names guard makes `_bootstrap_imports()` re-run. The re-run publishes
    each freshly-imported name via `globals().setdefault(...)`, so it binds
    exactly the still-missing names and leaves the caller's patched name
    untouched -- it does NOT rebind every name in `_BOOTSTRAP_NAMES`. No
    pop/restore snapshot is needed because a partially-bound state is never
    mistaken for a fully-bound one.
    """
    if name in _BOOTSTRAP_NAMES:
        _bootstrap_imports()
        try:
            return globals()[name]
        except KeyError:
            raise AttributeError(
                f"module {__name__!r} has no attribute {name!r}"
            ) from None
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def main(argv: list[str]) -> int:
    _bootstrap_imports()

    parsed = _parse_args(argv)

    cwd_repo_root, verdict = resolve_checked_repo_root(explicit_root=None)
    if cwd_repo_root is None:
        # No git root resolved from cwd at all -- distinct from the
        # MISMATCH identity gate below (positive evidence of a DIFFERENT
        # real repo). This is "nowhere to write"; refusing here is not the
        # AC4 "UNRESOLVED never refuses" carve-out being violated.
        print(f"goal-close-day: cannot resolve git repo root from {os.getcwd()}", file=sys.stderr)
        return 2
    if verdict["verdict"] == "MISMATCH":
        # DR-277 named carve-out: this door dispatches goal.close_day_apply,
        # which writes closed-goal rows into cwd_repo_root's state tree
        # (coordinator_core/ops/goal_close_day.py::close_day_goals) -- a
        # genuine WRITER, not a diagnostic read. Refuse rather than write
        # into a foreign tree. UNRESOLVED never refuses (AC4).
        print(verdict["message"], file=sys.stderr)
        return 2

    try:
        result = cc_invoke("goal.close_day_apply", parsed, cwd_repo_root)
    except RuntimeError as exc:
        print(f"goal-close-day: {exc}", file=sys.stderr)
        return 2

    message = mutation_refusal_message("goal.close_day_apply", result)
    if message is not None:
        print(f"goal-close-day: {message}", file=sys.stderr)
        return 2

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
