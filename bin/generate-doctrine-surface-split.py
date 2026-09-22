"""coordinator/bin/generate-doctrine-surface-split.py — the sanctioned
split mechanism for an over-ceiling doctrinal-surface file in DoE-claude
(D4, A15, A16 of `docs/plans/2026-08-13-doctrinal-surface-weight-ratchet.md`).

WHY THIS EXISTS. The weight ratchet's 10:1 tier is unpayable by design for a
file the size of `coordinator-tripwires.md` — no amount of cutting brings it
back into a payable band. The sanctioned exit is structural: convert
`<name>.md` into a `<name>/` directory holding the split bodies plus a
GENERATED `README.md` index. Hand-maintained indexes rot the moment a page
is added — `DIRECTORY_GUIDE.md` is this repo's own standing proof of that
failure mode. This module composes the SAME regenerate-in-memory-and-diff
pattern `coordinator/lib/generate-doctrine-surfaces.py` already runs (its own
docstring: "Re-running this generator is the only way `surfaces` changes");
`build_split(...)` / `render_readme(...)` is that generator's
`build_manifest(...)` / `render(...)` pure pair, so
`coordinator/tests/test_doctrine_surface_split.py::test_no_drift` can diff a
committed split's `README.md` against a fresh in-memory regeneration exactly
as `test_doctrine_surfaces_manifest.py::test_no_drift` already does for the
manifest.

This module DOES NOT decide any specific split's internal section
boundaries — the section-per-heading split below is the only splitting
STRATEGY it ships (top-level `## ` headings, one body file per heading).
Which file gets split, and how its content is actually reorganised, is an
authoring/PM-class call for whoever runs the first real split
(`docs/plans/2026-08-13-doctrinal-surface-weight-ratchet.md` § C12a).

`is_sanctioned_split` is a SEPARATE, pure recognizer — not a re-validation
of this generator's own correctness (`test_no_drift` already owns that). It
answers one question for the ratio guard (C9b, `PreToolUse`+pre-commit leg
1b) and the relocation guard (C4): did commit content match the shape a
sanctioned split produces? It is imported by C4 and C9b ONLY.

Negative-spec: leg 1a (C8/C9a, a bare `PreToolUse` hook) MUST NOT import
`is_sanctioned_split` — a `PreToolUse` hook sees one tool call, has no prior
snapshot, and never observes the deletion of `stem_path.md` at all (a
delete is not a Write/Edit tool call), so the recognizer is inoperative at
that point. Leg 1a's advisory pricing may occasionally over-price a split's
constituent writes; that is harmless because leg 1a never denies.

Usage:
    python coordinator/bin/generate-doctrine-surface-split.py <source.md>            # write
    python coordinator/bin/generate-doctrine-surface-split.py <source.md> --check    # verify, exit 1 on drift

DOE-INTERNAL. `<source.md>` and the split directory it produces live and are
committed inside the DoE-claude checkout, never in this repo — claude-klabauter owns
and runs this CLI, DoE-claude is where its input and output live.

Path resolution: "doctrine asset" class (§ Path resolution,
docs/plans/2026-09-18-doe-holds-no-scripts.md), resolved through the plugin
root exactly as that section names: `coordinator_core.warm.caller_context ::
resolve_caller_context`, falling back to
`coordinator_core.subagent_sandbox.provision_report :: resolve_plugin_root`'s
own three-rung ambient probe — the same pair chunk W2-C9's mise-prep-entry.py
already uses for its own doctrine-asset seam, and this file's own sibling
`generate-doctrine-surfaces.py` (W3-C6) also uses. `_repo_root()` below
replaces the DoE original's own `Path(__file__).resolve().parent.parent.parent`
— the DoE-claude@b644d5a9 lesson this wave exists to fix.
`_no_console_creationflags()`'s `win_portability` import is a real package
import (`coordinator_core.win_portability`) rather than a
`sys.path`-inserted sibling-file load, since that primitive now lives inside
the engine.

Arrived from DoE-claude coordinator/lib/generate-doctrine-surface-split.py
(docs/plans/2026-09-18-doe-holds-no-scripts.md, chunk W3-C6).
Spec backlink: docs/plans/2026-08-13-doctrinal-surface-weight-ratchet.md (D4, C10)
"""
from __future__ import annotations

import difflib
import re
import subprocess  # noqa: F401 -- test_arrival_generate_doctrine_surface_split.py monkeypatches
# generator.subprocess.run to fake git calls (git_native's own subprocess.run call is the same
# stdlib module object, so the patch still reaches it); no direct call site in this module anymore.
import sys
from pathlib import Path, PurePosixPath

#: Populated by `_repo_root()`/`_no_console_creationflags()`, deferred out of module scope so the
#: non-stdlib imports they perform are not a module-body-inertness violation
#: (`coordinator_core.warm.serve_classifier`). Left resolvable as plain module attributes (not a
#: PEP 562 `__getattr__` shim) so `test_arrival_generate_doctrine_surface_split.py`'s
#: `monkeypatch.setattr(generator, "resolve_caller_context", ...)` and its identity assertion on
#: `no_console_creationflags` keep working unchanged.
resolve_caller_context = None  # type: ignore[assignment]
no_console_creationflags = None  # type: ignore[assignment]

#: Every generated README carries this marker as its first line. The
#: recognizer (`is_sanctioned_split`) uses it as the cheap, non-re-validating
#: signal that a given `README.md` is generator output rather than a
#: hand-written index that happens to live at the same path — recognition,
#: not re-verification (`test_no_drift` owns correctness).
GENERATED_MARKER = (
    "<!-- GENERATED by coordinator/lib/generate-doctrine-surface-split.py — "
    "DO NOT EDIT BY HAND. Source of truth is the split body files below. -->"
)

README_BASENAME = "README.md"

#: The hand-maintained preamble's real source file, sibling to `README.md`
#: inside an already-split directory. Written ONCE, at split time, from the
#: source page's frontmatter + pre-first-`##`-heading prose; never
#: regenerated after that (`build_split_from_dir` reads it verbatim and
#: never derives its content). This is the fix for the gap `render_readme`
#: alone could not close: the original monolith is deleted by a fresh
#: split, so once a page is split the preamble has no home but a real file
#: on disk — without one, a hypothetical future `--regenerate` path run
#: against an already-split directory would have nothing but the OLD
#: generated `README.md` to read the preamble back out of, and any
#: hand-edit made to that prose since the split (the exact P1 this file's
#: own review integration fixed) would be silently destroyed on the next
#: regen. Excluded from both the split's body-file set (`build_split` never
#: writes it — it does not exist until authored, by hand, once, right after
#: a fresh split) and the generated index (`_walk_wiki_dir` in
#: `generate-doctrine-surfaces.py` already represents a split directory by
#: its `README.md` alone, so a sibling `_preamble.md` is invisible to that
#: walk without any change there).
PREAMBLE_BASENAME = "_preamble.md"

#: `is_sanctioned_split`'s bound on `README.md`'s own growth, independent of
#: the zero-net-growth body-file check. Review: coordinator:code-reviewer
#: (Finding 1) — subtracting `readme_bytes` out of the growth total
#: unconditionally, with no bound of its own, let a commit pad README.md
#: with unlimited unbilled content while staying inside the vanished-`.md`
#: budget on body files alone; both C4 (relocation guard) and C9b leg 1b
#: (ratio guard) would then treat that commit as a sanctioned no-op. The
#: bound below is DERIVED from real committed body bytes, not arbitrary: to
#: gain README headroom past the fixed skeleton, a commit must also grow
#: real body-file content, which the existing zero-net-growth check already
#: bounds by `vanished_bytes` — so README growth can no longer be free.
#: Measured against the real 146-body-file `coordinator-tripwires/` split on
#: disk (2026-08-14): `README.md` is 24,488 bytes against 563,318 bytes of
#: total body content, a ratio of ~0.0435. `README_OVERHEAD_RATIO` below is
#: set to ~5.7x that observed ratio for headroom against legitimate splits
#: with unusually long headings; `README_SKELETON_ALLOWANCE_BYTES` covers
#: the fixed marker/title/frontmatter/boilerplate `render_readme` always
#: emits regardless of entry count (measured ~397 bytes with zero entries
#: and no frontmatter — 1024 leaves >2.5x headroom for a real frontmatter
#: block on top of that).
README_SKELETON_ALLOWANCE_BYTES = 1024
README_OVERHEAD_RATIO = 0.25

_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def _repo_root() -> Path:
    """The DoE-claude checkout root this generator reads and writes.

    `resolve_caller_context().plugin_root` is a CONTENT root (DoE-claude's
    `coordinator/` subdir) one level below the repo root this generator's
    paths are relative to — same convention this file's sibling
    `generate-doctrine-surfaces.py` documents. Raises loud when unresolvable:
    a caller resolving a relative source/split-dir argument against an
    unknown root has nothing safe to fall back to (`_relpath_str` below is
    the one caller that must NOT propagate this raise — see its own
    docstring)."""
    global resolve_caller_context
    if resolve_caller_context is None:
        from coordinator_core.warm.caller_context import resolve_caller_context as _rcc

        resolve_caller_context = _rcc

    plugin_root = resolve_caller_context().plugin_root
    if plugin_root is None:
        raise RuntimeError(
            "generate-doctrine-surface-split: cannot resolve the DoE-claude "
            "plugin root -- resolve_caller_context().plugin_root returned no "
            "result. Set CLAUDE_PLUGIN_ROOT, or register the coordinator-claude "
            "plugin install / .doe-root pointer (see resolve_plugin_root())."
        )
    return Path(plugin_root).resolve().parent


def _relpath_str(path: Path) -> str:
    """`path` -> its repo-relative POSIX string, for embedding in emitted
    instruction text. Falls back to the absolute string on the (untested,
    should-not-happen) case a caller passes a path outside the repo root, OR
    the repo root itself cannot be resolved — fail-open on display text, not
    a correctness-bearing path."""
    try:
        return path.resolve().relative_to(_repo_root()).as_posix()
    except (ValueError, RuntimeError):
        return str(path)


def slugify(title: str) -> str:
    """Turn a `## ` heading title into a stable, filesystem-safe stem.

    Lowercases, replaces runs of non-alnum characters with a single hyphen,
    and strips leading/trailing hyphens. Two headings that slugify to the
    same stem is an authoring-time collision, not something this pure
    function resolves on its own — see `build_split`'s doctest-shaped note
    below for the disambiguation it applies.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", title.strip().lower())
    return slug.strip("-") or "section"


def split_sections(source_text: str) -> list[tuple[str, str]]:
    """Split markdown text on top-level `## ` headings.

    Returns a list of `(heading_title, section_text)` pairs, one per
    top-level heading found, in source order. `section_text` includes the
    heading line itself and everything up to (not including) the next
    top-level heading. Content BEFORE the first `## ` heading (front matter,
    a title, preamble) is not a section — callers that need it use
    `preamble(source_text)`.
    """
    matches = list(_HEADING_RE.finditer(source_text))
    sections: list[tuple[str, str]] = []
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(source_text)
        title = match.group(1).strip()
        sections.append((title, source_text[start:end]))
    return sections


def preamble(source_text: str) -> str:
    """Everything before the first top-level `## ` heading."""
    matches = list(_HEADING_RE.finditer(source_text))
    if not matches:
        return source_text
    return source_text[: matches[0].start()]


def split_frontmatter_block(text: str) -> "tuple[str, str]":
    """Split a leading `---\\n...\\n---` YAML frontmatter fence off `text`,
    VERBATIM (no YAML parse — this generator only needs to relocate the raw
    block, never inspect its contents). Returns
    `(frontmatter_block_or_empty, remainder)`; `frontmatter_block`, if
    present, includes both fence lines. `(\"\", text)` on any shape mismatch
    (no leading fence, or fewer than two fences) — fail-open, same posture
    as `coordinator/tests/fixtures/doctrine-weight/_surface_primitives.py`'s
    `split_frontmatter`, which this intentionally does NOT import (a
    lib->tests dependency the plan's C3b reviewer amendment forbids) — this
    is the local equivalent-shape parse, verbatim rather than YAML-parsed
    since only relocation, not the parsed value, is needed here.

    CAVEAT (review: coordinator:code-reviewer Finding 6): `text.split("---",
    2)` finds the first two `---` occurrences anywhere in `text`, not just
    fence lines — a frontmatter value that legitimately contains a literal
    `---` substring (a horizontal-rule example, a `note: "see --- above"`
    scalar) truncates `parts[1]` early and corrupts both the emitted
    README and, via `is_sanctioned_split`, marker detection. Not exercised
    by the current corpus (no source page's frontmatter contains an
    embedded `---`); worth tightening to a line-anchored fence match if
    that ever changes.
    """
    if not text.startswith("---"):
        return "", text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return "", text
    frontmatter_block = "---" + parts[1] + "---"
    remainder = parts[2]
    return frontmatter_block, remainder


def build_split(stem: str, source_text: str, split_dir_relpath: str | None = None) -> dict:
    """Pure builder: `stem` + raw source markdown -> an in-memory split.

    Composes `generate-doctrine-surfaces.py`'s `build_manifest(...)` role —
    everything downstream (`render_readme`, `render_files`) derives from
    this dict, never re-reads `source_text`.

    `split_dir_relpath` is the split directory's actual repo-relative path
    (e.g. `"coordinator/docs/wiki/coordinator-tripwires"`) — carried through
    so `render_readme` can emit a followable regen command instead of a
    hardcoded location prefix (review: coordinator:code-reviewer Finding 1).
    """
    sections = split_sections(source_text)

    files: dict[str, str] = {}
    used_slugs: dict[str, int] = {}
    entries: list[tuple[str, str]] = []  # (filename, title), in order

    for title, body in sections:
        base_slug = slugify(title)
        count = used_slugs.get(base_slug, 0)
        used_slugs[base_slug] = count + 1
        slug = base_slug if count == 0 else f"{base_slug}-{count + 1}"
        filename = f"{slug}.md"
        # Disambiguation
        # above only tracks collisions in `base_slug` space, not in the
        # actual `filename` space it produces. A second `## Foo` disambiguates
        # to `foo-2.md`, but a distinct `## Foo 2` heading slugifies to that
        # SAME `foo-2.md` on the first try — the two collide on output
        # filename even though `used_slugs` never saw a repeat of `foo-2`.
        # `files[filename] = ...` would silently overwrite the earlier
        # entry, dropping a whole section with no error. Loud is correct
        # here: an authoring-time slug collision this pure function cannot
        # resolve on its own (see `slugify`'s docstring) must raise, not
        # silently drop content.
        if filename in files:
            raise ValueError(
                f"slug collision producing duplicate filename {filename!r} for heading "
                f"{title!r} — rename one of the colliding headings so they slugify distinctly"
            )
        files[filename] = body if body.endswith("\n") else body + "\n"
        entries.append((filename, title))

    frontmatter_block, preamble_rest = split_frontmatter_block(preamble(source_text))

    return {
        "stem": stem,
        "split_dir_relpath": split_dir_relpath,
        "frontmatter": frontmatter_block,
        "preamble": preamble_rest,
        "entries": entries,
        "files": files,
    }


def render_readme(build: dict) -> str:
    """Pure renderer: an in-memory split -> the generated `README.md` text.

    Composes `generate-doctrine-surfaces.py`'s `render(...)` role. Two
    distinct build shapes feed this, both producing the SAME README
    structure (an optional preamble block, then the boilerplate + index,
    which alone are what `GENERATED_MARKER` claims):

    - A FRESH split (`build_split`, from a still-live `<name>.md`
      monolith): the preamble is composed here from `frontmatter` +
      `preamble` (content before the first `## ` heading in the original
      file). The source page's YAML frontmatter, if present, is relocated
      VERBATIM to byte 0 — the corpus-wide convention every other page
      follows (`split_frontmatter` in
      `coordinator/tests/fixtures/doctrine-weight/_surface_primitives.py`)
      — rather than left inline as body text past `GENERATED_MARKER`, where
      it would render as a stray horizontal rule and be invisible to any
      frontmatter-parsing consumer.
    - A REGENERATION of an already-split directory (`build_split_from_dir`,
      no monolith left to read): `preamble_verbatim` carries the ENTIRE
      hand-maintained preamble read byte-for-byte from `_preamble.md` —
      frontmatter, `GENERATED_MARKER`, title, and any hand-authored meta
      sections alike — emitted here with no re-derivation, which is what
      makes a regeneration idempotent on that prose (`test_no_drift`-shaped
      proof in the test module).
    """
    lines: list[str] = []
    stem_name = build["stem"]
    split_dir_relpath = build["split_dir_relpath"]
    if "preamble_verbatim" in build:
        lines.append(build["preamble_verbatim"].rstrip("\n"))
        lines.append("")
    else:
        frontmatter_block = build.get("frontmatter", "")
        if frontmatter_block:
            lines.append(frontmatter_block)
            lines.append("")
        lines.append(GENERATED_MARKER)
        lines.append("")
        lines.append(f"# {stem_name} — split index")
        lines.append("")
        pre = build["preamble"].strip()
        if pre:
            lines.append(pre)
            lines.append("")
    lines.append("This directory is a sanctioned split of the former")
    lines.append(f"`{stem_name}.md` (D4, `docs/plans/2026-08-13-doctrinal-surface-weight-ratchet.md`).")
    lines.append(
        "Re-run `python3 coordinator/lib/generate-doctrine-surface-split.py "
        f"{split_dir_relpath} --regenerate` to refresh this index; "
        "do not hand-edit it."
    )
    lines.append("")
    for filename, title in build["entries"]:
        lines.append(f"- [{title}]({filename})")
    lines.append("")
    return "\n".join(lines)


_INDEX_LINE_RE = re.compile(r"^-\s+\[(.+?)\]\((\S+?\.md)\)\s*$", re.MULTILINE)
_FIRST_HEADING_RE = re.compile(r"^#{1,2}\s+(.+?)\s*$", re.MULTILINE)


def _index_order_from_readme(readme_text: str) -> list[str]:
    """Recover the existing index's filename order from a prior `README.md`
    (`- [Title](filename.md)` lines), so a regeneration does not reshuffle
    unrelated entries just because directory listing order differs from
    authoring order.

    Scoped to the text
    FOLLOWING `GENERATED_MARKER` only, not the whole README. A
    hand-maintained preamble (relocated frontmatter, `_preamble.md` prose)
    can legitimately contain markdown-link-shaped bullet lines cross-
    referencing a sibling body file; scanning the whole text would mistake
    those for real index entries and silently perturb ordering. A README
    with no marker (or none yet) has no generated index to recover order
    from — no false positives to guard against, correctly."""
    marker_pos = readme_text.find(GENERATED_MARKER)
    if marker_pos == -1:
        return []
    index_text = readme_text[marker_pos + len(GENERATED_MARKER):]
    return [m.group(2) for m in _INDEX_LINE_RE.finditer(index_text)]


def _first_heading_title(body_text: str) -> str:
    """Best-effort title for a body file lacking a prior README entry:
    its own first `#`/`##` heading line, verbatim."""
    match = _FIRST_HEADING_RE.search(body_text)
    return match.group(1).strip() if match else ""


def build_split_from_dir(
    stem: str, split_dir: Path, split_dir_relpath: str | None = None
) -> dict:
    """Pure builder for REGENERATING an already-split directory's
    `README.md` — the counterpart to `build_split` for the case the source
    monolith no longer exists (it was deleted by the original split).

    `split_dir_relpath`, when given, overrides the repo-relative path
    embedded in the rendered regen-command text (default: derived from
    `split_dir`'s own on-disk location via `_relpath_str`). Exists for
    callers that read `split_dir`'s content from a scratch copy elsewhere
    on disk (e.g. a read-only `HEAD`-vs-working-tree drift check) but need
    the emitted text to still name the split's real, canonical location.

    Reads the hand-maintained preamble VERBATIM from `_preamble.md`
    (`PREAMBLE_BASENAME`) — required; raises if absent, since an
    already-split directory with no preamble source has nothing safe to
    regenerate from (§ module docstring: this is the exact gap this
    function exists to close). Entries are every `*.md` body file present
    on disk excluding `README.md` and `_preamble.md` itself, ordered by the
    EXISTING `README.md`'s current index when one is present (so a rerun
    does not reshuffle unrelated entries), with any body file not yet
    listed there appended in filename-sorted order — a new body file is
    additive, never a reason to touch the ordering of files already
    indexed.
    """
    preamble_path = split_dir / PREAMBLE_BASENAME
    if not preamble_path.is_file():
        raise FileNotFoundError(
            f"{preamble_path} not found — an already-split directory must carry a "
            f"{PREAMBLE_BASENAME} source file to regenerate its README.md from; author "
            "it once, verbatim, from the current README.md's hand-maintained preamble "
            "before running a regeneration"
        )
    preamble_text = preamble_path.read_text(encoding="utf-8")

    body_filenames = sorted(
        p.name
        for p in split_dir.glob("*.md")
        if p.name not in (README_BASENAME, PREAMBLE_BASENAME)
    )

    existing_order: list[str] = []
    readme_path = split_dir / README_BASENAME
    if readme_path.is_file():
        existing_order = _index_order_from_readme(readme_path.read_text(encoding="utf-8"))

    # De-duplicate while preserving first-seen order. `existing_order` is recovered from a README
    # that may have been hand-edited, and a bullet added by hand for a body already indexed leaves
    # the same filename twice. Without this the duplicate is not merely re-emitted once — it is
    # read back on the NEXT regeneration and re-emitted again, so one hand-edit makes it permanent
    # and self-reproducing. The row-set gate cannot see it either: both rows resolve to a real
    # body, so nothing is missing and nothing is stale.
    seen: set[str] = set()
    ordered = [
        f for f in existing_order if f in body_filenames and not (f in seen or seen.add(f))
    ]
    ordered += [f for f in body_filenames if f not in seen]

    entries: list[tuple[str, str]] = []
    for filename in ordered:
        body_text = (split_dir / filename).read_text(encoding="utf-8")
        title = _first_heading_title(body_text) or filename[: -len(".md")]
        entries.append((filename, title))

    return {
        "stem": stem,
        "split_dir_relpath": split_dir_relpath
        if split_dir_relpath is not None
        else _relpath_str(split_dir),
        "preamble_verbatim": preamble_text,
        "entries": entries,
    }


def render_files(build: dict) -> dict[str, str]:
    """Pure renderer: an in-memory split -> every file this split writes,
    keyed by filename (repo-relative to the split directory), including the
    generated `README.md`."""
    files = dict(build["files"])
    files[README_BASENAME] = render_readme(build)
    return files


def split_dir_for(source_path: Path) -> Path:
    """`<name>.md` -> `<name>/` — the sanctioned split's directory, sibling
    to the original file."""
    return source_path.parent / source_path.stem


def _no_console_creationflags() -> dict:
    """`coordinator_core.win_portability`'s primitive.

    A real package import now that this module lives inside the engine —
    the DoE original loaded it lazily via a `sys.path` insert of its own
    sibling directory, because `coordinator/lib/` has no `__init__.py` and
    is not an importable package there. No fallback needed here: an
    ImportError on this engine-internal module would mean the engine itself
    is broken, not that a sibling file is merely absent.
    """
    global no_console_creationflags
    if no_console_creationflags is None:
        from coordinator_core.win_portability import no_console_creationflags as _ncc

        no_console_creationflags = _ncc
    return no_console_creationflags()


def dirty_bodies(split_dir: Path) -> list[tuple[str, str]]:
    """Body files in `split_dir` that make a regeneration unsafe, as (case, name) pairs.

    Two cases, both drawn from the hazard `_preamble.md` states in prose and both real
    events in this directory on 2026-08-28: an UNTRACKED body gets a row pointing at
    something no reader can open from HEAD, and an UNSTAGED DELETION of a committed body
    silently drops a live rule's only route into the index. The generator reads the
    WORKING TREE; the gate that checks its output reads HEAD; so either one lands in the
    running operator's commit as index drift under their name.

    MODIFIED bodies are deliberately NOT dirty here. Editing a body changes no row, so
    refusing on one would block the ordinary case while catching nothing.

    STAGED additions are deliberately NOT dirty either, and that is what keeps the
    sanctioned add-a-tripwire flow working: `git add` is the act by which an author claims
    a body as theirs, so staging a new body and then regenerating still lands body and row
    in ONE commit, as the convention requires. An unstaged body is exactly the one nobody
    has claimed yet — which may be a peer's in-flight work.

    Fails OPEN: no git, not a repository, or any git error returns empty. This is an
    ergonomic guard over a shared tree, not a correctness gate, and a consumer outside a
    checkout must still be able to regenerate.

    Routes through
    `coordinator_core.ops.ceremony.git_native._git` instead of a hand-rolled
    `subprocess.run` with its own creationflags handling.
    """
    from coordinator_core.ops.ceremony.git_native import _git as _git_native

    result = _git_native(["status", "--porcelain", "--", str(split_dir)], cwd=split_dir, timeout=15)
    if not result.ok:
        return []
    proc_stdout = result.stdout

    dirty: list[tuple[str, str]] = []
    for line in proc_stdout.splitlines():
        if len(line) < 4:
            continue
        code, path = line[:2], line[3:].strip().strip(chr(34))
        name = PurePosixPath(path).name
        if name in (README_BASENAME, PREAMBLE_BASENAME) or not name.endswith(".md"):
            continue
        if code == "??":
            dirty.append(("untracked", name))
        elif code[1] == "D":
            dirty.append(("deleted, unstaged", name))
    return sorted(dirty, key=lambda item: (item[0], item[1]))


def _refuse_on_dirty_bodies(split_dir: Path, dirty: list[tuple[str, str]]) -> None:
    """Print the named refusal: which tree was read, and what to do in each case."""
    print(
        f"refusing to regenerate {split_dir.name}/{README_BASENAME} — "
        f"{len(dirty)} body file(s) in this directory are uncommitted:",
        file=sys.stderr,
    )
    for case, name in dirty:
        print(f"  {name}  [{case}]", file=sys.stderr)
    print(
        "",
        "The generator reads BODY FILES FROM THE WORKING TREE; the gate that checks its",
        "output reads HEAD. Regenerating now writes rows for files HEAD does not have, or",
        "drops rows for files it still does, as index drift under YOUR name.",
        "",
        "  If these are yours:     `git add` them, then re-run — a staged body is claimed,",
        "                          and body + row still land in one commit.",
        "  If they are not yours:  they belong to a peer session. Do NOT regenerate. Add",
        "                          your own bullet by hand and leave the rest alone.",
        "",
        "  --allow-dirty           proceed anyway; you are asserting the rows for the files",
        "                          above belong in your commit.",
        sep=chr(10),
        file=sys.stderr,
    )

def regenerate_split_dir(
    split_dir: Path,
    *,
    check_mode: bool = False,
    split_dir_relpath: str | None = None,
    allow_dirty: bool = False,
) -> int:
    """Regenerate ONLY `README.md` for an already-split directory —
    `build_split_from_dir` + `render_readme`'s `preamble_verbatim` path —
    never touching body files or `_preamble.md` itself. This is the
    `--regenerate` path named in the module docstring's WHY: unlike a fresh
    split (`build_split`, reading a monolith that this same run deletes),
    there is no monolith left to re-derive the preamble from, so this path
    reads it verbatim from `_preamble.md` and is therefore idempotent on
    that prose by construction (`test_no_drift`-shaped proof in the test
    module) rather than by discipline.

    `split_dir_relpath` forwards to `build_split_from_dir` — see its
    docstring; the default (derived from `split_dir` itself) is what the
    CLI's own `--regenerate` path uses."""
    if not split_dir.is_dir():
        print(f"not a split directory: {split_dir}", file=sys.stderr)
        return 2

    stem = split_dir.name
    # `build_split_from_dir`
    # raises FileNotFoundError when `split_dir` is a real directory that
    # isn't actually a split (no `_preamble.md`). Every other CLI failure
    # mode here prints a clean stderr message and returns 2; let this one
    # propagate as a raw traceback and a caller pointing --regenerate at
    # the wrong path gets a crash instead of the module's usual error
    # contract. Named refusal, not a silent no-op.
    try:
        build = build_split_from_dir(stem, split_dir, split_dir_relpath)
    except FileNotFoundError as exc:
        print(f"not a valid split directory: {exc}", file=sys.stderr)
        return 2
    expected = render_readme(build)
    target = split_dir / README_BASENAME

    if check_mode:
        on_disk = target.read_text(encoding="utf-8") if target.is_file() else ""
        if on_disk != expected:
            diff = "".join(
                difflib.unified_diff(
                    on_disk.splitlines(keepends=True),
                    expected.splitlines(keepends=True),
                    fromfile=str(target),
                    tofile="<regenerated>",
                )
            )
            print(diff, file=sys.stderr)
            return 1
        return 0

    dirty = [] if allow_dirty else dirty_bodies(split_dir)
    if dirty:
        _refuse_on_dirty_bodies(split_dir, dirty)
        return 3

    target.write_text(expected, encoding="utf-8", newline="\n")
    return 0


def main(argv: list[str]) -> int:
    if not argv or argv[0].startswith("--"):
        print(
            "usage: generate-doctrine-surface-split.py <source.md> [--check]\n"
            "       generate-doctrine-surface-split.py <split-dir> --regenerate "
            "[--check] [--allow-dirty]",
            file=sys.stderr,
        )
        return 2

    source_arg = argv[0]
    check_mode = "--check" in argv[1:]
    regenerate_mode = "--regenerate" in argv[1:]
    allow_dirty = "--allow-dirty" in argv[1:]

    source_path = Path(source_arg)
    if not source_path.is_absolute():
        source_path = _repo_root() / source_path

    if regenerate_mode:
        return regenerate_split_dir(
            source_path, check_mode=check_mode, allow_dirty=allow_dirty
        )

    if source_path.is_dir():
        print(
            f"{source_path} is a directory — an already-split page has no monolith left to "
            "split; pass --regenerate to refresh its README.md from _preamble.md instead",
            file=sys.stderr,
        )
        return 2

    if not source_path.is_file():
        print(f"source file does not exist: {source_path}", file=sys.stderr)
        return 2

    stem = source_path.stem
    source_text = source_path.read_text(encoding="utf-8")
    out_dir = split_dir_for(source_path)
    build = build_split(stem, source_text, _relpath_str(out_dir))
    files = render_files(build)

    if check_mode:
        drift_found = False
        for filename, expected in files.items():
            target = out_dir / filename
            on_disk = target.read_text(encoding="utf-8") if target.is_file() else ""
            if on_disk != expected:
                drift_found = True
                diff = "".join(
                    difflib.unified_diff(
                        on_disk.splitlines(keepends=True),
                        expected.splitlines(keepends=True),
                        fromfile=str(target),
                        tofile="<generated>",
                    )
                )
                print(diff, file=sys.stderr)
        return 1 if drift_found else 0

    out_dir.mkdir(parents=True, exist_ok=True)
    for filename, content in files.items():
        (out_dir / filename).write_text(content, encoding="utf-8", newline="\n")
    source_path.unlink()
    return 0


def is_sanctioned_split(
    prior_snapshot: dict[str, bytes],
    current_snapshot: dict[str, bytes],
    stem_path: str,
) -> bool:
    """Recognizer, not re-validator (D4, C10). `test_no_drift` above already
    owns whether this generator's OUTPUT is correct; this function only
    answers whether a given commit's before/after snapshot pair matches the
    SHAPE a sanctioned split produces, for the ratio guard (C9b leg 1b) and
    the relocation guard (C4) to treat as a no-op.

    `prior_snapshot` / `current_snapshot` map repo-relative path -> file
    bytes. `stem_path` is the repo-relative path WITHOUT the `.md`
    extension and without a trailing slash, e.g.
    `"coordinator/docs/wiki/coordinator-tripwires"`.

    Recognizes: `stem_path.md`'s prior entry is absent from `current_snapshot`,
    one or more new files exist under `stem_path/` in `current_snapshot`,
    exactly one of them is `stem_path/README.md` carrying this module's
    `GENERATED_MARKER`, the BODY files (everything under `stem_path/` other
    than `README.md`) are closed to ZERO NET GROWTH (not a tolerance):
    `sum(bytes under stem_path/, excluding README.md) <=
    bytes(vanished stem_path.md entry)` — and `README.md` itself is bounded
    by `README_SKELETON_ALLOWANCE_BYTES + README_OVERHEAD_RATIO *
    (bytes of body files)`, not exempt from the check entirely (see
    `README_SKELETON_ALLOWANCE_BYTES`'s docstring for why that bound is
    derived rather than arbitrary).

    Negative-spec: an ordinary deletion-plus-unrelated-new-files in the same
    commit is NOT recognized — it will fail at least one of the marker
    check, the "exactly one README" check, or (most commonly) simply never
    touch `stem_path/` at all.
    """
    md_path = f"{stem_path}.md"

    if md_path not in prior_snapshot:
        return False
    if md_path in current_snapshot:
        return False

    prefix = f"{stem_path}/"
    new_under_stem = {
        path: content
        for path, content in current_snapshot.items()
        if path.startswith(prefix) and path not in prior_snapshot
    }
    if not new_under_stem:
        return False

    readme_path = f"{stem_path}/{README_BASENAME}"
    readmes = [p for p in new_under_stem if p == readme_path]
    if len(readmes) != 1:
        return False

    readme_content = new_under_stem[readme_path]
    try:
        readme_text = readme_content.decode("utf-8")
    except UnicodeDecodeError:
        return False
    # GENERATED_MARKER leads the README UNLESS the source page carried YAML
    # frontmatter, in which case that frontmatter is relocated verbatim to
    # byte 0 ahead of it (C12a-fix) — strip an optional leading frontmatter
    # fence before checking for the marker, same shape `render_readme` and
    # `split_frontmatter_block` produce.
    _, readme_after_frontmatter = split_frontmatter_block(readme_text)
    if not readme_after_frontmatter.lstrip("\n").startswith(GENERATED_MARKER):
        return False

    vanished_bytes = len(prior_snapshot[md_path])
    readme_bytes = len(readme_content)
    total_body_bytes = sum(
        len(content) for path, content in new_under_stem.items() if path != readme_path
    )

    if total_body_bytes > vanished_bytes:
        return False

    readme_allowance = README_SKELETON_ALLOWANCE_BYTES + README_OVERHEAD_RATIO * total_body_bytes
    return readme_bytes <= readme_allowance


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
