# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
check-wsc-inline-budget.sh — CLI trampoline over claude-klabauter
coordinator_core.ops.check_wsc_inline_budget.

Gate on inline bash-block count in workstream-complete/SKILL.md. Counts
```bash fenced code blocks and compares against a stored baseline integer —
a proxy for "mechanism logic that should live in a bin/wsc-*.sh script
instead of inline in the skill." WARNs when the count grows.

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

Exit codes (parity-critical — workweek-complete.md:289 pipes through
`2>&1 | tail -1`, which masks the exit; direct callers must opt in to
non-blocking explicitly, e.g. `check-wsc-inline-budget.sh || true`):
  0 — count within baseline (or no baseline file — safe to ship pre-finalization)
  1 — count exceeds baseline (WARN — non-blocking by caller convention)
  2 — fatal error (SKILL.md not found, or CLAUDE_KLABAUTER_ROOT/import resolution failed)

Env overrides (for testing — mirrors the retired bash script's contract):
  WSC_SKILL_PATH     — substitute a different SKILL.md path
  WSC_BASELINE_FILE  — substitute a different baseline file path

Spec backlink: wsc-asic task (2026-06-30) / skill-step-parallelization.md § wsc wiring rule
Port of: check-wsc-inline-budget.sh (DoE b5a4192c, 2026-07-20)
"""

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402


def _import_run_op_main():
    """Resolve CLAUDE_KLABAUTER_ROOT, put it on sys.path, and import `run_op_main`.

    Reuses cc_invoke's battle-tested CLAUDE_KLABAUTER_ROOT resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it — this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.

    DR-276: the op is run through `coordinator_core.cli_entry.run_op_main`
    rather than by calling its `main` directly, so any path it declares via
    `declare_write` becomes a session scope-touch claim instead of an
    unclaimed orphan at the `scoped_git_commit` sink.
    """
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def _resolve_default_paths() -> tuple[str, str]:
    """Mirror the bash oracle's default-path derivation exactly.

    SCRIPT_DIR = this file's own directory; COORDINATOR_DIR = its parent.
    WSC_SKILL_PATH defaults to COORDINATOR_DIR/skills/workstream-complete/SKILL.md;
    WSC_BASELINE_FILE defaults to SCRIPT_DIR/.wsc-inline-budget-baseline.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    coordinator_dir = os.path.dirname(script_dir)
    skill_path = os.environ.get(
        "WSC_SKILL_PATH",
        os.path.join(coordinator_dir, "skills", "workstream-complete", "SKILL.md"),
    )
    baseline_file = os.environ.get(
        "WSC_BASELINE_FILE",
        os.path.join(script_dir, ".wsc-inline-budget-baseline"),
    )
    return skill_path, baseline_file


def main() -> None:
    try:
        run_op_main = _import_run_op_main()
    except RuntimeError as exc:
        print(f"check-wsc-inline-budget.sh: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(2)
    except ImportError as exc:
        print(
            f"check-wsc-inline-budget.sh: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)

    skill_path, baseline_file = _resolve_default_paths()
    try:
        code = run_op_main("coordinator_core.ops.check_wsc_inline_budget", [skill_path, baseline_file])
    except ImportError as exc:
        print(
            f"check-wsc-inline-budget.sh: coordinator_core.ops.check_wsc_inline_budget not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(code)


if __name__ == "__main__":
    main()
