# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
check-plugin-drift.py — CLI trampoline over claude-klabauter
coordinator_core.plugin_health.drift.

Read-only drift probe for registered plugin live installs (git-state, venv-state,
SHA-sentinel). Surfaces daily via /workday-start Step 1.10 Addon Health.

IMPORTANT — this trampoline replaces an 8-line always-fail TEST STUB that had
silently occupied this path since commit dd820339 ("safety commit", 2026-07-14),
breaking the daily drift-check for every registered plugin. The real ~977-line
probe body was recovered from dd820339^ and ported wholesale into claude-klabauter's
coordinator_core.plugin_health.drift — this file is the restored + ported
replacement, not a fresh implementation.

Usage:
  check-plugin-drift.py [<plugin>] [--check-clean-only]

Exit codes: 0 — clean (no drift, or no plugin.mirrors registered); 1 — drift
detected, or engine-root/import resolution failed (fail-loud, same signal
class); 2 — argument error or registry-read failure.

Environment: MACHINE_LOCAL_REGISTRY_DIR, HOME, CURRENT_PYPROJECT_HASH_OVERRIDE
(consumed by the plugin-live-install refresh's post-flight invocation).

Spec backlink: DoE-claude:pln-bash-to-naked-python-engine-mi-c09292 § T3a-g2/T3b
Port of: coordinator/bin/check-plugin-drift.py (dd820339^ recovered pre-stub body)
"""

from __future__ import annotations

import os
import sys


def _import_main():
    """Resolve the engine root, put it on sys.path, and import the ported CLI entry.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it — this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.
    """
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.plugin_health.drift import main as _op_main

    return _op_main


def main(argv: "list[str] | None" = None) -> int:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"check-plugin-drift.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return 1
    except ImportError as exc:
        print(
            f"check-plugin-drift.py: coordinator_core.plugin_health.drift not importable: {exc}",
            file=sys.stderr,
        )
        return 1

    return op_main((sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    sys.exit(main())
