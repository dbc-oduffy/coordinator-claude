# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""coordinator-complete-entry.py — CLI trampoline over the claude-klabauter workstream
completion-entry scaffolder.

Scaffolds a pre-filled workstream completion entry — the mechanical spine of
/workstream-complete Step 2.6 — leaving up to two model-residue placeholders
for the caller to fill (<!-- NATURE-INFER --> when --nature is omitted, and a
<!-- PROSE: ... --> title/body slot). Idempotent per governing-plan-slug chain
filename; never seeds the commits: field (owned by
reconcile-completion-commits.py --append).
"""
# coordinator-complete-entry.py — CLI trampoline over claude-klabauter
# coordinator_core.ops.coordinator_complete_entry.
#
# Scaffolds a pre-filled workstream completion entry — the mechanical spine of
# /workstream-complete Step 2.6 (completion-entry ladder) in one command, with up
# to two model-residue placeholders left for the caller to fill:
#   <!-- NATURE-INFER -->  — present only when --nature is omitted
#   <!-- PROSE: ... -->    — always present (title + body slot for the model)
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
# Usage:
#   coordinator-complete-entry.py \
#       --sid <WSC_SID> \
#       --disposition <single-session|predecessor-consumed|memo-predecessor> \
#       [--consumed-handoff <path>]         required when predecessor-consumed;
#                                            not applicable to memo-predecessor
#       [--governing-plan-slug <slug>]      drives idempotency guard + chain-slug filename
#       [--nature <roadmap|bugfix|tech-debt|infra>]
#
# Exit codes:
#   0  — entry written, OR idempotent no-op (entry already exists for this chain slug)
#   1  — argument error (missing required flag, invalid --nature enum value, etc.)
#   2  — environment error (not inside a git repository)
#   3  — CLAUDE-KLABAUTER transport failure (engine-root resolution or module import failed).
#        DEDICATED code, distinct from the 0/1/2 business states above (this is a
#        fail-loud ceremony tool — an outage here must not misclassify as a
#        legitimate business outcome; see porter-brief addendum rule 3b).
#
# Spec backlink: docs/plans/2026-07-06-cockpit-contract-v27 (§ coordinator-complete-entry)
# Port of: coordinator/bin/coordinator-complete-entry.py (this file — logic moved to
#          claude-klabauter coordinator_core.ops.coordinator_complete_entry)
# Port backlink: docs/plans/2026-07-15-bash-to-naked-python-engine-migration.md (BIG_PORT Wave B)
#
# Negative-spec — commits: field:
#   This CLI NEVER seeds the commits: list. Step 2.6.8 owns that field entirely
#   via reconcile-completion-commits.py --append (Session-Id-trailer reconcile).

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402


def _import_runner():
    """Resolve the engine root, put it on sys.path, and import the DR-276 op runner.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it — this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.

    DR-276: the op is run through `coordinator_core.cli_entry.run_op_main`
    rather than by calling its `main` directly, so the paths it declares
    become a session scope-touch claim. Without that, everything this CLI
    writes is an orphan at the `scoped_git_commit` sink.
    """
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main() -> None:
    try:
        run_op_main = _import_runner()
    except RuntimeError as exc:
        print(f"coordinator-complete-entry.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(3)
    except ImportError as exc:
        print(
            f"coordinator-complete-entry.py: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(3)

    try:
        code = run_op_main(
            "coordinator_core.ops.coordinator_complete_entry", sys.argv[1:]
        )
    except ImportError as exc:
        print(
            f"coordinator-complete-entry.py: coordinator_core.ops.coordinator_complete_entry "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(3)

    sys.exit(code)


if __name__ == "__main__":
    main()
