# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
check-shipped-on-main.py — CLI trampoline over claude-klabauter
coordinator_core.ops.emit.resolvers.main (the `check-shipped-on-main.py` port).

Verify that one or more commits are reachable from origin/main (i.e., actually
shipped). Thin wrapper around `git merge-base --is-ancestor` providing a
consistent "is this work on main?" query. Its existence is the doctrine
signal — callers (handoff.md, lessons, rollup-derive.py, etc.) name this
script rather than inventing their own one-liner, so the definition of
"shipped" stays in one place and is greppable.

Usage:
  check-shipped-on-main.py [--verbose] <commit> [<commit>...]

Exit codes:
  0 — all commits are on origin/main.
  1 — at least one commit is NOT on origin/main (or a CLI-usage error).
  2 — not inside a git repository, origin/main is unreachable, or the
      claude-klabauter engine link itself failed (fail-loud — a "can't determine
      shipped-ness" outcome must never be silently reported as success).

Spec backlink: archive/specs/2026-05-01-orphan-branch-prevention.md § 1.2
Port of: git merge-base ancestor-check logic ported to
  coordinator_core/ops/emit/resolvers.py (_sha_on_origin_main et al., reused
  from the pre-existing `_stamp_shipped_sha` amortised-fetch helpers); the CLI
  entry point (`main(argv)`) was added to that module by this port.

Negative-spec: read-only. Never modifies the repo.
"""

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402


def _import_main():
    """Resolve the engine root, put it on sys.path, and import the ported CLI entry.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it — this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.
    """
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.ops.emit.resolvers import main as _op_main

    return _op_main


def main() -> None:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"check-shipped-on-main: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(2)
    except ImportError as exc:
        print(
            f"check-shipped-on-main: coordinator_core.ops.emit.resolvers not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(op_main(sys.argv[1:]))


if __name__ == "__main__":
    main()
