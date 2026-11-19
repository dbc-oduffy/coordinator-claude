# guard-not-a-hook-entrypoint
# Native git pre-commit gate wrapper, not a hooks.json entrypoint.
"""Native git pre-commit gate: run the published engine's
`coordinator-precommit-abs-path-check` against the staged changes.

The gate lives in the claude-klabauter engine root, not in this tree, so it is
located at commit time through `_engine_root.resolve_claude_klabauter_root()` — never a
repo-relative `coordinator/bin` path. It runs under the interpreter that runs
this wrapper (the engine script is Python, invoked via an explicit interpreter,
never shebang-exec), with the hook's cwd (git runs pre-commit at the worktree
top level); its stdout and stderr are relayed, so the engine's own banner and
`file:line` report reach the committer.

Fail-closed: an unresolvable engine root or an absent gate script exits 1 with
a named reason; the engine gate's own exit code is propagated. The registry's
`override_env` (COORDINATOR_OVERRIDE_PRECOMMIT_ABS_PATH) is honored by the hook
body around this wrapper, not here.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from _win_portability import no_console_spawn_kwargs  # noqa: E402

_GATE_NAME = "coordinator-precommit-abs-path-check"
_TAG = "[abs-path-precommit-guard]"


def main() -> int:
    import _engine_root

    root = _engine_root.resolve_claude_klabauter_root()
    if not root:
        print(
            f"{_TAG} cannot run: no stamped claude-klabauter engine is registered "
            "(registry key repos.claude_klabauter). Fetch "
            "https://github.com/dbc-oduffy/claude-klabauter and register it (INSTALL.md Step 1e).",
            file=sys.stderr,
        )
        return 1
    gate = Path(root) / "coordinator" / "bin" / _GATE_NAME
    if not gate.is_file():
        print(
            f"{_TAG} cannot run: published engine {root} has no coordinator/bin/{_GATE_NAME}; "
            "refresh the claude-klabauter engine.",
            file=sys.stderr,
        )
        return 1
    try:
        proc = subprocess.run(
            [sys.executable, str(gate)],
            check=False,
            capture_output=True,
            **no_console_spawn_kwargs(),
        )
    except OSError as exc:
        print(f"{_TAG} cannot run: launching {gate} failed: {exc}", file=sys.stderr)
        return 1
    # Re-emitted rather than inherited: a console-less child on Windows gets no std handles.
    for data, stream in ((proc.stdout, sys.stdout), (proc.stderr, sys.stderr)):
        if data:
            stream.write(data.decode("utf-8", "replace"))
            stream.flush()
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
