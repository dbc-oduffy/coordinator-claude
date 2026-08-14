# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""handoff-deliverable-carry.py — deliverable_id/initiative-FK carry-or-mint cascade
for the handoff authoring surface (D1 carry-not-remint rule).

Purpose: DoE-claude's coordinator/skills/handoff/SKILL.md used to inline this cascade
as a multi-step bash block spanning several `$(python ... )` command substitutions
that had to share one shell process (the resolved variables did not survive across
separate Bash tool calls). This CLI collapses that cascade into a single naked-Python
invocation whose output is meant to be `eval`'d by the calling shell in one step,
removing the same-shell-process fragility entirely.

Cascade (mirrors the bash oracle verbatim):
  deliverable_id — 1. active plan's frontmatter `deliverable_id`
                   2. predecessor handoff's frontmatter `deliverable_id`
                   3. carry (mint(deliverable_id=...)) if either hit, else
                      mint-from-slug (mint(slug="<YYYYMMDD>-handoff"))
  initiative     — 1. active plan's frontmatter `initiative`
                   2. predecessor handoff's frontmatter `initiative` (fallback only;
                      continuation handoffs inherit the predecessor's initiative FK
                      when the plan doesn't carry one)

Composes two already-ported claude-klabauter ops in-process (no subprocess re-invocation of
their standalone CLI trampolines):
  coordinator_core.ops.read_frontmatter_field.read_frontmatter_field
  coordinator_core.ops.mint_deliverable_id.mint

The cascade itself (`resolve_deliverable_and_initiative` / `DroppedDeliverableJoinError`)
lives in `coordinator_core.ops.deliverable_carry` — this script is a thin CLI
trampoline over that engine-importable implementation, not a second copy of it.

Out of scope for this port (a separate concern — C2 lifecycle-vocab predecessor_id
ID-companion resolution): resolving `predecessor_id` off the predecessor handoff's own
`handoff_id` field. That logic stays inline in SKILL.md pending its own port.

Usage:
  handoff-deliverable-carry.py resolve [--plan-file <path>] [--predecessor <path>]
                                        [--slug-suffix <suffix>]
                                        [--additional-predecessor <path> ...]

`--additional-predecessor` (repeatable, sedge-01 / succession-edge-cardinality roadmap):
names an extra fan-in predecessor leg beyond `--predecessor`, compared for
deliverable_id divergence alongside the plan/predecessor rungs — additive only, never
becomes the carried id itself. Omitting it reproduces today's 2-rung behaviour
byte-for-byte; no in-repo or DoE-claude caller passes it yet.

Caller-must-resolve obligation (Review: coordinator:code-reviewer af8ffeae, P2 finding 2
— documented, not fixed here; resolving raw argv paths in this CLI is out of the sedge-01
stub's scope): `resolve_deliverable_and_initiative`'s `additional_predecessors` contract
expects each entry already-RESOLVED (archive-aware, qualified) by the caller — this CLI
does NOT perform that resolution; it passes the raw argv string straight through. A
relative or archived path handed to `--additional-predecessor` will therefore fail
`os.path.isfile()` and degrade silently to an absent rung (same as an unset
`--predecessor`) rather than raising or resolving. Callers must pass an already-qualified,
directly-`isfile()`-able path.

Output (stdout): two shell-assignment lines, meant to be consumed via
`eval "$(handoff-deliverable-carry.py resolve ...)"` so both variables land directly
in the caller's current shell (matching the "must share one shell process" constraint
the bash oracle called out explicitly):
  DLVR_ID=<value>
  INITIATIVE_ID=<value>
Values are the plain deliverable_id / initiative strings — per the deliverable-spine
schema these never contain shell metacharacters, so no quoting is applied (matching the
oracle's own unquoted `$(...)` capture).

The carry/mint-from-slug path (mirrors mint_deliverable_id.mint's own "carry" /
"mint-from-stub" / "mint-from-slug" path_label vocabulary) is logged to stderr, exactly
as the bash oracle's inline comment documented ("logs 'carry path' / 'mint-from-slug
path' to stderr").

Exit codes: 0 on success. A missing/unresolvable CLAUDE_KLABAUTER_ROOT (this trampoline's own
transport failure) exits 3 — distinct from any business-logic exit, so a broken engine
link surfaces immediately rather than silently degrading to an empty/wrong carry.
Exit 4 is a dropped join: an active plan was named but yields no `deliverable_id` (read
failed or genuinely absent) and the predecessor fallback also yields nothing — this is
NOT the benign "no plan / no predecessor" mint-from-slug case, so it fails loud instead
of silently minting a fresh id that severs the deliverable-spine thread. Exit 5 is a
divergent join: the plan AND the predecessor handoff both name a non-empty
`deliverable_id` and the two values disagree (see `DivergentDeliverableIdError` in
`coordinator_core.ops.deliverable_carry` for the full reasoning and the DR-207 DD#1
earliest-artifact tiebreak this trampoline does not attempt to apply). Exit 3, exit 4,
and exit 5 are all consumed only by generic nonzero-halts callers (no in-repo or
reachable DoE-claude caller gates on a specific exit-code allowlist), so adding exit 5
is safe.

Spec backlink: coordinator/skills/handoff/SKILL.md § Deliverable-spine threading
               (D1 carry-not-remint) — DoE-claude, C3d
Port of: the `# C3d — deliverable_id auto-inheritance (D1 carry-not-remint rule)` bash
         block in DoE-claude coordinator/skills/handoff/SKILL.md (deliverable_id +
         initiative resolution only; predecessor_id carried separately, out of scope
         here — see module docstring above)
"""

from __future__ import annotations

import argparse
import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402

_TRANSPORT_FAIL = 3
_DROPPED_JOIN_FAIL = 4
_DIVERGENT_JOIN_FAIL = 5

# Pre-resolve CLAUDE_KLABAUTER_ROOT and import the cascade eagerly (same
# _resolve_claude_klabauter_root() ladder _import_ops() below reuses for the remaining
# ops) so `resolve_deliverable_and_initiative` / `DroppedDeliverableJoinError`
# are real, directly callable module attributes for in-process callers —
# matching how the cascade's own home module exposes them. Any resolution
# failure is stashed rather than raised here, so the CLI's tidy transport-
# failure reporting in main() (exit 3, no traceback) is unchanged.
_IMPORT_ERROR: Exception | None = None
try:
    _claude_klabauter_root = _resolve_claude_klabauter_root()
    if _claude_klabauter_root not in sys.path:
        sys.path.insert(0, _claude_klabauter_root)
    from coordinator_core.ops.deliverable_carry import (
        DivergentDeliverableIdError,
        DroppedDeliverableJoinError,
        resolve_deliverable_and_initiative,
    )
except (RuntimeError, ImportError) as _exc:
    _IMPORT_ERROR = _exc
    DivergentDeliverableIdError = RuntimeError
    DroppedDeliverableJoinError = RuntimeError
    resolve_deliverable_and_initiative = None


def _import_ops():
    """Resolve CLAUDE_KLABAUTER_ROOT, put it on sys.path, and import the two composed ops.

    Reuses cc_invoke's battle-tested CLAUDE_KLABAUTER_ROOT resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it — this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is deliberately
    NOT used here (same convention as archive-stamp-cli, read-frontmatter-field.py,
    mint-deliverable-id.py).
    """
    if _IMPORT_ERROR is not None:
        raise _IMPORT_ERROR
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.ops.read_frontmatter_field import read_frontmatter_field
    from coordinator_core.ops.mint_deliverable_id import mint

    return read_frontmatter_field, mint


def _cmd_resolve(args: argparse.Namespace, read_frontmatter_field, mint) -> int:
    dlvr_id, initiative_id = resolve_deliverable_and_initiative(
        read_frontmatter_field,
        mint,
        args.plan_file,
        args.predecessor,
        args.slug_suffix,
        additional_predecessors=args.additional_predecessor or None,
    )
    print(f"DLVR_ID={dlvr_id}")
    print(f"INITIATIVE_ID={initiative_id}")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="handoff-deliverable-carry.py",
        description="deliverable_id/initiative-FK carry-or-mint cascade for the handoff authoring surface",
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    resolve_parser = subparsers.add_parser(
        "resolve",
        help="resolve DLVR_ID and INITIATIVE_ID via the plan -> predecessor -> mint cascade",
    )
    resolve_parser.add_argument("--plan-file", default="", help="path to the plan this handoff checkpoints")
    resolve_parser.add_argument("--predecessor", default="", help="path to the predecessor handoff")
    resolve_parser.add_argument(
        "--slug-suffix",
        default="handoff",
        help="suffix appended to today's date when minting a fresh id (default: 'handoff', "
        "matching the bash oracle's '<YYYYMMDD>-handoff' slug)",
    )
    resolve_parser.add_argument(
        "--additional-predecessor",
        action="append",
        default=[],
        help="path to an additional (fan-in) predecessor handoff, beyond --predecessor; "
        "repeatable. Compared for deliverable_id divergence alongside --plan-file/"
        "--predecessor (sedge-01, succession-edge-cardinality roadmap) but never becomes "
        "the carried id itself — additive only, no in-repo caller passes this today. "
        "Must be supplied already-qualified (archive-aware-resolved) by the caller; this "
        "CLI does no resolution of its own, so a relative or archived path degrades "
        "silently to an absent rung instead of raising.",
    )

    args = parser.parse_args(argv)

    try:
        read_frontmatter_field, mint = _import_ops()
    except RuntimeError as exc:
        print(f"handoff-deliverable-carry.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL
    except ImportError as exc:
        print(f"handoff-deliverable-carry.py: coordinator_core ops not importable: {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL

    if args.subcommand == "resolve":
        try:
            return _cmd_resolve(args, read_frontmatter_field, mint)
        except DivergentDeliverableIdError as exc:
            print(f"handoff-deliverable-carry.py: divergent deliverable_id join: {exc}", file=sys.stderr)
            return _DIVERGENT_JOIN_FAIL
        except DroppedDeliverableJoinError as exc:
            print(f"handoff-deliverable-carry.py: dropped deliverable_id join: {exc}", file=sys.stderr)
            return _DROPPED_JOIN_FAIL

    parser.print_usage(sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
