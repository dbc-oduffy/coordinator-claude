"""check-posix-exec-assumptions.py — CLI trampoline over
coordinator_core.ops.check_posix_exec_assumptions.

Fleet-wide RED-on-existence guard (PM ruling, 2026-07-28) for POSIX-only
execution assumptions: env-stripped shebang, extensionless `#!`-executable,
and git mode 100755. Ratcheted against a frozen, shrink-only baseline —
fails on any NEW violation or on the baseline file itself having grown.

This file lives colocated inside claude-klabauter, so it imports
coordinator_core directly (no cross-repo resolution needed here). A sibling
repo (e.g. DoE-claude) invokes the SAME engine module via cross-repo import
(`_claude_klabauter_root.resolve_claude_klabauter_root()`) from its own test tier instead of
shelling out to this CLI — see that repo's own wiring for the reason
(DR-047: DoE owns contract, claude-klabauter owns engine; a cross-repo subprocess call
to a sibling's bin/ script is not the sanctioned transport).

Usage:
    check-posix-exec-assumptions[.py] [--root <path>] [--baseline <path>]

    --root      Repo root to scan. Default: `git rev-parse --show-toplevel`
                of cwd -- so this same entrypoint scans claude-klabauter when
                run from here, or ANY other fleet repo when run from there.
    --baseline  Baseline JSON path. Default: <root>/state/posix-exec-baseline.json.

Exit codes:
    0 — no new violations, baseline has not grown.
    1 — at least one new violation, or the baseline file grew since its
        frozen anchor commit (see coordinator_core.ops.check_posix_exec_
        assumptions module docstring § Anchor choice).

Spec backlink: coordinator_core/ops/check_posix_exec_assumptions.py (source-
  of-truth engine module docstring, itself backlinked to DoE-claude
  coordinator/docs/wiki/foreign-platform-path-guard.md)
"""


# --- routing half: this file is now a thin shim over entry_point_shim.run_gate_target ---
from __future__ import annotations

import sys


def main(argv: list[str]) -> int:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from entry_point_shim import run_gate_target

    return run_gate_target("check-posix-exec-assumptions", argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
