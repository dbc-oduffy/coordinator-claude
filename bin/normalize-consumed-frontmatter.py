"""normalize-consumed-frontmatter.py — reconciles a record's frontmatter with its consumed marker.

Flips a record's frontmatter to match its body's `<!-- consumed: YYYY-MM-DD
[notes] -->` marker: status -> consumed, deployment_state -> shipped,
consumed_at/shipped_in insertion, gate_dependency strip. A byte-parity port
of the retired node oracle's own module; engine logic lives claude-klabauter-side in
coordinator_core.ops.normalize_claimed_frontmatter (module renamed from
normalize_consumed_frontmatter per DR-084), and this file is a thin DoE-side
trampoline (direct in-process import, no subprocess re-spawn tax).
"""
from __future__ import annotations
# normalize-consumed-frontmatter.py — CLI trampoline over claude-klabauter
# coordinator_core.ops.normalize_claimed_frontmatter.
#
# Purpose: flips a record's frontmatter to match its body's
# `<!-- consumed: YYYY-MM-DD [notes] -->` marker (status -> consumed,
# deployment_state -> shipped, consumed_at/shipped_in insertion,
# gate_dependency strip). The engine (claude-klabauter's
# coordinator_core/ops/normalize_claimed_frontmatter.py, renamed from
# normalize_consumed_frontmatter per DR-084) is a byte-parity port of the
# node oracle's own module — this file is a thin DoE-side
# (contract) trampoline over that engine module, per DR-047 (DoE owns
# contract/generator, claude-klabauter owns engine), following the refresh-queries.py
# precedent: engine in claude-klabauter, thin DoE trampoline, no subprocess re-spawn
# tax (direct in-process import via _resolve_claude_klabauter_root, same as
# refresh-queries.py — NOT a `python -c` bootstrap subprocess like the
# retired node oracle used).
#
# Prior node implementation: coordinator/bin/normalize-consumed-frontmatter.js
# (still present as oracle — DEC-3-gated; not deleted by this repoint).
#
# Shebang note: the SHEBANG line above is `python3`, matching the
# cross-platform-invocation-parity target shape (DR-076) — never
# bareword-through-a-shell. docs/plans/2026-07-21-macos-first-class-
# invocation.md governs new Python entrypoints' invocation form.
#
# Exit-code contract — byte-parity with the node oracle (unlike
# refresh-queries.py's hardened 0/1/2/3 split, this trampoline does NOT
# reharden the exit codes; it forwards the engine's own byte-parity return
# value verbatim, per the engine module's own docstring "Exit codes
# (byte-parity with the node oracle...)"):
#   0 — run completed cleanly (no drift, or drift fixed/reported with zero
#       per-file processing errors).
#   1 — EITHER a CLI usage error (unrecognized flag) OR at least one
#       per-file processing error occurred during the scan (scanning
#       continues past a per-file error; exit 1 does not mean "nothing was
#       written" — check stdout for the per-file summary).
#   3 — TRANSPORT failure: engine-root resolution or
#       coordinator_core.ops.normalize_claimed_frontmatter import failed.
#
# Spec backlink: DoE-claude:pln-de-polyglot-the-coordinator-mi-119303
#     § Tasks B1 (chunk B1-E2)
# Port source: coordinator_core/ops/normalize_claimed_frontmatter.py
#     (claude-klabauter, renamed from normalize_consumed_frontmatter per
#     DR-084) — its own docstring: "mirrors the node CLI verbatim"

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root, require_dispatch_engine_on_path  # noqa: E402


def _import_runner():
    """Resolve the engine root and import the runner.

    DR-276: the op is run through `coordinator_core.cli_entry.run_op_main`
    rather than by calling its `main` directly, so the paths it declares become
    a session scope-touch claim. Without that, everything this CLI writes is an
    orphan at the `scoped_git_commit` sink.
    """
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main
    return run_op_main


def main() -> None:
    try:
        run_op_main = _import_runner()
    except RuntimeError as exc:
        print(
            f"normalize-consumed-frontmatter.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}",
            file=sys.stderr,
        )
        sys.exit(3)
    except ImportError as exc:
        print(
            "normalize-consumed-frontmatter.py: "
            f"coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(3)

    try:
        code = run_op_main("coordinator_core.ops.normalize_claimed_frontmatter", sys.argv[1:])
    except ImportError as exc:
        print(
            "normalize-consumed-frontmatter.py: "
            f"coordinator_core.ops.normalize_claimed_frontmatter not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(3)
    sys.exit(code)


if __name__ == "__main__":
    main()
