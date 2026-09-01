"""coordinator/lib/percolate/content_strip_inventory.py — enumerate every publish
row and state, per row, whether a content-strip transform is declared.

The defect this closes (state/bug-backlog/2026-09-01-nothing-enumerates-which-
publish-rows-ca-5194901fbf52.yaml): a publish row with NO `sentinel_strip`
declaration is indistinguishable, from every surface this repo had, from a row
whose strip is declared and firing. Both are silence. Two rows leaked DoE-only
content to the OSS mirror in one session and neither was found by reading config
-- config was read carefully, by two sessions, in both directions, over four
rounds, and produced three wrong root causes in sequence. What was missing was
not a more careful reader; it was a LIST.

This module is that list. It joins the two halves nothing previously joined:

  - the publish topology (`setup/publish-targets.portable` -- which rows exist),
    read through `targets.raw_dest_sigil_by_name` so this module and the real
    loader can never disagree about which rows there are; and
  - the percolation store (`setup/percolate-hooks/percolate-store.yaml` -- which
    rows declare a strip), read through `store.load_store` + `store.resolve_target`
    so base-inherited entries and per-target hook-set membership resolve exactly as
    the engine resolves them at publish time.

`sentinel-strip` fires only when a target declares BOTH a non-empty
`sentinel_strip` list AND `sentinel-strip` in its `hooks`
(`coordinator_core/percolate/engine.py::_transform_text_body`, and the schema's own
`sentinel_strip` description). Those are two independent switches, so there are two
distinct ways to declare a strip that never runs -- and both look like a working
strip to a reader skimming for the word `sentinel_strip`. Each gets its own state
below rather than collapsing into "not stripping", because the remedy differs: one
is a missing hook, the other a missing entry.

Negative-spec: this module resolves no machine-local paths, spawns no process,
touches no destination tree, and makes no judgement about whether a given row
SHOULD strip. It reports declared state. Whether a row's raw publish is INTENDED is
answered by `setup/publish-allowlist-declarations.yaml`'s per-row `content_strip`
block and enforced by
`coordinator/tests/test_publish_row_content_strip_declared.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from coordinator.lib.percolate.targets import raw_dest_sigil_by_name
from coordinator_core.percolate.store import load_store, resolve_target

#: The transform-kind's hook name (`hooks` membership) and its section key. Both are
#: required for a strip to fire; see module docstring.
STRIP_HOOK = 'sentinel-strip'
STRIP_SECTION = 'sentinel_strip'

#: Per-row verdicts. `STRIPS` is the only state in which a declared marker pair is
#: actually removed from this row's published bytes.
STRIPS = 'strips'
PUBLISHES_RAW = 'publishes-raw'
DEAD_DECLARATION = 'dead-declaration'
EMPTY_HOOK = 'empty-hook'
NO_STORE_SECTION = 'no-store-section'

#: States that are a defect regardless of what the row's declaration says: config
#: exists, reads as protection, and protects nothing.
MISCONFIGURED_STATES = (DEAD_DECLARATION, EMPTY_HOOK)

#: One line per state, for the CLI and for a failing test's message — the remedy is
#: the part a reader needs, and it differs per state.
STATE_MEANING = {
    STRIPS: 'declares a marker pair AND activates the hook — the block is removed',
    PUBLISHES_RAW: 'no marker pair, no hook — every byte of this row publishes verbatim',
    DEAD_DECLARATION: f'declares {STRIP_SECTION} entries but omits {STRIP_HOOK!r} from hooks — never fires',
    EMPTY_HOOK: f'activates {STRIP_HOOK!r} but declares no {STRIP_SECTION} entries — nothing to strip',
    NO_STORE_SECTION: 'publish row has no store targets section at all — the store has never heard of it',
}


@dataclass(frozen=True)
class StripRow:
    """One publish row's content-strip state, as DECLARED (not as observed in output).

    `state` is the single field a caller should branch on; the three inputs that
    produced it are kept alongside so a report can say why without re-deriving it.
    """

    name: str
    dest_sigil: str
    has_store_target: bool
    hook_active: bool
    entry_count: int
    state: str

    @property
    def strips(self) -> bool:
        return self.state == STRIPS

    @property
    def misconfigured(self) -> bool:
        return self.state in MISCONFIGURED_STATES


def _classify(has_store_target: bool, hook_active: bool, entry_count: int) -> str:
    if not has_store_target:
        return NO_STORE_SECTION
    if hook_active and entry_count:
        return STRIPS
    if hook_active:
        return EMPTY_HOOK
    if entry_count:
        return DEAD_DECLARATION
    return PUBLISHES_RAW


def _store_path(setup_dir: Path, store_file: Optional[Path]) -> Path:
    if store_file is not None:
        return Path(store_file)
    return setup_dir / 'percolate-hooks' / 'percolate-store.yaml'


def enumerate_strip_rows(
    setup_dir: Path,
    *,
    portable_targets_file: Optional[Path] = None,
    store_file: Optional[Path] = None,
) -> list[StripRow]:
    """Every PRIMARY publish row, with its resolved content-strip state.

    Rows come from the tracked portable topology only (tier 1) — the same scope
    `raw_dest_sigil_by_name` documents, for the same reason: tiers 2 and 3 are
    per-machine and deprecated overrides, so a row from either could not be part of a
    tracked, auditable inventory even if it were read here.

    A row whose name has no `targets` section in the store yields NO_STORE_SECTION
    rather than being omitted. That omission IS the second of the two live leaks
    (`coordinator-claude-toplevel-wiki` declared no strip hook at all — absent, not
    misconfigured — and nobody was watching the file it published), so a row the store
    has never heard of must appear in this list, loudly, rather than fall out of it.

    Raises `StoreValidationError` if the store does not load: an inventory computed
    from a store the engine would itself refuse is not evidence about anything.
    """
    setup_dir = Path(setup_dir)
    store_path = _store_path(setup_dir, store_file)

    dest_by_name = raw_dest_sigil_by_name(setup_dir, portable_targets_file=portable_targets_file)
    store = load_store(store_path) if store_path.is_file() else {'targets': {}}
    declared_targets = store.get('targets') or {}

    rows: list[StripRow] = []
    for name, dest_sigil in dest_by_name.items():
        has_store_target = name in declared_targets
        hook_active = False
        entry_count = 0
        if has_store_target:
            section = resolve_target(store, name)
            hook_active = STRIP_HOOK in (section.get('hooks') or [])
            entry_count = len(section.get(STRIP_SECTION) or [])
        rows.append(
            StripRow(
                name=name,
                dest_sigil=dest_sigil,
                has_store_target=has_store_target,
                hook_active=hook_active,
                entry_count=entry_count,
                state=_classify(has_store_target, hook_active, entry_count),
            )
        )
    return rows


def orphan_store_targets(
    setup_dir: Path,
    *,
    portable_targets_file: Optional[Path] = None,
    store_file: Optional[Path] = None,
) -> list[str]:
    """Store `targets` sections naming no PRIMARY publish row.

    The mirror image of NO_STORE_SECTION, and the second way a reader is misled: a
    store section carrying a working-looking strip for a row that no longer exists
    reads as coverage while covering nothing.
    """
    setup_dir = Path(setup_dir)
    store_path = _store_path(setup_dir, store_file)
    if not store_path.is_file():
        return []
    store = load_store(store_path)
    row_names = set(raw_dest_sigil_by_name(setup_dir, portable_targets_file=portable_targets_file))
    return sorted(set(store.get('targets') or {}) - row_names)
