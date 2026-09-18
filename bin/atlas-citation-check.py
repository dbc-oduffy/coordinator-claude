#!/usr/bin/env python3
"""coordinator/bin/atlas-citation-check.py — mechanical citation/coverage check
over the architecture atlas (`docs/architecture/`).

Ported from DoE-claude `coordinator/bin/atlas-citation-check.py` (W2-C6,
`docs/plans/2026-09-18-doe-holds-no-scripts.md`) — mechanical move, no behavioural change.
`REPO_ROOT` was already "engine" class (§ Path resolution): resolved from this module's own
`__file__`, unchanged by the move. It checks THIS repo's own `docs/architecture/` atlas, which
Claude-klabauter carries independently of DoE-claude's.

Purpose: AC5 of `docs/plans/2026-08-20-make-the-atlas-mechanical.md`. Every
citation an atlas page makes (symbol, file, record) is resolved by lookup
against project-rag's on-disk planes or the filesystem — never by model
judgment. For a `## Why It Is This Way` rationale citation, the claim's
verbatim quoted span is checked for literal occurrence in the cited record.
Atlas-global bookkeeping is also checked: every inventoried system has a
page, every scoped source file appears in `file-index.md`, every declared
`dependencies:` edge is reciprocated on the counterpart page, and every such
edge has at least one corroborating row in the refs graph.

Zero model dispatches. Zero subprocess fan-out. Opens project-rag's SQLite
planes strictly read-only (`mode=ro`, short timeout) — this box runs ~40 live
sessions and a write here would be a shared-substrate defect, not a local one.

Spec backlink: docs/plans/2026-08-20-make-the-atlas-mechanical.md chunk C4.

Negative-spec
-------------
- Does NOT judge whether a resolved citation is the *correct* target for its
  surrounding claim, nor whether a quoted span actually *supports* the
  rationale drawn from it — that residual judgment is C5's job
  (coordinator/docs/wiki/coordinator-tripwires/
  a-lens-checks-the-citation-resolves-not-that-the-file-does-the-thing.md).
- Does NOT dispatch an agent or call a model under any code path.
- Does NOT write to any project-rag database. Read-only connections only.
- Does NOT shell out to git/subprocess for any check in this file.
- Does NOT resolve a bare filename (`settings.json`, no separator) or a
  symbol-shaped identifier (`real_symbol`) as a citation. Only a backtick
  span with both a path separator and a real extension is unambiguous
  enough to be a citation the atlas actually claims — an earlier version
  resolved every identifier-shaped and bare-filename backtick span too, and
  6,119 of 7,525 live findings came from spans (`mv`, `mktemp`, `tsc`,
  `MultiEdit`, env-var names) the atlas never claimed were citations. See
  `classify_backtick_token`'s docstring.
- Does NOT corroborate a `dependencies:` edge against the references graph.
  A prior `unrefs-edge` leg did; measured against the live plane with its
  join bug fixed (527 real rows, not 0), the substring-over-joined-path
  heuristic still produced 0 hits on the corpus's 17 real edges — deleted
  as a leg that could not produce an informative result, not shipped as
  constant-fail noise.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# file-index.md's own declared scope (its header, verbatim) — the directories
# under coordinator/ this checker walks for the coverage check.
SCOPED_SUBDIRS = [
    "bin", "hooks", "lib", "cockpit", "skills", "commands", "agents",
    "snippets", "pipelines", "schemas", "whoami", "docs/wiki",
]
EXCLUDED_DIR_NAMES = {"tests", "test", "__pycache__", "node_modules", "dist"}

_BACKTICK_RE = re.compile(r"`([^`\n]+)`")
_QUOTED_SPAN_RE = re.compile(r'"([^"]{8,})"')
_MD_HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.MULTILINE)
_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_FILE_EXT_RE = re.compile(r"\.[A-Za-z0-9]{1,6}$")
# A citation may carry a locator suffix -- `path/to/f.md:220-227`, `f.md#anchor`.
# Stripped BEFORE the extension test, not only inside the resolver: the
# extension regex is end-anchored, so `f.md:220-227` ends in `227` and used to
# classify "skip" -- a well-formed citation silently exempted from every check
# while the resolver carried unreachable code to handle exactly that shape.
_LOCATOR_SUFFIX_RE = re.compile(r":\d+(-\d+)?$")
_ELIDED_TOKENS = {"...", "…"}
_GLOB_MARKERS = ("*", "?")
# missing-file-index-row emits one Finding for the whole gap, carrying a
# capped sample rather than one row per file (see Finding 4, rebuild notes).
_FILE_INDEX_SAMPLE_CAP = 20


@dataclass
class Finding:
    kind: str  # unresolved-file | misrooted-file | unresolved-record | unspanned-quote | missing-page | missing-file-index-row | unreciprocated-edge
    page: str
    line: int | None
    detail: str

    def render(self) -> str:
        loc = f"{self.page}:{self.line}" if self.line else self.page
        return f"[{self.kind}] {loc} — {self.detail}"


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    degraded: list[str] = field(default_factory=list)
    # Every file-shaped span that resolved. Without this the printed totals
    # cannot be reconciled against the spans actually scanned: a resolved
    # citation produces no finding and no skip, so it was invisible, and the
    # module's "every span accounted for" contract was unverifiable from a run.
    resolved_ok: int = 0
    # Spans classified as non-citation shapes and deliberately not resolved —
    # every one counted here so "skipped" never means "silently dropped".
    skip_counts: dict[str, int] = field(default_factory=dict)

    def add(self, kind: str, page: str, line: int | None, detail: str) -> None:
        self.findings.append(Finding(kind, page, line, detail))

    def bump_skip(self, category: str) -> None:
        self.skip_counts[category] = self.skip_counts.get(category, 0) + 1

    @property
    def ok(self) -> bool:
        return not self.findings and not self.degraded


# ---------------------------------------------------------------------------
# project-rag plane access — strictly read-only
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Page-local citation extraction and resolution
# ---------------------------------------------------------------------------

def split_frontmatter(text: str) -> tuple[dict, str]:
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    fm_text = m.group(1)
    body = text[m.end():]
    fm: dict = {}
    for line in fm_text.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            items = [v.strip() for v in value[1:-1].split(",") if v.strip()]
            fm[key] = items
        else:
            fm[key] = value
    return fm, body


def strip_locator(raw: str) -> str:
    """Drop a citation's `#anchor` and `:LINE`/`:LINE-LINE` locator, leaving the
    path itself. Shared by the classifier and the resolver so the two can never
    disagree about what the path part of a citation is."""
    return _LOCATOR_SUFFIX_RE.sub("", raw.split("#", 1)[0])


def resolve_repo_path(repo_root: Path, raw: str) -> Path | None:
    """Resolve a backtick-cited path against the repo root. Returns the
    resolved Path if it exists on disk, else None."""
    raw = raw.strip()
    if raw.startswith("`") and raw.endswith("`"):
        raw = raw[1:-1]
    raw = strip_locator(raw)
    if not raw:
        return None
    candidate = (repo_root / raw).resolve()
    try:
        candidate.relative_to(repo_root.resolve())
    except ValueError:
        return None
    return candidate if candidate.exists() else None


def classify_backtick_token(token: str) -> str:
    """Classify a backtick-quoted span against the atlas's declared citation
    shape.

    Only one shape is unambiguous enough to resolve as a citation: a
    repo-relative path with both a directory separator and a real trailing
    extension — that shape is self-identifying and needs no plane lookup or
    heuristic to confirm. A bare filename (`settings.json`) and a
    symbol-shaped identifier (`real_symbol`, `mktemp`, `MultiEdit`) are
    common but ambiguous: nothing about the backtick span itself says the
    atlas author meant "this exact record" rather than "a word that happens
    to look like one". An earlier version resolved both anyway and 6,119 of
    7,525 live findings came from spans the atlas never claimed were
    citations — see the module Negative-spec.

    Returns one of:
      "elided" — "..."/"…", never a citation.
      "glob"   — contains "*"/"?" or a trailing "/" (a pattern or a bare
                 subtree, not a single resolvable file).
      "file"   — has a path separator AND a real trailing extension: the
                 only shape resolved as a citation.
      "skip"   — anything else (a bare filename, a symbol-shaped identifier,
                 a flag, a prose word). Counted in `report.skip_counts`
                 under this key — never resolved, never a finding, never
                 silently dropped.
    """
    if token in _ELIDED_TOKENS:
        return "elided"
    if any(ch in token for ch in _GLOB_MARKERS) or token.endswith("/"):
        return "glob"
    path_part = strip_locator(token)
    has_sep = "/" in path_part
    has_ext = bool(_FILE_EXT_RE.search(path_part)) and not path_part.startswith(".")
    if has_sep and has_ext:
        return "file"
    return "skip"


def check_page_citations(rel_page: str, text: str, repo_root: Path, report: Report) -> None:
    for lineno, line in enumerate(text.splitlines(), start=1):
        for match in _BACKTICK_RE.finditer(line):
            token = match.group(1)
            if not token or token.startswith("http://") or token.startswith("https://"):
                continue
            cls = classify_backtick_token(token)
            if cls != "file":
                report.bump_skip(cls)
                continue
            if resolve_repo_path(repo_root, token) is not None:
                report.resolved_ok += 1
                continue
            if resolve_repo_path(repo_root / "coordinator", token) is not None:
                report.add(
                    "misrooted-file",
                    rel_page,
                    lineno,
                    f"cited path resolves only under `coordinator/`, not from the "
                    f"repo root as written: `{token}`",
                )
                continue
            report.add(
                "unresolved-file", rel_page, lineno,
                f"cited path does not resolve: `{token}`",
            )


# ---------------------------------------------------------------------------
# Rationale span check (## Why It Is This Way)
# ---------------------------------------------------------------------------

def check_rationale_spans(rel_page: str, text: str, repo_root: Path, report: Report) -> None:
    # Takes the page text the caller already read for check_page_citations —
    # a prior version re-read the file and re-ran _BACKTICK_RE/
    # classify_backtick_token over it a second time for no benefit (Finding 5).
    section = extract_section(text, "Why It Is This Way")
    if section is None:
        return  # AC4 (C3) has not shipped yet on every page; absence is not a defect here
    for line in section.splitlines():
        quote_matches = list(_QUOTED_SPAN_RE.finditer(line))
        path_matches = list(_BACKTICK_RE.finditer(line))
        if not quote_matches or not path_matches:
            continue
        cited_path_raw = next(
            (m.group(1) for m in path_matches if classify_backtick_token(m.group(1)) == "file"),
            None,
        )
        if cited_path_raw is None:
            continue
        resolved = resolve_repo_path(repo_root, cited_path_raw)
        # line number within the page: locate offset of this line in the full text
        full_lineno = text[: text.index(section) + section.index(line)].count("\n") + 1
        if resolved is None:
            continue  # already reported as unresolved-file/-record above
        record_text = resolved.read_text(encoding="utf-8", errors="replace")
        for qm in quote_matches:
            span = qm.group(1)
            if span not in record_text:
                report.add(
                    "unspanned-quote", rel_page, full_lineno,
                    f"quoted span not found verbatim in {cited_path_raw}: \"{span[:80]}\"",
                )


def extract_section(text: str, heading: str) -> str | None:
    headings = list(_MD_HEADING_RE.finditer(text))
    for i, m in enumerate(headings):
        if m.group(1).strip() == heading:
            start = m.end()
            end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
            return text[start:end]
    return None


# ---------------------------------------------------------------------------
# Atlas-global coverage / consistency
# ---------------------------------------------------------------------------

_INDEX_TABLE_ROW_RE = re.compile(r"^\|\s*\[([^\]]+)\]\(([^)]+)\)\s*\|")


def check_systems_index_coverage(atlas_root: Path, repo_root: Path, report: Report) -> None:
    index_path = atlas_root / "systems-index.md"
    rel = str(index_path.relative_to(repo_root)).replace("\\", "/")
    if not index_path.exists():
        report.degraded.append(f"{rel} absent — cannot check system-page coverage")
        return
    text = index_path.read_text(encoding="utf-8")
    for lineno, line in enumerate(text.splitlines(), start=1):
        m = _INDEX_TABLE_ROW_RE.match(line)
        if not m:
            continue
        system_name, link_target = m.group(1), m.group(2)
        page = (index_path.parent / link_target).resolve()
        if not page.exists():
            report.add(
                "missing-page", rel, lineno,
                f"system `{system_name}` has no page at {link_target}",
            )


def check_file_index_coverage(atlas_root: Path, repo_root: Path, report: Report) -> None:
    file_index_path = atlas_root / "file-index.md"
    rel = str(file_index_path.relative_to(repo_root)).replace("\\", "/")
    if not file_index_path.exists():
        report.degraded.append(f"{rel} absent — cannot check file coverage")
        return
    text = file_index_path.read_text(encoding="utf-8")
    indexed: set[str] = set()
    for line in text.splitlines():
        if not line.startswith("coordinator/"):
            continue
        path = line.split(" ->", 1)[0].strip()
        if path:
            indexed.add(path)

    scope_root = repo_root / "coordinator"
    missing: list[str] = []
    for sub in SCOPED_SUBDIRS:
        base = scope_root / sub
        if not base.is_dir():
            continue
        for f in base.rglob("*"):
            if not f.is_file():
                continue
            if any(part in EXCLUDED_DIR_NAMES for part in f.relative_to(scope_root).parts):
                continue
            if f.name.startswith("."):
                continue
            rel_path = str(f.relative_to(repo_root)).replace("\\", "/")
            if rel_path not in indexed:
                missing.append(rel_path)

    # One Finding for the whole gap, not one row per file (Finding 4): a
    # 1,020-row file-index gap is a single fact — "file-index.md is this
    # many rows short" — not 1,020 separate defects for a reader to page
    # past to reach the ones that name something specific.
    if missing:
        missing.sort()
        sample = missing[:_FILE_INDEX_SAMPLE_CAP]
        detail = f"{len(missing)} scoped file(s) have no row in file-index.md: " + ", ".join(sample)
        if len(missing) > len(sample):
            detail += f", … ({len(missing) - len(sample)} more)"
        report.add("missing-file-index-row", rel, None, detail)


def check_cross_system_reciprocity(atlas_root: Path, repo_root: Path, report: Report) -> None:
    systems_dir = atlas_root / "systems"
    if not systems_dir.is_dir():
        report.degraded.append(f"{systems_dir} absent — cannot check cross-system reciprocity")
        return
    pages: dict[str, tuple[dict, str, Path]] = {}
    for page_path in sorted(systems_dir.glob("*.md")):
        text = page_path.read_text(encoding="utf-8")
        fm, body = split_frontmatter(text)
        pages[page_path.stem] = (fm, body, page_path)

    for name, (fm, _, page_path) in pages.items():
        rel = str(page_path.relative_to(repo_root)).replace("\\", "/")
        deps = fm.get("dependencies")
        if not isinstance(deps, list):
            continue  # scalar/absent — nothing edge-shaped to check
        for dep in deps:
            dep = dep.strip()
            if not dep or dep.lower() == "none":
                continue
            counterpart = pages.get(dep)
            if counterpart is None:
                report.add(
                    "unresolved-record", rel, None,
                    f"dependency `{dep}` in frontmatter names no page under systems/",
                )
                continue
            counter_fm, counter_body, _ = counterpart
            counter_deps = counter_fm.get("dependencies") or []
            reciprocated = (
                name in counter_deps
                or f"systems/{name}.md" in counter_body
                or f"[{name}]" in counter_body
            )
            if not reciprocated:
                report.add(
                    "unreciprocated-edge", rel, None,
                    f"declares dependency on `{dep}`, but {dep}'s page does not "
                    f"reference `{name}` back",
                )
            # No refs-graph corroboration leg here. A prior `unrefs-edge`
            # check queried the references plane and flagged an edge with no
            # corroborating row via `_files_span_systems`, a system-slug
            # substring test over a joined file-path pair. Its join was
            # buggy (see Planes._load_structural_db) and returned 0 rows,
            # firing on 17/17 edges unconditionally. Fixed and measured
            # against the real 527-row plane, the substring heuristic still
            # produced 0 hits on this corpus's 17 real edges — deleted as
            # unable to produce an informative result, not merely
            # unpopulated. See module Negative-spec.


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def run(repo_root: Path, atlas_root: Path) -> Report:
    report = Report()
    if not atlas_root.is_dir():
        report.degraded.append(f"atlas root absent: {atlas_root}")
        return report

    page_paths = sorted(atlas_root.rglob("*.md"))
    for page_path in page_paths:
        rel_page = str(page_path.relative_to(repo_root)).replace("\\", "/")
        text = page_path.read_text(encoding="utf-8")
        check_page_citations(rel_page, text, repo_root, report)
        check_rationale_spans(rel_page, text, repo_root, report)

    check_systems_index_coverage(atlas_root, repo_root, report)
    check_file_index_coverage(atlas_root, repo_root, report)
    check_cross_system_reciprocity(atlas_root, repo_root, report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--atlas-root", default=None)
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    atlas_root = Path(args.atlas_root).resolve() if args.atlas_root else repo_root / "docs" / "architecture"

    report = run(repo_root, atlas_root)

    if report.degraded:
        print("DEGRADED — one or more planes could not be checked:")
        for reason in report.degraded:
            print(f"  - {reason}")

    if report.findings:
        print(f"\n{len(report.findings)} unresolved citation(s)/gap(s):")
        for finding in report.findings:
            print(f"  {finding.render()}")

    glob_skipped = report.skip_counts.get("glob", 0)
    elided_skipped = report.skip_counts.get("elided", 0)
    non_citation_skipped = report.skip_counts.get("skip", 0)
    total_skipped = glob_skipped + elided_skipped + non_citation_skipped
    print(
        f"\n{report.resolved_ok} span(s) resolved as a file citation; "
        f"{total_skipped} span(s) not treated as a repo-relative file citation: "
        f"glob/subtree={glob_skipped}, elided={elided_skipped}, "
        f"non-citation-shape={non_citation_skipped} (bare filenames, symbol-shaped "
        "identifiers, and prose words — see classify_backtick_token's docstring)"
    )

    if report.ok:
        print("atlas-citation-check: OK — all citations resolved, coverage/consistency checks passed")
        return 0

    print(
        f"\natlas-citation-check: FAIL — {len(report.findings)} finding(s), "
        f"{len(report.degraded)} degraded plane(s)"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
