"""Citation extraction and four-class resolution over the doctrine wiki corpus.

Purpose: the doctrine corpus cites a sibling page overwhelmingly by a
backticked bare filename in prose (`` `some-page.md` ``), not a markdown
link -- 3,933 such bare-backtick `.md` citations were measured against 874
resolved markdown page links (`docs/research/2026-08-30-17h00-llm-wiki-
doctrine-corpus-workdir/own-side-audit.md`). Nothing today can tell a live
bare citation from one whose target was renamed or deleted out from under
it ("rename rot") -- this module is the extraction + resolution library C1
was dispatched to ship, so a later chunk can build a ratchet report on top
of pure data rather than re-deriving the regexes.

Extraction grammar -- extension allowlist, decided deliberately, not
inherited by accident. `project-rag` allowlists many source extensions
(`.py` included) on the reasoning that a citation is a citation whatever
the target's language. This module allowlists **`.md` only**. That is a
narrower deliberate choice, not an oversight: every one of this chunk's
four resolution classes, its rot ratchet, and its ground-truth sample are
all defined over the `coordinator/docs/wiki/` markdown corpus specifically
(see the plan's `## Unresolved` section) -- a `.py`/`.yaml`/`.json`
backticked reference is a different citation-integrity question (already
partly covered, for a different corpus, by
`coordinator/hooks/scripts/_prompt_surface_citations.py`) that this chunk
was not asked to fold in. Widening the allowlist without a stated resolution
rule for the added extensions would silently produce unclassifiable
citations; narrowing it to what this chunk actually resolves is the
correct-by-construction choice.

Reused, not reimplemented, from `_prompt_surface_citations.py` per this
chunk's dispatch brief -- its already-established false-positive allowlist:
fenced-code-block skip, the frontmatter `spec_backlink:` exemption,
structural HTML-comment markers, and the directory-convention placeholder
heuristic (a trailing glob/no filename is a convention being described, not
a citation being resolved). This module does NOT import that module
directly -- it targets a different corpus and a different violation
definition (rename-rot over the wiki tree, not percolation-safety over the
five prompt-surface trees), and the `## Unresolved` section of
`docs/plans/2026-08-30-citation-integrity-tier-1.md` leaves open whether a
future chunk merges the two. Re-deriving the same four allowlist CLASSES
here (not the same code) is the deliberate interim answer for C1 alone.

Resolution -- FOUR classes, each resolved by its own function, never one
shared code path (Anti-scope: a pathed reference resolves REPO-ROOT-RELATIVE,
never joined against the citing file's directory -- the prototype's
inherited bug):
  - `resolve_bare_basename` -- a bare basename (`some-page.md`), resolved by
    basename against the stated wiki file set (`coordinator/docs/wiki/`).
  - `resolve_cross_surface` -- folded into `resolve_bare_basename`'s verdict:
    a bare basename absent from the wiki set but present elsewhere in the
    repo is CROSS_SURFACE, not ROT -- a real citation into a different
    tracked surface (a plan, handoff, lesson), out of scope for this plan's
    wiki rot ratchet.
  - `resolve_pathed` -- a pathed reference (`docs/wiki/some-page.md`),
    resolved REPO-ROOT-RELATIVE.
  - `resolve_markdown_link` -- a real `[text](path.md)` markdown link,
    resolved relative to the CITING file's own directory -- the one form for
    which that join is correct.

Anchor pass -- SEPARATE from the four classes above. `scan_anchors` runs over
a `CorpusReport`'s `"live"` single-file verdicts only and yields
`AnchorVerdict`s (`anchor_live` | `anchor_missing`) for `[t](x.md#frag)`
fragment links and prose `x.md` § Heading citations. It never alters a
`Verdict`, `resolve_citation` or `scan_corpus`.

Negative-spec (Anti-scope): no CLI, no output formatting, no exit codes --
pure functions over a root path returning structured (dataclass) results, so
a caller's tests can assert on data. No ratchet baseline, no storage of a
resolved verdict (a resolution is a fact about OTHER files and goes stale on
any change that doesn't touch the citing file -- recompute per run, never
persist). No per-line cross-line-split or de-extensioned-citation handling --
both are open evasions tracked at
`state/improvement-queue/2026-07-30-citation-detector-still-has-two-open-
evasions.yaml` against the sibling detector and are inherited here
unresolved, not this chunk's job to fix.

Spec: `docs/plans/2026-08-30-citation-integrity-tier-1.md`, chunk C1.
"""

from __future__ import annotations

import random
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
WIKI_ROOT = REPO_ROOT / "coordinator" / "docs" / "wiki"

#: The plugin root. This corpus's authors write pathed backticked citations
#: (`` `docs/wiki/some-page.md` ``) relative to the PLUGIN root, not the repo
#: root -- "Both trees are named 'coordinator-claude'; they are NOT the same
#: tree. The live plugin root under `~/.claude/plugins/coordinator-claude/`
#: is one level *above* a `coordinator/` subdirectory; under THIS source
#: root, `coordinator/` IS the plugin root." (`CLAUDE.md` § Architecture).
#: A pathed citation must therefore be tried against the plugin root FIRST,
#: falling back to the repo root, or the overwhelming majority of pathed
#: citations in this corpus misresolve as rot.
PLUGIN_ROOT = REPO_ROOT / "coordinator"

#: Ordered candidate roots for `resolve_pathed` -- plugin root first (see
#: `PLUGIN_ROOT`), repo root second. First hit wins.
PATHED_RESOLUTION_ROOTS: "tuple[Path, ...]" = (PLUGIN_ROOT, REPO_ROOT)

#: Deliberate, narrow allowlist -- see module docstring for why `.md` only.
TRACKED_EXTENSIONS = (".md",)

#: Characters that mark a token as a directory-CONVENTION placeholder, not a
#: specific file being cited -- reused class from `_prompt_surface_citations.py`
#: (`_PLACEHOLDER_CHARS`), re-derived here rather than imported (see module
#: docstring: different corpus, different module, same false-positive class).
_PLACEHOLDER_CHARS = ("<", ">", "*", "{", "}", "$", "…", "!")

#: A literal ASCII ellipsis (`...`) used the same way as the unicode `…` char
#: above -- "a placeholder/elided span, not a specific file" -- but it is
#: three ordinary characters, not one, so it can't live in `_PLACEHOLDER_CHARS`
#: (which is checked one character at a time) and needs its own substring
#: check. Measured against the residue of C1's citation-integrity plan: nine
#: `pathed`/`rot` citations used `…`/`!`/literal `...` to describe a class of
#: paths in prose (`docs/plans/...md`, `!scratch/important.md`) rather than
#: cite one specific file, and evaded the original narrower charset.
_PLACEHOLDER_ELLIPSIS = "..."

_FENCE = re.compile(r"^\s*```")
_HTML_COMMENT = re.compile(r"<!--(.*?)-->", re.DOTALL)
_SPEC_BACKLINK_FRONTMATTER_KEY = re.compile(r"^\s*spec_backlink:\s")

#: Structural HTML-comment markers this corpus uses as routing/fence text
#: (`<!-- BEGIN ... -->`, `<!-- consumers: ... -->` etc.) -- a citation-shaped
#: string inside one of these is machinery, not prose asking a reader to
#: resolve a file. Kept narrow and explicit rather than importing the
#: sibling module's dynamically-loaded set, since this module must not take
#: a hard import dependency on a `hooks/scripts/` private module.
_STRUCTURAL_MARKERS = (
    re.compile(r"^\s*BEGIN\b"),
    re.compile(r"^\s*END\b"),
    re.compile(r"^\s*consumers:"),
    re.compile(r"^\s*canonical source"),
)

#: A backticked citation ending `.md`, optionally with a trailing `:LINE`
#: line-reference (`writing-plans.md:51`, matching a form seen in the
#: corpus) before the closing backtick.
_BACKTICK_CITATION = re.compile(r"`([^`\n]*?\.md)(?::\d+)?`")

#: A real markdown link `[text](target.md)`, optional `#anchor`.
_MARKDOWN_LINK = re.compile(r"\[[^\]\n]*\]\(([^)\n#]+\.md)(?:#[^)\n]*)?\)")

#: A wikilink `[[page-slug]]` -- a fourth citation shape this corpus uses
#: (74 occurrences across 53 wiki pages, measured) that neither
#: `_BACKTICK_CITATION` nor `_MARKDOWN_LINK` can see: a bare slug, no `.md`
#: extension, no backticks, resolving to `<slug>.md` in the wiki by the same
#: basename lookup as a bare-backtick citation (`resolve_bare_basename`).
#: Emitted as `kind="bare_basename"` -- the surface grammar differs (no
#: extension, doubled brackets), but it resolves through the identical
#: lookup with no distinguishable status, so a separate `kind` value would
#: carry no downstream consequence (overengineering-reviewer finding 1).
#:
#: The slug charset is deliberately narrow -- lowercase-hyphenated-slug
#: characters only (`[A-Za-z0-9_-]`), no spaces/quotes/`$`/`{`/`:` -- because
#: this corpus's bash prose is FULL of unrelated double-bracket syntax that
#: is not a wikilink at all: POSIX character classes (`` `[[:space:]]` ``),
#: bash conditional tests (`` `[[ -z "$VAR" ]]` ``, `` `if [[ "$OSTYPE" ==
#: "darwin"* ]]` ``). Every one of those contains a space, `$`, `"`, or a
#: leading/embedded `:` that a real slug never does; restricting the
#: charset excludes the whole class without an explicit backtick-context
#: check (measured false-positive source:
#: `coordinator/docs/wiki/portability/cross-platform-shell-portability.md`,
#: `coordinator/docs/wiki/test-design-discipline.md`,
#: `coordinator/docs/wiki/hook-best-practices/machine-local-registry.md`).
#:
#: A slug carrying NO separator (`[[array]]`) is likewise not a wikilink:
#: every page slug in this corpus is multi-word and separated, and the one
#: single-token match in the whole tree is TOML array-of-tables syntax
#: inside a backticked code span (`coordinator/docs/wiki/
#: implementation-standards-by-domain.md`, documenting that a flat key
#: appended after a `[[array]]` header is table-scoped). Requiring a `-`
#: or `_` excludes that class without a backtick-context check, which
#: could not tell it apart from a genuine backticked wikilink anyway.
_WIKILINK = re.compile(r"\[\[([A-Za-z0-9_][A-Za-z0-9_-]*[_-][A-Za-z0-9_-]*)\]\]")


def _normalize_wikilink_slug(slug: str) -> str:
    """Normalize a `[[slug]]` wikilink target before resolution: lowercase,
    `_` -> `-`. This corpus uses TWO wikilink conventions side by side --
    a page's own lowercase-hyphenated filename slug (`[[some-page]]`), and a
    tripwire page's uppercase GREPPABLE_TOKEN (`[[A_COUNTED_FAILURE_IS_NOT_
    A_FAILED_TEST]]`, which names `a-counted-failure-is-not-a-failed-test.md`)
    -- both separators (`_` and `-`) appear in the wild, so normalization is
    unconditional rather than gated on an all-uppercase check: a lowercase
    slug is a no-op under this transform, so applying it always never
    changes an already-correct citation."""
    return slug.lower().replace("_", "-")

#: Shell-command verbs whose presence as the FIRST word of a backticked span
#: means the whole span is invoking a tool, not naming a file -- Defect 1
#: (residue named in `state/handoffs/2026-08-30_214534_citation-integrity-
#: tier-1.md`): `` `grep -r foo docs/x.md` `` is a command, not a reference,
#: even though it ends `.md`. A real citation is a bare path and never
#: begins with a recognized verb followed by more text, so checking only the
#: first whitespace-split word cannot misclassify a genuinely named file
#: like `git-workflow.md` (no internal space, so it never reaches this
#: check at all -- see `interpret_backtick_span`).
#:
#: Known open risk, not a live bug (code review 2026-08-30): `find`, `cat`,
#: `diff`, `wc`, `ls`, `sh` are also ordinary English verbs that could open a
#: prose sentence citing multiple `.md` files (e.g. "find the renamed page in
#: a.md, see also b.md"), which would silently drop the whole span rather
#: than surfacing it as rot. A full-corpus grep for every verb here
#: immediately followed by a `.md`-bearing span found zero false negatives
#: today -- every hit was a genuine shell command. Do not widen or narrow
#: this set without re-running that grep; this note exists so the next
#: reader doesn't have to re-derive the same probe.
_SHELL_COMMAND_VERBS = frozenset(
    {
        "grep", "git", "python", "python3", "sed", "awk", "find", "cat",
        "ls", "tee", "cp", "mv", "rm", "diff", "wc", "dd", "chmod", "bash",
        "sh",
    }
)


#: Defect 2 (same residue doc as Defect 1): a single backtick span can name
#: more than one file in prose (`` `-> a.md, b.md` ``) -- each
#: whitespace/comma-separated `.md`-ending run is an independent citation,
#: not one target formed by concatenating both. Excludes `,` and whitespace
#: from the run so a comma-joined or space-joined list splits at its real
#: boundaries instead of swallowing the separator into the first target.
_CONCATENATED_TARGET_RUN = re.compile(r"[^\s,]+\.md")


def interpret_backtick_span(token: str) -> "tuple[str, ...]":
    """The one decision point for what a backticked `.md` span means: `()`
    for a command-shaped span (a tool invocation, one of whose arguments
    happens to end `.md`, not a citation at all), else the independent
    path-shaped targets it names. Two independent checks, not one: the
    command-shaped check only fires on multi-word input (a bare path is
    never whitespace-separated from a leading verb), but the concatenated-
    target split below runs on EVERY input regardless of word count -- a
    single-word, comma-joined, no-whitespace span (`` `bin,lib,x.md,y.md` ``,
    single-word by whitespace-split) still reaches and correctly splits at
    the concatenated-target check (code review 2026-08-30, finding: this
    docstring previously undersold the concatenation branch as multi-word
    only; see the real corpus's `claude-md-surfaces.md:141` for a live
    single-word multi-target case this path already handles).

    Collapses what were two independently-ordered predicates
    (`_is_shell_command_text`, `_split_concatenated_targets`) into one
    function, per overengineering-reviewer finding 2: two mechanisms
    deciding one input class with ordering as the tiebreaker is spaghetti,
    not two features."""
    words = token.split(None, 1)
    if len(words) >= 2 and words[0].strip("\"'") in _SHELL_COMMAND_VERBS:
        return ()
    runs = _CONCATENATED_TARGET_RUN.findall(token)
    if len(runs) <= 1:
        return (token,)
    return tuple(runs)


@dataclass(frozen=True)
class Citation:
    """One extracted citation-shaped token."""

    citing_file: Path
    line_no: int
    kind: str  # "bare_basename" | "pathed" | "markdown_link" | "decision_ref"
    raw_target: str
    excerpt: str
    #: True only for a `[[slug]]` wikilink -- `raw_target` here already
    #: passed through `_normalize_wikilink_slug`'s lossy fold, unlike every
    #: other `bare_basename` citation. `resolve_bare_basename` uses this to
    #: check the fold-collision guard WITHOUT applying it to an exact
    #: backtick citation, which is never folded and stays unambiguous on
    #: its own (code review 2026-08-30, finding: `_normalize_wikilink_slug`
    #: has no injectivity guard).
    is_wikilink: bool = False


@dataclass(frozen=True)
class Verdict:
    """One resolution outcome for a single `Citation`."""

    citation: Citation
    status: str  # "live" | "cross_surface" | "rot" | "ambiguous" | "dead_link" | "home_relative" | "moved" | "orphaned" | "reserved"  # last two: decision_ref only
    matches: "tuple[Path, ...]" = field(default_factory=tuple)
    #: Which candidate root resolved a `pathed` citation (`resolve_pathed`
    #: only) -- e.g. `PLUGIN_ROOT` or `REPO_ROOT` -- so the verdict is
    #: auditable rather than a bare boolean. `None` for every other
    #: resolver, and for `pathed` citations that resolved under no root.
    resolved_root: "Path | None" = None


def _excerpt(line: str) -> str:
    return " ".join(line.split())[:120]


def _is_placeholder(token: str) -> bool:
    """True if `token` is a directory-convention placeholder (trailing
    glob/no filename) or a bare extension mention (a generic `` `.md` ``
    used to talk ABOUT the extension, e.g. "an agent `.md`") -- neither is a
    specific file being cited."""
    if not token or token.endswith("/"):
        return True
    if any(ch in token for ch in _PLACEHOLDER_CHARS):
        return True
    if _PLACEHOLDER_ELLIPSIS in token:
        return True
    basename = token.rsplit("/", 1)[-1]
    stem = basename[: -len(".md")] if basename.endswith(".md") else basename
    if not stem:
        return True
    return False


def _neutralize_structural_comments(text: str) -> str:
    """Blank out (preserving length/newlines) any HTML comment body matching
    `_STRUCTURAL_MARKERS`, so an incidental substring inside a routing/fence
    marker never extracts as a citation. Mirrors
    `_prompt_surface_citations._neutralize_structural_comments`."""

    def _replace(match: "re.Match[str]") -> str:
        body = match.group(1)
        if any(marker.search(body.strip()) for marker in _STRUCTURAL_MARKERS):
            return re.sub(r"[^\n]", " ", match.group(0))
        return match.group(0)

    return _HTML_COMMENT.sub(_replace, text)


def _walk_prose_lines(text: str) -> "Iterable[tuple[int, str, bool]]":
    """`(line_no, line, in_frontmatter)` for every line of `text` that is not
    a fence delimiter, fenced content, or a frontmatter `---` delimiter, after
    structural-comment neutralization. Shared by every extractor so the
    fence/frontmatter rules cannot diverge."""
    text = _neutralize_structural_comments(text)
    in_fence = False
    in_frontmatter = False
    for line_no, line in enumerate(text.split("\n"), start=1):
        stripped = line.strip()
        if stripped == "---" and line_no <= 2:
            in_frontmatter = True
            continue
        if stripped == "---" and in_frontmatter:
            in_frontmatter = False
            continue
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        yield line_no, line, in_frontmatter


def extract_citations(text: str, citing_file: Path) -> "list[Citation]":
    """Every citation-shaped token in `text`, in line order.

    Skips fenced code blocks, the frontmatter `spec_backlink:` line, and
    directory-convention placeholders -- the reused false-positive allowlist
    (see module docstring). Pure function over already-loaded text; the
    caller decides what `text`/`citing_file` are (this makes the function
    trivially testable without touching disk)."""
    citations: "list[Citation]" = []

    for line_no, line, in_frontmatter in _walk_prose_lines(text):
        if in_frontmatter and _SPEC_BACKLINK_FRONTMATTER_KEY.match(line):
            continue

        for m in _BACKTICK_CITATION.finditer(line):
            token = m.group(1)
            if _is_placeholder(token):
                continue
            # A backticked span immediately followed by `](` is the LABEL of
            # a markdown link, not a second, independent citation --
            # `[\`some-page.md\`](../other/some-page.md)` is one citation,
            # already captured below by `_MARKDOWN_LINK`. Counting the label
            # too double-counts every such link as two citations instead of
            # one, and can classify the label half as rot for a link whose
            # target half resolves live.
            if line[m.end() : m.end() + 2] == "](":
                continue
            for sub_token in interpret_backtick_span(token):
                kind = "pathed" if "/" in sub_token else "bare_basename"
                citations.append(
                    Citation(citing_file, line_no, kind, sub_token, _excerpt(line))
                )

        for m in _MARKDOWN_LINK.finditer(line):
            token = m.group(1)
            if _is_placeholder(token) or token.startswith(("http://", "https://")):
                continue
            citations.append(
                Citation(citing_file, line_no, "markdown_link", token, _excerpt(line))
            )

        for m in _WIKILINK.finditer(line):
            slug = _normalize_wikilink_slug(m.group(1).strip())
            target = f"{slug}.md"
            if _is_placeholder(target):
                continue
            citations.append(
                Citation(
                    citing_file,
                    line_no,
                    "bare_basename",
                    target,
                    _excerpt(line),
                    is_wikilink=True,
                )
            )

    return citations


# ---------------------------------------------------------------------------
# Resolution -- four classes, four functions, never one shared code path.
# ---------------------------------------------------------------------------


#: Namespace prefix for a wikilink fold-collision entry in the dict
#: `load_wiki_index` returns -- kept out of the plain basename keyspace
#: (`\0` can never appear in a filename) so it is visible only to a
#: wikilink-origin lookup (`Citation.is_wikilink`) and never shadows an
#: exact basename key used by a literal backtick citation.
_WIKI_FOLD_COLLISION_PREFIX = "\0fold:"


def load_wiki_index(wiki_root: Path = WIKI_ROOT) -> "dict[str, tuple[Path, ...]]":
    """`basename -> (path, ...)` for every `*.md` file under `wiki_root`.
    A basename with more than one entry is the ambiguous case a caller of
    `resolve_bare_basename` must check for.

    Also records the wikilink fold-collision guard: `_normalize_wikilink_slug`
    unconditionally lowercases and folds `_` -> `-` before a `[[slug]]`
    lookup, which is lossy -- if the corpus ever gains two DISTINCT on-disk
    basenames that fold to the same normalized slug (e.g. `a_b.md` and
    `a-b.md`; zero such pairs exist today), a `[[a_b]]` wikilink would
    otherwise silently resolve to whichever raw basename happens to equal
    the folded string instead of surfacing `ambiguous`. Any such collision
    is recorded under `_WIKI_FOLD_COLLISION_PREFIX + <folded name>`, checked
    by `resolve_bare_basename` only for `is_wikilink` citations -- an exact
    backtick citation to one of the colliding basenames is never folded and
    stays unambiguous on its own, so this must not (and does not) touch the
    plain basename keys already in the index."""
    index: "dict[str, list[Path]]" = {}
    for path in sorted(wiki_root.rglob("*.md")):
        index.setdefault(path.name, []).append(path)

    fold_groups: "dict[str, list[str]]" = {}
    for name in index:
        folded_name = _normalize_wikilink_slug(name[: -len(".md")]) + ".md"
        fold_groups.setdefault(folded_name, []).append(name)
    for folded_name, raw_names in fold_groups.items():
        if len(raw_names) > 1:
            merged: "list[Path]" = []
            for raw_name in sorted(raw_names):
                merged.extend(index[raw_name])
            index[_WIKI_FOLD_COLLISION_PREFIX + folded_name] = merged

    return {name: tuple(paths) for name, paths in index.items()}


def load_repo_index(repo_root: Path = REPO_ROOT) -> "dict[str, tuple[Path, ...]]":
    """`basename -> (path, ...)` for every `*.md` file in the whole repo
    (used only for the cross-surface class -- a basename resolving here but
    not in the wiki index is live-elsewhere, not rot)."""
    index: "dict[str, list[Path]]" = {}
    for path in sorted(repo_root.rglob("*.md")):
        if ".git" in path.parts:
            continue
        index.setdefault(path.name, []).append(path)
    return {name: tuple(paths) for name, paths in index.items()}


def resolve_bare_basename(
    citation: Citation,
    wiki_index: "dict[str, tuple[Path, ...]]",
    repo_index: "dict[str, tuple[Path, ...]]",
) -> Verdict:
    """Bare basename resolved against `wiki_index` first. Exactly one match
    there is `"live"`; more than one is `"ambiguous"`; zero there but a match
    in `repo_index` (a plan, handoff, lesson, or other tracked surface) is
    `"cross_surface"` -- live, out-of-scope for the wiki rot ratchet; zero
    anywhere is `"rot"`.

    For a wikilink-origin citation (`Citation.is_wikilink`), the
    fold-collision guard is checked FIRST: if `raw_target` (itself already
    folded) names a normalized key two or more distinct on-disk basenames
    fold to, that is `"ambiguous"` regardless of which one an exact key
    lookup would otherwise hit -- see `load_wiki_index`."""
    name = citation.raw_target
    if citation.is_wikilink:
        fold_matches = wiki_index.get(_WIKI_FOLD_COLLISION_PREFIX + name)
        if fold_matches is not None:
            return Verdict(citation, "ambiguous", fold_matches)
    wiki_matches = wiki_index.get(name, ())
    if len(wiki_matches) == 1:
        return Verdict(citation, "live", wiki_matches)
    if len(wiki_matches) > 1:
        return Verdict(citation, "ambiguous", wiki_matches)
    repo_matches = repo_index.get(name, ())
    if repo_matches:
        return Verdict(citation, "cross_surface", repo_matches)
    return Verdict(citation, "rot", ())


def resolve_pathed(
    citation: Citation,
    roots: "tuple[Path, ...]" = PATHED_RESOLUTION_ROOTS,
    wiki_index: "dict[str, tuple[Path, ...]] | None" = None,
) -> Verdict:
    """Pathed reference (`docs/wiki/some-page.md`), resolved against each of
    `roots` in order -- never joined against the citing file's own
    directory. First hit wins; the winning root is recorded on the returned
    `Verdict.resolved_root` so the verdict is auditable. See
    `PLUGIN_ROOT`/`PATHED_RESOLUTION_ROOTS` for why plugin root must be
    tried before repo root -- the inherited-bug correction named in the
    plan's Anti-scope was about the JOIN (never against the citing file's
    directory), not about which absolute root the join lands on; this fixes
    the latter without reopening the former.

    A `~`-prefixed target (`~/.claude/CLAUDE.md`) is a HOME-relative path,
    not a repo citation at all -- it names a file on the reader's own
    machine, outside this repo's tree entirely, so joining it against any
    repo-rooted candidate can never be meaningful. Classified
    `"home_relative"` rather than `"rot"`: "citation target renamed or
    deleted" and "citation was never a repo path to begin with" are
    different facts, and folding the second into the rot ratchet would both
    inflate the rot count and hide a class no wiki edit can fix.

    When every root misses AND the target sits under a `docs/wiki/` prefix,
    the citation is a candidate for a wiki page that moved rather than
    vanished: fall back to a basename lookup in `wiki_index` (C2). Exactly
    one match is `"moved"`, carrying the resolved current path -- the
    citation is live but stale, out of the rot ratchet, reported as its own
    count. Several matches is `"ambiguous"` (the basename now names more
    than one page, so which one moved is undecidable). Zero matches there
    too is `"rot"`, same as with no `wiki_index` supplied at all. A target
    NOT under `docs/wiki/` never takes this fallback and goes straight to
    `"rot"` on an all-root miss, regardless of `wiki_index`."""
    if citation.raw_target.startswith("~"):
        return Verdict(citation, "home_relative", ())
    for root in roots:
        candidate = root / citation.raw_target
        if candidate.is_file():
            return Verdict(citation, "live", (candidate,), resolved_root=root)
    if wiki_index is not None and "docs/wiki/" in citation.raw_target.replace("\\", "/"):
        basename = citation.raw_target.replace("\\", "/").rsplit("/", 1)[-1]
        matches = wiki_index.get(basename, ())
        if len(matches) == 1:
            return Verdict(citation, "moved", matches)
        if len(matches) > 1:
            return Verdict(citation, "ambiguous", matches)
    return Verdict(citation, "rot", ())


def resolve_markdown_link(citation: Citation) -> Verdict:
    """Real markdown link, resolved relative to the CITING file's own
    directory -- the one citation form for which that join is correct."""
    candidate = (citation.citing_file.parent / citation.raw_target).resolve()
    if candidate.is_file():
        return Verdict(citation, "live", (candidate,))
    return Verdict(citation, "dead_link", ())


def resolve_citation(
    citation: Citation,
    wiki_index: "dict[str, tuple[Path, ...]]",
    repo_index: "dict[str, tuple[Path, ...]]",
    roots: "tuple[Path, ...]" = PATHED_RESOLUTION_ROOTS,
) -> Verdict:
    """Dispatch a single `Citation` to the resolver matching its `kind`."""
    if citation.kind == "bare_basename":
        return resolve_bare_basename(citation, wiki_index, repo_index)
    if citation.kind == "pathed":
        return resolve_pathed(citation, roots, wiki_index)
    if citation.kind == "markdown_link":
        return resolve_markdown_link(citation)
    raise ValueError(f"unknown citation kind: {citation.kind!r}")


# ---------------------------------------------------------------------------
# Decision-record citations -- bare `DR-148` / `SC-DR-012` prose tokens.
# `extract_citations` never emits this kind and `resolve_citation` does not
# dispatch it; callers use `extract_decision_refs` / `resolve_decision_ref`.
# ---------------------------------------------------------------------------

DECISION_REF_KIND = "decision_ref"
DECISIONS_ROOT = REPO_ROOT / "docs" / "decisions"
SC_DR_HOME = WIKI_ROOT / "concurrent-em-git-operations" / "scoped-safety-commits.md"

#: Normalized example ids used in prose to illustrate the grammar; never
#: counted as orphans.
RESERVED_EXAMPLE_IDS: "frozenset[str]" = frozenset({"DR-0", "DR-999", "SC-DR-0"})

#: Lookbehind keeps `SC-DR-012` out of the DR namespace and rejects `XDR-1`;
#: the trailing `(?!-\d)` rejects date-shaped sibling-repo names
#: (`DR-2026-08-08-...`). A slug continuation (`DR-148-foo`) still yields 148.
_DECISION_TOKEN = re.compile(r"(?<![A-Za-z0-9_-])(SC-)?DR-(\d+)(?![A-Za-z0-9_])(?!-\d)")

#: A record's own frontmatter `id:` line -- not a citation of itself.
_DECISION_ID_LINE = re.compile(r"^id:\s*[\"']?DR-(?:PV1-)?[0-9]+[\"']?\s*$")
_DECISION_FRONTMATTER_ID = re.compile(r"^id:\s*[\"']?DR-([0-9]+)[\"']?\s*$", re.MULTILINE)
_DECISION_FILENAME = re.compile(r"^DR-(\d+)(?:-|\.md$)")
_DECISION_PREFIXED_FILENAME = re.compile(r"^DR-[A-Za-z][A-Za-z0-9]*-\d+-")
_SC_DR_HEADING = re.compile(r"^#{1,6} +SC-DR-(\d+)\b")
_DECISIONS_ARTIFACT_NAME = "ORPHANED-CITATIONS.md"


def normalize_decision_id(namespace: str, digits: str) -> str:
    """("DR", "059") -> "DR-59"; ("SC-DR", "012") -> "SC-DR-12". Namespaces
    never merge."""
    return f"{namespace}-{int(digits)}"


@dataclass(frozen=True)
class DecisionIndex:
    """Which files define which normalized decision ids.

    The four carrier tuples partition every `decisions_root/*.md` except the
    ORPHANED-CITATIONS artifact."""

    entries: "dict[str, tuple[Path, ...]]"
    by_filename: "tuple[Path, ...]"
    by_frontmatter_id: "tuple[Path, ...]"
    prefixed: "tuple[Path, ...]"
    unnumbered: "tuple[Path, ...]"
    sc_dr_heading_count: int


def extract_decision_refs(text: str, citing_file: Path) -> "list[Citation]":
    """A `Citation(kind="decision_ref", raw_target=<normalized id>)` per prose
    `DR-` / `SC-DR-` token, in line order. Same fence/frontmatter walk as
    `extract_citations`; a frontmatter `id:` line is skipped."""
    out: "list[Citation]" = []
    for line_no, line, in_frontmatter in _walk_prose_lines(text):
        if in_frontmatter and _DECISION_ID_LINE.match(line):
            continue
        for m in _DECISION_TOKEN.finditer(line):
            namespace = "SC-DR" if m.group(1) else "DR"
            out.append(
                Citation(
                    citing_file,
                    line_no,
                    DECISION_REF_KIND,
                    normalize_decision_id(namespace, m.group(2)),
                    _excerpt(line),
                )
            )
    return out


def load_decision_index(
    decisions_root: Path = DECISIONS_ROOT, sc_dr_home: Path = SC_DR_HOME
) -> DecisionIndex:
    """Classify each `decisions_root/*.md` into exactly one carrier and index
    the ids they define, plus the `SC-DR-N` headings of `sc_dr_home`. A file
    whose filename number and frontmatter id disagree is indexed under both,
    so the mismatch surfaces as `ambiguous` rather than hiding."""
    entries: "dict[str, list[Path]]" = {}

    def _add(key: str, path: Path) -> None:
        paths = entries.setdefault(key, [])
        if path not in paths:
            paths.append(path)

    by_filename: "list[Path]" = []
    by_frontmatter_id: "list[Path]" = []
    prefixed: "list[Path]" = []
    unnumbered: "list[Path]" = []

    files = sorted(decisions_root.glob("*.md")) if decisions_root.is_dir() else []
    for path in files:
        if path.name == _DECISIONS_ARTIFACT_NAME:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            text = ""
        fm = _DECISION_FRONTMATTER_ID.search(text)
        name_match = _DECISION_FILENAME.match(path.name)
        if name_match:
            by_filename.append(path)
            _add(normalize_decision_id("DR", name_match.group(1)), path)
            if fm:
                _add(normalize_decision_id("DR", fm.group(1)), path)
        elif _DECISION_PREFIXED_FILENAME.match(path.name):
            prefixed.append(path)
        elif fm:
            by_frontmatter_id.append(path)
            _add(normalize_decision_id("DR", fm.group(1)), path)
        else:
            unnumbered.append(path)

    heading_count = 0
    try:
        sc_text = sc_dr_home.read_text(encoding="utf-8")
    except Exception:
        sc_text = ""
    in_fence = False
    for line in sc_text.split("\n"):
        if _FENCE_ANY.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = _SC_DR_HEADING.match(line)
        if m:
            heading_count += 1
            entries.setdefault(normalize_decision_id("SC-DR", m.group(1)), []).append(
                sc_dr_home
            )

    return DecisionIndex(
        entries={k: tuple(v) for k, v in entries.items()},
        by_filename=tuple(by_filename),
        by_frontmatter_id=tuple(by_frontmatter_id),
        prefixed=tuple(prefixed),
        unnumbered=tuple(unnumbered),
        sc_dr_heading_count=heading_count,
    )


def resolve_decision_ref(citation: Citation, index: DecisionIndex) -> Verdict:
    """`"reserved"` for an example id; else `"live"` (one definer),
    `"ambiguous"` (several) or `"orphaned"` (none) against `index.entries`."""
    target = citation.raw_target
    if target in RESERVED_EXAMPLE_IDS:
        return Verdict(citation, "reserved", ())
    matches = index.entries.get(target, ())
    if len(matches) == 1:
        return Verdict(citation, "live", matches)
    if len(matches) > 1:
        return Verdict(citation, "ambiguous", matches)
    return Verdict(citation, "orphaned", ())


# ---------------------------------------------------------------------------
# Corpus-wide scan
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CorpusReport:
    """The full measured output of one scan: every extracted citation
    together with its resolved verdict, plus the file count and git SHA the
    numbers are pinned to (dispatch brief: "State the file count and the git
    SHA alongside every measured figure ... so every number ... is pinned to
    one tree")."""

    wiki_file_count: int
    git_sha: "str | None"
    verdicts: "tuple[Verdict, ...]"

    def by_status(self, status: str) -> "tuple[Verdict, ...]":
        return tuple(v for v in self.verdicts if v.status == status)

    def counts(self) -> "dict[str, int]":
        out: "dict[str, int]" = {}
        for v in self.verdicts:
            out[v.status] = out.get(v.status, 0) + 1
        return out


def git_head_sha(repo_root: Path = REPO_ROOT) -> "str | None":
    """The repo's current HEAD SHA, or `None` if git is unavailable or the
    tree isn't a git checkout -- fail-open rather than raising, since this is
    metadata pinning a report, not a precondition for resolution itself."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
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


def scan_corpus(
    wiki_root: Path = WIKI_ROOT,
    repo_root: Path = REPO_ROOT,
) -> CorpusReport:
    """Extract and resolve every citation across `wiki_root`'s markdown
    files. Recomputes from scratch on every call (Anti-scope: never resolve
    at write time and persist the verdict -- a verdict is a fact about OTHER
    files and goes stale on any change that doesn't touch the citing file)."""
    wiki_index = load_wiki_index(wiki_root)
    repo_index = load_repo_index(repo_root)
    wiki_files = sorted(wiki_root.rglob("*.md"))

    verdicts: "list[Verdict]" = []
    for path in wiki_files:
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        roots = (repo_root / "coordinator", repo_root)
        for citation in extract_citations(text, path):
            verdicts.append(resolve_citation(citation, wiki_index, repo_index, roots))

    return CorpusReport(
        wiki_file_count=len(wiki_files),
        git_sha=git_head_sha(repo_root),
        verdicts=tuple(verdicts),
    )


# ---------------------------------------------------------------------------
# Seeded, reproducible sampler -- for a recomputable precision figure, not to
# clear a threshold (dispatch brief: a 30-sample draw's ~95% CI is roughly
# +/-11pp, wide enough that it cannot itself decide anything).
# ---------------------------------------------------------------------------


def sample_verdicts(
    verdicts: "Iterable[Verdict]", *, seed: int, sample_size: int
) -> "tuple[Verdict, ...]":
    """A deterministic, seeded sample of `sample_size` verdicts drawn from
    `verdicts` (order-independent -- sorted onto a stable key first so the
    same `seed` reproduces the same draw regardless of input ordering).
    `sample_size` larger than the population returns the whole population,
    unsampled and in stable order (never raises)."""
    population = sorted(
        verdicts,
        key=lambda v: (str(v.citation.citing_file), v.citation.line_no, v.citation.raw_target),
    )
    if sample_size >= len(population):
        return tuple(population)
    rng = random.Random(seed)
    return tuple(rng.sample(population, sample_size))


# ---------------------------------------------------------------------------
# Anchor pass -- separate from the four file-resolution classes. Runs only over
# file-live single-target verdicts; never changes a Verdict.
# ---------------------------------------------------------------------------

#: Grammar G2: a `.md` target followed (optionally after a closing backtick)
#: by `§` and a free-text tail.
_SECTION_CITATION = re.compile(
    r"(?P<t>[A-Za-z0-9_./-]+\.md)(?::\d+)?`?\s*§\s*"
    r"(?P<tail>.*?)(?=`?[A-Za-z0-9_./-]+\.md|$)"
)
#: Grammar G1: `[text](x.md#frag)`.
_FRAGMENT_LINK = re.compile(r"\[[^\]\n]*\]\(([^)\n#]+\.md)#([^)\n]*)\)")
_SECTION_SPLIT = re.compile(r"\s*[,;]?\s*(?:and\s+|/\s*)?§\s*")
_FENCE_ANY = re.compile(r"^\s*(```|~~~)")
_ATX_HEADING = re.compile(r"^ {0,3}#{1,6}[ \t]+(.*?)[ \t]*$")
_CLOSING_HASHES = re.compile(r"[ \t]+#+$")
_BOLD_LEAD_IN = re.compile(r"^\s*(?:[-*]\s+|\d+[.)]\s+)?\*\*(.{3,120}?)\*\*")
_ID_LIKE_REF = re.compile(
    r"^(?:[A-Z]{1,6}-?\d+[a-z]?(?:[.-]\d+)*|[A-Z]\.\d+|[A-Z]{2,}(?:-[A-Z0-9]+){2,})$"
)
_REF_CUT = re.compile(r"<!--|\s[-—–]\s|;|\)|\(|\.\s|:\s|,\s")
_HEADING_SEGMENT_SPLIT = re.compile(r"\s-\s|[—–]|:\s|\(")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class AnchorVerdict:
    """One anchor resolution for a citation whose file verdict is `live`."""

    citation: Citation
    anchor: str
    grammar: str  # "fragment" | "section"
    status: str  # "anchor_live" | "anchor_missing"


@dataclass(frozen=True)
class _Headings:
    """Heading candidates of one file: raw lowercased texts (ATX + bold
    lead-ins) for the section grammar, slugs of ATX headings for fragments."""

    raw: "tuple[str, ...]"
    slugs: "frozenset[str]"


def _strip_marks(text: str) -> str:
    return text.replace("`", "").replace("*", "")


def _norm(text: str) -> str:
    return _NON_ALNUM.sub(" ", _strip_marks(text).lower()).strip()


def _github_slug(heading: str) -> str:
    cleaned = _strip_marks(heading).lower()
    cleaned = re.sub(r"[^\w \-]", "", cleaned)
    return cleaned.strip().replace(" ", "-")


def extract_headings(text: str) -> _Headings:
    """Fence-aware ATX headings plus bold lead-ins of one file's text; CRLF
    normalised. A heading inside a fenced block does not exist."""
    raw: "list[str]" = []
    slugs: "set[str]" = set()
    in_fence = False
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if _FENCE_ANY.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = _ATX_HEADING.match(line)
        if m:
            heading = _CLOSING_HASHES.sub("", m.group(1)).strip()
            if heading:
                raw.append(_strip_marks(heading).lower())
                slugs.add(_github_slug(heading))
            continue
        b = _BOLD_LEAD_IN.match(line)
        if b:
            lead = b.group(1).strip().rstrip(".:-").strip()
            if lead:
                raw.append(lead.lower())
    return _Headings(tuple(raw), frozenset(slugs))


def _load_headings(
    path: Path, cache: "dict[Path, _Headings | None]"
) -> "_Headings | None":
    if path not in cache:
        try:
            cache[path] = extract_headings(path.read_text(encoding="utf-8"))
        except Exception:
            cache[path] = None
    return cache[path]


def _cut_ref(ref: str) -> str:
    """One `§` ref's heading text: quoted/backticked text when the ref opens
    with a quote, else the ref cut at the first prose boundary."""
    ref = ref.strip()
    if not ref:
        return ""
    if ref[0] in "\"“":
        m = re.match(r"[\"“](.*?)[\"”]", ref)
        text = m.group(1) if m else ref[1:]
    elif ref[0] == "'":
        m = re.match(r"'(.*?)'(?!\w)", ref)
        text = m.group(1) if m else ref[1:]
    elif ref[0] == "`":
        end = ref.find("`", 1)
        text = ref[1:end] if end != -1 else ref[1:]
    else:
        cut = _REF_CUT.search(ref)
        text = ref[: cut.start()] if cut else ref
    text = re.sub(r"\s+(?:and|or|&)\s*$", "", text.split("-->", 1)[0])
    return text.strip().strip("`'\"*“”").strip()


def _words_prefix(a: str, b: str) -> bool:
    """`a == b` or `a` starts with `b` plus a word boundary."""
    return bool(b) and (a == b or a.startswith(b + " "))


def _section_matches(ref: str, headings: "tuple[str, ...]") -> bool:
    """The chosen C1 match rule (R5): the ref is found if any of a-f holds."""
    n = _norm(ref)
    norms = [_norm(h) for h in headings]
    for h in norms:
        if h and (_words_prefix(n, h) or _words_prefix(h, n)):
            return True
    num = re.match(r"(?:step )?(\d+)", n)
    if num:
        pat = re.compile(rf"^(?:step )?{num.group(1)}(?:[.): ]|$)")
        if any(pat.match(h) for h in headings):
            return True
    phased = re.match(r"(?:phase|step|part|section) (\d+)", n)
    if phased:
        word = re.compile(rf"\b{phased.group(1)}\b")
        lead = re.compile(r"^(?:(?:phase|step|part|section) )?\d")
        if any(lead.match(h) and word.search(h) for h in norms):
            return True
    if len(n) >= 4 and any(f" {n} " in f" {h} " for h in norms):
        return True
    for heading in headings:
        for seg in _HEADING_SEGMENT_SPLIT.split(heading):
            s = _norm(seg)
            if len(s) >= 4 and (_words_prefix(n, s) or _words_prefix(s, n)):
                return True
    tok = re.match(r"\d+[a-z]?", n)
    if tok:
        pat = re.compile(rf"^(?:[a-z]{{0,2}}\s*)?{re.escape(tok.group(0))}(?:[.): ]|$)")
        if any(pat.match(h) for h in headings):
            return True
    return False


def resolve_anchor(
    citation: Citation,
    anchor: str,
    grammar: str,
    target: Path,
    cache: "dict[Path, _Headings | None] | None" = None,
) -> "AnchorVerdict | None":
    """`AnchorVerdict` for one anchor against the single resolved `target`
    file, or `None` when the anchor is not checkable (unreadable target,
    empty or ID-like section ref). `cache` memoises headings per path within
    one scan."""
    headings = _load_headings(target, {} if cache is None else cache)
    if headings is None:
        return None
    if grammar == "fragment":
        from urllib.parse import unquote

        found = unquote(anchor).strip().lower() in headings.slugs
    elif grammar == "section":
        if not anchor or not _norm(anchor) or _ID_LIKE_REF.match(anchor):
            return None
        found = _section_matches(anchor, headings.raw)
    else:
        raise ValueError(f"unknown anchor grammar: {grammar!r}")
    return AnchorVerdict(citation, anchor, grammar, "anchor_live" if found else "anchor_missing")


def scan_anchors(report: CorpusReport) -> "tuple[AnchorVerdict, ...]":
    """Anchor verdicts for every `[t](x.md#frag)` and `x.md` § Heading
    citation behind a `"live"` verdict resolving to exactly one file. Reads
    each citing file once; never touches `report` or any `Verdict`."""
    by_file: "dict[Path, dict[tuple[int, str], Verdict]]" = {}
    for v in report.verdicts:
        if v.status == "live" and len(v.matches) == 1:
            c = v.citation
            by_file.setdefault(c.citing_file, {}).setdefault((c.line_no, c.raw_target), v)

    cache: "dict[Path, _Headings | None]" = {}
    out: "list[AnchorVerdict]" = []
    for citing_file in sorted(by_file):
        try:
            text = citing_file.read_text(encoding="utf-8")
        except Exception:
            continue
        live = by_file[citing_file]
        in_fence = False
        for line_no, line in enumerate(
            text.replace("\r\n", "\n").replace("\r", "\n").split("\n"), start=1
        ):
            if _FENCE_ANY.match(line):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            for m in _FRAGMENT_LINK.finditer(line):
                v = live.get((line_no, m.group(1)))
                if v is not None and v.citation.kind == "markdown_link":
                    av = resolve_anchor(v.citation, m.group(2), "fragment", v.matches[0], cache)
                    if av is not None:
                        out.append(av)
            for m in _SECTION_CITATION.finditer(line):
                v = live.get((line_no, m.group("t")))
                if v is None:
                    continue
                for ref in _SECTION_SPLIT.split(m.group("tail")):
                    av = resolve_anchor(v.citation, _cut_ref(ref), "section", v.matches[0], cache)
                    if av is not None:
                        out.append(av)
    return tuple(out)
