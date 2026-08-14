from __future__ import annotations
#
# roadmap-number-stubs — CLI trampoline over claude-klabauter
# coordinator_core.roadmap.number_stubs.
#
# Authoring-helper CLI for roadmap stub topological linearization — default mode
# reads an author-written edges file (before stubs exist) and prints a
# label -> (stub number, sprint, wave) mapping table to transcribe into stub
# frontmatter; --check mode verifies stubs already on disk for a given
# roadmap_id have dependency-monotone (sprint, wave) ordering.
#
# Shebang note: the SHEBANG line above is `#!/usr/bin/env python3`, and correct
# for this shape. On Windows, this file's co-located `.cmd` twin wins via
# `PATHEXT` when invoked as a bareword, so the shebang is never read there; on
# macOS/Linux `python3` is the right interpreter. Caution: callers must invoke
# via the extensionless name or a resolved-interpreter prefix, never a bareword
# `.py` through git-bash — git-bash DOES honor the shebang and would exec-127
# with no `python3` present. See the carve-out in DoE-claude's
# coordinator/docs/wiki/bash-on-windows-gotchas.md § Carve-out (cross-repo —
# this wiki lives in the DoE-claude repo, not here).
#
# Usage:
#   roadmap-number-stubs <edges-file>      # linearize from edges file
#   roadmap-number-stubs --check <run-id>  # verify stubs on disk
#   roadmap-number-stubs --state <run-id>  # print per-stub readiness state
#
# Exits 0 on success; 1 on a dependency cycle (default mode) or dependency-order
# violations (--check mode); 2 on a CLI usage error; 3 on a CLAUDE_KLABAUTER_ROOT
# resolution/import failure (transport failure — distinct from both business
# codes above so a caller cannot misclassify a claude-klabauter-link outage as "no
# violations found" (0) or "usage error" (2)).
#
# Spec backlink: docs/plans/2026-06-28-roadmap-stub-numbering-dependency-order.md § C2
# Port of: coordinator/bin/roadmap-number-stubs.js + coordinator/bin/lib/roadmap-graph.js
#          (retired on this cutover; see git log)
# Port backlink: BIG_PORT Wave B, item roadmap-pair

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402


def _import_main():
    """Resolve CLAUDE_KLABAUTER_ROOT, put it on sys.path, and import the ported CLI entry.

    Reuses cc_invoke's battle-tested CLAUDE_KLABAUTER_ROOT resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it — this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.
    """
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.roadmap.number_stubs import main as _op_main

    return _op_main


def main() -> None:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"roadmap-number-stubs: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(3)
    except ImportError as exc:
        print(
            f"roadmap-number-stubs: coordinator_core.roadmap.number_stubs not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(3)

    # Review: code-reviewer — F3, op_main's call was unguarded; a RuntimeError
    # escaping resolve_root() (now caught inside op_main itself, see
    # number_stubs.py run_check_mode) or any other unhandled exception would
    # otherwise surface as a raw Python traceback here instead of a clean
    # exit-code contract.
    try:
        sys.exit(op_main(sys.argv[1:]))
    except Exception as exc:  # noqa: BLE001 — last-resort trampoline guard
        print(f"roadmap-number-stubs: {exc}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
