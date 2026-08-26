"""coordinator/lib/percolate/allowlist.py — fail-closed allowlist enforcement
gate for percolate publish targets.

Native-Python port of the allowlist machinery in `setup/publish.sh` (HEAD,
post-8130729b — the commit that made the gate fail CLOSED when a declared
allowlist was not actually applied). Three pieces, ported faithfully:

  1. `build_allowlisted_source` — port of `_build_allowlisted_source`
     (setup/publish.sh:713-790). Builds a restricted temp tree containing
     ONLY the allowlisted subpaths of a real source tree. Rejects any
     allowlist entry that is absolute (`/`-leading) or contains `..` —
     both shapes could escape the real source tree via `cp -r`/copytree.
     Copies `.percolate-ignore` into the restricted tree so downstream
     ignore-rule loading (which reads `<SOURCE_DIR>/.percolate-ignore`)
     does not fall through to the "publish everything" default.

  2. `check_working_data_paths` — port of `_check_working_data_paths`
     (setup/publish.sh:803-855). Secondary / defense-in-depth scan of the
     restricted tree for any file under a known working-data prefix
     (state/, docs/plans, docs/research, docs/problems, cross-repo/,
     archive/, tasks/) or any non-wiki docs/* path. Returns False (hard
     fail) on any match — the bash original's "return 1" contract, not a
     warn-and-continue.

  3. `assert_allowlist_applied` — port of the FATAL post-condition
     (setup/publish.sh:1670-1678). If a target declared an allowlist, the
     source actually used for sync MUST be the restricted temp tree built
     by `build_allowlisted_source` — never the original, unrestricted
     source. There is NO override for this check. An unenforced allowlist
     is never a deliberate opt-out; it is the exact failure mode (a full,
     unrestricted publish of internal doctrine to a public mirror) this
     gate exists to prevent.

Every ambiguity in this module resolves toward refusing to publish, never
toward permitting one. A gate that fails open here is a defect even if
every test passes.

## Exclusion entries (leading `!`)

A `!`-prefixed allowlist entry (e.g. `!coordinator_core/benchmarks/fixtures/repo`)
is a PM-approved exclusion, not a second inclusion vocabulary: it removes a
subpath that some plain entry already admitted, letting a publish row wave
off legitimate content (test-fixture trees whose *fixture data* happens to
reuse a `_DENY_PREFIXES` segment name) without widening `_DENY_PREFIXES`
itself or teaching `check_working_data_paths` to look the other way for a
path that still ships. Chosen over a foreign exclusion syntax (e.g. glob
negation, a separate CSV field) because `!` composes with the grammar
`_parse_allowlist_csv` already tokenizes (comma-separated, whitespace-
trimmed) with no new parsing pass, and mirrors the leading-sigil convention
`.percolate-ignore` and `.gitignore` both already use for "narrow this".

Applied by `_apply_exclusions` strictly AFTER `build_allowlisted_source` has
finished copying every plain (inclusion) entry into the restricted tree —
never as a pre-copy filter and never as a rule taught to
`check_working_data_paths`. This ordering is the structural enforcement of
two invariants:

  - **Additive**: a CSV with zero `!`-entries takes the exact code path that
    existed before this feature (the inclusion-only entry list, unchanged);
    exclusion processing is skipped outright when there are none.
  - **Narrows-only, never grants**: an exclusion target must be a STRICT
    DESCENDANT of some inclusion entry — computed from the entry list
    itself, not inferred from what happens to exist on disk — and its
    resolved path must land strictly inside the restricted tree (never
    equal to the tree root). Membership-on-disk is checked only AFTER that
    structural test passes, and a target legitimately absent from disk
    (already dropped by copy-time ignore-filtering, or by an earlier
    exclusion in the same CSV) is treated as already satisfied, not as a
    missing/typo'd target. This closes the two gaps a disk-existence-only
    check left open: `!.` (the tree root itself resolves "inside itself"
    under a naive check) and `!<inclusion-entry-name>` (removing an entry's
    own top-level name wholesale, silently undoing what AC18(c)'s
    fail-closed-on-absent-entry behaviour exists to make loud). There is no
    code path by which an exclusion entry can cause a file to be copied, or
    cause `check_working_data_paths` to suppress a violation for a path
    that is still physically present in the tree it scans — the guard is
    never touched by this feature at all.

A malformed exclusion (`!` with nothing after it, an unsafe `!../x` or
`!/abs` path, a target that is not a strict descendant of any inclusion
entry, or a target that resolves to the tree root itself) raises
`AllowlistError` — never a silent pass — naming the offending entry.

**Mirror-mode consequence, stated explicitly because it is easy to miss:**
on a mirror or flat-mirror publish target, removing a path via `!` is not
merely "don't publish this" — the next publish's orphan-cleanup pass reads
the DESTINATION tree and deletes whatever the source no longer has. An
exclusion therefore becomes a DESTINATION DELETION on the following publish,
not a one-time narrowing of what gets copied this run.

**...with ONE exception, which is not a bug and must not be "fixed" here
(2026-08-21).** A withdrawn TOP-LEVEL FILE is never deleted at the
destination — not by `!`, not by `^`, not by dropping the name from the
inclusion CSV. `publish_sync._sync_mirror_top_level_files` copies source
files and deliberately runs no reverse sweep, because top-level files at a
mirror destination are not target-owned by construction (the mirror repo's
own `README.md`, `LICENSE`, and dotfiles live exactly there) — see that
function's own negative spec. `sync_mirror`'s delete pass runs only INSIDE
each subdirectory, and the orphan sweep only ever `rmtree`s top-level
DIRECTORIES. So the three cases diverge:

    nested path (`!ops/percolate_run.py`)   -> deleted next round
    top-level directory (`^percolate`)      -> deleted next round
    top-level file (`^publish.py`)          -> STRANDED, frozen forever

The stranded copy keeps serving whatever it said the day it was withdrawn,
and no round will ever refresh or remove it. Withdrawing a top-level file
from a mirror row therefore owes a one-time reconciliation commit in the
destination repo; the publish round cannot do it for you. Observed the
expensive way: the 2026-08-20 bin-row deny left eight base CLIs frozen in
`claude-klabauter/coordinator/bin/` for a day, one of them a publish driver
that answered with superseded remediation text.


## Whole-entry deny (leading `^`)

A `^`-prefixed allowlist entry (e.g. `^percolate`) declares that a
top-level name must NEVER be published — a whole-entry deny, distinct
from `!`'s narrows-an-already-admitted-subpath exclusion vocabulary and
not expressible through it: `_apply_exclusions` check (a) requires every
`!` target to be a STRICT DESCENDANT of some plain inclusion entry
already in the CSV, and a top-level name is by definition not nested
under any other top-level entry, so `!percolate` against a CSV with no
plain `percolate` inclusion always raises `AllowlistError` the next time
that row is actually published. Check (a) is not relaxed by this
feature — it stays exactly as strict as before for descendant targets.

`^` is evaluated at INCLUSION-SET CONSTRUCTION (`_split_inclusion_
exclusion`), not as a post-copy removal: a denied name is simply never
added to the inclusion list `build_allowlisted_source` copies from, so
there is no "removal" step, no disk state to reconcile, and no way for
a denied name to have been copied and then un-copied. A name that never
enters the tree needs no removal from it.

This is a declaration, not by itself an enforcement mechanism: nothing
in this module cross-checks a `^`-denied name against the inclusion set
for disjointness (that is a generator-time / row-authoring invariant,
not a `build_allowlisted_source`-time one) — see
`setup/publish-allowlist-declarations.yaml`, the deny declaration's
source of truth, and the plan this feature ships under
(`docs/plans/2026-08-20-the-publish-allowlist-stops-being-hand-m.md`)
for where that disjointness is actually asserted.


## Multi-source publish (source_map)

`build_allowlisted_source` accepts an optional `source_map: dict[str, Path]`
mapping individual allowlist entries to a *contributing root* other than
`real_src`. Two modes, chosen by the shape of `source_map`, never by a
separate flag:

  - **SINGLE-SOURCE** — `source_map` is `None`, empty, or every value in it
    equals `real_src`. Behaviour is byte-for-byte identical to the
    single-root code path that existed before this feature, including the
    tolerant "`.percolate-ignore` absent is fine" branch. Every publish row
    that does not declare a `source_map` takes this path, unchanged.
  - **MULTI-SOURCE** — `source_map` introduces two or more distinct
    contributing roots (the union of `real_src` and `source_map`'s values).
    New rules apply, all fail-closed:
      - Every contributing root MUST have its own readable
        `.percolate-ignore`, or the build aborts (§ below) — a flat single
        ignore file cannot express "this root's rules govern only this
        root's entries," so silence from one root is a leak, not a no-op.
      - Copy-time filtering: each entry is copied through its *own* root's
        ignore matcher, matching on the restricted-tree-relative path (the
        path as it will appear under the temp root), because after
        composition into one tree, provenance (which root a file came from)
        is gone — copy time is the only place it still exists.
      - A composed `.percolate-ignore` is still written at the restricted
        root (kept, not replaced by copy-time filtering alone) — see
        `_compose_percolate_ignore` for why both legs are required.
      - A collision preflight runs before any copy — two allowlist entries
        that would land on the same or a nested restricted-tree path abort
        the build loudly rather than silently shadowing one root's content
        with another's (see `_collision_preflight`).
    Entries absent from `source_map` always resolve against `real_src`,
    in both modes.

NOTE for the future publish.py integration (out of this module's scope —
ignore.py and publish.py are peer/later chunks): the orphan check that
runs after sync must reload ignore rules from the REAL, unrestricted
source dir, not from the restricted allowlist tree this module builds.
That ordering is deliberate in the bash original and must be preserved
when publish.py wires this module together with ignore.py.

Spec backlink: DoE-claude:pln-doe-maximalist-execution-plugi-6d808d
               § W5.1
Port: docs/plans/2026-07-21-percolate-python-port.md (chunk C-W1c).
Multi-source: state/subagent-share/5bae563a-448a-4c5e-96ef-2de84498bd09/
              coordinatorstaff-eng-dfffb96b.md (DoE-claude) §§ 1, 5.

Negative-spec: this module never falls back to publishing the unrestricted
source tree when allowlist enforcement fails or is ambiguous — every error
path here is a refusal, not a downgrade to "publish everything." An
allowlist edit that drops a top-level entry is a destructive change
disguised as a narrowing — the AC18(c) fail-closed-on-absent-entry
behaviour exists precisely so that dropping an entry surfaces as a loud
build failure at the earliest point, not as a silently smaller publish.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path
from typing import IO, Iterable, Optional

# Dual import: this module is loaded two different ways by its own test
# suite. Newer tests (and publish.py) import it package-relatively as
# `percolate.allowlist`, where the leading-dot relative import resolves
# normally. Three older tests predate the `percolate` package and still use
# the bare `sys.path.insert(<...>/lib/percolate)` + `import allowlist` idiom
# — under that idiom this module has no parent package, so the relative
# import raises ImportError ("attempted relative import with no known parent
# package"), not because `.ignore` is missing but because there is no `.` to
# resolve against. The fallback below retries as a plain top-level `ignore`
# import, which resolves because sys.path already contains this file's own
# directory under that same bare-import idiom. Any other ImportError (e.g.
# `ignore.py` genuinely absent or broken) propagates unchanged from the
# fallback line — this only papers over the "no parent package" case, it
# does not mask a real missing dependency.
try:
    from .ignore import PercolateIgnoreMatcher, load_percolate_ignore
except ImportError:
    from ignore import PercolateIgnoreMatcher, load_percolate_ignore  # type: ignore[no-redef]

# Working-data top-level prefix patterns (port of _check_working_data_paths'
# _deny_prefixes array). No trailing slash — matched as an exact leading
# path component or as `.../<pfx>/...` anywhere in the relative path, same
# as the bash `[[ "$_rel" == "${_pfx}/"* || "$_rel" == *"/${_pfx}/"* ]]`.
_DENY_PREFIXES = (
    "state",
    "docs/plans",
    "docs/research",
    "docs/problems",
    "cross-repo",
    "archive",
    "tasks",
)


class AllowlistError(Exception):
    """Raised for a fatal allowlist-gate failure — a hard stop that must
    prevent the caller from proceeding to publish. Never caught and
    downgraded to a warning by this module."""


# Keyed by the `Path` a `build_allowlisted_source` call returned, holding the
# PRE-FILTER (pre-copy-time-ignore) restricted-tree-relative path list for
# that build — see `build_allowlisted_source`'s multi-source branch and
# `get_pre_filter_paths` below. `pathlib.Path` cannot carry an ad-hoc
# attribute (it is `__slots__`-based), and `build_allowlisted_source`'s
# return type is fixed at `-> Path` by contract, so this out-of-band-by-key
# map is the seam: keyed by the unique per-call `tempfile.mkdtemp()` result,
# never overwritten across calls, and cheap to leave unread (single-source
# callers never touch it).
_pre_filter_paths_by_tmp_src: dict[Path, list[str]] = {}


def get_pre_filter_paths(tmp_src: Path) -> Optional[list[str]]:
    """Return the pre-copy-time-ignore-filter restricted-tree-relative path
    list recorded for a `build_allowlisted_source(...)` call that returned
    `tmp_src`, or `None` if that build was single-source (nothing recorded —
    `check_working_data_paths` should walk `tmp_src` directly instead) or if
    `tmp_src` was never produced by this module."""
    return _pre_filter_paths_by_tmp_src.get(tmp_src)


def _parse_allowlist_csv(allowlist_csv: str) -> list[str]:
    """Split a comma-separated allowlist string into trimmed, non-empty
    entries — port of the bash `IFS=',' read -ra` + manual whitespace-trim
    loop."""
    entries = []
    for raw_entry in allowlist_csv.split(","):
        entry = raw_entry.strip()
        if entry:
            entries.append(entry)
    return entries


def _split_inclusion_exclusion(entries: list[str]) -> tuple[list[str], list[str]]:
    """Split `_parse_allowlist_csv`'s output into (inclusion entries,
    exclusion targets).

    Two distinct negative-sigil vocabularies, never conflated:

      - Leading `!` is the EXCLUSION sigil (see module docstring §
        Exclusion entries): a post-copy narrowing of a subpath already
        admitted by some plain entry, applied by `_apply_exclusions`
        strictly AFTER `build_allowlisted_source` has copied every
        inclusion entry in. `!` is stripped and the remainder
        whitespace-trimmed, and the target is returned in `exclusions`.
      - Leading `^` is the DENY sigil (§ Whole-entry deny in the module
        docstring): a top-level name that must never be admitted at
        all, evaluated at INCLUSION-SET CONSTRUCTION — i.e. simply
        never added to `inclusions` — rather than as a post-copy
        removal. A `^`-prefixed entry is recognized and consumed here
        but deliberately NOT surfaced in either returned list: it is
        not an inclusion (the whole point is that it never admits
        anything) and it is not an `!`-exclusion (it never reaches
        `_apply_exclusions`'s strict-descendant check (a) at all, which
        is exactly why a whole-entry deny needs a sigil distinct from
        `!` in the first place — check (a) rejects any target that is
        not a strict descendant of a plain inclusion entry, and a
        top-level name can never satisfy that by construction). Kept
        out of this function's return shape on purpose — `entries` is a
        cross-module contract this module shares with `publish.py`'s
        `_publish_relevant_allowlist_leg`/`_publish_relevant_allowlist_
        leg_dirspec` (see `split_inclusion_exclusion`'s public alias
        below), and those two out-of-repo-file call sites unpack a
        2-tuple; recognizing `^` here without widening the return shape
        is what keeps a denied name from landing in `entries` (where
        the unresolved-entry branch would otherwise turn it into a
        phantom `git status` pathspec) while leaving every existing
        2-tuple unpacker — in this module and its cross-repo consumers
        alike — untouched. The deny declaration's actual source of
        truth is `setup/publish-allowlist-declarations.yaml`, not a
        `^`-entry surviving into a CSV field; this recognition exists
        as a safety net so a `^`-entry can never be silently
        misclassified as a literal inclusion/exclusion path, not as the
        deny mechanism's primary carrier.

    No other entry shape is affected — an entries list with no `!`- or
    `^`-prefixed member returns `(entries, [])` unchanged, which is what
    keeps the no-exclusion, no-deny path additive."""
    inclusions: list[str] = []
    exclusions: list[str] = []
    for entry in entries:
        if entry.startswith("!"):
            exclusions.append(entry[1:].strip())
        elif entry.startswith("^"):
            continue
        else:
            inclusions.append(entry)
    return inclusions, exclusions


# Public aliases for the two cross-module consumers below (Review:
# code-reviewer — coordinator/bin/publish.py's `_publish_relevant_paths`
# consumes these via the SAME parse primitives `build_allowlisted_source`
# uses, to avoid computing the allowlist-entry set twice, differently; the
# leading-underscore names above stay as the in-module-private spelling for
# every other caller in this file, and are NOT renamed or removed).
parse_allowlist_csv = _parse_allowlist_csv
split_inclusion_exclusion = _split_inclusion_exclusion


def _apply_exclusions(
    tmp_src: Path,
    exclusion_targets: list[str],
    inclusion_entries: list[str],
    pre_filter_paths: Optional[list[str]] = None,
) -> list[str]:
    """Remove each exclusion target from the ALREADY-BUILT restricted tree
    (see module docstring § Exclusion entries for why this must run after,
    never before, the inclusion copy).

    Two structural checks gate every target — computed from the entry list
    and the resolved path, never inferred from disk contents:

      (a) `target_rel` must be a STRICT DESCENDANT of some entry in
          `inclusion_entries` (`target_rel.startswith(entry + "/")`).
          Neither an exact match on an entry name (whole-entry removal,
          e.g. `!pkg` against inclusion entry `pkg`) nor an unrelated
          string that happens to coincide with something on disk qualifies.
      (b) `target.resolve()` must land STRICTLY inside `tmp_src.resolve()`
          — non-identity (rules out `!.`, which resolves to the tree root
          itself) AND containment.

    Only once both checks pass does this function look at disk state. A
    target absent from `tmp_src` at that point is NOT automatically an
    error — it may legitimately have never landed there (copy-time
    ignore-filtering already dropped it or a containing directory; see
    `pre_filter_paths`) or have already been removed by an earlier,
    broader exclusion in the same CSV (e.g. `!pkg` alongside
    `!pkg/sub` — checked here even though whole-entry removal itself is
    now rejected by check (a), the same "already satisfied" reasoning
    applies to any exclusion nested under an earlier one). Both of those
    are treated as satisfied, not missing. Genuinely absent (typo'd or
    wrong-rooted) still raises.

    Raises `AllowlistError` for:
      - a bare `!` (empty target after stripping the sigil),
      - an unsafe target (`/`-absolute or containing `..`), same rule as an
        inclusion entry,
      - a target failing structural check (a) or (b) above,
      - a target absent from `tmp_src` that is not explained by an earlier
        exclusion in this same call or by `pre_filter_paths` admitting it
        pre-ignore-filter — this is what makes a typo'd or wrong-rooted
        exclusion a HARD ERROR instead of a silent no-op.

    Returns the restricted-tree-relative FILE paths actually removed from
    disk (directories are expanded to their file members), in the same
    shape `build_allowlisted_source`'s `pre_filter_paths` list uses, so a
    caller can drop them from that list too.
    """
    tmp_src_resolved = tmp_src.resolve()
    pre_filter_set = set(pre_filter_paths or [])
    removed: list[str] = []
    applied_prefixes: list[str] = []

    for target_rel in sorted(set(exclusion_targets)):
        if not target_rel:
            raise AllowlistError(
                "build_allowlisted_source: malformed exclusion entry '!' — an "
                "exclusion entry must name a path after the '!' prefix"
            )
        if target_rel.startswith("/") or ".." in target_rel:
            raise AllowlistError(
                f"build_allowlisted_source: rejected unsafe exclusion entry: '!{target_rel}'"
            )

        is_descendant = any(
            target_rel.startswith(entry + "/") for entry in inclusion_entries
        )
        if not is_descendant:
            raise AllowlistError(
                f"build_allowlisted_source: exclusion entry '!{target_rel}' does not "
                "match any path admitted by the inclusion list — an exclusion must "
                "name a path strictly nested under some already-admitted inclusion "
                "entry (never the entry itself, '.', or an unrelated path), so it "
                "can only ever narrow what inclusion already admitted — fix the "
                "entry or drop it."
            )

        target = tmp_src / target_rel
        target_resolved = target.resolve()
        if target_resolved == tmp_src_resolved or tmp_src_resolved not in target_resolved.parents:
            raise AllowlistError(
                f"build_allowlisted_source: rejected exclusion entry '!{target_rel}' — "
                "resolves to the restricted tree root itself (or outside the "
                "restricted tree), which an exclusion may never target."
            )

        if target.is_dir():
            for sub in sorted(target.rglob("*")):
                if sub.is_file():
                    removed.append(f"{target_rel}/{sub.relative_to(target).as_posix()}")
            shutil.rmtree(target)
            applied_prefixes.append(target_rel)
        elif target.is_file():
            removed.append(target_rel)
            target.unlink()
            applied_prefixes.append(target_rel)
        else:
            removed_by_earlier_exclusion = any(
                target_rel == prefix or target_rel.startswith(prefix + "/")
                for prefix in applied_prefixes
            )
            removed_by_ignore_filter = any(
                p == target_rel or p.startswith(target_rel + "/") for p in pre_filter_set
            )
            if not (removed_by_earlier_exclusion or removed_by_ignore_filter):
                raise AllowlistError(
                    f"build_allowlisted_source: exclusion entry '!{target_rel}' does not "
                    f"match any path admitted by the inclusion list (looked for "
                    f"'{target}' in the restricted tree after every inclusion entry was "
                    "copied in). An exclusion may only narrow a path the inclusion list "
                    "already admitted — fix the entry or drop it."
                )
    return removed


def _collision_preflight(entry_roots: dict[str, Path]) -> None:
    """Pre-copy validation for multi-source builds (Trap A). With a single
    root, allowlist entries are guaranteed distinct paths under one tree, so
    collision cannot happen. With N roots it can: the same entry named twice,
    or a deep entry from one root nesting inside another root's simple entry
    (root A gives `bin`, root B gives `bin/foo.py`). Both land at overlapping
    restricted-tree paths, and — because `shutil.copytree` is called without
    `dirs_exist_ok=True` (see `build_allowlisted_source`) — an unvalidated
    collision would otherwise surface only as a bare `FileExistsError` deep
    inside the copy loop, order-dependent and confusing.

    Iterates entries in sorted order so an abort is reproducible regardless
    of `source_map`'s underlying dict order.

    Raises `AllowlistError` naming both colliding entries and both
    contributing roots.
    """
    sorted_entries = sorted(entry_roots)
    for i, a in enumerate(sorted_entries):
        for b in sorted_entries[i + 1 :]:
            if a == b or b.startswith(a + "/") or a.startswith(b + "/"):
                raise AllowlistError(
                    "build_allowlisted_source: allowlist entry collision across "
                    f"multi-source roots — '{a}' (root: {entry_roots[a]}) and "
                    f"'{b}' (root: {entry_roots[b]}) resolve to overlapping "
                    "restricted-tree paths. Rename or scope one of the entries "
                    "so no entry equals or nests inside another."
                )


def _normalize_dir_pattern(pattern: str) -> Optional[str]:
    """Strip a `.percolate-ignore` pattern down to its directory-form body —
    a leading and/or trailing `/` removed, branches 1/2/4 collapsed to the
    same normalized shape — or `None` for a basename glob (branch 3, leading
    `*`, no fixed path position) or an empty body. Shared normalization for
    `_classify_dir_pattern_against_entries`, the composition filter's sole
    consumer of this shape — kept in one place so it does not reimplement
    `ignore.py`'s branch matching, per this module's negative-spec."""
    if pattern.startswith("*"):
        return None
    if len(pattern) >= 2 and pattern[0] == "/" and pattern[-1] == "/":
        dir_ = pattern[1:-1]
    elif pattern.endswith("/"):
        dir_ = pattern[:-1]
    else:
        dir_ = pattern
    if not dir_:
        return None
    return dir_


def _classify_dir_pattern_against_entries(
    dir_: Optional[str], all_entries: set[str]
) -> tuple[str, object]:
    """Classify a `.percolate-ignore` pattern (already normalized to its
    directory-form body by `_normalize_dir_pattern`, or `None` for a
    basename glob) against the FULL allowlist entry set — the union of
    every contributing root's entries, which may be multi-segment/deep
    (`docs/wiki`, `cockpit-contract/schema`) rather than a single path
    component. Comparing against only `pattern`'s first path segment (the
    prior implementation) misclassifies any pattern nesting under or
    ancestoring a deep entry as root-agnostic noise — silently keeping a
    wholesale-suppression pattern that should have been dropped. See this
    module's negative-spec and `_compose_percolate_ignore`'s docstring.

    Returns one of:
      - `("noise", None)` — `dir_` is `None` (basename glob) or neither
        nests under nor is an ancestor of any entry in `all_entries`.
        Root-agnostic (`*.log`, `__pycache__/`, `*.bak`) — always kept.
      - `("wholesale", entry)` — `dir_ == entry` exactly, for the single
        entry in `all_entries` that `dir_` nests under (longest/most
        specific match — `_collision_preflight` guarantees at most one such
        entry exists on every production path; `max(nesting, key=len)`
        below is a defensive fallback for callers, including this
        function's own unit tests, that invoke it directly without having
        run preflight first). A bare reference to another root's entry
        name; wholesale-suppresses it if not owned by the pattern's own
        root.
      - `("below", entry)` — `dir_.startswith(entry + "/")` for that same
        nesting entry: reaches BELOW it (an exact file or a below-entry
        directory subtree), never suppresses the entry wholesale, so it is
        always kept regardless of which root owns `entry`.
      - `("ancestor", entries)` — `dir_` itself has no nesting entry, but
        is a STRICT ANCESTOR of one or more entries in `all_entries`, per
        `ignore.py` branch 2's full any-depth rule: either a strict
        path-prefix (`entry.startswith(dir_ + "/")`, e.g. pattern `docs/`
        against entry `docs/wiki`) OR `dir_` occurring as an interior/
        trailing path segment of `entry` anywhere (`("/" + dir_ + "/") in
        ("/" + entry + "/")`, e.g. pattern `wiki/` against the SAME entry
        `docs/wiki` — `dir_` names only the entry's LAST segment, not a
        prefix). Both shapes wholesale-suppress every listed entry just as
        surely as the exact-match case above, so each must be checked
        against the pattern's own root individually by the caller.

    Nesting and ancestor relationships are mutually exclusive for a given
    `dir_`: allowlist entries never nest inside one another
    (`_collision_preflight` rejects that at build time), so `dir_` cannot
    simultaneously nest under one entry and ancestor a different one —
    that would require the first entry to itself be an ancestor of the
    second.
    """
    if dir_ is None:
        return ("noise", None)

    # `_normalize_dir_pattern` strips at most one leading/trailing slash, so
    # a degenerate multi-slash pattern like `bin//` would leave a residual
    # `/` in `dir_` here — comparing that residual against `e + "/"` would
    # misclassify it as reaching BELOW entry `bin` (leftover separator
    # junk, not genuine path content) rather than as the wholesale
    # reference to `bin` it actually is. Stripping residual surrounding
    # slashes before every comparison closes that gap (mirrors the prior
    # `_pattern_reaches_below_first_component`'s `dir_.strip("/")` guard).
    dir_ = dir_.strip("/")
    if not dir_:
        return ("noise", None)

    nesting = [e for e in all_entries if dir_ == e or dir_.startswith(e + "/")]
    if nesting:
        longest = max(nesting, key=len)
        if dir_ == longest:
            return ("wholesale", longest)
        return ("below", longest)

    # Per `ignore.py` branch 2, an any-depth directory pattern matches not
    # only a strict path-prefix of `entry` (`e.startswith(dir_ + "/")`) but
    # also `dir_` occurring as an INTERIOR or TRAILING path segment of
    # `entry` anywhere (`("/" + dir_ + "/") in rel_path` in `ignore.py`'s own
    # matcher). The substring form below covers both: for `dir_` a strict
    # prefix, `"/" + e + "/"` contains `"/" + dir_ + "/"` at its start; for
    # `dir_` naming a middle or last segment (e.g. `wiki` against entry
    # `docs/wiki`), the leading/trailing `/` padding turns the plain
    # `in`-membership test into exactly ignore.py's any-depth check. The
    # `nesting` check above runs first, so `dir_ == e` is already claimed as
    # `wholesale` before reaching here — this substring test would also
    # match that case, but it never gets the chance to.
    ancestored = [e for e in all_entries if ("/" + dir_ + "/") in ("/" + e + "/")]
    if ancestored:
        return ("ancestor", ancestored)

    return ("noise", None)


def _compose_percolate_ignore(
    entry_roots: dict[str, Path],
    *,
    stderr: IO[str],
) -> list[str]:
    """Compose a single restricted-root `.percolate-ignore` out of every
    contributing root's own file (multi-source Leg B — kept alongside
    copy-time filtering, not a replacement for it: `sync_mirror`'s
    destination-side skip also needs a file at the restricted root, or every
    ignored destination file becomes an orphan and gets deleted).

    Fail-closed composition rule, per root S with entry set E_S, classified
    by `_classify_dir_pattern_against_entries` against the FULL entry set
    (the union of every contributing root's entries — entries may be
    deep/multi-segment, e.g. `docs/wiki`, `cockpit-contract/schema`, not
    just a single path component):
      - **`"noise"`** — the pattern nests under no entry and is an
        ancestor of no entry (or is a basename glob). Root-agnostic
        (`*.log`, `__pycache__/`, `*.bak`) — always kept, from every root.
      - **`"below"`** — the pattern reaches BELOW some entry (path content
        past it — `bin/depersonalize-identity.yaml`, `bin/private/`).
        Denies a file or a subtree strictly beneath that entry and cannot
        suppress the entry's publish, so it is honoured even against
        another root's entry — a contributing root otherwise has no way to
        deny a single path inside another root's content in path form at
        all. Always kept, regardless of which root owns the entry.
      - **`"wholesale"`** — the pattern IS some entry, exactly (bare
        `entry`, trailing-slash `entry/`, root-anchored `/entry/`, all of
        which normalize to the bare entry name with no path content past
        it). Kept only if that entry is S's own (`entry in e_s`); dropped
        otherwise. This is the actual footgun: a stray `skills/` rule in
        claude-klabauter's file, where claude-klabauter contributes no `skills/` entry, would
        suppress DoE's entire `skills/` publish outright.
      - **`"ancestor"`** — the pattern is a strict ANCESTOR of one or more
        entries (e.g. pattern `docs/` against entry `docs/wiki`, where
        `docs/wiki` is a full allowlist entry name, not decomposable into
        a first-component match). Per `ignore.py` branch 2, an any-depth
        directory pattern suppresses everything beneath it — this
        wholesale-suppresses every listed entry exactly as surely as the
        `"wholesale"` case above, just one level up. Kept only if EVERY
        such entry belongs to S (`e in e_s` for all of them); dropped if
        even one belongs to another root — a pattern that would suppress
        even a single foreign entry is exactly the leak this gate exists
        to prevent, regardless of how many of its own entries it also
        (harmlessly) covers.
      - The asymmetry (below always kept, wholesale/ancestor gated on
        ownership) is deliberate: an ignore rule is fail-closed by nature,
        and a spurious drop only costs missing mirror content (visible at
        review, recoverable), while an inert one costs an irreversible
        leak into an OSS mirror — the same reasoning `ignore.py`'s
        SECURITY-LOAD-BEARING marking rests on.
      - Union across roots, in root-then-file order, de-duplicated,
        iterated in sorted-root order for determinism.

    Every surviving (wholesale) drop still gets its per-pattern stderr line
    as before, plus an end-of-compose summary — a total count and a
    per-root breakdown (root -> number of patterns dropped), not a
    re-emission of every pattern/root pair, so it stays useful (a drop
    stays visible once the per-pattern lines have scrolled off in long
    publish output — AC4 of
    docs/plans/2026-08-05-consumer-ignore-patterns-reach-below-entry.md)
    without doubling stderr volume for no new information. Composition
    itself never aborts on a drop (no fail-closed/abort mode).

    Review: code-reviewer — the summary previously re-printed every
    dropped pattern verbatim, duplicating the per-pattern line above it
    with no cap on the loop; aggregating to counts keeps AC4's
    scroll-survivability intent without the duplication.
    """
    root_entries: dict[Path, set[str]] = {}
    for entry, root in entry_roots.items():
        root_entries.setdefault(root, set()).add(entry)

    all_entries = set(entry_roots.keys())

    composed: list[str] = []
    seen: set[str] = set()
    dropped: list[tuple[str, Path]] = []
    for root in sorted(root_entries, key=str):
        ignore_file = root / ".percolate-ignore"
        e_s = root_entries[root]
        for pattern in load_percolate_ignore(ignore_file):
            dir_ = _normalize_dir_pattern(pattern)
            kind, info = _classify_dir_pattern_against_entries(dir_, all_entries)

            if kind == "noise" or kind == "below":
                keep = True
                reason = None
            elif kind == "wholesale":
                keep = info in e_s
                reason = (
                    f"is a wholesale reference to another root's entry "
                    f"'{info}', not among this root's own entries ({sorted(e_s)})"
                )
            else:  # "ancestor"
                foreign = sorted(e for e in info if e not in e_s)
                keep = not foreign
                reason = (
                    f"is an ancestor of another root's entry/entries "
                    f"{foreign}, wholesale-suppressing them; this root's "
                    f"own entries are {sorted(e_s)}"
                )

            if not keep:
                print(
                    "  percolate-ignore compose: dropping shadowing pattern "
                    f"'{pattern}' from {ignore_file} — {reason}.",
                    file=stderr,
                )
                dropped.append((pattern, root))
                continue
            if pattern not in seen:
                composed.append(pattern)
                seen.add(pattern)

    if dropped:
        per_root_counts: dict[Path, int] = {}
        for _, root in dropped:
            per_root_counts[root] = per_root_counts.get(root, 0) + 1
        print(
            f"  percolate-ignore compose: {len(dropped)} shadowing pattern(s) "
            "dropped total —",
            file=stderr,
        )
        for root in sorted(per_root_counts, key=str):
            print(
                f"    {per_root_counts[root]} from root: {root}",
                file=stderr,
            )

    return composed


def _copytree_ignore_filter(matcher: PercolateIgnoreMatcher, src_root: Path, entry: str):
    """Build a `shutil.copytree(ignore=...)` callable that filters against
    `matcher` (the CONTRIBUTING ROOT's own `.percolate-ignore`), matching on
    the restricted-tree-relative path the copy target will actually have —
    i.e. `<entry>/<path-within-src_root>` — not the real-source-relative
    path. `entry` is always the exact restricted-tree-relative destination
    prefix regardless of whether it is a simple or deep allowlist entry
    (both land at `tmp_src / entry`).

    Directory-shaped patterns (`ignore.py`'s branches 1/2, e.g. `tests/`,
    `fixtures/`) only match a path that has a trailing slash OR content past
    the directory segment (`.../tests/foo`) — `is_ignored`'s `startswith(dir_
    + "/")` / `"/" + dir_ + "/"` checks both require that trailing `/`.
    `shutil.copytree`'s `ignore` callback, however, is asked about a bare
    directory NAME with no trailing slash before it ever recurses into that
    directory (`names` is `os.listdir(dirpath)`, unqualified). Matching only
    the bare `rel_full` therefore never fires for a directory-shaped pattern
    on the directory entry itself — `copytree` proceeds to `mkdir` it and
    recurse, and only the *files inside* get filtered out one level down
    (their own rel path does end in `/<name>`, so they DO match). Net effect
    without this second check: the directory survives as an empty shell in
    the restricted tree instead of being excluded outright, silently
    contradicting `.percolate-ignore`'s directory entries. Also probe
    `rel_full + "/"` — the directory-pattern-matching shape — whenever `name`
    is itself a directory, so `ignore()` returns it (and copytree skips it,
    never recursing) exactly as a directory-shaped pattern intends."""

    def _ignore(dirpath: str, names: list[str]) -> set[str]:
        dirpath_p = Path(dirpath)
        rel_from_root = dirpath_p.relative_to(src_root)
        ignored: set[str] = set()
        for name in names:
            rel_full = (
                f"{entry}/{name}"
                if rel_from_root == Path(".")
                else f"{entry}/{(rel_from_root / name).as_posix()}"
            )
            if matcher.matches(rel_full):
                ignored.add(name)
                continue
            if (dirpath_p / name).is_dir() and matcher.matches(rel_full + "/"):
                ignored.add(name)
        return ignored

    return _ignore


def build_allowlisted_source(
    real_src: Path,
    allowlist_csv: str,
    *,
    source_map: dict[str, Path] | None = None,
    stderr: IO[str] = sys.stderr,
) -> Path:
    """Port of `_build_allowlisted_source`. Creates a new temp directory
    containing only the allowlisted subpaths copied out of `real_src` (or,
    for entries named in `source_map`, out of that entry's contributing
    root — see the module docstring's § Multi-source publish), and returns
    its path.

    Allowlist entries (comma-separated, whitespace-trimmed):
      - Simple name ("bin", "lib", ".claude-plugin"): copy the whole dir
        (or file) to land directly under the temp root — never double-
        nested (a naive `tmp/<entry>/<entry>` would defeat exact-path
        `.percolate-ignore` patterns).
      - Deep path ("docs/wiki"): create the parent dir under the temp
        root, then copy the leaf into it.
      - An entry absent from its resolved root ABORTS the build (raises
        `AllowlistError`). This is a deliberate divergence from the bash
        original (`publish.sh:772`, which skipped silently on the
        rationale that the allowlist only narrows the publish set, never
        widens it) — see plan AC18(c)
        (`docs/plans/2026-07-21-percolate-python-port.md`). Under a
        file-level curated seed list (the `restore-oss-seed-wiki` model),
        narrowing the publish set IS the harm: a typo'd or wrong-rooted
        entry is indistinguishable on disk from a deliberately-absent
        one, and the bash behavior would silently drop a wiki from the
        public mirror with no error. Fail-closed here catches drift at
        the earliest possible point instead of shipping a quietly
        incomplete publish.
      - Leading-`!` exclusion ("!coordinator_core/benchmarks/fixtures/repo"):
        removes that already-admitted subpath from the built restricted
        tree — see module docstring § Exclusion entries. Applied only after
        every plain (inclusion) entry above has been copied in, so an
        exclusion can only narrow what inclusion already admitted, never
        grant new content; a CSV with no `!`-entries is unaffected by this
        branch entirely (the additive guarantee).
      - Leading-`^` deny ("^percolate"): a top-level name declared as never
        published — see module docstring § Whole-entry deny. Recognized and
        discarded by `_split_inclusion_exclusion` before this function ever
        sees an `entries`/`exclusion_targets` list, so a deny target is
        simply never copied — there is no removal step for it, unlike `!`.

    Raises `AllowlistError` if any entry is `/`-absolute or contains `..`
    — both are unconditionally unsafe: an absolute path or a `..`
    traversal could escape its resolved root and pull content the
    allowlist was never meant to admit. Also raises `AllowlistError` if any
    entry resolves to nothing under its root (see above), if a multi-source
    build has a collision between two entries' restricted-tree paths, if
    a multi-source build has a contributing root with no readable
    `.percolate-ignore`, or if any `!`-exclusion entry is malformed or does
    not resolve to a path the inclusion entries actually admitted (see
    `_apply_exclusions`).
    """
    entries, exclusion_targets = _split_inclusion_exclusion(_parse_allowlist_csv(allowlist_csv))
    sm = source_map or {}

    # SINGLE-SOURCE vs MULTI-SOURCE per the module contract: determined by
    # the *shape of source_map itself*, not merely by which roots the
    # current allowlist entries happen to use — a source_map that names a
    # second root always puts the build on the multi-source path, even if
    # (today) every entry still resolves to real_src.
    contributing_roots = {real_src} | set(sm.values())
    multi_source = len(contributing_roots) >= 2

    entry_roots: dict[str, Path] = {entry: sm.get(entry, real_src) for entry in entries}

    _collision_preflight(entry_roots)

    if multi_source:
        used_roots = sorted(set(entry_roots.values()), key=str)
        for root in used_roots:
            ignore_path = root / ".percolate-ignore"
            if not ignore_path.is_file():
                raise AllowlistError(
                    "build_allowlisted_source: multi-source publish requires "
                    f"every contributing root to have a readable "
                    f".percolate-ignore, but '{root}' has none. Author "
                    f"{root}/.percolate-ignore before this root may "
                    "contribute to a multi-source publish."
                )

    tmp_src = Path(tempfile.mkdtemp())

    # Pre-filter relative-path list (multi-source only) — retained so
    # check_working_data_paths can scan what the allowlist ADMITTED before
    # copy-time ignore filtering shrank the tree, rather than losing the
    # ability to distinguish "allowlist is correct" from "allowlist is
    # wrong but the ignore file happened to cover it."
    pre_filter_paths: list[str] = []

    # Cache one ignore matcher per contributing root (multi-source only) —
    # never rebuild per entry.
    matcher_cache: dict[Path, PercolateIgnoreMatcher] = {}

    # Entries this build cannot resolve against their root (§ AC18(c)
    # fail-closed above) — collected across the WHOLE entry set rather than
    # raised at the first miss, so one abort names every stale token instead
    # of one. The prior first-miss-only raise made a commit that deleted N
    # allowlisted paths (e.g. a batch dead-script retirement) surface as N
    # sequential publish failures, each requiring a full re-run to find the
    # next name — see the task brief this fix implements, "Defect 2".
    unresolved_entries: list[str] = []

    for entry in sorted(entry_roots):
        root = entry_roots[entry]

        if entry.startswith("/") or ".." in entry:
            shutil.rmtree(tmp_src, ignore_errors=True)
            raise AllowlistError(
                f"_build_allowlisted_source: rejected unsafe allowlist entry: '{entry}'"
            )

        src_path = root / entry

        if src_path.is_dir():
            for sub in sorted(src_path.rglob("*")):
                if sub.is_file():
                    pre_filter_paths.append(f"{entry}/{sub.relative_to(src_path).as_posix()}")

            ignore_fn = None
            if multi_source:
                if root not in matcher_cache:
                    matcher_cache[root] = PercolateIgnoreMatcher.from_file(
                        root / ".percolate-ignore"
                    )
                ignore_fn = _copytree_ignore_filter(matcher_cache[root], src_path, entry)

            if "/" in entry:
                dst_parent = tmp_src / entry.rsplit("/", 1)[0]
                dst_parent.mkdir(parents=True, exist_ok=True)
                # dirs_exist_ok deliberately NOT passed — see
                # _collision_preflight's docstring. A future maintainer
                # "fixing" a FileExistsError here by adding dirs_exist_ok=True
                # would convert a loud, unvalidated collision into a silent
                # file-by-file shadow. Don't.
                shutil.copytree(src_path, dst_parent / src_path.name, ignore=ignore_fn)
            else:
                shutil.copytree(src_path, tmp_src / entry, ignore=ignore_fn)
        elif src_path.is_file():
            pre_filter_paths.append(entry)
            if "/" in entry:
                dst_parent = tmp_src / entry.rsplit("/", 1)[0]
                dst_parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_path, dst_parent / src_path.name)
            else:
                shutil.copy2(src_path, tmp_src / entry)
        else:
            unresolved_entries.append(f"'{entry}' (resolved: '{src_path}')")

    if unresolved_entries:
        shutil.rmtree(tmp_src, ignore_errors=True)
        raise AllowlistError(
            f"_build_allowlisted_source: {len(unresolved_entries)} allowlist entry(ies) "
            f"not found under their source root(s): {'; '.join(unresolved_entries)}. "
            "Fail-closed per AC18(c) — an absent entry is indistinguishable from a "
            "typo'd or wrong-rooted one and must abort, not silently narrow the "
            "publish set."
        )

    if multi_source:
        composed = _compose_percolate_ignore(entry_roots, stderr=stderr)
        if composed:
            (tmp_src / ".percolate-ignore").write_text(
                "\n".join(composed) + "\n", encoding="utf-8", newline="\n"
            )
    else:
        # Single-source: preserve today's tolerant behaviour exactly.
        # Absence of a .percolate-ignore at real_src is a no-op, not an
        # error — changing this would break every existing publish row.
        percolate_ignore = real_src / ".percolate-ignore"
        if percolate_ignore.is_file():
            shutil.copy2(percolate_ignore, tmp_src / ".percolate-ignore")

    if exclusion_targets:
        # Runs strictly AFTER every inclusion entry has been copied in (see
        # module docstring § Exclusion entries and `_apply_exclusions`'
        # docstring) — this ordering is what makes "exclusions narrow, never
        # grant" structural rather than conventional.
        try:
            removed = set(
                _apply_exclusions(tmp_src, exclusion_targets, entries, pre_filter_paths)
            )
        except AllowlistError:
            shutil.rmtree(tmp_src, ignore_errors=True)
            raise
        if pre_filter_paths:
            # Subtract by PREFIX against the exclusion targets themselves,
            # not only by exact membership in `removed` — a target that
            # copy-time ignore-filtering already dropped before
            # `_apply_exclusions` ran was never added to `removed` (nothing
            # to unlink/rmtree on disk), but every pre_filter_paths entry
            # nested under it is still stale and must not reach
            # check_working_data_paths's gate scan.
            pre_filter_paths = [
                p
                for p in pre_filter_paths
                if p not in removed
                and not any(
                    p == target or p.startswith(target + "/")
                    for target in exclusion_targets
                )
            ]

    if multi_source:
        _pre_filter_paths_by_tmp_src[tmp_src] = pre_filter_paths

    return tmp_src


def check_working_data_paths(
    src_tree: Path,
    *,
    paths: Optional[Iterable[str]] = None,
    stderr: IO[str] = sys.stderr,
) -> bool:
    """Port of `_check_working_data_paths`. Scans either every file under
    `src_tree` (default — legacy single-source behaviour, unchanged), or,
    when `paths` is given, exactly that explicit list of restricted-tree-
    relative paths instead of re-walking `src_tree`.

    `paths` exists for multi-source builds: copy-time ignore filtering
    shrinks the tree this function would otherwise walk, which would let a
    working-data leak get masked by an ignore rule that happens to also
    cover it — indistinguishable from "the allowlist is correct." Feeding
    the caller's own pre-filter path list (what the allowlist ADMITTED,
    before ignore-filtering — retrieve it via `get_pre_filter_paths(tmp_src)`
    once `build_allowlisted_source` returns) closes that gap. Single-source
    callers should not pass `paths` — walking `src_tree` is exactly
    equivalent there (and `get_pre_filter_paths` returns `None` for a
    single-source build) and keeps this call site unchanged.

    Emits an ERROR line to `stderr` per violating file.

    Returns True if the tree is clean (no violations — matches the bash
    "Secondary assertion: [checkmark]" success path). Returns False on any
    violation — this is a HARD STOP for the caller: a primary-allowlist
    gap that lets working-data through is the exact failure mode this
    check exists to catch, so it must halt, not warn-and-continue.
    """
    found_violation = False

    if paths is not None:
        rel_paths: Iterable[str] = sorted(paths)
    else:
        rel_paths = [
            p.relative_to(src_tree).as_posix()
            for p in sorted(src_tree.rglob("*"))
            if p.is_file()
        ]

    for rel in rel_paths:
        matched_deny = False
        for prefix in _DENY_PREFIXES:
            if rel == prefix or rel.startswith(prefix + "/") or f"/{prefix}/" in rel:
                print(
                    f"  ERROR (secondary assertion): working-data path in publish set: {rel}",
                    file=stderr,
                )
                found_violation = True
                matched_deny = True
                break

        if not matched_deny and rel.startswith("docs/") and not rel.startswith("docs/wiki/"):
            print(
                f"  ERROR (secondary assertion): non-wiki docs path in publish set: {rel}",
                file=stderr,
            )
            found_violation = True

    if found_violation:
        print(
            "  SECONDARY ASSERTION FAILED — working-data content found in allowlisted source.",
            file=stderr,
        )
        print(
            "  The primary allowlist build should prevent this; inspect build_allowlisted_source.",
            file=stderr,
        )
        return False

    print("  Secondary assertion: ✓ no working-data paths in publish set.")
    return True


def assert_allowlist_applied(
    *,
    target_name: str,
    allowlist_csv: str,
    restricted_tmp_src: Optional[Path],
    effective_source_dir: Path,
    unrestricted_source_dirs: Iterable[Path],
) -> None:
    """Port of the FATAL post-condition (setup/publish.sh:1670-1678).

    If `allowlist_csv` is non-empty, the target declared an allowlist —
    and by the time this is called, `effective_source_dir` MUST be exactly
    `restricted_tmp_src` (the tree `build_allowlisted_source` produced),
    and it must NOT equal any root in `unrestricted_source_dirs`. Raises
    `AllowlistError` (FATAL, no override) on any deviation — an older
    publish path that silently ignored the allowlist field and synced the
    entire tree is the exact failure this exists to prevent.

    `unrestricted_source_dirs` takes every UNRESTRICTED root the build
    could plausibly have been pointed at instead of the restricted tree —
    both the REAL contributing roots and, post-materialization
    (docs/plans/2026-08-04-publish-from-a-committed-ref.md C1a/C1b), their
    SHADOW (committed-ref) counterparts. A shadow root is just as
    unrestricted as the real root it was materialized from — narrowing
    happens only in `build_allowlisted_source`, never in materialization —
    so a bug that forgot to narrow and set `effective_source_dir` to
    `shadow[source_dir]` must be caught here exactly as if it had been set
    to the real, live `source_dir`. Under multi-source that is more than
    one root of each kind (the primary plus every `source_map` root, real
    and shadow); a single-source caller passes an iterable of exactly the
    roots in play. This is the multi-source Trap B fix: a form of this
    assertion that only knew about real roots cannot catch a
    misconfiguration that pointed `effective_source_dir` at a contributing
    (non-primary) root's raw OR shadow tree, either of which would
    otherwise pass.

    No-op (returns None) when `allowlist_csv` is empty — a target with no
    declared allowlist has nothing to enforce here.
    """
    if not allowlist_csv:
        return

    unrestricted_roots = set(unrestricted_source_dirs)

    reasons = []
    if restricted_tmp_src is None:
        reasons.append("no restricted tree was ever built")
    elif effective_source_dir != restricted_tmp_src:
        reasons.append(
            f"SOURCE_DIR is '{effective_source_dir}', expected the restricted "
            f"tree '{restricted_tmp_src}'"
        )
    if effective_source_dir in unrestricted_roots:
        reasons.append(
            f"SOURCE_DIR '{effective_source_dir}' is itself an unrestricted root "
            "— narrowing never happened, it only looks like a restricted tree"
        )

    if not reasons:
        return

    raise AllowlistError(
        f"FATAL: target '{target_name}' declares an allowlist "
        f"({allowlist_csv.replace(',', ', ')}) but it was NOT applied before "
        f"publish — {'; also: '.join(reasons)}.\n"
        f"Refusing to publish {target_name} to prevent an unrestricted publish "
        "of the full source tree."
    )
