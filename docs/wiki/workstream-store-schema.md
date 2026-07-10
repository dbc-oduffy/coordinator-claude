---
title: "Workstream Store — Definition + Field-Scoped Event Schema"
kind: wiki
audience: coordinator-em
created: 2026-07-08
last-updated: 2026-07-08
system: workstream-store
---

# Workstream Store Schema

<!-- Spec backlink: docs/plans/2026-07-08-project-tracker-render-from-queue.md § Approach / § Substrate / § Chunks C2 -->

<!-- Negative-spec: do NOT hand-author frontmatter for state/workstreams/*.yaml or
     state/workstreams/events/*.yaml — both are GENERATE-altitude schemas, registered
     in coordinator/schemas/*.schema.json, with coordinator-queue-append as the
     required write entry point (--schema workstream / --schema workstream-event).
     Hand-authoring trips SCHEMAED-DOC-GENERATE-OBLIGATION per canonical-artifact-shapes.md.
     Do NOT fold events by wall-clock/mtime anywhere downstream — the fold key is
     strictly (sequence, session-id); wall-clock is never monotonic across machines
     (clock skew, NTP correction, DST). Do NOT mutate a definition file field-by-field
     in place for status/deliverable-completion — those are field-scoped events; only
     adding a new deliverable slot is a definition edit (rare, atomic rewrite). -->

The workstream store is the per-entry, collision-safe substrate behind `docs/project-tracker.md`'s
render-from-queue architecture. It replaces in-place editing of the tracker's numbered-list rows
with two directories of structured YAML: **definitions** (one file per strategic workstream) and
**field-scoped events** (append-only, one file per `(workstream, field)` mutation). A generator
(`coordinator/bin/render-project-tracker.sh`, chunk C3) folds both into the rendered tracker view.

This is a **different substrate from the tactical backlogs** (`state/debt-backlog/`,
`state/bug-backlog/`, `state/improvement-queue/`) — those track tactical items (debt, bugs, central
improvement patterns); the workstream store tracks *strategic workstreams* (the tracker's
`### N. Name` sections, Status, spec links, checkbox deliverables, dependency annotations). Zero
field overlap; do not conflate the two systems.

---

## Why two schemas, not one

A plain per-entry definition file fixes *different*-workstream collisions (two sessions creating
two different workstreams both survive as distinct files) but does **not** fix the *same*-row
lost-update: two sessions mutating the *same* workstream's status in place would still race, with
the second write silently discarding the first. Status and deliverable-completion are therefore
modeled as **append-only, field-scoped events** in a separate directory — both writes persist (audit
trail), and a generator folds them to a deterministic current state. This is the design move that
makes "both survive" literally true, not just "different-rows survive."

---

## Schema 1 — `workstream` (definition)

**File:** `coordinator/schemas/workstream.schema.json` · **applies_to:** `state/workstreams/*.yaml`
**Write entry point:** `coordinator-queue-append --schema workstream`

One file per workstream, keyed by `workstream_id` (the filename stem —
`state/workstreams/<workstream_id>.yaml`, no date prefix, unlike the tactical backlogs). Concurrent
creation of *different* workstreams lands in different files — collision-free by construction.
Definition edits are rare; the file is **rewritten atomically** (write-temp + rename, single writer,
low-contention assumption) rather than mutated field-by-field — status/deliverable-completion are
events, not definition edits (see § Definition/event boundary below).

| Field | Type | Required? | Semantics | Example |
|---|---|---|---|---|
| `workstream_id` | string | **required** | Stable identifier; also the filename stem. Immutable once minted. | `"doe-authoring-repo-build"` |
| `title` | string | **required** | Human-readable name, as rendered in the tracker's numbered-list heading. | `"DoE authoring repo build & doctrine migration"` |
| `created` | string (ISO date) | **required** | Creation date (`YYYY-MM-DD`). Part of the render-order tiebreaker `(created, workstream_id)` (§ Approach finding 3). | `"2026-07-08"` |
| `coordinator_root_path` | string | **required** | Dual-tenant discriminator — see § Dual-tenant discriminator below. Auto-resolved from cwd git root; override only for tests/cross-repo routed writes. | `"/Users/example-operator/X/DoE-claude"` |
| `deliverables` | array of `{text: string}` | optional | Ordered deliverable slots. Completion state is NOT recorded here — see § Definition/event boundary. | `[{text: "Ship the store schema"}]` |
| `specs` | array of strings | optional | Spec links (paths under `docs/plans/`, `docs/decisions/`, etc.). | `["docs/plans/2026-07-08-project-tracker-render-from-queue.md"]` |
| `dependency_annotations` | array of strings | optional | Free-text dependency notes carried forward from the hand-edited tracker format. | `["blocked by cross-repo memo loop"]` |

### Invocation

```bash
coordinator-queue-append \
    --schema workstream \
    --workstream-id "doe-authoring-repo-build" \
    --title "DoE authoring repo build & doctrine migration" \
    --created "2026-07-08" \
    --coordinator-root-path "/Users/example-operator/X/DoE-claude"
```

<!-- Review: code-reviewer — F3 (P2): `coordinator_root_path` is `required` on this schema;
     the example now shows the flag explicitly rather than relying on the writer's
     auto-resolve-from-cwd-git-root behavior, so the invocation is self-sufficient and
     schema-valid even if auto-resolution is unavailable (e.g. non-git cwd, cross-repo
     routed write). -->

`--body` and `--status` are **not** part of this schema's shape — the shared base field-set
(`created`/`title`/`body`/`status`) that the tactical backlogs use does not apply here; `status` is
a field-scoped *event*, never a definition field (see below).

A minimal, required-fields-only invocation (e.g. the shape `/workstream-start` uses before any
deliverables are known) omits `deliverables`/`specs`/`dependency_annotations` entirely:

```bash
coordinator-queue-append \
    --schema workstream \
    --workstream-id "new-workstream-slug" \
    --title "New Workstream Title" \
    --created "2026-07-08" \
    --coordinator-root-path "/Users/example-operator/X/DoE-claude"
```
<!-- Review: code-reviewer — F4 (nit): no worked example anywhere showed the
     minimal required-fields-only shape; added alongside the fully-populated example. -->

---

## Schema 2 — `workstream-event` (field-scoped event)

**File:** `coordinator/schemas/workstream-event.schema.json` · **applies_to:** `state/workstreams/events/*.yaml`
**Write entry point:** `coordinator-queue-append --schema workstream-event`

Append-only, one file per event, filename `<date>-<workstream_id>-<session>.yaml` — the proven
collision-safe `state/review-trail/`-style idiom (write-new, keyed by date+workstream+session-id).
The generator folds every event for a given `(workstream, field)` pair to compute that field's
current value at render time.

| Field | Type | Required? | Semantics | Example |
|---|---|---|---|---|
| `workstream` | string | **required** | FK to `state/workstreams/<workstream>.yaml`. | `"doe-authoring-repo-build"` |
| `field` | string | **required** | The field-scoped sub-state this event mutates — `status`, `deliverable[0].done`, `order`, etc. The fold is strictly per-`(workstream, field)` — never whole-event. | `"status"` |
| `value` | string | **required** | The new value for the named field, as of this event. | `"in_progress"` |
| `sequence` | integer | **required** | Explicit machine-independent order key — the writer counts existing events for this `(workstream, field)` and adds 1. **NEVER wall-clock.** See § Fold rule below. | `1` |
| `session` | string | **required** | Writer's session id. Lexical tiebreaker when two events for the same `(workstream, field)` share a `sequence`. | `"ses-2026-07-08-abc123"` |
| `coordinator_root_path` | string | **required** | Dual-tenant discriminator — mirrors the `workstream` schema's field. See § Dual-tenant discriminator. | `"/Users/example-operator/X/DoE-claude"` |
| `supersedes` | string | optional | Retraction/correction pointer to a prior event, so a session can directly correct a mistake without the fold inferring causality from timestamps. | `"2026-07-08-doe-authoring-repo-build-ses-abc.yaml"` |

### Invocation

```bash
coordinator-queue-append \
    --schema workstream-event \
    --workstream "doe-authoring-repo-build" \
    --field "status" \
    --value "in_progress" \
    --sequence 1 \
    --session "ses-2026-07-08-abc123" \
    --coordinator-root-path "/Users/example-operator/X/DoE-claude"
```
<!-- Review: code-reviewer — F3 (P2): `coordinator_root_path` is `required` on this schema too;
     example now shows the flag explicitly rather than relying on auto-resolve, for the same
     self-sufficiency reason as the workstream schema's invocation example above. -->

A minimal, required-fields-only invocation — all six fields on this schema are required, so there
is no further reduction possible beyond showing every flag explicitly (unlike the `workstream`
schema, which has three optional fields to omit):

```bash
coordinator-queue-append \
    --schema workstream-event \
    --workstream "doe-authoring-repo-build" \
    --field "deliverable[0].done" \
    --value "true" \
    --sequence 1 \
    --session "ses-2026-07-08-abc123" \
    --coordinator-root-path "/Users/example-operator/X/DoE-claude"
```
<!-- Review: code-reviewer — F4 (nit): added a second worked example showing a
     deliverable-completion event distinct from the status example above. -->

---

## Fold rule (machine-independent deterministic total order)

Wall-clock is **never** the order key: timestamps are not monotonic across machines (clock skew,
NTP correction, DST) and can tie at the file-mtime/ISO-second granularity the review-trail idiom
uses. The fold instead keys strictly on:

1. **`sequence`** (integer) — the writer counts existing events for `(workstream, field)` and adds 1
   at append time. The fold picks the **highest-sequence** event.
2. **`session` lexical** — tiebreaker when two events share the same `sequence`. Deterministic, not
   causal, and independent of directory read order or which write physically lands on disk first.
3. **`supersedes`** — lets a session directly retract/correct a prior event without the fold needing
   to infer causality from timestamps.

A lost sequence race (two writers computing the same next-sequence integer concurrently) just
retries to the next integer via the same `_write_out_path_excl` retry-with-suffix idiom the file
layer already uses — no new collision primitive is needed.

**Fold granularity is field-scoped, not whole-event-scoped.** Two different-deliverable-field
events on the *same* workstream both survive the fold independently — folding at whole-event
granularity would silently drop one deliverable's completion, reintroducing the exact lost-update
this design exists to kill, one level down.

---

## Definition/event boundary

"Definition mutated in place" means the definition file is rewritten atomically (write-temp +
rename, single writer, low-contention assumption) — never hand-edited field-by-field. Once
deliverable *completion* is a field-scoped event, the boundary is:

- **Adding a new deliverable slot** — a definition edit (rare, atomic rewrite).
- **Checking an existing deliverable** — an event (frequent, field-scoped, e.g.
  `field: "deliverable[4].done"`).

A narrow race exists where session A adds deliverable 5 (definition edit) while session B
concurrently checks deliverable 4 — if the fold reads a definition snapshot predating A's add. The
generator's fold is **union-tolerant**: an event referencing a deliverable slot not yet present in
the definition snapshot renders as a pending/orphan line rather than being silently dropped.

---

## Dual-tenant discriminator — `coordinator_root_path`

Both schemas carry `coordinator_root_path` — the git root path of the repo the record belongs to,
the same composite-natural-key component example-orchestration-hub's `trackers.py` already uses. It is folded from the
example-orchestration-hub-repo-em constraints memo (2026-07-08).

**Why it's needed:** the physical directory `<example-orchestration-hub>/state/workstreams/` is **dual-tenant** when
the git root is the meta-repo — example-orchestration-hub's tree co-mingles BOTH the meta-repo's routed workstreams AND
example-orchestration-hub's own workstreams in one directory (identical to how `state/improvement-queue/` and
`state/lessons/` already co-mingle multiple repos' central entries). Without this discriminator, the
generator (C3) would have no way to tell the two tenants' rows apart at render time.

**Resolution:** auto-resolved from the writer's cwd git root (`git rev-parse --show-toplevel`,
mirroring `from_repo`'s resolution) — override via `--coordinator-root-path` only for tests or
cross-repo routed writes.

**Generator obligation (C3):** the generator MUST filter store entries by this discriminator when
rendering each repo's tracker — render ONLY the current repo's workstreams, never fold the
co-tenant's entries (AC9).

---

## Collision-safety mechanics

Both schemas' writers reuse `coordinator-queue-append`'s existing `_write_out_path_excl` primitive —
`os.O_CREAT | os.O_EXCL` exclusive-create with an incrementing-suffix retry loop
(`<base>-2.yaml`, `-3.yaml`, ...) bounded to 1000 attempts. The negative-spec that already governs
`coordinator-queue-append`'s legacy fallback applies here unchanged: the event-append is a
**terminal caller with no retry path** (like the tactical backlogs, unlike `cross-repo-memo`'s
interactive `--topic` retry), so **retry-with-suffix is correct, NOT bare `O_EXCL` fail-loud**
(`coordinator-queue-append:609-652` at chunk-C1 authoring time).

This closes three collision shapes:

- **(a) Two concurrent status events for the SAME workstream** — both survive as distinct event
  files (same-field concurrency legitimately produces two events; the fold, not file-survival, later
  picks one winner).
- **(b) Two definition creates for DIFFERENT workstreams** — both survive (different filenames,
  collision-free by construction).
- **(c) N-thread concurrent writers racing the same event base-path** — all survive with distinct
  bodies via the exclusive-create + retry-with-suffix loop.

---

## Filename conventions (diverge from the tactical backlogs)

Unlike `state/debt-backlog/`, `state/bug-backlog/`, and `state/improvement-queue/` (all
`<date>-<slug-of-title>.yaml`), the workstream store's filenames are keyed by workstream identity,
not title:

| Schema | Filename | Rationale |
|---|---|---|
| `workstream` | `<workstream_id>.yaml` | One file per workstream, no date prefix — a workstream definition is a long-lived singleton, not a dated log entry. |
| `workstream-event` | `<date>-<workstream_id>-<session>.yaml` | Mirrors `state/review-trail/`'s collision-safe idiom (write-new, keyed by date+entity+session-id). |

`coordinator-queue-append`'s `_output_path()` accepts a `filename_override` parameter for exactly
this divergence — the shared `<date>-<slug>.yaml` scheme is the default for the tactical-backlog
schemas; the workstream-store schemas pass an override computed from their own identity fields.

---

## Relationship to `docs/project-tracker.md`

The workstream store is the substrate; `docs/project-tracker.md` is a **generated, read-only view**
(chunk C3's `render-project-tracker.sh`) — folded definitions + folded events, rendered in the exact
format `pipelines/update-docs/tracker-maintenance.md § Project Tracker Format Reference` defines,
using render order `(created, workstream_id)` (a separate deterministic total order from the fold,
not a contended create-time integer — § Approach finding 3). The render is idempotent: regenerating
twice from an unchanged store produces a byte-identical file (AC3), which holds only because both
the fold and the render order are deterministic total orders — a wall-clock or unspecified-tie fold
would make this unprovable.

**As of this chunk (C2), the store primitive exists but the generator does not yet** — C1-C4 land as
unwired reference code; the live `docs/project-tracker.md` continues to be hand-edited by the
not-yet-retargeted writers (C5-C13) until the cross-repo memo loop closes. See
`docs/plans/2026-07-08-project-tracker-render-from-queue.md § Cross-repo rollout & sequencing`.

---

## Sweep-exclusion contract

`state/workstreams/` (and its `events/` subdirectory) is under `state/`. Per coordinator CLAUDE.md
§ "state/ vs tasks/", `state/` is **never archived** by `/distill` or `/update-docs`. Named here for
greppability — any future sweep or archive script that encounters `workstreams` must confirm this
exclusion before acting. These files are the canonical source of record for the project tracker and
must not be swept by age-based or fingerprint-based cruft eviction.
