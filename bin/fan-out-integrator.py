# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""fan-out-integrator.py — DoE-side contract trampoline over the claude-klabauter
fan-out integrator compiler.

Collapses the parallel-review-integrator dispatch ceremony into one call:
given a slice-spec TSV (slice-id, reviewer-sidecar path, comma-separated file
paths), validates each cited reviewer sidecar exists on disk, runs the
file-overlap pass, and emits N paste-ready coordinator:review-integrator
dispatch prompts, one per slice. DoE owns the contract; claude-klabauter
(coordinator_core.ops.fan_out_integrator) owns the engine (DR-047).
"""
# bin/fan-out-integrator.py — Fan-out integrator compiler: overlap pass + scoped
# review-integrator prompts. Now a thin DoE-side (contract) trampoline over
# claude-klabauter coordinator_core.ops.fan_out_integrator (DR-047: DoE owns contract,
# claude-klabauter owns engine).
#
# Purpose: Collapse the parallel-integrator dispatch ceremony into one EM-side call so
# fanning out integrators is the path of least resistance. Given a slice-spec (TSV),
# validates each cited reviewer sidecar exists on disk, runs the file-overlap pass, then
# emits N paste-ready coordinator:review-integrator dispatch prompts — one per slice.
#
# Spec backlink: docs/plans/2026-06-09-partitioned-review-integrator-fan-out.md §Chunk 1
# Port spec: docs/plans/2026-07-16-bash-clean-slate-residual-migration.md
#
# Input format (TSV on stdin or --spec <file>), one row per slice:
#   <slice-id>TAB<reviewer-sidecar-path>TAB<comma-separated-file-paths>
#
# Usage:
#   printf 'slice-A\tstate/review-trail/findings/slice-A.md\tauth.py,auth_test.py\n' | python bin/fan-out-integrator.py
#   python bin/fan-out-integrator.py --spec slices.tsv
#
# Reviewer sidecar path (column 2): the path each reviewer RETURNED after self-persisting its
# findings — lives under state/review-trail/findings/ (the sole sanctioned dir). Code-reviewer
# always scaffolds its own sidecar there via coordinator-doc-new and returns the path in its
# DONE line. Do NOT pass docs/plans/*.review.md or any EM-authored path here; the reviewer
# owns its sidecar, not the EM.
# Spec backlink (self-persist design): cross-repo/inbox/2026-07-01-reviewer-selfpersist-confinement-redirect.md
#
# Exit codes:
#   0 — success, N blocks emitted to stdout
#   1 — content validation error (missing sidecar, file overlap, malformed row) — matches
#       claude-klabauter op's own contract byte-for-byte, see coordinator_core/ops/fan_out_integrator.py
#   2 — invocation error (usage, environment, missing spec file, DoE-side snippet resolution)
#   3 — claude-klabauter-link failure: CLAUDE_KLABAUTER_ROOT resolution or coordinator_core.ops.fan_out_integrator
#       import failed. NEW failure mode vs. the original bash script (which had no cross-repo
#       dependency) — a DEDICATED code, distinct from BOTH business codes above, so a caller
#       cannot misclassify "claude-klabauter engine unreachable" (fix your CLAUDE_KLABAUTER_ROOT / install) as
#       either a content problem (1, fix your spec) or a usage problem (2, fix your invocation).
#       Per docs/wiki addendum § 3b (fail-loud gate/validator posture — this script's rc encodes
#       a real business pass/fail the EM ceremony branches on, so transport failure may not
#       silently degrade to 0 the way a best-effort/never-block script would).
#
# Environment: none required beyond a resolvable CLAUDE_KLABAUTER_ROOT (see cc_invoke). Snippet paths
# resolve via coordinator_data_root.data_root("snippets") (co-located rung 1, DoE-resident
# rung 2 — see that module's docstring), NOT a bare __file__-relative walk: this script now
# lives in claude-klabauter while snippets/ stayed in DoE-claude (DR-047 split), so a naive
# `dirname(dirname(__file__))` walk lands inside claude-klabauter where snippets/ no longer
# exists. CLAUDE_PLUGIN_ROOT is set from that resolved root before the claude-klabauter op is imported
# (unless the caller already set CLAUDE_PLUGIN_ROOT, which wins unconditionally), so its own
# PLUGIN_ROOT resolution rung 1 always wins here.

from __future__ import annotations

import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(_SCRIPT_DIR, "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402
from coordinator_data_root import data_root  # noqa: E402

_PLUGIN_ROOT = os.environ.get("CLAUDE_PLUGIN_ROOT") or str(data_root("snippets").parent)


# DR-276: routed through `coordinator_core.cli_entry.run_op_main` rather than a
# plain in-process `import ... as _op_main` + `sys.exit(op_main(argv))` tail,
# so any paths the op declares via `declare_write` become a session
# scope-touch claim (this op only ever emits dispatch prompts to stdout — see
# module docstring's Exit codes/Usage — so it declares none; routing it is a
# baseline-shrink, not a behavior change).


def _import_run_op_main():
    """Resolve CLAUDE_KLABAUTER_ROOT, put it on sys.path, and import `run_op_main`.

    Also sets CLAUDE_PLUGIN_ROOT to this trampoline's own resolved plugin root —
    `data_root("snippets").parent` (co-located or DoE-resident per the split-repo
    layout; see coordinator_data_root.py), or the caller's pre-existing
    CLAUDE_PLUGIN_ROOT env value if one was already set (never clobbered) — so
    the claude-klabauter op's own PLUGIN_ROOT resolver
    (coordinator_core.ops.fan_out_integrator._resolve_plugin_root) hits its
    rung-1 short-circuit and never needs its own fallback ladder in the normal
    call shape.
    """
    os.environ.setdefault("CLAUDE_PLUGIN_ROOT", _PLUGIN_ROOT)
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.cli_entry import run_op_main
    return run_op_main


def main() -> None:
    try:
        run_op_main = _import_run_op_main()
    except RuntimeError as exc:
        print(f"fan-out-integrator.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(3)
    except ImportError as exc:
        print(
            f"fan-out-integrator.py: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(3)

    try:
        code = run_op_main("coordinator_core.ops.fan_out_integrator", sys.argv[1:])
    except ImportError as exc:
        print(
            f"fan-out-integrator.py: coordinator_core.ops.fan_out_integrator not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(3)
    sys.exit(code)


if __name__ == "__main__":
    main()
