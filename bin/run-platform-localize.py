# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
run-platform-localize.py — CLI trampoline over claude-klabauter
coordinator_core.install.run_platform_localize.

Collapses install.md § Step 9 ("Fire platform-localize once at install
time") into one call — this trampoline owns no logic of its own beyond the
standard CLAUDE_KLABAUTER_ROOT resolve-and-import dance (mirrors
coordinator/bin/ensure-doe-clone.py's own shape 1:1). All install-time
behavior — the in-process ``platform_localize.main()`` call, the
``--check-only`` short-circuit, and the conditional JSON-schema-validation
branch — lives in coordinator_core.install.run_platform_localize; see that
module's own docstring for the full design rationale.

Spec backlink: DoE-claude:pln-extirpate-pasted-code-from-em--0f42e9 § M3
"""

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402


def _import_main():
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.install.run_platform_localize import main as _op_main
    return _op_main


def main() -> None:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"run-platform-localize.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        print("platform_localize: error (see stderr)")
        sys.exit(3)
    except ImportError as exc:
        print(
            f"run-platform-localize.py: coordinator_core.install.run_platform_localize not importable: {exc}",
            file=sys.stderr,
        )
        print("platform_localize: error (see stderr)")
        sys.exit(3)
    sys.exit(op_main(sys.argv[1:]))


if __name__ == "__main__":
    main()
