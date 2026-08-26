"""trusted-root-guard-cli.py — Python-native CLI trampoline over claude-klabauter
coordinator_core.trusted_root_guard.coordinator_trusted_root_guard_or_exit.

Purpose: gives a bash call site that has NOT yet resolved PYTHON_BIN (the
bootstrap-order situation the session-state fallback branches below are in —
this CLI is invoked exactly when resolve-python.sh could not be found at its
expected BASH_SOURCE-relative sibling path) a way to run the shared
CLAUDE_PLUGIN_ROOT trust-check natively instead of sourcing the former bash
sourced-lib coordinator-trusted-root-guard.sh (deleted 2026-07-22 — every
caller now invokes this CLI, or imports coordinator_core.trusted_root_guard
directly where the call site is already Python).

Trust-core + mode semantics are NOT reimplemented here — this is a thin argv
passthrough to coordinator_core.trusted_root_guard (DR-047: DoE owns
contract, claude-klabauter owns engine).

This CLI is now the sole non-Python entrypoint for the trust-core check.

Usage:
  trusted-root-guard-cli.py --mode=fail-loud|fail-open --root=<path> [--site=<label>]

Exit codes (parity with the former bash sourced-lib function's contract):
  0 — root is trusted. Caller proceeds unchanged in both modes.
  1 — root is untrusted (fail-loud: an ERROR line was already printed to
      stderr by the underlying module before this process exits; fail-open:
      at most one WARNING line was printed when the anomaly is
      security-relevant, silent on routine absence — caller is responsible
      for blanking its own root variable on a nonzero exit, mirroring the
      bash function's no-nameref contract).
      Also used for a missing/invalid --mode or --root (the module's
      documented "--mode is REQUIRED" message is printed verbatim).
  2 — transport failure: the engine root could not be resolved, or
      coordinator_core.trusted_root_guard is not importable. Distinct from
      the business-rejection code above (porter addendum §3/3b) — a
      claude-klabauter-link failure must not read as "untrusted root".

Spec backlink: docs/plans/2026-07-19-bash-clean-slate-residual-migration.md [DEAD-CITATION: plan file never committed to this repo]
               § unit-coordinator-session-family
Canonical trust-core: coordinator_core.trusted_root_guard (claude-klabauter) —
                       prose/trust-core doc-of-record remains
                       coordinator/snippets/cc-root-source-guard.md
Native module: claude-klabauter coordinator_core/trusted_root_guard.py
"""
from __future__ import annotations

import os
import sys


def _resolve_claude_klabauter_root() -> str:
    """Delegate to cc_invoke's battle-tested engine-root resolution ladder
    (env var -> settings-home pointer file -> coordinator-claude-klabauter-root.sh)
    rather than re-deriving it — mirrors migrate-state-to-claude-klabauter.sh's
    _import_main().
    """
    _this_dir = os.path.dirname(os.path.abspath(__file__))
    # lib/ -> coordinator/ -> coordinator/bin/lib/
    _coordinator_root = os.path.dirname(_this_dir)
    _bin_lib_dir = os.path.join(_coordinator_root, "bin", "lib")
    if _bin_lib_dir not in sys.path:
        sys.path.insert(0, _bin_lib_dir)
    from cc_invoke import require_dispatch_engine_on_path  # noqa: E402

    return require_dispatch_engine_on_path()


def _parse_args(argv: list[str]) -> tuple[str, str, str]:
    mode = ""
    root: str | None = None
    site = "coordinator root"
    for arg in argv:
        if arg.startswith("--mode="):
            mode = arg[len("--mode="):]
        elif arg.startswith("--root="):
            root = arg[len("--root="):]
        elif arg.startswith("--site="):
            site = arg[len("--site="):]
        else:
            print(f"trusted-root-guard-cli.py: unrecognized arg {arg!r}", file=sys.stderr)
            sys.exit(1)
    if root is None:
        print("trusted-root-guard-cli.py: --root is REQUIRED", file=sys.stderr)
        sys.exit(1)
    return mode, root, site


def main() -> None:
    mode, root, site = _parse_args(sys.argv[1:])

    try:
        claude_klabauter_root = _resolve_claude_klabauter_root()
    except RuntimeError as exc:
        print(
            f"trusted-root-guard-cli.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)

    try:
        from coordinator_core.trusted_root_guard import (
            coordinator_trusted_root_guard_or_exit,
        )
    except ImportError as exc:
        print(
            f"trusted-root-guard-cli.py: coordinator_core.trusted_root_guard "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)

    try:
        trusted = coordinator_trusted_root_guard_or_exit(mode=mode, root=root, site=site)
    except ValueError as exc:
        # Missing/invalid --mode — module's own message already carries the
        # "coordinator_trusted_root_guard: ..." prefix; print verbatim for
        # parity with the bash function's echo-to-stderr shape.
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    # fail-loud's rejection branch calls sys.exit(1) inside
    # coordinator_trusted_root_guard_or_exit itself (mirrors the bash
    # function's literal `exit 1`); reaching here means either mode
    # returned normally — 0 for trusted, 1 for fail-open's untrusted return.
    sys.exit(0 if trusted else 1)


if __name__ == "__main__":
    main()
