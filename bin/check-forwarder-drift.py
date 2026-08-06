#!/usr/bin/env python3
# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
check-forwarder-drift.py — CLI trampoline over claude-klabauter
coordinator_core.plugin_health.forwarder_drift.

Read-only staleness probe for generated agent-helper bin/ forwarders: compares
the DERIVED forwarder set (a live scan of claude-klabauter's own `coordinator/bin/`)
against the INSTALLED forwarders in the settings-home `bin/` and the
`~/.claude/bin` compat mirror, in both directions. Surfaces daily via
/workday-start Step 1.10 Addon Health, alongside its sibling
`check-plugin-drift.py` (git/venv/SHA drift) and `check-claude-klabauter-doctor-
sentinel.py` (claude-klabauter's own doctor sentinel) — this probe closes the adjacent
gap those two don't cover: a CLI landing in (or removed from) `coordinator/
bin/` with no forwarder regenerated since, because no install has run.

Never fails: mirrors coordinator_core.plugin_health.forwarder_drift's own
WARN-only contract (see that module's docstring for why — install-health-run's
_NATIVE_LEGS legs are fail-loud BY DESIGN because they run only at install
time when derived==installed by construction; this probe runs BETWEEN
installs, where drift is expected transient state, not an install defect).

Usage:
  check-forwarder-drift.py

Exit codes: always 0 (advisory-only — see forwarder_drift.py's module
docstring; `ok=False` in the underlying result means drift was found and is
reported via stdout lines, not a nonzero exit).

Spec backlink: cross-repo/inbox/2026-07-23-claude-central-em-claude-klabauter-pickup-assemble-heads-up.md
Port of: coordinator/bin/check-plugin-drift.py (trampoline pattern)
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
    from coordinator_core.plugin_health.forwarder_drift import main as _op_main

    return _op_main


def main() -> None:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"check-forwarder-drift.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        # Unresolvable claude-klabauter root is a clean skip for this probe, not a
        # failure (see forwarder_drift.py's own resolution-ladder contract) —
        # never fail the calling ceremony.
        sys.exit(0)
    except ImportError as exc:
        print(
            f"check-forwarder-drift.py: coordinator_core.plugin_health.forwarder_drift "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(0)

    sys.exit(op_main(sys.argv[1:]))


if __name__ == "__main__":
    main()
