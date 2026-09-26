# file as `"$PYTHON_BIN" "${PYTHON_ARGS[@]}" "${_PLUGIN_ROOT}/lib/setup-rag-decision.py" --root "$(pwd)"`
# is EXECUTABLE-ONLY. The sole live caller never sources this file (its own
#      coordinator_core.ops.setup_rag_decision not importable. A DEDICATED

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bin", "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402


def _import_main():
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.ops.setup_rag_decision import main as _op_main

    return _op_main


def main() -> None:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"setup-rag-decision: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(2)
    except ImportError as exc:
        print(
            f"setup-rag-decision: coordinator_core.ops.setup_rag_decision not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(op_main(sys.argv[1:]))


if __name__ == "__main__":
    main()
