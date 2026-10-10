"""pm-brief — thin CLI over `coordinator/bin/lib/pm_brief.py`.

`render --for executor|reviewer <plan>` prints the `## PM intent (verbatim)` block that module
resolves and renders. Exit 1 with the `NoPmBriefError` message when nothing resolves — same
fail-loud rule the emitter (C4) and `compose-review-wave.py` (C10) both use. All logic lives in
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


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="pm-brief")
    sub = parser.add_subparsers(dest="command", required=True)

    render = sub.add_parser("render", help="render the PM intent block for an audience")
    render.add_argument("plan", type=str, help="repo-relative or absolute path to the plan")
    render.add_argument(
        "--for", dest="audience", choices=("executor", "reviewer"), required=True,
    )

    args = parser.parse_args(argv)

    pm_brief = _pm_brief()
    repo_root = _repo_root()
    plan_path = Path(args.plan)
    if not plan_path.is_absolute():
        plan_path = repo_root / plan_path

    try:
        brief = pm_brief.resolve(plan_path, repo_root)
    except pm_brief.NoPmBriefError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(pm_brief.render_block(brief, args.audience))
    return 0


if __name__ == "__main__":
    sys.exit(main())
