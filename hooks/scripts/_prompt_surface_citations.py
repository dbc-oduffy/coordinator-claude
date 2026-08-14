"""Shared detector for unresolvable citations in coordinator prompt surfaces.

`coordinator/{agents,skills,commands,snippets,pipelines}/` PERCOLATE: they run in
sibling repos, on other operators' machines, and in OSS installs that ship a
deliberately sparse curated wiki seed. A citation that resolves in THIS clone 404s for
those readers — worse for `docs/plans/`, `docs/decisions/`, `archive/specs/`,
`archive/completed/`, `cross-repo/{inbox,archive}/`, and `state/{handoffs,lessons,
review-trail}/`, none of which percolate at all, and worst for a cross-repo memo
citation, which is designed to be ephemeral (distilled into a wiki, then archived
and deleted) so it rots by construction. A bare decision-record id (`DR-058`,
`SC-DR-015`) is the same failure in miniature — the reader has no `decisions/` tree.

Consumers — BOTH import `iter_violations()`/`new_violations()` from here rather
than keeping a second copy of the regexes, which is exactly the failure mode a
shared module exists to prevent:
  - `coordinator/hooks/scripts/guard-prompt-surface-citations.py` — PreToolUse
    write-time guard. Uses `new_violations()`, not `iter_violations()` directly,
    so it only ever reacts to citations the CURRENT write introduces — see that
    function's docstring for why this makes hard-deny safe against the corpus's
    ~550 pre-existing legacy violations.
  - `coordinator/tests/test_prompt_surfaces_cite_resolvably.py` — ratchet test.
    Uses `iter_violations()` against each file's full current text and compares
    the per-file COUNT to a checked-in baseline.

NOT a violation (see the two consumers' own docstrings for the false-positive
classes this module exists to avoid):
  - a directory CONVENTION with a trailing placeholder/glob/no filename
    (`archive/<queue>/<YYYY-MM>/`, `state/subagent-share/<session-id>/…`,
    `tasks/`, or a bare `docs/plans/` mentioned as a destination to write to);
  - frontmatter `spec_backlink:` — schema-validated metadata, exempt by ruling;
  - a structural HTML-comment marker (`STRUCTURAL_MARKERS`, reused from
    `test_prompt_surfaces_carry_no_provenance.py` rather than re-derived);
  - anything inside a fenced code block — deliberately lenient (a genuinely
    unsure case is NOT flagged, per the false-positive-cost reasoning in the
    two consumers) since a fence usually holds an illustrative command example,
    not an operative citation the reader is expected to resolve.

SEED_WIKIS and STRUCTURAL_MARKERS are loaded from their OWN ratified sources
(`test_publish_seed_wiki_allowlist.py`, `test_prompt_surfaces_carry_no_provenance.py`)
via `importlib`, not hardcoded here — a hardcoded second copy is precisely the
drift this module exists to prevent. Load failure degrades that ONE detection
class to fail-OPEN (no `docs/wiki/*` or structural-comment handling), never to a
hard failure — this module runs inside a PreToolUse hook, where an internal
resolution hiccup must narrow coverage, not brick every edit. The ratchet test
asserts both loaded successfully as part of its own setup (see that file), so a
load failure is loud in CI even though it is silent-and-narrowing at hook time.
"""

from __future__ import annotations

import ast
import importlib.util
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[3]

#: Same five trees as `test_prompt_surfaces_carry_no_provenance.py::PROMPT_SURFACE_DIRS`
#: — kept as a separate tuple (not imported) because that module is a test, not a
#: stable import surface, and its own docstring explains why `templates/`/`schemas/`/
#: `dist/` are deliberately excluded. If that set ever changes, update both.
PROMPT_SURFACE_DIRS = (
    REPO_ROOT / "coordinator" / "agents",
    REPO_ROOT / "coordinator" / "skills",
    REPO_ROOT / "coordinator" / "commands",
    REPO_ROOT / "coordinator" / "snippets",
    REPO_ROOT / "coordinator" / "pipelines",
)

#: `coordinator/hooks/` (C3, docs/plans/2026-08-13-doe-guard-text-trust-failure-
#: coverage.md) -- a SEPARATE tree from `PROMPT_SURFACE_DIRS` above because it is
#: governed on `.py` source (guard/hook scripts carrying `_WIKI_ANCHOR`-shaped
#: string literals and citation-bearing docstrings/comments), not `.md` prose.
#: Prior to this chunk the detector's corpus excluded `hooks/` entirely, which is
#: exactly why unresolvable anchors accumulated there unseen while every `.md`
#: prompt surface was held to zero. `resolve_wiki_citation()`
#: (`_message_envelope.py`) rewrites a `docs/wiki/<page>.md` (optionally
#: `coordinator/`-prefixed) citation into an absolute path anchored at the real
#: plugin root AT RENDER TIME -- so a hook-resident `_WIKI_ANCHOR` holding that
#: literal is resolvable-at-rest and must NOT be flagged on that basis alone; the
#: existing SEED_WIKIS/REAL_WIKI_PAGES membership checks below already capture
#: the orthogonal question (does the target page exist/percolate at all), so no
#: separate resolution rule is needed here -- widening the corpus to include this
#: tree is sufficient for the existing classification logic to apply to it.
PY_SURFACE_DIRS = (REPO_ROOT / "coordinator" / "hooks",)

_TESTS_DIR = REPO_ROOT / "coordinator" / "tests"

#: Subdirectory names that, anywhere in a prompt-surface-relative path, exempt a
#: file entirely — test fixtures under `pipelines/**/tests/` and `**/fixtures/**`
#: are test data, not prompt surfaces read by a model mid-task.
_EXEMPT_PATH_SEGMENTS = frozenset({"tests", "fixtures"})


def _load_module(path: Path, name: str):
    """Best-effort load of a sibling test module by file path. Returns None on
    any failure (missing file, syntax error, import-time exception) rather than
    raising — see module docstring for why this degrades detection instead of
    crashing the guard."""
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        return module
    except Exception:
        return None


def _load_seed_wikis() -> frozenset:
    module = _load_module(
        _TESTS_DIR / "test_publish_seed_wiki_allowlist.py",
        "_prompt_surface_citations_seed_wikis",
    )
    if module is None:
        return frozenset()
    return frozenset(getattr(module, "SEED_WIKIS", ()))


def _load_structural_markers() -> tuple:
    module = _load_module(
        _TESTS_DIR / "test_prompt_surfaces_carry_no_provenance.py",
        "_prompt_surface_citations_structural_markers",
    )
    if module is None:
        return ()
    return tuple(getattr(module, "STRUCTURAL_MARKERS", ()))


#: Resolved once at import time. Empty means "unresolvable on this run" — see
#: `_load_seed_wikis`/`_load_structural_markers` docstrings for the fail-open
#: contract that follows from that.
SEED_WIKIS: frozenset = _load_seed_wikis()
STRUCTURAL_MARKERS: tuple = _load_structural_markers()


@dataclass(frozen=True)
class Violation:
    line_no: int
    kind: str
    excerpt: str
    # Review: coordinator:code-reviewer -- F5, resolved via the alternative
    # the finding itself asked for rather than a raw line number: the
    # untruncated, whitespace-normalized line, used only for the identity
    # key below. `excerpt` stays truncated to 90 chars for display. A raw
    # line number was rejected -- `_violation_key`'s whole design point is
    # staying line-shift-safe (an edit elsewhere in the file must not make
    # an untouched violation look "new"), and keying on line number would
    # false-deny on every edit that merely shifts surrounding lines. This
    # field fixes the truncated-excerpt collision (two distinct >90-char
    # citations sharing the same first 90 chars) without reintroducing that
    # position-sensitivity.
    line_fingerprint: str = ""


# ---------------------------------------------------------------------------
# Scope — which files/paths this detector applies to
# ---------------------------------------------------------------------------


def is_in_scope(path: Path) -> bool:
    """True if `path` is a `*.md` file under one of `PROMPT_SURFACE_DIRS`, OR a
    `*.py` file under `PY_SURFACE_DIRS` (`coordinator/hooks/`) -- excluding
    `tests/`/`fixtures/` subdirectories anywhere in the relative path (see
    `_EXEMPT_PATH_SEGMENTS`) in either case."""
    try:
        resolved = path.resolve()
    except Exception:
        return False

    if resolved.suffix == ".md":
        candidate_roots = PROMPT_SURFACE_DIRS
    elif resolved.suffix == ".py":
        candidate_roots = PY_SURFACE_DIRS
    else:
        return False

    for root in candidate_roots:
        try:
            rel = resolved.relative_to(root)
        except ValueError:
            continue
        if _EXEMPT_PATH_SEGMENTS.intersection(rel.parts[:-1]):
            return False
        return True
    return False


def iter_prompt_surface_files() -> Iterable[Path]:
    """Every in-scope file under the prompt-surface `.md` trees and the
    `.py` hooks tree, sorted for determinism."""
    for root in PROMPT_SURFACE_DIRS:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.md")):
            if is_in_scope(path):
                yield path
    for root in PY_SURFACE_DIRS:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            if is_in_scope(path):
                yield path


# ---------------------------------------------------------------------------
# Violation detection
# ---------------------------------------------------------------------------

#: (prefix, label) — a specific-file citation under any of these prefixes is
#: unresolvable for a non-local reader; see module docstring for why each
#: never percolates.
_NONPERCOLATING_TREES = (
    ("docs/plans/", "docs/plans/ citation (plan, never percolates)"),
    ("docs/decisions/", "docs/decisions/ citation (decision record, never percolates)"),
    ("archive/specs/", "archive/specs/ citation (archived spec, never percolates)"),
    ("archive/completed/", "archive/completed/ citation (archived, never percolates)"),
    ("cross-repo/inbox/", "cross-repo/inbox/ citation (ephemeral memo, never percolates)"),
    ("cross-repo/archive/", "cross-repo/archive/ citation (ephemeral memo, never percolates)"),
    ("state/handoffs/", "state/handoffs/ citation (never percolates)"),
    ("state/lessons/", "state/lessons/ citation (never percolates)"),
    ("state/review-trail/", "state/review-trail/ citation (never percolates)"),
    (
        # Review: code-reviewer (Finding 3) -- dropped the "reader has
        # already loaded this exact text" clause; not true on OSS/sibling
        # installs where global-doctrine/ doesn't exist at all.
        "global-doctrine/",
        "global-doctrine/ citation (never percolates -- cite the section "
        "by name alone)",
    ),
)

#: A token following a non-percolating prefix must look like a SPECIFIC file
#: (has a real extension) to count — a bare directory, a trailing placeholder
#: (`<...>`), a glob (`*`), a template var (`{...}`/`$...`), or a trailing
#: slash is a convention being described, not a citation being resolved.
# Review: coordinator:code-reviewer -- F4: `\b` alone still matches
# "foo.md-style" (word char "d" -> non-word "-" is a boundary), so an
# adjectival citation ("our internal docs/plans/foo.md-style convention")
# false-positived as a specific-file citation. The added negative lookahead
# additionally excludes a trailing hyphen so the extension must be followed
# by whitespace/punctuation/end-of-token, not more path-shaped text.
_FILE_EXTENSION = re.compile(r"\.(md|ya?ml|py|json|jsonl|sh|txt)(?![\w-])")
_PLACEHOLDER_CHARS = ("<", ">", "*", "{", "}", "$")
_PATH_TOKEN = re.compile(r"[^\s`)\]\"'>]*")

_DR_ID = re.compile(r"\bDR-\d{2,}\b|\bSC-DR-\d{2,}\b")

#: An inline `code span`. Used ONLY by `_literal_sentinel_spans` below — a DR id
#: in a bare code span (`` `DR-091` ``) is still an ordinary prose citation and
#: is NOT exempt.
_CODE_SPAN = re.compile(r"`([^`\n]+)`")


def _literal_sentinel_spans(line: str) -> "list[tuple[int, int]]":
    """Character ranges of inline code spans holding a LITERAL SENTINEL STRING.

    A DR id inside one of these is not a citation. It is part of a value the
    coordinator writes to, and later matches against, a real file on the
    operator's disk — e.g. install.md documents the marker
    `# coordinator-install: brew shellenv (DR-148)` that gets appended to
    `~/.bash_profile` and re-detected on the next install via `grep -qF`.
    Rewriting the id out of that string would not remove a dangling pointer;
    it would change a wire value, so an existing install's marker would stop
    matching and the installer would append a duplicate block. The id is data
    here, exactly like the `BEGIN`/`END` fence markers and routing pairs the
    provenance gate exempts as wiring rather than prose. That `DR-148` is
    frozen historical numbering: the live record is
    `docs/decisions/DR-166-require-bash4-on-macos.md`, and the sentinel does
    not follow it.

    Deliberately narrow: the span must look like a comment/marker literal (it
    starts with a `#` comment introducer). A DR id inside any other code span
    — `` `DR-091` `` in a sentence, a `SC-DR-015` reference — stays a
    violation, because the reader is genuinely being pointed at a document
    they cannot open. Widening this to all code spans would silently exempt
    most real citations in the corpus, since prose here habitually backticks
    them.
    """
    spans: "list[tuple[int, int]]" = []
    for match in _CODE_SPAN.finditer(line):
        if match.group(1).lstrip().startswith("#"):
            spans.append((match.start(), match.end()))
    return spans

_WIKI_CITATION = re.compile(r"docs/wiki/([A-Za-z0-9_\-]+\.md)")

#: A de-prefixed citation of a real wiki page — `writing-plans.md`, `` `writing-plans.md` ``,
#: `writing-plans.md:51`, or the partial-prefix form `wiki/writing-plans.md` (missing `docs/`).
#: Stripping the `docs/wiki/` prefix off a citation is a working evasion of `_WIKI_CITATION`
#: above: the reader still can't open the page, but the string "docs/wiki/" no longer appears
#: on the line. Matched against `REAL_WIKI_PAGES` (the actual files on disk) rather than a
#: filename-shaped regex, precisely so this can't be fooled by an unrelated `*.md` mention and
#: doesn't need its own allowlist of "things that look like a wiki page" — deliberately narrower
#: than `_FILE_EXTENSION`/`_looks_like_specific_file` for that reason.
#:
#: Deliberately two patterns, not one permissive one — a plain `\b`-bounded token also matches
#: `<central-state>/repo-registry.md`, `state/repo-registry.md`, or any other directory whose
#: basename happens to collide with a wiki page name. Those are repo-relative CONVENTIONS (a
#: path in the READER'S OWN environment the agent writes to or checks for existence), not a
#: citation of this repo's doctrine page of the same name — exactly the class CLAUDE.md
#: § Conventions carves out, and the false positive this module's docstring warns against
#: manufacturing. So only two shapes count: truly prefix-less (`_BARE_WIKI_PAGE_TOKEN`, not
#: preceded by a word char OR `/`) and the specific partial-prefix `wiki/name.md` missing only
#: the `docs/` segment (`_WIKI_SHORT_PREFIX_TOKEN`) — anything preceded by some OTHER directory
#: name is left alone. The `docs/wiki/name.md` form is excluded from both (already counted once
#: by `_WIKI_CITATION` above) via the negative lookbehind on the first and the negative
#: lookbehind on `docs/` on the second.
_BARE_WIKI_PAGE_TOKEN = re.compile(r"(?<![\w/])([A-Za-z0-9][\w-]*\.md)\b")
_WIKI_SHORT_PREFIX_TOKEN = re.compile(r"(?<!docs/)\bwiki/([A-Za-z0-9][\w-]*\.md)\b")

#: The contiguous non-whitespace/non-delimiter run immediately before a match — used to
#: detect a TEMPLATED write-target masquerading as a bare wiki-page name, e.g.
#: `state/audits/YYYY-MM-DD-<SID_SHORT>-plan-delivery-audit.md`: the trailing
#: `plan-delivery-audit.md` is a real wiki page's basename, but the match sits at the tail
#: of an output-path template the skill is told to WRITE to, not a citation of that page. A
#: token boundary alone (used for the DIRECTORY-prefixed case in `_looks_like_specific_file`)
#: doesn't catch this because the placeholder (`<SID_SHORT>`) is BEFORE the matched name, not
#: in a directory prefix. Same `_PLACEHOLDER_CHARS` used there.
_PRECEDING_RUN = re.compile(r"[^\s`\"'()\[\]]*$")


def _preceded_by_placeholder(line: str, match_start: int) -> bool:
    run = _PRECEDING_RUN.search(line[:match_start]).group(0)
    return any(ch in run for ch in _PLACEHOLDER_CHARS)


def _load_real_wiki_pages() -> frozenset:
    """Every `*.md` filename actually present under `coordinator/docs/wiki/` — the
    ground truth `_BARE_WIKI_PAGE_TOKEN` matches against. Loaded fresh (not cached
    across runs) for the same reason `SEED_WIKIS`/`STRUCTURAL_MARKERS` are re-derived
    rather than hand-copied: this is the one list that can't silently drift from the
    directory it describes. Empty on any failure (missing directory, permissions) —
    fail-open, same contract as the two `_load_*` helpers above."""
    wiki_dir = REPO_ROOT / "coordinator" / "docs" / "wiki"
    try:
        return frozenset(p.name for p in wiki_dir.glob("*.md"))
    except Exception:
        return frozenset()


#: Resolved once at import time, same fail-open contract as SEED_WIKIS/STRUCTURAL_MARKERS.
REAL_WIKI_PAGES: frozenset = _load_real_wiki_pages()

#: Wiki filenames that name a file THE CONSUMING REPO OWNS, rather than a
#: doctrine page this repo ships — a convention like `archive/<queue>/<YYYY-MM>/`,
#: not a citation. Naming one does not point a reader at a document only this
#: clone has; it names a path in the reader's own repo, and the prompt uses it
#: operationally (write to it, check whether it exists) rather than sending
#: anyone off to read it for content.
#:
#: ENTRY CRITERION, and it is narrow: the prompt must use the path as an
#: OPERATIONAL TARGET in the consuming repo — a write destination, or an
#: existence check gating behaviour. A page the reader is told to go READ for
#: doctrine is a violation no matter how conventional its name looks. Adding an
#: entry here is a deliberate judgment that the path is machinery, not
#: reference; it is an allowlist and never a heuristic, because the cost of a
#: wrong entry is a real dangling pointer going silently unreported.
#:
#: `DIRECTORY_GUIDE.md` is the index the artifact-distillation pipeline
#: assembles (its Phase 3c is literally titled "DIRECTORY_GUIDE.md Assembly"),
#: and several of its mentions are WRITE targets — "update
#: `docs/wiki/DIRECTORY_GUIDE.md` and `docs/README.md`". Flagging those pushed
#: a remediation pass toward stripping the directory off the path to quiet the
#: detector, which left an apply-agent told to update a file without being told
#: where it lives, with its fully-pathed sibling `docs/README.md` sitting in the
#: same sentence untouched — that asymmetry existed only because one path
#: happens to live under `docs/wiki/`. Making the instruction worse to satisfy
#: the gate is the failure mode; exempting the convention is the fix.
#:
#: `versioning-convention.md` is named by a conditional in workweek-complete:
#: "If `docs/wiki/versioning-convention.md` exists, it is the authority for
#: which number/artifact is canonical." The prompt never asks anyone to read
#: this repo's copy — it tells the agent to look for the CONSUMING repo's own
#: convention and defer to it, falling back to a semver heuristic stated inline
#: right there. Rewording the path out would have destroyed the instruction: an
#: agent told to honour a convention, but not where to find it, cannot perform
#: the check.
_CONSUMING_REPO_CONVENTION_FILES = frozenset(
    {
        "DIRECTORY_GUIDE.md",
        "versioning-convention.md",
    }
)

_FENCE = re.compile(r"^\s*```")

_HTML_COMMENT = re.compile(r"<!--(.*?)-->", re.DOTALL)

_SPEC_BACKLINK_FRONTMATTER_KEY = re.compile(r"^\s*spec_backlink:\s")


def _looks_like_specific_file(suffix: str) -> bool:
    if not suffix or suffix.endswith("/"):
        return False
    if any(ch in suffix for ch in _PLACEHOLDER_CHARS):
        return False
    return bool(_FILE_EXTENSION.search(suffix))


def _excerpt(line: str) -> str:
    return " ".join(line.split())[:90]


def _neutralize_structural_comments(text: str) -> str:
    """Blank out (preserving length/newlines, so line numbers stay stable) any
    HTML comment body matching `STRUCTURAL_MARKERS`, so an incidental
    substring inside a routing/fence marker can never match a violation
    pattern. A NON-structural comment is left as-is — a plain comment citing
    an unresolvable path is still a violation; only the provenance CLASS of
    that comment is a separate, sibling test's concern
    (`test_prompt_surfaces_carry_no_provenance.py`), not this module's."""

    def _replace(match: "re.Match[str]") -> str:
        body = match.group(1)
        if any(marker.search(body.strip()) for marker in STRUCTURAL_MARKERS):
            return re.sub(r"[^\n]", " ", match.group(0))
        return match.group(0)

    return _HTML_COMMENT.sub(_replace, text)


# ---------------------------------------------------------------------------
# `.py` scope narrowing — EMITTED MESSAGE TEXT ONLY (C3 rescope,
# docs/plans/2026-08-13-doe-guard-text-trust-failure-coverage.md)
#
# Why a `.py` hook needs a narrower rule than a `.md` prompt surface: a `.md`
# file under PROMPT_SURFACE_DIRS is emitted to a reader WHOLESALE, so every
# citation in it is something an agent is expected to resolve. A `.py` hook
# is not — only the message strings it actually sends an agent (stderr,
# hookSpecificOutput dict keys, or the `_message_envelope` compose/emit seam)
# ever reach a reader. Its module docstring, inline comments, and Review:
# provenance lines are read by a HUMAN maintaining the source, never
# forwarded anywhere — and per CLAUDE.md § Implementation Standards
# ("RAG-bait exception. Purpose docstrings, spec backlinks, negative-spec
# blocks: required") a spec-backlinked docstring citing docs/plans/ or a
# bare DR- id there is a REQUIRED convention, not a defect. Flagging it is
# the miscalibration this rescope corrects — restricting the `.py` leg
# structurally (an AST reachability rule) rather than adding a denylist of
# comment/docstring prefixes, which would silently miss the next syntactic
# shape provenance shows up in.
#
# Reuses the same emission-site taxonomy as
# `coordinator/tests/fixtures/hook-message-sweeps/population_scan.py`'s
# `scan_emission_sites()` (stderr write, stdout.buffer write, `print(...,
# file=sys.stderr)`, a `hookSpecificOutput` dict-literal key, a subscript
# assignment to one of those keys, and the `_message_envelope`
# compose/emit seam) rather than re-deriving a second detection of what
# counts as "emission" — that module's own docstring is the source of the
# taxonomy this section deliberately mirrors instead of importing directly
# (population_scan.py's own file-selection is scoped to non-underscore
# `coordinator/hooks/scripts/` files only, narrower than PY_SURFACE_DIRS,
# and it returns line numbers only, not the argument/value AST subtree this
# section needs to walk for string literals) -- see that module's own
# docstring for the negative-spec this mirrors: not a text grep, an AST scan
# over the file's *executed* body.
# ---------------------------------------------------------------------------

_PY_EMISSION_DICT_KEYS = frozenset(
    {"additionalContext", "systemMessage", "permissionDecisionReason"}
)
_PY_ENVELOPE_CALLABLES = frozenset({"compose", "emit"})
_PY_STDERR_NAMES = frozenset({"stderr"})


def _py_is_stderr_attr(node: "ast.AST") -> bool:
    """`sys.stderr` or any attribute chain rooted at it (`sys.stderr.buffer`)."""
    if not isinstance(node, ast.Attribute):
        return False
    if (
        node.attr in _PY_STDERR_NAMES
        and isinstance(node.value, ast.Name)
        and node.value.id == "sys"
    ):
        return True
    return _py_is_stderr_attr(node.value)


def _py_is_stdout_buffer_attr(node: "ast.AST") -> bool:
    """`sys.stdout.buffer` only — the byte-fidelity idiom, deliberately
    narrower than `_py_is_stderr_attr` (a bare `sys.stdout.write(...)` does
    not, by itself, indicate a guard-prose emission channel)."""
    if not isinstance(node, ast.Attribute) or node.attr != "buffer":
        return False
    value = node.value
    return (
        isinstance(value, ast.Attribute)
        and value.attr == "stdout"
        and isinstance(value.value, ast.Name)
        and value.value.id == "sys"
    )


def _py_envelope_import_bindings(tree: "ast.AST") -> "tuple[set, dict]":
    """Local names bound to the `_message_envelope` module, and local names
    bound directly to its `compose`/`emit` callables — see
    `population_scan.py::_envelope_import_bindings`, mirrored here."""
    module_aliases: "set" = set()
    callable_aliases: "dict" = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "_message_envelope":
                    module_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module != "_message_envelope":
                continue
            for alias in node.names:
                if alias.name in _PY_ENVELOPE_CALLABLES:
                    callable_aliases[alias.asname or alias.name] = alias.name
    return module_aliases, callable_aliases


def _py_emission_value_nodes(tree: "ast.AST") -> "list[ast.AST]":
    """The argument/value AST subtree carrying the PAYLOAD at each real
    emission site in `tree` — not the whole call/dict node, just the part
    that becomes text a reader sees."""
    module_aliases, callable_aliases = _py_envelope_import_bindings(tree)
    values: "list[ast.AST]" = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr in _PY_ENVELOPE_CALLABLES
                and isinstance(func.value, ast.Name)
                and func.value.id in module_aliases
            ) or (isinstance(func, ast.Name) and func.id in callable_aliases):
                values.extend(node.args)
                values.extend(kw.value for kw in node.keywords)
            elif (
                isinstance(func, ast.Attribute)
                and func.attr == "write"
                and (_py_is_stderr_attr(func.value) or _py_is_stdout_buffer_attr(func.value))
            ):
                values.extend(node.args)
            elif isinstance(func, ast.Name) and func.id == "print":
                if any(
                    kw.arg == "file" and _py_is_stderr_attr(kw.value)
                    for kw in node.keywords
                ):
                    values.extend(node.args)

        if isinstance(node, ast.Dict):
            for key, val in zip(node.keys, node.values):
                if (
                    isinstance(key, ast.Constant)
                    and isinstance(key.value, str)
                    and key.value in _PY_EMISSION_DICT_KEYS
                ):
                    values.append(val)

        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Subscript)
                    and isinstance(target.slice, ast.Constant)
                    and isinstance(target.slice.value, str)
                    and target.slice.value in _PY_EMISSION_DICT_KEYS
                ):
                    values.append(node.value)

    return values


def _py_name_definitions(tree: "ast.AST") -> "dict[str, list]":
    """`name -> [value-expr, ...]` for every simple `Assign`/`AnnAssign`/
    `AugAssign` to a bare `Name` anywhere in the module — deliberately
    scope-agnostic (no per-function shadowing analysis) because the failure
    mode this guards against is a false NEGATIVE (missing a real emitted
    citation because the slice under-traced), and over-tracing a same-named
    local in an unrelated function only risks pulling in a few extra
    genuinely-code string literals, never a docstring/comment — those are
    never reachable from an emission-site value node in the first place.

    `AugAssign` (`nudge += "..." + wrap(...)`) is traced on the same footing
    as `Assign` — wrapping-not-reachability (F1,
    em-finding-wrap-is-not-reachability.md): a message built incrementally
    via `+=` is exactly as reachable from its eventual emission site as one
    built via a single `=`, and the accumulate-then-emit shape is the common
    one for a multi-part nudge string. Omitting it let a citation embedded
    in an `+=` RHS go untraced regardless of whether it was wrapped in a
    format-resolving helper — the wrap was never itself special-cased here;
    the gap was this reachability trace silently stopping at the first
    `AugAssign`, independent of SEED_WIKIS/REAL_WIKI_PAGES membership, which
    is judged unchanged once the line is in scope."""
    defs: "dict[str, list]" = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    defs.setdefault(target.id, []).append(node.value)
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            if isinstance(node.target, ast.Name):
                defs.setdefault(node.target.id, []).append(node.value)
        elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
            defs.setdefault(node.target.id, []).append(node.value)
    return defs


def _py_local_function_params(tree: "ast.AST") -> "dict[str, list]":
    """`function-name -> [positional-and-keyword param names in signature
    order, *args name if present, **kwargs name if present]` for every
    `def`/`async def` in `tree` (module-level or nested — deliberately
    scope-agnostic, same rationale as `_py_name_definitions`)."""
    params: "dict[str, list]" = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names = [a.arg for a in node.args.posonlyargs]
            names.extend(a.arg for a in node.args.args)
            names.extend(a.arg for a in node.args.kwonlyargs)
            params[node.name] = names
    return params


def _py_param_bindings(tree: "ast.AST") -> "dict[str, list]":
    """`param-name -> [argument-value-expr, ...]` collected from every call
    site in `tree` to a LOCALLY-DEFINED function, matched by call target
    name against `_py_local_function_params`. Closes the reachability gap a
    parameter boundary otherwise creates: an emission site that hands its
    payload to a module-local wrapper function (e.g. `_emit_advisory(parts,
    ...)`) as a parameter, rather than composing it inline, previously
    dead-ended at that parameter — a bare function parameter is never an
    `Assign` target, so `_py_name_definitions` alone never resolves it back
    to the caller-built strings actually passed in. Positional args bind by
    signature position; keyword args bind by name; a call target that isn't
    a bare `Name` (a method call, an attribute, a dynamically-computed
    callable) is skipped — deliberately scope-agnostic and over-inclusive
    like its sibling, never under-inclusive, since the failure mode being
    guarded against is a false NEGATIVE."""
    local_params = _py_local_function_params(tree)
    bindings: "dict[str, list]" = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        sig = local_params.get(node.func.id)
        if sig is None:
            continue
        for index, arg in enumerate(node.args):
            if index < len(sig):
                bindings.setdefault(sig[index], []).append(arg)
        for kw in node.keywords:
            if kw.arg is not None and kw.arg in sig:
                bindings.setdefault(kw.arg, []).append(kw.value)
    return bindings


def _emitted_line_numbers(text: str) -> "set | None":
    """Every line number in `text` (a `.py` hook's source) that is
    STRUCTURALLY reachable from a real emission site — i.e. actually
    becomes part of a message an agent reads. Returns `None` on a parse
    failure (caller must then fall back to treating the whole file as
    in-scope rather than silently narrowing to nothing).

    Traces three kinds of reachability from each emission site's value node:
    a string literal (`ast.Constant`, including the literal segments of an
    f-string) directly inside it, a bare `Name` reference inside it resolved
    (transitively) against every simple module-level/function-level
    assignment to that name, and — closing the gap `_py_param_bindings`
    exists for — a `Name` that resolves to a locally-defined function's
    PARAMETER, resolved (transitively) against every argument expression
    passed to that parameter at any local call site. This is what lets a
    hook that builds its message in a `_TEXT = ("...")` constant, an
    f-string interpolating a helper's return value, OR a module-local
    `_emit_advisory(parts, ...)`-style wrapper that receives its payload as
    a parameter, still get its real citations checked — the property this
    guards is "does this string end up in front of an agent", not "is this
    string a direct literal argument".

    KNOWN LIMITATION (untraced direction — RETURN, not parameter): this
    closes the IN direction (payload flows INTO a local helper via a
    parameter) but not the OUT direction (payload flows OUT of a local
    helper via its `return`, back to a `Name` the caller then emits). A
    `Name` resolved to a bare `Call` targeting a locally-defined function is
    walked only as the `Call` node itself (the call and its argument
    expressions) — never descended into that function's own body, where the
    real citation-building lines live. Confirmed live in this repo:
    `runtime-tripwire-em-check.py`'s `push_failure_msg =
    _check_push_failures(git_root, session_id)`, whose `.format(...) +
    resolve_wiki_citation(...)` lines live inside `_check_push_failures`
    itself and are invisible to this trace. No live violation results today
    because that call site already wraps its citations correctly, but a
    future edit inside such a helper that reintroduces a bare
    `docs/wiki/...` literal would pass this `.py`-scoped lint silently. Fix
    shape (not yet implemented): mirror `_py_param_bindings` in the other
    direction — for a `Name` resolved to a `Call` targeting a
    locally-defined function, also walk that function's `Return` statement
    values as additional definition sources. A regression test pinning this
    gap belongs in `coordinator/tests/test_prompt_surfaces_cite_resolvably.py`
    — not added here; test authorship is out of this module's own write
    scope for this dispatch."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None

    defs = _py_name_definitions(tree)
    for name, values in _py_param_bindings(tree).items():
        defs.setdefault(name, []).extend(values)
    lines: "set" = set()
    visited_names: "set" = set()
    stack: "list" = list(_py_emission_value_nodes(tree))

    while stack:
        node = stack.pop()
        if node is None:
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                start = sub.lineno
                end = getattr(sub, "end_lineno", start) or start
                lines.update(range(start, end + 1))
            elif isinstance(sub, ast.Name) and sub.id not in visited_names:
                visited_names.add(sub.id)
                stack.extend(defs.get(sub.id, ()))

    return lines


def _restrict_text_to_lines(text: str, keep: "set") -> str:
    """`text` with every line NOT in `keep` blanked out (length/line-count
    preserved, same technique as `_neutralize_structural_comments`, so line
    numbers in reported violations stay accurate)."""
    lines = text.split("\n")
    return "\n".join(line if (i + 1) in keep else "" for i, line in enumerate(lines))


def iter_violations(text: str, *, path: "Path | None" = None) -> list:
    """Every unresolvable-citation violation in `text`, in line order.

    Pure function over already-loaded text — the caller decides whether that
    text is a whole file (the ratchet test) or a reconstructed before/after
    (the hook, via `new_violations`).

    `path` is optional and additive: when given AND its suffix is `.py`,
    scanning is first restricted to lines reachable from a real emission
    site (see `_emitted_line_numbers` above) — this is what keeps a
    `.py` hook's module docstring / inline comments / `# Review:`
    provenance lines out of scope while still catching a genuinely
    unresolvable citation inside text an agent actually receives. Omitting
    `path` (the existing call shape every consumer of this module already
    uses) preserves the prior full-text behaviour exactly — this is a
    strictly additive, opt-in narrowing, not a default-on behaviour change."""
    if path is not None and path.suffix == ".py":
        emitted = _emitted_line_numbers(text)
        if emitted is not None:
            text = _restrict_text_to_lines(text, emitted)
    text = _neutralize_structural_comments(text)
    lines = text.split("\n")
    violations: list = []
    in_fence = False
    in_frontmatter = False

    for line_no, line in enumerate(lines, start=1):
        stripped = line.strip()
        fingerprint = " ".join(line.split())

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

        if in_frontmatter and _SPEC_BACKLINK_FRONTMATTER_KEY.match(line):
            continue

        for prefix, label in _NONPERCOLATING_TREES:
            start = 0
            while True:
                idx = line.find(prefix, start)
                if idx == -1:
                    break
                after_prefix = line[idx + len(prefix) :]
                suffix = _PATH_TOKEN.match(after_prefix).group(0)
                if _looks_like_specific_file(suffix):
                    violations.append(Violation(line_no, label, _excerpt(line), fingerprint))
                start = idx + len(prefix)

        if SEED_WIKIS:
            for m in _WIKI_CITATION.finditer(line):
                name = m.group(1)
                if name not in SEED_WIKIS and name not in _CONSUMING_REPO_CONVENTION_FILES:
                    violations.append(
                        Violation(
                            line_no,
                            f"non-seed wiki citation: docs/wiki/{name}",
                            _excerpt(line),
                            fingerprint,
                        )
                    )

        if SEED_WIKIS and REAL_WIKI_PAGES:
            for pattern in (_BARE_WIKI_PAGE_TOKEN, _WIKI_SHORT_PREFIX_TOKEN):
                for m in pattern.finditer(line):
                    name = m.group(1)
                    if name not in REAL_WIKI_PAGES or name in _CONSUMING_REPO_CONVENTION_FILES:
                        continue
                    if name in SEED_WIKIS:
                        continue
                    if _preceded_by_placeholder(line, m.start()):
                        continue
                    violations.append(
                        Violation(
                            line_no,
                            f"non-seed wiki citation, de-prefixed: {name}",
                            _excerpt(line),
                            fingerprint,
                        )
                    )

        sentinel_spans = _literal_sentinel_spans(line)
        for m in _DR_ID.finditer(line):
            if any(lo <= m.start() < hi for lo, hi in sentinel_spans):
                continue
            violations.append(
                Violation(
                    line_no,
                    f"bare decision-record id: {m.group(0)}",
                    _excerpt(line),
                    fingerprint,
                )
            )

    return violations


def _violation_key(v: Violation) -> tuple:
    """Identity used for before/after delta comparison — kind + the FULL
    normalized line, deliberately NOT line number (an edit elsewhere in the
    file can shift line numbers for content the edit never touched, which
    would make an untouched violation look "new" and false-deny on every
    such edit -- rejected explicitly for that reason, see Finding 5 in this
    module's review sidecar).

    Deliberately NOT `v.excerpt` either, despite looking like the obvious
    choice: `excerpt` is truncated to 90 chars for display, so two distinct
    long citations that happen to share their first 90 normalized-whitespace
    characters would collide and could cancel out in the multiset delta
    (undercounting -- a new violation absorbed into the "already existed"
    bucket). `line_fingerprint` is the same normalization, untruncated, so
    it keeps the line-shift-safety property while fixing the truncation
    collision."""
    return (v.kind, v.line_fingerprint)


def new_violations(before: str, after: str, *, path: "Path | None" = None) -> list:
    """Violations present in `after` that were NOT already present in
    `before`, as a multiset difference keyed by `_violation_key`.

    `path` is optional and forwarded unchanged to `iter_violations` on both
    sides of the diff (see that function's docstring) — omitting it (every
    existing caller, including `guard-prompt-surface-citations.py`) keeps
    this function's behaviour exactly as before.

    This is what makes a hard-deny guard built on this function safe against
    the existing corpus's ~550 legacy violations: a file that already has a
    bad citation sitting untouched contributes the SAME count to both
    `before` and `after`, so the delta for it is zero regardless of how many
    times the guard fires against that file. Only a violation the CURRENT
    write introduces — one absent from `before` and present in `after` —
    survives the subtraction. Guard authors: do not call `iter_violations`
    directly on a post-write file and diff a hard-deny decision off its raw
    count; that re-flags every legacy violation on every future edit to the
    same file, which is exactly the wedge this function exists to avoid.
    """
    before_counts = Counter(_violation_key(v) for v in iter_violations(before, path=path))
    after_violations = iter_violations(after, path=path)
    after_counts = Counter(_violation_key(v) for v in after_violations)
    delta = after_counts - before_counts
    if not delta:
        return []
    result: list = []
    seen: Counter = Counter()
    for v in after_violations:
        key = _violation_key(v)
        if seen[key] < delta.get(key, 0):
            result.append(v)
            seen[key] += 1
    return result
