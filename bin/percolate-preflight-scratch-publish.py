# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""percolate-preflight-scratch-publish.py — hook-exercising scratch-publish gate for the C6 percolation cutover.

Fires a REAL non-dry-run `publish.py` into a throwaway scratch destination
so the real post_rsync-phase engine dispatch (`percolate-store.yaml`'s
declarative post_rsync entries for coordinator-claude — the legacy per-target
`post-rsync/*.sh` hook scripts this gate originally exercised were retired in
the percolate-engine cutover, chunk C-W2) actually fires, then independently
re-checks the codename and persona-slug leak guards plus a write-set
assertion. A fail-closed pre-flight gate: on transport failure it exits loud
rather than silently passing. Gate logic lives engine-side in
coordinator_core.ops.percolate_preflight_scratch_publish;
this file supplies the --coordinator-root path knowledge, resolved via
cc_invoke._resolve_claude_klabauter_root() + "/coordinator" (NOT doe_root() -- see
_resolve_coordinator_root() below for why the DoE-pointing resolver this
file used before DR-261 is now the wrong target).

Port of: percolate-preflight-scratch-publish.sh (DoE b5a4192c, 2026-07-20).
The engine module now spawns ONLY native Python — the non-dry-run publish is
the native `publish.py` driver (`coordinator/bin/publish.py`, DoE's ported
successor to the retired associative-array-driven `publish.sh`, DoE 16302166,
2026-07-21) — this trampoline supplies the coordinator-root path knowledge
(--coordinator-root) the engine module needs to find it. That root is
resolved via _resolve_coordinator_root() below (CLAUDE_PLUGIN_ROOT env, else
<engine repo root>/coordinator) -- NOT this script's own __file__ location.
See _resolve_coordinator_root()'s docstring for why __file__-based
resolution is STILL avoided even though this script itself now lives inside
the correct root post-DR-261 (it would happen to work today, but would
silently re-break under exactly the invocation shapes doe_root()-style
indirection exists to survive).

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

Fail-loud exit convention: this is a gate script (C6 pre-flight) — on
engine-link failure, exit 3 (a DEDICATED transport-failure code, distinct
from BOTH business codes below) rather than silently degrading to 0 or
colliding with 1/2. A silent pass-through here would mean a percolate
publish's pre-flight gate never actually ran — the opposite of what a
fail-closed gate must do. PORTER-BRIEF-ADDENDUM.md § 3b.

Exit codes:
    0 — GREEN (all gates passed)
    1 — RED (a gate failed)
    2 — usage/setup error (bad args, missing dependency file, unresolvable row)
    3 — engine-link/transport failure (the engine root unresolvable or
        coordinator_core.ops.percolate_preflight_scratch_publish not importable)

Spec backlink: DoE-claude:pln-doe-source-of-truth-percolatio-4722b4 § C6/AC8
Port backlink: docs/plans/2026-07-16-bash-clean-slate-residual-migration.md
Review note: the Director of Engineering F2 — running the transform bin directly does not exercise whether the
post_rsync-phase engine dispatch resolves DEPERSONALIZE_BIN from DoE; this script closes
that gap. (Historical: this originally referred to the 5 legacy post-rsync/*.sh hook
scripts, retired in the percolate-engine cutover, chunk C-W2.)

DR-276: routed through coordinator_core.cli_entry.run_op_main rather than a bare
in-process import + call, once --coordinator-root has been injected below. This
op writes nothing durable — every publish/guard re-check runs against a scratch
destination the op itself `_rmtree`s afterward (`--keep` aside, which is an
explicit operator opt-out of that cleanup, not a declared artifact) — so
run_op_main's declared-writes recording is a no-op here; it is still the
sanctioned entrypoint shape for consistency with every other trampoline in this
package.
"""

import os
import sys

def _resolve_coordinator_root() -> str:
    """Resolve the coordinator/ content root (owns bin/ guards; setup/ is its sibling —
    see coordinator_core.ops.percolate_preflight_scratch_publish.CoordinatorPaths).

    CLAUDE_PLUGIN_ROOT wins verbatim if set. Otherwise resolves via
    cc_invoke._resolve_claude_klabauter_root() (env CLAUDE_KLABAUTER_ROOT -> settings-home pointer file ->
    machine-local repos.claude_klabauter -> raise) and returns <claude_klabauter_root>/coordinator.

    DR-261 (docs/decisions/DR-261-claude-klabauter-owns-klabauter-publishing-end-to.md) moved
    klabauter publishing ownership -- the publish.py driver, the two leak guards, and
    the row/store config -- into the engine repo end to end. Before DR-261 this resolved
    via coordinator_registry.doe_root() (DoE-claude's repo root), because publish.py /
    the guards / the portable-targets file all lived DoE-side. That is no longer true:
    both `coordinator/bin/{publish,check-registry-codename-leak,check-persona-slug-leak}.py`
    AND the sibling `setup/publish-targets.portable` / `setup/percolate-hooks/
    percolate-store.yaml` now live in THIS repo. doe_root() pointed at
    the wrong repo post-move; this resolver was fixed to point at this repo instead.

    This still does NOT derive from this script's own __file__ location, even though
    __file__ *would* resolve to the right answer today (this script now lives inside
    the very root it needs to report). __file__-based resolution was rejected pre-DR-261
    because this script's on-disk location is not necessarily its content-authoritative
    location -- e.g. if this file itself is ever copied/mirrored into another repo or a
    discovered-repo checkout as part of a publish run, __file__ would resolve to that
    OTHER tree's coordinator/ dir, not this repo's own. For that reason this call site
    deliberately keeps using the bare `_resolve_claude_klabauter_root()` (env -> settings-home
    pointer -> machine-local registry, NO self-location rung) rather than the newer
    `require_engine_on_path()` (used a few lines below, in `_import_main()`, for a
    call site where self-location IS safe): `require_engine_on_path()` wraps
    `resolve_engine_root()`'s same env-first ladder, which consults __file__
    ahead of the registry, which is exactly the failure mode this docstring documents
    -- a copied/mirrored script would self-locate into the wrong tree instead of
    falling through to the registry. `_resolve_claude_klabauter_root()`'s pointer/registry-only
    ladder is invocation-location-independent and is the established pattern this
    repo already relies on for that reason.

    Fails loud (sys.exit(2), matching the op's own usage-error exit code)
    if _resolve_claude_klabauter_root() cannot resolve: this is a pre-flight gate script, not a
    never-block hook.
    """
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import _resolve_claude_klabauter_root

    env_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env_root:
        return env_root
    try:
        root = _resolve_claude_klabauter_root()
    except RuntimeError as exc:
        print(
            "percolate-preflight-scratch-publish.py: cannot resolve the claude-klabauter "
            f"repo root ({exc}). Set repos.claude_klabauter in the machine-local registry, "
            "or set the CLAUDE_KLABAUTER_ROOT env var, or set CLAUDE_PLUGIN_ROOT directly.",
            file=sys.stderr,
        )
        sys.exit(2)
    return os.path.join(root, "coordinator")


def _import_main():
    """Resolve the engine root, put it on sys.path, and import the ported entrypoint.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    self-location walk-up from this file -> settings-home pointer file ->
    machine-local registry) via `require_engine_on_path()` (which wraps
    `resolve_engine_root()`'s same ladder), rather than
    re-deriving it -- this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here (this is not a hot per-commit path, but the
    module's own dependency shell-outs to publish.py/the guards are already
    subprocess hops -- no benefit to adding a second envelope hop on top).
    Unlike `_resolve_coordinator_root()` above, self-location is safe here:
    this call resolves the engine checkout this SAME file lives in for its
    own in-process import, not a path reported to describe a possibly-copied
    script.

    That "safe" claim is narrower than `_resolve_coordinator_root()`'s
    rejection of self-location reads: it depends on this trampoline never
    being EXECUTED from inside a materialized copy of itself, not on
    self-location being safe in general (`_resolve_coordinator_root()`
    above still deliberately avoids `__file__` for that reason). Verified
    only this much: `publish.py::_git_materialize_ref` shadow trees ARE
    full copies of this repo (git-archive of the whole toplevel at a
    commit sha, so they carry both `coordinator_core/` and
    `pyproject.toml` and WOULD satisfy `_walk_up_to_checkout`'s probe if
    self-located into) but every checked publish.py call site that reads
    from a shadow tree (the `subprocess.run` sites invoking
    `check-registry-codename-leak.py`/`check-persona-slug-leak.py`/the
    version-consistency gate, plus the file-copy paths) treats it as a
    read-only COPY SOURCE, never as something re-executed in-process or
    re-invoked as this script. Not chased: every possible invocation
    surface, including an operator manually `cd`-ing into a materialized
    shadow tree and hand-running this script from there. If a future
    change ever causes this trampoline to be invoked from inside a
    `_git_materialize_ref` shadow root, self-location here would resolve
    into that (possibly stale/different-revision) shadow tree, and this
    call site would need to move back to the bare
    `_resolve_claude_klabauter_root()` ladder like `_resolve_coordinator_root()`
    above. — Review: code-reviewer P2 finding + EM ruling, 2026-08-07.
    """
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_engine_on_path

    require_engine_on_path(__file__)
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main(argv: "list[str] | None" = None) -> int:
    # argv threading: this CLI reads sys.argv at depth (argparse and helpers),
    # so the warm-call path swaps it for the duration rather than rewriting every read.
    # NOT re-entrant: a threaded server must serialise calls into this entrypoint.
    _prev_argv = sys.argv
    if argv is not None:
        sys.argv = [sys.argv[0], *argv]
    try:
        try:
            run_op_main = _import_main()
        except RuntimeError as exc:
            print(
                f"percolate-preflight-scratch-publish.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}",
                file=sys.stderr,
            )
            return 3
        except ImportError as exc:
            print(
                "percolate-preflight-scratch-publish.py: "
                f"coordinator_core.cli_entry not importable: {exc}",
                file=sys.stderr,
            )
            return 3
    
        # COORDINATOR_ROOT is resolved via _resolve_coordinator_root() (CLAUDE_PLUGIN_ROOT
        # env override, else <claude_klabauter_root>/coordinator via _resolve_claude_klabauter_root()) -- NOT
        # this file's own directory. Post-DR-261 this file's directory's parent DOES equal
        # the coordinator root (both live in this repo now), but resolution still goes
        # through the registry ladder rather than __file__ -- see _resolve_coordinator_root()'s
        # docstring for why. The op module owns the engine logic but not this repo's directory
        # layout (DR-047-style separation, now both sides engine-side post-DR-261), so this
        # trampoline supplies the resolved root explicitly rather than the module guessing.
        if "--coordinator-root" not in sys.argv[1:]:
            coordinator_root = _resolve_coordinator_root()
            argv = ["--coordinator-root", coordinator_root] + sys.argv[1:]
        else:
            argv = sys.argv[1:]
    
        try:
            return run_op_main("coordinator_core.ops.percolate_preflight_scratch_publish", argv)
        except ImportError as exc:
            print(
                "percolate-preflight-scratch-publish.py: "
                f"coordinator_core.ops.percolate_preflight_scratch_publish not importable: {exc}",
                file=sys.stderr,
            )
            return 3
    finally:
        sys.argv = _prev_argv


if __name__ == "__main__":
    sys.exit(main())
