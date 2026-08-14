# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
check-persona-slug-leak.py — CLI trampoline over claude-klabauter
coordinator_core.publish.time_transform.main_check_persona_slug_leak.

Finish-strangler port (DR-059): the bash implementation (lowercase/compound
persona-slug leak guard — scans a scratch publish tree for residual
lowercase persona slugs and the compound-glued finding literal that the
retired publish-time-transform.sh's (DoE 16302166, 2026-07-21) TitleCase-only
\\b-bounded matching historically missed) has been ported to
coordinator_core/publish/time_transform.py
(check_persona_slug_leak/main_check_persona_slug_leak, sibling to that
module's pre-existing --check/--fix drivers), per DR-047 (DoE owns
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

Exit-code contract preserved from the bash oracle:
    0 — clean (no unheld lowercase/compound persona-slug hits)
    1 — leak found (file:line report written to stderr)
    2 — usage error (bad arg count, target-dir not found)

This is a GATE script (used as a preflight check before scratch-publish, see
percolate-preflight-scratch-publish.py) — fail-loud on claude-klabauter-link failure
(exit 1, same "found a problem" signal as a genuine leak) rather than the
never-block auto-push shape (which always exits 0). A silently-skipped
persona-slug guard is a publish-safety regression, not a benign no-op.

Spec backlink: DoE-claude:pln-bash-polyglot-clean-slate-full-5c71ee
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
    from coordinator_core.publish.time_transform import main_check_persona_slug_leak as _op_main

    return _op_main


def main() -> None:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"check-persona-slug-leak.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(1)
    except ImportError as exc:
        print(
            f"check-persona-slug-leak.py: coordinator_core.publish.time_transform not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    sys.exit(op_main(sys.argv[1:]))


if __name__ == "__main__":
    main()
