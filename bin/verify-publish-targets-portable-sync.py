# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
verify-publish-targets-portable-sync.py — divergence check between the
DoE-tracked `setup/publish-targets.portable` and the PERCOLATE_ROOT-resolved
live-install copy.

THE DRIFT THIS GUARDS: `setup/publish-targets.portable` governs what
`publish.sh` ships to the PUBLIC OSS `coordinator-claude` mirror, including
the fail-closed wiki-publishing allowlist. From 2026-05-17 to 2026-07-10 that
allowlist silently stopped restricting `docs/wiki` and the seed grew
unratified from 8 wikis to 200 (commit `9a8d7b2`) — nobody decided this, the
allowlist just stopped doing its job. The 2026-07-21 restore-oss-seed-wiki
slice narrowed the DoE-tracked copy back to a curated 7-wiki seed and added
`coordinator/tests/test_publish_seed_wiki_allowlist.py` as a regression guard
— but that guard reads ONLY the DoE-tracked copy
(`REPO_ROOT = Path(__file__).resolve().parents[2]`), so it stays green even
if a SECOND, untracked copy at the live install location silently re-drifts.

WHY TWO COPIES EXIST: `publish.sh` reads whichever `publish-targets.portable`
sits beside it (`$SCRIPT_DIR`-relative). On a live-install machine that is
typically `${CLAUDE_HOME:-$HOME}/.claude/setup/publish-targets.portable` — a
file this repo does not track and has no sync mechanism for. Per
`coordinator/.percolate-ignore` (~line 99-101), the doctrine-documented
governing location is `$PERCOLATE_ROOT/setup/publish-targets.portable`. The
two copies were byte-identical only because they were hand-synced on
2026-07-21; nothing enforces that they stay that way, and a future edit to
either alone re-diverges them with zero test signal.

P-22 SEMANTICS CORRECTION (2026-08-01, docs/plans/2026-08-01-percolate-root-
rung-ordering.md chunk C4): this check's "live" side used to resolve via the
full PERCOLATE_ROOT ladder (`coordinator_percolate_runtime_root()`), which
now (chunk C1) prefers a registry-first DoE-root pointer rung ahead of the
shared install. On any machine with `repos.doe_claude` set — the machine
class that plan exists for — that made this check's "live" side and its
"DoE" side (`_doe_tracked_path()`, also resolved via the same registry key)
resolve to the IDENTICAL file: a tautological self-comparison that could
never observe drift. `_resolve_live_targets_path()` therefore no longer
calls the shared ladder at all — it resolves directly to rung 4 of that
ladder (`_rung4_shared_install()`, i.e. `${CLAUDE_HOME:-$HOME}/.claude`),
restoring the useful template-vs-live-authored comparison this check exists
to make. As a structural backstop against this collapsing again (by a future
resolution change, an operator override, or a machine shape not anticipated
here), `main()` treats a live path that still equals the DoE path as
INCONCLUSIVE, not a clean pass — see Negative-spec.

This check is READ-ONLY on both copies. It never syncs, fixes, or writes —
see `verify-templates-setup-sync.py`'s module docstring for why a prior
live->template --fix path on a sibling check was reverted (a sync tool on a
public-publish boundary config is a worse bug than the one it closes).

POST-MOVE THREE-COPY TOPOLOGY (2026-08-03,
docs/plans/2026-08-03-klabauter-rows-relocate-into-claude-klabauter.md chunk C4): the
four `claude-klabauter*` rows moved from DoE-claude's tracked copy into this
repo's own `setup/publish-targets.portable` (this script's own checkout).
DoE keeps its copy until it runs its source-side residual audit (AC8/C6) —
until then both DoE's and this repo's tracked copies carry these four rows,
with this side's row-4 (`source_subdir`) sigils simplified to
checkout-relative form per AC5 (published bytes unchanged, so this is NOT a
divergence). Once DoE strips its side, the DoE-tracked copy loses these four
names while the shared-install (live) copy may still carry a stale,
not-yet-republished mirror of them — a name-presence mismatch that reflects
ownership having moved, not drift. `KLABAUTER_TARGET_NAMES` is therefore
excluded from the ordinary DoE-vs-live two-way comparison (see `_diff_rows`'s
`exclude_names`); `_check_claude_klabauter_owned_rows_present` is the narrower
replacement signal — it still fails loud if one of those excluded names goes
missing from this repo's OWN tracked copy, so exclusion cannot silently hide an
accidental drop from every copy at once.

ALLOWLIST ROT — THE THIRD BLINDNESS (2026-08-07, carried item
`cf-allowlist-rot-guard-4a1c9e` from
state/handoffs/2026-08-07_222114_percolate-performance-delta-sweep.md):
everything above compares two COPIES against each other and never consults
the source tree the rows describe. An allowlist entry (field 7) naming a
path that no longer exists in that tree therefore compares clean forever, in
both copies, indefinitely — the two files agree perfectly about a file that
is gone. This is not hypothetical: a publish row aborted fail-closed on a
rotted entry (`build_allowlisted_source` raises `AllowlistError` per
AC18(c) — an absent entry is indistinguishable from a typo'd or wrong-rooted
one and must abort rather than silently narrow the publish set) for an
unknown length of time, and nothing reported it; it surfaced only when
someone ran a full two-pass publish proof. `_check_allowlist_entries_resolve`
closes the observation gap: each row's own field-4 `source_subdir` names the
tree its field-7 entries are relative to, so the check resolves that root and
asserts each entry exists — the same `root / entry` resolution
`build_allowlisted_source` performs at publish time, run at verification time
instead. This predicts the MISSING-ENTRY `AllowlistError` a publish would
abort on (AC18(c)); it does not predict every class of `AllowlistError` the
engine can raise — `build_allowlisted_source` also enforces a collision
precondition and a multi-source `.percolate-ignore`-readability precondition
that this check does not reproduce. It runs against the two TRACKED copies
(DoE's and this repo's own),
each rooted at the checkout that owns it, and it needs no live install to do
so — so it is computed ahead of every live-resolution outcome and survives
the clean-skip and INCONCLUSIVE paths that end the two-copy comparison. See
Negative-spec for why the live copy is not a third subject and for every
entry shape deliberately not flagged.

Placement: coordinator-doctor probe (see `docs/wiki/coordinator-doctor.md`
P-11 precedent — a machine-dependent check that is NOT wired into the fast
test tier because a missing live install must not fail a machine that never
had one). This script is invoked directly by the probe; it is NOT trampolined
through a claude-klabauter "op" module because it has no bash predecessor to port —
only the already-ported PERCOLATE_ROOT resolver
(`coordinator_core.percolate.runtime_root`) is imported from claude-klabauter, exactly
the same sanctioned read-only cross-repo import pattern `cc_invoke.py`'s
`_resolve_claude_klabauter_root` ladder uses.

Spec backlink: state/review-trail/findings/2026-07-21-codereview-slicerestore-oss-seed-wiki-setup-publish-targets-portable-coordinat.md
  (Finding 1a — code-reviewer, restore-oss-seed-wiki slice).
Debt entry: archive/debt-backlog/2026-07/2026-07-21-publish-targets-portable-divergence-chec-9bef66cfd78e.yaml

Negative-spec:
    - Does NOT write, sync, or "fix" either copy — inspect-only, no --fix flag.
    - Does NOT hard-fail when the live copy is absent (no ~/.claude install on
      this machine) — that is the expected, common state on a fresh clone-only
      machine, not a defect. Exits 0 with a "not applicable" message.
    - Does NOT do a byte-for-byte whole-file diff — pure comment/whitespace
      differences between the two files are not divergence; only the parsed
      target ROWS (and, for the allowlist field specifically, its entries as
      an order-insensitive set) are compared. See `_parse_rows` / `_diff_rows`.
    - Does NOT resolve its live side through the full PERCOLATE_ROOT ladder
      (`coordinator_percolate_runtime_root()`) — that ladder's DoE-root-
      pointer rung resolves via the same registry key this script's
      `_doe_tracked_path()` uses, which would make the two sides tautological
      on any machine with `repos.doe_claude` set. `_resolve_live_targets_path()`
      resolves the shared-install rung (`_rung4_shared_install()`) directly.
    - Does NOT report a clean pass when the live path and the DoE path
      resolve to the identical file — that self-comparison can observe no
      drift, so `main()` reports INCONCLUSIVE (non-zero exit) instead of OK,
      even though this is not itself a divergence finding. This guard stays
      in place regardless of how `_resolve_live_targets_path()` resolves in
      the future — see P-22 SEMANTICS CORRECTION above.
    - Does NOT flag `KLABAUTER_TARGET_NAMES` as DoE-vs-live divergence — see
      POST-MOVE THREE-COPY TOPOLOGY above. This is a deliberate, documented
      exclusion, not a blind spot: `_check_claude_klabauter_owned_rows_present` still
      fails loud if any of those names is absent from this repo's own
      tracked copy. The allowlist-rot check is NOT scoped by this exclusion
      — it reads each tracked copy against its own checkout, so the
      klabauter rows are the ones it covers most directly.
    - Does NOT run the allowlist-rot check against the LIVE copy. The
      shared-install root is a deployed install, not the source checkout its
      rows describe: `~/.claude` legitimately carries none of the trees
      (`coordinator_core`, `coordinator/bin`, `scripts`) the rows name, so
      rooting the check there would report every entry of every row as
      missing. The two tracked copies are also where rot originates — they
      are what a human edits — so checking them catches it at the source
      rather than at the mirror.
    - Does NOT skip the allowlist-rot check when the live copy is absent,
      unresolvable, or collapsed onto the DoE path. Rot detection needs no
      live install — it reads the two tracked copies against their own
      checkouts — so `main()` computes it ABOVE every live-resolution
      outcome and reports it from each terminal path. A clone-only machine
      therefore says the DoE-vs-live comparison was not applicable AND exits
      1 on rot, rather than skipping the one check it could still run. See
      `main()`'s LIVE-INDEPENDENT comment; the two finding classes stay
      separately labelled so an operator knows which signal they have.
    - Does NOT hard-fail an allowlist row whose SOURCE ROOT does not resolve
      — an unresolvable `plugin-source:<key>` (the registry key is unset on
      this machine) or a `source_subdir` naming no directory in the owning
      checkout skips that ROW's entries cleanly. This is a per-row skip, not
      the whole-check skip an absent live install triggers for the two-copy
      comparison. Only a RESOLVED root with a missing entry under it is a
      finding. Load-bearing rather than lenient:
      `setup/publish-targets.portable`'s
      `claude-klabauter-publish-repo-toplevel` row is authored against an
      agreed shape whose `dist/klabauter-toplevel` tree does not exist yet,
      and a machine without `plugin.mirrors.coordinator-claude.source_path`
      set cannot see DoE's source tree at all — neither is allowlist rot.
    - Does NOT apply `_resolve_source_sigil`'s non-strict
      `<meta-root>/plugins/<key>` fallback for an unset
      `plugin.mirrors.<key>.source_path`. That fallback is a warn-and-guess
      on the publish path; guessing a root here would manufacture a whole
      row's worth of missing-entry findings out of a machine-configuration
      gap. Unset means skip.
    - Does NOT flag `!`-prefixed EXCLUSION entries as rot. An exclusion is
      validated against the paths the inclusion entries actually admitted,
      and `_apply_exclusions` accepts one whose target was already removed by
      the contributing root's `.percolate-ignore` — so an exclusion naming a
      path absent from the source tree is legal by construction, not rot.
    - Does NOT flag allowlist entries routed elsewhere by a row's field-8
      `source_map`. Those resolve against a different contributing root
      (`entry_roots = {entry: sm.get(entry, real_src)}` in
      `build_allowlisted_source`), reached through a strict registry
      resolution this check does not reproduce; the row's remaining,
      primary-rooted entries are still checked rather than the whole row
      being skipped.
    - Does NOT re-validate entry SAFETY (`/`-absolute, `..`-traversing) or
      re-derive what an allowlist SHOULD contain. `build_allowlisted_source`
      already rejects unsafe entries loudly at publish time, and an entry
      deliberately omitted from a row is a ratified curation decision (see
      `claude-klabauter-toplevel-reference`'s two recorded omissions), not a
      gap this check may fill. It answers exactly one question: does every
      entry a row claims still exist under the root that row names?
    - Does NOT distinguish a case-mismatched entry from a correct one on a
      case-insensitive filesystem (Windows, default macOS): `Path.exists()`
      inherits the platform's casing rules, so an entry that would fail a
      publish on a case-sensitive host can pass here. Out of scope — the
      cross-platform casing surface belongs to a portability check, not to
      this one.
"""

# Review: code-reviewer — Finding 3 (P2, sliceverify-publish-targets-portable-sync):
# moved below the module docstring so the docstring binds to __doc__ (a future-import
# preceding the docstring makes it an inert discarded expression statement instead).
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

_BIN_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(_BIN_DIR, "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root, require_dispatch_engine_on_path  # noqa: E402

# `_registry_machine_local_get` is the only reader this lib exposes for an
# arbitrary registry key, and the allowlist-rot check needs exactly one class
# of them (`plugin.mirrors.<key>.source_path`) to resolve a `plugin-source:`
# source root. Imported rather than reimplemented: it already carries the
# sys.executable-not-PATH resolution and the Windows CREATE_NO_WINDOW guard
# that a local re-roll of `machine-local get` would drop.
from coordinator_registry import (  # noqa: E402
    _DoeUnresolvable,
    _registry_machine_local_get,
    doe_root,
)

_TARGETS_RELATIVE = Path("setup") / "publish-targets.portable"

_SOURCE_SUBDIR_FIELD = 3
_ALLOWLIST_FIELD = 6
_SOURCE_MAP_FIELD = 7

# Rows relocated into this repo from DoE-claude by
# docs/plans/2026-08-03-klabauter-rows-relocate-into-claude-klabauter.md (chunks
# C3/C4). See the module docstring's POST-MOVE THREE-COPY TOPOLOGY section
# for why these four names are excluded from the ordinary DoE-vs-live
# comparison below rather than compared field-by-field: this repo's copy
# deliberately carries simplified, checkout-relative `source_subdir` sigils
# (AC5 — published bytes unchanged), so a literal field diff against DoE's
# still-fully-qualified-`plugin-source:`-sigil row would report a false
# divergence on every one of these rows until DoE strips its side (C6/AC8).
KLABAUTER_TARGET_NAMES = frozenset(
    {
        "claude-klabauter",
        "claude-klabauter-publish-repo-toplevel",
        "claude-klabauter-toplevel-reference",
        "claude-klabauter-bin",
    }
)


def _claude_klabauter_tracked_path() -> Path:
    """Return this repo's own tracked `setup/publish-targets.portable`.

    Unlike `_doe_tracked_path()`, no registry lookup is needed: this script
    lives inside the engine-resident checkout
    (`coordinator/bin/verify-publish-targets-portable-sync.py`), so its own
    tracked copy is always `parents[2]` of `__file__` — the same
    self-location-first pattern `cc_invoke.resolve_colocated_claude_klabauter_root`
    uses for the CLI surface, applied here to the config surface this check
    reads.
    """
    return Path(__file__).resolve().parents[2] / _TARGETS_RELATIVE


def _doe_tracked_path() -> Path:
    """Return the DoE-tracked publish-targets.portable path.

    Resolved via doe_root() (env DOE_ROOT/REPO_DOE_CLAUDE -> machine-local
    repos.doe_claude -> raise), not this script's own __file__ location:
    this executable lives in claude-klabauter while setup/ stayed in
    DoE-claude per DR-047 (see verify-templates-bin-sync.py's
    _resolve_plugin_root() for the same fix on a sibling script). Exits 1
    with a diagnostic if doe_root() cannot resolve — a gate script must not
    silently degrade to comparing nothing.
    """
    try:
        root = doe_root()
    except _DoeUnresolvable as exc:
        print(
            "verify-publish-targets-portable-sync.py: cannot resolve the "
            f"DoE-claude repo root ({exc}). Set repos.doe_claude in the "
            "machine-local registry, or set the DOE_ROOT env var.",
            file=sys.stderr,
        )
        sys.exit(1)
    return Path(root) / _TARGETS_RELATIVE


def _resolve_live_targets_path() -> Optional[Path]:
    """Resolve the live-install (shared-install) publish-targets.portable
    path — rung 4 of the PERCOLATE_ROOT ladder, resolved DIRECTLY, not via
    the full `coordinator_percolate_runtime_root()` ladder.

    P-22 SEMANTICS CORRECTION (docs/plans/2026-08-01-percolate-root-rung-
    ordering.md chunk C4): the full ladder's rung 3 (DoE-root pointer) now
    resolves via the same registry key (`repos.doe_claude`) this script's
    `_doe_tracked_path()` uses via `doe_root()`. On any machine with that key
    set, calling the full ladder here would make this function's "live" side
    and `_doe_tracked_path()`'s "DoE" side resolve to the identical file —
    a tautological self-comparison that can never observe drift. This
    function therefore imports and calls `_rung4_shared_install()` directly,
    restoring the useful template-vs-live-authored comparison this check
    exists to make: the copy that would actually be found beside a
    `publish.sh` invocation at `${CLAUDE_HOME:-$HOME}/.claude`, independent
    of whether a DoE clone pointer is configured.

    Returns None when the claude-klabauter checkout itself is unresolvable (no
    engine-root rung matched — e.g. `claude-klabauter` isn't registered on this
    machine), OR when the shared-install root's setup/publish-targets.portable
    does not exist (e.g. a fresh machine with no ~/.claude install). Both are
    the same "not applicable on this machine" outcome from this check's
    perspective — see Negative-spec above.
    """
    # Review: code-reviewer — Finding 1 (P1, sliceverify-publish-targets-portable-sync):
    # _resolve_claude_klabauter_root() previously raised RuntimeError OUTSIDE this try block, so an
    # unresolvable claude-klabauter checkout propagated to main()'s sibling `except RuntimeError`
    # and hard-failed with exit 1 — indistinguishable from a genuine row divergence, and
    # contradicting the skip-clean contract this module's own docstring/Negative-spec and
    # the P-22 wiki row assert. Both RuntimeError sources are now folded into the same
    # clean-skip path.
    try:
        claude_klabauter_root = require_dispatch_engine_on_path()
    except RuntimeError:
        return None
    from coordinator_core.percolate.runtime_root import _rung4_shared_install

    live_path = _rung4_shared_install() / _TARGETS_RELATIVE
    if not live_path.is_file():
        return None
    return live_path


def _parse_rows(text: str) -> dict[str, str]:
    """Parse pipe-delimited target rows keyed by their field-1 name.

    Skips blank lines and `#`-comment lines — this is the "ignore pure
    comment/whitespace differences" decision (see module docstring
    Negative-spec): a file that only gained a comment or a trailing blank
    line is NOT divergence.
    """
    rows: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split("|")
        name = fields[0].strip()
        if not name:
            # Review: code-reviewer — Finding 4 (nit): non-fatal warning so a
            # malformed blank-name row doesn't silently drop out of the comparison.
            print(
                f"verify-publish-targets-portable-sync.py: WARNING — skipping "
                f"malformed row with blank name: {line!r}",
                file=sys.stderr,
            )
            continue
        if name in rows:
            # Review: code-reviewer — Finding 4 (nit): non-fatal warning so a
            # duplicated target name doesn't silently overwrite the earlier row.
            print(
                f"verify-publish-targets-portable-sync.py: WARNING — duplicate "
                f"target name {name!r}; keeping the last occurrence, discarding "
                f"earlier row: {rows[name]!r}",
                file=sys.stderr,
            )
        rows[name] = line
    return rows


def _row_diff_reason(doe_row: str, live_row: str) -> Optional[str]:
    """Compare two raw rows for the SAME target name; return a human-readable
    reason string if they diverge, else None.

    Field-by-field comparison (stripped). The allowlist field (index 6, 1-
    indexed field 7 — the same convention `test_publish_seed_wiki_allowlist.py`
    documents) is compared as an order-insensitive set of comma-separated
    entries, since a hand-edit that merely reorders allowlist entries is not
    a meaningful divergence. Every other field is compared as an exact
    stripped string. A field-count mismatch (e.g. one row carries an
    allowlist field and the other doesn't) is itself reported as a divergence
    — that is literally the flat-mirror bug state
    `test_publish_seed_wiki_allowlist.py` guards against.
    """
    doe_fields = [f.strip() for f in doe_row.split("|")]
    live_fields = [f.strip() for f in live_row.split("|")]

    if len(doe_fields) != len(live_fields):
        return (
            f"field count differs (DoE={len(doe_fields)} fields, "
            f"live={len(live_fields)} fields) — DoE row: {doe_row!r} "
            f"live row: {live_row!r}"
        )

    diffs: list[str] = []
    for idx, (doe_field, live_field) in enumerate(zip(doe_fields, live_fields)):
        if idx == 6:
            doe_set = {e.strip() for e in doe_field.split(",") if e.strip()}
            live_set = {e.strip() for e in live_field.split(",") if e.strip()}
            if doe_set != live_set:
                only_doe = sorted(doe_set - live_set)
                only_live = sorted(live_set - doe_set)
                diffs.append(
                    f"allowlist (field 7) differs — only in DoE: {only_doe}; "
                    f"only in live: {only_live}"
                )
        elif doe_field != live_field:
            diffs.append(
                f"field {idx + 1} differs — DoE: {doe_field!r} live: {live_field!r}"
            )

    if diffs:
        return "; ".join(diffs)
    return None


def _diff_rows(
    doe_rows: dict[str, str],
    live_rows: dict[str, str],
    *,
    exclude_names: frozenset[str] = frozenset(),
) -> list[str]:
    """Return a list of human-readable divergence descriptions, one per
    diverging target name. Empty list means the two files agree (semantically,
    per the field-comparison rules in `_row_diff_reason`).

    `exclude_names` skips target names entirely — used for
    `KLABAUTER_TARGET_NAMES` post-move (see module docstring, POST-MOVE
    THREE-COPY TOPOLOGY): those rows legitimately differ between DoE's and
    this repo's tracked copies (simplified source sigils) and legitimately go
    present-only-in-one-side once DoE strips its rows, neither of which is
    real drift. `_check_claude_klabauter_owned_rows_present` is the narrower signal
    that replaces this check for excluded names.
    """
    findings: list[str] = []
    all_names = sorted((set(doe_rows) | set(live_rows)) - exclude_names)
    for name in all_names:
        doe_row = doe_rows.get(name)
        live_row = live_rows.get(name)
        if doe_row is None:
            findings.append(
                f"'{name}': present in live copy only (missing from DoE-tracked "
                f"copy) — live row: {live_row!r}"
            )
            continue
        if live_row is None:
            findings.append(
                f"'{name}': present in DoE-tracked copy only (missing from live "
                f"copy) — DoE row: {doe_row!r}"
            )
            continue
        reason = _row_diff_reason(doe_row, live_row)
        if reason is not None:
            findings.append(f"'{name}': {reason}")
    return findings


def _check_claude_klabauter_owned_rows_present(
    claude_klabauter_rows: dict[str, str], owned_names: frozenset[str]
) -> list[str]:
    """Sanity check for `owned_names` (`KLABAUTER_TARGET_NAMES`): each name
    `_diff_rows` excludes from the DoE-vs-live comparison must still be
    PRESENT in this repo's own tracked copy. Exclusion is meant to silence a
    false-positive ownership-move signal, not to blind the probe to a real
    regression (e.g. a row accidentally dropped from that file while
    editing it) — this is the narrower replacement check for exactly those
    names. See module docstring, POST-MOVE THREE-COPY TOPOLOGY.
    """
    return [
        f"'{name}': excluded from the DoE-vs-live comparison as a "
        "claude-klabauter-owned row (KLABAUTER_TARGET_NAMES) but MISSING from "
        "claude-klabauter's own tracked copy"
        for name in sorted(owned_names)
        if name not in claude_klabauter_rows
    ]


def _resolve_row_source_root(source_subdir: str, checkout_root: Path) -> Optional[Path]:
    """Resolve a row's field-4 `source_subdir` to the tree its field-7
    allowlist entries are relative to, or None when this machine cannot see
    that tree.

    Mirrors `resolve_target._resolve_source_sigil` in its resolved-path shape
    — `plugin-source:<key>[/subpath]` reads
    `plugin.mirrors.<key>.source_path`, anything else is
    `checkout_root / sigil` — with one deliberate divergence, stated as
    Negative-spec above: the non-strict `<meta-root>/plugins/<key>` fallback
    for an unset registry key is NOT applied here. That fallback exists so a
    publish can proceed on a best guess; a guess in this position would
    invent an empty root and report every entry of the row as rotted.

    `checkout_root` is the repo root of the copy being read (the parent of
    its own `setup/`), never this script's own checkout: a row is always
    relative to the tree that tracks it, which is what makes DoE's copy and
    this repo's copy separately checkable.
    """
    if source_subdir.startswith("plugin-source:"):
        ref = source_subdir[len("plugin-source:") :]
        key, _, subpath = ref.partition("/")
        if not key:
            return None
        # Review: code-reviewer — mirrors _resolve_source_sigil's ".." rejection
        # on ps_subpath (resolve_target.py:423-427); without it this read-only
        # probe would silently .exists()-check outside the intended root
        # instead of raising, an undocumented second divergence from the
        # function it claims to mirror "with one deliberate divergence".
        if subpath and ".." in subpath:
            return None
        base = _registry_machine_local_get(f"plugin.mirrors.{key}.source_path")
        if base is None:
            return None
        return Path(base) / subpath if subpath else Path(base)
    return checkout_root / source_subdir


def _source_map_routed_entries(source_map_field: str) -> frozenset[str]:
    """Entry names a row's field-8 `source_map` routes to a contributing root
    other than the row's own field-4 source.

    Field grammar (`resolve_target._resolve_publish_mirror_row`):
    `<source-sigil>=<csv-of-entries>` segments joined by `;`. A malformed
    segment is skipped rather than reported — this check is not the
    source_map grammar gate (`resolve_publish_row` raises on it at publish
    time), and treating an unparseable segment as routing nothing would
    silently move its entries into the primary-root existence check.
    """
    routed: set[str] = set()
    for segment in source_map_field.split(";"):
        _, sep, entry_csv = segment.partition("=")
        if not sep:
            continue
        routed.update(entry.strip() for entry in entry_csv.split(",") if entry.strip())
    return frozenset(routed)


def _check_allowlist_entries_resolve(
    rows: dict[str, str], checkout_root: Path, *, copy_label: str
) -> list[str]:
    """Return one finding per allowlist entry that names a path absent from
    the source tree its own row points at — the rot `_diff_rows` is blind to
    by construction, since a rotted entry sits identically in both copies.

    Resolution is deliberately the same `root / entry` that
    `build_allowlisted_source` performs, so a finding here predicts the
    MISSING-ENTRY `AllowlistError` a publish of that row would abort on —
    not every class of `AllowlistError` the engine can raise (it also
    enforces a collision precondition via `_collision_preflight` and a
    multi-source `.percolate-ignore`-readability precondition, neither of
    which this check reproduces), not a stricter parallel rule that could
    disagree with the engine on the class it does cover.
    """
    findings: list[str] = []
    for name in sorted(rows):
        fields = [f.strip() for f in rows[name].split("|")]
        if len(fields) <= _ALLOWLIST_FIELD or not fields[_ALLOWLIST_FIELD]:
            continue
        source_subdir = fields[_SOURCE_SUBDIR_FIELD]
        if not source_subdir:
            continue
        source_root = _resolve_row_source_root(source_subdir, checkout_root)
        if source_root is None or not source_root.is_dir():
            continue
        routed = (
            _source_map_routed_entries(fields[_SOURCE_MAP_FIELD])
            if len(fields) > _SOURCE_MAP_FIELD
            else frozenset()
        )
        missing = [
            entry
            for entry in (e.strip() for e in fields[_ALLOWLIST_FIELD].split(","))
            if entry
            and not entry.startswith("!")
            and entry not in routed
            and not (source_root / entry).exists()
        ]
        if missing:
            findings.append(
                f"'{name}' ({copy_label} copy): allowlist (field 7) names "
                f"{len(missing)} path(s) absent from its own source root "
                f"{source_root}: {sorted(missing)}"
            )
    return findings


def _report_rot_findings(rot_findings: list[str]) -> None:
    """Print the allowlist-rot finding block. Factored out because rot is
    reported from every terminal path in `main()`, not just the one that
    reaches the two-copy comparison — see that function's LIVE-INDEPENDENT
    comment for why.

    See module docstring's ALLOWLIST ROT section for why this matters: a
    rotted entry aborts a publish fail-closed (AllowlistError, AC18(c)) and
    is otherwise invisible to the two-copy comparison, since it sits
    identically in every copy.
    """
    print(
        "verify-publish-targets-portable-sync.py: FAIL — allowlist rot: "
        "entries naming paths that no longer exist under the source root "
        "their own row points at. A publish of these rows aborts "
        "fail-closed (AllowlistError, AC18(c)); the two-copy comparison "
        "cannot see this, since a rotted entry sits identically in every "
        "copy:",
        file=sys.stderr,
    )
    for finding in rot_findings:
        print(f"  - {finding}", file=sys.stderr)
    print(
        "This check is READ-ONLY — it does not edit either copy. Recover "
        "manually: for each named entry, decide whether the source path "
        "moved (repoint the entry) or was deleted (drop the entry). Do "
        "not widen the allowlist to make the error go away — an entry's "
        "absence from a row is sometimes a ratified curation decision.",
        file=sys.stderr,
    )


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv:
        print(
            "verify-publish-targets-portable-sync.py: no arguments accepted "
            "(inspect-only, no --fix)",
            file=sys.stderr,
        )
        return 2

    doe_path = _doe_tracked_path()
    if not doe_path.is_file():
        print(
            f"verify-publish-targets-portable-sync.py: ERROR — DoE-tracked "
            f"copy not found at {doe_path}",
            file=sys.stderr,
        )
        return 1

    doe_rows = _parse_rows(doe_path.read_text(encoding="utf-8"))

    claude_klabauter_path = _claude_klabauter_tracked_path()
    claude_klabauter_rows = (
        _parse_rows(claude_klabauter_path.read_text(encoding="utf-8")) if claude_klabauter_path.is_file() else {}
    )

    # LIVE-INDEPENDENT: the allowlist-rot check is computed here, ABOVE every
    # live-copy resolution outcome, because it needs no live install at all —
    # it reads the two TRACKED copies against their own checkouts. Ordering it
    # below the `live_path is None` clean-skip (as the first cut of this check
    # did) made it dead on exactly the clone-only machine class where it is
    # cheapest to run and where the skip-clean contract exists. The two
    # finding classes then compose at every terminal path: a machine with no
    # live install can report rot and exit 1 while still saying the
    # DoE-vs-live comparison was not applicable.
    rot_findings = _check_allowlist_entries_resolve(
        doe_rows, doe_path.parent.parent, copy_label="DoE-tracked"
    )
    rot_findings += _check_allowlist_entries_resolve(
        claude_klabauter_rows, claude_klabauter_path.parent.parent, copy_label="claude-klabauter-tracked"
    )

    try:
        live_path = _resolve_live_targets_path()
    except ImportError as exc:
        print(
            "verify-publish-targets-portable-sync.py: "
            f"coordinator_core.percolate.runtime_root not importable: {exc}",
            file=sys.stderr,
        )
        if rot_findings:
            _report_rot_findings(rot_findings)
        return 1
    except RuntimeError as exc:
        print(
            "verify-publish-targets-portable-sync.py: engine-root resolution "
            f"failed: {exc}",
            file=sys.stderr,
        )
        if rot_findings:
            _report_rot_findings(rot_findings)
        return 1

    if live_path is None:
        print(
            "verify-publish-targets-portable-sync.py: not applicable — no "
            "live-install publish-targets.portable resolvable on this "
            "machine (no PERCOLATE_ROOT rung matched, or the resolved root "
            "has no setup/publish-targets.portable). Skipping the DoE-vs-live "
            "comparison cleanly.",
        )
        if rot_findings:
            _report_rot_findings(rot_findings)
            return 1
        print(
            "verify-publish-targets-portable-sync.py: OK — the allowlist-rot "
            "check needs no live install and DID run: every resolvable "
            f"allowlist entry in {doe_path} and {claude_klabauter_path} exists under "
            "its own source root."
        )
        return 0

    if live_path.resolve() == doe_path.resolve():
        # P-22 SEMANTICS CORRECTION (chunk C4): a self-comparison observes no
        # drift by construction, so it must never report as a clean pass —
        # that would silently retire this check's own signal. This guard
        # stays reachable even after the resolution fix above, in case a
        # future change (a rung reorder, an operator override) collapses the
        # two paths again.
        print(
            "verify-publish-targets-portable-sync.py: INCONCLUSIVE — live "
            f"copy resolves to the DoE-tracked copy itself ({doe_path}); "
            "this check has no second copy to compare against, so it cannot "
            "detect divergence. This is not itself a divergence finding, "
            "but it must not be reported as a clean pass — investigate why "
            "the live-side resolution (shared-install rung) collapsed onto "
            "the DoE-tracked path.",
            file=sys.stderr,
        )
        # Rot is still reportable here — it never depended on there being a
        # second copy — and is the one actionable signal this run can offer
        # an operator whose live resolution has collapsed.
        if rot_findings:
            _report_rot_findings(rot_findings)
        return 1

    live_rows = _parse_rows(live_path.read_text(encoding="utf-8"))

    findings = _diff_rows(doe_rows, live_rows, exclude_names=KLABAUTER_TARGET_NAMES)
    findings += _check_claude_klabauter_owned_rows_present(claude_klabauter_rows, KLABAUTER_TARGET_NAMES)

    if not findings and not rot_findings:
        print(
            f"verify-publish-targets-portable-sync.py: OK — {doe_path} and "
            f"{live_path} agree ({len(doe_rows)} target rows compared, "
            f"{len(KLABAUTER_TARGET_NAMES)} claude-klabauter-owned row(s) excluded per "
            "POST-MOVE THREE-COPY TOPOLOGY and separately confirmed present "
            f"in {claude_klabauter_path}); every resolvable allowlist entry in both "
            "tracked copies exists under its own source root."
        )
        return 0

    if rot_findings:
        _report_rot_findings(rot_findings)
        if not findings:
            return 1

    print(
        "verify-publish-targets-portable-sync.py: FAIL — DoE-tracked copy "
        f"({doe_path}) and live copy ({live_path}) have diverged:",
        file=sys.stderr,
    )
    for finding in findings:
        print(f"  - {finding}", file=sys.stderr)
    print(
        "This check is READ-ONLY — it does not sync either copy. Recover "
        "manually: decide which copy is correct (usually the DoE-tracked "
        "copy, since it is version-controlled) and hand-copy the diverging "
        "row(s) to the other file.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
