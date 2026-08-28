# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
backfill-week-changelog-gaps.py -- CLI trampoline over claude-klabauter
coordinator_core.ops.changelog_ops.main (changelog.backfill_gaps).

Finish-strangler port (bash to pure-Python engine migration): the prior body
of this file was itself already a finished strangler (T2-g1) -- a thin bash
veneer that built a params JSON blob and shelled out via cc_invoke
changelog.backfill_gaps ... (JSON-RPC over a spawned python3 -m
coordinator_core.invoke subprocess). That veneer is retired on this cutover:
this trampoline calls coordinator_core.ops.changelog_ops.main() directly,
in-process -- one subprocess hop cheaper, matching the coordinator-auto-push
/ handoff-gate-aging direct-import pattern. The op handler itself
(_backfill_gaps_handler) is a thin asyncio.to_thread wrapper around the same
backfill_gaps() the new main() calls -- routing this through the JSON-RPC /
cc_invoke seam bought nothing over a direct call.

Shebang note: the SHEBANG line above is `#!/usr/bin/env python3`, generator-
owned by `gen-launcher-shim.py --ensure-unix`, and correct for this shape. On
Windows, this file's co-located `.cmd` twin wins via `PATHEXT` when invoked as
a bareword, so the shebang is never read there; on macOS/Linux `python3` is the
right interpreter. Caution: callers must invoke via the extensionless name or a
resolved-interpreter prefix, never a bareword `.py` through git-bash — git-bash
DOES honor the shebang and would exec-127 with no `python3` present. See the
carve-out in the coordinator doctrine repo's coordinator/docs/wiki/bash-on-windows-gotchas.md §
Carve-out (cross-repo — this wiki lives in the coordinator doctrine repo, not
here).

Usage (unchanged surface -- zero caller repoints):
    backfill-week-changelog-gaps.py [repo-root]
    NOTE: the optional [repo-root] positional is accepted but IGNORED (was
    already ignored on the prior cc_invoke path -- the op always resolves the
    repo root from $PWD via git, never from argv).

Options:
    -h, --help    Print this usage text and exit 0. Does NOT run the backfill
        (fix for cross-repo/inbox/2026-08-11-project-rag-em-backfill-changelog-
        cli-three-defects.md item 1: prior to this fix, --help had no
        interception here, so it was swallowed as an ignored positional and
        the backfill ran -- writing files with no output naming them as
        writes).
    --dry-run     Report which day(s) would be backfilled and the paths that
        would be written, without writing anything. Forwarded to
        coordinator_core.ops.changelog_ops.main(), which resolves it into
        backfill_gaps(dry_run=True).

Exit codes:
    0 -- success or advisory-error. changelog_ops.main() never propagates an
        exception for expected failure modes (missing HEADER.md, unparseable
        "Week starting:" line) -- it returns/prints a message dict instead --
        mirroring the legacy `trap 'exit 0' ERR` advisory contract (DR-216
        D2) this whole op family preserves.
    1 -- cannot resolve git repo root from $PWD (not a git repo). Raised by
        changelog_ops.main() itself.
    2 -- claude-klabauter-link failure: the engine root unresolvable, or
        coordinator_core.ops.changelog_ops not importable at that root. This
        preserves the PRIOR cc_invoke veneer's own documented exit-2
        "post-spawn transport failure -- fail loud, no fallback" contract
        (the retired script's own header comment) rather than collapsing it
        into the generic fail-loud/never-block 0-vs-1 dichotomy other R-wave
        ports use: this script already carried a three-way exit contract
        (0 / 1 / 2) with its own distinct meanings, and this port preserves
        it exactly for byte-parity against the existing facade test and
        `workweek-complete.md` Step 1b's documented behavior.

Spec backlink: cross-repo/inbox/2026-07-06-strang-10-facade-adoption.md
"""

from __future__ import annotations

import os
import sys


def _import_runner():
    """In-process import, not an RPC invoke — a plain local file mutation.

    DR-276: the op is run through `coordinator_core.cli_entry.run_op_main`
    rather than by calling its `main` directly, so the paths it declares
    become a session scope-touch claim. Without that, everything this CLI
    writes is an orphan at the `scoped_git_commit` sink.
    """
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main
    return run_op_main


def main(argv: "list[str] | None" = None) -> int:
    argv = (sys.argv[1:] if argv is None else argv)
    if "-h" in argv or "--help" in argv:
        # Intercept BEFORE run_op_main -- see item 1 in the spec-backlinked
        # memo. Without this, --help was forwarded straight through as an
        # ignored positional and the backfill ran for real.
        print(__doc__)
        return 0

    try:
        run_op_main = _import_runner()
    except RuntimeError as exc:
        print(f"backfill-week-changelog-gaps.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return 2
    except ImportError as exc:
        print(
            f"backfill-week-changelog-gaps.py: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        return 2

    try:
        code = run_op_main("coordinator_core.ops.changelog_ops", (sys.argv[1:] if argv is None else argv))
    except ImportError as exc:
        print(
            f"backfill-week-changelog-gaps.py: coordinator_core.ops.changelog_ops "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        return 2

    return code


if __name__ == "__main__":
    sys.exit(main())
