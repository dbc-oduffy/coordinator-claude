# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""read-frontmatter-field.py — extracts a bare scalar from markdown YAML frontmatter.

CLI trampoline over claude-klabauter coordinator_core.ops.read_frontmatter_field. Reads
the first occurrence of a named field and prints the clean, unquoted value to
stdout with no trailing newline — designed for deliverable-spine id/FK fields
(deliverable_id, initiative) whose values are simple strings. Absence of the
field, a null value, or a missing/unreadable file all degrade to an empty
string rather than an error.
"""
from __future__ import annotations
# read-frontmatter-field.py — CLI trampoline over claude-klabauter
# coordinator_core.ops.read_frontmatter_field.
#
# Extracts a bare scalar value from markdown YAML frontmatter — reads the first
# occurrence of a named field and returns the clean, unquoted value to stdout, no
# trailing newline. Designed for deliverable-spine id/FK fields (deliverable_id,
# initiative) where values are simple strings that never contain '#'.
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
# Usage:  read-frontmatter-field.py <file> <field>
#
# Output: bare scalar value printed to stdout (no trailing newline), or empty
#         string when:
#         - the named field is absent in the file
#         - the value is the literal token 'null' (bare or quoted)
#         - the file path is missing, empty, or unreadable
#
# Exit:   always 0 — callers pass optional paths; absence is not an error. This
#         holds even when the claude-klabauter link itself fails (the engine root unresolved /
#         module not importable) — a link failure degrades to the same "empty
#         string" contract as a missing field, so callers doing `$(... )` capture
#         never see a crash from this helper.
#
# Spec backlink: DoE-claude:pln-bash-polyglot-clean-slate-full-5c71ee
# Port of: coordinator/bin/read-frontmatter-field.py (bash body retired on cutover;
#          see git log for the pre-port implementation)

import os
import sys


def _resolve_run_op_main():
    """Resolve the engine root, put it on sys.path, and import `run_op_main`.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it — this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.

    DR-276: routed through `coordinator_core.cli_entry.run_op_main` rather than
    a bare `main` import — this op declares no writes (pure read/print), so
    this changes nothing behaviorally, but keeps every operator CLI on the one
    recording seam uniformly.
    """
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main(argv: "list[str] | None" = None) -> int:
    try:
        run_op_main = _resolve_run_op_main()
    except RuntimeError as exc:
        print(f"read-frontmatter-field.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.stdout.write("")
        return 0
    except ImportError as exc:
        print(
            f"read-frontmatter-field.py: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        sys.stdout.write("")
        return 0

    try:
        code = run_op_main("coordinator_core.ops.read_frontmatter_field", (sys.argv[1:] if argv is None else argv))
    except ImportError as exc:
        print(
            f"read-frontmatter-field.py: coordinator_core.ops.read_frontmatter_field not importable: {exc}",
            file=sys.stderr,
        )
        sys.stdout.write("")
        return 0

    return code


if __name__ == "__main__":
    sys.exit(main())
