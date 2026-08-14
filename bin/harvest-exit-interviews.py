# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""harvest-exit-interviews.py — CLI trampoline over claude-klabauter
coordinator_core.subagent_sandbox.harvest_exit_interviews.

Three DoE plan ACs cite ``harvest_exit_interviews.py`` by filename as an
entrypoint, but the module lives under ``coordinator_core/subagent_sandbox/``
and was invocable only via ``python3 -m coordinator_core.subagent_sandbox.
harvest_exit_interviews`` — no bareword/bin entrypoint existed for it to be
picked up by ``coordinator_core/install/substrate.py``'s
``_derive_agent_helper_target_map`` (which derives the installed-forwarder
set purely from a ``coordinator/bin/`` directory listing). This file is that
thin trampoline: it exposes the module's ``main(argv)`` entrypoint verbatim,
with no reimplemented logic.

Shebang note: the SHEBANG line above is `#!/usr/bin/env python3`, generator-
owned by `gen-launcher-shim.py --ensure-unix`, and correct for this shape. On
Windows, this file's co-located `.cmd` twin wins via `PATHEXT` when invoked as
a bareword, so the shebang is never read there; on macOS/Linux `python3` is the
right interpreter. Caution: callers must invoke via the extensionless name or a
resolved-interpreter prefix, never a bareword `.py` through git-bash — git-bash
DOES honor the shebang and would exec-127 with no `python3` present. See the
carve-out in DoE-claude's coordinator/docs/wiki/bash-on-windows-gotchas.md §
Carve-out (cross-repo — this wiki lives in the DoE-claude repo, not
here).

Exit convention: this is a read-only harvest/report tool, not a commit gate.
On a CLAUDE_KLABAUTER_ROOT resolution or import failure this prints a stderr note and
exits 1 (transport failure is fail-loud here, unlike the advisory
check-harvest-debt.py trampoline, since this tool has no orientation-nudge
posture to fall back to). Once import succeeds, the exit code and stdout/
stderr shape are entirely coordinator_core.subagent_sandbox.
harvest_exit_interviews.main()'s own — see that module's docstring.

Spec backlink: pln-claude-klabauter-subagent-run-report-aut-f51428
"""

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402


def _import_main():
    """Resolve CLAUDE_KLABAUTER_ROOT, put it on sys.path, and import the ported entrypoint.

    Reuses cc_invoke's battle-tested CLAUDE_KLABAUTER_ROOT resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it -- this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.
    """
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.subagent_sandbox.harvest_exit_interviews import main as _op_main

    return _op_main


def main() -> None:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"harvest-exit-interviews.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(1)
    except ImportError as exc:
        print(
            f"harvest-exit-interviews.py: coordinator_core.subagent_sandbox.harvest_exit_interviews "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    sys.exit(op_main(sys.argv[1:]))


if __name__ == "__main__":
    main()
