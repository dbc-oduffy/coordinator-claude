# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""check-sidecar-fill.py — CLI trampoline over claude-klabauter
coordinator_core.subagent_sandbox.detect_unfilled_sidecar.

An EM whose dispatched agent went idle (named-teammate final text does not
route back — harness behaviour, not ours to fix) runs this against that
session's sidecar directory to tell "wrote nothing" apart from "wrote fine"
without a manual git-diff-and-eyeball pass. Exit 0: nothing flagged. Exit
1: at least one sidecar is still status: open with no agent-authored body
content — reconstruct from git diff / tests before trusting silence.

    check-sidecar-fill --session <session_id>
    check-sidecar-fill --path state/subagent-share/<session>/<file>.md

Shebang note: line 1 above is the retired-shebang placeholder comment (see
POSIX-EXEC-ASSUMPTION-GUARD, PM ruling 2026-07-28) -- there is no live
`#!/usr/bin/env python3` line in this file. On Windows, this file's
co-located `.cmd` twin wins via `PATHEXT` when invoked as a bareword; on
macOS/Linux the `.py` extension has no exec bit and must be invoked with an
explicit `python3` prefix. Caution: never invoke a bareword `.py` through
git-bash expecting shebang dispatch — there isn't one, and git-bash would
exec-127 with no `python3` present. See the carve-out in the doctrine repo's
coordinator/docs/wiki/bash-on-windows-gotchas.md § Carve-out (cross-repo —
this wiki does not live here).

Exit convention: this is a read-only diagnostic, not a commit gate. On a
engine-root resolution or import failure, or an unexpected exception once
inside detect_unfilled_sidecar.main() itself, this prints a stderr note and
exits 1 (fail-loud transport failure, since a silent 0 here would look
identical to "nothing flagged" and defeat the tool's own purpose). Absent
such a failure, the exit code and stdout/stderr shape are entirely
coordinator_core.subagent_sandbox.detect_unfilled_sidecar.main()'s own.

Spec backlink: dispatching EM's 2026-08-15 break-class chunk (subagent-share
sidecar detection gap) — see that module's own docstring for the incident.
"""

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402


def _import_main():
    """Resolve the engine root, put it on sys.path, and import the ported entrypoint.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it -- this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.
    """
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.subagent_sandbox.detect_unfilled_sidecar import main as _op_main

    return _op_main


def main() -> None:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"check-sidecar-fill.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(1)
    except ImportError as exc:
        print(
            f"check-sidecar-fill.py: coordinator_core.subagent_sandbox.detect_unfilled_sidecar "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        sys.exit(op_main(sys.argv[1:]))
    except SystemExit:
        raise
    except Exception as exc:
        print(
            f"check-sidecar-fill.py: detect_unfilled_sidecar.main() failed: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
