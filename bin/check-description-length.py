#!/usr/bin/env python3
# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
check-description-length.py — CLI trampoline over claude-klabauter
coordinator_core.ops.check_description_length.

Assert each enabled SKILL.md description fits its budget. Three-tier limit:
    - `description-budget: <N>` frontmatter field present -> use N
    - PM-gated skill (description starts with "PM-GATED" / "**PM-GATED**")
      -> use 175
    - default -> 150

Advisory-only caller: /workweek-complete captures this script's stdout/rc
without propagating a non-zero exit to the ceremony (see
docs/wiki/workday-workweek-cadence.md).

Port target: coordinator_core.ops.check_description_length (claude-klabauter).
"""

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402


def _import_main():
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.ops.check_description_length import main as _op_main
    return _op_main


def main() -> None:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"check-description-length.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(1)
    except ImportError as exc:
        print(f"check-description-length.py: coordinator_core.ops.check_description_length not importable: {exc}", file=sys.stderr)
        sys.exit(1)
    sys.exit(op_main(sys.argv[1:]))


if __name__ == "__main__":
    main()
