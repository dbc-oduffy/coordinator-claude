
"""Imports `sys.argv[1]` in a fresh subprocess and reports the module/file-open/spawn
cost of that import, so a caller can measure a hook module's own import overhead in
isolation rather than folded into the rest of an already-warm process."""

from __future__ import annotations

import json
import sys


def main(argv: "list[str] | None" = None) -> None:
    argv = sys.argv if argv is None else argv
    if len(argv) < 2:
        print("usage: _hook_cost_probe.py <module>", file=sys.stderr)
        raise SystemExit(2)
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
