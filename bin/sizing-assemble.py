# sizing-assemble — CLI trampoline over claude-klabauter
# coordinator_core.sizing_assemble (the computed-skill assembler for
# `/sizing`'s route table). Direct-import variant (template-variant #1,
# mirrors coordinator/bin/pickup-assemble): a plain in-process function
# call after resolving the engine root, no cc_invoke/IPC hop.
#
# Contract: coordinator-content-repo coordinator/docs/wiki/computed-skills.md, DR-090
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
#   3 — transport failure (the engine root unresolvable, coordinator_core
#       import failure, or an unexpected exception inside route()).

from __future__ import annotations

import sys


def _flag(argv: list[str], name: str):
    """Value of `name VALUE` or `name=VALUE` in argv, else None; the engine's argparse accepts both
    spellings, so the floor gate must too or `--tshirt=XS` walks past it."""
    for i, tok in enumerate(argv):
        if tok == name:
            return argv[i + 1] if i + 1 < len(argv) else None
        if tok.startswith(name + "="):
            return tok[len(name) + 1:]
    return None


def _floor_gate(argv: list[str]):
    """`--floor` prints the SizingFingerprint for --intent; a --tshirt below it exits 2.

    Returns None when the call is not floor-governed (no --intent) and falls through to the engine.
    """
    intent = _flag(argv, "--intent")
    if intent is None or "--help" in argv or "-h" in argv:
        return None
    import json

    from entry_point_shim import _cc_invoke_resolve_claude_klabauter_root

    # Engine root first: `coordinator_core.ops` caches an import failure for the life of the process.
    try:
        root = _cc_invoke_resolve_claude_klabauter_root()()
    except RuntimeError:
        return None
    if root not in sys.path:
        sys.path.insert(0, root)
    from coordinator_core.ops.sizing_floor import below_floor, floor

    fp = floor(intent)
    if "--floor" in argv:
        print(json.dumps({"parts_count": fp.parts_count, "tshirt_floor": fp.tshirt_floor, "rows": list(fp.rows)}))
        return 0
    tshirt = _flag(argv, "--tshirt")
    if tshirt is not None and below_floor(tshirt, fp):
        print(
            f"sizing-assemble: --tshirt {tshirt} is below the floor {fp.tshirt_floor} "
            f"for {fp.parts_count} counted parts: {', '.join(fp.rows)}",
            file=sys.stderr,
        )
        return 2
    return None


def main(argv: list[str]) -> int:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from entry_point_shim import run_target  # noqa: E402

    refusal = _floor_gate(argv)
    if refusal is not None:
        return refusal
    return run_target("sizing-assemble", argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
