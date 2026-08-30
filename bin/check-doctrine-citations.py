# Unix shebang — see resolve-repo-path.py's header note: gen-launcher-shim.py's
# --ensure-unix mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD); this
# line is no longer regenerated but is kept for parity with its bin/ siblings.
"""check-doctrine-citations.py — refuse a doctrine citation that resolves to
nothing, or to more than one doctrine tree.

A doctrine document cited by repo-relative path (`docs/wiki/foo.md`) resolves
to nothing when the ceremony that reads it runs with cwd = a consumer repo,
and resolves to DIFFERENT content once both repos hold a same-named file. The
origin incident: two analysts concluded a cited wiki page "does not exist",
invented its content from sibling files, and reported success — nothing
errored, because nothing was asked to.

Mechanism (settled by the spike this CLI implements —
docs/research/spike-verdicts/2026-08-29-doctrine-document-citation-resolution.md,
prior art sphinx-doc/sphinx#7280 / intersphinx `nitpicky` mode): an explicit,
never-inferred prefix -> tree map. A citation carrying one of the recognized
disambiguating prefixes (`coordinator/`, `~/.claude/`) resolves ONLY against
the tree that prefix names — missing there is unresolvable, full stop, never
a fallback search of the other trees. A citation with no recognized prefix
(the common case — most citations in the wild are bare `docs/...` paths) is
checked against every registered tree; resolving in exactly one is fine,
resolving in zero is unresolvable, and resolving in more than one is
AMBIGUOUS. Ambiguity is a refusal, never a tiebreak — a reference that
silently resolves to the wrong project's document is worse than one that
fails outright, which is the whole argument upstream's #7280 already made.

Usage:
    check-doctrine-citations.py --corpus <dir> [--corpus <dir> ...]
        [--tree NAME=PATH ...] [--no-default-trees]
        [--consumer-root PATH] [--plugin-root PATH]

Exit 0: every citation found resolved to exactly one tree (or none were
  found). Exit 1: at least one citation is unresolvable or ambiguous — every
  offending citation is named, once, with its source file and the reason.

`--consumer-root PATH` answers the question this tool exists for: not
"does this citation resolve given the whole map" but "does it resolve from
where the agent actually stands." A citation is reported dead-from-consumer
when its literal text (prefix + core path) does not exist under PATH, but
DOES exist in a DoE tree — the 21-across-11-unique-paths bucket the spike
measured, and the list C4's memo carries downstream.

`--plugin-root PATH` overrides the `plugin_root` default tree entry, which a
`${CLAUDE_PLUGIN_ROOT}/`-anchored citation resolves against.

Illustrative forms (a glob metacharacter, a `{...}` template slot, a literal
`YYYY-MM-DD-` or `path/to/` segment, or an `<...>` angle placeholder) are
excluded from resolution, not counted as dangling — the census
(state/audits/2026-07-23-doctrine-doc-reference-resolution-census.md) broke
these out for the same reason: folding them into the dangling bucket
inflated it by ~40%, and at that false-positive rate the lint gets
suppressed rather than trusted. Excluded citations are counted and reported
in the summary line so the exclusion stays visible.

Negative-spec: does NOT spawn a subprocess per citation or per file (a single
`os.walk` + in-process regex scan of the corpus, and at most one
`resolve-repo-path.py` subprocess call per default tree, memoized). Does NOT
infer a winner when a bare citation resolves in more than one tree — it
reports both and exits non-zero. Does NOT silently skip a citation that
matches the scan pattern but sits in a fenced code block or comment; scope is
plain-text substring matching, matching the spike's own probe methodology.
Does NOT count an illustrative/placeholder form as dangling or ambiguous —
it is excluded and separately tallied, never silently dropped. Does NOT
silently narrow the candidate tree set when a default tree fails to resolve
(P1 fix) — a failed `doe-claude` resolution (unregistered shortname, stale
`repos.*` key, a transient subprocess failure) is named and forces a
non-zero exit, even with zero citation findings, rather than degrading to a
false-clean scan of whatever trees happened to resolve. Does NOT perform a
real filesystem `..` traversal when checking a `../../`-prefixed citation
against `--consumer-root` (P-nit fix) — such a citation always falls
through to the DoE-tree check instead of an unsafe path join. Does NOT scan
`tests/fixtures/` directories (an artifact read as an oracle, not a
doctrine citation a session is meant to follow) or any file other than
`*.md`/`*.template` — narrower than a bare `*` glob, wide enough to catch
every markdown-shaped template file.

A dated incident narrative belongs in the commit message. The docstring
carries the invariant the incident established, and names the commit only
where a reader would otherwise re-litigate the decision.

Anchoring supersedes existence: the rule worth enforcing is not "does this
bare `docs/...` citation happen to resolve" but "is this citation anchored
at all". A citation with NO explicit root anchor (`_CITATION_RE`'s `prefix`
group empty) is reported `unanchored` — the PRIMARY finding class —
regardless of whether it resolves uniquely on the machine running the lint;
eight filenames now collide between DoE's tree and claude-klabauter's own
(`baton-lifecycle.md`, `cockpit-contract.md`, `code-review.md`,
`cross-repo.md`, `guard-messaging.md`, `test-infrastructure.md`,
`write-confinement.md`, `plans/INDEX.md`), so a bare citation resolving
cleanly here can resolve to different content wherever else it is read, with
no error anywhere existence-checking would catch. `unresolvable`/`ambiguous`
existence-checking remains the SECONDARY class, run only against citations
that already carry an explicit anchor (`coordinator/`, `~/.claude/`,
`${CLAUDE_PLUGIN_ROOT}/`, `../../`, a bare `/`).

Recognized anchor forms and matching boundaries: `${CLAUDE_PLUGIN_ROOT}/` is
a harness-expanded, cwd-independent plugin-install-root anchor — a CORRECT
anchored form with its own `_CITATION_RE` alternative, mapped through
`_PREFIX_TREE_MAP` to a dedicated `plugin_root` tree (resolvable via
`--plugin-root PATH` or the `plugin_root` default tree entry). The bare
`snippets/`, `pipelines/`, and `templates/` core alternatives (alongside the
`docs/{wiki,decisions,plans,problems,research}/` ones) are the only
non-`docs/` classes recognized — the doc-bearing directories an agent is
told to READ; `hooks/`, `bin/`, `state/` and friends name code and data
paths, where matching an incidental mention would trade a silent skip for
noise. A `(?<![\\w-])` lookbehind gates the whole core alternation so a path
segment merely ending in one of those words (`custom_snippets/foo.md`,
`ci-templates/bar.md`) is never mistaken for a citation. The core also
refuses a `.md` immediately followed by a further extension segment (a
`(?!\\.?[A-Za-z0-9])` negative lookahead) — `templates/CLAUDE.md.tmpl` and
`docs/wiki/foo.mdx` both name something other than the document, so neither
backtracks to a truncated `.md` match; ordinary trailing punctuation
(`docs/wiki/x.md.`, `..., x.md,`) still terminates a citation correctly.

Negative-spec gotcha: `${CLAUDE_PLUGIN_ROOT}` resolves to the plugin INSTALL
directory, not the repo root — for a marketplace source of `./plugin` that
is `<repo>/plugin`, not `<repo>/`; DoE-claude's own shipped citations resolve
it against the `coordinator/` subtree, which is why the default `plugin_root`
tree entry mirrors `doe_coordinator` rather than the bare repo root. Do NOT
assume plugin root == repo root elsewhere.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import re
import sys
from dataclasses import dataclass, field

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Citation shapes measured live by the spike's probe 3 regex, reproduced
# here verbatim as the recognized prefix set. Each entry maps the LITERAL
# leading text of a citation to the single tree name it disambiguates to.
# `_tree_for_prefix` does an exact `.get()` against the prefix text
# `_CITATION_RE` already extracted, so THIS dict's insertion order is
# irrelevant. If longest-alternative-first care is ever needed, it belongs
# to `_CITATION_RE`'s own alternation, not this map.
_PREFIX_TREE_MAP: dict[str, str] = {
    "coordinator/": "doe_coordinator",
    "~/.claude/": "doe_root",
    "${CLAUDE_PLUGIN_ROOT}/": "plugin_root",
}

_CITATION_RE = re.compile(
    r"""(?P<prefix>coordinator/|~/\.claude/|\$\{CLAUDE_PLUGIN_ROOT\}/|\.\./\.\./|(?:^|(?<=\s))/)?
        (?P<core>(?<![\w-])(?:docs/(?:wiki|decisions|plans|problems|research)|snippets|pipelines|templates)/[^\s\)\]"'<>]+\.md)
        (?!\.?[A-Za-z0-9])
    """,
    re.VERBOSE,
)
# The bare "/" (absolute-path) alternative is gated on start-of-line or a
# preceding whitespace char -- WITHOUT this gate a regex search finds the
# leftmost position where prefix+core can match, and a "/" immediately
# preceding "docs/" for an unrelated reason (a closing `>` of an
# `<other-placeholder>` form, a `}` boundary of an unrecognized variable
# expansion, any punctuation) gets silently mis-captured as a deliberate
# absolute-path anchor. That is the SAME misparse class the
# `${CLAUDE_PLUGIN_ROOT}/` fix corrects, generalized: `<resolved-engine-root>/
# docs/wiki/uninstall-agentic-judgment.md` (coordinator/commands/uninstall.md)
# is not an anchored citation -- `<resolved-engine-root>` is not a recognized
# anchor prefix -- yet without this gate its trailing "/" resolved cleanly
# against the claude-klabauter default tree and the citation was silently never
# reported as unanchored.

# Matches the census's own definition (state/audits/2026-07-23-doctrine-doc-
# reference-resolution-census.md § headline: "Illustrative placeholders
# (YYYY-MM-DD-, foo.md, path/to/... )") — a glob metacharacter, a `{...}`
# template slot, a literal `YYYY-MM-DD-`/`path/to/` segment, or an `<...>`
# angle placeholder. Tested against the full matched text (prefix + core).
_ILLUSTRATIVE_RE = re.compile(r"[*?{}<>]|YYYY-MM-DD-|path/to/", re.IGNORECASE)


def _is_illustrative(full_text: str) -> bool:
    return bool(_ILLUSTRATIVE_RE.search(full_text))


_DOE_TREE_NAMES = ("doe_root", "doe_coordinator")

_DEFAULT_TREE_SHORTNAMES: dict[str, tuple[str, str]] = {
    # tree name -> (repo shortname for resolve-repo-path.py, subpath under it)
    "doe_root": ("doe-claude", ""),
    "doe_coordinator": ("doe-claude", "coordinator"),
    # Sensible default only: DoE-claude's shipped plugin happens to install
    # from its `coordinator/` subtree, so this default mirrors
    # `doe_coordinator`. It is NOT a general "plugin root == this subpath"
    # assumption -- a caller whose plugin installs elsewhere overrides via
    # `--plugin-root PATH`, which replaces this entry outright.
    "plugin_root": ("doe-claude", "coordinator"),
    "claude-klabauter": ("claude-klabauter", ""),
}


@dataclass
class Citation:
    core_path: str
    prefix: str
    source_file: str
    line_no: int


@dataclass
class Finding:
    citation: Citation
    reason: str  # "unresolvable" | "ambiguous" | "dead-from-consumer"
    candidate_trees: list[str] = field(default_factory=list)


_RESOLVE_REPO_PATH_MODULE = None


def _load_resolve_repo_path_module():
    """Load resolve-repo-path.py as an in-process module, memoized at module
    scope for the life of the interpreter — never re-imported per shortname,
    never re-imported per run.

    resolve-repo-path.py is a hyphenated sibling script (not a valid Python
    module name), so it cannot be `import`-ed directly; this is the same
    `importlib.util.spec_from_file_location` pattern this file's own test
    module (test_check_doctrine_citations.py) already uses to load THIS
    file. No `sys.path` mutation, no `sys.modules` registration under a
    name another import could collide with."""
    global _RESOLVE_REPO_PATH_MODULE
    if _RESOLVE_REPO_PATH_MODULE is not None:
        return _RESOLVE_REPO_PATH_MODULE
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resolve-repo-path.py")
    spec = importlib.util.spec_from_file_location("_check_doctrine_citations_rrp", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _RESOLVE_REPO_PATH_MODULE = module
    return module


def _resolve_repo_path_shortname(shortname: str) -> tuple[str, str]:
    """In-process call into resolve-repo-path.py's own registry resolver.
    Returns (resolved_path, error_message) — error_message is "" on success.

    Negative-spec: does NOT spawn a `python <script>` subprocess to reach
    resolve-repo-path.py's resolution logic — that shape (an unnamed
    shell-out, absent from docs/reference/shell-out-carve-outs.md's closed
    list) doubled this tool's process-creation cost for zero behavioural
    gain, since resolve-repo-path.py's own registry read
    (`_resolve_registry_value`) is a plain in-process function once its
    module is loaded. The ONE subprocess resolve-repo-path.py itself still
    spawns (the machine-local CLI, to read the actual [repos] registry
    value) is untouched — that spawn reads real data this tool cannot get
    any other way, which is the shell-out-carve-outs distinction between
    "unnamed convenience shell-out" and "the one process that does the
    actual work". Do NOT reintroduce a `subprocess.run([sys.executable,
    ...])` wrapper here for convenience; import the module instead.

    resolve-repo-path.py's own contract is FAIL-LOUD-SKIP: an unregistered
    shortname is a legitimate empty-result skip, distinct from a genuine
    module-load failure. From THIS tool's perspective that distinction does
    not matter — either way a default tree this run was supposed to scan
    did not resolve, and P1's fix (see `_default_tree_roots`) is to make
    that visible rather than silently narrowing the candidate set."""
    try:
        rrp = _load_resolve_repo_path_module()
    except Exception as exc:
        return "", f"resolve-repo-path.py failed to load in-process: {exc}"
    normalized = shortname.replace("-", "_")
    key = f"repos.{normalized}"
    resolved = rrp._resolve_registry_value(key)
    if not resolved:
        return "", "resolve-repo-path.py resolved empty (unregistered shortname or empty repos.* key)"
    return resolved, ""


def _default_tree_roots() -> tuple[dict[str, str], list[tuple[str, str]]]:
    """Returns (roots, failures) — failures is [(tree_name, error_message)]
    for every default tree that did not resolve. The caller decides whether
    a failure is fatal (it is, unless a --tree override fills the gap)."""
    roots: dict[str, str] = {}
    failures: list[tuple[str, str]] = []
    resolved_shortnames: dict[str, tuple[str, str]] = {}
    for tree_name, (shortname, subpath) in _DEFAULT_TREE_SHORTNAMES.items():
        if shortname == "claude-klabauter":
            base, err = _REPO_ROOT, ""
        else:
            if shortname not in resolved_shortnames:
                resolved_shortnames[shortname] = _resolve_repo_path_shortname(shortname)
            base, err = resolved_shortnames[shortname]
        if err or not base:
            failures.append((tree_name, err or "resolved empty"))
            continue
        roots[tree_name] = os.path.join(base, subpath) if subpath else base
    return roots, failures


def _parse_tree_overrides(pairs: list[str]) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for pair in pairs:
        if "=" not in pair:
            raise ValueError(f"--tree expects NAME=PATH, got: {pair}")
        name, path = pair.split("=", 1)
        name = name.strip()
        if not name:
            raise ValueError(f"--tree expects NAME=PATH, got: {pair}")
        overrides[name] = path
    return overrides


def _unscannable_corpus_dirs(corpus_dirs: list[str]) -> list[tuple[str, str]]:
    """Return (path, reason) for every corpus argument that cannot be walked.

    Negative spec: a corpus path that does not exist, or names a file rather than a
    directory, must NEVER reach the scan as an empty contribution.  os.walk() yields
    nothing for both and raises nothing, so the run would report a clean corpus it
    never opened -- the same silent-skip this tool exists to refuse, committed by the
    tool itself.  Callers treat a non-empty return as fatal before any scanning.
    """
    unscannable: list[tuple[str, str]] = []
    for corpus_dir in corpus_dirs:
        if not os.path.exists(corpus_dir):
            unscannable.append((corpus_dir, "does not exist"))
        elif not os.path.isdir(corpus_dir):
            unscannable.append((corpus_dir, "is a file, not a directory"))
    return unscannable


def _is_test_fixture_dir(dir_path: str) -> bool:
    """True when `dir_path` is literally named `fixtures` directly under a
    directory literally named `tests` -- narrower than excluding all of
    `tests/`, so a genuine doctrine citation embedded in test prose is still
    scanned. Matches skills/learn-lessons/tests/fixtures/lesson-triage/
    expected-manifest.yaml's shape: an artifact read as an oracle, not a
    citation a session is meant to follow."""
    normalized = dir_path.replace("\\", "/").rstrip("/")
    if os.path.basename(normalized) != "fixtures":
        return False
    parent = os.path.dirname(normalized)
    return os.path.basename(parent) == "tests"


def _iter_corpus_files(corpus_dirs: list[str]):
    for corpus_dir in corpus_dirs:
        for root, dirs, files in os.walk(corpus_dir):
            if _is_test_fixture_dir(root):
                dirs[:] = []
                continue
            dirs[:] = [d for d in dirs if not _is_test_fixture_dir(os.path.join(root, d))]
            for name in files:
                if name.endswith(".md") or name.endswith(".template"):
                    yield os.path.join(root, name)


def _extract_citations(path: str) -> tuple[list[Citation], int]:
    """Returns (citations, illustrative_excluded_count).

    Dedup happens HERE, at extraction, on `(line_no, prefix, core)` --
    never downstream in a per-branch finding-emission pass. A markdown
    self-link (`[docs/wiki/x.md](docs/wiki/x.md)`) makes `_CITATION_RE`
    match the identical citation site twice on one line: once in the link
    text, once in the link target. Both matches name the same document at
    the same source line -- one citation appearing twice on a line is one
    citation, not two -- so deduping the raw match stream before a single
    Citation object is ever created is the point in the pipeline where
    "one finding per citation site" is true by construction for every
    downstream consumer (find_unanchored, resolve_citations,
    find_dead_from_consumer) and for the illustrative `excluded` tally,
    rather than needing the same dedup repeated in each branch
    separately. First-occurrence order is preserved -- `seen` only
    suppresses a repeat, it never reorders what already appeared.
    """
    citations: list[Citation] = []
    excluded = 0
    seen: set[tuple[int, str, str]] = set()
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError:
        return citations, excluded
    for line_no, line in enumerate(lines, start=1):
        for match in _CITATION_RE.finditer(line):
            prefix = match.group("prefix") or ""
            core = match.group("core")
            key = (line_no, prefix, core)
            if key in seen:
                continue
            seen.add(key)
            # Illustrative-ness is checked on `core` alone, never `prefix`:
            # a recognized anchor prefix is already known-good text, and
            # `${CLAUDE_PLUGIN_ROOT}/` legitimately contains `{`/`}` -- the
            # very characters `_ILLUSTRATIVE_RE` uses to catch a `{...}`
            # template slot in the CORE path. Folding prefix into the check
            # would make every plugin-root-anchored citation excluded as
            # illustrative rather than scanned.
            if _is_illustrative(core):
                excluded += 1
                continue
            citations.append(Citation(core_path=core, prefix=prefix, source_file=path, line_no=line_no))
    return citations, excluded


def _tree_for_prefix(prefix: str) -> str | None:
    return _PREFIX_TREE_MAP.get(prefix)


def _is_anchored(citation: Citation) -> bool:
    """Shared "does this citation carry an explicit root anchor" question --
    the one `find_unanchored` asks. An anchored citation (`coordinator/`,
    `~/.claude/`, `${CLAUDE_PLUGIN_ROOT}/`, `../../`, a bare `/`) is answered
    by its anchor and is never a candidate for `find_unanchored`'s findings
    on the strength of anchoring alone -- the question that function asks
    ("does this have an anchor") is already satisfied. This is deliberately
    NOT the question `find_dead_from_consumer` asks (see
    `_resolves_cwd_independently` below): most anchors, `coordinator/`
    included, are relative-to-some-repo-root text that a consumer-cwd check
    is exactly right to interrogate -- only a harness-expanded anchor is
    exempt from that check, not every anchored form."""
    return bool(citation.prefix)


# The subset of `_PREFIX_TREE_MAP`'s keys that the HARNESS expands to a fixed
# absolute location before a shell/reader ever sees the citation text --
# cwd-independent by construction, distinct from an anchor like `coordinator/`
# that is merely relative-to-some-repo-root (exactly what `--consumer-root`
# mode exists to interrogate). `${CLAUDE_PLUGIN_ROOT}/` is the one form that
# qualifies today; a future harness-expanded anchor form is added here, not
# by duplicating this reasoning at each call site.
_CWD_INDEPENDENT_PREFIXES: frozenset[str] = frozenset({"${CLAUDE_PLUGIN_ROOT}/"})


def _resolves_cwd_independently(citation: Citation) -> bool:
    """The question `find_dead_from_consumer` asks, and the only one it
    asks about anchoring: is this citation's root already fixed regardless
    of the reading agent's cwd. True only for `_CWD_INDEPENDENT_PREFIXES`
    members -- an anchor like `coordinator/` is NOT cwd-independent (its
    whole meaning is "relative to whichever repo root"), so it stays a
    `find_dead_from_consumer` candidate exactly as an unanchored citation
    does. Sharing `_PREFIX_TREE_MAP`'s prefix vocabulary (rather than
    inventing a second prefix literal here) is what keeps a future anchor
    form's cwd-independence a one-place decision -- add it to
    `_CWD_INDEPENDENT_PREFIXES` and both this function and
    `_tree_for_prefix`'s caller already agree on its identity."""
    return citation.prefix in _CWD_INDEPENDENT_PREFIXES


def find_unanchored(citations: list[Citation], tree_roots: dict[str, str]) -> list[Finding]:
    """PRIMARY finding class (supersedes plain existence-checking): a
    citation with no explicit root anchor is reported regardless of whether
    it happens to resolve uniquely on the machine running the lint. Eight
    filenames now collide between DoE's tree and claude-klabauter's own, so a bare
    `docs/...` citation that resolves cleanly here can resolve to different
    content wherever else it is read, with no error anywhere
    existence-checking alone would catch. `candidate_trees` is carried
    through for diagnostic value only (which tree(s) it happens to resolve
    in on this run) -- it never changes whether the citation is flagged.

    Negative-spec: does NOT consult `_tree_for_prefix` or attempt to
    disambiguate -- an unanchored citation is flagged on the sole fact of
    having an empty `prefix`, never on the outcome of a resolution attempt."""
    findings: list[Finding] = []
    for citation in citations:
        if _is_anchored(citation):
            continue
        matches = [
            tree_name
            for tree_name, root in tree_roots.items()
            if os.path.isfile(os.path.join(root, citation.core_path))
        ]
        findings.append(Finding(citation, "unanchored", sorted(matches)))
    return findings


def resolve_citations(citations: list[Citation], tree_roots: dict[str, str]) -> list[Finding]:
    """SECONDARY finding class: existence/ambiguity checking, run only
    against citations that already carry an explicit anchor. A citation with
    no prefix is skipped here entirely -- it is `find_unanchored`'s to
    report, not this function's, so an unanchored citation is never
    double-reported under both reasons."""
    findings: list[Finding] = []
    for citation in citations:
        if not citation.prefix:
            continue
        mapped_tree = _tree_for_prefix(citation.prefix)
        if mapped_tree is not None:
            root = tree_roots.get(mapped_tree)
            exists = bool(root) and os.path.isfile(os.path.join(root, citation.core_path))
            if not exists:
                findings.append(Finding(citation, "unresolvable", [mapped_tree]))
            continue

        matches = [
            tree_name
            for tree_name, root in tree_roots.items()
            if os.path.isfile(os.path.join(root, citation.core_path))
        ]
        if not matches:
            findings.append(Finding(citation, "unresolvable", list(tree_roots)))
        elif len(matches) > 1:
            findings.append(Finding(citation, "ambiguous", sorted(matches)))
    return findings


def _contains_dotdot_segment(literal_path: str) -> bool:
    return any(part == ".." for part in re.split(r"[\\/]", literal_path))


def find_dead_from_consumer(citations: list[Citation], tree_roots: dict[str, str], consumer_root: str) -> list[Finding]:
    """The consumer-cwd leg: not "does this resolve given the whole map" but
    "does it resolve from where the agent actually stands." A citation's
    LITERAL text (prefix + core path, exactly as an agent at `consumer_root`
    would read it) is checked against `consumer_root` first — resolving
    there means it is correct as written and not reported. Failing there, it
    is reported dead-from-consumer only if it resolves in a DoE tree (never
    against the claude-klabauter/consumer tree entry, which is the question already
    answered by the first check).

    A citation that resolves cwd-independently (`_resolves_cwd_independently`
    true -- `${CLAUDE_PLUGIN_ROOT}/` today) is excluded from this mode
    entirely, before the literal-text check runs: such an anchor is
    harness-expanded to a fixed root before a shell ever sees it, which is
    exactly the property this mode's "does it resolve from where the agent
    stands" question is asking about. Testing `consumer_root + prefix +
    core_path` for such a citation was previously meaningless (the joined
    path is not how the citation is ever actually resolved), and reproduced
    the same false-positive class this file's `${CLAUDE_PLUGIN_ROOT}/`
    misparse fix already corrected for `find_unanchored`/`resolve_citations`
    -- the same defect surviving in a second code path, not a separate one.
    A merely-anchored-but-relative citation (`coordinator/`, `~/.claude/`)
    is NOT exempt -- its whole meaning is relative to some repo root, which
    is precisely what a consumer-cwd check exists to interrogate, so it
    remains a candidate here exactly as an unanchored citation does.

    A `../../`-prefixed citation (the census counted 5 of this shape) is
    NEVER joined onto `consumer_root` for the literal-existence check: doing
    so performs a genuine filesystem `..` traversal that can escape
    `consumer_root` and match an unrelated file, silently flipping the
    verdict. Such a citation always falls through to the DoE-tree check
    below instead — the traversal is real on disk but this tool never
    resolves relative to a citing file's own directory, so there is no
    correct join to perform; skipping the literal check is the safe read,
    not a coincidental one."""
    findings: list[Finding] = []
    doe_roots = {name: tree_roots[name] for name in _DOE_TREE_NAMES if tree_roots.get(name)}
    for citation in citations:
        if _resolves_cwd_independently(citation):
            continue
        literal_path = citation.prefix + citation.core_path
        if not _contains_dotdot_segment(literal_path) and os.path.isfile(os.path.join(consumer_root, literal_path)):
            continue
        doe_matches = [
            tree_name for tree_name, root in doe_roots.items() if os.path.isfile(os.path.join(root, citation.core_path))
        ]
        if doe_matches:
            findings.append(Finding(citation, "dead-from-consumer", sorted(doe_matches)))
    return findings


def _format_finding(finding: Finding) -> str:
    loc = f"{finding.citation.source_file}:{finding.citation.line_no}"
    cited = f"{finding.citation.prefix}{finding.citation.core_path}"
    if finding.reason == "unanchored":
        trees = ", ".join(finding.candidate_trees) if finding.candidate_trees else "nowhere"
        return f"{loc}: unanchored citation '{cited}' — no explicit root anchor (resolves in: {trees})"
    if finding.reason == "ambiguous":
        trees = ", ".join(finding.candidate_trees)
        return f"{loc}: ambiguous citation '{cited}' resolves in trees: {trees}"
    if finding.reason == "dead-from-consumer":
        trees = ", ".join(finding.candidate_trees)
        return f"{loc}: dead-from-consumer citation '{cited}' (resolves only in: {trees})"
    return f"{loc}: unresolvable citation '{cited}'"


def run(
    corpus_dirs: list[str],
    tree_overrides: dict[str, str],
    use_default_trees: bool,
    consumer_root: str | None = None,
    plugin_root: str | None = None,
) -> tuple[int, list[str], int, int]:
    """Returns (exit_code, finding_lines, illustrative_excluded_count,
    unresolved_default_tree_count).

    P1 fix: a default tree that failed to resolve (unregistered shortname,
    stale repos.* key, a transient resolve-repo-path.py subprocess failure)
    is NEVER silently dropped from the candidate set — that degraded mode
    is exactly the failure this lint exists to catch, reproduced inside the
    lint itself (fewer trees to check against -> fewer possible misses/
    ambiguities -> a false-clean exit 0). A `--tree` override for the same
    name still fills the gap deliberately; only a tree left genuinely absent
    after overrides are applied is reported and forces a non-zero exit,
    even when zero citations were found.

    `plugin_root`, when given, overrides the `plugin_root` tree entry
    outright (same override semantics as `--tree`) -- it answers where
    `${CLAUDE_PLUGIN_ROOT}/`-anchored citations resolve, which is NOT
    necessarily the repo root (see module docstring's plugin-root gotcha).

    Anchoring supersedes existence when `consumer_root` is None: citations
    are split into unanchored (no prefix -- reported via `find_unanchored`,
    the PRIMARY class, regardless of resolution) and anchored (existence/
    ambiguity-checked via `resolve_citations`, the SECONDARY class). The
    `--consumer-root` leg (`find_dead_from_consumer`) is untouched by this
    split -- it already answers a literal-text question, not an existence
    question, so the anchoring rule does not apply there."""
    tree_roots: dict[str, str] = {}
    default_tree_failures: list[tuple[str, str]] = []
    if use_default_trees:
        default_roots, default_tree_failures = _default_tree_roots()
        tree_roots.update(default_roots)
    tree_roots.update(tree_overrides)
    if plugin_root is not None:
        tree_roots["plugin_root"] = plugin_root

    unresolved_defaults = [
        (name, err) for name, err in default_tree_failures if name not in tree_roots
    ] if use_default_trees else []

    unscannable = _unscannable_corpus_dirs(corpus_dirs)
    if unscannable:
        return (
            2,
            [f"corpus path {path!r} {reason} — nothing was scanned" for path, reason in unscannable],
            0,
            len(unresolved_defaults),
        )

    citations: list[Citation] = []
    excluded_total = 0
    for path in _iter_corpus_files(corpus_dirs):
        file_citations, file_excluded = _extract_citations(path)
        citations.extend(file_citations)
        excluded_total += file_excluded

    if consumer_root is not None:
        findings = find_dead_from_consumer(citations, tree_roots, consumer_root)
    else:
        findings = find_unanchored(citations, tree_roots) + resolve_citations(citations, tree_roots)

    lines = [_format_finding(f) for f in findings]
    for tree_name, err in unresolved_defaults:
        lines.append(f"default tree '{tree_name}' unresolved: {err}")

    exit_code = 1 if (findings or unresolved_defaults) else 0
    return exit_code, lines, excluded_total, len(unresolved_defaults)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="check-doctrine-citations.py",
        description="Refuse a doctrine citation that resolves to nothing or to more than one tree.",
    )
    parser.add_argument("--corpus", action="append", default=[], help="Directory to scan for citations; repeatable.")
    parser.add_argument(
        "--tree",
        action="append",
        default=[],
        metavar="NAME=PATH",
        help="Override or add a tree root (doe_root, doe_coordinator, claude-klabauter); repeatable.",
    )
    parser.add_argument(
        "--no-default-trees",
        action="store_true",
        help="Skip resolve-repo-path.py default tree resolution; use only --tree overrides.",
    )
    parser.add_argument(
        "--consumer-root",
        default=None,
        metavar="PATH",
        help=(
            "Answer 'does this citation resolve from where the agent actually stands', "
            "not 'does it resolve given the whole map': report every citation whose "
            "literal text does not exist under PATH but DOES exist in a DoE tree."
        ),
    )
    parser.add_argument(
        "--plugin-root",
        default=None,
        metavar="PATH",
        help=(
            "Root a ${CLAUDE_PLUGIN_ROOT}/-anchored citation resolves against. "
            "Overrides the 'plugin_root' default tree entry outright; this is NOT "
            "necessarily the repo root -- see the module docstring's plugin-root gotcha."
        ),
    )
    args = parser.parse_args(argv[1:])

    corpus_dirs = args.corpus or [_REPO_ROOT]
    try:
        tree_overrides = _parse_tree_overrides(args.tree)
    except ValueError as exc:
        print(f"check-doctrine-citations.py: {exc}", file=sys.stderr)
        return 2

    # P2 fix: --no-default-trees with zero --tree flags configures nothing
    # to scan against, which is a usage error, not "every citation failed."
    if args.no_default_trees and not tree_overrides:
        print(
            "check-doctrine-citations.py: --no-default-trees given with no --tree "
            "override — nothing is configured to resolve against",
            file=sys.stderr,
        )
        return 2

    exit_code, lines, excluded, unresolved_defaults = run(
        corpus_dirs,
        tree_overrides,
        use_default_trees=not args.no_default_trees,
        consumer_root=args.consumer_root,
        plugin_root=args.plugin_root,
    )
    for line in lines:
        print(line, file=sys.stderr)
    finding_count = len(lines) - unresolved_defaults
    if exit_code == 2 and any("nothing was scanned" in line for line in lines):
        print(
            "check-doctrine-citations.py: refused before scanning — "
            "no citation was examined, so a clean result would have been a false one",
            file=sys.stderr,
        )
        return exit_code
    if exit_code != 0:
        reason = "resolve from consumer cwd" if args.consumer_root else "resolve unambiguously"
        print(
            f"check-doctrine-citations.py: {finding_count} citation(s) failed to {reason} "
            f"({excluded} illustrative citation(s) excluded, "
            f"{unresolved_defaults} default tree(s) unresolved)",
            file=sys.stderr,
        )
    else:
        print(
            f"check-doctrine-citations.py: 0 citation(s) failed "
            f"({excluded} illustrative citation(s) excluded, "
            f"{unresolved_defaults} default tree(s) unresolved)",
            file=sys.stderr,
        )
    return exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
