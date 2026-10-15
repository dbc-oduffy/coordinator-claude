"""
check-fleet-claude-md-handoff-convention.py -- CLI trampoline over
coordinator_core.plugin_health.claude_md_handoff_convention.

Advisory lint: prints one line per fleet CLAUDE.md teaching the retired handoff location; exit 0 always.
"""

from __future__ import annotations

import argparse
import sys


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check-fleet-claude-md-handoff-convention",
        description="Flag fleet CLAUDE.md files that teach the retired handoff location (advisory, exit 0).",
    )
    parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        import lib  # noqa: F401 -- bootstraps coordinator/bin/lib onto sys.path
        from cc_invoke import require_dispatch_engine_on_path

        require_dispatch_engine_on_path()
        from coordinator_core.plugin_health.claude_md_handoff_convention import main as op_main
    except RuntimeError as exc:
        print(f"check-fleet-claude-md-handoff-convention: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return 0
    except ImportError as exc:
        print(f"check-fleet-claude-md-handoff-convention: not importable: {exc}", file=sys.stderr)
        return 0
    return op_main([])


if __name__ == "__main__":
    sys.exit(main())
