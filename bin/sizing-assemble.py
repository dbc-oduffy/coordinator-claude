# sizing-assemble — CLI trampoline over claude-klabauter
# coordinator_core.sizing_assemble (the computed-skill assembler for
# `/sizing`'s route table). Direct-import variant (template-variant #1,
# mirrors coordinator/bin/pickup-assemble): a plain in-process function
# call after resolving CLAUDE_KLABAUTER_ROOT, no cc_invoke/IPC hop.
#
# Contract: DoE-claude coordinator/docs/wiki/computed-skills.md, DR-090
# Spec backlink: docs/plans/2026-07-24-sizing-lobby-core.md, chunk C7
# Registration seam: a new engine capability registers by shipping a thin
# bin/ trampoline over an in-process coordinator_core module — same shape as
# every other direct-import CLI in this tree (pickup-assemble,
# archive-stamp-cli, session-claim-cli).
#
# Subcommand: none — this trampoline forwards straight to
# coordinator_core.sizing_assemble.main(argv). See that module's `main()`
# for the flag surface (--appetite, --tshirt, --express-lane,
# --probe-signal, --jtbd-unclear, --well-trodden-step-change,
# --premise-provenance, --boundary-in-notch, --scout-evidence-kind,
# --scout-evidence).
#
# READ-ONLY — mutates nothing. sizing_assemble.route() never writes a
# sizing-object; it returns the route/detents/fork fields for the caller to
# persist.
#
# Exit codes (locally scoped to this CLI, NOT inherited):
#   0 — OK, a decision object was computed and printed.
#   1 — reserved for a future business-failure class (unused today —
#       route() has no business-failure path, only usage errors).
#   2 — usage error (missing/malformed --appetite or --tshirt).
#   3 — transport failure (CLAUDE_KLABAUTER_ROOT unresolvable, coordinator_core
#       import failure, or an unexpected exception inside route()).
from __future__ import annotations
"""sizing-assemble — see the # comment block above for the RAG-bait purpose
text (the polyglot shebang line above makes THIS triple-quoted string a
silently-discarded expression statement, not the module __doc__ — same
convention as pickup-assemble)."""

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402

_TRANSPORT_FAIL = 3


def _import_module():
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    import coordinator_core.sizing_assemble as _mod

    return _mod


def main(argv: list[str]) -> int:
    try:
        mod = _import_module()
    except RuntimeError as exc:
        print(f"sizing-assemble: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL
    except ImportError as exc:
        print(f"sizing-assemble: coordinator_core.sizing_assemble not importable: {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL

    return mod.main(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
