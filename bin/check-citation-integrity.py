#!/usr/bin/env python3
"""coordinator/bin/check-citation-integrity.py -- ratchet gate over
`coordinator_core.citation_graph`'s resolution output.

Ported from DoE-claude `coordinator/bin/check-citation-integrity.py` (W2-C6,
`docs/plans/2026-09-18-doe-holds-no-scripts.md`). One path-resolution seam changes on arrival:
DoE's copy `sys.path`-inserted its sibling `coordinator/lib` directory and imported `citation_graph`
as a top-level module -- an "engine" class resolution that, in this engine, is simply
`coordinator_core.citation_graph` (moved to `coordinator_core/citation_graph.py` at W2-C3 of this
same plan), imported directly with no sys.path shim. `REPO_ROOT`/`DEFAULT_BASELINE_PATH` are
unchanged in shape: both still derive from `cg.REPO_ROOT`, which is itself `Path(__file__).
resolve().parents[1]` inside `coordinator_core/citation_graph.py` -- this engine's own root, not
DoE's. No `state/baselines/citation-integrity.json` exists in this repo yet (out of this chunk's
`writes:` scope, same as DoE's own C2 note below); this arrival's CLI degrades exactly as
documented -- a missing baseline is a deliberate no-op, not a crash or a wall of findings.

Purpose: `citation_graph.py` (chunk C1) answers "what is the corpus's
citation-resolution state right now" as pure data. This module is the
consumer that turns that data into a pass/fail gate: exit 0 when the tree's
violation set, WITHIN EACH CLASS, is a subset of that class's committed
baseline partition; exit non-zero, naming only the new violations, when it
is not. It never fixes anything and never stores the resolved graph -- see
`## Anti-scope` below.

Violation classes tracked by C2: `rot`, `ambiguous`, `dead_link` -- the
three `citation_graph.Verdict.status` values that name a citation genuinely
broken (as opposed to `live`, `cross_surface` -- real,
out-of-scope-for-this-ratchet -- or `home_relative`, never a repo path to
begin with).

C3 and C4 add three more classes, each its OWN partition, never merged into
an existing one:

  - `orphan` -- a wiki page with no inbound citation from any other wiki
    page, counted over ALL resolving citation forms (bare basename, pathed,
    markdown link) -- not markdown links alone. The links-only-vs-all-forms
    comparison that justified this was a one-time proof (see
    `citation-integrity.md`), not a standing figure -- this module carries
    no `links_only` recomputation in its default path.
  - `dead_end` -- a wiki page with no outbound citation to another wiki
    page, same all-forms counting. Listed ranked by INBOUND citation count
    (never byte size -- see `citation-integrity-tier-1.md` chunk C3 body:
    the corpus's two largest pages are 0.4% apart by size, a meaningless
    tie), most-referenced dead-ends first.
  - `guide_drift` -- a `DIRECTORY_GUIDE.md` row pointing at a file that does
    not exist. This is the only C4 figure that is gated; the guide's
    completeness percentage (pages absent from the guide entirely) is a
    plain count reported alongside it, not itself a violation identity, and
    is NOT baselined -- see `guide_drift` vs `absent_count` below.

A later chunk introducing a new violation CLASS adds only that class's own
partition to the baseline, in the same commit that introduces the gate
consuming it -- never touches an existing partition. See
`docs/plans/2026-08-30-citation-integrity-tier-1.md` chunks C2, C3, C4.

NOTE ON BASELINE SEEDING: this chunk's dispatch scope is exactly
`check-citation-integrity.py` + its test file -- it does NOT include
`state/baselines/citation-integrity.json`. The `orphan`/`dead_end`/
`guide_drift` partitions are therefore UNSEEDED in the committed baseline
as of this change; `diff_against_baseline`'s documented empty-baseline
behaviour means every current orphan/dead-end/dead-row will report as a
"new" violation until a follow-up seeds those three partitions via
`--emit-baseline` in the same commit that turns this gate live corpus-wide
-- do not run this CLI as a live gate before that seeding lands. Separately:
the CLI (`main()`, not the `run()` library call) treats an ENTIRELY ABSENT
baseline FILE at the resolved `--baseline` path as a deliberate no-op (exit
0, one stderr line) rather than diffing against an empty shell -- this is
what makes the gate a true no-op on a tree (e.g. an OSS mirror this script
percolated to one-way) that never received the baseline file at all,
instead of failing on every current violation.

## Baseline shape (class-partitioned)

`state/baselines/citation-integrity.json`:

    {
      "baseline_sha": "<the commit this baseline reflects -- an ancestry
          anchor for 'what was standing debt', NOT a guarantee that
          `--emit-baseline` against a clean checkout of this sha reproduces
          this file byte-for-byte; the identities may include edits made
          after this sha in the tree the baseline was actually captured
          from. See `test_baseline_sha_is_ancestor_of_head`.>",
      "wiki_file_count": <int, at that sha>,
      "partitions": {
        "<class-name>": {
          "count": <int>,
          "identities": ["<citing-file-relpath>:<raw-target>", ...]
        },
        ...
      }
    }

An "identity" is `f"{citing_file}:{raw_target}"` -- enough to
tell a NEW violation from a standing one, never the resolved graph itself
(see Anti-scope). `count` is `len(identities)`, carried redundantly so a
hand-edited baseline that drifts the two apart is visibly wrong rather than
silently trusted.

## Anti-scope

- Does NOT store the resolved graph -- no target paths, no `Verdict.matches`,
  nothing beyond the bare identity string above. A later change that starts
  caching resolutions here is out of scope; `test_citation_integrity_cli.py`
  asserts on this boundary directly.
- Does NOT fix any citation. The 133 rot citations are standing debt this
  gate makes visible and stops from regrowing; repairing them is a
  different chunk (C8).
- Does NOT resolve corpus root from cwd or a hardcoded path -- always from
  `__file__` (`coordinator_core.citation_graph.REPO_ROOT`), so the same
  invocation works from any cwd on Windows, macOS, or Linux.

Spec: `docs/plans/2026-08-30-citation-integrity-tier-1.md`, chunk C2.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

#: Deferred, not module-scope-imported: `coordinator_core.citation_graph` is a non-stdlib
#: dependency (`coordinator_core.warm.serve_classifier`'s module-body-inertness predicate), so
#: every runtime use below imports it locally, after ensuring `_REPO_ROOT` is on `sys.path`.
REPO_ROOT = _REPO_ROOT
#: Mirrors `coordinator_core.citation_graph.WIKI_ROOT` (`REPO_ROOT / "docs" / "wiki"`) without
#: importing that module at module scope -- both derive from the same `REPO_ROOT`.
WIKI_ROOT = REPO_ROOT / "docs" / "wiki"
DEFAULT_BASELINE_PATH = REPO_ROOT / "state" / "baselines" / "citation-integrity.json"


def _cg():
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    import coordinator_core.citation_graph as cg

    return cg


def __getattr__(name: str) -> object:
    """PEP 562 module `__getattr__` -- `module.cg` (the shape
    `test_arrival_check_citation_integrity.py` monkeypatches via `importlib.util.
    module_from_spec`) resolves here to `_cg()`'s import, without binding `cg` at module
    scope (a module-scope non-stdlib import per `coordinator_core.warm.serve_classifier`)."""
    if name == "cg":
        return _cg()
    raise AttributeError(f"module 'check-citation-integrity' has no attribute {name!r}")

#: The violation-shaped `Verdict.status` values C2's gate tracks.
#: `live` and `cross_surface` are not violations; `home_relative` names a
#: citation that was never a repo path to begin with, not rename rot.
VIOLATION_CLASSES: "tuple[str, ...]" = ("rot", "ambiguous", "dead_link")

#: C3's structural-health classes -- derived from the resolved graph, not
#: from a single `Verdict.status` value (see module docstring).
STRUCTURAL_CLASSES: "tuple[str, ...]" = ("orphan", "dead_end")

#: C4's index-drift class -- a `DIRECTORY_GUIDE.md` row naming a file that
#: does not exist. The guide's completeness percentage is a sibling figure,
#: reported but never baselined (see module docstring).
GUIDE_CLASSES: "tuple[str, ...]" = ("guide_drift",)

#: Every class this gate ratchets against, across all three chunks.
ALL_CLASSES: "tuple[str, ...]" = VIOLATION_CLASSES + STRUCTURAL_CLASSES + GUIDE_CLASSES

#: The `DIRECTORY_GUIDE.md` row pattern: a leading markdown-table cell
#: holding one markdown link to a `.md` file, e.g.
#: `| [some-page](some-page.md) | system | one-line |`.
_GUIDE_ROW_LINK = re.compile(r"^\|\s*\[[^\]\n]*\]\(([^)\n]+\.md)\)\s*\|")

#: The frontmatter `status:` key, bound to the fenced block by the caller
#: (`read_frontmatter_status`) -- never applied to a whole file, which
#: over-reports on this corpus by ~75% because body prose reuses the same
#: key (dispatch brief C4).
_FRONTMATTER_STATUS = re.compile(r"^status:\s*(.+?)\s*$", re.MULTILINE)


def citation_identity(verdict: "cg.Verdict") -> str:
    """The baseline's atomic unit: enough to tell a NEW violation from a
    standing one, and nothing about the resolved graph (Anti-scope).

    Deliberately carries NO line number. A line number makes every citation
    below an unrelated edit read as a brand-new violation -- a paragraph
    insertion reclassifies every downstream citation on the page as new
    (incident specifics: `citation-integrity.md`), which on a cadence is a
    gate that fires on every doc edit and teaches its readers to ignore it.
    The cost is a narrow blind spot: two violations to
    the SAME target in the SAME file collapse to one identity, so adding a
    second one goes unseen. A gate that cries wolf is worth less than that
    blind spot."""
    citation = verdict.citation
    try:
        rel = citation.citing_file.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        rel = citation.citing_file.as_posix()
    return f"{rel}:{citation.raw_target}"


def partition_current(report: "cg.CorpusReport") -> "dict[str, set[str]]":
    """Current violation identities, grouped by class -- only the classes in
    `VIOLATION_CLASSES`. Never includes `live`/`cross_surface`/`home_relative`."""
    out: "dict[str, set[str]]" = {cls: set() for cls in VIOLATION_CLASSES}
    for verdict in report.verdicts:
        if verdict.status in out:
            out[verdict.status].add(citation_identity(verdict))
    return out


def read_frontmatter_status(text: str) -> "str | None":
    """The frontmatter `status:` value, bound strictly to the leading `---`
    fence -- never a whole-file regex, which over-reports on this corpus by
    ~75% because body prose reuses the same key (dispatch brief C4). `None`
    if there's no leading fence, or no `status:` key inside it."""
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    fence = text[3:end]
    match = _FRONTMATTER_STATUS.search(fence)
    return match.group(1).strip() if match else None


def _relpath(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def wiki_live_edges(
    report: "cg.CorpusReport", wiki_root: Path, *, kinds: "tuple[str, ...]"
) -> "set[tuple[str, str]]":
    """`(citing_relpath, target_relpath)` pairs for every LIVE verdict whose
    citation kind is in `kinds` and whose resolved target is itself under
    `wiki_root` -- a `pathed`/`bare_basename` citation into a different
    tracked surface (cross_surface) never counts as a wiki-internal edge."""
    wiki_root_r = wiki_root.resolve()
    edges: "set[tuple[str, str]]" = set()
    for verdict in report.verdicts:
        if verdict.status != "live" or not verdict.matches:
            continue
        if verdict.citation.kind not in kinds:
            continue
        target = verdict.matches[0]
        try:
            target.resolve().relative_to(wiki_root_r)
        except ValueError:
            continue
        edges.add(
            (_relpath(verdict.citation.citing_file, wiki_root), _relpath(target, wiki_root))
        )
    return edges


def structural_health(
    report: "cg.CorpusReport", wiki_root: Path, wiki_files: "list[Path]"
) -> dict:
    """Orphan (no inbound edge) and dead-end (no outbound edge) reports over
    the corrected link graph -- counted across ALL resolving citation forms
    (bare basename, pathed, markdown link; wikilinks extract separately but
    resolve as bare_basename, see `citation_graph.py`). Dead-ends are ranked
    by INBOUND citation count, never byte size."""
    all_kinds = ("bare_basename", "pathed", "markdown_link")
    all_edges = wiki_live_edges(report, wiki_root, kinds=all_kinds)

    all_pages = {_relpath(p, wiki_root) for p in wiki_files}
    inbound_all = {page: 0 for page in all_pages}
    outbound_all = {page: 0 for page in all_pages}
    for citing, target in all_edges:
        if target in inbound_all:
            inbound_all[target] += 1
        if citing in outbound_all:
            outbound_all[citing] += 1

    orphans_all = sorted(page for page in all_pages if inbound_all[page] == 0)
    dead_ends_all = sorted(
        (page for page in all_pages if outbound_all[page] == 0),
        key=lambda page: (-inbound_all[page], page),
    )

    return {
        "orphans": orphans_all,
        "orphans_count": len(orphans_all),
        "dead_ends": dead_ends_all,
        "inbound_counts": inbound_all,
    }


def guide_rows(guide_text: str) -> "list[tuple[int, str]]":
    """`(line_no, target_relative_to_guide)` for every `DIRECTORY_GUIDE.md`
    row's markdown-link target."""
    rows = []
    for line_no, line in enumerate(guide_text.split("\n"), start=1):
        match = _GUIDE_ROW_LINK.match(line)
        if match:
            rows.append((line_no, match.group(1)))
    return rows


def guide_drift(wiki_root: Path, *, guide_relpath: str = "DIRECTORY_GUIDE.md") -> dict:
    """Two DISTINCT figures over `DIRECTORY_GUIDE.md`, per C4's split:

    - `dead_rows` -- rows pointing at a file that does not exist. GATED
      (its own baseline partition, `guide_drift`).
    - `absent_count`/`absent_pages` -- wiki pages the guide never mentions
      at all, a plain completeness figure. NOT gated, NOT baselined -- see
      module docstring for why (one-time figure, not a standing ratchet
      input). A page whose frontmatter `status:` is `deprecated` (read
      fence-bound, see `read_frontmatter_status`) is excluded from this
      count -- an intentionally-retired page is not a completeness gap.
    """
    guide_path = wiki_root / guide_relpath
    if not guide_path.is_file():
        return {"dead_rows": [], "absent_count": 0, "absent_pages": [], "guide_page_count": 0}

    guide_text = guide_path.read_text(encoding="utf-8")
    rows = guide_rows(guide_text)

    referenced: "set[str]" = set()
    dead_rows: "list[str]" = []
    for line_no, target in rows:
        candidate = (guide_path.parent / target).resolve()
        if candidate.is_file():
            try:
                referenced.add(_relpath(candidate, wiki_root))
            except ValueError:
                pass
        else:
            dead_rows.append(f"{guide_relpath}:{target}")

    tracked_pages: "set[str]" = set()
    for path in sorted(wiki_root.rglob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if read_frontmatter_status(text) == "deprecated":
            continue
        tracked_pages.add(_relpath(path, wiki_root))

    absent = sorted(tracked_pages - referenced)
    return {
        "dead_rows": dead_rows,
        "absent_count": len(absent),
        "absent_pages": absent,
        "guide_page_count": len(tracked_pages),
    }


def all_partitions_current(report: "cg.CorpusReport", wiki_root: Path) -> "dict[str, set[str]]":
    """Every gated class's current violation-identity set -- C2's citation
    classes plus C3's `orphan`/`dead_end` plus C4's `guide_drift`. Never
    includes the guide's `absent_count` figure -- that one is reported, not
    gated (see `guide_drift` docstring)."""
    current = partition_current(report)
    wiki_files = sorted(wiki_root.rglob("*.md"))
    health = structural_health(report, wiki_root, wiki_files)
    drift = guide_drift(wiki_root)
    current["orphan"] = set(health["orphans"])
    current["dead_end"] = set(health["dead_ends"])
    current["guide_drift"] = set(drift["dead_rows"])
    return current


def load_baseline(path: Path = DEFAULT_BASELINE_PATH) -> dict:
    """The committed baseline, or an empty class-partitioned shell if the
    file doesn't exist yet (first-run / pre-seed case)."""
    if not path.is_file():
        return {"baseline_sha": None, "wiki_file_count": 0, "partitions": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def baseline_identities(baseline: dict, cls: str) -> "set[str]":
    partition = baseline.get("partitions", {}).get(cls)
    if not partition:
        return set()
    return set(partition.get("identities", []))


def diff_against_baseline(
    current: "dict[str, set[str]]", baseline: dict
) -> "dict[str, list[str]]":
    """New violations per class -- only classes present in `current`
    (i.e. `VIOLATION_CLASSES`). A class absent from the baseline entirely
    (not yet seeded) is compared against an empty set, so every one of its
    current violations reports as new -- the correct behaviour for a class
    whose gate hasn't shipped yet, and the reason a later chunk must seed
    its own partition in the same commit that turns its gate on."""
    diffs: "dict[str, list[str]]" = {}
    for cls, identities in current.items():
        base = baseline_identities(baseline, cls)
        new = sorted(identities - base)
        if new:
            diffs[cls] = new
    return diffs


def build_baseline_payload(
    report: "cg.CorpusReport",
    wiki_root: Path = WIKI_ROOT,
    *,
    baseline_sha: "str | None" = None,
) -> dict:
    """A fresh class-partitioned baseline payload from a `CorpusReport` --
    used both by the CLI's `--emit-baseline` mode and by tests constructing
    a baseline from a synthetic report. Covers `ALL_CLASSES` (C2's citation
    classes plus C3's structural classes plus C4's `guide_drift`), never
    the guide's `absent_count` figure (reported, not baselined)."""
    current = all_partitions_current(report, wiki_root)
    partitions = {
        cls: {"count": len(identities), "identities": sorted(identities)}
        for cls, identities in current.items()
    }
    return {
        "baseline_sha": baseline_sha if baseline_sha is not None else report.git_sha,
        "wiki_file_count": report.wiki_file_count,
        "partitions": partitions,
    }


def _summary(
    report: "cg.CorpusReport", diffs: "dict[str, list[str]]", health: dict, drift: dict
) -> dict:
    return {
        "wiki_file_count": report.wiki_file_count,
        "git_sha": report.git_sha,
        "counts": report.counts(),
        "new_violation_counts": {cls: len(ids) for cls, ids in diffs.items()},
        "clean": not diffs,
        "orphans_count": health["orphans_count"],
        "dead_ends_count": len(health["dead_ends"]),
        "guide_dead_rows_count": len(drift["dead_rows"]),
        "guide_absent_count": drift["absent_count"],
        "guide_page_count": drift["guide_page_count"],
    }


def _human_report(
    report: "cg.CorpusReport",
    diffs: "dict[str, list[str]]",
    baseline: dict,
    current: "dict[str, set[str]]",
    drift: dict,
) -> str:
    lines = [
        f"citation-integrity: {report.wiki_file_count} wiki files @ "
        f"{report.git_sha or '<unknown sha>'} (baseline captured @ "
        f"{baseline.get('baseline_sha') or '<no baseline>'})",
    ]
    for cls in ALL_CLASSES:
        base_count = len(baseline_identities(baseline, cls))
        current_count = len(current.get(cls, ()))
        lines.append(f"  {cls}: {current_count} total (baseline: {base_count})")
    lines.append(
        "  evidentiary (one-time, not gated): guide completeness "
        f"{drift['guide_page_count'] - drift['absent_count']}/{drift['guide_page_count']} "
        f"wiki pages reachable from DIRECTORY_GUIDE.md ({drift['absent_count']} absent)"
    )
    if not diffs:
        lines.append("PASS -- no violation is new against the committed baseline.")
        return "\n".join(lines)
    lines.append("FAIL -- new violations against the committed baseline:")
    for cls, ids in sorted(diffs.items()):
        lines.append(f"  [{cls}] {len(ids)} new:")
        for identity in ids:
            lines.append(f"    {identity}")
    return "\n".join(lines)


def run(
    *,
    wiki_root: Path = WIKI_ROOT,
    repo_root: Path = REPO_ROOT,
    baseline_path: Path = DEFAULT_BASELINE_PATH,
) -> "tuple[int, dict, str]":
    """Scan, diff, and return `(exit_code, json_summary, human_report)` --
    pulled out of `main()` so tests can call it directly without going
    through argv/stdout."""
    report = _cg().scan_corpus(wiki_root=wiki_root, repo_root=repo_root)
    wiki_files = sorted(wiki_root.rglob("*.md"))
    health = structural_health(report, wiki_root, wiki_files)
    drift = guide_drift(wiki_root)
    baseline = load_baseline(baseline_path)
    current = partition_current(report)
    current["orphan"] = set(health["orphans"])
    current["dead_end"] = set(health["dead_ends"])
    current["guide_drift"] = set(drift["dead_rows"])
    diffs = diff_against_baseline(current, baseline)
    exit_code = 1 if diffs else 0
    return (
        exit_code,
        _summary(report, diffs, health, drift),
        _human_report(report, diffs, baseline, current, drift),
    )


def _git_dirty_paths(root: Path) -> "list[str] | None":
    """`git status --porcelain` paths, or `None` if git itself is
    unavailable (never treated as clean in that case -- caller refuses)."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    return [line[3:] for line in result.stdout.splitlines() if line.strip()]


def _git_head_sha(root: Path) -> "str | None":
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="print the machine-readable summary only")
    parser.add_argument(
        "--baseline",
        type=Path,
        default=DEFAULT_BASELINE_PATH,
        help="path to the class-partitioned baseline (default: state/baselines/citation-integrity.json)",
    )
    parser.add_argument(
        "--emit-baseline",
        action="store_true",
        help="print a fresh baseline payload for the current tree instead of diffing (used to (re)seed a partition from a clean checkout -- refuses on a dirty tree unless --i-know-the-tree-is-dirty is also passed; never run this against a live working tree with peer writes in flight)",
    )
    parser.add_argument(
        "--i-know-the-tree-is-dirty",
        action="store_true",
        help="opt out of --emit-baseline's dirty-tree refusal -- only for a caller who has manually confirmed no peer writes are citation-relevant",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help=argparse.SUPPRESS,  # test-only override for the dirty-tree check
    )
    args = parser.parse_args(argv)

    if args.emit_baseline:
        if not args.i_know_the_tree_is_dirty:
            dirty = _git_dirty_paths(args.repo_root)
            if dirty is None:
                print(
                    "check-citation-integrity: --emit-baseline refused -- could not "
                    "determine tree cleanliness (git unavailable); pass "
                    "--i-know-the-tree-is-dirty to override",
                    file=sys.stderr,
                )
                return 1
            if dirty:
                print(
                    "check-citation-integrity: --emit-baseline refused -- working tree "
                    "is dirty, so the emitted baseline would not reflect a reproducible "
                    "commit. Dirty paths:\n" + "\n".join(f"  {p}" for p in dirty) +
                    "\nPass --i-know-the-tree-is-dirty to override.",
                    file=sys.stderr,
                )
                return 1
        cg = _cg()
        report = cg.scan_corpus()
        payload = build_baseline_payload(report, cg.WIKI_ROOT, baseline_sha=_git_head_sha(REPO_ROOT))
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    if not args.baseline.is_file():
        # An unseeded baseline (e.g. an OSS mirror this script percolated to
        # one-way, which never received `state/baselines/citation-integrity.json`)
        # is a deliberate skip, not a failure: `load_baseline`'s empty-shell
        # fallback would otherwise report every current violation as NEW,
        # which is a wall of spurious failures on a tree that never asked
        # for this gate. See module docstring's NOTE ON BASELINE SEEDING.
        print(
            f"check-citation-integrity: no baseline at {args.baseline} -- skipping (no-op).",
            file=sys.stderr,
        )
        return 0

    exit_code, summary, human = run(baseline_path=args.baseline)
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(human)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
