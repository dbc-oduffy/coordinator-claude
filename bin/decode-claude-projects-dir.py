# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
decode-claude-projects-dir.py — CLI trampoline over claude-klabauter
coordinator_core.ops.decode_claude_projects_dir.

Decodes ~/.claude/projects/ encoded directory names to repo-shortname
candidates. Output: tab-separated `shortname<TAB>candidate-path<TAB>encoded-dir-name`,
one deduped line per candidate. Heuristic decoder — surfaces candidates for
PM review, not authoritative paths. Used by /update-docs Phase 14/15 to seed
the candidates block in ~/.claude/state/repo-registry.md.

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

Usage:
  decode-claude-projects-dir.py [projects-dir]   # default: ~/.claude/projects

Exit codes: 0 — candidates emitted; 1 — projects dir not found, or zero
candidates decoded (see claude-klabauter module's Negative-spec for the reproduced
bash-oracle bug this preserves rather than fixes); 2 — engine-root
resolution or module import failure.

Port of: coordinator/bin/decode-claude-projects-dir.py (bash body retired on
cutover; see git log)
Port backlink: docs/plans/2026-07-15-bash-to-naked-python-engine-migration.md
               (clean-slate residual migration, R1 DOE-PORT wave)
"""

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402


def _prepare_claude_klabauter_root() -> None:
    """Resolve the engine root and put it on sys.path.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it.

    DR-276: the op is run through `coordinator_core.cli_entry.run_op_main`
    rather than by importing and calling its `main` directly, so any paths it
    declares via `declare_write()` become a session scope-touch claim instead
    of landing unclaimed as an orphan at the `scoped_git_commit` sink.
    """
    claude_klabauter_root = require_dispatch_engine_on_path()


def main() -> None:
    try:
        _prepare_claude_klabauter_root()
    except RuntimeError as exc:
        print(f"decode-claude-projects-dir.py: engine-root resolution failed: {exc}", file=sys.stderr)
        sys.exit(2)

    from coordinator_core.cli_entry import run_op_main

    try:
        code = run_op_main("coordinator_core.ops.decode_claude_projects_dir", sys.argv[1:])
    except ImportError as exc:
        print(
            f"decode-claude-projects-dir.py: coordinator_core.ops.decode_claude_projects_dir not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(code)


if __name__ == "__main__":
    main()
