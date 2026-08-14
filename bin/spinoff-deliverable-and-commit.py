# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""spinoff-deliverable-and-commit.py — deliverable_id/origin-handoff-id carry cascade
and scope-scoped commit for the `/spinoff` authoring surface.

Purpose: DoE-claude's coordinator/skills/spinoff/SKILL.md inlines several multi-step
bash blocks (C3d deliverable_id auto-inheritance, C2 origin_handoff_id ID-companion
resolution, and Step 4's scope-path-extraction-then-commit) that had to share one
shell process (resolved variables do not survive across separate Bash tool calls).
This CLI collapses each concern into a single naked-Python subcommand.

Subcommands:
  resolve-deliverable        — D1 carry-not-remint: carry `deliverable_id` from a
                                parent artifact's frontmatter (roadmap stub / active
                                plan) when present, else mint fresh from `--slug`
                                (fail-loud if slug is also empty). Also carries
                                `initiative` (nullable FK) from the same parent.
  resolve-origin-handoff-id  — C2 ID-companion: read `handoff_id` off the SAME file
                                named by `--origin-handoff` (never a different
                                artifact) — the companion id for the `origin_handoff`
                                display-path edge.
  commit-scope                — Step 4: extract the `scope:` block's path list from a
                                handoff's YAML frontmatter, fail loud if the block is
                                missing/empty, then `git add`/`git commit` the scope
                                paths plus the handoff file itself (scoped commit,
                                never `git add -A`).

Composes two already-ported claude-klabauter ops in-process (no subprocess re-invocation of
their standalone CLI trampolines):
  coordinator_core.ops.read_frontmatter_field.read_frontmatter_field
  coordinator_core.ops.mint_deliverable_id.mint

Output convention (resolve-* subcommands): shell-assignment lines on stdout, meant to
be consumed via `eval "$(spinoff-deliverable-and-commit.py resolve-deliverable ...)"`
so resolved variables land directly in the caller's current shell — mirrors
handoff-deliverable-carry.py's convention (same "must share one shell process"
constraint the bash oracle called out for the handoff surface's analogous cascade).

Exit codes: 0 on success. A missing/unresolvable CLAUDE_KLABAUTER_ROOT (this trampoline's own
transport failure) exits 3 — distinct from any business-logic exit. A fail-loud
business-logic guard (empty slug on resolve-deliverable; missing/empty scope block on
commit-scope) exits 1, matching the bash oracle's own `exit 1` on the same guards.

Spec backlink: coordinator/skills/spinoff/SKILL.md § "Deliverable-spine threading
               (D1 carry-not-remint)" (C3d block), § "origin_handoff_id:" (C2 block),
               § "Step 4: Commit"
Port of: the three bash fences named above in DoE-claude
         coordinator/skills/spinoff/SKILL.md (bash bodies retired on cutover; the
         resolve-claude-klabauter-bin / _cc_trusted/_cc_root guard preambles surrounding those
         fences are NOT ported here — thin-invocation/guard-preamble concern, handled
         by the D2 SKILL.md repoint, not this engine-boundary CLI).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _no_console_passthrough_kw, _resolve_claude_klabauter_root  # noqa: E402

_TRANSPORT_FAIL = 3


def _import_ops():
    """Resolve CLAUDE_KLABAUTER_ROOT, put it on sys.path, and import the composed ops.

    Reuses cc_invoke's battle-tested CLAUDE_KLABAUTER_ROOT resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it — this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is deliberately
    NOT used here (same convention as archive-stamp-cli, read-frontmatter-field.py,
    mint-deliverable-id.py, handoff-deliverable-carry.py).
    """
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.ops.read_frontmatter_field import read_frontmatter_field
    from coordinator_core.ops.mint_deliverable_id import mint

    return read_frontmatter_field, mint


def resolve_deliverable_and_initiative(
    read_frontmatter_field,
    mint,
    parent_artifact: str | None,
    slug: str | None,
) -> tuple[str, str]:
    """Run the spinoff carry-or-mint cascade. Returns (deliverable_id, initiative_id).

    Mirrors SKILL.md's C3d block: a spinoff is a fork, so it discovers its
    deliverable_id from a single parent artifact (the roadmap stub or active plan it
    was forked from) rather than a plan/predecessor pair — that two-source cascade is
    handoff-deliverable-carry.py's concern, not this one. Only mints fresh (from
    `slug`) when the parent carries nothing; raises ValueError (fail-loud empty-slug
    guard) when neither a parent id nor a slug is available — the oracle's
    `[ -n "${slug:-}" ] || { echo ERROR...; exit 1; }` guard.
    """
    dlvr_id = ""
    if parent_artifact and os.path.isfile(parent_artifact):
        dlvr_id = read_frontmatter_field(parent_artifact, "deliverable_id")

    if dlvr_id:
        result, path_label = mint(deliverable_id=dlvr_id)
    else:
        if not slug:
            raise ValueError(
                "slug is empty — set slug from $ARGUMENTS before running this block"
            )
        result, path_label = mint(slug=slug)

    label_text = {
        "carry": f"carry path — using existing id: {result}",
        "mint-from-slug": f"mint-from-slug path — minted: {result}",
    }.get(path_label, f"{path_label} path — {result}")
    print(f"spinoff-deliverable-and-commit: {label_text}", file=sys.stderr)

    initiative_id = read_frontmatter_field(parent_artifact or "", "initiative")

    return result, initiative_id


def resolve_origin_handoff_id(read_frontmatter_field, origin_handoff: str | None) -> str:
    """C2 ID-companion resolve: `handoff_id` off the SAME file `origin_handoff` names.

    Emits empty string (never a different artifact's id) when `origin_handoff` is
    unset or does not exist on disk — mirrors the oracle's
    `[ -n "${ORIGIN_HANDOFF:-}" ] && [ -f "${ORIGIN_HANDOFF}" ]` guard.
    """
    if origin_handoff and os.path.isfile(origin_handoff):
        return read_frontmatter_field(origin_handoff, "handoff_id")
    return ""


def extract_scope_paths(handoff_text: str) -> list[str]:
    """Extract the `scope:` block's `  - <path>` entries from handoff frontmatter.

    Faithful Python port of the oracle's awk one-liner:
        awk '/^scope:/{found=1; next}
             found && /^  - /{print substr($0, 5)}
             found && /^[a-z]/{exit}'

    Rule order matters and is preserved: a `scope:` line sets `found` and is
    otherwise skipped (awk's `next`); once `found`, a 2-space-indented `- ` line
    contributes its path (substr($0,5) == strip the 4-char "  - " prefix); once
    `found`, any subsequent line starting with a lowercase ASCII letter (the next
    top-level frontmatter key) ends the block (awk's `exit` — later lines are never
    scanned, matching the oracle's early-termination, not merely "skipped").
    """
    found = False
    paths: list[str] = []
    for line in handoff_text.splitlines():
        if line.startswith("scope:"):
            found = True
            continue
        if found and line.startswith("  - "):
            paths.append(line[4:])
            continue
        if found and line[:1].islower():
            break
    return paths


def _cmd_resolve_deliverable(args: argparse.Namespace, read_frontmatter_field, mint) -> int:
    try:
        dlvr_id, initiative_id = resolve_deliverable_and_initiative(
            read_frontmatter_field, mint, args.parent_artifact, args.slug
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"DLVR_ID={dlvr_id}")
    print(f"INITIATIVE_ID={initiative_id}")
    return 0


def _cmd_resolve_origin_handoff_id(args: argparse.Namespace, read_frontmatter_field, _mint) -> int:
    origin_handoff_id = resolve_origin_handoff_id(read_frontmatter_field, args.origin_handoff)
    print(f"ORIGIN_HANDOFF_ID={origin_handoff_id}")
    return 0


def _cmd_commit_scope(args: argparse.Namespace, _read_frontmatter_field, _mint) -> int:
    handoff = args.handoff
    # Read the handoff relative to --cwd when both are given and the handoff path is
    # relative — mirrors the bash oracle, where the whole block runs in one shell
    # process sharing a single cwd (the repo root) for both the `awk` read and the
    # `git add`/`git commit` below.
    read_path = (
        os.path.join(args.cwd, handoff) if args.cwd and not os.path.isabs(handoff) else handoff
    )
    try:
        with open(read_path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError as exc:
        print(f"FAIL: cannot read handoff '{read_path}': {exc}", file=sys.stderr)
        return 1

    scope = extract_scope_paths(text)
    if not scope:
        print(
            "FAIL: handoff frontmatter scope: block missing or empty — cannot enumerate paths",
            file=sys.stderr,
        )
        return 1

    paths = scope + [handoff]
    message = f"chore(spinoff): {args.slug} [authored mid-session]"

    if args.dry_run:
        print("git add -- " + " ".join(paths))
        print(f"git commit -m {message!r} -- " + " ".join(paths))
        return 0

    add_proc = subprocess.run(
        ["git", "add", "--"] + paths,
        cwd=args.cwd,
        **_no_console_passthrough_kw(_resolve_claude_klabauter_root()),
    )
    if add_proc.returncode != 0:
        return add_proc.returncode

    commit_proc = subprocess.run(
        ["git", "commit", "-m", message, "--"] + paths,
        cwd=args.cwd,
        **_no_console_passthrough_kw(_resolve_claude_klabauter_root()),
    )
    return commit_proc.returncode


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="spinoff-deliverable-and-commit.py",
        description="deliverable_id/origin-handoff-id carry cascade + scope-scoped commit for /spinoff",
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    resolve_parser = subparsers.add_parser(
        "resolve-deliverable",
        help="carry deliverable_id/initiative from a parent artifact, else mint from --slug",
    )
    resolve_parser.add_argument(
        "--parent-artifact",
        default="",
        help="path to the roadmap stub or active plan this spinoff forks from (optional)",
    )
    resolve_parser.add_argument(
        "--slug", default="", help="the spinoff slug, used to mint fresh when no parent id is discoverable"
    )

    origin_parser = subparsers.add_parser(
        "resolve-origin-handoff-id",
        help="resolve origin_handoff_id (handoff_id off the origin_handoff file)",
    )
    origin_parser.add_argument(
        "--origin-handoff",
        default="",
        help="path to the active pickup baton this session was opened with (optional)",
    )

    commit_parser = subparsers.add_parser(
        "commit-scope",
        help="extract handoff frontmatter scope: paths and scoped-commit them plus the handoff itself",
    )
    commit_parser.add_argument("--handoff", required=True, help="path to the just-written spinoff handoff")
    commit_parser.add_argument("--slug", required=True, help="the spinoff slug, used in the commit subject")
    commit_parser.add_argument(
        "--cwd", default=None, help="repo root to run git in (default: current working directory)"
    )
    commit_parser.add_argument(
        "--dry-run", action="store_true", help="print the git commands instead of running them"
    )

    args = parser.parse_args(argv)

    try:
        read_frontmatter_field, mint = _import_ops()
    except RuntimeError as exc:
        print(f"spinoff-deliverable-and-commit.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL
    except ImportError as exc:
        print(f"spinoff-deliverable-and-commit.py: coordinator_core ops not importable: {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL

    if args.subcommand == "resolve-deliverable":
        return _cmd_resolve_deliverable(args, read_frontmatter_field, mint)
    if args.subcommand == "resolve-origin-handoff-id":
        return _cmd_resolve_origin_handoff_id(args, read_frontmatter_field, mint)
    if args.subcommand == "commit-scope":
        return _cmd_commit_scope(args, read_frontmatter_field, mint)

    parser.print_usage(sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
