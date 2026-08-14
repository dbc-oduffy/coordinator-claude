# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""verify-parallel-review-lens-orthogonality.py — CLI trampoline over claude-klabauter coordinator_core.ops.verify_parallel_review_lens_orthogonality.

Asserts the parallel-code-review gate's two structural properties: (1)
static — the orthogonal lens domains in the skill's lens-domain manifest
have agent files on disk and share no lens_domain value; (2) runtime
(--chunk-manifest) — the N code-semantics chunk partitions are disjoint by
file-scope. Wired into /update-docs Phase 11 (no-arg form) and
parallel-code-review pre-dispatch (--chunk-manifest form). Read-only —
does not modify files, dispatch agents, or commit.
"""
# verify-parallel-review-lens-orthogonality.py — CLI trampoline over claude-klabauter
# coordinator_core.ops.verify_parallel_review_lens_orthogonality.
#
# Shebang note: the SHEBANG line above is `#!/usr/bin/env python3`, generator-
# owned by `gen-launcher-shim.py --ensure-unix`, and correct for this shape. On
# Windows, this file's co-located `.cmd` twin wins via `PATHEXT` when invoked
# as a bareword, so the shebang is never read there; on macOS/Linux `python3`
# is the right interpreter. Caution: callers must invoke via the extensionless
# name or a resolved-interpreter prefix, never a bareword `.py` through git-
# bash — git-bash DOES honor the shebang and would exec-127 with no `python3`
# present. See the carve-out in DoE-claude's coordinator/docs/wiki/bash-on-
# windows-gotchas.md § Carve-out (cross-repo — this wiki lives in the
# DoE-claude repo, not here).
#
# Asserts the parallel-code-review gate's two structural properties:
#   (1) STATIC (no args): the orthogonal lens domains in the skill's
#       lens-domain manifest (3 specialist workers + code-semantics-as-a-class)
#       (a) have agent files on disk and (b) do not share any lens_domain
#       value.
#   (2) RUNTIME (--chunk-manifest <tsv>): the N code-semantics chunk
#       partitions are disjoint by file-scope — no file appears in two
#       chunks. Runs the static check first, then the chunk-disjointness
#       check.
#
# Usage:
#   verify-parallel-review-lens-orthogonality.py
#   verify-parallel-review-lens-orthogonality.py --chunk-manifest <tsv-path>
#
# Chunk-manifest format (TSV, one file per line): "chunk-<k>\t<relpath>".
#
# Exit codes (parity-critical — both callers branch on these):
#   0 — all checks passed.
#   1 — one or more checks failed (diagnostic printed to stdout), OR the
#       skill file / chunk manifest was not found, OR the DoE-claude repo
#       root could not be resolved cross-repo, OR a CLI usage error (unknown
#       arg, missing --chunk-manifest value; these print to stderr).
#   2 — claude-klabauter-link failure: CLAUDE_KLABAUTER_ROOT resolution failed, or
#       coordinator_core.ops.verify_parallel_review_lens_orthogonality was
#       not importable. Dedicated code — distinct from both business codes
#       (0/1) above, per the fail-loud-gate transport-failure convention
#       (this script gates /update-docs Phase 11 and the parallel-code-review
#       pre-dispatch step; a silent degrade-to-0 on outage would let a real
#       drift/collision slip through undetected).
#
# Wire-in note: the no-arg form is wired into /update-docs Phase 11
# (verify-sync phase); the --chunk-manifest form is called by
# skills/parallel-code-review/SKILL.md at pre-dispatch time.
#
# Negative-spec: does NOT modify any files, does NOT dispatch agents, does
# NOT commit. Read-only assertion only.
#
# Spec backlink: docs/plans/2026-05-06-parallel-code-review-weekly-gate.md Phase 3.5
# Spec backlink: docs/plans/2026-05-23-weekly-gate-restructure-and-arch-survey-audit-rename.md § Strand 1c
# Port of: coordinator/bin/verify-parallel-review-lens-orthogonality.py (bash oracle retired on cutover; see git log)
# Port backlink: docs/plans/2026-07-15-bash-to-naked-python-engine-migration.md

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402

_PROG = "verify-parallel-review-lens-orthogonality.py"
_EXIT_TRANSPORT_FAILURE = 2  # dedicated — never collides with the op's business codes (0/1)


def _import_main():
    """Resolve CLAUDE_KLABAUTER_ROOT, put it on sys.path, and import the ported CLI entry.

    Reuses cc_invoke's battle-tested CLAUDE_KLABAUTER_ROOT resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it — this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.
    """
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.ops.verify_parallel_review_lens_orthogonality import main as _op_main

    return _op_main


def main() -> None:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"{_PROG}: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(_EXIT_TRANSPORT_FAILURE)
    except ImportError as exc:
        print(
            f"{_PROG}: coordinator_core.ops.verify_parallel_review_lens_orthogonality not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(_EXIT_TRANSPORT_FAILURE)

    sys.exit(op_main(sys.argv[1:]))


if __name__ == "__main__":
    main()
