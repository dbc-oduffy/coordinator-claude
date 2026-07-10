---
title: "Debt-Backlog — Per-Entry YAML Schema"
kind: wiki
audience: coordinator-em
created: 2026-06-15
last-updated: 2026-06-25
system: debt-triage
---

# Debt-Backlog Schema

<!-- Spec backlink: archive/specs/2026-06/2026-06-15-structured-queue-medium-rollout.md § C1 -->
<!-- Spec backlink: docs/plans/2026-06-25-example-initiative-tc-2-queues-lessons-consolidation.md § D1 (unified base+extension shape) -->

<!-- Negative-spec: The pre-plan approach of appending debt items as pipe-separated rows to
     state/debt-backlog.md is REPLACED by per-entry YAML files at state/debt-backlog/*.yaml.
     state/debt-backlog.md has been swept by tc-2 / C7 (after its 13 live straggler bullets
     were drained in C6). The central universal improvement queue (state/improvement-queue/,
     queue_scope:central) is governed by improvement-queue-schema.md and uses the same git-mv
     closure as all other directory-form queues — it is no longer a markdown-line-per-entry holdout.
     Do NOT add an `id:` field to debt entries — the filename (<date>-<slug>.yaml) is the
     canonical handle (D2). Do NOT use `suggested_action:` — the canonical name is
     `proposed_action:` (renamed). Do NOT use `resolved_at:` or `resolution_note:` — the
     canonical closure fields are `closed_at:` and `closed_by:`. Do NOT use `cross_ref:` — the
     canonical name is `evidence:`. Do NOT use `status: resolved` — the canonical done value is
     `status: closed` (ported). Do NOT use `status: open for-weekly-arch-review` — use
     `status: open` with `tags: [weekly-arch-review]` instead (space-bearing enum value removed).
     Do NOT fold `source:` into the generic `evidence:` field — `source:` stays a required
     debt-domain field to preserve provenance audit discipline (prior-art-checker Claim #12).
     Do NOT add a stored `lifecycle:` or `live:` frontmatter field — liveness is DERIVED at
     query time from `status` (tc-0 negative-spec).
     Tombstone: state/debt-backlog.md was a migrated placeholder swept by tc-2 / C7. -->

The debt backlog is a per-entry YAML store at `state/debt-backlog/<date>-<slug>.yaml` inside the
repo. Each file represents one architectural debt item identified during strategic reviews. Entries
are produced by `coordinator-queue-append --schema debt-backlog` (invoked by the EM or by
`/debt-triage` during capture). The `/debt-triage` skill reads the directory and writes queries via
`bin/query-records.js --type debt`. Closure moves an entry to `archive/debt-backlog/<YYYY-MM>/`
via `git mv` — see § Closure contract. The filename `<date>-<slug>.yaml` is the canonical
identity key — no separate `id:` field.

---

## Base Field-Set (shared by all three queue schemas)

> The improvement-queue, bug-backlog, and debt-backlog share a common base field-set. The
> required-set is the small intersection every queue satisfies on disk. Additional fields are
> base-optional and required only within the domain extension that already carries them.
> This section is authoritative and near-identical in all three schema wikis.

| Field | Type | Base Req? | Semantics | Example |
|---|---|---|---|---|
| `created` | string (ISO date) | **required** | Date of entry creation. Format: `YYYY-MM-DD`. Fleet-canonical temporal key (tc-0 § Shared Core Keys). | `"2026-06-15"` |
| `title` | string | **required** | One-line summary. Noun-phrase or imperative; brief enough to scan in a queue listing. | `"Fan-out overlap pass verifies interface presence, not correctness"` |
| `body` | string (block scalar) | **required** | Multi-line prose description. **Expressive, never flattened** — what was observed, the structural gap, any relevant prior art or context. Use `body: |` block scalar. | See example below. |
| `status` | enum (string) | **required** | Lifecycle state. **Base enum: `{open, closed, deferred}`**. No domain-extension status values for debt. See § Status enum. | `"open"` |
| `from_repo` | string | optional | Registry shortname of the originating repo. Resolved from `machine-local/registry.local.toml [repos]`. Not a URL or filesystem path. | `"coordinator-claude"` |
| `surface` | string | optional | The file, subsystem, or script the entry concerns, using path-like notation. Debt entries rarely carry this; use `source` for provenance instead. | `"bin/fan-out-dispatch.sh"` |
| `proposed_action` | string | optional (required in improvement+debt domains) | What to do about it — the remediation. Action-form: what the EM or a future executor should do. Renamed from `suggested_action`. | `"Weekly arch pass: verify fan-out dispatch spec mandates interface pin verification."` |
| `closed_at` | string (ISO date) | optional | Closure date. Set when `status: closed`. Format: `YYYY-MM-DD`. Renamed from `resolved_at`. | `"2026-06-15"` |
| `closed_by` | string | optional | Closure attribution — commit SHA preferred; prose tolerated for ported entries. Renamed from `resolution_note`. | `"1044d68c"` |
| `tags` | list of strings | optional | Free-form filter tags: system name, symptom label, domain, triage bucket. Use `tags: [weekly-arch-review]` instead of the old `open for-weekly-arch-review` status value. Renamed from off-schema `tags`. | `["weekly-arch-review", "fan-out"]` |
| `evidence` | string or list of strings | optional | Provenance: commit SHA, plan path, related entry IDs, or cross-queue references. Renamed from `cross_ref`. Note: for debt, originating-review provenance belongs in `source:` (required debt-domain field), not here. | `"BS-2026-06-14-1"` |

**Dropped field — `id`:** the filename `<date>-<slug>.yaml` is the canonical identity key (D2).
No `id:` field is written or validated. Cross-references in entry bodies that cite old `DSR-`/`CDX-`
handles stay as prose in the `evidence` field or body; the dedicated `id:` field is gone. Note:
the 5 debt files whose filenames embed the DSR prefix (e.g. `DSR-2026-06-23-1-<slug>.yaml`) are
NOT renamed — the filename remains a unique handle; only the `id:` field inside was dropped.

**Renamed fields (migration note):** old names `suggested_action`, `resolved_at`, `resolution_note`,
`cross_ref` must NOT appear as live field names. Status value `resolved` is ported to `closed`;
status value `open for-weekly-arch-review` is ported to `open` + `tags: [weekly-arch-review]`.
These old names and values may appear only in migration notes or historical comments.

---

## Domain Extension — Debt Backlog

The debt domain adds the following fields on top of the base set. Fields marked "required-in-domain"
are validated by `coordinator-queue-append --schema debt-backlog`; they are NOT base-required (the
base required-set is only `{created, title, body, status}`).

| Field | Type | Domain Req? | Semantics | Example |
|---|---|---|---|---|
| `proposed_action` | string | **required-in-domain** | See base field-set. Required here because every debt entry must state what remediation to apply. Renamed from `suggested_action`. | `"Weekly arch pass: verify fan-out dispatch spec mandates interface pin verification."` |
| `risk` | string | **required-in-domain** | Why this matters — the consequence of leaving the debt unaddressed. Answers "so what?". The only first-class "consequence" field in the queue family. | `"Wrong interface pin causes divergent executor outputs that are expensive to reconcile."` |
| `source` | string | **required-in-domain** | The originating review or observation that produced this entry. Mirrors the old table column: `daily-review/the Staff Engineer/<date>`, `codex-review-gate/<date>`, `workday-complete/step4/sonnet-observer/<date>`. Kept as a distinct required field — NOT folded into the generic optional `evidence` — to preserve debt's provenance audit discipline. | `"daily-review/the Staff Engineer/2026-06-15"` |
| `severity` | enum (string) | optional | Priority classification. Default `P2` when omitted. See § Severity enum. Most existing entries do not carry severity; omitting is valid. | `"P1"` |

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

## Severity enum (optional field)

| Value | Semantics |
|---|---|
| `P0` | Critical — active breakage or imminent data loss risk. Warrants immediate action. |
| `P1` | High — structural integrity risk, latent failure mode; address within the current or next workstream. |
| `P2` | Medium — meaningful technical debt with measurable cost; address within current quarter or a named workstream. Default when omitted. |
| `P3` | Low — cosmetic or marginal; acceptable to carry for multiple sprints. |

---

## Status enum

| Value | Semantics | Liveness |
|---|---|---|
| `open` | Active debt item, not yet scheduled or resolved. | LIVE |
| `closed` | Debt addressed. Set `closed_at` and `closed_by` when transitioning. Move to archive via `git mv`. Renamed from `resolved`. | DONE |
| `deferred` | Deliberately deferred with a named architectural reason and PM authorization. Must include a rationale in `body` naming the deferral reason. Not a default escape hatch — "not now" without a named constraint does not qualify. | BLOCKED |

**Ported-away values (migration note):** `resolved` is now `closed`; `open for-weekly-arch-review`
is now `open` + `tags: [weekly-arch-review]`. The space-bearing enum value is retired.

---

## Example entry (complete)

```yaml
created: "2026-05-27"
source: "workday-complete/step4/sonnet-observer/2026-05-27"
status: "open"
tags: ["weekly-arch-review", "fan-out"]
title: "Fan-out overlap pass verifies interface presence, not interface correctness"
body: |
  The overlap pass in fan-out-dispatch.sh verifies that a pinned interface file exists
  on disk before dispatching concurrent executors, but does not verify that the file's
  contents match what the plan asserted. Plan-time pins are not uniformly checked by
  docs-checker or prior-art-checker before concurrent dispatch proceeds. The gap is
  between "the file is there" and "the file is what the plan said it would be."
risk: >
  A wrong interface pin causes divergent executor outputs that are expensive to
  reconcile after the fact. No guard today catches pin-vs-disk mismatch before
  execution starts, so the failure mode surfaces only after wave output is assembled.
proposed_action: >
  Weekly arch pass: verify that the fan-out dispatch spec mandates interface pin
  verification (disk-confirmed content, not just file-existence) as a pre-dispatch
  gate. If verification is absent, add a docs-checker call against the pinned
  interface file to the fan-out preamble.
severity: "P2"
```

---

## Closure contract

When a debt item is resolved or explicitly deferred:

1. Set `status: closed` (or `deferred`) and fill in `closed_at` + `closed_by`.
2. Move the entry from `state/debt-backlog/<slug>.yaml` to `archive/debt-backlog/<YYYY-MM>/<slug>.yaml`
   using `git mv` — this preserves provenance in `git log` and keeps the directory clean.
3. Create the archive directory if absent: `mkdir -p archive/debt-backlog/<YYYY-MM>` before the
   `git mv`.
4. The `state/debt-backlog/` directory MUST NOT be deleted when it becomes empty after closure —
   leave the directory in place so future entries can be written without re-creating it.

The `/debt-triage` skill Step 6 handles closure mechanically; manual closure follows the same sequence.

> **Do NOT mark entries closed inline without a `git mv`.** The pruner (`/update-docs` Phase 11i)
> does not sweep `state/debt-backlog/` — but inert `status: closed` YAML files left in the open
> directory accumulate and inflate query output. `git mv` to archive is the canonical closure
> for ALL directory-form queues (debt-backlog, bug-backlog, improvement-queue) including the
> central universal improvement queue (`state/improvement-queue/`, `queue_scope: central`).

---

## Sweep-exclusion contract

`state/debt-backlog/` and `archive/debt-backlog/` are never archived by `/distill` or `/update-docs`.
Per coordinator CLAUDE.md § "state/ vs tasks/", `state/` is load-bearing substrate and survives all
automated sweeps. `archive/debt-backlog/` is the closed-entry store — closed entries are retained
for provenance, not swept. Any future sweep or archive script that encounters either path must
confirm this exclusion before acting.
