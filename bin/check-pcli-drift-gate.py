# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
check-pcli-drift-gate.py — CLI trampoline over claude-klabauter
coordinator_core.ops.check_pcli_drift_gate.

Detects divergence between the `dispatch_feed` contract and the captured
live `Workflow` `agent()` option surface (both owned by the sibling DoE
repo's schema files), plus capture staleness and a C7
subagent-catering-resolution.json source-hash check. Direct-import shape
(same as check-harvest-debt.py), deliberately NOT the registered-op
`cc_invoke.route()` trampoline shape (schema-drift-gate.py's shape) — the
detection module is a plain, unregistered coordinator_core.ops module
(mirrors check_import_budget_staleness.py), so there is no op name to route
through. This CLI owns argument parsing and exit-code mapping only; all
detection logic lives in coordinator_core.ops.check_pcli_drift_gate.

Shebang note: the SHEBANG line above is `#!/usr/bin/env python3`, generator-
owned by `gen-launcher-shim.py --ensure-unix`, and correct for this shape. On
Windows, this file's co-located `.cmd` twin wins via `PATHEXT` when invoked as
a bareword, so the shebang is never read there; on macOS/Linux `python3` is the
right interpreter. Caution: callers must invoke via the extensionless name or a
resolved-interpreter prefix, never a bareword `.py` through git-bash — git-bash
DOES honor the shebang and would exec-127 with no `python3` present. See the
carve-out in the sibling DoE repo's coordinator/docs/wiki/bash-on-windows-gotchas.md
§ Carve-out (cross-repo — that wiki lives in the sibling repo, not here).

Exit codes: this is a BLOCKING gate, not an advisory nudge — a transport
failure (the engine root unresolvable, module not importable) maps to
EXIT_ERROR (2), never a silent 0. Business-logic exit codes (0 PASS / 1 FAIL
/ 2 ERROR) are otherwise produced by
coordinator_core.ops.check_pcli_drift_gate.main() once import succeeds —
see that module's own docstring for the full three-way contract.

Usage:
    check-pcli-drift-gate.py

Spec backlink: state/handoffs/2026-08-13-pcli-04-drift-gate.md
Spec backlink: state/debt-backlog/2026-08-13-pcli-04-drift-gate-dispatch-feed-vs-the-bce793e4e50e.yaml
"""


# --- routing half: this file is now a thin shim over entry_point_shim.run_gate_target ---
from __future__ import annotations

import sys


def main(argv: list[str]) -> int:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from entry_point_shim import run_gate_target

    return run_gate_target("check-pcli-drift-gate", argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
