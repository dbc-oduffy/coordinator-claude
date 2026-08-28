# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""verify-dist-publish-repo-sync.py — CLI trampoline over claude-klabauter coordinator_core.ops.verify_dist_publish_repo_sync.

Byte-identity check between the Claude Central dist/ source-of-truth and the
coordinator-claude publish repo, for the two flat-mirror targets (toplevel +
docs). One-way check only — source is truth, the publish repo is derivative;
there is no --fix mode, since the correct fix is always
`python coordinator/bin/publish.py <target>`.
"""
# verify-dist-publish-repo-sync.py — CLI trampoline over claude-klabauter
# coordinator_core.ops.verify_dist_publish_repo_sync. Byte-identity check
# between Claude Central dist/ source-of-truth and the coordinator-claude
# publish repo, for the two flat-mirror targets (toplevel + docs).
#
# Finish-strangler port (DR-059, DoE owns contract, claude-klabauter owns engine): the
# bash comparison/reporting logic has been fully ported to
# coordinator_core/ops/verify_dist_publish_repo_sync.py (co-located pytest:
# test_verify_dist_publish_repo_sync.py). This file is now a thin DoE-side
# (contract) trampoline over that claude-klabauter (engine) module, mirroring the
# direct-import template-variant #1 shape (no @register_op, plain in-process
# import + call — a byte-identity gate is not IPC-shaped work).
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
# ONE-WAY check only. Source IS the truth; publish repo is derivative.
# There is no --fix mode — the fix for an out-of-sync publish repo is
# always: python coordinator/bin/publish.py <target>
#
# Why no --fix mode? Authority cite: plugin-extraction-and-distribution.md
# § Persona-Name Guard on Percolation — "publish.py is the authority for
# percolation — manual cp is wrong." A script-driven copy would bypass
# depersonalize hooks and content-leakage scans that run as post-rsync hooks
# in the publish.py pipeline.
#
# Usage:
#   verify-dist-publish-repo-sync.py          Check all pairs; exit non-zero on any MISMATCH or MISSING.
#
# Targets verified (source → publish repo):
#   coordinator/dist/publish-repo-toplevel/   ↔  /x/coordinator-claude/ (toplevel)
#   coordinator/dist/publish-repo-docs/       ↔  /x/coordinator-claude/docs/
#
# .percolate-ignore semantics (each flat-mirror target):
#   Files listed in a target's dist/.percolate-ignore are NOT verified
#   — they are publish-repo-owned infrastructure (CLAUDE.md, .gitignore, etc.)
#   that Claude Central deliberately does not author.
#
# Output format:
#   OK        <rel-path>   — byte-identical between source and publish repo
#   MISMATCH  <rel-path>   — content differs
#   MISSING   <rel-path>   — file absent in publish repo (a NEW source file not yet published)
#   IGNORED   <rel-path>   — excluded by .percolate-ignore
#
# Exit codes (business codes returned by the claude-klabauter op — parity-critical,
# unchanged from the pre-port bash oracle):
#   0 — all verified files are byte-identical
#   1 — one or more MISMATCH or MISSING files detected, OR publish-repo-root
#       could not be resolved (env var unset and machine-local unavailable/
#       unset key — an environment problem the bash oracle also mapped to 1)
#   2 — source dir(s) or publish-repo dir(s) not found (environment problem),
#       OR CLAUDE_PLUGIN_ROOT could not be resolved
#
# Transport-failure exit code (this trampoline's own — NEVER returned by the
# claude-klabauter op itself, so it can never collide with the op's 0/1/2 business
# codes above; per porter-brief addendum § 3b, this is a fail-loud
# gate/validator script, so claude-klabauter-link failure gets a dedicated code
# rather than silently degrading to 0):
#   3 — engine-root resolution failed, or coordinator_core.ops.
#       verify_dist_publish_repo_sync was not importable
#
# Spec backlink: docs/plans/2026-05-21-back-percolate-publish-repo-orphans.md § Chunk 4 and docs/plans/2026-06-30-registry-publish-vs-working-targets.md § C8
# Port backlink: docs/plans/2026-07-15-bash-to-naked-python-engine-migration.md
# Prior bash implementation: see git log (verify-dist-publish-repo-sync.py, 257 lines, retired on this cutover)

import os
import sys

def _plugin_root() -> str:
    """Resolve the plugin root (coordinator/) that owns dist/publish-repo-{toplevel,docs}/.

    Env var CLAUDE_PLUGIN_ROOT wins if set, returned verbatim. Otherwise
    resolves via doe_root() (see that function's own docstring for its
    env-var/machine-local resolution chain) and returns
    <doe_root()>/coordinator.

    This does NOT derive from this script's own __file__ location. That
    used to be correct when this executable lived in DoE-claude
    (coordinator/bin/.. IS the plugin root there), but this file has since
    migrated to claude-klabauter (b644d5a9 there, 8a28a6ca here) while
    coordinator/dist/publish-repo-{toplevel,docs}/ stayed put in
    DoE-claude — self-location now resolves to <claude-klabauter>/coordinator, which
    has no dist/ at all, silently producing spurious MISSING/ERROR lines
    over a tree that never existed instead of a loud failure. doe_root()
    is the correct authority for "where is the DoE-claude repo,"
    independent of where THIS script happens to run from. A future reader
    must not "restore" __file__-based resolution to regain the old bash
    oracle's SCRIPT_DIR/.. shape — that is precisely what caused this
    break. The claude-klabauter op cannot derive this itself — it does not live in
    the DoE tree — so the trampoline resolves and forwards it via the
    environment.

    Fails loud (sys.exit(3)) if doe_root() cannot resolve: this is a gate
    script, not a never-block hook, so an unresolvable DoE root must not
    degrade to an exit-0 no-op. Exit code 3 (not 1 or 2) keeps this failure
    distinct from the op's own 0/1/2 business codes, matching this
    trampoline's existing engine-root-resolution-failure convention below.
    """
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from coordinator_registry import _DoeUnresolvable, doe_root

    env_val = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env_val:
        return env_val
    try:
        root = doe_root()
    except _DoeUnresolvable as exc:
        print(
            "verify-dist-publish-repo-sync.py: cannot resolve the DoE-claude repo root "
            f"({exc}). Set repos.doe_claude in the machine-local registry, or set "
            "the DOE_ROOT env var, or set CLAUDE_PLUGIN_ROOT directly.",
            file=sys.stderr,
        )
        sys.exit(3)
    return os.path.join(root, "coordinator")


def _import_run_op_main():
    """Resolve the engine root and import `run_op_main`.

    DR-276: the op is run through `coordinator_core.cli_entry.run_op_main`
    rather than by calling its `main` directly, so any path it declares via
    `declare_write` becomes a session scope-touch claim instead of an
    unclaimed orphan at the `scoped_git_commit` sink.
    """
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main(argv: "list[str] | None" = None) -> int:
    os.environ.setdefault("CLAUDE_PLUGIN_ROOT", _plugin_root())
    try:
        run_op_main = _import_run_op_main()
    except RuntimeError as exc:
        print(
            f"verify-dist-publish-repo-sync.py: engine-root resolution failed: {exc}",
            file=sys.stderr,
        )
        return 3
    except ImportError as exc:
        print(
            f"verify-dist-publish-repo-sync.py: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        return 3
    try:
        code = run_op_main("coordinator_core.ops.verify_dist_publish_repo_sync", (sys.argv[1:] if argv is None else argv))
    except ImportError as exc:
        print(
            "verify-dist-publish-repo-sync.py: "
            f"coordinator_core.ops.verify_dist_publish_repo_sync not importable: {exc}",
            file=sys.stderr,
        )
        return 3
    return code


if __name__ == "__main__":
    sys.exit(main())
