
from __future__ import annotations

import os
import re

DR_ID_RE = re.compile(r"^DR-(?:([A-Z][A-Z0-9]*)-)?(\d+)-")

_FRONTMATTER_MAX_LINES = 20
_FRONTMATTER_ID_LINE_RE = re.compile(r"^id:\s*(\S+)\s*$")


class DrAllocatorError(Exception):
    pass


class DrPrefixError(DrAllocatorError):
    pass


class DrCollisionError(DrAllocatorError):
    pass


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
    if explicit_prefix is not None:
        prefix_norm = explicit_prefix.strip().upper()
        if not re.match(r"^[A-Z][A-Z0-9]*$", prefix_norm):
            raise DrPrefixError(
                f"--dr-prefix '{explicit_prefix}' is not valid. "
                "Use uppercase alphanumeric characters only, starting with a letter."
            )
    else:
        prefix_norm = None

    entries: list[tuple[str, int, int]] = []
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
