# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
generate-repomap.py — CLI trampoline over claude-klabauter
coordinator_core.ops.generate_repomap.

Thin wrapper around the Python repomap generator (bin/repomap/generate-repomap.py,
DoE-resident, NOT ported — this trampoline only replaces the bash argument-
building/interpreter-resolution/trust-guard shell, not the generator itself).
Contains NO RAG-gating logic — callers gate via bin/check-rag-state.py before
invoking this. Full gating doctrine: docs/wiki/repomap-rag-gating.md.

With no arguments, runs with defaults: --project-root . --budget 4000
--profile balanced. With arguments, passes them through to the generator
verbatim (user args take full precedence — defaults are not merged).

Exit codes:
  0 — generator ran successfully
  1 — generator script not found at any of the three searched locations, OR
      the resolved plugin root failed the trusted-root-guard check, OR no
      python interpreter was found, OR CLAUDE_KLABAUTER_ROOT resolution / the claude-klabauter
      module import itself failed
  N — generator's own exit code on failure

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

Fail-loud convention: the original .sh exits 1 on every resolution failure
(missing generator, untrusted root, no interpreter) rather than degrading
silently — this trampoline preserves that convention for claude-klabauter-link failures
too (unlike the auto-push shape, which must never block a commit).

Spec backlink: docs/plans/2026-05-09-skill-consolidation-pass.md § T2
Port source: coordinator/bin/generate-repomap.py (this file, retired bash body
    on this cutover; see git log for the prior 82-line implementation)
"""

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402

# Generator-provenance declaration (C2, generator_provenance.py's AST reader).
# THIS file is a thin CLI trampoline (see module docstring) -- `sources` names
# the real implementation locus, `coordinator/bin/repomap/generate-repomap.py`
# (the vendored repomap tool this trampoline shells out to via
# coordinator_core.ops.generate_repomap.main), never this shim's own path;
# a `sources` pointing here would yield a since-range that is empty
# essentially forever (§ Mechanism correction,
# docs/plans/2026-08-13-generator-output-staleness-detector.md).
# `stamp_key` names the intended field, not one on disk today -- the
# repomap's only current stamp is a prose "Generated: <ts>" line, not a
# usable key (see plan C2 body); adding the artifact-side key requires
# editing `coordinator/bin/repomap/generate-repomap.py`, which is outside
# this chunk's write set (that module is a vendored DoE-resident tool, not
# owned by this trampoline) -- until that lands, this pair reads UNSTAMPED,
# which is the honest state, not FRESH.
GENERATES = [
    {
        "artifact": ".claude/repomap.md",
        "stamp_key": "generated",
        "sources": ["coordinator/bin/repomap/generate-repomap.py"],
    },
]


def _import_main():
    """Resolve CLAUDE_KLABAUTER_ROOT, put it on sys.path, and import the ported entrypoint.

    Reuses cc_invoke's battle-tested CLAUDE_KLABAUTER_ROOT resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it -- this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.
    """
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.ops.generate_repomap import main as _op_main

    return _op_main


def main() -> None:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"generate-repomap.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(1)
    except ImportError as exc:
        print(
            f"generate-repomap.py: coordinator_core.ops.generate_repomap not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    # plugin_root mirrors the original .sh's own resolution:
    # ${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)} —
    # env override first, else this file's own grandparent directory
    # (coordinator/bin/generate-repomap.py -> coordinator/).
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT") or os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    )
    # site mirrors the original .sh's own $0 in its ERROR line — whatever
    # invocation-time path/argv[0] the caller used, not a fixed basename.
    sys.exit(op_main(sys.argv[1:], plugin_root=plugin_root, site=sys.argv[0]))


if __name__ == "__main__":
    main()
