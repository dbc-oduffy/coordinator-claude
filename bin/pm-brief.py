#!/usr/bin/env python3
"""pm-brief — thin CLI over `coordinator/bin/lib/pm_brief.py`.

`render --for executor|reviewer <plan>` prints the `## PM intent (verbatim)` block that module
resolves and renders. Exit 1 with the `NoPmBriefError` message when nothing resolves — same
fail-loud rule the emitter (C4) and `compose-review-wave.py` (C10) both use.
`from-sizing <sizing>` prints the blockquote body that seeds `## PM brief` from a sizing's
`pm_verbatims`; exit 1 with nothing on stdout when the sizing carries none. All logic lives in
the imported module; this file is argument parsing and stdout only.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_BIN_LIB_DIR = Path(__file__).resolve().parent / "lib"


def _pm_brief():
    """`pm_brief`, imported on first use so a bare import of this module leaves
    `sys.path` untouched."""
    if str(_BIN_LIB_DIR) not in sys.path:
        sys.path.insert(0, str(_BIN_LIB_DIR))
    import pm_brief

    return pm_brief


def _repo_root(explicit: str | None) -> Path:
    """The repo the plan belongs to: `--repo-root`, else the nearest cwd ancestor holding
    `.git`, else cwd. Never this file's own location -- run from the published engine, that
    names the engine mirror, not the caller's repo (relative plans then FileNotFoundError)."""
    if explicit:
        return Path(explicit).resolve()
    cwd = Path.cwd().resolve()
    for candidate in (cwd, *cwd.parents):
        if (candidate / ".git").exists():
            return candidate
    return cwd


def _under(root: Path, raw: str) -> Path:
    """`raw` as given when absolute; otherwise cwd-relative when that exists, else
    `root`-relative -- a path typed at a shell means cwd first."""
    path = Path(raw)
    if path.is_absolute():
        return path
    cwd_path = Path.cwd() / path
    return cwd_path if cwd_path.exists() else root / path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="pm-brief")
    parser.add_argument(
        "--repo-root", default=None,
        help="repo the plan or sizing belongs to (default: the git checkout enclosing cwd)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    render = sub.add_parser("render", help="render the PM intent block for an audience")
    render.add_argument("plan", type=str, help="repo-relative or absolute path to the plan")
    render.add_argument(
        "--for", dest="audience", choices=("executor", "reviewer"), required=True,
    )

    from_sizing = sub.add_parser("from-sizing", help="print a sizing's pm_verbatims as a blockquote")
    from_sizing.add_argument("sizing", type=str, help="repo-relative or absolute sizing path")

    args = parser.parse_args(argv)

    pm_brief = _pm_brief()
    repo_root = _repo_root(args.repo_root)
    if args.command == "from-sizing":
        sizing_path = _under(repo_root, args.sizing)
        body = pm_brief.render_sizing_brief(sizing_path)
        if body is None:
            print(f"no pm_verbatims in {sizing_path}", file=sys.stderr)
            return 1
        print(body)
        return 0
    plan_path = _under(repo_root, args.plan)

    try:
        brief = pm_brief.resolve(plan_path, repo_root)
    except pm_brief.NoPmBriefError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(pm_brief.render_block(brief, args.audience))
    return 0


if __name__ == "__main__":
    sys.exit(main())
