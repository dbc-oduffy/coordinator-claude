# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""repo-census.py — language census + import-edge + cross-reference generator
for an arbitrary external repo.

NOT the same tool as `coordinator/bin/repomap/generate-repomap.py` ("repomap")
— see § Distinct from `repomap` below before reaching for either.

Purpose: subsumes the three shell pipelines (language census via `find | sed |
sort | uniq`, per-language import-edge extraction via `grep`, cross-reference
counting via `grep -rl | wc -l`) that DoE-claude's `pipelines/deep-research/
repo-research-internals.md` § Phase 1.5 formerly spelled out as copy-paste shell
shapes for the deep-research Pipeline B EM to retype. Ops belong in the claude-klabauter
engine, not in instruction-surface fences — see DoE-claude's
coordinator/docs/wiki/coordinator-tripwires.md (greppable token
NO-MULTI-LINE-SHELL-FENCE / SKILLS-CARRY-NO-CODE) and
coordinator/docs/wiki/invisible-doctrine.md § How we got here — six escalating
realizations ¶ 1 "The fence" (coordinator/CLAUDE.md retired 2026-07-27; the
original citation's other nested section, "Build For Someone Else's Machine",
is dropped here deliberately — it was unrelated nesting, not a lost pointer).

Unlike most `coordinator/bin/` entrypoints, repo-census does NOT operate on
THIS repo (or any repo claude-klabauter "owns") — its target is an arbitrary repository
this tool has never seen before, supplied as a positional argument, used by
the deep-research repo pipeline to scope specialist deep-reads on repos we do
not own. There is no dependency on `coordinator_core` (no trampoline) — this
is a pure, self-contained CLI.

Distinct from `repomap` (`coordinator/bin/repomap/generate-repomap.py`):
that tool builds a token-budgeted, PageRank-centrality + git-activity-ranked
Markdown map for LLM context injection into a repo WE OWN and have git
history for (it backs DoE-claude's project-orientation hook and update-docs
staleness banner). This tool has no git-activity signal, no token budget, and
no tree-sitter dependency — it emits a flat census + raw import-occurrence
counts + distinct-referencing-file counts, in JSON or human-readable form, for
a repo we have never seen and may have no git history intuition for. Reach
for `repomap` to orient an agent inside a repo we work in; reach for
`repo-census` to scope specialist deep-reads on a repo we don't.

Three phases, matching the three retired shell steps:
    Census    (was Step A: `find {repo} | sed 's/.*\\.//' | sort | uniq -c | ...`)
              Walks the tree in pure Python, honoring a best-effort .gitignore
              parse plus a fixed skip-list (.git/, node_modules/, venv/, common
              build artefacts) that the old `find | sed` pipeline did not
              respect — one reason it was a poor census on real repos.
    Edges     (was Step B's six-language grep table: Python, JS/TS, Go, Rust,
              C/C++, Java) Ranks import/dependency-statement targets by raw
              occurrence count for the top 2 languages by census (or a caller
              override).
    Cross-refs (was Step C: `grep -rl "{module}" | wc -l`) For the top-N most-
              imported modules per language, resolves a best-effort file path
              within the target repo and counts DISTINCT referencing files
              (not raw import-line count — matches the old `-l` dedup-by-file
              semantics).

Resolution is heuristic, not a language-aware import resolver (no venv/
node_modules/GOPATH consultation) — this tool never executes or imports code
from the target repo. It is scoping signal for a research pipeline, not a
build-system-accurate dependency graph.

Usage:
    repo-census.py <repo-path> [--json]
                           [--top-census N] [--top-edges N] [--top-cross-ref N]
                           [--languages LANG[,LANG...]]
                           [--max-files N] [--no-gitignore]

Exit codes:
    0 — OK (census/edges/cross-references written to stdout)
    2 — usage/argument error, or <repo-path> is not a directory

Spec backlink: coordinator/pipelines/deep-research/repo-research-internals.md
    § Phase 1.5 — Repomap Generation (DoE-claude)
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROG = "repo-census.py"

# ---------------------------------------------------------------------------
# Language registry — mirrors the six rows of the retired Step B grep table.
# ---------------------------------------------------------------------------

LANGUAGES = {
    "python": {".py"},
    "js_ts": {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"},
    "go": {".go"},
    "rust": {".rs"},
    "c_cpp": {".c", ".h", ".cpp", ".cc", ".cxx", ".hpp", ".hh"},
    "java": {".java"},
}

LANGUAGE_LABELS = {
    "python": "Python",
    "js_ts": "JS/TS",
    "go": "Go",
    "rust": "Rust",
    "c_cpp": "C/C++",
    "java": "Java",
}

_EXT_TO_LANGUAGE = {}
for _lang, _exts in LANGUAGES.items():
    for _ext in _exts:
        _EXT_TO_LANGUAGE[_ext] = _lang

# Skipped regardless of .gitignore — vendored/generated content that would
# otherwise dominate the census and edge-extraction on a huge repo.
DEFAULT_SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv",
    "env", ".tox", ".mypy_cache", ".pytest_cache", ".next", ".nuxt", "dist",
    "build", "target", "vendor", ".idea", ".vscode", ".gradle", "coverage",
    ".cache",
}

DEFAULT_MAX_FILES = 200_000


# ---------------------------------------------------------------------------
# .gitignore — best-effort, not full git-match-semantics.
#
# Reads every .gitignore under the walked tree and accumulates patterns,
# scoped to the directory the .gitignore lives in (a pattern from a nested
# .gitignore only applies under that subtree — mirrors git's actual scoping,
# not a flat merge). Supports the common subset: blank/comment lines, `!`
# negation, trailing-`/` directory-only markers, and glob wildcards via
# fnmatch. Does NOT implement `**` double-star semantics precisely — treated
# as a single wildcard segment, which over-matches in rare nested cases but
# never under-matches enough to silently admit vendor trees.
# ---------------------------------------------------------------------------


class GitignoreMatcher:
    def __init__(self):
        # list of (scope_dir_posix, pattern, is_negation, dir_only)
        self._rules = []

    def load(self, repo_root: Path):
        for gi_path in repo_root.rglob(".gitignore"):
            # Skip .gitignore files sitting inside a directory we'd already
            # prune anyway (e.g. a vendored node_modules/.gitignore).
            rel_parts = gi_path.relative_to(repo_root).parts[:-1]
            if any(p in DEFAULT_SKIP_DIRS for p in rel_parts):
                continue
            scope_dir = gi_path.parent.relative_to(repo_root).as_posix()
            if scope_dir == ".":
                scope_dir = ""
            try:
                text = gi_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for line in text.splitlines():
                line = line.rstrip()
                if not line or line.lstrip().startswith("#"):
                    continue
                negation = line.startswith("!")
                if negation:
                    line = line[1:]
                dir_only = line.endswith("/")
                if dir_only:
                    line = line[:-1]
                line = line.lstrip("/")
                if not line:
                    continue
                self._rules.append((scope_dir, line, negation, dir_only))

    def is_ignored(self, rel_posix_path: str, is_dir: bool) -> bool:
        ignored = False
        for scope_dir, pattern, negation, dir_only in self._rules:
            if dir_only and not is_dir:
                continue
            if scope_dir and not (
                rel_posix_path == scope_dir or rel_posix_path.startswith(scope_dir + "/")
            ):
                continue
            candidate = rel_posix_path
            if scope_dir:
                candidate = rel_posix_path[len(scope_dir) + 1:]
            name = candidate.rsplit("/", 1)[-1]
            if fnmatch.fnmatch(candidate, pattern) or fnmatch.fnmatch(name, pattern):
                ignored = not negation
        return ignored


# ---------------------------------------------------------------------------
# Phase: tree walk + census.
# ---------------------------------------------------------------------------


def walk_repo(repo_root: Path, respect_gitignore: bool, max_files: int):
    """Yield relative (posix) file paths under repo_root, skipping vendor dirs.

    Returns (file_list, truncated_bool).
    """
    matcher = None
    if respect_gitignore:
        matcher = GitignoreMatcher()
        matcher.load(repo_root)

    files = []
    truncated = False
    stack = [repo_root]
    while stack:
        current = stack.pop()
        try:
            entries = sorted(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            rel = entry.relative_to(repo_root).as_posix()
            if entry.is_dir():
                if entry.name in DEFAULT_SKIP_DIRS:
                    continue
                if matcher and matcher.is_ignored(rel, is_dir=True):
                    continue
                stack.append(entry)
            elif entry.is_file():
                if matcher and matcher.is_ignored(rel, is_dir=False):
                    continue
                files.append(rel)
                if len(files) >= max_files:
                    truncated = True
                    return files, truncated
    return files, truncated


def census(files: list[str]) -> Counter:
    counts = Counter()
    for f in files:
        ext = Path(f).suffix
        counts[ext if ext else "(no extension)"] += 1
    return counts


def dominant_languages(counts: Counter, override: list[str] | None) -> list[str]:
    if override:
        return [lang for lang in override if lang in LANGUAGES]
    lang_counts = Counter()
    for ext, n in counts.items():
        lang = _EXT_TO_LANGUAGE.get(ext)
        if lang:
            lang_counts[lang] += n
    return [lang for lang, _ in lang_counts.most_common(2)]


# ---------------------------------------------------------------------------
# Phase: import/dependency edge extraction, one extractor per language.
#
# Each extractor takes (repo_root, relpath) and yields raw module strings —
# one per import-statement occurrence (not deduped), matching the retired
# grep pipeline's "one match per line" semantics.
# ---------------------------------------------------------------------------

_PY_IMPORT_RE = re.compile(r"^\s*(?:from\s+([\w.]+)\s+import\b|import\s+([\w.,\s]+))")
_JS_FROM_RE = re.compile(r"""\bfrom\s+['"]([^'"]+)['"]""")
_JS_REQUIRE_RE = re.compile(r"""\brequire\(\s*['"]([^'"]+)['"]\s*\)""")
_GO_IMPORT_LINE_RE = re.compile(r'^\s*import\s+"([^"]+)"')
_GO_IMPORT_BLOCK_START_RE = re.compile(r"^\s*import\s+\(")
_GO_IMPORT_BLOCK_ENTRY_RE = re.compile(r'^\s*(?:\w+\s+)?"([^"]+)"')
_RUST_USE_RE = re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?use\s+([\w:]+)")
_CPP_INCLUDE_RE = re.compile(r'^\s*#include\s+"([^"]+)"')
_JAVA_IMPORT_RE = re.compile(r"^\s*import\s+(?:static\s+)?([\w.]+)\s*;")


def _read_lines(path: Path):
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []


def extract_python_edges(path: Path):
    for line in _read_lines(path):
        if line.lstrip().startswith("#"):
            continue
        m = _PY_IMPORT_RE.match(line)
        if not m:
            continue
        if m.group(1):
            yield m.group(1)
        elif m.group(2):
            for name in m.group(2).split(","):
                name = name.strip().split(" as ")[0].strip()
                if name:
                    yield name


def extract_js_ts_edges(path: Path):
    for line in _read_lines(path):
        for m in _JS_FROM_RE.finditer(line):
            yield m.group(1)
        for m in _JS_REQUIRE_RE.finditer(line):
            yield m.group(1)


def extract_go_edges(path: Path):
    in_block = False
    for line in _read_lines(path):
        if in_block:
            if line.strip() == ")":
                in_block = False
                continue
            m = _GO_IMPORT_BLOCK_ENTRY_RE.match(line)
            if m:
                yield m.group(1)
            continue
        if _GO_IMPORT_BLOCK_START_RE.match(line):
            in_block = True
            continue
        m = _GO_IMPORT_LINE_RE.match(line)
        if m:
            yield m.group(1)


def extract_rust_edges(path: Path):
    for line in _read_lines(path):
        m = _RUST_USE_RE.match(line)
        if m:
            yield m.group(1)


def extract_c_cpp_edges(path: Path):
    for line in _read_lines(path):
        m = _CPP_INCLUDE_RE.match(line)
        if m:
            yield m.group(1)


def extract_java_edges(path: Path):
    for line in _read_lines(path):
        m = _JAVA_IMPORT_RE.match(line)
        if m:
            yield m.group(1)


EXTRACTORS = {
    "python": extract_python_edges,
    "js_ts": extract_js_ts_edges,
    "go": extract_go_edges,
    "rust": extract_rust_edges,
    "c_cpp": extract_c_cpp_edges,
    "java": extract_java_edges,
}


def extract_edges(repo_root: Path, lang_files: list[str], lang: str):
    """Return list of (relpath, module_str) pairs for every import occurrence."""
    extractor = EXTRACTORS[lang]
    edges = []
    for relpath in lang_files:
        for module in extractor(repo_root / relpath):
            edges.append((relpath, module))
    return edges


# ---------------------------------------------------------------------------
# Phase: cross-reference resolution — module string -> best-effort file path.
# ---------------------------------------------------------------------------


def _index_by_suffix(files: list[str]):
    """Map each file to itself; lookups use endswith against this list.

    Kept as a flat list (not a trie) — repo sizes in scope for this tool
    (bounded by --max-files) make O(files) linear scan per module acceptable
    against a top-N (default 20) shortlist, and it avoids a bespoke index
    structure for a heuristic that is best-effort by design.
    """
    return files


def resolve_python(module: str, all_files: list[str]):
    candidate = module.replace(".", "/")
    for suffix in (candidate + ".py", candidate + "/__init__.py"):
        for f in all_files:
            if f == suffix or f.endswith("/" + suffix):
                return f
    return None


def resolve_java(module: str, all_files: list[str]):
    candidate = module.replace(".", "/") + ".java"
    for f in all_files:
        if f == candidate or f.endswith("/" + candidate):
            return f
    return None


def resolve_rust(module: str, all_files: list[str]):
    segment = module.split("::")[-1] if "::" in module else module
    for suffix in (segment + ".rs", segment + "/mod.rs"):
        for f in all_files:
            if f.endswith("/" + suffix) or f == suffix:
                return f
    return None


def resolve_basename(module: str, exts: set, all_files: list[str]):
    """Generic fallback: match on basename (last path segment) + a known ext.

    Used for Go (import-path last segment ~= package dir), C/C++ (#include
    "foo.h" is already a relative/basename-ish path), and JS/TS relative
    specifiers (./foo, ../bar/baz) where the leading path is importer-
    relative and not worth re-deriving here — basename match is the
    honestly-labeled heuristic, not a false-precision resolver.
    """
    base = module.rstrip("/").split("/")[-1]
    base = base.split(".")[0] if "." in base and Path(base).suffix in exts else base
    for f in all_files:
        stem = Path(f).stem
        name = Path(f).name
        if name == base or stem == base or f == module or f.endswith("/" + module):
            return f
    return None


def resolve_module(lang: str, module: str, all_files: list[str]):
    if lang == "python":
        return resolve_python(module, all_files)
    if lang == "java":
        return resolve_java(module, all_files)
    if lang == "rust":
        return resolve_rust(module, all_files)
    return resolve_basename(module, LANGUAGES[lang], all_files)


# ---------------------------------------------------------------------------
# Orchestration.
# ---------------------------------------------------------------------------


def build_repo_census(
    repo_root: Path,
    top_census: int,
    top_edges: int,
    top_cross_ref: int,
    language_override: list[str] | None,
    max_files: int,
    respect_gitignore: bool,
):
    all_files, walk_truncated = walk_repo(repo_root, respect_gitignore, max_files)
    counts = census(all_files)
    langs = dominant_languages(counts, language_override)

    edges_by_lang = {}
    cross_refs_by_lang = {}
    for lang in langs:
        lang_exts = LANGUAGES[lang]
        lang_files = [f for f in all_files if Path(f).suffix in lang_exts]
        edges = extract_edges(repo_root, lang_files, lang)
        edges_by_lang[lang] = edges

        line_counts = Counter(module for _, module in edges)
        top_modules = [m for m, _ in line_counts.most_common(top_cross_ref)]

        file_sets = defaultdict(set)
        for relpath, module in edges:
            file_sets[module].add(relpath)

        cross_refs = []
        for module in top_modules:
            resolved = resolve_module(lang, module, all_files)
            cross_refs.append(
                {
                    "module": module,
                    "resolved_path": resolved,
                    "referencing_files": len(file_sets[module]),
                }
            )
        cross_refs_by_lang[lang] = cross_refs

    return {
        "repo": str(repo_root),
        "file_count": len(all_files),
        "walk_truncated": walk_truncated,
        "census": [
            {"extension": ext, "count": n}
            for ext, n in counts.most_common(top_census)
        ],
        "dominant_languages": langs,
        "edges": {
            lang: [
                {"module": m, "count": n}
                for m, n in Counter(module for _, module in edges_by_lang[lang]).most_common(top_edges)
            ]
            for lang in langs
        },
        "cross_references": cross_refs_by_lang,
    }


# ---------------------------------------------------------------------------
# Rendering.
# ---------------------------------------------------------------------------


def render_human(result: dict) -> str:
    lines = []
    lines.append(f"Repo census — {result['repo']}")
    lines.append(f"Files scanned: {result['file_count']}" + (" (TRUNCATED)" if result["walk_truncated"] else ""))
    lines.append("")
    lines.append("== Language census (top {}) ==".format(len(result["census"])))
    for row in result["census"]:
        lines.append(f"  {row['count']:>8}  {row['extension']}")
    lines.append("")
    dom = ", ".join(LANGUAGE_LABELS.get(lang, lang) for lang in result["dominant_languages"])
    lines.append(f"Dominant language(s): {dom or '(none detected)'}")
    for lang in result["dominant_languages"]:
        label = LANGUAGE_LABELS.get(lang, lang)
        lines.append("")
        lines.append(f"== {label} — import/dependency edges (top {len(result['edges'][lang])}) ==")
        for row in result["edges"][lang]:
            lines.append(f"  {row['count']:>6}  {row['module']}")
        lines.append("")
        lines.append(f"== {label} — cross-references (top {len(result['cross_references'][lang])}) ==")
        for row in result["cross_references"][lang]:
            resolved = row["resolved_path"] or "(unresolved)"
            lines.append(f"  {row['referencing_files']:>4} files  {row['module']}  -> {resolved}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI.
# ---------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="Language census + import-edge + cross-reference generator for an arbitrary external repo.",
    )
    parser.add_argument("repo_path", help="path to the target repository")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--top-census", type=int, default=10, help="top-N extensions in the census (default 10)")
    parser.add_argument("--top-edges", type=int, default=40, help="top-N modules per language edge table (default 40)")
    parser.add_argument("--top-cross-ref", type=int, default=20, help="top-N modules to cross-reference (default 20)")
    parser.add_argument(
        "--languages",
        default=None,
        help="comma-separated override of dominant languages (choices: {}); default: auto top-2 by census".format(
            ",".join(sorted(LANGUAGES))
        ),
    )
    parser.add_argument("--max-files", type=int, default=DEFAULT_MAX_FILES, help="hard cap on files walked (default {})".format(DEFAULT_MAX_FILES))
    parser.add_argument("--no-gitignore", action="store_true", help="do not honor .gitignore patterns")

    args = parser.parse_args(argv)

    repo_root = Path(args.repo_path)
    if not repo_root.is_dir():
        sys.stderr.write(f"{PROG}: ERROR — not a directory: {args.repo_path}\n")
        return 2

    language_override = None
    if args.languages:
        language_override = [s.strip() for s in args.languages.split(",") if s.strip()]
        unknown = [lang for lang in language_override if lang not in LANGUAGES]
        if unknown:
            sys.stderr.write(
                "{}: ERROR — unknown language(s): {} (choices: {})\n".format(
                    PROG, ", ".join(unknown), ", ".join(sorted(LANGUAGES))
                )
            )
            return 2

    result = build_repo_census(
        repo_root=repo_root.resolve(),
        top_census=args.top_census,
        top_edges=args.top_edges,
        top_cross_ref=args.top_cross_ref,
        language_override=language_override,
        max_files=args.max_files,
        respect_gitignore=not args.no_gitignore,
    )

    if args.json:
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
    else:
        sys.stdout.write(render_human(result))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
