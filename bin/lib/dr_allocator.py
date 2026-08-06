"""DR-<PREFIX>-NNN decision-record identifier allocation.

Computes the next collision-free `DR-<PREFIX>-NNN` (or unprefixed `DR-NNN`)
identifier for a `docs/decisions/` directory, and asserts a proposed id isn't
already in use. Extracted from `coordinator-doc-new` so it can be vendored
verbatim by sibling repos — claude-klabauter maintains a duplicate Python port
of this algorithm and is the first consumer, publishing here as the single
source of truth so that port can be deleted in favor of a vendored copy of
this file. Vendored, never imported across repos: consumers copy these bytes
into their own tree, because a cross-repo runtime dependency is exactly the
install-time coupling both planes' isolation posture exists to prevent.

Deliberately dependency-free and side-effect-free: no coordinator-specific
imports, no `print`, no `sys.exit`. Failure is signalled by raising
`DrAllocatorError` (or a subclass) with a human-readable message; callers own
turning that into user-facing output (stderr + exit code, a raised HTTP
error, a log line — whatever fits the calling context).

Negative-spec: do not add imports beyond `os`/`re`, and do not reintroduce
`print`/`sys.exit` into this module — purity is the vendoring contract. A
change here that adds a coordinator import or a side effect breaks every
vendored copy silently, since vendored copies are copy-pasted, not
`pip install`'d, and won't pick up a "fix" until someone re-copies the file.
This purity budget is also why frontmatter-carried ids (below) are read via
a bounded `os`/`re` line scan rather than a YAML parser.

SSOT / vendoring: this module is tracked in claude-klabauter only, in two
places — `coordinator/bin/lib/dr_allocator.py` (this file, the live import
target of `coordinator-doc-new`) and its vendored copy at
`coordinator_core/ops/docgen/dr_allocator.py`. The two are kept
byte-identical by `test_dr_allocator_copies_conformance.py`, which is the
drift guard for the pair. Any behavioural change here must be re-vendored
into that copy in the same change (copy the bytes, don't retype the
algorithm) so the conformance test keeps passing; this repo holds both
copies, so no cross-repo memo is needed to close that loop. If a downstream
repo outside claude-klabauter vendors a further copy of its own, that is
currently unverified from here — say so rather than assuming a specific
obligation.

`decisions_dir` accepts `str` or any `os.PathLike` (e.g. `pathlib.Path`) —
vendoring consumers, including claude-klabauter's test suite, call these
functions with `Path` objects.
"""

from __future__ import annotations

import os
import re

DR_ID_RE = re.compile(r"^DR-(?:([A-Z][A-Z0-9]*)-)?(\d+)-")

# Bounded frontmatter scan: frontmatter always leads the file, so a handful
# of lines is enough to find an `id:` field without slurping whole files.
_FRONTMATTER_MAX_LINES = 20
_FRONTMATTER_ID_LINE_RE = re.compile(r"^id:\s*(\S+)\s*$")


class DrAllocatorError(Exception):
    """Base class for allocation failures raised by this module."""


class DrPrefixError(DrAllocatorError):
    """Raised when an explicit `--dr-prefix`-style value is not valid."""


class DrCollisionError(DrAllocatorError):
    """Raised when a proposed DR id already leads a filename on disk, or is
    carried in a date-named record's `id:` frontmatter field."""


def _read_frontmatter_dr_id(path: str) -> tuple[str, int, int] | None:
    """Read `path`'s leading lines and extract an `id: DR-...` frontmatter
    entry as `(prefix, number, digit-width)`, or `None`.

    Bounded read: opens the file and reads at most `_FRONTMATTER_MAX_LINES`
    lines — never the whole file — since frontmatter always leads a record.
    Any failure (missing file, unreadable, bad encoding), absent `id:` line,
    or an `id:` value that doesn't parse as a DR id returns `None` rather
    than raising: a malformed record must not break allocation.

    Spec backlink: cross-repo/inbox/2026-08-01-example-cockpit-repo-em-dr-allocator-frontmatter-id-blindness.md
    """
    try:
        with open(path, encoding="utf-8") as f:
            for _ in range(_FRONTMATTER_MAX_LINES):
                line = f.readline()
                if not line:
                    break
                m = _FRONTMATTER_ID_LINE_RE.match(line.rstrip("\n"))
                if not m:
                    continue
                id_match = DR_ID_RE.match(f"{m.group(1)}-")
                if not id_match:
                    return None
                num_str = id_match.group(2)
                return (id_match.group(1) or "", int(num_str), len(num_str))
    except (OSError, UnicodeDecodeError):
        return None
    return None


def _frontmatter_dr_entries(
    decisions_dir: str | os.PathLike[str],
) -> list[tuple[str, int, int]]:
    """Scan `decisions_dir` for `*.md` files whose FILENAME does not already
    carry a DR id (per `DR_ID_RE`), and fold in any `id:` frontmatter id
    found via `_read_frontmatter_dr_id`, as `(prefix, number, digit-width)`
    tuples.

    Covers repos (e.g. Example-cockpit-repo) where decision records are
    date-named and carry their id in frontmatter instead of leading the
    filename — a filename-only scan is blind to those ids, which let a
    duplicate `DR-008` get proposed there.

    Spec backlink: cross-repo/inbox/2026-08-01-example-cockpit-repo-em-dr-allocator-frontmatter-id-blindness.md
    """
    found: list[tuple[str, int, int]] = []
    for name in os.listdir(decisions_dir):
        if not name.endswith(".md"):
            continue
        if DR_ID_RE.match(name):
            continue
        entry = _read_frontmatter_dr_id(os.path.join(decisions_dir, name))
        if entry is not None:
            found.append(entry)
    return found


def allocate_dr_number(
    decisions_dir: str | os.PathLike[str], explicit_prefix: str | None = None
) -> str:
    """Allocate the next collision-free DR-<PREFIX>-NNN identifier.

    Scans `decisions_dir` for existing `DR-<PREFIX>-NNN-*.md` / `DR-NNN-*.md`
    filenames, resolves a prefix namespace (explicit `--dr-prefix`, else the sole
    prefix shared by every existing record, else the unprefixed namespace when
    records are unprefixed, mixed, or the directory is empty), and returns
    `max(existing NNN in that namespace) + 1`, zero-padded to the widest existing
    width in that namespace (minimum 3 digits).

    This closes the read-modify-write race that produced an 8-way collision on a
    single DR number in a downstream consumer repo (created 2026-06-15, discovered
    2026-07-20 after 5 silent weeks and a leak into shipped C++ strings): the prior scaffolder
    emitted a literal `DR-XXX` placeholder and left numbering to a manual
    docs/decisions/INDEX.md lookup with no compare-and-check against files already
    on disk.

    Also folds in ids carried in `id:` frontmatter for date-named records
    whose filename doesn't itself lead with a DR id, closing a second gap
    where a filename-only scan was blind to those ids and could return an
    already-taken number.

    Spec backlink: cross-repo/inbox/2026-07-20-example-game-repo-em-dr-number-allocator-collision.md
    Spec backlink: cross-repo/inbox/2026-08-01-example-cockpit-repo-em-dr-allocator-frontmatter-id-blindness.md
    """
    # `is not None`, not truthiness: "" is an explicitly-supplied invalid
    # value and must fail loud below, not silently fall through to disk inference.
    if explicit_prefix is not None:
        prefix_norm = explicit_prefix.strip().upper()
        if not re.match(r"^[A-Z][A-Z0-9]*$", prefix_norm):
            raise DrPrefixError(
                f"--dr-prefix '{explicit_prefix}' is not valid. "
                "Use uppercase alphanumeric characters only, starting with a letter."
            )
    else:
        prefix_norm = None

    entries: list[tuple[str, int, int]] = []  # (prefix, number, digit-width)
    if os.path.isdir(decisions_dir):
        for name in os.listdir(decisions_dir):
            if not name.endswith(".md"):
                continue
            m = DR_ID_RE.match(name)
            if not m:
                continue
            file_prefix = m.group(1) or ""
            num_str = m.group(2)
            entries.append((file_prefix, int(num_str), len(num_str)))
        entries.extend(_frontmatter_dr_entries(decisions_dir))

    if prefix_norm is None:
        # Infer namespace from disk: use the sole prefix shared by every existing
        # record. Mixed or absent -> plain (unprefixed) namespace — the safer
        # default, since guessing a prefix nobody has used yet risks starting a
        # second, silently-diverging namespace.
        distinct_prefixes = {e[0] for e in entries}
        prefix_norm = next(iter(distinct_prefixes)) if len(distinct_prefixes) == 1 else ""

    scoped = [(n, w) for (p, n, w) in entries if p == prefix_norm]
    if scoped:
        next_num = max(n for n, _ in scoped) + 1
        width = max(max(w for _, w in scoped), 3)
    else:
        next_num = 1
        width = 3

    num_str = str(next_num).zfill(width)
    return f"DR-{prefix_norm}-{num_str}" if prefix_norm else f"DR-{num_str}"


def assert_dr_id_unique(decisions_dir: str | os.PathLike[str], dr_id: str) -> None:
    """Fail loud if `dr_id` already leads a filename in `decisions_dir`.

    Defense-in-depth per the collision memo's ask #2 ("fail loud on collision"):
    `allocate_dr_number` computes max+1 from a directory scan, but an explicit
    `--dr-prefix` that collides with an existing namespace's numbering, or a
    concurrent `coordinator-doc-new` invocation landing between the scan and this
    write, can still produce a duplicate id. This check is the detection layer the
    prior placeholder-and-hope scheme lacked — that 8-way single-number collision
    sat unnoticed for 5 weeks precisely because nothing checked at write time.

    Numeric, not literal-string: a differently-zero-padded duplicate already on
    disk (e.g. `DR-0002-foo.md` when `dr_id` is `DR-002`) still collides — both
    `dr_id` and each candidate filename are parsed via `DR_ID_RE` (by matching
    against `<candidate>-`, which normalizes both the exact-match `DR-NNN.md`
    and slug-suffixed `DR-NNN-slug.md` filename shapes onto the same pattern
    used for `dr_id` itself) and compared on `(prefix, int(number))`, so
    `DR-002` and `DR-0002` collide regardless of which one is on disk and
    which is freshly allocated. A candidate that doesn't parse as a DR id at
    all is skipped, not treated as a collision.

    Also checks `id:` frontmatter for date-named `*.md` records whose
    filename doesn't itself carry a DR id, on the same numeric-not-literal
    comparison — a frontmatter `id: DR-0008` still collides with a proposed
    `dr_id` of `DR-008`. This is the same widening `allocate_dr_number`
    gets from `_frontmatter_dr_entries`, applied to the collision check so
    the two stay consistent with each other.

    Spec backlink: cross-repo/inbox/2026-07-20-example-game-repo-em-dr-number-allocator-collision.md
    Spec backlink: cross-repo/inbox/2026-08-01-example-cockpit-repo-em-dr-allocator-frontmatter-id-blindness.md
    """
    if not os.path.isdir(decisions_dir):
        return
    target_match = DR_ID_RE.match(f"{dr_id}-")
    target_key = (
        (target_match.group(1) or "", int(target_match.group(2)))
        if target_match
        else None
    )
    collision_prefix = f"{dr_id}-"
    for name in os.listdir(decisions_dir):
        collides = name == f"{dr_id}.md" or name.startswith(collision_prefix)
        if not collides and target_key is not None and name.endswith(".md"):
            stem = name[: -len(".md")]
            m = DR_ID_RE.match(f"{stem}-")
            if m:
                if (m.group(1) or "", int(m.group(2))) == target_key:
                    collides = True
            else:
                entry = _read_frontmatter_dr_id(os.path.join(decisions_dir, name))
                if entry is not None and (entry[0], entry[1]) == target_key:
                    collides = True
        if collides:
            raise DrCollisionError(
                f"DR id '{dr_id}' already in use by "
                f"{os.path.join(decisions_dir, name)!r} — refusing to write a duplicate "
                "decision record. This should not happen from normal allocation; if you "
                "passed an explicit --dr-prefix, check for a race with a concurrent "
                "coordinator-doc-new invocation and retry."
            )
