#!/usr/bin/env bash
# render-project-tracker.sh — generate docs/project-tracker.md from the
# per-entry workstream store (definitions + field-scoped events).
#
# Purpose: the SOLE writer of docs/project-tracker.md. Reads all
# state/workstreams/<id>.yaml definitions plus all
# state/workstreams/events/<date>-<id>-<session>.yaml field-scoped events,
# folds each (workstream, field) pair to its current value by
# (sequence, session-id lexical) — NEVER wall-clock — filters to the
# current repo via the coordinator_root_path discriminator, and renders
# the result in the format contract defined by
# coordinator/pipelines/update-docs/tracker-maintenance.md
# § Project Tracker Format Reference, with schema-conformant
# title/created/status frontmatter per coordinator/schemas/tracker.schema.json.
#
# Idempotent: two consecutive renders of an unchanged store are byte-identical
# (render order = (created, workstream-id); fold order = (sequence, session-id)
# — both deterministic total orders, per plan § Approach findings 1/3).
#
# Spec backlink: docs/plans/2026-07-08-project-tracker-render-from-queue.md
# § Approach (fold rule, fold granularity, render order) / § Substrate /
# § Chunks C3.
#
# Negative-spec: do NOT fold or sort by file mtime/wall-clock anywhere in
# this script or its embedded Python — that reintroduces the exact
# non-monotonic-clock hazard (clock skew, NTP correction, DST) the fold
# rule exists to rule out. Do NOT emit a `status` value outside
# {active, archived} — example-orchestration-hub-repo's cockpit emitter quarantines any
# other value fleet-wide (frozen-enum negative-spec, plan § C3).

# No bash>=4 features used here (all fold/render logic lives in the embedded
# Python below) — runs unmodified on stock macOS /bin/bash 3.2.

set -uo pipefail

# ---------------------------------------------------------------------------
# Resolve the store root and the docs output root.
#
# Precedence (mirrors coordinator-queue-append._output_path):
#   1. QUEUE_APPEND_OUTPUT_ROOT env override wins (test isolation) — both the
#      state/workstreams store AND docs/project-tracker.md are read/written
#      relative to this root.
#   2. Else the current git repo root (git rev-parse --show-toplevel).
#   3. Else the cwd (last-resort; not in a git repo).
# ---------------------------------------------------------------------------
_override_root="${QUEUE_APPEND_OUTPUT_ROOT:-}"
if [[ -n "${_override_root}" ]]; then
  if [[ "${_override_root}" != /* ]]; then
    printf 'render-project-tracker.sh: QUEUE_APPEND_OUTPUT_ROOT must be an absolute path, got %s\n' \
      "${_override_root}" >&2
    exit 1
  fi
  _root="${_override_root}"
else
  _git_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
  if [[ -n "${_git_root}" ]]; then
    _root="${_git_root}"
  else
    _root="$(pwd)"
  fi
fi

# ---------------------------------------------------------------------------
# Resolve the coordinator_root_path discriminator this render targets.
#
# This is deliberately NOT re-derived from the invocation cwd (which under
# QUEUE_APPEND_OUTPUT_ROOT test-isolation is an arbitrary tmp dir with no git
# repo of its own) — it MUST match what coordinator-queue-append's writer
# stamped onto each entry, which resolves via `_current_repo_root() or
# os.getcwd()` evaluated at the WRITER's actual invocation cwd
# (coordinator-queue-append:1393-1396). In production the writer and this
# generator are invoked from the same real repo, so the two must agree; the
# only stable anchor from inside this script (which may itself run with cwd
# pointed at an isolated test root) is this script's OWN on-disk location —
# resolving the git root of the repo this script lives in, not the process cwd.
# Spec backlink: docs/plans/2026-07-08-project-tracker-render-from-queue.md
# § Chunks C2 (writer auto-resolution) / C3 (generator dual-tenant filter, AC9).
_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)"
_coordinator_root_path="$(git -C "${_script_dir}" rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "${_coordinator_root_path}" ]]; then
  # Fallback path: the primary resolution (this script's own on-disk git
  # root) failed — e.g. vendored/copied outside a git checkout, a
  # detached-HEAD/worktree edge case, or the git binary is absent. Falling
  # back to `_root` here silently degrades the dual-tenant discriminator in
  # exactly the scenario AC9 exists to guard against (a co-tenant meta-repo
  # case), so surface it rather than let it happen invisibly.
  printf 'render-project-tracker.sh: warning: could not resolve this script'\''s own git root (script_dir=%s); falling back to coordinator_root_path=%s — verify this matches the writer'\''s discriminator in a dual-tenant setup\n' \
    "${_script_dir}" "${_root}" >&2
  _coordinator_root_path="${_root}"
fi

_python_bin="$(command -v python3 || true)"
if [[ -z "${_python_bin}" ]]; then
  printf 'render-project-tracker.sh: python3 not found on PATH\n' >&2
  exit 1
fi

exec "${_python_bin}" - "${_root}" "${_coordinator_root_path}" <<'PYEOF'
"""
render-project-tracker.py (embedded) — fold + render engine for the
project-tracker render-from-queue generator.

Purpose: read all state/workstreams/<id>.yaml definitions and all
state/workstreams/events/*.yaml field-scoped events under the given store
root, fold each (workstream, field) pair to its current value by
(sequence, session-id lexical) — never wall-clock — filter to the current
repo's coordinator_root_path, and render docs/project-tracker.md per the
format contract in
coordinator/pipelines/update-docs/tracker-maintenance.md
§ Project Tracker Format Reference, with schema-conformant frontmatter per
coordinator/schemas/tracker.schema.json.

Spec backlink: docs/plans/2026-07-08-project-tracker-render-from-queue.md
§ Approach / § Substrate / § Chunks C3.
"""

import glob
import os
import re
import sys

STORE_ROOT = sys.argv[1]

# The dual-tenant discriminator this render targets — resolved by the bash
# wrapper from THIS SCRIPT'S own on-disk git root (never from the process
# cwd/STORE_ROOT), so it agrees with what coordinator-queue-append's writer
# stamped onto each entry (writer resolves via `_current_repo_root() or
# os.getcwd()` at ITS OWN invocation cwd — coordinator-queue-append:1393-1396
# — which under QUEUE_APPEND_OUTPUT_ROOT test isolation is the real repo the
# test runs from, NOT the isolated tmp store root). See the bash wrapper's
# `_coordinator_root_path` resolution comment for the full rationale.
COORDINATOR_ROOT_PATH = sys.argv[2]

DEFINITIONS_DIR = os.path.join(STORE_ROOT, "state", "workstreams")
EVENTS_DIR = os.path.join(STORE_ROOT, "state", "workstreams", "events")
DOCS_DIR = os.path.join(STORE_ROOT, "docs")
TRACKER_PATH = os.path.join(DOCS_DIR, "project-tracker.md")

# Frozen negative-spec (plan § C3): the generator MUST NOT emit a status
# value outside this enum — example-orchestration-hub-repo's cockpit emitter quarantines
# any other value to malformed_records fleet-wide.
_ALLOWED_STATUSES = {"active", "archived"}
_DEFAULT_STATUS = "active"

# workstream.schema.json's `created` field is `format: date`
# (YYYY-MM-DD) — validated before frontmatter interpolation below (see
# _emitted_created) so an unsanitized store value can never break the
# `---`-delimited frontmatter parse boundary.
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _unquote_scalar(raw: str, *, key: str | None = None):
    """Parse a single YAML scalar value: strip surrounding quotes, else
    return the raw string. Deliberately minimal — the store's writer
    (coordinator-queue-append._emit_yaml_field) only ever emits plain or
    quoted scalars, block sequences of quoted scalars, and the
    deliverables[].text block-map shape; a full YAML grammar is not needed
    and would be a dependency this script does not otherwise carry (avoids
    a PyYAML runtime dependency the render subprocess's PATH/env cannot be
    guaranteed to expose — see the test harness's isolated env).

    Bare-integer coercion is restricted to the `sequence` field (the ONLY
    field schema-typed as an integer — workstream-event.schema.json). Every
    other scalar (workstream_id, field, value, session, etc.) is
    string-typed per schema and stays a str even when it happens to look
    numeric — e.g. a workstream slug named "2026" or an all-digit session
    token must not silently become a Python int, which would raise
    `TypeError` the moment it's compared against a str session/id from a
    different event in _fold_events' (sequence, session) tuple ordering.
    _fold_events does its own explicit int(sequence) at the call site
    regardless, so this coercion is redundant-but-harmless for that field
    and simply not applied to any other."""
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ("'", '"'):
        return raw[1:-1]
    if key == "sequence":
        try:
            return int(raw)
        except ValueError:
            return raw
    return raw


def _load_yaml(path: str) -> dict:
    """Minimal tolerant YAML reader for the workstream/workstream-event
    store shapes: flat `key: value` scalars, `key:` block sequences of
    `  - value` or `  - {text: value}`-ish deliverable maps, matching
    exactly what coordinator-queue-append's _build_yaml/_emit_yaml_field
    (bin/coordinator-queue-append:760-817) ever writes."""
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()

    result: dict = {}
    current_list_key = None
    current_list: list = []
    current_map: dict | None = None

    def _flush_list():
        nonlocal current_list_key, current_list
        if current_list_key is not None:
            result[current_list_key] = current_list
        current_list_key = None
        current_list = []

    for line in lines:
        if not line.strip():
            continue
        if line.startswith("  - "):
            item_raw = line[4:].strip()
            if item_raw.startswith("{") and item_raw.endswith("}"):
                # Minimal inline-map support: {text: "..."} deliverable slots.
                inner = item_raw[1:-1]
                entry: dict = {}
                for part in inner.split(","):
                    if ":" not in part:
                        continue
                    k, _, v = part.partition(":")
                    entry[k.strip()] = _unquote_scalar(v)
                current_list.append(entry)
            else:
                current_list.append(_unquote_scalar(item_raw))
            continue
        if line.startswith("    ") and current_map is not None:
            # Nested block-map deliverable item (text:\n    value form) —
            # not emitted by the current writer, but tolerated defensively.
            continue
        _flush_list()
        if ":" not in line:
            continue
        key, _, rest = line.partition(":")
        key = key.strip()
        rest = rest.strip()
        if rest == "":
            # Block sequence follows on subsequent "  - " lines.
            current_list_key = key
            current_list = []
        else:
            result[key] = _unquote_scalar(rest, key=key)
    _flush_list()
    return result


class _MalformedRecordError(Exception):
    """Raised when a store record is missing a schema-required field.
    Fail-loud, never silent-skip (coordinator/CLAUDE.md § Implementation
    Standards, "detect-then-silently-pick is a footgun"): a truncated write,
    disk corruption, hand-edited YAML, or schema-version drift must surface
    as a visible error naming the offending path, not vanish from the
    render with no diagnostic."""


def _load_definitions(coordinator_root_path: str):
    """Load all top-level state/workstreams/<id>.yaml definition files,
    filtered to the current repo via the coordinator_root_path discriminator
    (dual-tenant filter, plan § C3/AC9) — never fold a co-tenant's entries.
    A record missing the schema-required `workstream_id` field raises
    _MalformedRecordError naming the offending path (fail-loud, not
    silent-skip — coordinator/CLAUDE.md § Implementation Standards)."""
    definitions = {}
    if not os.path.isdir(DEFINITIONS_DIR):
        return definitions
    for path in sorted(glob.glob(os.path.join(DEFINITIONS_DIR, "*.yaml"))):
        if not os.path.isfile(path):
            continue
        body = _load_yaml(path) or {}
        if body.get("coordinator_root_path") != coordinator_root_path:
            continue
        workstream_id = body.get("workstream_id")
        if not workstream_id:
            raise _MalformedRecordError(
                f"{path}: missing required field 'workstream_id' "
                "(workstream.schema.json)"
            )
        definitions[workstream_id] = body
    return definitions


def _load_events(coordinator_root_path: str):
    """Load all field-scoped events under state/workstreams/events/,
    filtered to the current repo via the coordinator_root_path discriminator.
    A record missing a schema-required field raises _MalformedRecordError
    naming the offending path (fail-loud, not silent-skip). See
    _fold_events / _superseded_sessions for how a `supersedes:` pointer
    retracts a prior event by (workstream, field, session)."""
    events = []
    if not os.path.isdir(EVENTS_DIR):
        return events
    for path in sorted(glob.glob(os.path.join(EVENTS_DIR, "*.yaml"))):
        if not os.path.isfile(path):
            continue
        body = _load_yaml(path) or {}
        if body.get("coordinator_root_path") != coordinator_root_path:
            continue
        for required_field in ("workstream", "field", "sequence"):
            if body.get(required_field) in (None, ""):
                raise _MalformedRecordError(
                    f"{path}: missing required field '{required_field}' "
                    "(workstream-event.schema.json)"
                )
        try:
            int(body.get("sequence"))
        except (TypeError, ValueError):
            raise _MalformedRecordError(
                f"{path}: field 'sequence' is not an integer "
                f"(got {body.get('sequence')!r}; workstream-event.schema.json "
                "requires type integer)"
            )
        events.append(body)
    return events


def _superseded_sessions(events) -> set:
    """Collect every (workstream, field, session) triple retracted by some
    OTHER event's `supersedes:` pointer (plan § Approach, "Fold rule": "An
    explicit supersedes: field lets a session retract/correct a prior event
    directly, removing any need to infer causality from timestamps").

    `--supersedes` names the target event's session-id (the pinned contract
    per coordinator/tests/test_workstream_store_collision.py
    test_supersedes_event_wins_over_superseded_event — the plan does not fix
    the exact pointer shape, and session-id is the most direct "retraction
    pointer to a prior event" reading given events are keyed by session in
    this store). Scoped to (workstream, field) — the same session-id string
    could otherwise collide across unrelated workstreams/fields."""
    superseded: set = set()
    for event in events:
        supersedes = event.get("supersedes")
        if not supersedes:
            continue
        workstream = event.get("workstream")
        field = event.get("field")
        if workstream is None or field is None:
            continue
        superseded.add((workstream, field, str(supersedes)))
    return superseded


def _fold_events(events):
    """Fold events per-(workstream, field) independently (field-scoped fold,
    plan § Approach finding 2), each pair keyed on (sequence, session-id
    lexical) — never wall-clock (finding 1). A retracted/corrected event
    (named by some other event's `supersedes:` session-id pointer, scoped to
    the same (workstream, field)) is excluded from the fold entirely —
    regardless of its own sequence — so a same-or-lower-sequence retraction
    still overrides the event it names, per the plan's fold rule. Returns
    {(workstream, field): winning_event_body}."""
    superseded = _superseded_sessions(events)
    winners: dict[tuple[str, str], dict] = {}
    for event in events:
        workstream = event.get("workstream")
        field = event.get("field")
        if workstream is None or field is None:
            continue
        session = event.get("session", "")
        if (workstream, field, session) in superseded:
            # This event has been named by another event's `supersedes:`
            # pointer — it's retracted, so it never enters the fold
            # regardless of its own sequence number.
            continue
        key = (workstream, field)
        sequence = event.get("sequence")
        try:
            sequence = int(sequence)
        except (TypeError, ValueError):
            continue
        current = winners.get(key)
        if current is None:
            winners[key] = event
            continue
        current_seq = int(current.get("sequence", 0))
        current_session = current.get("session", "")
        # Deterministic total order: higher sequence wins; ties broken by
        # lexically-greatest session-id. Never wall-clock/write-order.
        if (sequence, session) > (current_seq, current_session):
            winners[key] = event
    return winners


def _deliverable_index(field: str) -> int | None:
    """Parse a 'deliverable[N].done' field name into its slot index N, or
    None if the field is not a deliverable-completion field."""
    prefix = "deliverable["
    suffix = "].done"
    if field.startswith(prefix) and field.endswith(suffix):
        idx_str = field[len(prefix):-len(suffix)]
        try:
            return int(idx_str)
        except ValueError:
            return None
    return None


def _build_workstream_view(workstream_id: str, definition: dict, folded: dict):
    """Merge a workstream's definition with its folded field state into a
    single render-ready view. Union-tolerant (finding 6): a folded
    deliverable-completion event referencing a slot not present in the
    definition's deliverables[] renders as a pending/orphan line rather
    than being silently dropped."""
    status_event = folded.get((workstream_id, "status"))
    status = status_event.get("value") if status_event else None

    deliverables = list(definition.get("deliverables") or [])
    deliverable_done = {}
    max_orphan_index = -1
    for (ws_id, field), event in folded.items():
        if ws_id != workstream_id:
            continue
        idx = _deliverable_index(field)
        if idx is None:
            continue
        done_value = str(event.get("value", "")).strip().lower() in ("true", "1", "yes")
        deliverable_done[idx] = done_value
        if idx >= len(deliverables):
            max_orphan_index = max(max_orphan_index, idx)

    # Union-tolerant: extend the rendered deliverable list with orphan slots
    # (events referencing indices past the current definition snapshot) so
    # their completion state is never silently dropped. Deliberately fills
    # EVERY intermediate index up to max_orphan_index, not just the indices
    # an event actually references — e.g. 2 defined deliverables (0-1) plus
    # an event on index 5 backfills 2, 3, and 4 as orphan placeholders too,
    # avoiding gaps in the rendered numbered list.
    rendered_deliverables = list(deliverables)
    for idx in range(len(deliverables), max_orphan_index + 1):
        rendered_deliverables.append({"text": f"deliverable[{idx}] (orphan — pending definition sync)"})

    return {
        "workstream_id": workstream_id,
        "title": definition.get("title", workstream_id),
        "created": definition.get("created", ""),
        "status": status,
        "specs": definition.get("specs") or [],
        "dependency_annotations": definition.get("dependency_annotations") or [],
        "deliverables": rendered_deliverables,
        "deliverable_done": deliverable_done,
    }


def _render_deliverable_line(index: int, deliverable: dict, done: bool) -> str:
    text = deliverable.get("text", f"deliverable[{index}]")
    marker = "[x]" if done else "[ ]"
    label = f"deliverable[{index}]"
    if done:
        return f"- {marker} ~~{text}~~ ({label})"
    return f"- {marker} {text} ({label})"


def _render_workstream_section(number: int, view: dict) -> str:
    lines = [f"### {number}. {view['title']}"]
    status_display = view["status"] if view["status"] else "Ready"
    lines.append(f"**Status:** {status_display}")
    if view["specs"]:
        lines.append(f"**Specs:** {', '.join(view['specs'])}")
    if view["dependency_annotations"]:
        for annotation in view["dependency_annotations"]:
            lines.append(f"- {annotation}")
    lines.append("")
    for idx, deliverable in enumerate(view["deliverables"]):
        done = view["deliverable_done"].get(idx, False)
        lines.append(_render_deliverable_line(idx, deliverable, done))
    return "\n".join(lines)


def _emitted_status(views) -> str:
    """Overall tracker frontmatter status — active unless every workstream
    is archived, in which case the tracker itself is archived. Frozen to
    {active, archived} per the negative-spec above.

    Deliberate: an empty store (zero workstream definitions, e.g. a fresh
    day-0 scaffold, or every definition filtered out by the dual-tenant
    discriminator) falls through to `_DEFAULT_STATUS` ("active"), not
    "archived" — matches the day-0 scaffold's expectation of an
    active-but-empty tracker rather than treating "nothing yet" the same
    as "everything is done"."""
    statuses = {v["status"] for v in views if v["status"]}
    if statuses and statuses == {"archived"}:
        return "archived"
    return _DEFAULT_STATUS


def _emitted_created(views) -> str:
    """Tracker frontmatter 'created' — the earliest workstream creation
    date, so the frontmatter reflects the store's actual provenance rather
    than the render timestamp (AC10: no silent value drift vs the existing
    emission's heuristically-derived value). Each candidate value is
    validated against workstream.schema.json's `format: date` (YYYY-MM-DD)
    before being considered — mirrors the existing `status` re-validation
    pattern at emission time (main()) — since this value is interpolated
    directly into the hand-built frontmatter block with no escaping; an
    unsanitized value containing a newline or a `---` line could otherwise
    corrupt the frontmatter's parse boundary. Fail-loud (not silent-skip)
    on a malformed date, per _MalformedRecordError's standard."""
    created_dates = []
    for view in views:
        created = view["created"]
        if not created:
            continue
        if not _DATE_RE.match(created):
            raise _MalformedRecordError(
                f"workstream {view['workstream_id']!r}: field 'created' "
                f"is not a valid YYYY-MM-DD date (got {created!r}; "
                "workstream.schema.json requires format: date)"
            )
        created_dates.append(created)
    if created_dates:
        return sorted(created_dates)[0]
    return ""


def main() -> int:
    coordinator_root_path = COORDINATOR_ROOT_PATH

    definitions = _load_definitions(coordinator_root_path)
    events = _load_events(coordinator_root_path)
    folded = _fold_events(events)

    views = [
        _build_workstream_view(workstream_id, definition, folded)
        for workstream_id, definition in definitions.items()
    ]

    # Render order (finding 3): deterministic total order by
    # (created-timestamp, workstream-id lexical) — never directory read
    # order, never wall-clock.
    views.sort(key=lambda v: (v["created"], v["workstream_id"]))

    status = _emitted_status(views)
    if status not in _ALLOWED_STATUSES:
        status = _DEFAULT_STATUS
    created = _emitted_created(views)
    title = "Project Tracker"

    frontmatter_lines = [
        "---",
        f"title: {title}",
        f"created: {created}",
        f"status: {status}",
        "---",
        "",
    ]

    body_lines = [
        f"# Project Tracker — {title}",
        f"**Last updated:** {created}",
        "**Overall status:** generated from state/workstreams/ — see coordinator/bin/render-project-tracker.sh",
        "",
        "## Active Workstreams",
        "",
    ]

    for number, view in enumerate(views, start=1):
        body_lines.append(_render_workstream_section(number, view))
        body_lines.append("")

    body_lines.extend([
        "## Backlog",
        "Items that are real but not imminently actionable.",
        "",
        "## Archive Pointer",
        "→ Completed work: archive/completed/",
        "→ Query: query-completions --since <date> (per-entry files under archive/completed/YYYY-MM/)",
        "",
    ])

    # Single join over the concatenated line lists — one source of truth for
    # line separators. (Previously two separate joins concatenated directly;
    # that only worked because frontmatter_lines' trailing "" element
    # happened to supply the one newline needed between the closing `---`
    # and the body's first line — a future edit removing that "" sentinel
    # would have silently glued the two together with no error.)
    rendered = "\n".join(frontmatter_lines + body_lines)

    os.makedirs(DOCS_DIR, exist_ok=True)
    with open(TRACKER_PATH, "w", encoding="utf-8") as fh:
        fh.write(rendered)

    return 0


sys.exit(main())
PYEOF
