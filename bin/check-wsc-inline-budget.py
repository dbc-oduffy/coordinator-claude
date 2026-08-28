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
  2 — fatal error (SKILL.md not found, or engine-root/import resolution failed)

Env overrides (for testing — mirrors the retired bash script's contract):
  WSC_SKILL_PATH     — substitute a different SKILL.md path
  WSC_BASELINE_FILE  — substitute a different baseline file path

Spec backlink: wsc-asic task (2026-06-30) / skill-step-parallelization.md § wsc wiring rule
Port of: check-wsc-inline-budget.sh (DoE b5a4192c, 2026-07-20)
"""

from __future__ import annotations

import os
import sys


def _import_run_op_main():
    """Resolve the engine root, put it on sys.path, and import `run_op_main`.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it — this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.

    DR-276: the op is run through `coordinator_core.cli_entry.run_op_main`
    rather than by calling its `main` directly, so any path it declares via
    `declare_write` becomes a session scope-touch claim instead of an
    unclaimed orphan at the `scoped_git_commit` sink.
    """
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def _default_skill_path() -> str:
    """Resolve workstream-complete/SKILL.md via `coordinator_data_root.data_root()`'s
    co-located/codename-free/DoE-resident ladder, not a bare `__file__`-relative walk.

    Skills are a coordinator-claude (DoE-claude) discovery-resolved surface, not
    part of this engine repo (CLAUDE.md: "Discovery-resolved surfaces (skills,
    plugins, hooks) belong in coordinator-claude, not here") — the prior
    `<this file's dir>/../skills/...` derivation assumed skills/ was co-located
    with this CLI's own bin/ dir, which is only ever true if someone materializes
    a skills/ tree inside claude-klabauter (an inversion of the tri-plane boundary; do not
    do that — see the dispatch note this fix responds to). `data_root("skills")`
    is the shared resolver every other cross-plane data lookup in this repo
    already uses (see check-multi-event-hook-hardcoded-event.py's
    `_default_hooks_json()`, same shape) — resolved lazily so an explicit
    WSC_SKILL_PATH override never pays this cost.
    """
    from coordinator_data_root import data_root

    return str(data_root("skills") / "workstream-complete" / "SKILL.md")


def _resolve_default_paths() -> tuple[str, str]:
    """Resolve WSC_SKILL_PATH and WSC_BASELINE_FILE, honoring env overrides.

    WSC_SKILL_PATH defaults to `_default_skill_path()` (the settings-home/
    DoE-root ladder — see that function's docstring); WSC_BASELINE_FILE defaults
    to SCRIPT_DIR/.wsc-inline-budget-baseline (this repo's own state, unaffected
    by the skills cross-plane resolution).

    An explicitly-set-but-empty/whitespace WSC_SKILL_PATH is treated as unset
    (`.strip() or _default_skill_path()`) and falls through to the default
    resolver rather than being passed through as an empty path — a
    behavior improvement over passing an empty string straight through, not
    a regression (no caller sets WSC_SKILL_PATH="" deliberately).

    Raises RuntimeError, naming which rungs were tried, if WSC_SKILL_PATH is
    unset and `data_root("skills")` cannot resolve a skills/ directory on this
    box (e.g. a consumer repo whose coordinator-claude mirror lacks it).
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    skill_path = os.environ.get("WSC_SKILL_PATH", "").strip() or _default_skill_path()
    baseline_file = os.environ.get(
        "WSC_BASELINE_FILE",
        os.path.join(script_dir, ".wsc-inline-budget-baseline"),
    )
    return skill_path, baseline_file


def main(argv: "list[str] | None" = None) -> int:
    del argv  # this CLI takes no arguments; argv accepted for the warm-call contract
    try:
        run_op_main = _import_run_op_main()
    except RuntimeError as exc:
        print(f"check-wsc-inline-budget.sh: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return 2
    except ImportError as exc:
        print(
            f"check-wsc-inline-budget.sh: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        return 2

    try:
        skill_path, baseline_file = _resolve_default_paths()
    except RuntimeError as exc:
        print(f"check-wsc-inline-budget.sh: could not resolve workstream-complete/SKILL.md: {exc}", file=sys.stderr)
        return 2

    try:
        code = run_op_main("coordinator_core.ops.check_wsc_inline_budget", [skill_path, baseline_file])
    except ImportError as exc:
        print(
            f"check-wsc-inline-budget.sh: coordinator_core.ops.check_wsc_inline_budget not importable: {exc}",
            file=sys.stderr,
        )
        return 2

    return code


if __name__ == "__main__":
    sys.exit(main())
