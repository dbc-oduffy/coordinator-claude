"""sizing-link-baton.py -- link batons to their existing sizing objects.

Usage:
    sizing-link-baton.py --baton RECORD [--baton RECORD ...] [--write] [--repo-root PATH]

Prints one JSON object per baton: {baton, sizing, basis, stamped, conflict}. The match is
`coordinator_core.roadmap.sizing_match.match_sizings` (deliverable_id, else title slug; one
batched git spawn). Without --write nothing is written; with it the sizing gets its `baton:`
key and the baton gets `sizing_object` / `deliverable_id` / `handoff_id`.

Exit codes:
    0 -- every baton is linked or was already linked.
    3 -- any baton is ambiguous, unmatched or conflicted (JSON still printed).
    2 -- bad argv.

Negative-spec: does NOT mint a sizing, relax any lane check, or commit.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_EXIT_UNLINKED = 3


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="sizing-link-baton.py",
        description="Link batons to their existing sizing objects (dry run unless --write).",
    )
    p.add_argument("--baton", action="append", required=True, metavar="RECORD",
                   help="baton record, repo-relative or absolute; repeatable.")
    p.add_argument("--write", action="store_true",
                   help="stamp the sizing's `baton:` and the baton's sizing citation.")
    p.add_argument("--repo-root", default=None, metavar="PATH",
                   help="worktree root (default: the nearest ancestor of cwd holding .git).")
    return p


def _find_root(start: Path) -> Path | None:
    for d in (start, *start.parents):
        if (d / ".git").exists():
            return d
    return None


def _rel(root: Path, baton: str) -> str:
    p = Path(baton)
    if p.is_absolute():
        try:
            p = p.resolve().relative_to(root.resolve())
        except ValueError:
            return baton.replace("\\", "/")
    return p.as_posix()


def _ensure_engine() -> None:
    try:
        import coordinator_core  # noqa: F401
    except ImportError:
        import lib  # noqa: F401 -- bootstraps coordinator/bin/lib onto sys.path
        import cc_invoke

        cc_invoke.require_engine_on_path(__file__)


def link(root: Path, batons: list[str], write: bool) -> list[dict]:
    from coordinator_core.roadmap.blitz_land import LandingRefused, join_xs_sizing_to_baton
    from coordinator_core.roadmap.sizing_match import match_sizings, stamp_sizing_baton

    rels = [_rel(root, b) for b in batons]
    out: list[dict] = []
    for m in match_sizings(root, rels):
        row = {"baton": m["baton"], "sizing": m["sizing"], "basis": m["basis"],
               "stamped": False, "conflict": None}
        if m["sizing"] is None:
            if m["candidates"]:
                row["conflict"] = "candidates: " + ", ".join(m["candidates"])
        elif write:
            try:
                s = stamp_sizing_baton(root, m["sizing"], m["baton"])
                j = join_xs_sizing_to_baton(root, m["baton"], {"sizingObject": m["sizing"]})
            except LandingRefused as exc:
                row["conflict"] = str(exc)
            except OSError as exc:
                row["conflict"] = f"{type(exc).__name__}: {exc}"
            else:
                row["stamped"] = bool(s["stamped"] or j["stamped"])
                row["conflict"] = s["conflict"] or ("; ".join(j["conflicts"]) or None)
        out.append(row)
    return out


def main(argv: list[str] | None = None) -> int:
    try:
        ns = build_parser().parse_args(sys.argv[1:] if argv is None else argv)
    except SystemExit as exc:
        return 2 if exc.code not in (0, None) else 0
    root = Path(ns.repo_root) if ns.repo_root else _find_root(Path(os.getcwd()))
    if root is None or not root.is_dir():
        print("sizing-link-baton: no repo root (pass --repo-root)", file=sys.stderr)
        return 2
    _ensure_engine()
    rows = link(root, ns.baton, ns.write)
    for row in rows:
        print(json.dumps(row))
    return 0 if all(r["sizing"] and not r["conflict"] for r in rows) else _EXIT_UNLINKED


if __name__ == "__main__":
    sys.exit(main())
