#!/usr/bin/env python3
"""run-tests.py — CLI trampoline over claude-klabauter coordinator_core.ops.whoami_run_tests.

Canonical test runner for the coordinator_whoami package. coordinator_whoami
is a standalone installable package (its own pyproject.toml, editable
install, jsonschema dependency) nested inside the ~/.claude meta-repo. Bare
`pytest` under the meta-repo's ambient interpreter cannot run these tests —
it lacks the editable install, jsonschema, and the correct sys.path, and may
import a stale installed copy of the package. This wrapper provisions an
isolated .venv (idempotent) and runs pytest inside it, so the suite is
reproducible on any machine.

Usage:
  ./run-tests.py                       # run the whole suite
  ./run-tests.py tests/test_machine.py # run a selector (any pytest args pass through)

Exit code is pytest's — 0 == green. On claude-klabauter-link failure (CLAUDE_KLABAUTER_ROOT
unresolvable, or coordinator_core.ops.whoami_run_tests not importable) this
exits 1 (fail-loud) — a broken test-runner must not report a false green.

Port of: coordinator/whoami/run-tests.sh (sh-suffixed polyglot trampoline
retired on the 2026-07-20 sh-suffix-polyglot de-bash sweep — see
state/audits/2026-07-20-sh-suffixed-python-trampolines.md; git log carries
the bash-era history predating that trampoline).
Port backlink: docs/plans/2026-07-16-bash-clean-slate-residual-migration.md
"""
from __future__ import annotations

import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(_SCRIPT_DIR, "..", "bin", "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402


def _import_main():
    """Resolve CLAUDE_KLABAUTER_ROOT, put it on sys.path, and import the ported CLI entry.

    Reuses cc_invoke's battle-tested CLAUDE_KLABAUTER_ROOT resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it — this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.
    """
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.ops.whoami_run_tests import main as _op_main

    return _op_main


def main() -> None:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"run-tests.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(1)
    except ImportError as exc:
        print(
            f"run-tests.py: coordinator_core.ops.whoami_run_tests not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    sys.exit(op_main(sys.argv[1:], base_dir=_SCRIPT_DIR))


if __name__ == "__main__":
    main()
