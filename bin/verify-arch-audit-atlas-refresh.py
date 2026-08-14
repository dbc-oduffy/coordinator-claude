# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""verify-arch-audit-atlas-refresh.py — CLI trampoline over claude-klabauter coordinator_core.ops.verify_arch_audit_atlas_refresh.

Pre-commit gate helper for /architecture-audit Step 6.5. Verifies that the
targeted-system atlas page is being refreshed (Branch A) or asserted current
(Branch B) as part of the closeout commit, reading STAGED content only (never
HEAD) plus the intended commit-message file. Always exits 0 — informational,
caller decides whether to abort — emitting a verbose `FAIL:` message on
stdout when neither branch is satisfied.
"""
# verify-arch-audit-atlas-refresh.py — CLI trampoline over claude-klabauter
# coordinator_core.ops.verify_arch_audit_atlas_refresh.
#
# Pre-commit gate helper for /architecture-audit Step 6.5. Verifies that the
# targeted-system atlas page is being refreshed (Branch A) or asserted
# current (Branch B) as part of the closeout commit.
#
# Spec backlink: docs/plans/2026-06-04-architecture-audit-atlas-refresh-gate.md § C1
# Spec backlink: docs/plans/2026-06-08-atlas-attested-clock-split.md (clock split)
#
# Pre-commit gate: reads STAGED content via `git show :<path>` and
# `git diff --cached -- <path>`. Does NOT read HEAD. Reads the intended
# commit-message file ($3 or .git/COMMIT_EDITMSG).
#
# Behavior:
#   - SKIP   — no atlas page exists for <TARGET_SYSTEM>
#   - PASS branch=A — staged body diff AND staged last_mapped == AUDIT_DATE
#                     AND staged last_attested == AUDIT_DATE
#   - PASS branch=B — commit-msg contains `atlas-current-as-of:<AUDIT_DATE>`
#                     AND staged last_attested == AUDIT_DATE
#                     AND zero staged body delta AND last_mapped UNCHANGED
#   - FAIL — neither branch satisfied; verbatim multi-line message emitted
#
# Exit code: always 0 (informational — caller decides whether to abort),
# INCLUDING on a CLAUDE_KLABAUTER_ROOT resolution or import (transport) failure — this
# is a never-block-shaped gate (mirrors the bash oracle's own always-exit-0
# contract), so a claude-klabauter-link failure degrades to a stdout `FAIL:` line
# (fail-safe — visible to the operator, not silently rubber-stamped as
# PASS) rather than a distinct exit code no caller was ever wired to handle.
#
# Shebang note: the SHEBANG line above is `#!/usr/bin/env python3`, generator-
# owned by `gen-launcher-shim.py --ensure-unix`, and correct for this shape. On
# Windows, this file's co-located `.cmd` twin wins via `PATHEXT` when invoked
# as a bareword, so the shebang is never read there; on macOS/Linux `python3`
# is the right interpreter. Caution: callers must invoke via the extensionless
# name or a resolved-interpreter prefix, never a bareword `.py` through git-
# bash — git-bash DOES honor the shebang and would exec-127 with no `python3`
# present. See the carve-out in DoE-claude's coordinator/docs/wiki/bash-on-
# windows-gotchas.md § Carve-out (cross-repo — this wiki lives in the
# DoE-claude repo, not here).
#
# Filename note: the `.sh` extension is retained (NOT dropped per the
# `coordinator-auto-push`/`handoff-gate-aging` convention) — this script is
# invoked by its literal `.sh`-suffixed name from
# coordinator/pipelines/weekly-architecture-audit/PIPELINE.md and
# coordinator/skills/architecture-audit/SKILL.md; the polyglot shebang makes
# the retained suffix harmless (`bash verify-arch-audit-atlas-refresh.py
# ...` still Just Works), avoiding an otherwise-unnecessary multi-caller
# repoint.
#
# Spec backlink: DoE-claude:pln-bash-polyglot-clean-slate-full-5c71ee
#
# DR-276: routed through `coordinator_core.cli_entry.run_op_main` rather than a
# plain in-process `import ... as _op_main` + `sys.exit(op_main(argv))` tail, so
# any paths the op declares via `declare_write` become a session scope-touch
# claim (this op is a read-only staged-content gate — it writes nothing — so
# it declares none; routing it is a baseline-shrink, not a behavior change).

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
    """
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main() -> None:
    try:
        run_op_main = _import_run_op_main()
    except RuntimeError as exc:
        print(
            f"verify-arch-audit-atlas-refresh.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}",
            file=sys.stderr,
        )
        print(
            "FAIL: /architecture-audit Step 6.5 atlas-refresh gate could not run "
            "(claude-klabauter-link resolution failed) — treat as gate-not-satisfied and retry."
        )
        sys.exit(0)
    except ImportError as exc:
        print(
            f"verify-arch-audit-atlas-refresh.py: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        print(
            "FAIL: /architecture-audit Step 6.5 atlas-refresh gate could not run "
            "(claude-klabauter-link import failed) — treat as gate-not-satisfied and retry."
        )
        sys.exit(0)

    try:
        code = run_op_main("coordinator_core.ops.verify_arch_audit_atlas_refresh", sys.argv[1:])
    except ImportError as exc:
        print(
            f"verify-arch-audit-atlas-refresh.py: coordinator_core.ops.verify_arch_audit_atlas_refresh not importable: {exc}",
            file=sys.stderr,
        )
        print(
            "FAIL: /architecture-audit Step 6.5 atlas-refresh gate could not run "
            "(claude-klabauter-link import failed) — treat as gate-not-satisfied and retry."
        )
        sys.exit(0)

    sys.exit(code)


if __name__ == "__main__":
    main()
