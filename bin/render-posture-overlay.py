# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""render-posture-overlay.py — merges a Posture overlay block into a target file.

CLI trampoline over claude-klabauter coordinator_core.ops.render_posture_overlay, per
DR-047 (DoE owns contract/generator, claude-klabauter owns engine). Performs an
idempotent managed-section merge (marker-delimited insert/swap), detects
collisions against markerless legacy '## Posture'/'## Working Style'
headings, and creates the target when absent. The target is a consumer
repo's `.claude/em-context.md` — the EM-only channel — not a global
CLAUDE.md, so this op deliberately enforces NO byte budget: the CLAUDE.md
HARD threshold is a basename/governed-path concept that does not apply to a
per-repo file. What lives on the consuming side (assert-em-role.py's
repo-snippet soft cap) is read-time visibility, not a write-time refusal —
it banners an oversized em-context.md and then delivers it in full anyway,
so nothing blocks an oversized em-context.md from being written here, by
design. Do not reintroduce a size gate here. The DoE-resident coordinator_root (anchor templates) is
resolved here and passed into the op explicitly, since the op
cannot re-derive a DoE-only path itself. Resolution honors a
CLAUDE_PLUGIN_ROOT override first (matching every other bin/ trampoline's
env-override convention, e.g. coordinator/bin/snippet-registry's
_resolve_plugin_root), then falls back to the shared
coordinator_data_root.data_root() split-repo ladder — this file no longer
walks its own on-disk location to find templates/, since templates/ moved
to coordinator-content-repo in the 2026-07-22 executable-surface migration.
"""
# render-posture-overlay.py — CLI trampoline over claude-klabauter
# coordinator_core.ops.render_posture_overlay.
#
# Finish-strangler port (DR-059 / bash-clean-slate residual migration): the
# bash implementation (idempotent managed-section merge of a Posture overlay
# block into a target CLAUDE.md — marker-delimited insert/swap, collision
# detection against markerless legacy '## Posture'/'## Working Style'
# headings, size-guard enforcement against the check-claude-md-size.py hook's
# HARD threshold) has been fully ported to
# coordinator_core/ops/render_posture_overlay.py (see
# test_render_posture_overlay.py). This file is now a thin DoE-side
# (contract) trampoline over that claude-klabauter (engine) module, per DR-047 (DoE
# owns contract/generator, claude-klabauter owns engine).
#
# coordinator_root is resolved HERE (DoE-side) and passed into the op's
# main() explicitly — the anchor templates (templates/postures/<anchor>.md)
# are DoE-resident, not claude-klabauter-resident, so the op cannot re-derive this root
# itself the way a claude-klabauter-native op would. The op no longer reads a
# size-guard SSOT at all; templates/ is now the only DoE-resident input.
#
# Post-2026-07-22 executable-surface migration, this file's own on-disk
# location (coordinator/bin/ under claude-klabauter) is no longer a valid
# anchor for templates/ or hooks/ (those stayed in coordinator-content-repo, per DR-047).
# coordinator_root is now resolved via the shared
# coordinator_data_root.data_root() split-repo ladder (co-located rung 1 ->
# DoE-resident rung 2 via coordinator_registry.content_root()), with a
# CLAUDE_PLUGIN_ROOT env override taking precedence first — the same
# override convention every other bin/ trampoline honors (see
# coordinator/bin/snippet-registry's _resolve_plugin_root).
#
# Exit codes (parity-critical — forwarded verbatim from the op's own
# contract, see that module's docstring):
#   0 — success (insert/swap performed, or --check-only report printed)
#   1 — usage error / validation failure / collision
#   2 — engine-root resolution failure OR coordinator_core.ops.
#       render_posture_overlay not importable (transport/claude-klabauter-link
#       failure) — a DEDICATED code, distinct from both business codes
#       above, per the porter-brief addendum §3b rule that a transport
#       failure must never collide with a business exit code. This is a
#       fail-loud validator/gate script (its rc is consumed by install
#       flows to decide whether the merge happened), so — unlike
#       coordinator-auto-push's never-block posture — a claude-klabauter-link failure
#       here degrades to a loud, distinguishable exit 2, not a silent 0.
#
# Spec backlink: coordinator-content-repo:pln-bash-polyglot-clean-slate-full-5c71ee
# Prior bash implementation: see git log (render-posture-overlay.py, 262
#   lines pre-port, retired on this cutover)
import os
import sys

_BOOTSTRAPPED_NAMES = (
    "require_dispatch_engine_on_path",
    "data_root",
)

_BOOTSTRAP_DONE = False


def _bootstrap_engine() -> None:
    global _BOOTSTRAP_DONE
    if _BOOTSTRAP_DONE:
        return
    try:
        import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
        from cc_invoke import require_dispatch_engine_on_path
        from coordinator_data_root import data_root
    finally:
        _resolved = locals()
        for _name in _BOOTSTRAPPED_NAMES:
            if _name not in globals() and _name in _resolved:
                globals()[_name] = _resolved[_name]

    _BOOTSTRAP_DONE = True


def __getattr__(name: str):
    if name in _BOOTSTRAPPED_NAMES:
        _bootstrap_engine()
        if name not in globals():
            global _BOOTSTRAP_DONE
            _BOOTSTRAP_DONE = False
            _bootstrap_engine()
        try:
            return globals()[name]
        except KeyError:
            raise AttributeError(
                f"module {__name__!r} has no attribute {name!r} after bootstrap"
            ) from None
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _import_main():
    _bootstrap_engine()
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.ops.render_posture_overlay import main as _op_main

    return _op_main


def _import_recorder():
    _bootstrap_engine()
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import recording_declared_writes

    return recording_declared_writes


def _coordinator_root() -> str:
    """DoE-side coordinator/ root (parent of templates/ and hooks/).

    CLAUDE_PLUGIN_ROOT env override always wins (matches every other bin/
    trampoline's convention, e.g. coordinator/bin/snippet-registry's
    _resolve_plugin_root — this lets test fixtures and CI point the CLI at a
    synthetic coordinator root without touching real disk). Otherwise
    resolved via coordinator_data_root.data_root("templates").parent, the
    shared split-repo ladder (co-located rung 1 -> DoE-resident rung 2 via
    coordinator_registry.content_root()) — never re-derived here (see that
    module's negative-spec).
    """
    _bootstrap_engine()
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env:
        return env
    return str(data_root("templates").parent)


def main(argv: "list[str] | None" = None) -> int:
    _bootstrap_engine()
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(
            f"render-posture-overlay.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}",
            file=sys.stderr,
        )
        return 2
    except ImportError as exc:
        print(
            f"render-posture-overlay.py: coordinator_core.ops.render_posture_overlay "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        return 2

    try:
        recording_declared_writes = _import_recorder()
    except (RuntimeError, ImportError) as exc:
        print(
            f"render-posture-overlay.py: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        return 2

    with recording_declared_writes():
        code = op_main((sys.argv[1:] if argv is None else argv), coordinator_root=_coordinator_root())
    return code


if __name__ == "__main__":
    sys.exit(main())
