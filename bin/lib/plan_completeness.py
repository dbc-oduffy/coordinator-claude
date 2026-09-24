"""coordinator.bin.lib.plan_completeness — reader half of the plan-level completeness ledger.

PURPOSE. Answers "what is complete out of this plan?" straight off disk: which `## Tasks`
spine rows exist and how they are resolved, which dispatched chunks belong to each row, which
run-report sidecar is the current one for a chunk that was dispatched more than once, whether the
plan's `divergence` corpus classifies cleanly, and whether the plan's frontmatter `status` claims
more completion than the computed state supports. See
`docs/plans/2026-09-11-plan-level-completeness-ledger.md` (task C2) — this module is a literal
implementation of that row's body; do not extend its behaviour without updating that spec first.

NEGATIVE SPEC.
  - Pure functions. No file is written by anything in this module — `coordinator/bin/
    plan-completeness.py` (C3) owns the sole write target, the ledger sidecar.
  - Never re-parses the `## Tasks` spine locally. Rows come from the engine's own
    `coordinator_core.ops.plan_tasks_render.load_rows`, imported exactly as `plan-spine-check.py`
    and `mise-prep-gate.py` already do.
  - Never defaults an unknown chunk total to the row count, and never folds a malformed
    `divergence` shape into zero-divergence. UNKNOWN and NON-CONFORMANT are reported values.
  - Never reads `status_detail`. The CONTRADICTION predicate reads frontmatter `status` only.
  - The repo root is always an argument (from the caller, or the caller's own `__file__`) —
    never derived from `cwd` — and every path join goes through `pathlib.Path` plus the engine's
    own `machinery_paths` accessors, never a hand-built literal.

Arrived from DoE-claude coordinator/bin/lib/plan_completeness.py (plan-completeness was never
ported when its sibling reader `plan-spine-check` was; this module mirrors that arrival's
registration). Requirement-restated, not carried verbatim: the DoE-side `ensure_engine_on_path`
resolved `coordinator_core` through a `coordinator/hooks/scripts::_engine_root` seam because that
copy lived outside the engine; this copy lives inside it (`coordinator/bin/lib/`), so it resolves
through `cc_invoke.require_engine_on_path`'s self-locating ladder instead — the same seam
`workday_ceremony_lib.py` (this module's own directory) already uses, never a re-derived one.
"""

from __future__ import annotations

import fnmatch
import os
import re
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import yaml

# ---------------------------------------------------------------------------
# Constants — mirrored 1:1 from the plan's § CONTRADICTION predicate and
# § Divergence conformance, never re-derived at call time.
# ---------------------------------------------------------------------------

#: plan-tasks.schema.json's closed `disposition` enum.
KNOWN_DISPOSITIONS = frozenset({"open", "coded", "spun_off", "backlogged", "wont_do"})

#: Rows counted as resolved (plan's § CONTRADICTION predicate, `rows_resolved`).
RESOLVED_DISPOSITIONS = frozenset({"coded", "spun_off", "backlogged", "wont_do"})

#: `disposition` -> `grouping_approvals` block name for the gated-closure join.
GATED_GROUPING_FOR_DISPOSITION = {
    "spun_off": "spun_off",
    "backlogged": "defer",
    "wont_do": "ruled_out",
}

#: run-report.schema.json `status` values that make a chunk's dispatch terminal.
TERMINAL_SIDECAR_STATUSES = frozenset({"complete", "blocked", "thrashing"})

#: Where an emitted workflow's executor writes its report:
#: `<repo>/<this>/<plan stem>/<chunk id>.md`. Pinned equal to
#: `dispatch_emit.emit._DISPATCH_REPORT_DIR`, not imported: that module costs ~50ms.
DISPATCH_REPORT_DIR = ".coordinator-local/subagent-share/dispatch-reports"

#: An emitted-workflow report carries no frontmatter; its executor return contract
#: writes a `Status: <DONE|BLOCKED|PARTIAL>` line. PARTIAL stopped short: terminal,
#: not complete.
_DISPATCH_REPORT_STATUS = {"DONE": "complete", "BLOCKED": "blocked", "PARTIAL": "blocked"}
#: Tolerates markdown emphasis either side (`**Status: DONE**`) -- executors write both.
_DISPATCH_STATUS_LINE_RE = re.compile(r"^[\s*_]*Status:[\s*_]*([A-Z_]+)\b", re.M)

_DATE_PREFIX_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}-")
_WORK_LABEL_RE = re.compile(r"label:\s*'work:([^'\s]+)'")


# ---------------------------------------------------------------------------
# Engine import seam — "engine" class (§ Path resolution, per plan-spine-check.py's own
# arrival note): this module lives INSIDE the engine checkout, so it resolves through
# `cc_invoke.require_engine_on_path`'s self-locating ladder, the same seam this module's own
# sibling `workday_ceremony_lib.py` already uses at module scope. No `_engine_root` seam.
# ---------------------------------------------------------------------------

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from cc_invoke import require_engine_on_path  # noqa: E402


class EngineUnreachableError(RuntimeError):
    """The engine (`coordinator_core`) could not be resolved or imported."""


def ensure_engine_on_path() -> Path:
    """Resolve this engine's own root onto `sys.path`, idempotently.

    `require_engine_on_path` self-locates (walks up from this file to the checkout root)
    before consulting any environment override, so this always resolves to the engine this
    module ships inside of. Raises `EngineUnreachableError` (never a bare `RuntimeError`) on
    failure, naming the fix.
    """
    try:
        root = require_engine_on_path(__file__)
    except (RuntimeError, OSError) as exc:
        raise EngineUnreachableError(str(exc)) from exc
    return Path(root)


# ---------------------------------------------------------------------------
# Frontmatter
# ---------------------------------------------------------------------------


def read_frontmatter(text: str) -> dict:
    """The document's frontmatter mapping, or `{}` when absent/unparseable.

    Splitting is delegated to the engine's `frontmatter.primitives.split_frontmatter` — never a
    local regex — mirroring `mise-prep-gate.py::_frontmatter`. Tolerant by design: a caller here
    is reading `status`/`plan_id`/`slug`/`grouping_approvals`, not validating authoring shape.
    """
    ensure_engine_on_path()
    from coordinator_core.frontmatter.primitives import split_frontmatter

    split = split_frontmatter(text)
    if split is None:
        return {}
    try:
        loaded = yaml.safe_load(split.fm_text)
    except yaml.YAMLError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


# ---------------------------------------------------------------------------
# (a) Spine rows
# ---------------------------------------------------------------------------


@dataclass
class SpineRow:
    """One `## Tasks` row, classified per the plan's § CONTRADICTION predicate."""

    id: str
    title: str
    raw_disposition: Optional[str]
    disposition: str  # classified: absent -> "open", in-enum -> itself, out-of-enum -> itself
    out_of_enum: bool
    disposition_ref: Optional[str]
    unapproved_closure: bool


@dataclass
class SpineResult:
    """Outcome of loading + classifying a plan's spine rows."""

    status: str  # "located" | "no-spine" | "unreadable"
    rows: list  # list[SpineRow]


def classify_disposition(raw: Any) -> tuple:
    """`(classified, out_of_enum)` per the plan's § CONTRADICTION predicate.

    Absent -> ("open", False) — the schema default. In-enum -> (raw, False). Out-of-enum ->
    (raw, True), counted but never folded to "open" and never counted resolved.
    """
    if raw is None:
        return "open", False
    if not isinstance(raw, str):
        return raw, True
    if raw in KNOWN_DISPOSITIONS:
        return raw, False
    return raw, True


def _row_unapproved_closure(disposition: str, frontmatter: dict) -> bool:
    """Is `disposition` a gated closure whose `grouping_approvals` block does not read `approved`?

    An absent block counts as unapproved (plan's § CONTRADICTION predicate: 15 of 25 gated-closure
    plans in the corpus carry no block at all).
    """
    grouping = GATED_GROUPING_FOR_DISPOSITION.get(disposition)
    if grouping is None:
        return False
    approvals = frontmatter.get("grouping_approvals")
    if not isinstance(approvals, dict):
        return True
    block = approvals.get(grouping)
    if not isinstance(block, dict):
        return True
    return block.get("status") != "approved"


def load_spine(plan_path: Path, text: str, frontmatter: dict) -> SpineResult:
    """(a) Load and classify the plan's `## Tasks` rows via the engine's public `load_rows`.

    Never a local re-parse. `RowsResult.status` ABSENT -> `"no-spine"`; MALFORMED, or a LOCATED
    block that does not parse to a list of mappings -> `"unreadable"` (never zero rows read as
    zero complete).
    """
    ensure_engine_on_path()
    from coordinator_core.frontmatter.body_blocks import LocateStatus
    from coordinator_core.ops.plan_tasks_render import load_rows

    result = load_rows(text)
    if result.status is LocateStatus.ABSENT:
        return SpineResult(status="no-spine", rows=[])
    if result.status is LocateStatus.MALFORMED:
        return SpineResult(status="unreadable", rows=[])

    raw_rows = result.rows
    if not isinstance(raw_rows, list) or not all(isinstance(r, dict) for r in raw_rows):
        return SpineResult(status="unreadable", rows=[])

    rows = []
    for raw in raw_rows:
        row_id = raw.get("id")
        if not isinstance(row_id, str) or not row_id:
            return SpineResult(status="unreadable", rows=[])
        raw_disposition = raw.get("disposition")
        classified, out_of_enum = classify_disposition(raw_disposition)
        rows.append(
            SpineRow(
                id=row_id,
                title=raw.get("title", "") if isinstance(raw.get("title"), str) else "",
                raw_disposition=raw_disposition,
                disposition=classified,
                out_of_enum=out_of_enum,
                disposition_ref=raw.get("disposition_ref")
                if isinstance(raw.get("disposition_ref"), str)
                else None,
                unapproved_closure=_row_unapproved_closure(classified, frontmatter),
            )
        )
    return SpineResult(status="located", rows=rows)


# ---------------------------------------------------------------------------
# (b) work: labels from sibling emitted workflow scripts
# ---------------------------------------------------------------------------


def _plan_stem(plan_path: Path) -> str:
    """The plan's own filename stem, sans `.md` — the delimiter both workflow-script glob
    patterns below anchor on, so a sibling plan whose stem merely extends this one (`foo-bar`
    under `foo`) is never absorbed."""
    name = plan_path.name
    return name[:-3] if name.endswith(".md") else name


def read_work_labels(plan_path: Path) -> Optional[list]:
    """(b) `work:<id>` labels from every sibling `<stem>.workflow.mjs` /
    `<stem>.*.workflow.mjs` script next to `plan_path`, unioned. `None` (UNKNOWN) when no such
    script exists — chunks_total NEVER defaults to the row count on that basis.

    Matched with `fnmatch.fnmatchcase` (never a bare `<stem>*` glob, which has no delimiter and
    would absorb a sibling plan's labels), and the union is de-duplicated but ORDER-preserving.
    """
    stem = _plan_stem(plan_path)
    directory = plan_path.parent
    if not directory.is_dir():
        return None
    patterns = (f"{stem}.workflow.mjs", f"{stem}.*.workflow.mjs")
    scripts = sorted(
        entry
        for entry in os.listdir(directory)
        if any(fnmatch.fnmatchcase(entry, pattern) for pattern in patterns)
    )
    if not scripts:
        return None
    labels: list = []
    seen = set()
    for name in scripts:
        try:
            text = (directory / name).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in _WORK_LABEL_RE.finditer(text):
            token = match.group(1)
            if token and token not in seen:
                seen.add(token)
                labels.append(token)
    return labels


# ---------------------------------------------------------------------------
# (c) chunk-id -> spine-row mapping, longest case-sensitive prefix
# ---------------------------------------------------------------------------


def map_label_to_row(label: str, row_ids: list) -> Optional[str]:
    """The spine row whose id is `label`'s longest CASE-SENSITIVE prefix among `row_ids`.

    Matched against the REAL id set, never guessed by regex — `C1` never swallows `C10`, and
    `C0B` never lands on a `C0b` row. `None` when no row id prefixes `label` (an orphan).
    """
    best: Optional[str] = None
    for row_id in row_ids:
        if label.startswith(row_id) and (best is None or len(row_id) > len(best)):
            best = row_id
    return best


# ---------------------------------------------------------------------------
# (d) candidate-prefix slug set + session-crossing sidecar join
# ---------------------------------------------------------------------------


def derive_stripped_slug(plan_path: Path) -> str:
    """The date-stripped plan slug — byte-parity with the engine's
    `coordinator_core.ops.fold_execution_record._derive_plan_slug` (pinned by the canary test
    below, not re-implemented by import: that symbol is underscore-private; this module lives
    inside the same engine as the symbol it mirrors, so no public accessor is needed)."""
    basename = plan_path.name
    slug = _DATE_PREFIX_RE.sub("", basename)
    if slug.endswith(".md"):
        slug = slug[:-3]
    return slug


def candidate_slugs(plan_path: Path, frontmatter: dict) -> list:
    """(d) The candidate-prefix set, in priority order: `frontmatter` (the plan's own `slug:`,
    when present), `stripped` (the date-stripped basename), `dated` (the full dated stem).

    Each entry is `(slug_form, slug)`. `frontmatter` is emitted only when the plan declares one.
    """
    candidates = []
    fm_slug = frontmatter.get("slug")
    if isinstance(fm_slug, str) and fm_slug:
        candidates.append(("frontmatter", fm_slug))
    candidates.append(("stripped", derive_stripped_slug(plan_path)))
    candidates.append(("dated", _plan_stem(plan_path)))
    return candidates


def read_sidecar_frontmatter(path: Path) -> dict:
    """A run-report sidecar's frontmatter mapping, or `{}` when unreadable/unparseable."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    return read_frontmatter(text)


@dataclass
class ChunkCandidate:
    """One sidecar file that matched a chunk id under some candidate slug + session root."""

    path: Path
    slug_form: str
    spawned_at: Optional[str]
    status: Optional[str]
    divergence: Any


@dataclass
class ChunkResolution:
    """The result of resolving one chunk id against the sidecar corpus (C1 schema § chunks[])."""

    provision_key: str
    slug_form: Optional[str]
    resolution: str  # "unique" | "ambiguous" | "absent"
    sidecar_path: Optional[str]
    spawned_at: Optional[str]
    status: Optional[str]
    divergence_class: str  # "object" | "non-conformant" | "absent"
    diverged: Optional[bool]


@lru_cache(maxsize=None)
def _listdir_cached(session_dir: str) -> frozenset:
    """`os.listdir(session_dir)`, memoized for this process's lifetime, as a set index.

    `resolve_chunk` is called once per label (up to dozens per plan) and re-lists the SAME
    session directories under every candidate slug -- on a live, long-running share-root tree
    this was measured at 90k+ `os.listdir` calls for one 25-label plan (repeat-scanning ~1,200
    session directories ~75x each), pushing one `status` invocation past a full second of process
    time. A directory's entry set cannot change mid-invocation in a way this tool's own output
    depends on (it does not watch for concurrent writes), so caching it for the process's
    lifetime changes nothing about WHICH sidecars are found -- only how many times the same
    listing is read off disk. Never invalidated: this module's own process exits after one CLI
    call (`generate`/`status`), so there is no second call in the same process to go stale for.

    A `frozenset`, not a tuple: `_match_exact_or_glob` below needs O(1) membership, and no
    caller of this function reads entry ORDER -- a directory's per-session filenames are unique,
    so a literal (non-glob) pattern matches at most one entry regardless of container order, and
    `discover_untotaled_chunks` already folds its own results through an unordered `set`.
    """
    try:
        return frozenset(os.listdir(session_dir))
    except OSError:
        return frozenset()


#: fnmatch's own special characters (`fnmatch.translate`'s grammar) -- a pattern containing
#: none of these matches by plain string equality, exactly as `fnmatch.fnmatchcase` would.
_FNMATCH_SPECIAL_RE = re.compile(r"[*?\[]")


def _match_exact_or_glob(entries: frozenset, pattern: str) -> tuple:
    """Every `entries` member `fnmatch.fnmatchcase(entry, pattern)` would admit, byte-identical
    to a linear fnmatch scan for EVERY possible pattern -- but O(1) for the pattern shape this
    module's own callers always construct (`"{slug}.{chunk_id}.md"`, a literal string with no
    glob metacharacters), instead of an O(len(entries)) scan repeated per label per candidate
    slug. Never assumes the literal shape: a pattern that DOES carry a special character (a
    slug or work-label token this module does not control the grammar of) falls back to the
    original full scan, so behaviour never depends on an input this module cannot vouch for.
    """
    if _FNMATCH_SPECIAL_RE.search(pattern) is None:
        return (pattern,) if pattern in entries else ()
    return tuple(entry for entry in entries if fnmatch.fnmatchcase(entry, pattern))


def _iter_session_roots(repo_root: str) -> list:
    """Every existing session directory under every root `machinery_paths.share_roots` returns,
    current root first."""
    ensure_engine_on_path()
    from coordinator_core.session.machinery_paths import share_roots

    session_dirs = []
    for root in share_roots(repo_root):
        if os.path.isdir(root):
            for name in sorted(os.listdir(root)):
                candidate = os.path.join(root, name)
                if os.path.isdir(candidate):
                    session_dirs.append(candidate)
    return session_dirs


def classify_divergence(value: Any) -> tuple:
    """Per the plan's § Divergence conformance: `(divergence_class, diverged)`.

    An object carrying `diverged` -> `("object", bool(diverged))`. Any other present shape
    (array, scalar, object missing `diverged`) -> `("non-conformant", None)`, never zero-
    divergence. Absent -> `("absent", None)` — not a defect on a non-terminal sidecar.
    """
    if value is None:
        return "absent", None
    if isinstance(value, dict) and "diverged" in value and isinstance(value["diverged"], bool):
        return "object", value["diverged"]
    return "non-conformant", None


def _dispatch_report_candidate(
    chunk_id: str, plan_path: Path, repo_root: str
) -> Optional[ChunkCandidate]:
    """The emitted workflow's own report for `chunk_id`, or `None` when absent.

    Frontmatter `status` wins when present; otherwise the executor contract's
    `Status:` line, mapped onto the run-report enum. An unmapped token, or a
    body carrying more than one `Status:` line, leaves `status` None, so the
    chunk resolves but never counts as reported."""
    path = Path(repo_root) / DISPATCH_REPORT_DIR / Path(plan_path).stem / f"{chunk_id}.md"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    fm = read_frontmatter(text)
    status = fm.get("status") if isinstance(fm.get("status"), str) else None
    if status is None:
        matches = _DISPATCH_STATUS_LINE_RE.findall(text)
        status = _DISPATCH_REPORT_STATUS.get(matches[0]) if len(matches) == 1 else None
    return ChunkCandidate(
        path=path,
        slug_form="dispatch-report",
        spawned_at=fm.get("spawned_at") if isinstance(fm.get("spawned_at"), str) else None,
        status=status,
        divergence=fm.get("divergence"),
    )


def resolve_chunk(
    chunk_id: str,
    plan_path: Path,
    frontmatter: dict,
    repo_root: str,
    session_roots: Optional[list] = None,
) -> ChunkResolution:
    """(d) Resolve one chunk id against the sidecar corpus.

    Globs `<root>/<session>/<candidate>.<chunk_id>.md` for every candidate slug under every
    existing session directory of every share root, `fnmatch.fnmatchcase` throughout. All matches
    across every candidate and every session form ONE pool. On more than one match, the newest
    `spawned_at` wins and its form is recorded; the result is `ambiguous` when any candidate in
    the pool lacks `spawned_at`, or the newest value ties.
    """
    if session_roots is None:
        session_roots = _iter_session_roots(repo_root)

    provision_key_template = "{slug}.%s.md" % chunk_id
    pool = []  # list[ChunkCandidate]
    for slug_form, slug in candidate_slugs(plan_path, frontmatter):
        pattern = provision_key_template.format(slug=slug)
        for session_dir in session_roots:
            for entry in _match_exact_or_glob(_listdir_cached(session_dir), pattern):
                sidecar_path = Path(session_dir) / entry
                fm = read_sidecar_frontmatter(sidecar_path)
                pool.append(
                    ChunkCandidate(
                        path=sidecar_path,
                        slug_form=slug_form,
                        spawned_at=fm.get("spawned_at")
                        if isinstance(fm.get("spawned_at"), str)
                        else None,
                        status=fm.get("status") if isinstance(fm.get("status"), str) else None,
                        divergence=fm.get("divergence"),
                    )
                )

    # The workflow report carries no `spawned_at`, so pooling it beside a
    # sidecar would force every such chunk to `ambiguous`; it is consulted
    # only when no Agent-tool sidecar exists.
    if not pool:
        report = _dispatch_report_candidate(chunk_id, plan_path, repo_root)
        if report is not None:
            pool.append(report)

    if not pool:
        return ChunkResolution(
            provision_key=f"<slug>.{chunk_id}.md",
            slug_form=None,
            resolution="absent",
            sidecar_path=None,
            spawned_at=None,
            status=None,
            divergence_class="absent",
            diverged=None,
        )

    if len(pool) == 1:
        winner = pool[0]
        resolution = "unique"
    else:
        timestamps = [c.spawned_at for c in pool]
        if any(t is None for t in timestamps):
            resolution = "ambiguous"
            winner = max(pool, key=lambda c: c.spawned_at or "")
        else:
            newest = max(timestamps)
            tied = [c for c in pool if c.spawned_at == newest]
            if len(tied) > 1:
                resolution = "ambiguous"
                winner = tied[0]
            else:
                resolution = "unique"
                winner = tied[0]

    divergence_class, diverged = classify_divergence(winner.divergence)
    return ChunkResolution(
        provision_key=f"{winner.path.stem}",
        slug_form=winner.slug_form,
        resolution=resolution,
        sidecar_path=str(winner.path),
        spawned_at=winner.spawned_at,
        status=winner.status,
        divergence_class=divergence_class,
        diverged=diverged,
    )


def discover_untotaled_chunks(
    plan_path: Path, frontmatter: dict, row_ids: list, repo_root: str
) -> list:
    """With NO emitted workflow (chunks_total UNKNOWN): sidecars discovered under
    `<candidate>.*.md` whose chunk-id segment prefix-matches a spine id still count toward
    `chunks_reported`, while `chunks_total` stays `None`. Returns the distinct chunk ids found,
    each mapping to a real spine row.
    """
    session_roots = _iter_session_roots(repo_root)
    found = set()
    for slug_form, slug in candidate_slugs(plan_path, frontmatter):
        prefix = f"{slug}."
        for session_dir in session_roots:
            for entry in _listdir_cached(session_dir):
                if not entry.startswith(prefix) or not entry.endswith(".md"):
                    continue
                chunk_segment = entry[len(prefix) : -len(".md")]
                if not chunk_segment:
                    continue
                if map_label_to_row(chunk_segment, row_ids) is not None:
                    found.add(chunk_segment)
    return sorted(found)


# ---------------------------------------------------------------------------
# (e)/(f) rollup + CONTRADICTION predicate
# ---------------------------------------------------------------------------


@dataclass
class Rollup:
    rows_total: int
    rows_resolved: int
    rows_coded: int
    out_of_enum_disposition_count: int
    unapproved_closure_count: int
    chunks_total: Optional[int]
    chunks_reported: int
    diverged_count: int
    non_conformant_divergence_count: int
    ambiguous_chunk_count: int
    orphan_labels: list
    contradiction: Optional[dict]


def compute_contradiction(status_claim: str, rollup_partial: dict) -> Optional[dict]:
    """(f) The plan's § CONTRADICTION predicate table, reading `status` only.

    `rollup_partial` carries `rows_total`, `rows_resolved`, `rows_coded`, `chunks_total`,
    `chunks_reported` — the only terms the table reads. Returns `None` when the predicate does
    not fire, else `{claim, reason}`.
    """
    if status_claim == "landed":
        chunks_total = rollup_partial["chunks_total"]
        if chunks_total is not None and rollup_partial["chunks_reported"] < chunks_total:
            return {"claim": "landed", "reason": "chunks_reported < chunks_total"}
        return None
    if status_claim == "implemented":
        if rollup_partial["rows_resolved"] < rollup_partial["rows_total"]:
            return {"claim": "implemented", "reason": "rows_resolved < rows_total"}
        if rollup_partial["rows_coded"] == 0:
            return {"claim": "implemented", "reason": "rows_coded == 0"}
        return None
    # draft/reviewed/approved/executing (no delivery claim) and
    # deferred/abandoned/superseded (stopped, no delivery claim): never fires.
    # An out-of-enum status is treated the same as the never-fires groups —
    # this predicate reads `status`, it does not validate it (plan.schema.json's own enum is
    # the authoring-time check for that).
    return None


# ---------------------------------------------------------------------------
# Top-level: build the full ledger document (C1 schema shape)
# ---------------------------------------------------------------------------


@dataclass
class LedgerResult:
    """Either a ledger document (`status == "located"`) or a terminal non-document status
    (`"no-spine"` | `"unreadable"`)."""

    status: str
    document: Optional[dict] = None


def build_ledger(repo_root: str, plan_path: str) -> LedgerResult:
    """The whole reader, end to end: load the spine, read the plan frontmatter, read the
    emitted-workflow chunk-id set (or discover chunks without one), resolve each chunk against
    the sidecar corpus, and compute the rollup plus the CONTRADICTION predicate.

    `repo_root` and `plan_path` are both required arguments — never derived from `cwd`.
    """
    repo_root_path = Path(repo_root)
    plan_path_obj = Path(plan_path)
    if not plan_path_obj.is_absolute():
        plan_path_obj = (repo_root_path / plan_path_obj).resolve()

    try:
        text = plan_path_obj.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return LedgerResult(status="unreadable")

    frontmatter = read_frontmatter(text)
    spine = load_spine(plan_path_obj, text, frontmatter)
    if spine.status != "located":
        return LedgerResult(status=spine.status)

    row_ids = [row.id for row in spine.rows]
    labels = read_work_labels(plan_path_obj)

    row_chunks: dict = {row.id: [] for row in spine.rows}
    orphan_labels: list = []

    if labels is not None:
        chunks_total: Optional[int] = len(labels)
        session_roots = _iter_session_roots(str(repo_root_path))
        for label in labels:
            owner = map_label_to_row(label, row_ids)
            if owner is None:
                orphan_labels.append(label)
                continue
            resolution = resolve_chunk(
                label, plan_path_obj, frontmatter, str(repo_root_path), session_roots
            )
            row_chunks[owner].append(resolution)
    else:
        chunks_total = None
        for chunk_id in discover_untotaled_chunks(
            plan_path_obj, frontmatter, row_ids, str(repo_root_path)
        ):
            owner = map_label_to_row(chunk_id, row_ids)
            if owner is None:
                continue  # discover_untotaled_chunks already filters to mapped ids
            resolution = resolve_chunk(chunk_id, plan_path_obj, frontmatter, str(repo_root_path))
            row_chunks[owner].append(resolution)

    rows_total = len(spine.rows)
    rows_resolved = sum(1 for r in spine.rows if r.disposition in RESOLVED_DISPOSITIONS)
    rows_coded = sum(1 for r in spine.rows if r.disposition == "coded")
    out_of_enum_disposition_count = sum(1 for r in spine.rows if r.out_of_enum)
    unapproved_closure_count = sum(1 for r in spine.rows if r.unapproved_closure)

    all_chunks = [c for chunks in row_chunks.values() for c in chunks]
    chunks_reported = sum(
        1 for c in all_chunks if c.status in TERMINAL_SIDECAR_STATUSES
    )
    diverged_count = sum(
        1 for c in all_chunks if c.divergence_class == "object" and c.diverged
    )
    non_conformant_divergence_count = sum(
        1 for c in all_chunks if c.divergence_class == "non-conformant"
    )
    ambiguous_chunk_count = sum(1 for c in all_chunks if c.resolution == "ambiguous")

    rollup_partial = {
        "rows_total": rows_total,
        "rows_resolved": rows_resolved,
        "rows_coded": rows_coded,
        "chunks_total": chunks_total,
        "chunks_reported": chunks_reported,
    }
    status_claim = frontmatter.get("status", "") if isinstance(frontmatter.get("status"), str) else ""
    contradiction = compute_contradiction(status_claim, rollup_partial)

    rollup = Rollup(
        rows_total=rows_total,
        rows_resolved=rows_resolved,
        rows_coded=rows_coded,
        out_of_enum_disposition_count=out_of_enum_disposition_count,
        unapproved_closure_count=unapproved_closure_count,
        chunks_total=chunks_total,
        chunks_reported=chunks_reported,
        diverged_count=diverged_count,
        non_conformant_divergence_count=non_conformant_divergence_count,
        ambiguous_chunk_count=ambiguous_chunk_count,
        orphan_labels=orphan_labels,
        contradiction=contradiction,
    )

    document = {
        "plan": str(plan_path_obj),
        "plan_id": frontmatter.get("plan_id", "") if isinstance(frontmatter.get("plan_id"), str) else "",
        "status_claim": status_claim,
        "generated_at": None,  # the CLI (C3) stamps this at write time
        "rows": [
            {
                "id": row.id,
                "title": row.title,
                "disposition": row.disposition,
                **({"disposition_ref": row.disposition_ref} if row.disposition_ref else {}),
                "chunks": [
                    {
                        "provision_key": c.provision_key,
                        "slug_form": c.slug_form,
                        "resolution": c.resolution,
                        **({"sidecar_path": c.sidecar_path} if c.sidecar_path else {}),
                        **({"spawned_at": c.spawned_at} if c.spawned_at else {}),
                        **({"status": c.status} if c.status else {}),
                        "divergence_class": c.divergence_class,
                        **({"diverged": c.diverged} if c.diverged is not None else {}),
                    }
                    for c in row_chunks[row.id]
                ],
            }
            for row in spine.rows
        ],
        "rollup": {
            "rows_total": rollup.rows_total,
            "rows_resolved": rollup.rows_resolved,
            "rows_coded": rollup.rows_coded,
            "out_of_enum_disposition_count": rollup.out_of_enum_disposition_count,
            "unapproved_closure_count": rollup.unapproved_closure_count,
            "chunks_total": rollup.chunks_total,
            "chunks_reported": rollup.chunks_reported,
            "diverged_count": rollup.diverged_count,
            "non_conformant_divergence_count": rollup.non_conformant_divergence_count,
            "ambiguous_chunk_count": rollup.ambiguous_chunk_count,
            "orphan_labels": rollup.orphan_labels,
            "contradiction": rollup.contradiction,
        },
    }
    return LedgerResult(status="located", document=document)
