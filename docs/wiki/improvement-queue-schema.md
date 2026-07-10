---
title: "Improvement-Queue — Per-Entry YAML Schema"
kind: wiki
audience: coordinator-em
created: 2026-06-15
last-updated: 2026-07-09
system: improvement-queue
---

# Improvement-Queue Schema

<!-- Spec backlink: archive/specs/2026-06/2026-06-15-structured-queue-medium-rollout.md § C3 -->
<!-- Spec backlink: docs/plans/2026-06-22-cockpit-contract-ext.md § C2c (central-queue restructure) -->
<!-- Spec backlink: docs/plans/2026-06-25-example-initiative-tc-2-queues-lessons-consolidation.md § D1 (unified base+extension shape) -->
<!-- Spec backlink: tasks/2026-07-08-install-dogfood-friction.md § F12 (doc-edit/test-edit change_kind additions; per-schema --help) -->

<!-- Negative-spec: Do NOT write [universal] entries directly to state/improvement-queue/ without
     setting queue_scope: central — universal entries without that tag are indistinguishable from
     project-scoped rows in the same directory. Do NOT write [universal] lessons (wiki-bound) here —
     those route to state/lessons-outbox/ via bin/coordinator-lesson-promote (/learn-lessons local-mode).
     doctrine-edit is NOT a valid change_kind in the project tier — universal-only.
     Do NOT use the old pipe-delimited prose file state/coordinator-improvement-queue.md — that
     file has been swept; it no longer exists. All entries go to state/improvement-queue/*.yaml.
     Do NOT add an `id:` field to queue entries — the filename (<date>-<slug>.yaml) is the
     canonical handle (D2). Do NOT add a stored `lifecycle:` or `live:` frontmatter field —
     liveness is DERIVED at query time from `status` (tc-0 negative-spec).
     Tombstone: state/improvement-queue.md was a migrated placeholder swept by tc-2 / C7. -->

The improvement queue is a structured YAML directory (`state/improvement-queue/`) holding actionable
improvement items at two scope tiers: **project-specific** entries (one per consumer repo) and
**central universal** entries (in example-orchestration-hub at `$(coordinator_state_root --central)/improvement-queue/`, tagged `queue_scope: central` — see `state-placement-law.md`).
The queue is the tail of the two-tier lesson routing system: universal wiki-bound lessons promote to
`state/lessons-outbox/` via `bin/coordinator-lesson-promote`; improvement items (actionable changes to
scripts, skills, hooks, agents, or wikis) land here.

This schema defines the **structured per-entry YAML shape** for all entries stored under
`state/improvement-queue/` (one file per entry, YAML, no `---` delimiter blocks). The filename
`<date>-<slug>.yaml` is the canonical identity key — no separate `id:` field.

---

## Base Field-Set (shared by all three queue schemas)

> The improvement-queue, bug-backlog, and debt-backlog share a common base field-set. The
> required-set is the small intersection every queue satisfies on disk. Additional fields are
> base-optional and required only within the domain extension that already carries them.
> This section is authoritative and near-identical in all three schema wikis.

| Field | Type | Base Req? | Semantics | Example |
|---|---|---|---|---|
| `created` | string (ISO date) | **required** | Date of entry creation. Format: `YYYY-MM-DD`. Fleet-canonical temporal key (tc-0 § Shared Core Keys). | `"2026-06-15"` |
| `title` | string | **required** | One-line summary. Noun-phrase or imperative; brief enough to scan in a queue listing. | `"Promote persona-name word-boundary patterns into REVIEW_PATTERNS"` |
| `body` | string (block scalar) | **required** | Multi-line prose description. **Expressive, never flattened** — a paragraph is sufficient; this is not a mini-plan. Use `body: |` block scalar. | See example below. |
| `status` | enum (string) | **required** | Lifecycle state. **Base enum: `{open, closed, deferred}`**. Domain extensions may add values (bug adds `wontfix`). See § Status enum. | `"open"` |
| `from_repo` | string | optional (required in improvement domain) | Registry shortname of the originating repo. Resolved from `machine-local/registry.local.toml [repos]`. Not a URL or filesystem path. | `"coordinator-claude"` |
| `surface` | string | optional (required in improvement+bug domains) | The file, subsystem, or script the entry concerns, using path-like notation. Renamed from `surface` (improvement) / `system` (bug); debt never had this field. | `"setup/publish.sh:88-95"` |
| `proposed_action` | string | optional (required in improvement+debt domains) | What to do about it — the remediation or fix target. Renamed from `proposed_target` (improvement) / `suggested_action` (debt) / off-schema `recommended_fix` (bug). | `"setup/publish.sh (REVIEW_PATTERNS array)"` |
| `closed_at` | string (ISO date) | optional | Closure date. Set when `status: closed` (or `wontfix` for bug). Format: `YYYY-MM-DD`. Renamed from `resolved_at` (debt). | `"2026-07-01"` |
| `closed_by` | string | optional | Closure attribution — commit SHA preferred; prose tolerated for ported debt entries. Renamed from `resolution_note` (debt). | `"a232af90"` |
| `tags` | list of strings | optional | Free-form filter tags: system name, symptom label, domain, triage bucket. Renamed from `scope_tags` (improvement) / off-schema `tags` (debt). | `["publish", "depersonalize", "oss"]` |
| `evidence` | string or list of strings | optional | Provenance: commit SHA, plan path, related entry IDs, or cross-queue references. Renamed from `cross_ref` (bug, debt). | `"docs/plans/2026-05-08-formalize-percolation.md"` |

**Dropped field — `id`:** the filename `<date>-<slug>.yaml` is the canonical identity key (D2).
No `id:` field is written or validated. Cross-references in entry bodies that cite old `BS-`/`DSR-`
handles stay as prose in the `evidence` field; the dedicated `id:` field is gone.

**Renamed fields (migration note):** old names `proposed_target`, `scope_tags`, `cross_ref`,
`resolved_at`, `resolution_note`, `system`, `suggested_action`, `recommended_fix` must NOT appear
as live field names. They may appear only in migration notes or historical comments.

---

## Domain Extension — Improvement Queue

The improvement domain adds the following fields on top of the base set. Fields marked
"required-in-domain" are validated by `coordinator-queue-append --schema improvement-queue`;
they are NOT base-required (the base required-set is only `{created, title, body, status}`).

| Field | Type | Domain Req? | Semantics | Example |
|---|---|---|---|---|
| `from_repo` | string | **required-in-domain** | See base field-set. Required here because the improvement must be traceable to its originating repo. | `"coordinator-claude"` |
| `surface` | string | **required-in-domain** | See base field-set. Required here because the improvement must name the specific file or script it targets. | `"setup/publish.sh:88-95"` |
| `proposed_action` | string | **required-in-domain** | See base field-set. Required here because the improvement must state what change to make. | `"setup/publish.sh (REVIEW_PATTERNS array)"` |
| `change_kind` | enum (string) | **required-in-domain** | Classification of the target change: `{script-edit, skill-edit, wiki-append, wiki-new, hook-edit, agent-prompt-edit, doc-edit, test-edit}`. See § Change-kind enum. `doctrine-edit` is NOT valid at project scope — universal-only, routes via lessons-outbox. | `"script-edit"` |
| `queue_scope` | enum (string) | optional | Population tag: `central` (universal pattern, captured in `~/.claude`) or `project` (repo-local). Both kinds share `state/improvement-queue/` in the meta-repo; this field is the discriminator. Omitting is treated as `project` by convention, but explicit tagging is preferred. | `"central"` |

---

## Provenance Block — `system:`

<!-- Spec backlink: ccos-3 § C4 (system-provenance block wiki documentation) -->

> **Three-layer logical grouping (modeled on example-voice-system's TrackerRecord).** Coordinator queue/backlog records form an _identity_ / _fields_ / _system_ provenance triple: **identity** (routing columns — `created`, `title`, `status`) and **fields** (business data — the domain extension fields) are the existing top-level keys. ccos-3 adds the **`system` provenance block** as a third logical layer. This split is *logical and documented* — records are NOT physically re-nested; the `system:` map sits alongside existing top-level keys (additive realization).

The `system` block carries provenance metadata for cockpit indexing and historical audit. **All subfields are OPTIONAL** — see § `required:` = intersection rationale below.

| Field | Type | Semantics |
|---|---|---|
| `created_by_session` | string | Canonical harness session_id of the authoring session. **Cockpit-load-bearing** — the primary session-identity key for fleet indexing. |
| `created_by_agent` | string | Persona or agent identity string (e.g. `"the Staff Engineer"`, `"code-reviewer"`, `"em"`). **DISTINCT from `created_by_session`** — a single session can involve multiple agent personas; do not collapse agent identity into session identity. |
| `linked_sessions` | list of strings | All harness session_ids that have touched this record. Belongs to the **shared session-id identifier space** across ccos-3/4/5/6 — NEVER mix with authoring-session path strings or commit SHAs. |
| `linked_commits` | list of strings | Commit SHAs that realized or subsequently modified this record. |
| `provenance_completeness` | enum string | `complete` or `unknown`. See § Completeness default and closed-enum exemption below. |

### Design B — absence implies `provenance_completeness: unknown`

A record with **no `system` block** (the ~309 historical flat records that predate ccos-3) is treated as `provenance_completeness: unknown` by default. This is an **honest marker, NOT fabricated back-fill** — `unknown` is the truthful annotation for records whose provenance cannot be determined. Raw-record consumers (ccos-4/5/6 pipelines) MUST resolve completeness via the shared helper `bin/lib/provenance.get_provenance_completeness(record)` — **never assume the block is present** or re-derive the default inline.

`unknown` intentionally covers two structurally distinct cases:
1. **Historical-absent** — no `system` block at all (pre-ccos-3 flat record).
2. **Write-time-unresolved** — a present `system` block exists (possibly with `linked_sessions`) but completeness cannot be confirmed at write time.

The binary `complete` / `unknown` axis suffices for cockpit; these two cases remain structurally distinguishable by inspecting whether the `system` key is present at all.

### `required:` = intersection rationale

The `system` subfields are **OPTIONAL, never `required:`**. Requiring them would cause all historical flat records to fail schema validation — the documented "new schema requiring legacy-absent fields re-creates fight-the-hook" trap. The base required-set (`created`, `title`, `body`, `status`) is the intersection every record satisfies on disk; provenance metadata sits outside that intersection by design.

### Closed-enum exemption for `provenance_completeness`

`provenance_completeness` is a **closed enum `[complete, unknown]`** because it is an **internal honesty axis**: (a) it is NOT emitted into cockpit switching logic, and (b) it is exhaustive by construction. This is **NOT precedent** for closing genuinely-evolving consumer-facing fields (e.g. `dominant_tool`, `model`, link-type) — those stay OPEN strings per the cockpit emit-discipline (caveat 3).

### `created_by_agent` string-vs-boolean divergence

Coordinator uses `created_by_agent: string` (carrying the specific persona/agent identity), **intentionally diverging from example-voice-system's `createdByAgent?: boolean`**. Coordinator tracks multiple concurrent agent personas (the Staff Engineer, the Game Dev Reviewer, the Data Science Reviewer, the Front-End Reviewer, the UX Reviewer, the Director of Engineering, and others) — a string carries which persona authored the record; a boolean would collapse all agent identity to true/false and discard that information.

### ccos-8 owns the snake_case emission projection

The `system` block stays snake_case internally. **ccos-8's cockpit-emission projection OWNS the mapping** from the snake_case spine record to the emission contract as a named, explicit step — not an implicit conversion baked into the record format. Cockpit couples to that emission projection, not to the raw spine record.

### Example `system` block

```yaml
system:
  created_by_session: "ses-2026-06-27-abc123"
  created_by_agent: "em"
  linked_sessions:
    - "ses-2026-06-27-abc123"
  linked_commits:
    - "a232af90"
  provenance_completeness: "complete"
```

---

## Change-kind enum

These are the change kinds applicable to improvement-queue entries. The lessons-outbox schema
(`docs/wiki/lessons-outbox-schema.md § Change-kind enum`) defines the full universal enum;
`doctrine-edit` and `snippet-sync-update` from that enum are NOT valid here at project scope.

| Value | Semantics |
|---|---|
| `script-edit` | A change to a `bin/` utility script that is not a hook. Applies when the entry identifies a bug, missing flag, or wrong default in a CLI tool. |
| `skill-edit` | A `SKILL.md` body edit. Use when the entry identifies a missing step, wrong gate, or incorrect procedure in a project-specific skill. |
| `wiki-append` | An append to an existing wiki section within the project. The most common value — use when the entry adds a row, paragraph, or named exception to an existing wiki article. |
| `wiki-new` | A new wiki file under `docs/wiki/`. Use when the entry introduces a concept or subsystem with no existing wiki home in the project. |
| `hook-edit` | A change to a hook script — any `.sh`, `.py`, or `.ps1` file under `hooks/`. Applies when the entry identifies a missing guard, wrong trigger, or silent failure in a hook. |
| `agent-prompt-edit` | A change to an agent prompt body (files under `agents/`). Applies when the entry refines how a named agent reasons or what it checks, scoped to this project. |
| `doc-edit` | A change to a non-wiki documentation file — `README.md`, `INSTALL.md`, `CONTEXT.md`, or similar project-root/consumer-facing docs. Use when the entry doesn't fit `wiki-append`/`wiki-new` (those are `docs/wiki/` specifically) and isn't a wiki at all. |
| `test-edit` | A new or modified test file — `*.test.py`, `*.test.js`, `bats` fixtures, or similar. Use when the entry's fix target is test coverage itself, not the production code the tests exercise. |

Unrecognized values should be flagged at admission time. If a new project-specific change kind
is needed, surface it to the EM for schema extension — do not use `doctrine-edit` as a stand-in.

---

## Status enum

| Value | Semantics | Liveness |
|---|---|---|
| `open` | Entry is actionable and not yet worked. Default on admission. | LIVE |
| `closed` | Entry has been resolved. Set `closed_at` and `closed_by` when transitioning. Move to archive via `git mv`. | DONE |
| `deferred` | Intentionally deferred with PM authorization. Requires (a) an architectural reason and (b) in-session PM authorization. Surfaces at the next `/workweek-complete` Step 4 triage. | BLOCKED |

---

## Example entry (complete)

```yaml
created: "2026-06-15"
from_repo: "coordinator-claude"
title: "Promote persona-name word-boundary patterns into REVIEW_PATTERNS"
body: |
  setup/publish.sh:88-95 should promote the 7 persona-name word-boundary patterns
  from depersonalize-for-publish.sh (the Staff Engineer, the Game Dev Reviewer, the Data Science Reviewer, the Front-End Reviewer, the UX Reviewer, the Director of Engineering, the VP-Product Reviewer)
  into REVIEW_PATTERNS so Phase 4 audit warns if Phase 3.5 missed any (belt-and-braces).
  Open from formalize-percolation Spec 3.
surface: "setup/publish.sh:88-95"
proposed_action: "Add persona-name patterns to REVIEW_PATTERNS in setup/publish.sh"
change_kind: "script-edit"
tags: ["publish", "depersonalize", "oss"]
evidence: "docs/plans/2026-05-08-formalize-percolation.md"
status: "open"
queue_scope: "project"
```

---

## Lifecycle

1. **Admission.** An entry is admitted when an improvement is identified during `/learn-lessons`,
   `/update-docs`, or EM observation. The EM surfaces a one-line visibility note ("Queuing X because Y")
   so the PM can veto. Write with `coordinator-queue-append --schema improvement-queue`; set
   `queue_scope: central` for universal patterns captured in `~/.claude`, `queue_scope: project` for
   repo-local items. The entry lands at `state/improvement-queue/<date>-<slug>.yaml`.

2. **Surfacing.** `/workstream-start` offers the backlog. `/workday-complete` depth-nudges when
   the queue has ≥5 entries. `/workweek-complete` Step 4 triages.

3. **Resolution.** The entry is resolved when the underlying fix is committed. Set `status: closed`,
   `closed_at`, and `closed_by` (commit SHA), then `git mv` the file to
   `archive/improvement-queue/<YYYY-MM>/<slug>.yaml`. **Never** mark closed inline in the YAML —
   closed entries left in the open directory inflate query output.

4. **Migration to debt-backlog.** `/debt-triage` may migrate project-specific entries from
   `state/improvement-queue/` to `state/debt-backlog/` when they represent longer-horizon structural
   debt rather than near-term queue items.

5. **Pruning.** The directory form is pruned by `git mv` to archive (§ Resolution). The open
   directory stays lean; `git log` is the history.

---

## Relationship to lessons-outbox

The two systems serve different scope tiers:

| Dimension | improvement-queue | lessons-outbox |
|---|---|---|
| **Scope** | Project-specific | Universal (cross-project) |
| **Target audience** | Local EM operating in this repo | DoE drain → central wiki |
| **Format** | Per-entry YAML (one file per entry) | Per-entry YAML (always structured) |
| **Admission path** | EM writes directly | `bin/coordinator-lesson-promote` CLI only |
| **Drain path** | `/debt-triage`, `/workweek-complete` triage, or inline resolution | `/learn-lessons --central` DoE drain |
| `change_kind` values | `script-edit`, `skill-edit`, `wiki-append`, `wiki-new`, `hook-edit`, `agent-prompt-edit`, `doc-edit`, `test-edit` | Superset including `doctrine-edit`, `snippet-sync-update` |
| **`[universal]` entries** | FORBIDDEN — route to lessons-outbox instead | Required — must be tagged universal |

When the EM identifies an improvement entry at `/learn-lessons` triage time, the routing decision is:

- **Universal + central-wiki target** → invoke `coordinator-lesson-promote` CLI; entry lands in `state/lessons-outbox/`
- **Universal + project-local-wiki target** → auto-apply locally via `/learn-lessons` local-mode
- **Project-specific** → write to `state/improvement-queue/<date>-<slug>.yaml` with `queue_scope: project` (this schema)

---

## Sweep-exclusion contract

`state/improvement-queue/` and `archive/improvement-queue/` are both under `state/` and `archive/`
respectively. Per coordinator CLAUDE.md § "state/ vs tasks/", `state/` is **never archived** by
`/distill` or `/update-docs`. These paths are explicitly named here for greppability — any future
sweep or archive script that encounters `improvement-queue` must confirm this exclusion before acting.

The structured YAML files under `state/improvement-queue/` are not ephemera; they are the
canonical source of record for open project-specific improvement items and must not be swept by
age-based or fingerprint-based cruft eviction.
