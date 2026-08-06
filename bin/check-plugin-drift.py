#!/usr/bin/env python3
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
detected, or CLAUDE_KLABAUTER_ROOT/import resolution failed (fail-loud, same signal
class); 2 — argument error or registry-read failure.

Environment: MACHINE_LOCAL_REGISTRY_DIR, HOME, CURRENT_PYPROJECT_HASH_OVERRIDE
(consumed by the plugin-live-install refresh's post-flight invocation).

Spec backlink: docs/plans/2026-07-15-bash-to-naked-python-engine-migration.md § T3a-g2/T3b
Port of: coordinator/bin/check-plugin-drift.py (dd820339^ recovered pre-stub body)
"""

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402


def _import_main():
    """Resolve CLAUDE_KLABAUTER_ROOT, put it on sys.path, and import the ported CLI entry.

    Reuses cc_invoke's battle-tested CLAUDE_KLABAUTER_ROOT resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it — this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.
    """
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.plugin_health.drift import main as _op_main

    return _op_main


def main() -> None:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"check-plugin-drift.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(1)
    except ImportError as exc:
        print(
            f"check-plugin-drift.py: coordinator_core.plugin_health.drift not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    sys.exit(op_main(sys.argv[1:]))


if __name__ == "__main__":
    main()
