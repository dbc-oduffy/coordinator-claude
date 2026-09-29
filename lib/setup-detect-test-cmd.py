#   4  — TRANSPORT FAILURE: the engine root could not be resolved, or the claude-klabauter
#        found nothing" (PORTER-BRIEF-ADDENDUM.md rule A3b). On a cold
#   (BIG_PORT Wave C, item setup-detect-test-cmd)

from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.normpath(os.path.join(_HERE, "..", "bin", "lib"))
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402


def _import_main():
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.install.detect_test_cmd import main as _op_main

    return _op_main


def main() -> None:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"setup-detect-test-cmd: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        print(
            "  Remediation: ensure CLAUDE_KLABAUTER_ROOT is set, or that "
            "repos.claude_klabauter is registered in "
            "<settings-home>/machine-local/registry(.local).toml.",
            file=sys.stderr,
        )
        sys.exit(4)
    except ImportError as exc:
        print(
            f"setup-detect-test-cmd: coordinator_core.install.detect_test_cmd not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(4)
    sys.exit(op_main(sys.argv[1:]))


if __name__ == "__main__":
    main()
