#!/usr/bin/env python3
#
# gem-inbox-apply — CLI trampoline over claude-klabauter coordinator_core.gem_inbox_apply.
#
# Applies a fleet-inbox-blitz APPLY MANIFEST (JSON) to the repo it names: pending
# ledger, writes, baton lint, guarded stamps, moves, memos_to_send, one scoped
# `git commit -- <pathspec>`, ledger delete.
#
# Usage:
#   gem-inbox-apply <manifest.json>
#
# Exit codes:
#   0 — applied
#   1 — manifest refused (baton lint failed; writes removed, nothing stamped)
#   2 — usage error (missing/unknown argument, manifest not found)
#   3 — TRANSPORT failure (engine-root resolution or import failed), or the
#       scoped commit failed

from __future__ import annotations

import sys


def _import_main():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    require_dispatch_engine_on_path()
    from coordinator_core.gem_inbox_apply import main as _main

    return _main


def main(argv: "list[str] | None" = None) -> int:
    try:
        run = _import_main()
    except RuntimeError as exc:
        print(f"gem-inbox-apply: engine-root resolution failed: {exc}", file=sys.stderr)
        return 3
    except ImportError as exc:
        print(f"gem-inbox-apply: coordinator_core.gem_inbox_apply not importable: {exc}", file=sys.stderr)
        return 3
    return run(sys.argv[1:] if argv is None else argv)


if __name__ == "__main__":
    sys.exit(main())
