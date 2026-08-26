"""
coordinator-fold-execution-record — CLI trampoline over claude-klabauter
coordinator_core.ops.fold_execution_record.

Composes the execution-record fold from a plan + run-report sidecars: given a
plan file, reads all state/subagent-share/*/<plan-slug>.<chunk-id>.md run-report
sidecars (the universal subsume of the retired flight-recorder — see
docs/plans/2026-07-13-subagent-run-report-subsume.md C6) and emits two markdown
blocks to stdout:
  Part A — "## Execution Observations": one entry per sidecar, keyed by
           chunk-id resolved to the AC/segment it targets (from the plan's
           ## Chunks section).
  Part B — "## Completion Entry Prose": a suggested past-tense TITLE + <=8
           sentence BODY synthesised from the observations + an optional
           --desc one-liner.

The prose synthesis (Part B) is a judgment step. The ported module gathers and
structures the raw material mechanically and emits it in a clearly-labelled
block. If sidecars are present but no chunk-to-AC mapping is resolvable, the
block is emitted with the raw chunk-id so a downstream Sonnet compose step can
fill in the AC annotation.

Finish-strangler port: the bash implementation (374 lines — argument parsing,
plan-slug derivation, chunk-to-AC map extraction, sidecar frontmatter/body
parsing, SKIP-sentinel emission) has been fully ported to
coordinator_core/ops/fold_execution_record.py (claude-klabauter), with independent
coverage in the co-located pytest
(coordinator_core/ops/test_fold_execution_record.py). This file is now a thin
DoE-side trampoline over that claude-klabauter (engine) module, per DR-047 (DoE owns
contract/generator, claude-klabauter owns engine) and the bash-kill campaign
(coordinator.local.md).

plan_slug derivation contract (CRITICAL SEMANTIC COUPLING): the ported module
and coordinator/bin/fan-out-dispatch.py derive plan_slug via the IDENTICAL
Python idiom — strip a leading "YYYY-MM-DD-" date prefix from the plan's
basename, then strip a trailing ".md" suffix. This equivalence is asserted by
DoE's coordinator/tests/run-report-provision-key-flattening.bats (parity
test), which greps both scripts for their respective idiom fragments — same
input MUST yield a byte-identical slug on both sides, or provisioning (write
side) and folding (read side) silently mislocate each other's sidecars.

Unlike emit-artifact-shape-contract (which hands the ported module a DoE-side
coordinator-root env var because it reads coordinator/schemas/), this op reads
and writes purely repo-relative state (the plan file's own repo, resolved via
`git rev-parse --show-toplevel` from the plan's own directory, inside the
ported module) — no DoE-side path needs to be handed across the trampoline
boundary.

Usage:
  coordinator-fold-execution-record --plan <path> [--desc <one-liner>]

Exit codes (parity-critical — matches
coordinator_core.ops.fold_execution_record.main exactly; see that module's
docstring for the full contract):
  0 — normal exit (output emitted, or no sidecars found -> SKIP signal on
      stdout).
  1 — argument / validation error.
  2 — DEDICATED transport/config-failure code, distinct from the business
      code above: engine-root resolution failed, or
      coordinator_core.ops.fold_execution_record not importable.

SKIP sentinel — callers MUST check stdout for a line matching:
  <!-- coordinator-fold-execution-record: SKIP
before appending stdout to a plan file. Scripted pipelines that blindly
redirect stdout (>> "$plan") will silently write the SKIP comment into the
shell-doc-ok: that redirect is the real shell hazard this warns a caller away from.
plan body. Hard-error SKIPs (plan-not-found, invalid-slug, repo-root-fail)
also write a diagnostic to stderr. Soft SKIPs (no subagent-share dir, no
sidecars, trivial observations) write only to stdout; exit is always 0 for
all SKIPs.

NEVER commits or stages files. NEVER edits the plan or any sidecar.

Spec backlink: docs/plans/2026-07-13-subagent-run-report-subsume.md § C6, C10, DEC-6
Prior bash implementation: see git log (coordinator/bin/coordinator-fold-execution-record,
                            374 lines, retired on this cutover)
"""

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
    deliberately NOT used here (variant-#1 direct-import trampoline — see
    tasks/2026-07-16-clean-slate-recon/r1-doe-port-template.md § 1).
    """
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.ops.fold_execution_record import main as _op_main

    return _op_main


def main() -> None:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"coordinator-fold-execution-record: engine-root resolution failed: {exc}", file=sys.stderr)
        sys.exit(2)
    except ImportError as exc:
        print(
            f"coordinator-fold-execution-record: coordinator_core.ops.fold_execution_record not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(op_main(sys.argv[1:]))


if __name__ == "__main__":
    main()
