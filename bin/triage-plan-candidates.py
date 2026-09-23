#!/usr/bin/env python3
"""Rank plans by whether dispatching them would do any WORK, not by whether a
row still says `disposition: open`.

WHY THIS EXISTS. A plan-tasks row's `disposition` is a declaration an author
writes and nobody retracts. Nothing walks back and flips it when the work
lands by another route -- a peer session's commit, a chunk folded into a
neighbouring plan, a fix applied directly. So picking candidates by
`disposition: open` selects for *unretracted declarations*, which is not the
same set as *unexecuted work*, and the gap is invisible until a wave halts.

Measured 2026-09-17: three plans selected that way dispatched three waves,
all three VOID -- every declared write already on disk. Each void wave costs a
full dispatch plus the EM's hand-edit, restamp and resume to clear the halt
gate. The filter is cheaper than the wave.

WHAT IT MEASURES. Two independent legs, because neither alone caught all
three:

  1. SLUG REFERENCE. A commit message naming the plan's stem. Catches the
     ordinary case where a chunk landed under its own plan's name. Caught 2/3.
  2. WRITES ALREADY PRESENT. Every path a row declares in `writes` exists on
     disk AND has at least one commit touching it. Caught the third, whose
     deliverables were committed under a message that never names the plan.

Both legs are reported per plan and neither is authoritative alone.

NEGATIVE-SPEC -- what this tool is NOT:

  - NOT a skip list, and it never edits a plan. `suspect` means LOOK, not
    "closed": a row legitimately rewrites an existing file, so leg 2 cannot
    tell "done" from "needs another pass". The output ranks reading order.
  - NOT a disposition writer. Flipping a row to `backlogged`/`wont_do` needs
    `pm_approved` + `case_against` + refs, which is a PM gate and not a thing
    a triage filter gets to infer.
  - NOT a substitute for the exit criterion. A plan whose criterion is
    already satisfied is void whatever its writes look like; that question is
    the falsifier's, not this tool's.
  - Does NOT read `disposition` at all. Reading it back would reintroduce the
    signal this tool exists because of.

PATH RESOLUTION -- ENGINE CLASS. This script now lives inside the engine
checkout (`coordinator/bin/`), so `coordinator_core` is a sibling package
resolved through the ordinary `coordinator/bin/lib/cc_invoke.py` bootstrap --
no more `_engine_root`/`resolve_claude_klabauter_root` seam import from a DoE-side
`coordinator/hooks/scripts/_engine_root.py` (`docs/plans/2026-09-18-doe-holds-no-scripts.md`
§ Path resolution).

Spec backlink: docs/plans/2026-09-18-doe-holds-no-scripts.md, chunk W3-C2.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_CLI_ROOT = Path(__file__).resolve().parents[2]


class TriageError(RuntimeError):
    """A fail-loud precondition. `main()` prints it and exits non-zero."""


def _resolve_engine_root() -> Path:
    """Put `coordinator_core` on `sys.path` via the standard engine-resident CLI bootstrap.

    Engine imports happen here, inside a function, never at module scope -- keeps the module
    body pure so `serve_classifier` still classifies this file warm-servable.
    """
    try:
        import lib  # noqa: F401 -- bootstraps coordinator/bin/lib onto sys.path
        import cc_invoke

        root = cc_invoke.require_engine_on_path(__file__)
    except Exception as exc:
        raise TriageError(f"coordinator_core unreachable: engine bootstrap failed ({exc})")

    root_path = Path(root)
    if not (root_path / "coordinator_core").is_dir():
        raise TriageError(
            f"coordinator_core unreachable: {root_path} has no coordinator_core/ package"
        )
    return root_path


def _git(repo: Path, *args: str) -> str:
    """One git read. Returns stdout stripped, or "" on any non-zero exit --
    this tool reports signal strength and must never fail a whole triage run
    because one path has no history.

    # Routes through
    # coordinator_core.ops.ceremony.git_native._git instead of hand-rolling a
    # second subprocess.run wrapper with its own creationflags/timeout/failure
    # mapping.

    Bootstraps itself: its only caller is `RepoFacts.__init__`, reachable from
    the exported `triage()` without passing through `main()`.
    """
    _resolve_engine_root()
    from coordinator_core.ops.ceremony.git_native import _git as _git_native

    result = _git_native(list(args), cwd=repo, timeout=30)
    if not result.ok:
        return ""
    return result.stdout.strip()


class RepoFacts:
    """Both git reads this tool needs, taken ONCE for the whole run.

    TWO SPAWNS, NEVER PER-ITEM. The first cut asked git per declared write
    path (`git log -1 -- <path>`) and per plan (`git log --grep`), which is
    hundreds of process creations across a plan corpus and the exact
    per-item-spawn shape `claude-klabauter`'s amplification gate exists to
    refuse -- process creation is the cost, not the query. It also did not
    finish inside two minutes on claude-klabauter's corpus.

    Both questions answer from bulk reads instead:

      - `log --format=%H%x00%B%x00%x00` over all refs, once: every commit
        message, searched in memory for a plan stem.
      - `ls-tree -r HEAD --name-only`, once: the set of paths committed at
        HEAD. Membership answers "has a commit touching it" exactly, and
        does so without asking about any single path.
    """

    def __init__(self, repo: Path) -> None:
        self.repo = repo
        blob = _git(repo, "log", "--all", "--format=%H%x00%B%x00%x00")
        self._messages = blob.lower()
        tracked = _git(repo, "ls-tree", "-r", "HEAD", "--name-only")
        self.committed: set[str] = {
            line.strip() for line in tracked.splitlines() if line.strip()
        }

    def slug_hits(self, stem: str) -> int:
        """How many commit messages mention `stem`.

        Counted on the lowercased corpus because a commit message may
        capitalize a slug it quotes in prose. A stem is a dated, hyphenated
        title -- specific enough that substring matching does not need word
        boundaries to stay meaningful.
        """
        needle = stem.lower()
        if not needle:
            return 0
        return self._messages.count(needle)


def _writes_state(repo: Path, facts: RepoFacts, writes: object) -> tuple[int, int, int]:
    """(declared, present_on_disk, committed) across a row's declared writes.

    A row whose `writes` is the engine's UNDECLARED sentinel rather than a
    list reports (0, 0, 0) -- nothing to measure, and guessing paths from the
    title would invent evidence.
    """
    if not isinstance(writes, list):
        return (0, 0, 0)
    declared = present = committed = 0
    for raw in writes:
        if not isinstance(raw, str) or not raw.strip():
            continue
        declared += 1
        rel = raw.strip().replace("\\", "/").lstrip("./")
        if (repo / rel).exists():
            present += 1
            if rel in facts.committed:
                committed += 1
    return (declared, present, committed)


_MOSTLY_PRESENT = 0.8

_SCAFFOLD_MARKERS: "tuple[str, ...]" = (
    "path/to/file/this/chunk/writes.py",
    "path/to/another/file/this/chunk/writes.py",
)


def _scaffold_residue(plan_text: str) -> list[str]:
    """Placeholder strings `coordinator-doc-new.py`'s plan template emits,
    still present in a plan body.

    THE THIRD LEG, and it catches what the other two cannot. A scaffolded but
    never-enriched plan declares writes in its spine, so the writes leg
    measures it as fresh and the slug leg has nothing to find -- it emits
    cleanly and then halts at PREFLIGHT, because the pathspec the preflight
    agent is handed is the template's literal
    `[path/to/file/this/chunk/writes.py]` rather than a path. The agent
    correctly refuses to verify a placeholder, the wave dies before any write,
    and the whole dispatch is spent.

    Measured 2026-09-17: two of the three plans `claude-klabauter` reported as
    genuine candidates were this, and both halted exactly here.

    The remedy differs from every other verdict, which is why it gets its own:
    the plan is real unexecuted work and wants ENRICHING, not skipping.
    """
    return [marker for marker in _SCAFFOLD_MARKERS if marker in plan_text]


def _classify(slug_hits: int, declared: int, present: int, committed: int) -> str:
    """Six verdicts, and the two that look alike are the point.

    `candidate` means MEASURED AND FRESH: the rows declared writes and none of
    them are on disk. `unmeasured` means the rows declared no writes at all,
    so the writes leg had nothing to read and this plan's state is unknown,
    not clean. Collapsing the two is how a triage filter sends you straight
    back into the void waves it exists to prevent -- on `claude-klabauter` the
    first cut did exactly that, and 41 of 75 "candidates" were really
    unmeasured.

    Presence is a RATIO, not an equality. Requiring every declared write to be
    present before flagging anything filed a plan with 48 of 52 writes already
    committed as a clean candidate. `suspect-mostly-landed` catches the
    partially-executed case that exact matching cannot see.
    """
    if declared:
        if present == declared and committed == declared:
            return "suspect-void"
        if present / declared >= _MOSTLY_PRESENT:
            return "suspect-mostly-landed"
    if slug_hits:
        return "suspect-landed"
    if not declared:
        return "unmeasured"
    if present:
        return "check-writes"
    return "candidate"


_ORDER = {
    "candidate": 0,
    "scaffold-stub": 1,
    "unmeasured": 2,
    "check-writes": 3,
    "suspect-landed": 4,
    "suspect-mostly-landed": 5,
    "suspect-void": 6,
}


def triage(repo: Path, plans: list[Path]) -> list[dict]:
    from coordinator_core.ops.dispatch_emit.spine_read import read_spine

    facts = RepoFacts(repo)
    rows_out: list[dict] = []
    for plan in plans:
        stem = plan.stem
        record: dict = {"plan": plan, "stem": stem}
        try:
            spine = read_spine(str(plan))
        except Exception as exc:
            record.update(
                verdict="unreadable-spine",
                detail=f"{type(exc).__name__}: {exc}",
                rows=0,
            )
            rows_out.append(record)
            continue

        slug_hits = facts.slug_hits(stem)
        declared = present = committed = 0
        for row in spine:
            d, p, c = _writes_state(repo, facts, row.writes)
            declared += d
            present += p
            committed += c

        try:
            residue = _scaffold_residue(plan.read_text(encoding="utf-8"))
        except OSError:
            residue = []

        verdict = (
            "scaffold-stub" if residue
            else _classify(slug_hits, declared, present, committed)
        )
        record.update(
            rows=len(spine),
            slug_hits=slug_hits,
            declared=declared,
            present=present,
            committed=committed,
            residue=residue,
            verdict=verdict,
        )
        rows_out.append(record)

    rows_out.sort(
        key=lambda r: (_ORDER.get(r.get("verdict", ""), 9), str(r["plan"]))
    )
    return rows_out


def _render(records: list[dict]) -> str:
    lines = []
    for r in records:
        if r["verdict"] == "unreadable-spine":
            lines.append(f"{r['verdict']:<16} {r['stem']}\n{'':<17} {r['detail']}")
            continue
        lines.append(
            f"{r['verdict']:<16} {r['stem']}\n"
            f"{'':<17} rows={r['rows']}  slug-commits={r['slug_hits']}  "
            f"writes declared={r['declared']} on-disk={r['present']} "
            f"committed={r['committed']}"
        )
        if r.get("residue"):
            lines.append(
                f"{'':<17} UNENRICHED -- plan body still carries "
                f"{len(r['residue'])} scaffold placeholder(s); it will emit "
                "and then halt at preflight"
            )
    counts: dict[str, int] = {}
    for r in records:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    summary = "  ".join(f"{k}={v}" for k, v in sorted(counts.items()))
    lines.append(f"\n{len(records)} plans triaged: {summary}")
    lines.append(
        "Dispatch from 'candidate' -- rows declared writes and none are on "
        "disk. 'unmeasured' declared no writes, so nothing was measured and "
        "its state is UNKNOWN, not clean. 'suspect-*' means open it first."
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Rank plans by whether dispatching them would do work. Reports "
            "signal strength; never edits a plan and never writes a disposition."
        )
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Repo whose docs/plans/ to triage (default: this script's repo).",
    )
    parser.add_argument(
        "plans",
        nargs="*",
        help="Plan paths. Omitted means every docs/plans/*.md under --repo-root.",
    )
    parser.add_argument(
        "--only",
        default=None,
        help="Keep only this verdict (e.g. candidate, suspect-void).",
    )
    args = parser.parse_args(argv)

    try:
        _resolve_engine_root()
    except TriageError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    repo = Path(args.repo_root).resolve() if args.repo_root else _CLI_ROOT
    if not (repo / ".git").exists():
        print(f"not a git repo: {repo}", file=sys.stderr)
        return 2

    if args.plans:
        plans = [Path(p).resolve() for p in args.plans]
        missing = [p for p in plans if not p.is_file()]
        if missing:
            print(f"no such plan: {missing[0]}", file=sys.stderr)
            return 2
    else:
        plans = sorted((repo / "docs" / "plans").glob("*.md"))
        if not plans:
            print(f"no plans under {repo / 'docs' / 'plans'}", file=sys.stderr)
            return 2

    records = triage(repo, plans)
    if args.only:
        records = [r for r in records if r["verdict"] == args.only]
    print(_render(records))
    return 0


if __name__ == "__main__":
    sys.exit(main())
