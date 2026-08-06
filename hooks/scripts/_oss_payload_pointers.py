"""Dangling-pointer detector for coordinator prompt surfaces, built around the
repo-boundary manifest that separates "cites a tree that ships via the engine
repo" from "cites a tree that simply is not there."

WHY THIS IS A SEPARATE MODULE FROM `_prompt_surface_citations.py`
    That sibling module asks "is the TARGET reachable for a non-local reader"
    (a `docs/plans/…` path, a bare `DR-` id, a non-seed wiki page — none of
    which percolate at all). This module asks a narrower, structurally
    different question: for a target that DOES look like it should resolve
    somewhere in the shipped payload, does it actually exist anywhere a
    reader with the coordinator plugin installed could find it? The two
    questions overlap in places (both would flag a citation of a retired
    file) and that overlap is fine — they check different properties of the
    same construct, exactly as that module's own docstring says about its
    relationship to the provenance gate.

THE HARD PART IS NOT THE EXISTENCE CHECK
    `coordinator/bin/` and `coordinator/lib/` are tracked as 0 and 2 files
    respectively IN THIS CLONE — the executable surface migrated wholesale to
    the `claude-klabauter` engine repo on 2026-07-22 (see `_oss_payload.py`'s
    module docstring). A citation of `coordinator/bin/wsc-close.py` is
    CORRECT: it resolves for a reader with the plugin installed, because that
    tree ships via `_oss_payload.py`'s `source_map` routing even though it is
    absent from THIS working tree. A citation of `coordinator/scripts/
    install-maximalist.py` is a GENUINE dangling pointer: `scripts/` is also
    engine-resident (the script lives under the resolved engine root), but it
    is named in NEITHER the allowlist NOR `source_map` — it does not ship,
    full stop. No textual heuristic separates these two shapes; only the
    allowlist + source_map composition (`_oss_payload.parse_mirror_row()`)
    does.

THE MANIFEST'S ENTRY RULE (stated explicitly — sharper than "derive from
source_map" conveys, and the next reader must not "fix" `scripts/` into it):
  - A tree that is BOTH allowlisted AND named in `source_map` ships AND is
    engine-resident, so it resolves for a reader with the plugin installed
    -> SKIP the existence check entirely; do not require it to exist here.
  - A tree that is engine-resident (would resolve against a sibling repo
    root) but NOT allowlisted does NOT ship. A citation of it is a real
    dangling pointer -> FLAG. `coordinator/scripts/` is exactly this shape:
    do not add it to the skip manifest to quiet a "false positive" that is
    in fact the class this module exists to catch.

PREFIX NORMALIZATION
    The corpus cites the same engine-resident trees in at least five
    distinct prefixed forms (bare `coordinator/bin/…`, `$CLAUDE_PLUGIN_ROOT/
    coordinator/lib/…`, an angle-bracketed engine-root placeholder followed by
    `/coordinator/lib/…`, the same with `/coordinator/bin/…`, and a shell
    variable holding the engine root followed by `/coordinator/scripts/…`), and
    `${CLAUDE_PLUGIN_ROOT}` on its own resolves to the plugin root, which
    lands ON the `coordinator/` directory rather than above it — so
    `${CLAUDE_PLUGIN_ROOT}/skills/…` never contains the literal substring
    `coordinator/` at all. `_normalize_citation` handles both shapes:
    anchoring on a literal `coordinator/` substring wherever it occurs in the
    token (so any prefix before it — an env var, a root placeholder, a
    quote — is irrelevant to classification), and treating a
    `${CLAUDE_PLUGIN_ROOT}`/`$CLAUDE_PLUGIN_ROOT` prefix as an implicit
    `coordinator/` root. `_OBSERVED_ENGINE_CITATION_PREFIXES` records the five
    forms seen in the corpus and is exercised by
    `test_oss_payload_pointers_resolve.py` precisely so this normalization is
    proven against the actual shapes rather than only the mechanism's own
    self-consistency.

SCOPE — DELIBERATELY NARROW (v1)
    Only two citation SHAPES count: a token inside an inline code span
    (`` `...` ``) and a markdown link target (`[text](target)`). A first-pass
    extractor that also matched bare prose produced ~450 apparent dangling
    pointers across 244 targets with ~55% false positives, bare prose being
    the dominant source — a rule whose yield is majority noise is not worth
    tightening. If bare-prose citation becomes worth catching later, that is
    a deliberate widening of THIS module, not a reason to route around it.

    SCOPE IS ALSO NARROW ON *TARGET VOCABULARY*, not just citation shape, for
    the same measured reason. A `coordinator/…`-anchored token (the engine-
    boundary class this module exists for) is checked unconditionally — that
    tree structure is stable and existing-vs-not is exactly this module's
    question. A token with NO `coordinator/` anchor is checked only when it
    names one of the four known flat-file-vs-directory migration targets
    (`_MIGRATED_FLAT_FILES`) — anything else in that shape (`package.json`,
    `settings.json`, a bare script name, a generic `PIPELINE.md` output-file
    example) is a CONSUMING-repo convention, an illustrative filename, or
    already the sibling module's domain (`docs/wiki/*.md`, `docs/plans/…`,
    `state/{handoffs,lessons,review-trail}/…`), never a citation this module
    can validate against `REPO_ROOT` without duplicating that module's job or
    manufacturing false positives. Measured: an unrestricted "does this
    repo-relative-looking token exist at REPO_ROOT" check produced 1247
    "dangling" hits across 136 files before this narrowing, the overwhelming
    majority bare generic filenames with no directory component at all
    (`script.sh` × 28, `settings.json` × 21, `package.json` × 15, …) or
    `docs/wiki/*.md` seed-wiki citations the sibling module already resolves
    correctly via its own (mirror-aware) `SEED_WIKIS` set — this module's
    plain `Path.exists()` has no notion of the wiki's flat-mirror relocation
    and would flag every one of those as dangling. `_MIGRATED_FLAT_FILES` is
    an intentionally short, explicit allowlist of the one non-`coordinator/`
    class this module DOES validate — the known-answer corpus it is proven
    against — not a general-purpose repo-relative existence checker.

FALSE-POSITIVE SOURCES THIS MODULE IS BUILT TO AVOID (each named, not just
avoided by accident):
  - The lookbehind bug: an earlier extractor sliced by regex lookbehind
    excluding `\\w`, `/`, and backtick but not `-` or `.`, mis-slicing
    `${CLAUDE_PLUGIN_ROOT}/skills/finishing-a-development-branch/SKILL.md`
    into `a-development-branch/SKILL.md` and `~/.claude/…` into `claude/…`.
    This module never slices with a lookbehind — it splits on whitespace and
    classifies the whole resulting word, so there is no boundary to get
    wrong.
  - Placeholder tokens: `<...>`, `*`, `{...}`, `$...`, and now `[...]` (the
    deep-research pipeline templates' `[SCRATCH_DIR]`/`[RUN_ID]` forms, which
    an earlier pass counted because its placeholder set omitted brackets).
  - A `~`-rooted path (`~/.claude/…`) is the READER'S OWN home directory, not
    a citation of a document only this clone has — never flagged.
  - A `<sha>[~^]:path` git-revision reference (`git show 434365dcb^:state/
    lessons.md`) names a HISTORICAL tree, not the current one — never
    flagged; the parent-commit content it names is not expected to exist in
    the current working tree at all.
  - A conditionally-hedged citation ("read `state/foo.md` if it exists")
    correctly acknowledges the target may be absent — `_HEDGE_PHRASES` skips
    the whole line when one of a short list of hedge phrases is present,
    rather than flagging every citation on it as an unconditional assertion.

FAIL-LOUD vs FAIL-OPEN
    `_skip_entries()` reads the SAME ratified allowlist `_oss_payload.py`
    already parses — no second hand-maintained directory tuple. If that
    parse fails, this module lets the exception propagate (fail-loud): a
    silently-empty skip manifest would misclassify every `bin`/`lib`
    citation as a dangling pointer, which is a wrong verdict, not a narrowed
    one — there is no safe degraded mode here, unlike the sibling module's
    `SEED_WIKIS`/`STRUCTURAL_MARKERS` fail-open contract (those degrade one
    detection class; this module's manifest IS the detection).

WRITE-TIME GUARD: DELIBERATELY NOT BUILT YET
    Per the plan this module serves: arm the ratchet test only. A pointer
    check that cries wolf gets disarmed, and the class then goes unwatched
    behind a green test — so the write-time guard is a later chunk, gated on
    this detector holding a zero false-positive rate on the current corpus.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

import _oss_payload  # noqa: E402
import _prompt_surface_citations as _surfaces  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]

#: Reused verbatim from the sibling citation detector rather than re-derived —
#: same five percolating trees, same tests/fixtures exemption. See that
#: module's own docstring for why `templates/`/`schemas/`/`dist/` are
#: deliberately excluded.
iter_prompt_surface_files = _surfaces.iter_prompt_surface_files
is_in_scope = _surfaces.is_in_scope


@dataclass(frozen=True)
class Violation:
    line_no: int
    kind: str
    target: str
    excerpt: str
    line_fingerprint: str = ""


# ---------------------------------------------------------------------------
# The engine-resident skip manifest — derived from the allowlist, never
# hand-maintained. See module docstring "THE MANIFEST'S ENTRY RULE".
# ---------------------------------------------------------------------------


def _skip_entries() -> frozenset:
    """Allowlist top-level entries that are BOTH `source_map`-routed AND
    present in the allowlist itself — the only entries that ship from the
    engine repo. Fails loud (propagates) on a malformed/missing allowlist
    row: see module docstring's FAIL-LOUD section."""
    row = _oss_payload.parse_mirror_row()
    allowlist = set(row.allowlist)
    routed: set = set()
    for entries in row.source_map.values():
        routed.update(entries)
    return frozenset(e for e in routed if e in allowlist)


def _ignore_patterns() -> tuple:
    """`coordinator/.percolate-ignore`'s parsed exclusion patterns, reused
    verbatim from `_oss_payload.py` (the module that already owns this parse)
    rather than re-parsed here — a second hand-maintained copy is exactly the
    drifting-duplicate failure that module's own composition exists to
    prevent. This is the THIRD layer the manifest is missing without this
    call: allowlist + `source_map` alone overstate what ships, because
    `.percolate-ignore` then excludes specific subtrees (`bin/tests/`,
    `hooks/scripts/tests/`, `lib/tests/`, `snippets/registry.toml`, …) from
    entries that are otherwise allowlisted and source_map-routed."""
    return _oss_payload.excluded_patterns()


def _coarse_dir_entries() -> frozenset:
    """Allowlist entries that are bare top-level directory admissions (no
    `/` and no `.` in the entry itself — today: `bin`, `lib`, `hooks`,
    `skills`, `agents`, `commands`, `snippets`, `whoami`) as opposed to an
    INDIVIDUALLY curated file-level allowlist entry (e.g. one specific
    `docs/wiki/<page>.md`, `subagent-sandbox-policy.yaml`, `.claude-plugin`).

    Only a coarse directory admission can have an internal subtree carved
    back out by `.percolate-ignore` (`bin/tests/`, `hooks/scripts/tests/`,
    `lib/tests/`, `snippets/registry.toml`) — that is the shape every
    existing exclusion pattern actually targets. `docs` is never a bare
    entry here: every `docs/…` path this repo ships is individually
    allowlisted one file at a time, and `.percolate-ignore`'s directory-
    shaped `docs/` pattern is a DIFFERENT, unrelated rule (it keeps the main
    mirror's raw `docs/` tree walk from colliding with the dedicated
    install-target mirror — see that file's own header) that happens to
    textually overlap every `docs/…` path including the individually
    allowlisted ones. Applying the exclusion check to a non-coarse entry
    would therefore misclassify an explicitly-shipped, individually
    allowlisted file (e.g. `coordinator/docs/wiki/scoped-safety-commits.md`)
    as excluded — measured: this was the one false-positive class the
    exclusion check produced before this scoping was added."""
    row = _oss_payload.parse_mirror_row()
    return frozenset(e for e in row.allowlist if "/" not in e and "." not in e)


def _excluded_from_payload(rel_str: str, ignore_patterns: tuple) -> bool:
    """True if a `coordinator/`-relative candidate (e.g. `coordinator/bin/
    tests/foo.py`) falls inside a `.percolate-ignore`-excluded subtree — i.e.
    it never ships even though it is tracked/allowlisted. `rel_str` already
    carries its leading `coordinator/`; `.percolate-ignore` patterns are
    matched relative to that same root, so the prefix is stripped before
    reusing `_oss_payload`'s own matcher. Callers must first confirm the
    candidate's top-level entry is a coarse directory admission (see
    `_coarse_dir_entries`) — this function has no knowledge of that
    restriction itself."""
    rel_to_coordinator = rel_str[len("coordinator/") :]
    return _oss_payload._is_excluded(rel_to_coordinator, ignore_patterns)


#: Observed citation-form PREFIXES that precede `coordinator/{entry}/` in the
#: corpus for `source_map`-routed entries — kept explicit and exercised by the
#: ratchet test (not just implicitly relied upon by `_normalize_citation`'s
#: anchor-strip below) so a reader can see the five forms this detector is
#: actually proven against. `_normalize_citation` is a strict superset of
#: this list (it anchors on ANY prefix before a literal `coordinator/`), so a
#: sixth unlisted form still classifies correctly — this tuple documents and
#: tests the corpus's actual shapes, it does not gate the mechanism.
_OBSERVED_ENGINE_CITATION_PREFIXES = (
    "",  # bare `coordinator/{entry}/...`
    "$CLAUDE_PLUGIN_ROOT/",
    "<claude-klabauter-root>/",
    "<claude-klabauter-root>/",
    '"$_cc_claude_klabauter/',
)


# ---------------------------------------------------------------------------
# Token classification
# ---------------------------------------------------------------------------

_PLACEHOLDER_CHARS = ("<", ">", "*", "{", "}", "$", "[", "]")
#: Derived from extensions actually observed among `coordinator/`-anchored
#: citations in the corpus (measured alongside the other narrowing decisions
#: in this module) — not a general-purpose extension allowlist.
_FILE_EXTENSION = re.compile(r"\.(md|ya?ml|py|json|jsonl|sh|txt|js|toml)(?![\w-])")
_URL = re.compile(r"^\w+://")
_GIT_REV_REF = re.compile(r"[0-9a-f]{6,40}[\^~]*:")
_PLUGIN_ROOT_PREFIX = re.compile(r"^\"?\$\{?CLAUDE_PLUGIN_ROOT\}?/")

#: A trailing `:38` or `:62-76` line-locator anchor on an otherwise-real
#: file citation (`coordinator/skills/plan/SKILL.md:38`) — stripped before
#: the existence check, which must resolve the FILE, not the anchored
#: substring. Left in place would make every line-anchored cross-reference
#: to a real, existing sibling file misclassify as dangling.
_LINE_LOCATOR_SUFFIX = re.compile(r":\d+(?:-\d+)?$")

#: A pytest node-id suffix (`::TestClass::test_method`) on an otherwise-real
#: file citation — same shape of false positive as the line-locator above,
#: from a `pytest: path.py::Class::test` cell in a test-surface table.
_PYTEST_NODE_ID_SUFFIX = re.compile(r"::.*$")

#: `coordinator/CLAUDE.md` was retired 2026-07-27 and is cited ~40 times in
#: changelog-voice parentheticals ("(coordinator/CLAUDE.md retired
#: 2026-07-27)"). That population belongs to the existing provenance gate
#: (`test_prompt_surfaces_carry_no_provenance.py`), which already refuses
#: changelog voice naming a retired file — routing it there rather than
#: re-handling the same finding under a second mechanism (per this plan's
#: own AC8c). Excluded here so this module's baseline doesn't duplicate a
#: population another gate already owns.
_ROUTED_TO_PROVENANCE_GATE = frozenset({"coordinator/CLAUDE.md"})

_LEADING_STRIP = "\"'([{"
_TRAILING_STRIP = "\"'.,;:)]}"

#: The one non-`coordinator/`-anchored citation class this module validates —
#: see module docstring "SCOPE IS ALSO NARROW ON TARGET VOCABULARY". This is
#: the known-answer corpus (`test_oss_payload_pointers_resolve.py`'s
#: round-trip against the commits that repointed these).
_MIGRATED_FLAT_FILES = frozenset(
    {
        "state/lessons.md",
        "state/bug-backlog.md",
        "state/debt-backlog.md",
        "state/improvement-queue.md",
    }
)

_CODE_SPAN = re.compile(r"`([^`\n]+)`")
_MD_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_FENCE = re.compile(r"^\s*```")

#: A citation on a line carrying one of these phrases is a correctly-hedged
#: conditional read ("if it exists"), not an unconditional assertion the
#: target is resolvable — see module docstring.
_HEDGE_PHRASES = (
    "if it exists",
    "if present",
    "if this exists",
    "if that exists",
    "if any exist",
    "if it doesn't exist",
    "if it does not exist",
    "may not exist",
    "may not yet exist",
    "does not yet exist",
)


def _clean_token(token: str) -> str:
    return token.strip(_LEADING_STRIP + _TRAILING_STRIP)


def _normalize_citation(token: str) -> "tuple[bool, str]":
    """(is_coordinator_relative, rel_str).

    `rel_str` is always relative to `REPO_ROOT` when `is_coordinator_relative`
    is False, and relative to `REPO_ROOT` with a leading `coordinator/`
    already included when True — i.e. `REPO_ROOT / rel_str` is the candidate
    path in both cases. A `${CLAUDE_PLUGIN_ROOT}`/`$CLAUDE_PLUGIN_ROOT` prefix
    is treated as an implicit `coordinator/` root (that env var resolves TO
    the plugin root, which IS this repo's `coordinator/` directory — see
    module docstring); anything else is anchored on the first literal
    `coordinator/` substring, wherever it occurs, so any prefix before it
    (an env var, a root placeholder, a quote character) never has to be
    enumerated to be handled correctly.
    """
    anchor = token.find("coordinator/")
    if anchor != -1:
        return True, token[anchor:]
    m = _PLUGIN_ROOT_PREFIX.match(token)
    if m:
        return True, "coordinator/" + token[m.end() :]
    return False, token


def classify_token(
    token: str,
    skip_entries: frozenset,
    ignore_patterns: "tuple | None" = None,
    coarse_dir_entries: "frozenset | None" = None,
) -> str:
    """Classify one already-extracted (backtick or markdown-link) citation
    token. Returns one of:
      - "not-a-citation" — a directory convention, a placeholder-bearing
        template, a URL, a home-dir path, a historical git-revision
        reference, or anything else that is not a concrete file citation.
      - "resolved-engine" — under an allowlisted + source_map-routed tree
        AND not `.percolate-ignore`-excluded; ships from the engine repo,
        never checked for local existence.
      - "resolved-local" — exists in this working tree and is not
        `.percolate-ignore`-excluded.
      - "dangling" — looks like a concrete file citation, and either is not
        engine-resident-and-shipped, does not exist locally, or falls inside
        a `.percolate-ignore`-excluded subtree of an otherwise-shipping tree.

    `ignore_patterns` and `coarse_dir_entries` each default to a fresh read
    when omitted — callers classifying many tokens in one pass (e.g.
    `iter_violations`) should compute both once and pass them through.
    """
    if ignore_patterns is None:
        ignore_patterns = _ignore_patterns()
    if coarse_dir_entries is None:
        coarse_dir_entries = _coarse_dir_entries()
    token = _clean_token(token)
    if not token:
        return "not-a-citation"
    if _URL.match(token):
        return "not-a-citation"
    if token.startswith("~"):
        return "not-a-citation"
    if _GIT_REV_REF.search(token):
        return "not-a-citation"

    is_coord, rel_str = _normalize_citation(token)

    if any(ch in rel_str for ch in _PLACEHOLDER_CHARS):
        return "not-a-citation"
    if rel_str.endswith("/") or not rel_str:
        return "not-a-citation"
    if not _FILE_EXTENSION.search(rel_str):
        return "not-a-citation"

    rel_str = _LINE_LOCATOR_SUFFIX.sub("", rel_str)
    rel_str = _PYTEST_NODE_ID_SUFFIX.sub("", rel_str)

    if rel_str in _ROUTED_TO_PROVENANCE_GATE:
        return "not-a-citation"

    if is_coord:
        parts = rel_str.split("/")
        entry = parts[1] if len(parts) > 1 else ""
        if entry in coarse_dir_entries and _excluded_from_payload(rel_str, ignore_patterns):
            return "dangling"
        if entry in skip_entries:
            return "resolved-engine"
        return "resolved-local" if (REPO_ROOT / rel_str).exists() else "dangling"

    if rel_str not in _MIGRATED_FLAT_FILES:
        return "not-a-citation"
    return "resolved-local" if (REPO_ROOT / rel_str).exists() else "dangling"


def _excerpt(line: str) -> str:
    return " ".join(line.split())[:90]


def _extract_tokens(line: str) -> "list[str]":
    """Every backtick-span word and markdown-link target on `line` —
    the two citation SHAPES this module deliberately limits itself to (see
    module docstring "SCOPE"). A backtick span is split on whitespace so a
    multi-word span (`` `python3 coordinator/scripts/foo.py` ``) still
    yields its path-shaped word."""
    tokens: "list[str]" = []
    for m in _CODE_SPAN.finditer(line):
        tokens.extend(m.group(1).split())
    for m in _MD_LINK.finditer(line):
        target = m.group(1).split("#", 1)[0]
        if target:
            tokens.append(target)
    return tokens


def iter_violations(text: str) -> "list[Violation]":
    """Every dangling-pointer violation in `text`, in line order. Pure
    function over already-loaded text, mirroring
    `_prompt_surface_citations.iter_violations`'s shape."""
    skip_entries = _skip_entries()
    ignore_patterns = _ignore_patterns()
    coarse_dir_entries = _coarse_dir_entries()
    lines = text.split("\n")
    violations: "list[Violation]" = []
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
        if in_fence or in_frontmatter:
            continue

        lowered = line.lower()
        if any(phrase in lowered for phrase in _HEDGE_PHRASES):
            continue

        for token in _extract_tokens(line):
            verdict = classify_token(token, skip_entries, ignore_patterns, coarse_dir_entries)
            if verdict == "dangling":
                violations.append(
                    Violation(
                        line_no=line_no,
                        kind=f"dangling pointer: {_clean_token(token)}",
                        target=_clean_token(token),
                        excerpt=_excerpt(line),
                        line_fingerprint=fingerprint,
                    )
                )

    return violations


def _violation_key(v: Violation) -> str:
    """Identity for a before/after multiset diff — the CLASSIFIED,
    normalized target (post `_normalize_citation`), deliberately NOT the raw
    `kind`/`line_fingerprint` text. Used across the mirror/source boundary
    (`test_oss_payload_mirror_vantage.py`), where the raw cited text can
    legitimately differ without the underlying dangling pointer being any
    different: publish-time operator/sibling-repo-name depersonalization
    rewrites literal prefixes (e.g. `coordinator-claude/coordinator/…` in
    source becomes `coordinator/…` in the published mirror). Keying on raw
    text would misread that rewrite as a brand-new violation; keying on the
    same normalized target this module already classifies by treats it as
    the unchanged pointer it is."""
    _is_coord, rel_str = _normalize_citation(v.target)
    return rel_str


def new_violations(before: str, after: str) -> "list[Violation]":
    """Violations present in `after` that were not already present in
    `before`, as a multiset difference — same contract as the sibling
    detectors' `new_violations`. Used by the mirror-vantage check to ask a
    content-level question ("does the mirror carry a dangling pointer this
    source snapshot does not?") rather than a raw before/after count
    comparison, which cannot distinguish an unchanged violation that merely
    shifted lines (or was rewritten by a publish-time text transform) from a
    genuinely new one."""
    before_counts = Counter(_violation_key(v) for v in iter_violations(before))
    after_violations = iter_violations(after)
    after_counts = Counter(_violation_key(v) for v in after_violations)
    delta = after_counts - before_counts
    if not delta:
        return []
    result: "list[Violation]" = []
    seen: Counter = Counter()
    for v in after_violations:
        key = _violation_key(v)
        if seen[key] < delta.get(key, 0):
            result.append(v)
            seen[key] += 1
    return result


def iter_engine_boundary_targets(text: str) -> "set[str]":
    """Every normalized target in `text` whose classification depends on the
    engine-resident skip manifest (today: a `coordinator/{bin,lib,scripts}/…`
    or `${CLAUDE_PLUGIN_ROOT}/…` citation) — the exact ambiguous class this
    module exists to resolve. Used by the ratchet test to enumerate and hand-
    classify the acceptance-bar sample; not itself a violation check."""
    skip_entries = _skip_entries()
    targets: set = set()
    lines = text.split("\n")
    in_fence = False
    for line in lines:
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for token in _extract_tokens(line):
            token = _clean_token(token)
            if not token:
                continue
            is_coord, rel_str = _normalize_citation(token)
            if not is_coord:
                continue
            if any(ch in rel_str for ch in _PLACEHOLDER_CHARS):
                continue
            parts = rel_str.split("/")
            entry = parts[1] if len(parts) > 1 else ""
            if entry in ("bin", "lib", "scripts"):
                targets.add(rel_str)
    return targets
