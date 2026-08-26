# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""spinoff-deliverable-and-commit.py — origin-handoff-id carry and scope-scoped commit
for the `/spinoff` authoring surface.

Purpose: DoE-claude's coordinator/skills/spinoff/SKILL.md inlines several multi-step
bash blocks (C2 origin_handoff_id ID-companion resolution and Step 4's
scope-path-extraction-then-commit) that had to share one shell process (resolved
variables do not survive across separate Bash tool calls). This CLI collapses each
concern into a single naked-Python subcommand.

Subcommands:
  resolve-origin-handoff-id  — C2 ID-companion: read `handoff_id` off the SAME file
                                named by `--origin-handoff` (never a different
                                artifact) — the companion id for the `origin_handoff`
                                display-path edge.
  commit-scope                — Step 4: extract the `scope:` block's path list from a
                                handoff's YAML frontmatter, fail loud if the block is
                                missing/empty, then `git add`/`git commit` the scope
                                paths plus the handoff file itself (scoped commit,
                                never `git add -A`).

Note: this CLI does NOT carry `deliverable_id` — that cascade lives solely in
coordinator_core.ops.deliverable_carry.resolve_deliverable_and_initiative
(the `/spinoff` authoring surface routes through the assembler, which calls the
canonical cascade directly; see the 2026-08-05 PM ruling on the authoring door).
This file previously forked a second, unconditional-carry copy of that function —
removed as dead code contradicting the ruling and deliverable_carry.py's
module-level negative-spec against a second copy of it.

Composes an already-ported claude-klabauter op in-process (no subprocess re-invocation of
its standalone CLI trampoline):
  coordinator_core.ops.read_frontmatter_field.read_frontmatter_field

Output convention (resolve-* subcommands): shell-assignment lines on stdout, meant to
be consumed via `eval "$(spinoff-deliverable-and-commit.py resolve-origin-handoff-id ...)"`
so resolved variables land directly in the caller's current shell — mirrors
handoff-deliverable-carry.py's convention (same "must share one shell process"
constraint the bash oracle called out for the handoff surface's analogous cascade).

Exit codes: 0 on success. A missing/unresolvable engine root (this trampoline's own
transport failure) exits 3 — distinct from any business-logic exit. A fail-loud
business-logic guard (missing/empty scope block on commit-scope) exits 1, matching
the bash oracle's own `exit 1` on the same guard.

Spec backlink: coordinator/skills/spinoff/SKILL.md § "origin_handoff_id:" (C2 block),
               § "Step 4: Commit"
Port of: the two bash fences named above in DoE-claude
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
from cc_invoke import _no_console_passthrough_kw, _resolve_claude_klabauter_root, require_dispatch_engine_on_path  # noqa: E402

_TRANSPORT_FAIL = 3


def _import_ops():
    """Resolve the engine root, put it on sys.path, and import the composed ops.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it — this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is deliberately
    NOT used here (same convention as archive-stamp-cli, read-frontmatter-field.py,
    mint-deliverable-id.py, handoff-deliverable-carry.py).
    """
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.ops.read_frontmatter_field import read_frontmatter_field

    return read_frontmatter_field


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


def _cmd_resolve_origin_handoff_id(args: argparse.Namespace, read_frontmatter_field) -> int:
    origin_handoff_id = resolve_origin_handoff_id(read_frontmatter_field, args.origin_handoff)
    print(f"ORIGIN_HANDOFF_ID={origin_handoff_id}")
    return 0


def _cmd_commit_scope(args: argparse.Namespace, _read_frontmatter_field) -> int:
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
        description="origin-handoff-id carry + scope-scoped commit for /spinoff",
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

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
        read_frontmatter_field = _import_ops()
    except RuntimeError as exc:
        print(f"spinoff-deliverable-and-commit.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL
    except ImportError as exc:
        print(f"spinoff-deliverable-and-commit.py: coordinator_core ops not importable: {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL

    if args.subcommand == "resolve-origin-handoff-id":
        return _cmd_resolve_origin_handoff_id(args, read_frontmatter_field)
    if args.subcommand == "commit-scope":
        return _cmd_commit_scope(args, read_frontmatter_field)

    parser.print_usage(sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
