# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
capture-fan-out-threshold.sh — CLI trampoline over claude-klabauter
coordinator_core.ops.capture_fan_out_threshold.

Finish-strangler port (DR-059): the bash implementation (idempotent
cores-scaled fan-out large-wave threshold capture into the machine-local
registry — 100 lines) has been fully ported to
coordinator_core/ops/capture_fan_out_threshold.py (co-located pytest:
test_capture_fan_out_threshold.py). This file is now a thin DoE-side
(contract) trampoline over that claude-klabauter (engine) module, per DR-047 (DoE owns
contract/generator, claude-klabauter owns engine).

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

Filename intentionally KEEPS the `.sh` suffix (unlike coordinator-auto-push,
which dropped it) — three call sites (install-maximalist.py Step 8,
commands/install.md's documented `bash .../capture-fan-out-threshold.sh`
invocation lines, and capture-fan-out-threshold.test.sh's own
`"${SCRIPT_DIR}/capture-fan-out-threshold.sh"` path) hardcode the `.sh`
suffix; the polyglot shebang mechanism works identically regardless of
filename, so keeping the suffix avoids three caller edits for zero
functional benefit.

Exit convention: install-maximalist.py calls this via `run_required` — a
FAIL-LOUD gate (stops the install, non-idempotent to skip past). Unlike
coordinator-auto-push (a never-block hot-path hook that always exits 0),
this is a config-writer gate script: CLAUDE_KLABAUTER_ROOT resolution failure or an
import failure here MUST propagate as a non-zero exit so the install phase
fails loud rather than silently skipping the threshold capture.

Spec backlink: DoE-claude:pln-bash-to-naked-python-engine-mi-c09292

DR-276: routed through `coordinator_core.cli_entry.run_op_main` rather than a
plain in-process `import ... as _op_main` + `sys.exit(op_main(argv))` tail, so
any paths the op declares via `declare_write` become a session scope-touch
claim (this op currently declares none — it writes only through the external
`machine-local` registry CLI, never a repo-relative file — so the practical
effect today is zero declared paths, not a behavior change).
"""

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402


def _import_run_op_main():
    """Resolve CLAUDE_KLABAUTER_ROOT, put it on sys.path, and import `run_op_main`.

    Reuses cc_invoke's battle-tested CLAUDE_KLABAUTER_ROOT resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it -- this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.
    """
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main() -> None:
    try:
        run_op_main = _import_run_op_main()
    except RuntimeError as exc:
        print(
            f"capture-fan-out-threshold.sh: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)
    except ImportError as exc:
        print(
            f"capture-fan-out-threshold.sh: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        code = run_op_main("coordinator_core.ops.capture_fan_out_threshold", sys.argv[1:])
    except ImportError as exc:
        print(
            f"capture-fan-out-threshold.sh: coordinator_core.ops.capture_fan_out_threshold "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    sys.exit(code)


if __name__ == "__main__":
    main()
