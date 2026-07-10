---
title: "Lessons — Per-Entry YAML Schema"
kind: wiki
audience: coordinator-em
created: 2026-06-30
last-updated: 2026-06-30
system: lessons
---

# Lessons Schema

<!-- Spec backlink: docs/plans/2026-06-30-lessons-md-to-queryable-yaml-queue.md § C1 -->
<!-- Spec backlink: docs/plans/2026-06-25-example-initiative-tc-2-queues-lessons-consolidation.md § D1 (unified base+extension shape) -->

<!-- Negative-spec: Do NOT write entries directly to state/lessons.md — that file has been replaced
     by the per-entry YAML directory state/lessons/. Use coordinator-queue-append --schema lessons
     (or the coordinator-lesson-add wrapper) to admit new entries.
     Do NOT write [universal] lessons here using the old inline-tag syntax — scope is now a
     structured field (scope: universal). The inline [universal] tag convention is FROZEN and
     applies only to the legacy lessons.md migration migration window.
     Do NOT add an `id:` field to lesson entries — the filename (<date>-<slug>.yaml) is the
     canonical handle (D2). Do NOT add a stored `lifecycle:` or `live:` frontmatter field —
     liveness is DERIVED at query time from `status` (tc-0 negative-spec).
     Do NOT write to the promote-altitude surface lessons-outbox/ here — that surface is written
     by coordinator-lesson-promote for universal lessons routed to the central DoE wiki drain.
     Do NOT use the old prose file state/lessons.md — it has been superseded; all new captures
     go to state/lessons/<date>-<slug>.yaml. -->

The lessons queue is a structured YAML directory (`state/lessons/`) holding captured patterns,
anti-patterns, and recurring observations from active EM sessions. It is the **capture altitude**
of the two-level lesson routing system: universal lessons that warrant a central wiki edit promote
to `state/lessons-outbox/` via `bin/coordinator-lesson-promote`; the capture queue records them
first as they are observed.

This schema defines the **stored per-entry YAML shape** for all entries stored under
`state/lessons/` (one file per entry, YAML, no `---` delimiter blocks). The filename
`<date>-<slug>.yaml` is the canonical identity key — no separate `id:` field.

---

## Base Field-Set (shared by all four queue schemas)

> The improvement-queue, bug-backlog, debt-backlog, and lessons queues share a common base
> field-set. The required-set is the small intersection every queue satisfies on disk. Additional
> fields are base-optional and required only within the domain extension that already carries them.
> This section is authoritative and near-identical in all four schema wikis.

| Field | Type | Base Req? | Semantics | Example |
|---|---|---|---|---|
| `created` | string (ISO date) | **required** | Date of entry creation. Format: `YYYY-MM-DD`. Fleet-canonical temporal key (tc-0 § Shared Core Keys). | `"2026-06-30"` |
| `title` | string | **required** | One-line summary. Noun-phrase or imperative; brief enough to scan in a queue listing. | `"Shared-tree multi-machine append-only state needs per-entry filenames"` |
| `body` | string (block scalar) | **required** | Multi-line prose description. **Expressive, never flattened** — includes UPDATE addenda and SECOND-INSTANCE threads verbatim from old format. Use `body: |` block scalar. | See example below. |
| `status` | enum (string) | **required** | Lifecycle state. **Lessons enum — ADD-with-tolerated-base (the Director of Engineering R1):** new vocabulary adds `applied` and `triaged`; base `{open, closed, deferred}` remain tolerated for migrated/back-compat entries. See § Status enum. | `"open"` |
| `from_repo` | string | optional (required in lessons domain) | Registry shortname of the originating repo. Resolved from `machine-local/registry.local.toml [repos]`. Not a URL or filesystem path. | `"coordinator-claude"` |
| `evidence` | string or list of strings | optional | Provenance: commit SHA, plan path, or related entry IDs. Replaces brittle `state/lessons.md:<line>` citations from the old inline-markdown format. | `"docs/plans/2026-06-30-lessons-md-to-queryable-yaml-queue.md"` |
| `closed_at` | string (ISO date) | optional | Closure date. Set when `status: applied` or `status: closed`. Format: `YYYY-MM-DD`. | `"2026-07-01"` |
| `closed_by` | string | optional | Closure attribution — commit SHA preferred; prose tolerated for migrated entries. | `"a232af90"` |
| `tags` | list of strings | optional | Free-form filter tags: scope, system name, symptom label, triage bucket. | `["concurrency", "file-append", "anti-pattern"]` |

**Dropped field — `id`:** the filename `<date>-<slug>.yaml` is the canonical identity key (D2).
No `id:` field is written or validated. Cross-references in entry bodies that cite old lessons.md
line numbers stay as prose in the `evidence` field; the dedicated `id:` field is absent by design.

---

## Domain Extension — Lessons

The lessons domain adds the following fields on top of the base set. Fields marked
"required-in-domain" are validated by `coordinator-queue-append --schema lessons`;
they are NOT base-required (the base required-set is only `{created, title, body, status}`).

| Field | Type | Domain Req? | Semantics | Example |
|---|---|---|---|---|
| `scope` | enum (string) | **required-in-domain** | Classification of the lesson's applicability. `universal` = applies across all coordinator-consuming projects; `project` = local to one repo; `wiki-only` = captured for a specific wiki update. Replaces the old inline `[universal]` tag convention. | `"universal"` |
| `from_repo` | string | **required-in-domain** | See base field-set. Required here because a lesson must be traceable to its originating repo for fleet-query routing. | `"coordinator-claude"` |
| `target_wiki` | string | optional | The `Belongs in <wiki>.md` routing clause from the old format. Names the wiki article the lesson routes to when applied. CLI-settable via `--target-wiki`. | `"lessons-schema.md"` |
| `proposed_target` | string | optional | The doctrine/wiki/hook/skill the lesson routes to when richer than `target_wiki` (e.g., a specific section or skill step). | `"docs/wiki/concurrent-em-git-ops.md § Append-Only Files"` |
| `queue_scope` | enum (string) | optional | Population tag: `central` for universal patterns captured in `~/.claude`, `project` for repo-local items. Omitting is treated as `project` by convention; explicit tagging preferred. | `"central"` |

---

## Provenance Block — `system:`

<!-- Spec backlink: ccos-3 § C4 (system-provenance block wiki documentation) -->

> **Three-layer logical grouping (modeled on example-voice-system's TrackerRecord).** Coordinator queue/backlog
> records form an _identity_ / _fields_ / _system_ provenance triple: **identity** (routing columns —
> `created`, `title`, `status`) and **fields** (business data — the domain extension fields) are the
> existing top-level keys. ccos-3 adds the **`system` provenance block** as a third logical layer.
> This split is *logical and documented* — records are NOT physically re-nested; the `system:` map
> sits alongside existing top-level keys (additive realization).

The `system` block carries provenance metadata for cockpit indexing and historical audit. **All
subfields are OPTIONAL** — see § `required:` = intersection rationale below.

| Field | Type | Semantics |
|---|---|---|
| `created_by_session` | string | Canonical harness session_id of the authoring session. **Cockpit-load-bearing** — the primary session-identity key for fleet indexing. |
| `created_by_agent` | string | Persona or agent identity string (e.g. `"the Staff Engineer"`, `"code-reviewer"`, `"em"`). **DISTINCT from `created_by_session`** — a single session can involve multiple agent personas; do not collapse agent identity into session identity. |
| `linked_sessions` | list of strings | All harness session_ids that have touched this record. |
| `linked_commits` | list of strings | Commit SHAs that realized or subsequently modified this record. |
| `provenance_completeness` | enum string | `complete` or `unknown`. A record with no `system` block is treated as `provenance_completeness: unknown` by default. |

**`required:` = intersection rationale.** The `system` subfields are OPTIONAL, never `required:`.
Requiring them would cause all historical migrated entries (which predate ccos-3) to fail schema
validation. The base required-set (`created`, `title`, `body`, `status`) is the intersection every
record satisfies on disk; provenance metadata sits outside that intersection by design.

### Example `system` block

```yaml
system:
  created_by_session: "ses-2026-06-30-abc123"
  created_by_agent: "em"
  linked_sessions:
    - "ses-2026-06-30-abc123"
  linked_commits:
    - "a232af90"
  provenance_completeness: "complete"
```

---

## Structured Facets — trigger / why / how_to_apply

<!-- Spec backlink: docs/plans/2026-06-30-lesson-structured-facets-and-emit-metadata-fix.md § C2 -->
<!-- Negative-spec: Do NOT post-hoc LLM-extract facets from a lesson's existing prose body —
     fabrication hazard; facets are AUTHOR-SUPPLIED at capture time. This norm extends
     ccos-3 § Anti-scope "do NOT fabricate provenance" from provenance fields to content facets.
     Reference: docs/plans/2026-06-27-ccos-3-provenance-triple-work-item-record.md § Anti-scope -->

The three structured facets are OPTIONAL schema fields that let a lesson be **queried by internal
structure** without losing the expressive prose `body`. They are additive — a lesson without any
facets is fully valid; a lesson with all three is richer for fleet queries.

**CONVENTION: the prose `body` remains the always-present expressive layer; facets are additive,
optional, and AUTHOR-SUPPLIED at capture — never post-hoc LLM-extracted from existing prose
(fabrication hazard).** Capturing a lesson whose body already contains the substance of a facet
does not retroactively make that facet "safe to extract" — the extraction path is still LLM
judgement applied to prose, which drifts. Set facets when you write the entry; leave them absent
on migrated/historical entries whose body you would have to re-interpret to fill them.

| Field | Type | Semantics | Example |
|---|---|---|---|
| `trigger` | string | The precondition or symptom under which the lesson fires — the observable state that should prompt the agent to recall and apply this lesson. | `"When routing a lesson to CLAUDE.md rather than a wiki article."` |
| `why` | string | The rationale — why the corrective action is the right response to the trigger. Names the failure mode or downstream harm the lesson prevents. | `"CLAUDE.md is load-bearing boot-time context, not a per-lesson store; per-lesson inlining causes bloat and violates the routing-bias rule."` |
| `how_to_apply` | string | The corrective action — the concrete step the agent should take when the trigger fires. Imperative phrasing preferred. | `"Route to wiki-append/wiki-new instead; add doe_escalation: true if a CLAUDE.md pointer is genuinely warranted."` |

**`required:` = intersection rationale for facets (same as `system:` subfields).** The three facets
are OPTIONAL, never `required:`. Requiring them would cause all historical migrated entries (which
predate this schema extension) to fail schema validation, recreating the fight-the-hook anti-pattern
documented in `state/lessons/2026-06-23-a-new-schema-that-requires-fields-legacy.yaml`. The base
required-set (`created`, `title`, `body`, `status`) is the intersection every record satisfies on
disk; facet metadata sits outside that intersection by design (same rationale as
`docs/plans/2026-06-27-ccos-3-provenance-triple-work-item-record.md § required: discipline`).

### Example entry with structured facets

```yaml
created: "2026-06-30"
scope: "universal"
from_repo: "coordinator-claude"
title: "Routing lessons to CLAUDE.md instead of a wiki inflates boot-time context"
body: |
  A lesson whose routing target is CLAUDE.md or a CLAUDE.md pointer violates the routing-bias
  rule (wikis are the default; doctrine-edit is DoE-only). Lessons are change-requests against
  doctrine surfaces — the wiki is the right grain; CLAUDE.md is the boot-time entrypoint, not
  a per-lesson store.
trigger: "When a router or EM proposes change_kind: doctrine-edit or target_wiki pointing at CLAUDE.md."
why: "Per-lesson inlining in CLAUDE.md causes bloat and is structurally wrong — routing-bias rule exists to prevent this."
how_to_apply: "Downgrade to wiki-append/wiki-new; set doe_escalation: true if a CLAUDE.md pointer is genuinely needed downstream."
status: "open"
tags: ["routing", "doctrine-edit", "anti-pattern"]
```

---

## Status enum

The lessons domain uses an **ADD-with-tolerated-base** enum (the Director of Engineering R1, binding). New vocabulary
adds `applied` and `triaged`; the base values `{open, closed, deferred}` remain tolerated for
migrated and back-compat entries.

| Value | Semantics | Liveness | Notes |
|---|---|---|---|
| `open` | Entry is actionable and not yet worked. Default on capture. | LIVE | Base value, tolerated. |
| `applied` | Lesson has been applied — the target wiki/doc/hook/skill edit is committed. Set `closed_at` and `closed_by` when transitioning. Move to archive via `git mv`. | DONE | **Terminal.** Preferred over `closed` for new resolutions. |
| `triaged` | Lesson has been routed — a target wiki or plan has been identified and an edit is in-flight. **LIVE, NOT BLOCKED.** A triaged lesson is actively in progress (the routing decision is made, the edit is pending); it is not gated on an external condition. | LIVE | In-flight/routed. |
| `closed` | Back-compat alias for `applied`. Entry has been resolved. Set `closed_at` and `closed_by` when transitioning. Move to archive via `git mv`. | DONE | Tolerated for migrated entries; prefer `applied` for new closures. |
| `deferred` | Intentionally deferred with PM authorization. Requires (a) an architectural reason and (b) in-session PM authorization. Surfaces at the next `/workweek-complete` Step 4 triage. | BLOCKED | Tolerated. Genuinely parked, not in-flight. |

**`triaged` is LIVE, NOT BLOCKED.** This is the load-bearing distinction from `deferred`: a triaged
lesson has a routing decision and an in-flight edit; a deferred lesson is explicitly parked. Do not
conflate them — misclassifying an in-flight lesson as BLOCKED inflates the BLOCKED set and obscures
the real queue depth.

**Liveness mapping for fleet queries:**
- DONE: `applied`, `closed`
- BLOCKED: `deferred`
- LIVE: `open`, `triaged`, or any unknown value

---

## Example entry (complete)

```yaml
created: "2026-06-30"
scope: "universal"
from_repo: "coordinator-claude"
title: "Shared-tree multi-machine append-only state needs per-entry filenames"
body: |
  state/lessons.md is an append-only flat markdown file that all concurrent EM sessions
  on the shared work/* branch append to at /workstream-complete Step 1. This is the
  exact two-failure anti-pattern the structured YAML queues were built to avoid: anchored
  Edits go stale, raw appends are clobbered by a sibling's read-modify-write, and two
  machines appending to one tracked file git-conflict at EOF on every concurrent append.
  Pattern: any shared-tree multi-machine append-only surface needs per-entry filenames
  (one file per entry, atomically written), never a single shared appended file.
target_wiki: "concurrent-em-git-ops.md"
evidence: "docs/plans/2026-06-30-lessons-md-to-queryable-yaml-queue.md"
queue_scope: "central"
status: "open"
tags: ["concurrency", "file-append", "anti-pattern"]
```

---

## Lifecycle

1. **Capture.** A lesson is captured when an EM observes a pattern during active work.
   Use `coordinator-queue-append --schema lessons --title "..." --body "..." --scope universal`
   (or the thin wrapper `coordinator-lesson-add`). The CLI auto-derives `created` (today),
   `from_repo` (cwd git-root via machine-local), and `status: open`. The entry lands atomically at
   `state/lessons/<date>-<slug>.yaml` — one file per entry prevents concurrent-append conflicts.

2. **Dedup pre-check.** Before writing, `coordinator-lesson-add` queries `query-records --type lesson`
   for title-token overlap. If a candidate match exists: "possible duplicate of <file>: '<title>' —
   re-run with `--force` to add anyway, or amend the existing entry." Default is warn-and-exit-nonzero;
   `--force` overrides. This catches SECOND-INSTANCE duplication at capture time.
   **Note: dedup is coordinator-lesson-add only.** Direct `coordinator-queue-append --schema lessons`
   bypasses the dedup check and writes unconditionally. Use `coordinator-lesson-add` for all
   interactive lesson captures; reserve direct `coordinator-queue-append` for programmatic/scripted
   writes that have already been deduplicated at the call site.

3. **Surfacing.** `/workstream-start` surfaces the open backlog. `/workday-complete` depth-nudges
   when the queue has ≥5 entries. `/workweek-complete` Step 4 triages.

4. **Routing.** At `/learn-lessons` triage:
   - **Universal + central-wiki target** → invoke `coordinator-lesson-promote` CLI; entry lands in
     `state/lessons-outbox/` and is drained by `/learn-lessons --central`.
   - **Universal + project-local-wiki target** → auto-apply locally via `/learn-lessons` local-mode.
   - **Project-specific** → work directly; close the entry with `status: applied` + `closed_at` +
     `closed_by` (commit SHA).

5. **Closure.** Set `status: applied` (preferred) or `status: closed` (back-compat), `closed_at`,
   and `closed_by` (commit SHA), then `git mv` the file to `archive/lessons/<YYYY-MM>/<slug>.yaml`.
   **Never** mark closed/applied inline in the YAML while leaving the entry in the open directory —
   closed entries left in `state/lessons/` inflate the open-queue count.

6. **Promotion to triaged.** If a target wiki is identified and an edit is in flight, set
   `status: triaged`. The entry remains in `state/lessons/` (LIVE) until the edit is committed and
   the entry is archived (status: applied, git mv).

---

## Sweep-exclusion contract

`state/lessons/` and `archive/lessons/` are both under `state/` and `archive/` respectively.
Per coordinator CLAUDE.md § "state/ vs tasks/", `state/` is **never archived** by `/distill` or
`/update-docs`. These paths are explicitly named here for greppability — any future sweep or
archive script that encounters `lessons` must confirm this exclusion before acting.

The structured YAML files under `state/lessons/` are not ephemera; they are the canonical source
of record for open captured lessons and must not be swept by age-based or fingerprint-based cruft
eviction.

---

## Relationship to lessons-outbox

The two surfaces serve different altitudes of the lesson routing pipeline:

| Dimension | lessons (capture queue) | lessons-outbox (promote altitude) |
|---|---|---|
| **Path** | `state/lessons/<date>-<slug>.yaml` | `state/lessons-outbox/<topic>.yaml` |
| **Altitude** | EM capture — any lesson, any scope | DoE drain — universal lessons only |
| **Writer** | `coordinator-queue-append --schema lessons` (or wrapper) | `coordinator-lesson-promote` CLI only |
| **Drain path** | `/learn-lessons` triage, `/workweek-complete` Step 4 | `/learn-lessons --central` DoE drain |
| **Scope** | `universal`, `project`, or `wiki-only` | Always universal (scope requirement enforced at promote time) |
| **Schema** | `lesson-entry` (`schemas/lesson-entry.yaml`) | `lessons-outbox` (`schemas/lessons-outbox.yaml`) |

When the EM identifies a lesson at `/learn-lessons` triage time, the routing decision is:

- **Universal + central-wiki target** → invoke `coordinator-lesson-promote` CLI; entry lands in `state/lessons-outbox/`
- **Universal + project-local-wiki target** → auto-apply locally via `/learn-lessons` local-mode; archive the `state/lessons/` entry as `status: applied`
- **Project-specific** → apply directly to the local surface; archive as `status: applied`

The `state/lessons-outbox/` surface is out of scope for this schema — see
`docs/wiki/lessons-outbox-schema.md` for its field definitions and lifecycle.
