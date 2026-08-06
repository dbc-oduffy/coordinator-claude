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

SIBLING_REPO_NAMES is sourced from `_oss_payload._ENGINE_REPO_NAME` rather
than re-declared here — the one sibling repo this fleet's OSS-payload
machinery already knows about, kept to a single source of truth. A future
second sibling gets added there (and its `source_map` row), not invented
here first.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[3]
_MCP_TOPOLOGY_PATH = REPO_ROOT / "coordinator" / "mcp-topology.yaml"


def _sibling_repo_names() -> tuple:
    """Fail-open, matching every other loader in this module and in
    `_prompt_surface_locality.py`: an import or attribute-read failure
    degrades to an EMPTY tuple, never a hardcoded copy of the name this
    function exists to source from a single place. A hardcoded fallback here
    would silently keep working on a stale value if `_oss_payload` is ever
    renamed or the engine repo's canonical name changes, instead of
    surfacing the drift."""
    try:
        import _oss_payload  # local import: avoids a hard import-time dependency
    except Exception:
        return ()
    name = getattr(_oss_payload, "_ENGINE_REPO_NAME", None)
    return (name,) if isinstance(name, str) and name else ()


#: The one sibling repo known to this fleet's OSS-payload machinery today.
SIBLING_REPO_NAMES: tuple = _sibling_repo_names()

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
        108,
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


def is_identifier_shape_operative(token: str, sibling_names: Iterable = SIBLING_REPO_NAMES) -> bool:
    """True if `token` is an identifier-shaped string (env var, dotted or
    hyphenated registry key) that carries one of `sibling_names` as a
    `_`/`.`-delimited COMPONENT — not merely a substring, so this does not
    fire on an unrelated word that happens to contain the same letters.

    Independent of which specific token it is (`CLAUDE_KLABAUTER_ROOT` vs
    `REPO_CLAUDE_KLABAUTER` vs `repos.claude_klabauter` vs
    `plugin.mirrors.claude-klabauter.source_path`) — that is the point: one
    shape rule instead of four hand-curated entries, generalizing to any
    future sibling name with no per-name edit.
    """
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
        # example to validate it against.
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
