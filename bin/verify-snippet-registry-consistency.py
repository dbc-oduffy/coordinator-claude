from __future__ import annotations
# verify-snippet-registry-consistency — CLI trampoline over claude-klabauter
# coordinator_core.snippet_sync.verify_registry_consistency.
#
# Sync-of-syncs verifier for snippets/registry.toml. Confirms registry.toml
# is consistent with the 4 HARDCODED-shape verify-<X>-sync.sh scripts
# (reviewer-calibration, docs-checker-consumption,
# plan-coverage-check-consumption, prior-art-check-consumption).
#
# Usage:
#   verify-snippet-registry-consistency          Run all checks. Exit 0 on success.
#   verify-snippet-registry-consistency --list    Print one line per check in execution order.
#
# Exit codes:
#   0 — all checks pass
#   1 — consistency violation (printed to stderr)
#   2 — missing dep or file not found (ALSO: missing schema_version — a
#       faithfully-reproduced oracle quirk, see the claude-klabauter module's own
#       negative-spec docstring)
#   3 — schema_version present but unsupported (not 1 or 2)
#   4 — DEDICATED transport-failure code (PORTER-BRIEF-ADDENDUM § 3b): the
#       coordinator-root / engine-root resolution failed, the DoE-claude repo
#       root (which owns snippets/registry.toml) was unresolvable, or
#       coordinator_core.snippet_sync.verify_registry_consistency was not
#       importable. Distinct from business code 2 ("missing dep or file not
#       found" — a repo-content problem) so a caller can tell "claude-klabauter link is
#       down" apart from "registry.toml is missing on disk".
#
# Port of: verify-snippet-registry-consistency.sh (DoE 93887f6f, 2026-07-17)
# Spec backlinks:
#   - docs/plans/2026-06-15-snippet-sync-consumer-registry.md § Dispatch Ledger C4, C8
#   - docs/decisions/2026-06-15-snippet-registry-shape.md § Schema amendments — the Staff Engineer C2

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402
from coordinator_registry import _DoeUnresolvable, doe_root  # noqa: E402

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
    return os.path.join(root, "coordinator")


def _import_main():
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.snippet_sync.verify_registry_consistency import main as _op_main
    return _op_main


def main() -> None:
    # Review: code-reviewer — business codes 0/1/2/3 are all already spoken
    # for here (2 = "missing dep or file not found", a repo-content problem);
    # a claude-klabauter-link failure is an architecturally distinct failure mode (a
    # coordinator/claude-klabauter packaging problem) and gets its OWN dedicated
    # transport-failure code (4), per PORTER-BRIEF-ADDENDUM § A3b's
    # never-reuse-a-business-rc rule — matching the other two trampolines in
    # this slice (coordinator-complete-entry.py, platform-localize.sh), which
    # both correctly mint a previously-unused dedicated code for this case.
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(
            f"verify-snippet-registry-consistency: engine-root resolution failed: {exc}",
            file=sys.stderr,
        )
        sys.exit(_TRANSPORT_FAILURE_EXIT)
    except ImportError as exc:
        print(
            "verify-snippet-registry-consistency: "
            f"coordinator_core.snippet_sync.verify_registry_consistency not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(_TRANSPORT_FAILURE_EXIT)

    plugin_root = _resolve_plugin_root()
    sys.exit(op_main([plugin_root] + sys.argv[1:]))


if __name__ == "__main__":
    main()
