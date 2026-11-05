"""research_layout -- the one docs/research layout contract: docs/research/<topic>/<date>-<run-slug>/.

Single source of truth read by the write guard, the migration tool and the docs: a research run
writes only inside its run dir, whose children are FIXED_CHILDREN; the top level of
docs/research holds topic dirs, the INDEX redirect file and dot-prefixed markers, nothing else. Stdlib only, no I/O
beyond pathlib types; reached by explicit path insertion (coordinator/lib is not a package).
"""
from __future__ import annotations

import re
from pathlib import PurePosixPath

# A topic never opens with a date and never takes a legacy flat-run name; the bare charset regex
# would accept both, which is why they are excluded here and nowhere else.
RESERVED_TOPICS = ("trail", "spike-verdicts", "archive", "evidence")
TOPIC_RE = re.compile(
    r"^(?!\d{4}-\d{2}-\d{2}-)(?!(?:" + "|".join(RESERVED_TOPICS) + r")$)[a-z0-9][a-z0-9-]*$"
)
RUN_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-[a-z0-9][a-z0-9-]*$")

FIXED_CHILDREN = ("synthesis.md", "trail.yaml", "verdict.md", "outputs/", "workdir/")
INDEX = "README.md"
DEFAULT_TOPIC = "misc"
SPIKE_TOPIC = "spikes"

KNOWN_SUFFIXES = ("advisory", "survey", "audit", "review", "report", "notes", "findings", "synthesis")
# Multi-word tails fold whole, tried before KNOWN_SUFFIXES, so `x-coverage-audit` joins topic x
# (run `coverage-audit`) rather than minting topic `x-coverage`.
COMPOUND_SUFFIXES = ("coverage-audit", "coverage-report", "gap-analysis", "gap-report")
# Words that end real topic names as often as they name a follow-up stage
# (`review-trail-foreign-session-gap`): folded only when the base is a known sibling topic.
SIBLING_SUFFIXES = ("coverage", "gap", "analysis")

INDEX_KIND = "index"
MARKER = "marker"
RUN_CHILD = "run-child"
TOPIC_DIR = "topic-dir"
RUN_DIR = "run-dir"
NONCONFORMING = "nonconforming"

_DIR_CHILDREN = frozenset(c.rstrip("/") for c in FIXED_CHILDREN if c.endswith("/"))
_FILE_CHILDREN = frozenset(c for c in FIXED_CHILDREN if not c.endswith("/"))
_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-(.+)$")
_MONTH_RE = re.compile(r"^\d{4}-\d{2}-(?!\d{2}(?:-|$))(.+)$")
_HHMM_RE = re.compile(r"^(\d{2}h\d{2})(?:-(.+))?$")


def run_dir(topic: str, date: str, run_slug: str) -> PurePosixPath:
    """Repo-relative-to-docs/research path of one run: <topic>/<date>-<run-slug>.

    Raises ValueError when topic or the joined run name breaks TOPIC_RE / RUN_RE.
    """
    if not TOPIC_RE.match(topic):
        raise ValueError(f"not a valid research topic: {topic!r}")
    name = f"{date}-{run_slug}"
    if not RUN_RE.match(name):
        raise ValueError(f"not a valid research run name: {name!r}")
    return PurePosixPath(topic) / name


def is_marker(name: str) -> bool:
    """True for a top-level dot-prefixed name (`.fleet-readable`): a marker that stays in place."""
    return len(name) > 1 and name.startswith(".") and name != ".." and "/" not in name and "\\" not in name


def fold_topic(slug: str, known_topics: frozenset[str] = frozenset()) -> tuple[str, str]:
    """Fold one trailing `-<suffix>` (COMPOUND_SUFFIXES, then KNOWN_SUFFIXES) into its base topic;
    a SIBLING_SUFFIXES tail folds only when its base is in known_topics.

    Returns (topic, run_slug_rest): rest is the suffix when folded, else "" with topic == slug.
    Folds only when the remainder is non-empty and is itself a valid TOPIC_RE topic.
    """
    for suffix in COMPOUND_SUFFIXES + KNOWN_SUFFIXES + SIBLING_SUFFIXES:
        tail = "-" + suffix
        if slug.endswith(tail):
            base = slug[: -len(tail)]
            if base and TOPIC_RE.match(base) and (suffix not in SIBLING_SUFFIXES or base in known_topics):
                return base, suffix
    return slug, ""


def conforming_path_for(rel: str, today: str) -> str:
    """Path under docs/research/ that a denied top-level file `rel` should be written to.

    Form `<topic>/<date>-<slug>/synthesis.md`; the date is the name's own prefix, else `today`.
    """
    _, rd = plan_move(rel, date=today)
    return f"{rd}/synthesis.md"


def classify(relpath: str) -> str:
    """Classify a path relative to docs/research/ as index, marker, run-child, topic-dir, run-dir or nonconforming.

    Only the path text is judged; whether the entry exists on disk is the caller's concern.
    """
    parts = _parts(relpath)
    if not parts:
        return NONCONFORMING
    if parts == [INDEX]:
        return INDEX_KIND
    if len(parts) == 1 and is_marker(parts[0]):
        return MARKER
    if not TOPIC_RE.match(parts[0]):
        return NONCONFORMING
    if len(parts) == 1:
        return TOPIC_DIR
    if not RUN_RE.match(parts[1]):
        return NONCONFORMING
    if len(parts) == 2:
        return RUN_DIR
    child = parts[2]
    if len(parts) == 3 and child in _FILE_CHILDREN:
        return RUN_CHILD
    if child in _DIR_CHILDREN:
        return RUN_CHILD
    return NONCONFORMING


def plan_move(
    entry_name: str, topic: str | None = None, date: str | None = None,
    known_topics: frozenset[str] = frozenset(),
) -> tuple[str, PurePosixPath]:
    """Plan the destination run dir for a legacy flat entry; returns (topic, run_dir).

    entry_name is relative to docs/research (`2026-03-18-x.md`, `<run-id>-<slug>-workdir`,
    `trail/<run-id>.yaml`, `spike-verdicts/<date>-<slug>.md`). The date prefix is kept; an
    undated entry takes `date` (the caller reads it from git log) and topic `misc`. Use
    move_child to learn which fixed child of the returned run dir receives the entry.
    known_topics (sibling entries' topics plus existing topic dirs) gates SIBLING_SUFFIXES folds.
    """
    parts = _parts(entry_name)
    if not parts or len(parts) > 2:
        raise ValueError(f"not a flat docs/research entry: {entry_name!r}")
    if len(parts) == 2:
        group, leaf = parts
        if group not in ("trail", "spike-verdicts"):
            raise ValueError(f"not a flat docs/research entry: {entry_name!r}")
    else:
        group, leaf = None, parts[0]
    stem = _strip_ext(leaf) if group or leaf.lower().endswith(".md") else leaf.split(".", 1)[0] or leaf
    if group is None and stem.endswith("-workdir"):
        stem = stem[: -len("-workdir")]

    m = _DATE_RE.match(stem)
    mm = None if m else _MONTH_RE.match(stem)
    if m:
        entry_date, rest = m.group(1), m.group(2)
    else:
        if date is None:
            raise ValueError(f"undated entry {entry_name!r} needs a date")
        entry_date, rest = date, mm.group(1) if mm else stem

    hhmm = ""
    hm = _HHMM_RE.match(rest) if m else None
    if hm:
        hhmm, rest = hm.group(1), hm.group(2) or ""

    slug = _slugify(rest)
    run_part = slug
    if group == "spike-verdicts":
        default_topic = SPIKE_TOPIC
    elif (m or mm) and TOPIC_RE.match(slug):
        default_topic, suffix = fold_topic(slug, known_topics)
        if suffix and topic is None:
            run_part = suffix
    else:
        default_topic = DEFAULT_TOPIC
    chosen = topic if topic is not None else default_topic
    run_slug = "-".join(p for p in (hhmm, run_part) if p) or DEFAULT_TOPIC
    return chosen, run_dir(chosen, entry_date, run_slug)


def move_child(entry_name: str) -> str:
    """The child of its run dir that a flat entry moves to.

    A FIXED_CHILDREN member, except a non-.md file, which keeps its own basename (a sidecar
    `<stem>.claims.json` lands beside its `<stem>.md`'s synthesis.md).
    """
    parts = _parts(entry_name)
    if len(parts) == 2 and parts[0] == "trail":
        return "trail.yaml"
    if len(parts) == 2 and parts[0] == "spike-verdicts":
        return "verdict.md"
    if parts and parts[-1].endswith("-workdir"):
        return "workdir/"
    if parts and "." not in parts[-1]:
        return "outputs/"
    if parts and not parts[-1].lower().endswith(".md"):
        return parts[-1]
    return "synthesis.md"


def _parts(relpath: str) -> list[str]:
    text = relpath.replace("\\", "/")
    parts = [p for p in text.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        return []
    return parts


def _strip_ext(name: str) -> str:
    dot = name.rfind(".")
    return name[:dot] if dot > 0 else name


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
