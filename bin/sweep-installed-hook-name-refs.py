# coordinator/bin/sweep-installed-hook-name-refs.py
#
# Answers "which coordinator/bin entrypoint names do the git hooks installed on
# this machine actually name?" by reading every co-located repo's `.git/hooks/`
# directly.
#
# Why this exists: `.git/hooks` is untracked state living in peer working trees,
# so no repo grep, cross-repo memo, or reference census reaches it. The C6
# rename chunk of docs/plans/2026-08-13-grind-the-posix-exec-baseline-to-zero.md
# names it as a blind spot and reasons about it indirectly, via the installer's
# `_GATE_REGISTRY` version stamp. That indirection is unnecessary on a machine
# where the sibling trees are co-located: the hooks are readable, so the
# question has a direct answer. Renaming a name this script reports breaks the
# installed hook in every tree listed beside it, until that tree re-runs the
# installer.
#
# The failure is not uniform, and the quiet one is the dangerous one:
# `prepare-commit-msg` and `post-commit` end their resolution chain with a
# warning and `exit 0`, so a rename silently stops annotating and auto-pushing;
# `pre-commit` exits 1 on a missing gate script, which at least announces
# itself. Read the hook body before deciding a hit is survivable.
#
# Exit 0 always -- this reports, it does not gate. Callers decide.

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

def _default_sibling_root() -> Path:
    """The directory holding the co-located working trees — this repo's PARENT.

    Derived, never a literal: an operator-home path baked in here would be
    unresolvable on any other machine, and this file would then be a violation
    of the very `unresolved_cross_path` class the drain it serves is clearing.

    Count the rungs from THIS file, not from the repo root: `parents[0]` is
    `coordinator/bin`, `[1]` is `coordinator`, `[2]` is the repo itself, and
    `[3]` is the sibling root. `[2]` was the original value and it was wrong in
    the worst available direction — it made the sweep walk one repo instead of
    all of them, find nothing, and report a confident clean "no installed hook
    names one of them". A safety check whose failure mode is a false ALL-CLEAR
    is worse than no check, and this one was handed to six executors as a
    pre-rename gate. It cleared them by accident: every genuine hit was a name
    already held back for another reason."""
    return Path(__file__).resolve().parents[3]


def _extensionless_bin_names(baseline: Path) -> set[str]:
    """The population a rename wave draws from: entries under coordinator/bin/
    whose basename carries no extension. Read off the baseline rather than the
    filesystem so the answer tracks what the POSIX-exec gate still counts."""
    data = json.loads(baseline.read_text(encoding="utf-8"))
    names: set[str] = set()
    for value in data.values():
        if not isinstance(value, list):
            continue
        for entry in value:
            base = entry.rsplit("/", 1)[-1]
            if entry.startswith("coordinator/bin/") and "." not in base:
                names.add(base)
    return names


def _hook_files(sibling_root: Path):
    for repo in sorted(sibling_root.iterdir()):
        hooks = repo / ".git" / "hooks"
        if not hooks.is_dir():
            continue
        for hook in sorted(hooks.iterdir()):
            if hook.is_file() and not hook.name.endswith(".sample"):
                yield repo.name, hook


def sweep(names: set[str], sibling_root: Path) -> dict[str, list[str]]:
    """Maps each named entrypoint to the `<repo>/<hook>` bodies naming it.

    Matching is word-boundary-ish on both sides but treats `.` and `-` as name
    characters, so `foo` does not match an already-renamed `foo.py`: a hit means
    the hook names the OLD extensionless form and would break on the rename."""
    patterns = {n: re.compile(r"(?<![\w.-])" + re.escape(n) + r"(?![\w.-])") for n in names}
    hits: dict[str, set[str]] = {}
    for repo_name, hook in _hook_files(sibling_root):
        try:
            body = hook.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for name, pattern in patterns.items():
            if pattern.search(body):
                hits.setdefault(name, set()).add(f"{repo_name}/{hook.name}")
    return {name: sorted(where) for name, where in sorted(hits.items())}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="sweep-installed-hook-name-refs",
        description=(
            "Report which extensionless coordinator/bin names are referenced by "
            "git hooks installed in co-located repos. Reports only; never gates."
        ),
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=Path("state/posix-exec-baseline.json"),
        help="POSIX-exec baseline the name population is read from.",
    )
    parser.add_argument(
        "--sibling-root",
        type=Path,
        default=_default_sibling_root(),
        help="Directory holding the co-located working trees.",
    )
    parser.add_argument("--json", action="store_true", help="Emit one JSON object instead of text.")
    args = parser.parse_args(argv)

    if not args.baseline.is_file():
        print(f"sweep-installed-hook-name-refs: no baseline at {args.baseline}", file=sys.stderr)
        return 2
    if not args.sibling_root.is_dir():
        print(f"sweep-installed-hook-name-refs: no sibling root at {args.sibling_root}", file=sys.stderr)
        return 2

    names = _extensionless_bin_names(args.baseline)
    hooks_scanned = sum(1 for _ in _hook_files(args.sibling_root))
    if hooks_scanned == 0:
        # Zero hook files is not a clean result, it is a broken sweep: this tool
        # is used as a pre-rename gate, so "found nothing" and "looked nowhere"
        # must never render the same. They did once — a sibling-root off by one
        # directory scanned a repo instead of the repo's parent, found no
        # `.git/hooks` anywhere beneath it, and printed a confident all-clear to
        # six executors. Exit 2, loudly, rather than clearing anything.
        print(
            f"sweep-installed-hook-name-refs: no git hooks found under {args.sibling_root} — "
            "this is a broken sweep, not a clean one. Point --sibling-root at the directory "
            "that HOLDS the co-located working trees (the repo's parent), not at a repo.",
            file=sys.stderr,
        )
        return 2
    hits = sweep(names, args.sibling_root)

    if args.json:
        print(json.dumps({"population": len(names), "hits": hits}, indent=2))
        return 0

    print(f"{len(names)} extensionless coordinator/bin name(s) in the baseline population.")
    if not hits:
        print("No installed hook in any co-located tree names one of them.")
        return 0
    print(f"{len(hits)} name(s) named by an installed hook -- renaming one breaks every tree listed:")
    for name, where in hits.items():
        print(f"  {name} ({len(where)} hook file(s))")
        for entry in where:
            print(f"      {entry}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
