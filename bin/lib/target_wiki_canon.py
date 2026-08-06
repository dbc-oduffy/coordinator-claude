"""target_wiki_canon.py — shared `target_wiki` canonicalization for the lessons-outbox pair.

Purpose: `coordinator-lesson-promote` (writer) and `lessons-outbox-drain.py` (reader/
deduper) both need to collapse equivalent spellings of a central-wiki `target_wiki`
value ('foo', 'foo.md', 'docs/wiki/foo.md', ...) to one canonical string — the writer
so a normalized value is what actually lands on disk, the drain so its dedupe key
treats those spellings as the same target. Before this module existed the two tools
carried independently-drifting copies of "the" canonicalization (promote's collapsed
the directory prefix; drain's collapsed only the `.md` suffix), so a value promote
wrote as `docs/wiki/foo.md` and a legacy bare `foo.md` entry in the corpus still
deduped as two distinct keys downstream — the A9 fix did not actually compose across
the two tools. This module is the single canonicalization both now import.

`target_wiki` is NOT always a wiki path — it is the generic promotion-target field for
every `change_kind` in the lessons-outbox schema (docs/wiki/lessons-outbox-schema.md
§ Change-kind enum). Only `wiki-new` and `wiki-append` are wiki-targeting by the
schema's own semantics (a new wiki file / an append to an existing wiki section);
every other accepted change_kind (`doctrine-edit`, `agent-prompt-edit`, `hook-edit`,
`script-edit`, `snippet-sync-update`, `skill-edit`) stores a non-wiki path in this
same field (a `SKILL.md`, a `bin/` script, a hook file, ...). Collapsing the directory
prefix on those values is unsafe: every skill file shares the basename `SKILL.md`, so
a basename-only collapse would silently merge unrelated skills' entries into one
dedupe group. `canonical_target_wiki_for_kind` resolves that by making the full
collapse conditional on `change_kind` — non-wiki kinds keep their raw value as the
comparison/storage key; only wiki-targeting kinds get the full canonical form.

Spec backlink: cross-repo/inbox/2026-07-23-example-cockpit-repo-em-learn-lessons-dogfood-2026-07-23.md
(findings A7/A9)
"""

from __future__ import annotations

# The two schema-enum members whose semantics are unambiguously wiki-targeting
# (docs/wiki/lessons-outbox-schema.md § Change-kind enum: `wiki-new` = "A new wiki
# file under docs/wiki/"; `wiki-append` = "An append to an existing wiki section").
# Every other accepted change_kind stores a non-wiki path in `target_wiki` and must
# NOT be run through the directory-collapsing normalization below.
WIKI_TARGETING_CHANGE_KINDS = frozenset({"wiki-new", "wiki-append"})

# Public (no leading underscore) — both `coordinator-lesson-promote` and
# `lessons-outbox-drain.py` import these directly rather than re-declaring their
# own private copies, closing the exact drift shape this module exists to end.
TARGET_WIKI_UNKNOWN = "unknown"
TARGET_WIKI_PREFIX = "docs/wiki/"


def normalize_target_wiki(raw: str) -> str:
    """Normalize a wiki-targeting `target_wiki` value to the canonical
    'docs/wiki/<name>.md' form.

    The literal sentinel 'unknown' (schema-documented for an unresolved classifier
    target) passes through unchanged. Otherwise collapses any of the equivalent
    input shapes routers emit — 'foo', 'foo.md', 'wiki/foo.md', 'docs/wiki/foo',
    'docs/wiki/foo.md', and any of those with backslash separators — to exactly
    one canonical string, so two routers naming "the same" target always produce
    byte-identical YAML / dedupe keys.

    Callers MUST gate this on `change_kind in WIKI_TARGETING_CHANGE_KINDS` first —
    this function has no way to tell a genuine bare wiki name ('foo') from a non-wiki
    path that happens to have no directory component, so applying it unconditionally
    to every change_kind silently corrupts non-wiki targets (verified defect: a
    `skill-edit` value of `coordinator/skills/pickup/SKILL.md` became
    `docs/wiki/coordinator/skills/pickup/SKILL.md` under the unconditional call this
    module replaces).

    Negative-spec: do NOT special-case only the '.md' suffix — a bare
    'wiki/'-prefixed or already-canonical input must collapse to the same string
    too, or a third router variant reopens the bug this collapses.
    """
    value = raw.strip()
    if not value or value == TARGET_WIKI_UNKNOWN:
        return TARGET_WIKI_UNKNOWN
    value = value.replace("\\", "/").strip("/")
    if value.startswith(TARGET_WIKI_PREFIX):
        name = value[len(TARGET_WIKI_PREFIX):]
    elif value.startswith("wiki/"):
        name = value[len("wiki/"):]
    else:
        name = value
    if name.endswith(".md"):
        name = name[:-len(".md")]
    return f"{TARGET_WIKI_PREFIX}{name}.md"


def canonical_target_wiki_for_kind(target_wiki: str | None, change_kind: str) -> str | None:
    """Return the canonical/comparison form of `target_wiki`, gated on `change_kind`.

    - `None` or the 'unknown' sentinel passes through unchanged (never a real target).
    - `change_kind` in `WIKI_TARGETING_CHANGE_KINDS` (`wiki-new`, `wiki-append`) gets
      the full `normalize_target_wiki` directory/suffix collapse.
    - Every other change_kind returns `target_wiki` completely UNCHANGED — no `.md`
      suffix massage, no prefix collapse. These values are generic non-wiki paths
      (a `SKILL.md`, a `bin/` script, a hook file, ...) where any collapse risks
      merging unrelated entries that happen to share a basename.
    """
    if target_wiki is None or target_wiki == TARGET_WIKI_UNKNOWN:
        return target_wiki
    if change_kind in WIKI_TARGETING_CHANGE_KINDS:
        return normalize_target_wiki(target_wiki)
    return target_wiki
