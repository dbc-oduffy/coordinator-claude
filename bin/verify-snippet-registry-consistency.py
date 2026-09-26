from __future__ import annotations
# is consistent with the 4 HARDCODED-shape verify-<X>-sync.sh scripts
#       coordinator_core.snippet_sync.registry._SUPPORTED_SCHEMA_VERSIONS and is
#   4 — DEDICATED transport-failure code (PORTER-BRIEF-ADDENDUM § 3b): the

import os
import sys

_TRANSPORT_FAILURE_EXIT = 4


def _resolve_plugin_root() -> str:
    """Resolve the plugin root (coordinator/) that owns snippets/registry.toml.

    Env var CLAUDE_PLUGIN_ROOT wins if set, returned verbatim. Otherwise
    resolves via doe_root() (see that function's own docstring for its
    env-var/machine-local resolution chain) and returns
    <doe_root()>/coordinator.

    This does NOT derive from this script's own __file__ location. b644d5a9
    migrated this executable to claude-klabauter while snippets/ (and
    registry.toml) stayed in DoE-claude — self-location now resolves to
    <claude-klabauter>/coordinator, which has no snippets/ at all. doe_root() is the
    correct authority for "where is the DoE-claude repo," independent of
    where THIS script happens to run from. Do not "restore" __file__-based
    resolution to regain byte-parity with the retired bash oracle — that
    parity is exactly what caused the break once this file moved repos.

    Fails loud (sys.exit(_TRANSPORT_FAILURE_EXIT)) if doe_root() cannot
    resolve, via the same transport-failure path as engine-root resolution
    below — this is a gate script, not a never-block hook.
    """
    _bootstrap_engine()
    from coordinator_data_root import content_root_or_private
    from coordinator_registry import _DoeUnresolvable, doe_root

    env_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env_root:
        return env_root
    try:
        root = doe_root()
    except _DoeUnresolvable as exc:
        print(
            "verify-snippet-registry-consistency: cannot resolve the coordinator doctrine repo root "
            f"({exc}). Set repos.doe_claude in the machine-local registry, or set "
            "the DOE_ROOT env var, or set CLAUDE_PLUGIN_ROOT directly.",
            file=sys.stderr,
        )
        sys.exit(_TRANSPORT_FAILURE_EXIT)
    return content_root_or_private(root)


def _bootstrap_engine() -> str:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    return require_dispatch_engine_on_path()


def _import_main():
    _bootstrap_engine()
    from coordinator_core.snippet_sync.verify_registry_consistency import main as _op_main
    return _op_main


def main(argv: "list[str] | None" = None) -> int:
    # transport-failure code (4), per PORTER-BRIEF-ADDENDUM § A3b's
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(
            f"verify-snippet-registry-consistency: engine-root resolution failed: {exc}",
            file=sys.stderr,
        )
        return _TRANSPORT_FAILURE_EXIT
    except ImportError as exc:
        print(
            "verify-snippet-registry-consistency: "
            f"coordinator_core.snippet_sync.verify_registry_consistency not importable: {exc}",
            file=sys.stderr,
        )
        return _TRANSPORT_FAILURE_EXIT

    plugin_root = _resolve_plugin_root()
    return op_main([plugin_root] + (sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    sys.exit(main())
