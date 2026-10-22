"""plan-overlap — offer a merge when the plans of two claimed batons write the same files. Writes nothing.

WHY THIS EXISTS. `/mise-en-place` can claim N batons whose plans write the same files, and
nothing noticed. The shared-path answer already exists in the engine: `plan.overlap_edges` is what
Phase 0 orders certified plans with, and a second scanner beside it would be a second answer to a
settled question. But that op compares CERTIFIED plans only, so a naive wrapper reads "not
compared" as "no overlap". This script resolves each baton to its plans, asks the op for the
shared paths of one cross plan pair at a time, and returns `offer`, `none` or `undetermined` per
baton pair.

ONE CALL PER CROSS PLAN PAIR. The op drops a pair already ordered through edges it added earlier
in the same derivation, so a call over the whole grab can lose a real overlap. A two-plan call can
only drop a pair the plans themselves order by `depends_on_plan`.

THRESHOLD. At least one shared path. One shared write file is already the collision a merge
resolves; a ratio would hide it inside a large plan.

UNDETERMINED IS NOT NONE. A plan the op did not compare (`uncertified`, `unreadable`) or a baton
that resolves to no plan (`no-plan`) has an unknown footprint. Reading that as disjoint is the
absent-key-as-empty defect. An overlap found among the compared plans still yields `offer`.

Negative-spec:
  - Does NOT write any file or store a verdict on a baton or plan.
  - Does NOT call or import `plan.merge`; the offer is the line below and acceptance is the
    caller's explicit act.
  - Does NOT read a plan spine, a row write set or a row surface. Every shared path comes from
    the engine op.
  - Does NOT fall back when the engine is unreachable: that is exit 3, never a verdict, because
    the caller's bootstrap fails open and a silent fallback would read as "no overlap".
  - Does NOT import aggregate-rollup (hyphenated filename); the frontmatter split is transcribed.

Zero subprocess, stdlib plus PyYAML.

Offer line: `these two batons' plans overlap on <file>, <file>; merge them?` (files sorted).

Exit status is a verdict: 0 every pair is `none`, 1 at least one pair is `offer` (a membership
fact, not an error), 2 no `offer` and at least one `undetermined`, 3 a usage, parse or engine
error.
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import itertools
import json
import re
import sys
from pathlib import Path

import yaml

_SCRIPT_DIR = Path(__file__).resolve().parent
_PLUGIN_ROOT = _SCRIPT_DIR.parent.parent
_HOOKS_SCRIPTS_DIR = _PLUGIN_ROOT / "hooks" / "scripts"

OFFER = "offer"
NONE = "none"
UNDETERMINED = "undetermined"

EXIT_NONE = 0
EXIT_OFFER = 1
EXIT_UNDETERMINED = 2
EXIT_ERROR = 3

_FM_DELIMITER_RE = re.compile(r"^---[ \t]*$")


class OverlapError(RuntimeError):
    """A usage, parse or engine failure. `main()` prints it to stderr and exits `EXIT_ERROR`."""


def _frontmatter(path: Path, needles: tuple = ()) -> dict:
    """Frontmatter mapping of `path`, read up to the closing `---` only; `{}` when absent.

    With `needles`, a block containing none of those substrings returns `{}` unparsed: the plan
    index only needs the few plans a claimed baton names, and YAML-parsing every plan dominates
    the run time."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise OverlapError(f"cannot read {path}: {exc}") from exc
    if not lines or not _FM_DELIMITER_RE.match(lines[0]):
        return {}
    block = []
    for line in lines[1:]:
        if _FM_DELIMITER_RE.match(line):
            break
        block.append(line)
    else:
        return {}
    text = "\n".join(block)
    if needles and not any(n in text for n in needles):
        return {}
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise OverlapError(f"unparseable frontmatter in {path}: {exc}") from exc
    return doc if isinstance(doc, dict) else {}


def _as_str_list(value) -> list:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value if isinstance(v, (str, int)) and str(v).strip()]
    return []


def _baton_ids(baton: Path) -> list:
    fm = _frontmatter(baton)
    return (_as_str_list(fm.get("origin_plan_id")) + _as_str_list(fm.get("plan_ids"))
            + _as_str_list(fm.get("deliverable_id")))


def _plan_index(repo_root: Path, needles: tuple = ()) -> tuple:
    """(by plan_id, by deliverable_id) -> repo-relative plan paths, from `docs/plans/*.md`.

    `needles` limits parsing to plans whose frontmatter mentions one of the ids."""
    by_plan: dict = {}
    by_deliverable: dict = {}
    plans_dir = repo_root / "docs" / "plans"
    if not plans_dir.is_dir():
        return by_plan, by_deliverable
    for path in sorted(plans_dir.glob("*.md")):
        try:
            fm = _frontmatter(path, needles)
        except OverlapError:
            continue  # unparseable plan: a baton naming it reads no-plan
        rel = f"docs/plans/{path.name}"
        for pid in _as_str_list(fm.get("plan_id")):
            by_plan.setdefault(pid, set()).add(rel)
        for did in _as_str_list(fm.get("deliverable_id")):
            by_deliverable.setdefault(did, set()).add(rel)
    return by_plan, by_deliverable


def baton_plans(baton: Path, index: tuple) -> list:
    """The union of the plans a baton names by `origin_plan_id`, `plan_ids` and `deliverable_id`."""
    by_plan, by_deliverable = index
    fm = _frontmatter(baton)
    plans: set = set()
    for pid in _as_str_list(fm.get("origin_plan_id")) + _as_str_list(fm.get("plan_ids")):
        plans |= by_plan.get(pid, set())
    for did in _as_str_list(fm.get("deliverable_id")):
        plans |= by_deliverable.get(did, set())
    return sorted(plans)


def _default_repo_root() -> Path:
    """The repo the invocation is standing in -- cwd's git root, shared with aggregate-rollup."""
    if str(_HOOKS_SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(_HOOKS_SCRIPTS_DIR))
    from _repo_root import repo_root

    return repo_root(Path(__file__).resolve().parents[3])


def _resolve_engine_root():
    """The engine root through the shared `_engine_root` seam, or None when none resolves."""
    if str(_HOOKS_SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(_HOOKS_SCRIPTS_DIR))
    try:
        from _engine_root import resolve_claude_klabauter_root  # pyright: ignore[reportMissingImports]
    except Exception as exc:
        raise OverlapError(f"coordinator_core unreachable: _engine_root unimportable ({exc})") from exc
    return resolve_claude_klabauter_root()


def _engine_handler():
    """The in-process `plan.overlap_edges` handler; raises `OverlapError` naming why it is absent."""
    root = _resolve_engine_root()
    if not root:
        raise OverlapError(
            "coordinator_core unreachable: could not resolve the engine root "
            "(set REPO_CLAUDE_KLABAUTER, or COORDINATOR_ENGINE_ROOT, or register "
            "repos.claude_klabauter in machine-local)"
        )
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        from coordinator_core.ipc import get_op_handler
        from coordinator_core.op_budget_suspension import OpSuspendedError
    except Exception as exc:
        raise OverlapError(f"coordinator_core unimportable from {root}: {exc}") from exc
    try:
        handler = get_op_handler("plan.overlap_edges")
    except OpSuspendedError:
        handler = None
    except Exception as exc:
        raise OverlapError(f"plan.overlap_edges lookup failed: {exc}") from exc
    if handler is None:
        raise OverlapError("plan.overlap_edges is not available (unregistered or suspended)")
    return handler


def overlap_call(plans: list, repo_root: Path) -> dict:
    """One `plan.overlap_edges` reply for `plans`. Module-level so tests replace it."""
    handler = _engine_handler()
    try:
        from coordinator_core.lifecycle import git_common_dir

        result = handler({"plans": list(plans)}, git_common_dir(repo_root))
        if inspect.isawaitable(result):
            result = asyncio.run(result)
    except OverlapError:
        raise
    except Exception as exc:
        raise OverlapError(f"plan.overlap_edges failed: {exc}") from exc
    if not isinstance(result, dict):
        raise OverlapError("plan.overlap_edges returned a non-mapping reply")
    return result


def _cross_pair_reading(reply: dict, x: str, y: str) -> tuple:
    """(shared paths, set of plans not compared, {plan: reason}) from one two-plan reply."""
    pair = {x, y}
    paths: set = set()
    for edge in reply.get("edges") or []:
        if {edge.get("before"), edge.get("after")} == pair:
            paths.update(edge.get("paths") or [])
    for cycle in reply.get("cycles") or []:
        if set(cycle.get("plans") or []) == pair and cycle.get("path"):
            paths.add(cycle["path"])
    reasons: dict = {}
    for rel in reply.get("uncertified") or []:
        if rel in pair:
            reasons[rel] = "uncertified"
    for item in reply.get("unreadable") or []:
        rel = item.get("plan") if isinstance(item, dict) else item
        if rel in pair:
            reasons[rel] = "unreadable"
    return paths, reasons


def offer_line(files: list) -> str:
    return f"these two batons' plans overlap on {', '.join(files)}; merge them?"


def pair_verdict(plans_x: list, plans_y: list, repo_root: Path) -> dict:
    """Verdict for one baton pair: `{verdict, files, reason, offer_line}`."""
    if not plans_x or not plans_y:
        return {"verdict": UNDETERMINED, "files": [], "reason": "no-plan", "offer_line": None}
    files: set = set()
    reasons: set = set()
    for x, y in itertools.product(sorted(set(plans_x)), sorted(set(plans_y))):
        if x == y:
            continue
        reply = overlap_call(sorted((x, y)), repo_root)
        paths, not_compared = _cross_pair_reading(reply, x, y)
        files |= set(paths)
        reasons |= set(not_compared.values())
    if files:
        ordered = sorted(files)
        return {"verdict": OFFER, "files": ordered, "reason": None, "offer_line": offer_line(ordered)}
    if reasons:
        return {"verdict": UNDETERMINED, "files": [], "reason": "/".join(sorted(reasons)),
                "offer_line": None}
    return {"verdict": NONE, "files": [], "reason": None, "offer_line": None}


def detect(batons: list, repo_root: Path) -> dict:
    """Pairwise verdicts for every unordered baton pair. `batons` are resolved paths."""
    needles = tuple(sorted({i for b in batons for i in _baton_ids(b)}))
    index = _plan_index(repo_root, needles) if needles else ({}, {})
    resolved = [(b, baton_plans(b, index)) for b in batons]
    pairs = []
    for (bx, px), (by, py) in itertools.combinations(resolved, 2):
        row = pair_verdict(px, py, repo_root)
        pairs.append({"batons": [str(bx), str(by)], **row})
    return {"pairs": pairs}


def exit_code(report: dict) -> int:
    verdicts = {p["verdict"] for p in report["pairs"]}
    if OFFER in verdicts:
        return EXIT_OFFER
    if UNDETERMINED in verdicts:
        return EXIT_UNDETERMINED
    return EXIT_NONE


def _render(report: dict) -> str:
    out = []
    for p in report["pairs"]:
        a, b = (Path(x).name for x in p["batons"])
        if p["verdict"] == OFFER:
            out.append(f"{a} + {b}: offer: {p['offer_line']}")
        elif p["verdict"] == UNDETERMINED:
            out.append(f"{a} + {b}: undetermined: {p['reason']}")
        else:
            out.append(f"{a} + {b}: none")
    return "\n".join(out)


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(
        prog="plan-overlap",
        description="Offer a merge when claimed batons' plans write the same files. Writes nothing.",
    )
    parser.add_argument("batons", nargs="+", help="two or more baton paths")
    parser.add_argument("--json", action="store_true", help="emit the report as JSON")
    parser.add_argument("--repo-root", default=None,
                        help="repo to resolve plans against (default: cwd's git root)")
    args = parser.parse_args(argv[1:])

    try:
        if len(args.batons) < 2:
            raise OverlapError("plan-overlap needs at least two batons")
        repo_root = Path(args.repo_root).resolve() if args.repo_root else _default_repo_root()
        paths = []
        for raw in args.batons:
            baton = Path(raw)
            if not baton.is_absolute():
                baton = baton.resolve() if baton.resolve().is_file() else repo_root / baton
            if not baton.is_file():
                raise OverlapError(f"no such baton: {raw}")
            paths.append(baton)
        report = detect(paths, repo_root)
    except OverlapError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_ERROR

    print(json.dumps(report, indent=2) if args.json else _render(report))
    return exit_code(report)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
