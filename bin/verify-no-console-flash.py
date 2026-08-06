#!/usr/bin/env python3
# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""verify-no-console-flash.py — CLI trampoline over claude-klabauter coordinator_core.ops.verify_no_console_flash.

Guards against console-window flashes on Windows: spawning any native
console-subsystem .exe (python.exe, node.exe, powershell.exe) without an
explicit CREATE_NO_WINDOW / windowsHide:true suppression allocates a fresh
conhost.exe window that briefly flashes. Flags variable-interpreter, heredoc,
bare-literal, array-form, and unsuppressed powershell/pwsh spawn shapes
across *.sh, *.json, and coordinator-auto-push under the coordinator-claude
tree.
"""
# verify-no-console-flash.py — CLI trampoline over claude-klabauter
# coordinator_core.ops.verify_no_console_flash.
#
# Purpose: guard against console-window flashes on Windows. On Windows
# (git-bash/mintty), spawning any native console-subsystem .exe (python.exe,
# node.exe, powershell.exe) allocates a fresh conhost.exe window that briefly
# flashes. The only reliable suppression is CREATE_NO_WINDOW / windowsHide:true
# at the CreateProcess call — not `-WindowStyle Hidden`, which is
# create-then-hide. See: docs/wiki/claude-code-platform-gotchas.md § Windows
# console window flash.
#
# Spec backlink: docs/plans/2026-05-29-windows-console-flash-elimination.md § Chunk 3
#                docs/plans/2026-07-15-bash-to-naked-python-engine-migration.md
#
# This guard flags any of the following spawn shapes when they lack an explicit
# suppression flag or routing through lib/spawn-hidden.sh:
#   (1) variable-interpreter:  "${PYTHON:-python3}", "$PYTHON", $PYTHON_BIN, "${NODE...}"
#   (2) heredoc spawn:         interpreter token followed by ' - ' and/or '<<'
#                              e.g. "${PYTHON:-python3}" - "$pname" "$reg_file" <<'PYEOF'
#   (3) bare literals:         python , python3 , node  (with trailing space)
#   (4) array-form / flags:    python -c / node -e / python3 -c
#   (5) hooks.json commands:   ARCHITECTURALLY EXEMPT (2026-06-14) — Claude Code is the
#                               CreateProcess parent; see rationale in the ported module's docstring.
#   (6) powershell/pwsh:       missing -WindowStyle Hidden  (legacy check, preserved)
#
# A spawn is EXEMPT (not flagged) if any of the following are true:
#   a) The line routes through lib/spawn-hidden.sh
#   b) The line carries CREATE_NO_WINDOW, windowsHide, or -WindowStyle Hidden
#   c) The line has a trailing allowlist comment:
#        # verify-no-console-flash: allow
#      (use for: the launcher itself, this guard script, test fixtures,
#       or any spawn that is verifiably not on the Windows hot-path)
#   d) The FILE carries a header allow marker within its first 10 lines:
#        # verify-no-console-flash: file-allow — <rationale>
#      (use for: physically-Linux-only scripts — RunPod / training pipelines —
#       where no Windows conhost can be allocated regardless of spawn shape, so
#       per-line allow on 20+ interpreter calls is just noise)
#
# Usage:
#   verify-no-console-flash.py [ROOT]
#   ROOT defaults to $HOME/.claude/plugins
#
# Exit codes:
#   0 — clean: no unsuppressed spawn sites found (op's own verdict, passed through).
#   1 — violations found (report printed to stdout; op's own verdict, passed through).
#   2 — TRANSPORT failure: CLAUDE_KLABAUTER_ROOT resolution failed or the ported op module
#       was not importable. Dedicated code, collides with neither business
#       verdict above — this guard is a fail-loud merge-gate check
#       (/workweek-complete), so a claude-klabauter-link outage must not be misread as
#       "clean" (0) nor as "violations found" (1). Matches the sibling
#       verify-no-powershell-flash.py shim's own transport-failure convention.
#
# Scans *.sh, *.json, and coordinator-auto-push under coordinator-claude tree.
from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402


def _prepare_claude_klabauter_root() -> None:
    """Resolve CLAUDE_KLABAUTER_ROOT and put it on sys.path.

    Reuses cc_invoke's battle-tested CLAUDE_KLABAUTER_ROOT resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it.

    DR-276: the op is run through `coordinator_core.cli_entry.run_op_main`
    rather than by importing and calling its `main` directly, so any paths it
    declares via `declare_write()` become a session scope-touch claim instead
    of landing unclaimed as an orphan at the `scoped_git_commit` sink.
    """
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)


def main() -> None:
    try:
        _prepare_claude_klabauter_root()
    except RuntimeError as exc:
        print(f"verify-no-console-flash.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(2)

    from coordinator_core.cli_entry import run_op_main

    try:
        code = run_op_main("coordinator_core.ops.verify_no_console_flash", sys.argv[1:])
    except ImportError as exc:
        print(
            f"verify-no-console-flash.py: coordinator_core.ops.verify_no_console_flash not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)
    sys.exit(code)


if __name__ == "__main__":
    main()
