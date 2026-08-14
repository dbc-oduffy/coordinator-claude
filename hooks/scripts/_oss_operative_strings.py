"""Ratified classification data for `_prompt_surface_locality.py`'s
operative-string carve-out — the table of private sibling-repo-name literals
that are LOAD-BEARING (a wire value a live mechanism matches against) rather
than ATTRIBUTION PROSE (a mention that costs an OSS reader something and
carries no working reference back).

Two of the historically-considered four classes are DERIVABLE, not
curatable, and are computed here rather than hand-listed — see
`mcp_tool_prefixes()` and `is_identifier_shape_operative()`:

  - MCP tool-name prefixes (`mcp__project-rag__*`, `mcp__example_game_repo-control__*`)
    are derived from `coordinator/mcp-topology.yaml`, which already declares
    every first-party MCP server's `configKey`. Adding a server there makes
    its prefix exempt automatically — no edit here.
  - An env-var or dotted/hyphenated registry-key IDENTIFIER TOKEN that has a
    sibling repo's name embedded as one of its `_`/`.`-delimited components
    (`CLAUDE_KLABAUTER_ROOT`, `REPO_CLAUDE_KLABAUTER`, `repos.claude_klabauter`,
    `plugin.mirrors.claude-klabauter.source_path`) is operative regardless of
    which specific token it is — this is ONE SHAPE RULE
    (`is_identifier_shape_operative`), not four entries, and it covers every
    future sibling name with no per-name edit either.
  - A MINTED STABLE ARTIFACT ID whose slug carries a sibling repo's name as a
    `-`-delimited component (`pln-claude-klabauter-driven-ceremony-redesig-c7fe9a`) is
    a citation of a private DOCUMENT, not a mention of a private REPO. It is
    the same class as the `docs/plans/<slug>.md § Cn` path form the shape
    rule above already exempts incidentally — a path's `.md` supplies the dot
    that rule's precondition demands — and the fleet's spec-backlink
    convention now mints ids in place of those paths, so the two shapes cite
    the same record and cost an OSS reader the same string. This is a second
    SHAPE RULE (`is_stable_artifact_id`) keyed off the RATIFIED id scheme,
    not a per-id list.

What is left, `IRREDUCIBLE_LITERALS` below, is the residue neither rule
reaches: a BARE sibling-repo-name string that a live fallback mechanism
matches against directly, with no identifier shape and no substitute.

ENTRY CRITERION for `IRREDUCIBLE_LITERALS` — read this before adding to it:
an entry qualifies ONLY when removing the literal breaks a live tool call or
a cross-repo wire-key match WITH NOTHING TO SUBSTITUTE. "The test is red" is
EXPLICITLY NOT a qualification — that is the silent-widening failure this
criterion exists to block. This is a closed list, edited deliberately, in
one place — never an inline suppression marker (an inline `<!-- oss-ok -->`
escape hatch is indistinguishable from remediation at review time and would
launder the ratchet).

Each entry is scoped to the exact `(file, line)` site its rationale names,
not to the bare literal wherever it recurs. A bare-string exemption would
also exempt every OTHER mention of the same literal in the same file (and
every other file) — including ordinary attribution prose that happens to
use the identical word, which is the actual defect this ratchet exists to
catch, not a case for the exemption to swallow. Scoping to the named site
keeps the exemption exactly as wide as its own justification and no wider.

SIBLING_REPO_RECORD is a name-keyed record assembled from TWO distinct
sources, because it answers two distinct questions:

  - "which sibling does the publish `source_map` route to" is sourced from
    `_oss_payload._ENGINE_REPO_NAME` — the one sibling repo this fleet's
    OSS-payload machinery already knows about, kept to a single source of
    truth. A future second sibling gets added there (and its `source_map`
    row), not invented here first. This arm alone is subject to fail-open
    degradation: an `_oss_payload` import failure narrows it to nothing.
  - "can an OSS reader follow this pointer" is a DIFFERENT question — one
    `_ENGINE_REPO_NAME` cannot answer for this repo: private,
    published verbatim to the OSS mirror, with every property the detector
    guards, but with no `source_map` row and never one, because it is not a
    publish-routing target. Those two names are declared as literals below
    (`_PINNED_UNREACHABLE_RECORD`) rather than sourced from any table — see
    that constant's own docstring for why no such table exists in this repo
    to derive from. This arm is NOT subject to fail-open degradation: it is
    declared in-module and resolves on a fresh clone by construction.

`SIBLING_REPO_NAMES` is kept as a derived tuple view over the union, for
callers that only need the bare name set.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[3]
_MCP_TOPOLOGY_PATH = REPO_ROOT / "coordinator" / "mcp-topology.yaml"


def _engine_sibling_record() -> dict:
    """Fail-open, matching every other loader in this module and in
    `_prompt_surface_locality.py`: an import or attribute-read failure
    degrades to an EMPTY dict, never a hardcoded copy of the name this
    function exists to source from a single place. A hardcoded fallback here
    would silently keep working on a stale value if `_oss_payload` is ever
    renamed or the engine repo's canonical name changes, instead of
    surfacing the drift.

    The record's `short_forms`/`case_sensitive` reproduce exactly the legacy
    derive-from-trailing-part, case-insensitive behavior
    `_prompt_surface_locality._normalize_sibling_record` used to compute
    from a bare tuple, so this split does not change matching behavior for
    the engine-sibling name."""
    try:
        import _oss_payload  # local import: avoids a hard import-time dependency
    except Exception:
        return {}
    name = getattr(_oss_payload, "_ENGINE_REPO_NAME", None)
    if not (isinstance(name, str) and name):
        return {}
    norm = name.replace("-", "_")
    parts = norm.split("_")
    short_forms = (parts[-1],) if len(parts) > 1 else ()
    return {
        name: {
            "is_engine_sibling": True,
            "oss_reachable": False,
            "short_forms": short_forms,
            "aliases": (),
            "case_sensitive": False,
        }
    }


#: Declared literals, not derived from any table — see module docstring.
#: No in-repo table plays that role here on a fresh OSS clone with no
#: machine-local registry present (the plan's Anti-scope entry rules out the
#: candidates: `_ENGINE_REPO_NAME` answers the sibling-routing question, not
#: the OSS-reachability one; the machine-local `repos.*` registry and
#: `.doe-root` are runtime-detected and absent by design on a fresh install;
#: `percolate-store.yaml`'s keep-set governs the publish transform, not
#: detector input). The first name below is this repo: private, published
#: verbatim to the OSS mirror, with no `source_map` row and never one,
#: because it is not a publish-routing target. The second is its short
#: form, declared separately because `_sibling_name_pattern` derives short
#: forms only from a record entry's own declared `short_forms`, never from
#: another entry's name.
_PINNED_UNREACHABLE_RECORD: dict = {
    "DoE-claude": {
        "is_engine_sibling": False,
        "oss_reachable": False,
        "short_forms": (),
        "aliases": (),
        "case_sensitive": True,
    },
    "DoE": {
        "is_engine_sibling": False,
        "oss_reachable": False,
        "short_forms": (),
        # Review: no-op duplicate of this entry's own key (already in
        # `forms` via `_sibling_name_pattern`'s `{name, norm}` seed);
        # `()` matches the sibling entry's convention for "no distinct
        # alias declared".
        "aliases": (),
        "case_sensitive": True,
    },
}


def _sibling_repo_record() -> dict:
    """The union: the engine-sibling arm (fail-open, may be empty) plus the
    pinned-unreachable literals (never empty, resolve on a fresh clone by
    construction — see module docstring's fail-open interaction note)."""
    record: dict = {}
    record.update(_engine_sibling_record())
    record.update(_PINNED_UNREACHABLE_RECORD)
    return record


#: Name-keyed record — see module docstring. The consumer
#: (`_prompt_surface_locality._raw_sibling_source`) looks for this exact
#: attribute name first, falling back to the legacy `SIBLING_REPO_NAMES`
#: tuple when absent.
SIBLING_REPO_RECORD: dict = _sibling_repo_record()

#: Derived view over `SIBLING_REPO_RECORD` — kept exported for other callers
#: that still read the bare name tuple. Filtered to `oss_reachable is False`
#: to match `_prompt_surface_locality.SIBLING_REPO_NAMES`'s filter — this
#: identifier means the same thing in both modules; a future
#: `oss_reachable: True` entry stays excluded from BOTH exports rather than
#: silently drifting into one and not the other.
SIBLING_REPO_NAMES: tuple = tuple(
    name for name, data in SIBLING_REPO_RECORD.items() if data.get("oss_reachable") is False
)

#: Genuinely irreducible bare-literal residue. See module docstring's ENTRY
#: CRITERION before adding to this tuple. Each entry is a
#: (literal, file, line, reason) tuple: `file` is the repo-relative POSIX
#: path and `line` the line number of the exact site the exemption covers —
#: the literal is exempt ONLY there, never at any other occurrence of the
#: same string, including elsewhere in the same file. The rationale ships
#: alongside the literal instead of drifting into a separate changelog no
#: one re-reads.
IRREDUCIBLE_LITERALS: tuple = (
    (
        "claude-klabauter",
        "coordinator/hooks/scripts/_engine_root.py",
        112,
        "the `_CLAUDE_KLABAUTER_SIBLING_DIR_NAME` constant — the ONE site this "
        "dirname is written, read by the rung-3 sibling-directory "
        "auto-discovery fallback (`repo_root.parent / <it>`). There is "
        "nothing to substitute it with, because it IS the string that path "
        "is built from and compared against, not a reference to a document "
        "about that string. Was pinned at :158 against an inline literal in "
        "rung 3 until DR-129 added the (since-deleted) engine-snapshot rung "
        "and hoisted the literal to a shared constant; the rename to "
        "`_CLAUDE_KLABAUTER_SIBLING_DIR_NAME` on the snapshot rung's deletion "
        "2026-08-05 narrowed the entry back to its original single "
        "operative site.",
    ),
)


# ---------------------------------------------------------------------------
# Shape rule — env-var / dotted-or-hyphenated registry-key identifier tokens
# ---------------------------------------------------------------------------


def _normalize(token: str) -> str:
    return token.lower().replace("-", "_")


def _strip_trailing_sentence_period(token: str) -> str:
    """`token` with any trailing `.` run removed.

    Callers recover a token by extending over identifier-shaped characters,
    which include `.` — so a sibling name that merely ENDS A PROSE SENTENCE
    arrives here carrying the sentence's period and reads as dotted SHAPE
    with no dotted CONTENT. Stripping it is what keeps the shape rule from
    exempting the single most natural place for an attribution defect to
    occur. A dot with an actual component after it (`claude_klabauter.module`)
    is not trailing and is untouched."""
    return token.rstrip(".")


#: The ratified stable-ID prefixes, one per artifact type, all four minted by
#: `coordinator-doc-new`'s `_mint_artifact_id` off one uniqueness basis —
#: hence one pattern, not four. Canonical:
#: `coordinator/docs/wiki/canonical-artifact-shapes.md` § Stable-ID table
#: (`plan.schema.json` `plan_id`, `handoff.schema.json` `handoff_id`,
#: `completion-entry.schema.json` `completion_id`, `mint-deliverable-id.py`
#: `deliverable_id`).
STABLE_ID_PREFIXES: tuple = ("pln", "dlv", "hnd", "cmp")

#: `<prefix>-<slug>-<6hex>`, anchored whole-token. Deliberately the STRICT
#: minted shape the ratified schema patterns declare
#: (`^hnd-[a-z0-9-]+-[0-9a-f]{6}$` and its siblings): lowercase only, and the
#: 6-hex uniqueness suffix REQUIRED. That suffix is what holds this rule to
#: citations — an ordinary hyphenated prose phrase, or a bare sibling-repo
#: name standing alone, fails the anchor and the suffix both.
#:
#: Negative spec: `dlv-<stub_id>` (the roadmap-stub deliverable form
#: `plan.schema.json` also permits) carries no 6-hex suffix and is NOT
#: matched. Admitting a suffix-free shape would widen this to any
#: `dlv-`-prefixed hyphenated phrase, and no such id carrying a sibling-repo
#: name exists in the corpus to validate the widening against.
_STABLE_ARTIFACT_ID = re.compile(
    r"^(?:" + "|".join(STABLE_ID_PREFIXES) + r")-[a-z0-9-]+-[0-9a-f]{6}$"
)


def is_stable_artifact_id(token: str, sibling_names: Iterable = SIBLING_REPO_NAMES) -> bool:
    """True if `token` is a minted stable artifact id whose slug carries one
    of `sibling_names` as a `-`-delimited COMPONENT — the fleet's
    spec-backlink citation form (`coordinator/docs/wiki/coordinator-tripwires/
    spec-backlink-cites-the-minted-id-not-the-path.md`).

    A citation of a private DOCUMENT, not a mention of a private REPO: it
    names a record an OSS reader cannot open, exactly as the older
    `docs/plans/<slug>.md § Cn` path form did, and costs that reader the same
    string either way. The path form clears `is_identifier_shape_operative`
    incidentally — its `.md` extension supplies the dot that shape rule's
    precondition demands — so exempting it while flagging the id form is
    detector narrowness dating from before the ids existed, not a policy
    distinction between the two shapes.

    Component-matched, not substring-matched, for the same reason
    `is_identifier_shape_operative` is: an unrelated slug word that merely
    contains the same letters must not fire.

    Negative spec: a BARE sibling-repo name in prose is not an id and stays a
    violation — it fails `_STABLE_ARTIFACT_ID`'s prefix anchor and its
    required 6-hex suffix. That strictness is this rule's entire narrowness
    guarantee; loosening either end swallows attribution prose.
    """
    token = _strip_trailing_sentence_period(token)
    if not _STABLE_ARTIFACT_ID.match(token):
        return False
    normalized = _normalize(token)
    for name in sibling_names:
        norm_name = _normalize(name)
        candidates = {norm_name, norm_name.rsplit("_", 1)[-1]}
        for candidate in candidates:
            if re.search(rf"(?:^|_){re.escape(candidate)}(?:_|$)", normalized):
                return True
    return False


def is_identifier_shape_operative(token: str, sibling_names: Iterable = SIBLING_REPO_NAMES) -> bool:
    """True if `token` is an identifier-shaped string that carries one of
    `sibling_names` as a delimited COMPONENT — not merely a substring, so
    this does not fire on an unrelated word that happens to contain the same
    letters. Two shapes qualify, and this is the single entry point the
    detector calls for both:

      - an env var, or a dotted/hyphenated registry key
        (`CLAUDE_KLABAUTER_ROOT`, `REPO_CLAUDE_KLABAUTER`, `repos.claude_klabauter`,
        `plugin.mirrors.claude-klabauter.source_path`);
      - a minted stable artifact id — see `is_stable_artifact_id`.

    Independent of which specific token it is — that is the point: shape
    rules instead of hand-curated entries, generalizing to any future sibling
    name with no per-name edit.

    Negative spec: a trailing sentence-period is not attribute access. See
    `_strip_trailing_sentence_period`.
    """
    token = _strip_trailing_sentence_period(token)
    if is_stable_artifact_id(token, sibling_names):
        return True
    if "_" not in token and "." not in token:
        # A bare hyphenated-or-plain word — the sibling name standing alone,
        # in either its full or short form — with no `_`/`.` at all is not
        # env-var/registry-key SHAPED. It is either
        # the irreducible bare literal (handled separately by the caller via
        # `IRREDUCIBLE_LITERALS`) or plain attribution prose. Without this
        # precondition the component-match below would trivially match the
        # bare sibling name against itself and silently exempt every prose
        # mention of it, which is the exact silent-widening this rule must
        # not do.
        #
        # A hyphen-only multi-segment token (e.g. a hypothetical
        # `mirrors-claude-klabauter-path`) also falls into this branch and
        # returns False, even though it is structurally the same
        # multi-segment shape this rule targets. No registry key in this
        # repo is hyphen-only-delimited today (dotted keys are the shape
        # actually in use), so the gap is unexercised — left as-is rather
        # than widening the precondition against a shape with no current
        # example to validate it against. The one hyphen-only shape that IS
        # exercised — the minted stable artifact id — is matched above by
        # `is_stable_artifact_id`, on its own anchored pattern, precisely so
        # this precondition does not have to be loosened to admit it.
        return False

    normalized = _normalize(token)
    for name in sibling_names:
        norm_name = _normalize(name)
        candidates = {norm_name}
        # The short form — the last underscore-delimited segment of the
        # normalized name — also counts as a component on its own, because an
        # env-var name typically carries only that segment, not the full repo
        # name.
        candidates.add(norm_name.rsplit("_", 1)[-1])
        for candidate in candidates:
            if re.search(rf"(?:^|[_.]){re.escape(candidate)}(?:[_.]|$)", normalized):
                return True
    return False


# ---------------------------------------------------------------------------
# MCP tool-name prefixes — derived from coordinator/mcp-topology.yaml
# ---------------------------------------------------------------------------


def _normalize_config_key_to_prefix(config_key: str) -> str:
    """`configKey` -> the `mcp__<...>__` tool-name prefix the harness
    registers it under. Best-effort normalization (`.`/space -> `_`) — this
    is derivation, not a guarantee of exact harness-internal casing, and a
    miss here only means one server's prefix isn't exempted (fail-narrow,
    not fail-loud), never a false exemption."""
    normalized = re.sub(r"[.\s]+", "_", config_key.strip())
    return f"mcp__{normalized}__"


def mcp_tool_prefixes() -> frozenset:
    """Every `mcp__<server>__` prefix derivable from
    `coordinator/mcp-topology.yaml`'s declared `configKey` list. Empty on any
    read/parse failure (missing PyYAML, missing/malformed file) — fail-open,
    same contract as the citation detector's ratified-data loaders: a load
    failure narrows this ONE carve-out rather than bricking the whole
    detector."""
    try:
        import yaml
    except Exception:
        return frozenset()
    try:
        data = yaml.safe_load(_MCP_TOPOLOGY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return frozenset()
    if not isinstance(data, dict):
        return frozenset()
    servers = data.get("servers")
    if not isinstance(servers, list):
        return frozenset()
    prefixes = set()
    for entry in servers:
        if not isinstance(entry, dict):
            continue
        config_key = entry.get("configKey")
        if isinstance(config_key, str) and config_key:
            prefixes.add(_normalize_config_key_to_prefix(config_key))
    return frozenset(prefixes)


#: Resolved once at import time — same fail-open contract as the loaders above.
MCP_TOOL_PREFIXES: frozenset = mcp_tool_prefixes()

#: Matches an `mcp__<anything>__` span structurally, used to locate candidate
#: spans cheaply before checking membership in `MCP_TOOL_PREFIXES` — kept
#: separate from the derived set so a name that fails normalization (an
#: unmodeled `configKey` shape) still gets a structural match attempt rather
#: than silently falling through.
MCP_TOOL_PREFIX_SPAN = re.compile(r"mcp__[\w\-. ]*?__")
