# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
coordinator/bin/workday-complete-assemble.py — thin CLI trampoline over
coordinator_core.workday_complete.{brief,apply}.

Purpose: `commands/workday-complete.md` Step 0.95 and Step (apply) invoke
the bareword, settings-home-installed entrypoint
`"${COORDINATOR_SETTINGS_HOME:-...}/bin/workday-complete-assemble" brief`
and `... apply --decisions '<json>'` — the `workday_complete` assembler
(`coordinator_core/workday_complete/brief.py` + `apply.py`) computes the
whole mechanical spine of the daily-close ceremony but, prior to this file,
had no bareword `coordinator/bin/` CLI trampoline through which either half
was reachable outside a Python REPL. This file is that trampoline.

`brief.py` and `apply.py` each already own a complete `main(argv)` (no
shared package-level dispatcher lives under `coordinator_core/
workday_complete/` — unlike `consolidate_assemble`, this package ships no
`__init__.py`); this trampoline's only job is subcommand routing to
whichever submodule's `main(argv)` the caller named, then forwarding argv
verbatim — it does not parse or reinterpret `--decisions` itself.

Usage:
    python3 workday-complete-assemble.py brief
    python3 workday-complete-assemble.py apply [--decisions <json>]

Exit codes (locally scoped to this CLI, NOT inherited — see the contract's
own § Exit-code contract):
    0 — OK, the named subcommand's own `main(argv)` returned 0.
    2 — usage error (missing/unknown subcommand) OR whatever `brief.main`/
        `apply.main` itself returns for a malformed `--decisions` value —
        this trampoline never re-validates argv shape past the subcommand
        token, so a submodule's own usage-error exit code passes through
        unchanged.
    3 — transport failure (CLAUDE_KLABAUTER_ROOT unresolvable or
        `coordinator_core.workday_complete.{brief,apply}` not importable) —
        this trampoline's own transport failure, distinct from any business
        exit code the underlying submodule may compute.

Spec backlink: DoE-claude coordinator/commands/workday-complete.md § Step 0.95, § apply
Spec backlink: claude-klabauter coordinator_core/workday_complete/brief.py
Spec backlink: claude-klabauter coordinator_core/workday_complete/apply.py

Negative-spec: does NOT reimplement the decision-object compute or the
directive-execution loop — both live entirely in the named submodule; this
file is subcommand dispatch only, same posture as `coordinator/bin/
autonomous-verb.py` over `workday_complete.autonomous_verb`.
"""
from __future__ import annotations

import sys
from pathlib import Path

_LIB_DIR = str(Path(__file__).resolve().parent / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_colocated_engine_on_path  # noqa: E402

_USAGE_FAIL = 2
_TRANSPORT_FAIL = 3


def main(argv: list[str]) -> int:
    prog = "workday-complete-assemble"
    if not argv or argv[0] not in ("brief", "apply"):
        print(f"{prog}: usage: {prog} brief|apply [...]", file=sys.stderr)
        return _USAGE_FAIL

    subcmd, rest = argv[0], argv[1:]

    try:
        require_colocated_engine_on_path(__file__)
    except RuntimeError as exc:
        print(f"{prog}: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL

    try:
        if subcmd == "brief":
            from coordinator_core.workday_complete.brief import main as sub_main
        else:
            from coordinator_core.workday_complete.apply import main as sub_main
    except ImportError as exc:
        print(
            f"{prog}: coordinator_core.workday_complete.{subcmd} not importable: {exc}",
            file=sys.stderr,
        )
        return _TRANSPORT_FAIL

    return sub_main(rest)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
