# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""verify-skill-anchor-links.py — dead-anchor gate for `<path>.md § <section>` citations.

Thin DoE-side (contract) trampoline over claude-klabauter's
coordinator_core.ops.verify_skill_anchor_links. Resolution is PATH-DIRECTED:
each `<path>.md § <section>` citation is checked against the file that citation
itself names, never against a union of doctrine files. An OPTIONAL manifest at
<doe_root>/coordinator/doctrine-surfaces.json (override:
COORDINATOR_DOCTRINE_MANIFEST) supplies an alias map so home-relative citations
such as `~/.claude/CLAUDE.md` become checkable; its ABSENCE is not an error —
those citations simply stay QUALIFIED rather than resolved.

Invoked from `/update-docs` Phase 11h. Exit codes are three distinct outcomes,
not a clean/dirty pair: 0 = checked, clean; 1 = checked, DEAD anchors found;
2 = COULD NOT CHECK (manifest present but broken, or plugin root unresolvable).
A 2 is never a finding about the citations — it means the gate never ran.

This trampoline's OWN failures are could-not-check conditions and exit 2 on the
same contract as the op's: engine root unresolvable, and the op module not
importable once it is. Neither says anything about the citations, so neither may
report 1 — a gate that could not load reporting a DEAD-anchor finding is the
false-signal class this gate exists to catch.
"""
from __future__ import annotations
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
# Exit-code convention: this is a fail-loud verification gate, and its three
# outcomes are load-bearing contract for `/update-docs` Phase 11h — 0 checked/
# clean, 1 checked/DEAD anchors found, 2 COULD NOT CHECK. 1 and 2 are NOT
# severity tiers of one thing: a 1 is a real finding about the citations, a 2
# says the gate never got to look (manifest present but unparseable, plugin root
# unresolvable) and carries no verdict about the citations at all. Unlike
# `coordinator-auto-push` (a never-block hook), a claude-klabauter-link failure here must
# NOT be silently swallowed into exit 0 — this trampoline's own engine-root-
# resolution and import failures exit 2, so a broken link surfaces as "the gate
# could not run" rather than a false "clean" report OR a fabricated finding.
#
# Spec backlink: DoE-claude:pln-bash-polyglot-clean-slate-full-5c71ee
#
# DR-276: routed through `coordinator_core.cli_entry.run_op_main` rather than a
# plain in-process `import ... as _op_main` + `sys.exit(op_main(argv))` tail, so
# any paths the op declares via `declare_write` become a session scope-touch
# claim (this op is a read-only anchor-link checker — it writes nothing — so
# it declares none; routing it is a baseline-shrink, not a behavior change).
import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402


def _import_run_op_main():
    """Resolve the engine root, put it on sys.path, and import `run_op_main`.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it -- this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.
    """
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main() -> None:
    try:
        run_op_main = _import_run_op_main()
    except RuntimeError as exc:
        print(
            f"verify-skill-anchor-links: COULD NOT CHECK — engine root did not resolve, "
            f"so the op backing this gate was never located and no citation was read: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)
    except ImportError as exc:
        print(
            f"verify-skill-anchor-links: COULD NOT CHECK — engine root resolved but "
            f"coordinator_core.cli_entry was not importable from it, "
            f"so no citation was read: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)

    try:
        code = run_op_main("coordinator_core.ops.verify_skill_anchor_links", sys.argv[1:])
    except ImportError as exc:
        print(
            f"verify-skill-anchor-links: COULD NOT CHECK — engine root resolved but "
            f"coordinator_core.ops.verify_skill_anchor_links was not importable from it, "
            f"so no citation was read: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(code)


if __name__ == "__main__":
    main()
