# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""orphan-branch-sweep.py — read-only sweep classifying orphaned work/feature branches.

Enumerates user-owned work/* and feature/* branches in the current repo and
classifies each as CRITICAL (commits post-dating a merged PR), WARNING (open,
no PR, aged past threshold), or OK. Emits JSON lines (or text) to stdout;
never mutates branches, refs, or PRs. Sweep logic lives claude-klabauter-side in
coordinator_core.ops.orphan_branch_sweep; this file is a thin trampoline.
"""
# orphan-branch-sweep.py — CLI trampoline over claude-klabauter
# coordinator_core.ops.orphan_branch_sweep.
#
# Enumerates user-owned work/* and feature/* branches in the current repo. For
# each qualifying branch, determines whether it has commits that post-date a
# merged PR (CRITICAL), is an open branch with no PR and a branch-name date
# >=2 days old or age_h>36 (WARNING), or is clean (OK). Emits JSON lines (or
# text, via --format) to stdout. Read-only — never mutates branches, refs, or
# PRs. See the ported module's own docstring for the full negative-spec
# (faithfully-reproduced current-branch drop bug, sorted iteration order,
# dropped jq dependency).
#
# Bash-4 note: the retired bash implementation guarded on BASH_VERSINFO[0]<4
# (associative arrays). This trampoline has NO bash-version dependency — it
# execs straight into Python — so that guard is dropped, not silently lost:
# the script now also runs cleanly under stock macOS bash 3.2 (an improvement,
# not a scope-drop). docs/wiki/cross-platform-shell-portability.md's citation
# of this file as a BASH_VERSINFO<4 exemplar is now stale (flagged, not fixed
# here — out of scope for this port).
#
# Usage:
#   orphan-branch-sweep.py [OPTIONS]
#
# Options:
#   --format json|text                      Output format (default: json)
#   --severity-min ok|warning|critical       Minimum severity to emit (default: ok)
#   --include-remote / --no-include-remote   Include origin/* branches (default: on)
#   --max-age-days N                         Ignore branches older than N days (default: 30)
#   --help                                   Show this help
#
# Exit codes (parity-critical — matches ported main()'s actual returns):
#   0 — normal completion (including: not inside a git repo, gh unavailable, --help)
#   1 — unrecognized CLI argument (usage error)
#
# Spec backlink: archive/specs/2026-05-01-orphan-branch-prevention.md § 1.1
# Port source: this file (retired-in-place; body replaced by trampoline on cutover)
# Port backlink: docs/plans/2026-07-15-bash-to-naked-python-engine-migration.md
#
# DR-276: NOT converted to run_op_main. This op is read-only (enumerates
# branches, emits JSON/text to stdout, never mutates branches/refs/PRs/disk —
# see this file's own module docstring and coordinator_core.ops.
# orphan_branch_sweep's). There is nothing to declare_write and therefore
# nothing for a session scope-touch claim to cover; routing a no-write op
# through run_op_main would add an import hop for zero benefit.
from __future__ import annotations

import os
import sys

def _import_main():
    """Resolve the engine root, put it on sys.path, and import the ported CLI entry.

    Reuses cc_invoke's battle-tested engine-root resolution ladder rather than
    re-deriving it — this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.
    """
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.ops.orphan_branch_sweep import main as _op_main

    return _op_main


def main(argv: "list[str] | None" = None) -> int:
    # This tool is best-effort/advisory (feeds /workday-start and
    # merging-to-main's pre-merge scan; never a hard gate) — a claude-klabauter-link
    # (transport) failure degrades to exit 0 loud-on-stderr, matching the
    # ORIGINAL script's own "Exits 0 always" posture, rather than mapping to a
    # caller-facing error code. See porter-brief addendum § 3b.
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"orphan-branch-sweep.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return 0
    except ImportError as exc:
        print(
            f"orphan-branch-sweep.py: coordinator_core.ops.orphan_branch_sweep not importable: {exc}",
            file=sys.stderr,
        )
        return 0
    return op_main((sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    sys.exit(main())
