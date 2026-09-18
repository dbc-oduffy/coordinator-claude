"""
coordinator.bin._hook_cost_probe -- fresh-interpreter structural-cost probe for one arm of one
hook class, run as a child process by measure-hook-class-cost.py (C2).

Ported from DoE-claude `coordinator/bin/_hook_cost_probe.py` (W3-C1,
`docs/plans/2026-09-18-doe-holds-no-scripts.md`) -- mechanical move, no behavioural change. No
path resolution here at all (§ Path resolution): the module imports its target by name only,
never touches `__file__`. `_`-prefixed, so the launcher map excludes it
(`substrate.py :: _derive_agent_helper_target_map`) -- it is a helper spawned by
`measure-hook-class-cost.py`, not a CLI in its own right.

Run as `python3 _hook_cost_probe.py <entrypoint-module>`. Imports `entrypoint` and prints one
JSON line: `{"module_count", "own_module_count", "file_open_count", "spawn_count"}`.

Isolation is load-bearing, same reasoning as claude-klabauter's
`coordinator_core.benchmarks._import_probe`: an in-process measurement after a sibling import
has already populated `sys.modules` silently undercounts the delta, and file-open/spawn counts
additionally require nothing to have opened a file or spawned a process before the audit hooks
below are installed -- which is only true this early, in a fresh interpreter, before the target
entrypoint is imported.

Spec backlink: pln-the-doe-side-of-the-warm-engin-a6876d chunk C2 (AC2, AC3).
"""

from __future__ import annotations

import json
import sys


def main(argv: "list[str] | None" = None) -> None:
    argv = sys.argv if argv is None else argv
    target = argv[1]

    file_open_count = 0
    spawn_count = 0

    def _audit_hook(event: str, _args: tuple) -> None:
        nonlocal file_open_count, spawn_count
        if event in ("open", "os.open"):
            file_open_count += 1
        elif event in ("os.posix_spawn", "os.spawnv", "subprocess.Popen"):
            spawn_count += 1

    sys.addaudithook(_audit_hook)

    before = set(sys.modules)
    __import__(target)
    after = set(sys.modules)
    delta = after - before
    own_module_count = len([m for m in delta if m.split(".", 1)[0] == "coordinator_core"])

    print(
        json.dumps(
            {
                "module_count": len(delta),
                "own_module_count": own_module_count,
                "file_open_count": file_open_count,
                "spawn_count": spawn_count,
            }
        )
    )


if __name__ == "__main__":
    main()
