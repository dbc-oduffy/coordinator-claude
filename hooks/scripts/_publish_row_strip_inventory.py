"""Per-row content-strip inventory: for every `setup/publish-targets.portable` row,
does that row strip DoE-only content before its bytes leave the tree — and if not, is
that a signed claim or an unnoticed leak?

WHY THIS EXISTS
    Two `INSTALL-DOE-ONLY` leaks reached the OSS mirror. Both were found by reading
    bytes after the fact, and four rounds of careful config-reading before that found
    neither. The reason is structural: this repo's strip eligibility is keyed on PATHS
    and FILENAMES, never on rows — `setup/publish_sync.py`'s
    `_MIRROR_DOE_STRIP_ELIGIBLE_PATHS` (reachable only under `_is_coordinator_plugin_src`)
    and a bare `rel_path == INSTALL.md` test in `sync_flat_mirror`. No surface anywhere
    took a row name and answered "does this row strip?", so a row that published a
    marker-carrying file through no gate at all looked exactly like a row that had
    nothing to strip. This module is that surface.

    Order matters: enumeration before assertion. A byte assertion only ever runs against
    a row someone remembered to name; the second leak was found only because a test
    written for the first happened to sweep wider than its author intended.

    Cross-repo source: `cross-repo/inbox/2026-09-01-claude-klabauter-em-publish-row-strip-
    enumeration-doe-half.md` (the engine plane's half of the same bug, closed on their
    side; the five-state shape is theirs, the leak state and the contested-dest report
    are this tree's, because path-keyed eligibility makes both reachable here).

TWO STRIP PLANES, NOT ONE
    A row-level answer that consults only `publish_sync.py` is WRONG, and wrong in the
    direction that reports leaks where none exist. Two independent mechanisms strip
    DoE-only content on this boundary:

      - `setup/publish_sync.py` — path- and filename-keyed, per FILE:
        `_MIRROR_DOE_STRIP_ELIGIBLE_PATHS` under `_is_coordinator_plugin_src` (mirror leg)
        and `rel_path == INSTALL.md` (flat-mirror leg).
      - `setup/percolate-hooks/percolate-store.yaml` — target-keyed, per ROW: a
        `sentinel_strip` pair naming the `INSTALL-DOE-ONLY` markers, active only when the
        row's resolved `hooks` list carries `sentinel-strip`. Resolved here through the
        engine's own `store.resolve_target`, so base inheritance composes as the engine
        composes it.

    A row is covered if EITHER plane reaches it, and `gated_by` records which — because
    "covered by the other plane" and "covered by this one" have different failure modes,
    and a stale entry in one plane hides behind live coverage in the other. That is not
    hypothetical here: `docs/wiki/install-command-residue.md` is named in
    `_MIRROR_DOE_STRIP_ELIGIBLE_PATHS` and published by NO mirror row — the store plane
    took the job over, and the publish_sync entry has been dead ever since, reporting
    nothing.

WHY STATES AND NOT A BOOLEAN
    A boolean collapses "declared but never fires" into "does not strip", and those have
    opposite remedies — one is a stale constant to delete, the other is a gate to build.
    Six states, each with a distinct remedy:

      strips          the row publishes marker-carrying files and every one of them
                      reaches a strip gate. Nothing to do.
      publishes-raw   the row publishes no marker-carrying file and reaches no gate.
                      Correct, but must be a SIGNED claim (a `strips: false` plus a
                      reason in the declarations file), never silence.
      leaks           the row publishes a marker-carrying file that reaches NO gate.
                      Break-class: DoE-only bytes are being published. Build the gate.
      empty-hook      a gate is reachable on a path this row publishes, but that file
                      carries no markers today. Harmless now, load-bearing the moment
                      a marker is added — keep.
      dead-declaration
                      a strip is DECLARED for this row but can never fire: the store
                      section declares an `INSTALL-DOE-ONLY` `sentinel_strip` pair while
                      its resolved `hooks` list omits `sentinel-strip`. Entries, no hook.
                      Reported per row; the file-plane equivalent (a path named in
                      `_MIRROR_DOE_STRIP_ELIGIBLE_PATHS` that no row publishes) is
                      reported inventory-wide as `dead_eligible_paths`, because no row
                      owns it.
      undeclared      the row is absent from `setup/publish-row-strip-declarations.yaml`.
                      Only the test reports this; the inventory itself never invents a
                      declaration it did not read.

    `contested-dest` is reported alongside, and is not a row state: it is a dest path two
    rows both write where they disagree about stripping. Publish order then decides
    whether DoE-only bytes survive, and publish order is not expressible in the config —
    so a contested dest is unanswerable by reading config, which is precisely the failure
    mode this module exists to end.

HOW IT DECIDES — real gates, never re-derived
    Every gate predicate here reads `setup/publish_sync.py`'s own constants and helpers
    through the already-ratified `_prepublish_projection` importer (`_import_publish_sync`),
    and every row's published file set comes from `_prepublish_projection`'s real
    projectors. Nothing about include/exclude semantics, `.percolate-ignore` matching, or
    allowlist grammar is restated here; a second hand-synced table is the shape of the
    bug this module is closing, not a tool for closing it.

KNOWN SIMPLIFICATIONS (report, don't hide)
    - `_is_coordinator_plugin_src` is a suffix test on the resolved source dir. The
      projection resolves that row to `<repo>/coordinator`, which satisfies it; the real
      publish resolves the same row through `machine-local get
      plugin.mirrors.coordinator-claude.source_path`, which on a differently-laid-out box
      could resolve to a directory NOT ending in `/coordinator` and silently disable
      every mirror-leg strip. This inventory reports what the projection resolves, and
      names that divergence here rather than asserting the registry agrees.
    - Store-plane coverage is modeled at ROW granularity, matching the store's own
      `sentinel_strip` granularity — the store strips every file of a target, so a row
      whose store hook is live is treated as covering all its carriers. It does not model
      `file_surface`, which scopes the CONTENT-TRANSFORM sweep and is a different question
      (§ `_prepublish_projection`'s own docstring on the same distinction).
    - A source file that cannot be read as UTF-8 text is not a carrier. The markers are
      HTML comments; a binary carrying them is out of model.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
_HOOKS_SCRIPTS_DIR = REPO_ROOT / "coordinator" / "hooks" / "scripts"
if str(_HOOKS_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_SCRIPTS_DIR))

import _prepublish_projection as projection_mod  # noqa: E402
from _prepublish_projection import (  # noqa: E402
    ProjectionIssue,
    ProjectionUnavailableError,
    PublishRow,
)

DECLARATIONS_PATH = REPO_ROOT / "setup" / "publish-row-strip-declarations.yaml"

STATE_STRIPS = "strips"
STATE_PUBLISHES_RAW = "publishes-raw"
STATE_LEAKS = "leaks"
STATE_EMPTY_HOOK = "empty-hook"
STATE_DEAD_DECLARATION = "dead-declaration"

#: Row states a `strips: true` declaration is consistent with. `empty-hook` counts: the
#: gate is wired and reachable, it simply has nothing to remove today. `dead-declaration`
#: does NOT — a declared-but-unhooked strip removes nothing.
_STRIPPING_STATES = frozenset({STATE_STRIPS, STATE_EMPTY_HOOK})

#: `percolate-store.yaml` hook-kind that runs the `sentinel_strip` pairs.
_SENTINEL_STRIP_HOOK = "sentinel-strip"

GATED_BY_PUBLISH_SYNC = "publish_sync"
GATED_BY_STORE = "store"
GATED_BY_BOTH = "both"
GATED_BY_NOTHING = "none"

#: Values a `strips: true` declaration may name for `plane:`. Excludes `none` — a row
#: that strips is gated by something.
_DECLARABLE_PLANES = frozenset({GATED_BY_PUBLISH_SYNC, GATED_BY_STORE, GATED_BY_BOTH})


# ---------------------------------------------------------------------------
# Row roster — ALL rows, not just the ones the citation projector models
# ---------------------------------------------------------------------------
#
# `_prepublish_projection.iter_publish_rows` filters to rows sourced from the
# `plugin-source:coordinator-claude` sigil, which drops
# `coordinator-claude-repo-root-install-md` — the meta-repo-root row, and the ONLY row
# that reaches the flat-mirror `INSTALL.md` gate at all. An inventory of "which rows
# strip" that cannot see the one row that strips is worse than no inventory, so the
# roster is parsed here over every row landing in the mirror, and the dropped row's file
# set is projected by calling the projector's own real flat-mirror projector against the
# meta-repo root.
_REPO_ROOT_SOURCE_SUBDIR = "."


def iter_all_mirror_rows(
    dest_sigil: str = projection_mod._PUBLISH_MIRROR_DEST,  # noqa: SLF001
) -> "list[PublishRow]":
    """Every row targeting `dest_sigil`, including rows sourced from the meta-repo root.

    `PublishRow.source_subpath` is coordinator-relative for sigil-sourced rows (the
    projector's convention, preserved) and the literal `"."` for a meta-repo-root row —
    `row_source_root` is the only place that distinction is interpreted."""
    path = projection_mod.PUBLISH_TARGETS_PATH
    rows: "list[PublishRow]" = []
    if not path.is_file():
        return rows
    sigil = projection_mod._SOURCE_SIGIL_COORDINATOR_CLAUDE  # noqa: SLF001
    for line in path.read_text(encoding="utf-8").split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        fields = stripped.split("|")
        if len(fields) < 5 or fields[2] != dest_sigil:
            continue
        source = fields[3]
        if source == sigil:
            source_subpath = ""
        elif source.startswith(sigil + "/"):
            source_subpath = source[len(sigil) + 1 :]
        elif source == _REPO_ROOT_SOURCE_SUBDIR:
            source_subpath = _REPO_ROOT_SOURCE_SUBDIR
        else:
            continue
        rows.append(
            PublishRow(
                name=fields[0],
                mode=fields[1],
                dest_sigil=fields[2],
                source_subpath=source_subpath,
                dest_subdir=fields[4].strip(),
                allowlist_csv=fields[6].strip() if len(fields) >= 7 else "",
                source_map_csv=fields[7].strip() if len(fields) >= 8 else "",
            )
        )
    return rows


def row_source_root(row: PublishRow) -> Path:
    if row.source_subpath == _REPO_ROOT_SOURCE_SUBDIR:
        return REPO_ROOT
    if row.source_subpath:
        return REPO_ROOT / "coordinator" / row.source_subpath
    return REPO_ROOT / "coordinator"


# ---------------------------------------------------------------------------
# Gate predicates — publish_sync's own constants, read not restated
# ---------------------------------------------------------------------------


def _gate_reaches(row: PublishRow, source_path: Path, real_src: Path, publish_sync) -> bool:
    """Does `setup/publish_sync.py` apply the DoE-only strip transform to this file when
    published through this row?

    Mirror leg (`sync_mirror`): keyed on the source-root-relative path against
    `_MIRROR_DOE_STRIP_ELIGIBLE_PATHS`, guarded by `_is_coordinator_plugin_src`. The
    `plugin_name + "/" + rel_path` the real loop builds IS that relative path — its
    "plugins" are the source root's top-level directories.

    Flat-mirror leg (`sync_flat_mirror`): keyed on the bare filename against
    `_INSTALL_MD_FILENAME`, with no source-root guard at all."""
    if row.mode == "mirror":
        if not publish_sync._is_coordinator_plugin_src(real_src):  # noqa: SLF001
            return False
        try:
            rel = source_path.relative_to(real_src).as_posix()
        except ValueError:
            return False
        return rel in publish_sync._MIRROR_DOE_STRIP_ELIGIBLE_PATHS  # noqa: SLF001
    if row.mode == "flat-mirror":
        return source_path.name == publish_sync._INSTALL_MD_FILENAME  # noqa: SLF001
    return False


def _carries_markers(source_path: Path, publish_sync) -> bool:
    """Does this source file carry at least one well-formed DoE-only BLOCK?

    Decided by running `publish_sync`'s own `_strip_install_doe_only_blocks` and asking
    whether it removed anything — never by substring-searching for the marker text. The
    difference is load-bearing: `percolate-store.yaml` and its template *name* both
    markers as config values, and a substring test classifies the strip RULES themselves
    as DoE-only content, reporting a leak on the file that declares the fix.

    A malformed marker set counts as a carrier: `_strip_install_doe_only_blocks` fails
    loud on those, so routing the file to a gate is what surfaces it."""
    try:
        text = source_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    try:
        _, blocks_removed, _ = publish_sync._strip_install_doe_only_blocks(  # noqa: SLF001
            text, file_label=str(source_path)
        )
    except publish_sync.InstallMdMarkerError:
        return True
    return blocks_removed > 0


def _store_strip_state(row_name: str, store_module, store: dict, begin_marker: str) -> "tuple[bool, bool]":
    """`(hook_active, pair_declared)` for one row's `percolate-store.yaml` section.

    Resolved through the engine's own `store.resolve_target` so `base` inheritance
    composes exactly as the engine composes it — a hand-read of the target's own block
    misses every inherited hook. An undeclared target yields `(False, False)`."""
    try:
        section = store_module.resolve_target(store, row_name)
    except KeyError:
        return False, False
    hooks = section.get("hooks") or []
    pairs = section.get("sentinel_strip") or []
    hook_active = _SENTINEL_STRIP_HOOK in hooks
    pair_declared = any(pair.get("start_marker") == begin_marker for pair in pairs)
    return hook_active, pair_declared


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RowStrip:
    """One row's answer to "does this row strip?", with the evidence that produced it."""

    row: str
    mode: str
    state: str
    gated_by: str  # publish_sync | store | both | none
    published_count: int
    carriers: "tuple[str, ...]"  # dest-relpaths carrying a well-formed DoE-only block
    gated: "tuple[str, ...]"  # dest-relpaths publish_sync's file-plane gate reaches
    ungated_carriers: "tuple[str, ...]"  # carriers reaching neither plane — the leak set
    store_hook: bool  # row's resolved hooks carry `sentinel-strip`
    store_pair: bool  # row's resolved section declares the INSTALL-DOE-ONLY pair


@dataclass(frozen=True)
class ContestedDest:
    """One dest path written by two or more rows that disagree about stripping. Which
    bytes survive depends on publish ORDER, which `publish-targets.portable` does not
    express — so this is unanswerable from config by construction."""

    dest_relpath: str
    stripping_rows: "tuple[str, ...]"
    raw_rows: "tuple[str, ...]"


@dataclass
class Inventory:
    rows: "list[RowStrip]" = field(default_factory=list)
    contested: "list[ContestedDest]" = field(default_factory=list)
    dead_eligible_paths: "tuple[str, ...]" = ()
    issues: "list[ProjectionIssue]" = field(default_factory=list)

    def by_state(self, state: str) -> "list[RowStrip]":
        return [r for r in self.rows if r.state == state]


def build_inventory() -> Inventory:
    """Join "which rows exist" with "which rows reach a strip gate" and "which rows
    publish bytes that need one". Read-only: source trees and config are opened for
    reading, the destination mirror is never touched."""
    publish_sync = projection_mod._import_publish_sync()  # noqa: SLF001
    allowlist_module = projection_mod._import_percolate_allowlist()  # noqa: SLF001
    store_module = projection_mod._import_percolate_store()  # noqa: SLF001
    claude_klabauter_root = projection_mod._resolve_claude_klabauter_root()  # noqa: SLF001
    rename_map = projection_mod._load_basename_rename_map(store_module)  # noqa: SLF001
    store = store_module.load_store(projection_mod.STORE_PATH)
    begin_marker = publish_sync._INSTALL_DOE_ONLY_BEGIN  # noqa: SLF001

    inventory = Inventory()
    eligible_seen: "set[str]" = set()
    # dest_relpath -> (rows that strip it, rows that publish it raw, any writer a carrier)
    dest_writers: "dict[str, tuple[list[str], list[str], list[bool]]]" = {}

    for row in iter_all_mirror_rows():
        real_src = row_source_root(row)
        entry_roots, unresolved = projection_mod._parse_source_map(  # noqa: SLF001
            row.source_map_csv, claude_klabauter_root=claude_klabauter_root
        )
        for sigil in unresolved:
            inventory.issues.append(
                ProjectionIssue(row=row.name, entry="(source_map)", reason=f"unresolved source_map sigil: {sigil}")
            )

        if row.mode == "mirror":
            pairs = projection_mod._project_mirror_row(  # noqa: SLF001
                row,
                real_src=real_src,
                entry_roots=entry_roots,
                publish_sync_module=publish_sync,
                allowlist_module=allowlist_module,
                issues=inventory.issues,
            )
        elif row.mode == "flat-mirror":
            pairs = projection_mod._project_flat_mirror_row(  # noqa: SLF001
                row,
                real_src=real_src,
                publish_sync_module=publish_sync,
                allowlist_module=allowlist_module,
                issues=inventory.issues,
            )
        else:
            inventory.issues.append(
                ProjectionIssue(row=row.name, entry="(mode)", reason=f"unmodeled publish mode: {row.mode!r}")
            )
            continue

        store_hook, store_pair = _store_strip_state(row.name, store_module, store, begin_marker)
        store_covers = store_hook and store_pair

        carriers: "list[str]" = []
        gated: "list[str]" = []
        ungated_carriers: "list[str]" = []
        for rel, source_path in pairs:
            dest_relpath = f"{row.dest_subdir}/{rel}" if row.dest_subdir else rel
            dest_relpath = projection_mod._apply_basename_rename(dest_relpath, rename_map)  # noqa: SLF001
            file_gated = _gate_reaches(row, source_path, real_src, publish_sync)
            if file_gated:
                gated.append(dest_relpath)
                if row.mode == "mirror":
                    eligible_seen.add(source_path.relative_to(real_src).as_posix())
            is_carrier = _carries_markers(source_path, publish_sync)
            if is_carrier:
                carriers.append(dest_relpath)
                if not (file_gated or store_covers):
                    ungated_carriers.append(dest_relpath)
            strippers, rawers, carrier_flags = dest_writers.setdefault(dest_relpath, ([], [], []))
            (strippers if (file_gated or store_covers) else rawers).append(row.name)
            carrier_flags.append(is_carrier)

        if store_pair and not store_hook:
            # Entries, no hook — the store declares a strip this row's hook set can never
            # run. Reported ahead of `leaks` because it is the same defect one step
            # earlier, and its remedy (add the hook) differs from `leaks`' (build a gate).
            state = STATE_DEAD_DECLARATION
        elif ungated_carriers:
            state = STATE_LEAKS
        elif carriers:
            state = STATE_STRIPS
        elif gated or store_covers:
            state = STATE_EMPTY_HOOK
        else:
            state = STATE_PUBLISHES_RAW

        if gated and store_covers:
            gated_by = GATED_BY_BOTH
        elif gated:
            gated_by = GATED_BY_PUBLISH_SYNC
        elif store_covers:
            gated_by = GATED_BY_STORE
        else:
            gated_by = GATED_BY_NOTHING

        inventory.rows.append(
            RowStrip(
                row=row.name,
                mode=row.mode,
                state=state,
                gated_by=gated_by,
                published_count=len(pairs),
                carriers=tuple(sorted(carriers)),
                gated=tuple(sorted(gated)),
                ungated_carriers=tuple(sorted(ungated_carriers)),
                store_hook=store_hook,
                store_pair=store_pair,
            )
        )

    inventory.dead_eligible_paths = tuple(
        sorted(set(publish_sync._MIRROR_DOE_STRIP_ELIGIBLE_PATHS) - eligible_seen)  # noqa: SLF001
    )
    # Only a dest whose SOURCE carries DoE-only content is contested in the sense that
    # matters. Rows disagreeing about a file with nothing to strip is a plain dest
    # collision -- real, but a different concern, and reporting it here buries the one
    # case where publish order decides whether DoE-only bytes survive.
    inventory.contested = [
        ContestedDest(dest_relpath=dest, stripping_rows=tuple(strippers), raw_rows=tuple(rawers))
        for dest, (strippers, rawers, carrier_flags) in sorted(dest_writers.items())
        if strippers and rawers and any(carrier_flags)
    ]
    return inventory


# ---------------------------------------------------------------------------
# Declarations — the signed claim, read never inferred
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Declaration:
    row: str
    strips: bool
    reason: str
    plane: str  # "" when strips is false; else publish_sync | store | both


def load_declarations(path: Path = DECLARATIONS_PATH) -> "dict[str, Declaration]":
    """Parse `setup/publish-row-strip-declarations.yaml` into `{row: Declaration}`.

    Raises `FileNotFoundError` if absent and `ValueError` on a malformed row — an
    unreadable declarations file must never degrade to "nothing declared", which reads
    as a clean inventory."""
    import yaml  # noqa: PLC0415

    if not path.is_file():
        raise FileNotFoundError(f"strip declarations not found at {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw_rows = data.get("rows")
    if not isinstance(raw_rows, dict):
        raise ValueError(f"{path}: top-level `rows:` mapping missing or not a mapping")
    out: "dict[str, Declaration]" = {}
    for name, body in raw_rows.items():
        if not isinstance(body, dict) or "content_strip" not in body:
            raise ValueError(f"{path}: row {name!r} has no `content_strip:` block")
        block = body["content_strip"]
        if not isinstance(block, dict) or not isinstance(block.get("strips"), bool):
            raise ValueError(f"{path}: row {name!r} `content_strip.strips` missing or not a bool")
        reason = str(block.get("reason", "")).strip()
        plane = str(block.get("plane", "")).strip()
        if not block["strips"] and not reason:
            raise ValueError(
                f"{path}: row {name!r} declares `strips: false` with no `reason` — "
                '"this row publishes raw" is a signed claim, not silence'
            )
        if block["strips"] and plane not in _DECLARABLE_PLANES:
            raise ValueError(
                f"{path}: row {name!r} declares `strips: true` with `plane: {plane!r}` — "
                f"must be one of {sorted(_DECLARABLE_PLANES)}; which plane strips is the "
                "part that silently moves"
            )
        out[name] = Declaration(row=name, strips=block["strips"], reason=reason, plane=plane)
    return out


def reconcile(inventory: Inventory, declarations: "dict[str, Declaration]") -> "list[str]":
    """Every disagreement between the computed inventory and the signed declarations,
    in both directions, plus every state that is a defect regardless of declaration."""
    problems: "list[str]" = []
    computed = {r.row: r for r in inventory.rows}

    for row in inventory.rows:
        if row.state == STATE_LEAKS:
            problems.append(
                f"{row.row}: LEAKS — publishes {len(row.ungated_carriers)} DoE-only-marked "
                f"file(s) through no strip gate on either plane: {', '.join(row.ungated_carriers)}"
            )
        elif row.state == STATE_DEAD_DECLARATION:
            problems.append(
                f"{row.row}: dead-declaration — percolate-store.yaml declares an "
                f"INSTALL-DOE-ONLY sentinel_strip pair for this row, but its resolved "
                f"`hooks` list omits `{_SENTINEL_STRIP_HOOK}`, so the strip never runs"
            )
        decl = declarations.get(row.row)
        if decl is None:
            problems.append(f"{row.row}: undeclared — no `content_strip:` block in {DECLARATIONS_PATH.name}")
            continue
        strips_now = row.state in _STRIPPING_STATES
        if decl.strips and not strips_now:
            problems.append(
                f"{row.row}: declared `strips: true` but computes {row.state!r} — "
                "the declaration is dead, or the gate was removed"
            )
        elif not decl.strips and strips_now:
            problems.append(
                f"{row.row}: declared `strips: false` ({decl.reason}) but computes "
                f"{row.state!r} — the claim is stale"
            )
        elif decl.strips and strips_now and decl.plane != row.gated_by:
            problems.append(
                f"{row.row}: declared `plane: {decl.plane}` but is gated by "
                f"{row.gated_by!r} — coverage moved between planes; confirm the plane it "
                "left is intentionally empty, then update the declaration"
            )

    for name in sorted(set(declarations) - set(computed)):
        problems.append(f"{name}: declared but no such publish row targets the mirror")

    for dead in inventory.dead_eligible_paths:
        problems.append(
            f"(none): dead-declaration — {dead!r} is named in `_MIRROR_DOE_STRIP_ELIGIBLE_PATHS` "
            "but no row publishes it; delete the entry or fix the allowlist that should admit it"
        )

    for contested in inventory.contested:
        problems.append(
            f"(contested dest): {contested.dest_relpath} — stripped by "
            f"{', '.join(contested.stripping_rows)}, published raw by "
            f"{', '.join(contested.raw_rows)}; which bytes survive depends on publish order, "
            "which the config does not express"
        )

    return problems


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def format_report(inventory: Inventory) -> str:
    lines = ["Publish-row content-strip inventory", ""]
    width = max((len(r.row) for r in inventory.rows), default=0)
    for row in sorted(inventory.rows, key=lambda r: r.row):
        lines.append(
            f"  {row.row.ljust(width)}  {row.state:<16} gated-by={row.gated_by:<12} "
            f"{row.published_count:>5} published, {len(row.carriers)} marked, "
            f"{len(row.gated)} file-gated, store-hook={row.store_hook}/pair={row.store_pair}"
        )
        for path in row.ungated_carriers:
            lines.append(f"  {' ' * width}    LEAK: {path}")
    if inventory.dead_eligible_paths:
        lines += ["", "Dead eligibility entries (published by no row):"]
        lines += [f"  {d}" for d in inventory.dead_eligible_paths]
    if inventory.contested:
        lines += ["", "Contested dests (two rows, disagreeing gates, order decides):"]
        for c in inventory.contested:
            lines.append(f"  {c.dest_relpath}: strips={','.join(c.stripping_rows)} raw={','.join(c.raw_rows)}")
    if inventory.issues:
        lines += ["", "Projection issues:"]
        lines += [f"  {i.row}/{i.entry}: {i.reason}" for i in inventory.issues]
    return "\n".join(lines)


def _as_json(inventory: Inventory) -> str:
    return json.dumps(
        {
            "rows": [
                {
                    "row": r.row,
                    "mode": r.mode,
                    "state": r.state,
                    "gated_by": r.gated_by,
                    "store_hook": r.store_hook,
                    "store_pair": r.store_pair,
                    "published_count": r.published_count,
                    "carriers": list(r.carriers),
                    "gated": list(r.gated),
                    "ungated_carriers": list(r.ungated_carriers),
                }
                for r in sorted(inventory.rows, key=lambda r: r.row)
            ],
            "dead_eligible_paths": list(inventory.dead_eligible_paths),
            "contested": [
                {
                    "dest_relpath": c.dest_relpath,
                    "stripping_rows": list(c.stripping_rows),
                    "raw_rows": list(c.raw_rows),
                }
                for c in inventory.contested
            ],
            "issues": [{"row": i.row, "entry": i.entry, "reason": i.reason} for i in inventory.issues],
        },
        indent=2,
    )


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="reconcile against setup/publish-row-strip-declarations.yaml; exit 1 on any disagreement",
    )
    parser.add_argument("--json", action="store_true", help="emit the inventory as JSON")
    args = parser.parse_args(argv)

    try:
        inventory = build_inventory()
    except ProjectionUnavailableError as exc:
        print(f"inventory unavailable: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(_as_json(inventory))
    else:
        print(format_report(inventory))

    if not args.check:
        return 0

    try:
        declarations = load_declarations()
    except (FileNotFoundError, ValueError) as exc:
        print(f"\ndeclarations unreadable: {exc}", file=sys.stderr)
        return 2
    problems = reconcile(inventory, declarations)
    if problems:
        print("\nFAIL — strip inventory disagrees with declarations:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    print("\nOK — every row's strip state matches its signed declaration.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
