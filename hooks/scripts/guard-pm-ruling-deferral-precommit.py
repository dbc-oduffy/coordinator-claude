# guard-not-a-hook-entrypoint
# Native git pre-commit gate wrapper, not a hooks.json entrypoint.
"""Native git pre-commit gate: run `coordinator/bin/check-pm-ruling-gate.py --staged`.

Refuses a commit whose added plan/DR/handoff lines defer to the PM on a topic an accepted PM
ruling settles, defer without naming a surfaced ask, or reverse a cited ruling without a newer
`pm_turn:`. The decision logic lives in the check; this wrapper only runs it with the hook's cwd
(git runs pre-commit at the worktree top level) and the inherited git environment
(`GIT_INDEX_FILE` stays inherited so a pathspec commit is checked against its own index), relays
its output, and maps its exit code.

Exit contract: check exit 0 -> 0; exit 1 (refusal) -> 1; any other code or a launch failure
(the check could not run) -> 1 fail-closed with a named reason. The registry's `override_env`
(COORDINATOR_OVERRIDE_PRECOMMIT_PM_RULING_GATE) is honored by the hook body around this wrapper,
not here.

Engine commits run no git hook; the engine route for this gate is owed by claude-klabauter.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from _win_portability import no_console_spawn_kwargs  # noqa: E402

_CHECK = _SCRIPTS.parent.parent / "bin" / "check-pm-ruling-gate.py"
_TAG = "[pm-ruling-deferral-precommit-guard]"


def run_check(check: Path = _CHECK) -> int:
    """Run the check on the staged set; relay its output; return 0 or 1 only."""
    if not check.is_file():
        print(f"{_TAG} cannot run: {check} is missing; restore it from git.", file=sys.stderr)
        return 1
    try:
        proc = subprocess.run(
            [sys.executable, str(check), "--staged"],
            check=False,
            capture_output=True,
            **no_console_spawn_kwargs(),
        )
    except OSError as exc:
        print(f"{_TAG} cannot run: launching {check} failed: {exc}", file=sys.stderr)
        return 1
    # Re-emitted rather than inherited: a console-less child on Windows gets no std handles.
    for data, stream in ((proc.stdout, sys.stdout), (proc.stderr, sys.stderr)):
        if data:
            stream.write(data.decode("utf-8", "replace"))
            stream.flush()
    if proc.returncode == 0:
        return 0
    if proc.returncode == 1:
        print(
            f"{_TAG} refused: an added line defers to the PM on a settled ruling, names no ask, "
            "or reverses a ruling without a newer pm_turn. See "
            "coordinator/docs/wiki/doctrine-authoring/pm-ruling-gate.md.",
            file=sys.stderr,
        )
        return 1
    print(
        f"{_TAG} cannot run: the check exited {proc.returncode} (could not check); "
        "blocking rather than letting an unchecked commit through.",
        file=sys.stderr,
    )
    return 1


def main() -> int:
    return run_check()


if __name__ == "__main__":
    sys.exit(main())
