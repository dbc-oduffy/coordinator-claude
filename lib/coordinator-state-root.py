"""coordinator-state-root.py — Python-native CLI trampoline over claude-klabauter
coordinator_core.state_root.coordinator_state_root.

Purpose: single entry point for resolving the coordinator state directory
root. Replaces the sourced bash oracle that paid the bash-invocation tax on
every call and degrades Windows. Its
5-rule routing logic is NOT reimplemented here — the claude-klabauter side already
carries a native peer, `coordinator_core.state_root` (COMPOSED over the
already-native `coordinator_core.ops.coordinator_doe_root`,
`coordinator_core.engine_root`, `coordinator_core.artifact_subject`, and
`coordinator_core.meta_repo_identity`), so this file is a thin argv/exit-code
+ importable bridge over that seam — mirroring `coordinator-is-meta-repo.py`'s
bridge shape (DR-047: DoE owns contract, claude-klabauter owns engine).

De-bash campaign port: docs/plans/2026-07-16-bash-clean-slate-residual-migration.md
Spec backlinks:
  docs/plans/2026-07-03-stop-the-rot-claude-klabauter-state-home-placement.md § C2 / AC2
  docs/plans/2026-07-04-doe-authoring-repo-build-subject-matter-.md § W2.3

Usage (byte-for-byte CLI parity with the retired bash oracle):
  coordinator-state-root.py [--central] [--subject <engine|doctrine>] [--artifact <path>]
    Prints the resolved state root path to stdout (no trailing newline).
    Returns 0 on success, 1 on failure (stderr carries remediation message),
    or 2 when --artifact resolves to cross-cutting (human routing required).

  coordinator-state-root.py --print-map
    Prints a single-line JSON object mapping the two central subjects to
    their resolved state roots:
      {"schema":"coordinator-state-root-map/v1","subjects":{"doctrine":"<doe>/state","engine":"<claude-klabauter>/state"}}
    Unresolvable subjects emit JSON null (not a hard error) plus one stderr
    WARN line per unresolvable subject; always returns 0.
    --print-map is standalone: cannot be combined with --subject or
    --artifact (returns 1). --central alongside --print-map is
    harmless/ignored.

Exit codes:
  0 — success (state-root path printed), or --print-map (always 0)
  1 — usage error or resolution failure (bad flags, unresolvable root),
      OR engine-root transport failure (cannot reach the native seam) —
      the transport failure is folded into the same rc=1 shape the bash
      oracle used for "coordinator_state_root failed", so callers checking
      only exit-code parity see no behavior change.
  2 — --artifact resolves to cross-cutting (human routing decision
      required); preserves the classifier's exit-2 semantics.

Public API (importable, mirrors the retired bash function's call shape):
    coordinator_state_root(central=False, subject=None, artifact=None,
                            git_root=None) -> str
        Returns the resolved <root>/state path. Raises RuntimeError on any
        failure (engine-root transport, or the native module's own
        StateRootError/CrossCuttingStateRoot — both subclass RuntimeError).
        A caller that wants to discriminate cross-cutting (rc=2) from a
        plain failure (rc=1) should import CrossCuttingStateRoot from this
        module and catch it specifically (re-exported below).
    print_map() -> str
        Single-line JSON central map; delegates directly to the native
        module's print_map(). Raises RuntimeError on engine-root transport
        failure only (the native print_map() itself never raises — it
        folds each subject's own failure to JSON null + stderr WARN).

Negative-spec (faithfully reproduced — do NOT "fix" mid-port):
  - Does NOT reimplement any of the 5 routing rules — delegates entirely to
    coordinator_core.state_root.
  - Does NOT fall back silently when git root is missing (Rule 5) — the
    native module fails loud; this bridge does not swallow that failure.
  - Does NOT fall back to claude-klabauter when doctrine DoE root fails (Rule 1).
  - Does NOT auto-route a cross-cutting artifact (Rule 3) — rc=2 preserved.
  - Does NOT define any function named `coordinator_claude_klabauter_root` — that
    identifier is owned by the still-live coordinator-claude-klabauter-root.sh
    (collision-avoidance note carried over from the retired bash oracle;
    see that file's own header for why a same-named public function here
    would silently collide via source-order-dependent resolution).

Port of: coordinator-state-root.sh (DoE 6fb5fb37, 2026-07-22, bash sourced-lib oracle)
Native module: claude-klabauter coordinator_core/state_root.py
"""
from __future__ import annotations

import os
import sys
from typing import List, Optional


def _cc_invoke():
    """Put `coordinator/bin/lib` on `sys.path` and hand back `cc_invoke`.

    Extracted because both callers below need a name out of that module and
    only one of them used to do the path setup: `require_dispatch_engine_on_path`
    was imported into `_resolve_claude_klabauter_root`'s LOCAL scope and then referenced
    from `_import_state_root`, a different function, so every call raised
    `NameError` and this CLI could not resolve a state root at all. The
    failure is silent at the callers that treat it as best-effort --
    `percolate-round.py :: _resolve_central_state` maps a non-zero exit to
    `None` and drops the peer-repo-name scan leg without saying so.
    """
    _this_dir = os.path.dirname(os.path.abspath(__file__))
    # lib/ -> coordinator/ -> coordinator/bin/lib/
    _coordinator_root = os.path.dirname(_this_dir)
    _bin_lib_dir = os.path.join(_coordinator_root, "bin", "lib")
    if _bin_lib_dir not in sys.path:
        sys.path.insert(0, _bin_lib_dir)
    import cc_invoke  # noqa: PLC0415 - path must be set first

    return cc_invoke


def _resolve_claude_klabauter_root() -> str:
    """Delegate to cc_invoke's battle-tested engine-root resolution ladder
    (env var -> settings-home pointer file -> machine-local registry ->
    coordinator_core.engine_root) rather than re-deriving it — mirrors
    coordinator-is-meta-repo.py's _resolve_claude_klabauter_root().
    """
    return _cc_invoke()._resolve_claude_klabauter_root()


def _import_state_root():
    """Resolve the engine root, put it on sys.path, and import the native seam.

    Raises RuntimeError (engine root unresolvable) or ImportError
    (coordinator_core.state_root not importable) — both are transport
    failures the CLI maps to exit code 1, distinct from the module's own
    StateRootError/CrossCuttingStateRoot business-logic failures.
    """
    claude_klabauter_root = _cc_invoke().require_dispatch_engine_on_path()
    from coordinator_core.state_root import (  # noqa: E402
        CrossCuttingStateRoot as _CrossCuttingStateRoot,
        StateRootError as _StateRootError,
        coordinator_state_root as _native_coordinator_state_root,
        print_map as _native_print_map,
    )

    return _native_coordinator_state_root, _native_print_map, _StateRootError, _CrossCuttingStateRoot


# Re-exported so importers can `from coordinator_state_root import CrossCuttingStateRoot`
# after loading this hyphenated module via importlib (see test/import precedent in
# coordinator-artifact-subject.test.py) without reaching into coordinator_core directly.
# Populated lazily on first successful _import_state_root() call — None until then.
StateRootError: Optional[type] = None
CrossCuttingStateRoot: Optional[type] = None


def coordinator_state_root(
    central: bool = False,
    subject: Optional[str] = None,
    artifact: Optional[str] = None,
    git_root: Optional[str] = None,
) -> str:
    """Importable public API mirroring the retired bash function's call
    shape. Raises RuntimeError on any resolution failure: engine-root
    transport, or the native module's own StateRootError /
    CrossCuttingStateRoot (both already subclass RuntimeError).
    """
    global StateRootError, CrossCuttingStateRoot
    native_fn, _native_print_map, _StateRootError, _CrossCuttingStateRoot = _import_state_root()
    StateRootError = _StateRootError
    CrossCuttingStateRoot = _CrossCuttingStateRoot
    return native_fn(central=central, subject=subject, artifact=artifact, git_root=git_root)


def print_map() -> str:
    """Importable public API mirroring `--print-map`. Raises RuntimeError
    only on engine-root transport failure — the native print_map() itself
    never raises (each subject's own failure folds to JSON null + stderr
    WARN)."""
    global StateRootError, CrossCuttingStateRoot
    _native_fn, native_print_map, _StateRootError, _CrossCuttingStateRoot = _import_state_root()
    StateRootError = _StateRootError
    CrossCuttingStateRoot = _CrossCuttingStateRoot
    return native_print_map()


def main(argv: Optional[List[str]] = None) -> int:
    """CLI-shaped wrapper preserving the bash oracle's exit codes for
    parity: prints the resolved path to stdout (no trailing newline) and
    returns 0; or writes remediation to stderr and returns 1 (usage error /
    StateRootError / engine-root transport failure) / 2
    (CrossCuttingStateRoot). ``--print-map`` prints the JSON map and
    returns 0."""
    args = list(sys.argv[1:] if argv is None else argv)

    central = False
    subject: Optional[str] = None
    artifact: Optional[str] = None
    want_print_map = False

    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--central":
            central = True
            i += 1
        elif arg == "--subject":
            if i + 1 >= len(args) or not args[i + 1]:
                print(
                    "coordinator_state_root: --subject requires an argument: engine or doctrine",
                    file=sys.stderr,
                )
                return 1
            subject = args[i + 1]
            i += 2
        elif arg == "--artifact":
            if i + 1 >= len(args) or not args[i + 1]:
                print(
                    "coordinator_state_root: --artifact requires an argument: an artifact path",
                    file=sys.stderr,
                )
                return 1
            artifact = args[i + 1]
            i += 2
        elif arg == "--print-map":
            want_print_map = True
            i += 1
        else:
            print(
                f"coordinator_state_root: unknown flag '{arg}'; valid flags: "
                "--central, --subject, --artifact, --print-map",
                file=sys.stderr,
            )
            return 1

    # (Review: code-reviewer — F2, 2026-07-22: restored dropped negative-spec
    # branch from the bash oracle, ordered before the --print-map check to
    # mirror its original sequencing.)
    if subject is not None and artifact is not None:
        print(
            "coordinator_state_root: --subject and --artifact are mutually exclusive; specify at most one",
            file=sys.stderr,
        )
        return 1

    if want_print_map and (subject is not None or artifact is not None):
        print(
            "coordinator_state_root: --print-map cannot be combined with --subject/--artifact",
            file=sys.stderr,
        )
        return 1

    try:
        native_fn, native_print_map, _StateRootError, _CrossCuttingStateRoot = _import_state_root()
    except RuntimeError as exc:
        print(f"coordinator_state_root: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return 1
    except ImportError as exc:
        print(
            f"coordinator_state_root: coordinator_core.state_root not importable: {exc}",
            file=sys.stderr,
        )
        return 1

    if want_print_map:
        sys.stdout.write(native_print_map())
        return 0

    try:
        path = native_fn(central=central, subject=subject, artifact=artifact)
    except _CrossCuttingStateRoot as exc:
        print(exc.message, file=sys.stderr)
        return 2
    except _StateRootError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    sys.stdout.write(path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
