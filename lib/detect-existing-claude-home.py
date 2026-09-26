#   CLAUDE_CONFIG_DIR=<dir> detect-existing-claude-home.py
# Spec backlink: docs/plans/2026-07-16-bash-to-naked-python-engine-migration.md [DEAD-CITATION: plan file never committed to this repo]
from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin", "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402


def _import_main():
    """Resolve the engine root, put it on sys.path, and import the ported entrypoint.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it -- this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here: the classifier is a handful of filesystem
    stat/listdir calls, and routing it through a JSON-RPC envelope would add a
    subprocess hop for a call this cheap.
    """
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.ops.detect_existing_claude_home import main as _op_main

    return _op_main


def main() -> int:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        # CLAUDE_KLABAUTER_ROOT resolution failed. This is a best-effort advisory
        print(
            f"detect-existing-claude-home.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}",
            file=sys.stderr,
        )
        return 0
    except ImportError as exc:
        print(
            "detect-existing-claude-home.py: "
            f"coordinator_core.ops.detect_existing_claude_home not importable: {exc}",
            file=sys.stderr,
        )
        return 0

    return op_main(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
