
from __future__ import annotations

WIKI_TARGETING_CHANGE_KINDS = frozenset({"wiki-new", "wiki-append"})

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
