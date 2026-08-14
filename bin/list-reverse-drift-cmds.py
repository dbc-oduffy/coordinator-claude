# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""list-reverse-drift-cmds.py — emits reverse-drift-cmd rows for copy_install plugin mirrors.

Reads plugin.mirrors from the machine-local registry and prints one
`<plugin_name>|<source_path>|<reverse_drift_cmd>` line per copy_install
plugin carrying a non-empty reverse_drift_cmd. Consumed by
/workweek-complete Step 4g, which cd's into <source_path> and runs the
command as a blocking merge gate. Supports --scope-repo so a consumer
repo's release never gates on a sibling plugin's live-install drift.
"""
# bin/list-reverse-drift-cmds.py — CLI trampoline over claude-klabauter
# coordinator_core.ops.list_reverse_drift_cmds.
#
# Purpose: read plugin.mirrors from the machine-local registry and emit one
# line per copy_install plugin that has a non-empty reverse_drift_cmd:
#
#   <plugin_name>|<source_path>|<reverse_drift_cmd>
#
# Consumed by /workweek-complete Step 4g, which cd's to <source_path> and runs
# <reverse_drift_cmd> as a blocking merge gate.
#
# Per-repo scoping (--scope-repo <repo-root>):
#   Without --scope-repo, EVERY copy_install row is emitted (legacy behavior;
#   preserved for direct callers and tests). Step 4g always passes its repo
#   root so a CONSUMER repo's release never gates on a SIBLING plugin's
#   live-install drift. The meta-repo (${HOME}/.claude) is the explicit
#   check-all case. Paths are normalized before comparison (Windows X:/ vs
#   MSYS /x/ vs $HOME /c/) so the meta-repo and source_path matches survive
#   cross-platform path forms.
#   Spec backlink: cross-repo/inbox/2026-06-01-reverse-drift-gate-per-repo-scoping.md
#
# Business exit codes (unchanged from the bash oracle — encode the difference
# between "gate is genuinely N/A" and "gate is blind because of misconfig" so
# Step 4g never silently passes when it should be running but cannot):
#   0  — emitted >=1 runnable row, OR no copy_install plugins exist at all (N/A).
#   3  — copy_install plugins ARE registered but NONE carry a reverse_drift_cmd.
#        The gate is structurally blind (the bug-equivalent state). Fail loud.
#   2  — invocation/parse error.
#   1  — TRANSPORT failure (CLAUDE_KLABAUTER_ROOT resolution or import failed) — this
#        trampoline's OWN exit code, distinct from the ported module's 0/2/3
#        business codes (addendum rule 3b: this is a fail-loud gate feeder —
#        Step 4g must not misclassify a claude-klabauter-link outage as "no copy_install
#        plugins registered" (0) or "misconfigured registry" (3)). Lowest
#        unused business code.
#
# Spec backlink: docs/plans/2026-05-28-reverse-drift-gate-meta-repo-coverage.md §Chunk 3
# Port backlink: docs/plans/2026-07-15-bash-to-naked-python-engine-migration.md
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
        print(f"list-reverse-drift-cmds.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(1)

    from coordinator_core.cli_entry import run_op_main

    try:
        code = run_op_main("coordinator_core.ops.list_reverse_drift_cmds", sys.argv[1:])
    except ImportError as exc:
        print(
            f"list-reverse-drift-cmds.py: coordinator_core.ops.list_reverse_drift_cmds not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    sys.exit(code)


if __name__ == "__main__":
    main()
