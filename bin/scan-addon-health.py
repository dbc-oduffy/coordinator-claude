# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
scan-addon-health.sh — CLI trampoline over claude-klabauter
coordinator_core.plugin_health.scan.

Read addon-health sentinel files (`<plugin>/data/doctor-last-run.json`, written
by coordinator_core.plugin_health.sentinel or any sibling plugin's own doctor)
and emit operator notices. Surfaces via /workday-start (--red-and-stale,
default) and /workstream-start (--red-only, plus --check-sentinel-presence for
fresh-install bootstrap).

Modes:
  --red-only                emit lines only for RED verdicts (signal-not-noise)
  --red-and-stale            RED + AMBER + stale (>24h) + missing/absent sentinels (default)
  --check-sentinel-presence  fresh-install bootstrap check (fires at most once per install life)

Output: zero or more `[health] <plugin>: <message>` lines. Exit 0 always
(advisory, never gating). Silent when nothing to report.

Environment: COORDINATOR_PLUGINS_ROOT (default ~/.claude/plugins),
COORDINATOR_CONSUMER_HEALTH_ROOT (default ~/.claude),
COORDINATOR_HEALTH_STALE_SEC (default 86400).

Spec backlink: DoE-claude:pln-bash-to-naked-python-engine-mi-c09292 § T3a-g2/T3b
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

    Plain in-process import, not an RPC invoke — cc_invoke's subprocess-spawn
    transport (cc_invoke()/route()) is deliberately NOT used here.
    """
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.plugin_health.scan import main as _op_main

    return _op_main


def main() -> None:
    # This script's own docstring contract (line 32)
    # says "Exit 0 always (advisory, never gating)". A sys.exit(1) here would
    # abort a caller (/workday-start, /workstream-start --check-sentinel-
    # presence at fresh-install bootstrap — exactly when CLAUDE_KLABAUTER_ROOT is most
    # likely unresolvable) that trusts the "never gating" promise and has no
    # defensive `|| true`. Degrade to a stderr notice and exit 0 instead.
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"scan-addon-health.sh: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(0)
    except ImportError as exc:
        print(
            f"scan-addon-health.sh: coordinator_core.plugin_health.scan not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(0)

    sys.exit(op_main(sys.argv[1:]))


if __name__ == "__main__":
    main()
