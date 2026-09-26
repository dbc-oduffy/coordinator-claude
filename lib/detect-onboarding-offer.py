from __future__ import annotations
#     DETECT_ONBOARDING_REPO_ROOT    — repo to check (default: git root of cwd)
#     DETECT_ONBOARDING_PLUGIN_ROOT  — coordinator plugin root (default: this
# Port backlink: docs/plans/2026-07-16-bash-clean-slate-residual-migration.md, BIG_PORT wave
import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PLUGIN_ROOT = os.path.dirname(_SCRIPT_DIR)
_LIB_DIR = os.path.join(_PLUGIN_ROOT, "bin", "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402


def _import_main():
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.ops.detect_onboarding_offer import main as _op_main
    return _op_main


def main() -> None:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(
            f"detect-onboarding-offer.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}",
            file=sys.stderr,
        )
        sys.exit(0)
    except ImportError as exc:
        print(
            f"detect-onboarding-offer.py: coordinator_core.ops.detect_onboarding_offer "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(0)
    sys.exit(op_main(sys.argv[1:], default_plugin_root=_PLUGIN_ROOT))


if __name__ == "__main__":
    main()
