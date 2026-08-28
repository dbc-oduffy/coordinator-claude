# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
check-surface-inline-budget.sh — CLI trampoline over claude-klabauter
coordinator_core.ops.check_surface_inline_budget.

Generalized anti-rebound inline-mechanism budget gate (WARN) for any
converted skill/agent surface — a file path or glob, held to a stored
baseline integer across four inline-mechanism signals (bash_fence,
cc_trusted, narrated_step, inline_payload). See the ported module's
docstring for the full signal rationale (AC-11).

Shebang note: the SHEBANG line above is `#!/usr/bin/env python3`,
generator-owned by `gen-launcher-shim.py --ensure-unix`, and correct for
this shape. On Windows, this file's co-located `.cmd` twin wins via
`PATHEXT` when invoked as a bareword, so the shebang is never read there;
on macOS/Linux `python3` is the right interpreter. Caution: callers must
invoke via the extensionless name or a resolved-interpreter prefix, never a
bareword `.py` through git-bash — git-bash DOES honor the shebang and
would exec-127 with no `python3` present.

Exit codes (parity-critical):
  0 — count within baseline (or no baseline file — safe pre-finalization)
  1 — count exceeds baseline (WARN — non-blocking by caller convention)
  2 — fatal error (no file matched the surface glob, missing args, or
      engine-root/import resolution failed)

Usage: check-surface-inline-budget <surface_glob> <baseline_path>
  <surface_glob>   a file path or glob pattern (e.g.
                    "coordinator/skills/pickup/SKILL.md" or
                    "coordinator/skills/*/SKILL.md")
  <baseline_path>  path to a file holding a single stored baseline integer

Spec backlink: canonical-resolution-engine plan, chunk W1-A3a (2026-07-24)
  — AC-11 anti-rebound inline-mechanism budget gate.
Port of: coordinator_core/ops/check_surface_inline_budget.py
Prior art: check-wsc-inline-budget.py (single-surface, single-signal
  ancestor trampoline — this mirrors its shape).
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
    from coordinator_core.ops.check_surface_inline_budget import main as _op_main

    return _op_main


def main(argv: "list[str] | None" = None) -> int:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"check-surface-inline-budget.sh: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return 2
    except ImportError as exc:
        print(
            f"check-surface-inline-budget.sh: coordinator_core.ops.check_surface_inline_budget not importable: {exc}",
            file=sys.stderr,
        )
        return 2

    return op_main((sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    sys.exit(main())
