# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
parse-resolves-trailer.py — CLI trampoline over claude-klabauter
coordinator_core.ops.parse_resolves_trailer.

Emits the artifact-IDs from a commit's `Resolves:` git trailers, one per
stdout line, so callers (coordinator/bin/rollup-derive.py) can derive
resolving-commit sets without hand-parsing commit bodies.

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
  parse-resolves-trailer.py <commit>

Exit codes: 0 — success (incl. vacuous zero-trailer output); 1 — usage error;
2 — not a git repo / invalid commit / CLAUDE_KLABAUTER_ROOT resolution or import failure
(fail-loud, matching the ported script's own internal-error convention).

Spec backlink: DoE-claude:pln-lifecycle-vocab-c2-durable-cro-991bd4 § C4
Doctrine: coordinator/docs/wiki/resolves-commit-trailer.md
Port of: coordinator/bin/parse-resolves-trailer.py (bash body retired on cutover; see git log)
Port backlink: docs/plans/2026-07-16-bash-clean-slate-residual-migration.md
"""

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
        print(f"parse-resolves-trailer.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(2)

    from coordinator_core.cli_entry import run_op_main

    try:
        code = run_op_main("coordinator_core.ops.parse_resolves_trailer", sys.argv[1:])
    except ImportError as exc:
        print(
            f"parse-resolves-trailer.py: coordinator_core.ops.parse_resolves_trailer not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(code)


if __name__ == "__main__":
    main()
