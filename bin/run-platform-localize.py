# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
run-platform-localize.py — CLI trampoline over claude-klabauter
coordinator_core.install.run_platform_localize.

Collapses install.md § Step 9 ("Fire platform-localize once at install
time") into one call — this trampoline owns no logic of its own beyond the
standard engine-root resolve-and-import dance (mirrors
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

def _import_main():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.install.run_platform_localize import main as _op_main
    return _op_main


def main(argv: "list[str] | None" = None) -> int:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"run-platform-localize.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        print("platform_localize: error (see stderr)")
        return 3
    except ImportError as exc:
        print(
            f"run-platform-localize.py: coordinator_core.install.run_platform_localize not importable: {exc}",
            file=sys.stderr,
        )
        print("platform_localize: error (see stderr)")
        return 3
    return op_main((sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    sys.exit(main())
