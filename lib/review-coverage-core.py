# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""review-coverage-core.py — shared coverage-computation core for review-trail gates.

CLI trampoline over claude-klabauter coordinator_core.ops.review_coverage_core (direct-import,
no @register_op — a plain in-process module call, not a JSON-RPC op). Provides the
reusable primitives consumed by review-trail coverage consumers: SAFE_RANGE
argument-injection validation, JSON-OR-JSONL dual-shape trail-record parsing, per-record
`git rev-list <sha_range>` resolution, and the canonical verdict filter (pending
excluded; ok/warn/blocked/waived/absent included). Called as a subprocess by
test_review_coverage_core.py and, via --segments-json, feeds workweek-trail-scope.py's
seam detection.
"""
# consumers — SAFE_RANGE argument-injection validator, JSON-OR-JSONL dual-shape
# no @register_op — this is a plain-module in-process call, not a JSON-RPC op).
#   TRAIL_FILES — newline-separated list of trail-file paths (alternative to
#   WEEK_START  — if set, only records whose filename date-prefix falls within
#                 [WEEK_START, TODAY] are processed (weekly-gate filtering).
#   TODAY       — if set, upper bound for date-prefix filtering (pairs with WEEK_START).

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bin", "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402


def _import_main():
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.ops.review_coverage_core import main as _op_main
    return _op_main


def main() -> None:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"review-coverage-core.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(2)
    except ImportError as exc:
        print(
            f"review-coverage-core.py: coordinator_core.ops.review_coverage_core not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)
    sys.exit(op_main(sys.argv[1:]))


if __name__ == "__main__":
    main()
