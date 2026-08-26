"""
publish-time-transform-py — CLI trampoline over claude-klabauter
coordinator_core.publish.time_transform.

Naked-Python successor to `coordinator/bin/publish-time-transform.sh`. Named
with a `-py` suffix (not a same-name collapse of the `.sh`) because this
chunk's build rule is GATED delete: the bash original stays in place, live,
and callers stay repointed to it until the Python port has cleared its
adversarial/golden-diff bar and a follow-on chunk flips callers + deletes
bash. Once that cutover lands, this trampoline is the one that gets renamed
to the bare `publish-time-transform` name (mirroring `handoff-gate-aging` /
`derive-session-hierarchy`'s already-cutover shape) — do not rename it early.

Shebang note: the SHEBANG line above is `#!/usr/bin/env python3`, and correct
for this shape. On Windows, this file's co-located `.cmd` twin wins via
`PATHEXT` when invoked as a bareword, so the shebang is never read there; on
macOS/Linux `python3` is the right interpreter. Caution: callers must invoke
via the extensionless name or a resolved-interpreter prefix, never a bareword
`.py` through git-bash — git-bash DOES honor the shebang and would exec-127
with no `python3` present. See the carve-out in DoE-claude's
coordinator/docs/wiki/bash-on-windows-gotchas.md § Carve-out (cross-repo —
this wiki lives in the DoE-claude repo, not here).

Usage:
  publish-time-transform-py --check PATH
  publish-time-transform-py --fix [--keep-bak] PATH

Exit codes: 0 clean/fixed; 1 hits found (--check) or fix error; 2 usage error;
3 self-corruption (state/environment fault) — see the ported module's own
docstring for the full contract and documented divergences from the bash
oracle (coordinator_core/publish/time_transform.py, claude-klabauter repo).

Spec backlink: DoE-claude:pln-bash-to-naked-python-engine-mi-c09292 § T4a-g3c
Port of: publish-time-transform.sh (DoE 16302166, 2026-07-21)
"""
from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402


def _import_main():
    """Resolve the engine root, put it on sys.path, and import the ported CLI entry.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it — this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.
    """
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.publish.time_transform import main as _op_main

    return _op_main


def main() -> None:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        # Review: code-reviewer P2 — engine-root resolution failure is an
        # environment/install fault, not a CLI usage mistake; the docstring
        # (line 39) reserves exit 3 for exactly this class, distinct from
        # the exit-2 usage-error tier. Was sys.exit(2), misclassifying it.
        print(f"publish-time-transform-py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(3)
    except ImportError as exc:
        print(
            f"publish-time-transform-py: coordinator_core.publish.time_transform not "
            f"importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(3)

    sys.exit(op_main(sys.argv[1:]))


if __name__ == "__main__":
    main()
