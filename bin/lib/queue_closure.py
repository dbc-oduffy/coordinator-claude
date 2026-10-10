"""Partition structured queue entries by what their own recorded state already implies.

The queue family (`state/{bug-backlog,debt-backlog,improvement-queue}/`) has ceremony for
FILING an entry -- a skill, a schema, `coordinator-queue-append` -- and no ceremony at all for
retiring one. Closure is a hand-run `git mv` to `archive/<queue>/<YYYY-MM>/`, so an entry whose
defect was fixed stays on the open side until a human remembers it. Nothing measures the gap, so
`status: open` stops being evidence the defect is live and every consumer that reads the queue
reads stale truth as current.

This module is the measuring instrument. It classifies without judging: each class is derived
from what the entry itself records, never from an opinion about whether the underlying defect is
still real. Only ARCHIVABLE is safe to action mechanically -- the entry has already declared
itself terminal and merely never moved. Every other class is a QUESTION for a reader, and is
reported as one.

Negative-spec: this module never decides an open entry is fixed. It cannot read code, run tests,
or resolve a claim against HEAD, and an inference of that kind dressed as a classification is the
exact failure it exists to prevent -- a backlog closed on a guess is worse than one left stale,
because the guess erases the record. SURFACE_VANISHED and DUPLICATE_TITLE are candidate sets
handed to a verifier, never verdicts.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

QUEUES = ("bug-backlog", "debt-backlog", "improvement-queue")

#: Anything outside this set is off-schema on disk.
SCHEMA_STATUSES = frozenset({"open", "closed", "deferred", "wontfix"})

#: Off-schema terminal spellings are included deliberately -- they exist on disk in quantity, and
#: refusing to read them would leave the largest archivable population invisible.
TERMINAL_STATUSES = frozenset({
    "closed", "fixed", "resolved", "done", "obe", "wontfix", "invalid",
    "superseded", "superseded_by_sizing", "withdrawn", "retracted", "transferred",
    "discharged", "duplicate",
})

# Liveness is the COMPLEMENT of terminal, never a membership test against a known-live list.
# On disk the live side spells itself a dozen ways -- in_progress, sized, closeable,
# partially-resolved, open-upstream, proposed-awaiting-pm -- and a gate that required membership
# would silently skip the closure-note and surface checks for every spelling nobody enumerated,
# which is the worst failure available: a candidate class that looks empty because the reader
# could not see into it.

#: Off-schema terminal spellings normalize to the schema value on archival; the original spelling
#: is preserved in the archival note.
STATUS_NORMALIZATION = {
    "fixed": "closed",
    "resolved": "closed",
    "done": "closed",
    "obe": "closed",
    "discharged": "closed",
    "duplicate": "closed",
}

#: A field whose presence means someone wrote down a closure finding. An entry carrying one while
#: still `status: open` is the divergence case: verification happened and the lifecycle never moved.
CLOSURE_NOTE_RE = re.compile(r"^(resolution[_:]|closed_at:|closed_by:|[a-z0-9_]*obe_check:)", re.M)

# A field a drain verifier writes when it settles an entry WITHOUT closing it: still open, or
# diverged, or filed against the wrong tree. It is a receipt, not a closure note -- the entry has
# already had the reader this instrument exists to summon. Without this check the receipt itself
# matches CLOSURE_NOTE_RE's neighbourhood of "somebody wrote a finding here" and re-flags the
# entry on every later run, so each drain pass regenerates its own predecessor's work: a measured
# 19 of one run's 79 closure-note-open entries were the previous run's own output.
VERIFICATION_RECEIPT_RE = re.compile(r"^(?:verified|divergence|misfiled)_(\d{4})_(\d{2})_(\d{2}):", re.M)

#: A top-level key written twice. YAML is last-wins, so the file reads correctly to every consumer
#: while being schema-invalid -- a plain safe_load parse check passes, so nothing else catches it.
_TOP_LEVEL_KEY_RE = re.compile(r"^([a-zA-Z_][\w-]*):", re.M)

ARCHIVABLE = "archivable"
COMMIT_CLAIMED = "commit-claimed"
CLOSURE_NOTE_OPEN = "closure-note-open"
VERIFIED_OPEN = "verified-open"
DUPLICATE_KEY = "duplicate-key"
SURFACE_VANISHED = "surface-vanished"
SURFACE_ELSEWHERE = "surface-in-sibling-repo"
DUPLICATE_TITLE = "duplicate-title"
STATUS_MISSING = "status-missing"
OPEN_UNVERIFIED = "open-unverified"

#: Ordered most- to least-actionable, so a reader meets the class they can act on without
#: judgement before the ones that need a verifier.
CLASSES = (
    ARCHIVABLE,
    COMMIT_CLAIMED,
    CLOSURE_NOTE_OPEN,
    SURFACE_VANISHED,
    SURFACE_ELSEWHERE,
    DUPLICATE_TITLE,
    STATUS_MISSING,
    DUPLICATE_KEY,
    VERIFIED_OPEN,
    OPEN_UNVERIFIED,
)

#: The glossary lives here and nowhere else -- `render_report` emits it, and other surfaces cite
#: the command's output rather than re-tabulating it.
CLASS_DESCRIPTIONS = {
    ARCHIVABLE: (
        "the entry's own `status` is already terminal. Closure was decided; only the move to "
        "`archive/` never happened. Mechanically actionable, no judgement."
    ),
    COMMIT_CLAIMED: (
        "live, and a commit's trailer block names this entry in `Fixes-Row:`. The author claimed "
        "a fix; a reader confirms it against the claiming SHA(s), or annotates a divergence. "
        "Never closed by this instrument."
    ),
    CLOSURE_NOTE_OPEN: (
        "still live, but carries a `resolution_*` / `closed_at` / `*obe_check` field. Someone "
        "verified this and the lifecycle did not move. Read the note: it may record a DIVERGENCE "
        "(the landed fix differs from what the entry asked for), which needs an annotation rather "
        "than a close."
    ),
    SURFACE_VANISHED: (
        "live, and its `surface:` path is absent from the tree. A candidate, never a verdict: the "
        "file may have moved, or the defect may have migrated with it."
    ),
    SURFACE_ELSEWHERE: (
        "live, its surface is absent here and present in another swept repo. Not a fix signal at "
        "all: the entry is filed against the wrong tree, and counting it as vanished would turn a "
        "routing mistake into a closure candidate."
    ),
    DUPLICATE_TITLE: (
        "two or more live entries share a normalized title. One of them is the record; the rest "
        "need merging into it."
    ),
    STATUS_MISSING: "no `status` field at all; schema-invalid and unqueryable.",
    DUPLICATE_KEY: (
        "a top-level key is written twice. YAML is last-wins, so the entry reads correctly and a "
        "parse check passes while the record is schema-invalid. Never archived in this state; "
        "repair the file first."
    ),
    VERIFIED_OPEN: (
        "live, and carrying a dated `verified_`/`divergence_`/`misfiled_` receipt from a drain "
        "pass. A reader already settled it. NOT a candidate: re-flagging it makes every run "
        "re-dispatch a verifier over the last run's finished work."
    ),
    OPEN_UNVERIFIED: (
        "nothing recorded either way. Needs a reader who checks the claim against HEAD. This "
        "instrument cannot and does not guess at these."
    ),
}

_STATUS_RE = re.compile(r"^status:\s*[\"']?([A-Za-z][A-Za-z_-]*)", re.M)
_TITLE_RE = re.compile(r"^title:\s*(.+)$", re.M)
_SURFACE_RE = re.compile(r"^surface:\s*(.+)$", re.M)
_CREATED_RE = re.compile(r"^created:\s*[\"']?(\d{4}-\d{2}-\d{2})", re.M)
# Anchored to the full scalar value: a prefix match would catch `central-something`/
# `centralized` and silently route them into OPEN_UNVERIFIED via the central-scope branch.
_CENTRAL_RE = re.compile(r"^queue_scope:\s*[\"']?central[\"']?\s*$", re.M)
_BLOCK_SCALAR_RE = re.compile(r"^[|>][-+0-9]*$")


def read_title(text: str) -> str:
    """Read `title:`, following a block scalar into its indented body.

    A title written as `title: |-` has its text on the FOLLOWING lines. Reading the scalar
    header literally yields "|-" for every such entry, which then collide with each other under
    any title-equality test -- one measured run grouped fifteen unrelated entries that way. An
    identity key that silently degrades to a constant is worse than no key: it does not fail, it
    reports confident nonsense.
    """
    m = _TITLE_RE.search(text)
    if not m:
        return ""
    raw = m.group(1).strip().strip("\"'").strip()
    if not _BLOCK_SCALAR_RE.match(raw):
        return raw
    lines = text[m.end():].split("\n")[1:]
    body: list = []
    for line in lines:
        if not line.strip():
            if body:
                break
            continue
        if not line.startswith((" ", "\t")):
            break
        body.append(line.strip())
    return " ".join(body).strip()


def _scalar(match: "re.Match[str] | None") -> str:
    if not match:
        return ""
    return match.group(1).strip().strip("\"'").strip()


def looks_like_path(surface: str) -> bool:
    """True when a `surface:` value is concrete enough that its absence means something -- a real
    tree path can be checked against disk, but a prose surface, glob, or bare symbol cannot, and
    treating its non-existence as evidence would manufacture a candidate set out of nothing."""
    if not surface or len(surface) > 200:
        return False
    if any(ch in surface for ch in " ,*?<>|"):
        return False
    if "/" not in surface:
        return False
    if surface.startswith(("http", "~", "$")):
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9_./#:@+-]+", surface))


def normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


@dataclass
class Entry:
    repo: str
    queue: str
    path: str
    status: str
    title: str
    surface: str
    created: str
    klass: str = ""
    reason: str = ""
    normalized_status: str = ""
    duplicates: list = field(default_factory=list)
    claimed_by: list = field(default_factory=list)

    def to_dict(self) -> dict:
        d = {
            "repo": self.repo, "queue": self.queue, "path": self.path,
            "status": self.status, "title": self.title, "surface": self.surface,
            "created": self.created, "class": self.klass, "reason": self.reason,
        }
        if self.normalized_status:
            d["normalized_status"] = self.normalized_status
        if self.duplicates:
            d["duplicates"] = self.duplicates
        if self.claimed_by:
            d["claimed_by"] = self.claimed_by
        return d


def classify_repo(
    repo_root: str, repo_name: str, queues=QUEUES, sibling_roots=(), read_claims=None,
) -> list:
    """`read_claims(since)` returns `{stem: [(sha, yyyy-mm-dd), ...]}` and is called at most once,
    only when a live entry exists; `since` is the oldest live parseable `created`, or None.
    No process is spawned here: a sweep costing a process per entry cannot run over thousands of
    them, and a mechanism too expensive to run on a cadence is the same as no mechanism."""
    raw: list = []
    for queue in queues:
        qdir = os.path.join(repo_root, "state", queue)
        if not os.path.isdir(qdir):
            continue
        for name in sorted(os.listdir(qdir)):
            if not name.endswith(".yaml"):
                continue
            full = os.path.join(qdir, name)
            try:
                with open(full, encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
            except OSError:
                continue
            status = _scalar(_STATUS_RE.search(text)).lower()
            entry = Entry(
                repo=repo_name,
                queue=queue,
                path=f"state/{queue}/{name}",
                status=status,
                title=read_title(text),
                surface=_scalar(_SURFACE_RE.search(text)),
                created=_scalar(_CREATED_RE.search(text)),
            )
            raw.append((entry, text))

    probes = [Entry(**{f: getattr(e, f) for f in (
        "repo", "queue", "path", "status", "title", "surface", "created",
    )}) for e, _ in raw]
    for probe, (_, text) in zip(probes, raw):
        _assign_class(probe, text, repo_root, sibling_roots)
    duplicate_peers = _find_duplicate_title_peers(probes)

    claims: dict = {}
    live = [e for e, _ in raw if e.status not in TERMINAL_STATUSES]
    if read_claims is not None and live:
        created = [e.created for e in live if e.created]
        claims = read_claims(min(created) if created else None) or {}

    entries: list = []
    for entry, text in raw:
        _assign_class(entry, text, repo_root, sibling_roots,
                       duplicate_peers=duplicate_peers.get(entry.path, ()),
                       claims=claims.get(os.path.basename(entry.path)[:-len(".yaml")], ()))
        entries.append(entry)
    return entries


def duplicate_top_level_keys(text: str):
    seen, dupes = {}, []
    for key in _TOP_LEVEL_KEY_RE.findall(text):
        seen[key] = seen.get(key, 0) + 1
        if seen[key] == 2:
            dupes.append(key)
    return dupes


def _assign_class(
    entry: Entry, text: str, repo_root: str, sibling_roots=(), duplicate_peers=(), claims=(),
) -> None:
    """`duplicate_peers` is a peer-derived fact, not a per-entry one -- title collision can only
    be judged once every other entry's own record has been read too, so `classify_repo` computes
    it in a pre-pass and hands it in here. This is the only place `.klass` is set."""
    status = entry.status
    if not status:
        entry.klass = STATUS_MISSING
        entry.reason = "no status field; schema requires one"
        return
    dupes = duplicate_top_level_keys(text)
    if dupes:
        entry.klass = DUPLICATE_KEY
        entry.reason = f"top-level key written twice ({', '.join(dupes)}); YAML last-wins hides it"
        return
    if status in TERMINAL_STATUSES:
        entry.klass = ARCHIVABLE
        entry.normalized_status = STATUS_NORMALIZATION.get(status, status)
        entry.reason = f"status: {status} is terminal; entry never moved to archive/"
        return
    if claims:
        newest = max(d for _, d in claims)
        receipts = ["-".join(m) for m in VERIFICATION_RECEIPT_RE.findall(text)]
        if not receipts or max(receipts) < newest:
            entry.klass = COMMIT_CLAIMED
            entry.claimed_by = [sha for sha, _ in claims]
            newest_sha = max(claims, key=lambda c: c[1])[0]
            entry.reason = (
                f"{len(claims)} commit(s) claim this row in Fixes-Row: (newest {newest_sha[:9]}); "
                f"a reader confirms or annotates a divergence"
            )
            return
    if VERIFICATION_RECEIPT_RE.search(text):
        entry.klass = VERIFIED_OPEN
        entry.reason = "a verifier already settled this and left it open; not a candidate again"
        return
    if CLOSURE_NOTE_RE.search(text):
        entry.klass = CLOSURE_NOTE_OPEN
        entry.reason = "carries a closure note while still live; verify then close or annotate"
        return
    # A central-scope entry's `surface:` is PROVENANCE -- where the observation was captured in
    # the originating repo -- while its proposed_action targets a surface in this one. Reading
    # that citation's absence as a fix signal misclassified 199 entries in one measured run,
    # every one of them correctly filed. Provenance is not a target.
    # Same reasoning, reached by a second route. A surface under state/lessons/ (or its archive)
    # names the capture-queue file the entry was DERIVED from. /learn-lessons age-sweeps that
    # queue on its own cadence, independent of whether the derived improvement ever landed, so
    # its absence is scheduled churn. This instrument's own author ran such a sweep hours before
    # the first fleet run and then read the resulting absences as candidate fixes.
    if re.match(r"^(state|archive)/lessons[/.]", entry.surface):
        _resolve_open_unverified(
            entry, duplicate_peers,
            "surface names a lessons capture file, which is age-swept on its own cadence",
        )
        return
    if _CENTRAL_RE.search(text):
        _resolve_open_unverified(
            entry, duplicate_peers,
            "central-scope entry; its surface cites capture provenance, not a target",
        )
        return
    if looks_like_path(entry.surface):
        target = entry.surface.split("#", 1)[0].split(":", 1)[0]
        if not os.path.exists(os.path.join(repo_root, target)):
            # A surface absent here but present in a sibling is an entry filed against another
            # repo's tree, not a vanished one -- reading it as evidence of a fix would manufacture
            # a candidate out of a routing mistake.
            for sib_name, sib_root in sibling_roots:
                if sib_root == repo_root:
                    continue
                if os.path.exists(os.path.join(sib_root, target)):
                    entry.klass = SURFACE_ELSEWHERE
                    entry.reason = (
                        f"surface {target} is absent here but present in {sib_name}; "
                        f"this entry is filed against another repo's tree"
                    )
                    return
            entry.klass = SURFACE_VANISHED
            entry.reason = f"surface {target} absent from tree; candidate only, verify"
            return
    _resolve_open_unverified(entry, duplicate_peers, "no recorded signal; requires a verifier")


def _resolve_open_unverified(entry: Entry, duplicate_peers, fallback_reason: str) -> None:
    """The one place an entry lands on OPEN_UNVERIFIED or DUPLICATE_TITLE instead.

    Both are "nothing else claimed this entry" outcomes; which of the two depends solely on the
    peer fact `_assign_class` was handed, never on a later pass re-deciding it.
    """
    if duplicate_peers:
        entry.klass = DUPLICATE_TITLE
        entry.duplicates = list(duplicate_peers)
        entry.reason = f"title collides with {len(duplicate_peers)} other open entr(y/ies)"
        return
    entry.klass = OPEN_UNVERIFIED
    entry.reason = fallback_reason


def _find_duplicate_title_peers(probe_entries: list) -> dict:
    """Pre-pass: map each OPEN_UNVERIFIED-bound entry's path to its duplicate-title peers.

    `probe_entries` have already been through `_assign_class` once with no duplicate fact
    available -- the only way to know which entries are open-unverified-shaped is to classify
    them first. This never mutates them; it only reads `.klass`/`.title` to build the fact that
    the real classification pass then hands back into `_assign_class`.
    """
    by_title: dict = {}
    for e in probe_entries:
        if e.klass != OPEN_UNVERIFIED or not e.title:
            continue
        by_title.setdefault((e.queue, normalize_title(e.title)), []).append(e.path)
    peers: dict = {}
    for paths in by_title.values():
        if len(paths) < 2:
            continue
        for p in paths:
            peers[p] = [o for o in paths if o != p]
    return peers
