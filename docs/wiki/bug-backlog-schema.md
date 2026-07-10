---
title: "Bug-Backlog — Per-Entry YAML Schema"
kind: wiki
audience: coordinator-em
created: 2026-06-15
last-updated: 2026-06-25
system: bug-sweep
---

# Bug-Backlog Schema

<!-- Spec backlink: archive/specs/2026-06/2026-06-15-structured-queue-medium-rollout.md § C2 -->
<!-- Spec backlink: docs/plans/2026-06-25-example-initiative-tc-2-queues-lessons-consolidation.md § D1 (unified base+extension shape) -->

<!-- Negative-spec: Post-2026-06-15 migration, the authoritative store is the per-entry YAML
     directory `state/bug-backlog/*.yaml`. The legacy `state/bug-backlog.md` was a migrated
     placeholder header that has been swept by tc-2 / C7; reading it for live bug data returns
     nothing. This schema defines the per-entry YAML contract that the directory form implements.
     Do NOT add an `id:` field to bug entries — the filename (<date>-<slug>.yaml) is the canonical
     handle (D2). Do NOT use `system:` as the field name for the affected surface — the canonical
     name is `surface:` (renamed from `system`). Do NOT use `cross_ref:` — the canonical name is
     `evidence:`. Do NOT add a stored `lifecycle:` or `live:` frontmatter field — liveness is
     DERIVED at query time from `status` (tc-0 negative-spec).
     Tombstone: state/bug-backlog.md was a migrated placeholder swept by tc-2 / C7. -->

The bug backlog is a **directory of per-entry YAML files** at `state/bug-backlog/<date>-<slug>.yaml`
with the field contract defined here. Each YAML file is one bug entry. The bug-sweep skill
(`skills/bug-sweep/`) populates this backlog via `coordinator-queue-append --schema bug-backlog`;
`/debt-triage` may migrate entries to `state/debt-backlog/` when scope warrants. Closure is via
`git mv state/bug-backlog/<slug>.yaml archive/bug-backlog/<YYYY-MM>/<slug>.yaml` with
`status: closed`, `closed_at:`, `closed_by:` set. The filename `<date>-<slug>.yaml` is the
canonical identity key — no separate `id:` field.

---

## Base Field-Set (shared by all three queue schemas)

> The improvement-queue, bug-backlog, and debt-backlog share a common base field-set. The
> required-set is the small intersection every queue satisfies on disk. Additional fields are
> base-optional and required only within the domain extension that already carries them.
> This section is authoritative and near-identical in all three schema wikis.

| Field | Type | Base Req? | Semantics | Example |
|---|---|---|---|---|
| `created` | string (ISO date) | **required** | Date of entry creation. Format: `YYYY-MM-DD`. Fleet-canonical temporal key (tc-0 § Shared Core Keys). | `"2026-06-14"` |
| `title` | string | **required** | One-line summary. Noun-phrase or imperative; brief enough to scan in a queue listing. | `"publish.sh Phase 4 personal-data audit skips unchanged files"` |
| `body` | string (block scalar) | **required** | Multi-line prose description. **Expressive, never flattened** — include root cause if known; omit speculation. Use `body: |` block scalar. | See example below. |
| `status` | enum (string) | **required** | Lifecycle state. **Base enum: `{open, closed, deferred}`**. Bug domain adds `wontfix`. See § Status enum. | `"open"` |
| `from_repo` | string | optional | Registry shortname of the originating repo. Resolved from `machine-local/registry.local.toml [repos]`. Not a URL or filesystem path. | `"coordinator-claude"` |
| `surface` | string | optional (required in bug+improvement domains) | The file, subsystem, or script the entry concerns, using path-like notation. Renamed from `system` (bug). | `"setup/publish"` |
| `proposed_action` | string | optional | What to do about it — the remediation or fix target. Bug entries rarely carry this; use `why_blocked` for blockers instead. Renamed from off-schema `recommended_fix`. | `"Add --full-audit flag to rescan all destination files"` |
| `closed_at` | string (ISO date) | optional | Closure date. Set when `status: closed` or `wontfix`. Format: `YYYY-MM-DD`. | `"2026-06-15"` |
| `closed_by` | string | optional | Closure attribution — commit SHA preferred. | `"8eed9572"` |
| `tags` | list of strings | optional | Free-form filter tags: system name, symptom label, domain, triage bucket. | `["publish", "audit", "data-loss"]` |
| `evidence` | string or list of strings | optional | Provenance: commit SHA, plan path, related entry IDs, or cross-queue references. Renamed from `cross_ref`. | `"setup/publish.sh:904-983"` |

**Dropped field — `id`:** the filename `<date>-<slug>.yaml` is the canonical identity key (D2).
No `id:` field is written or validated. Cross-references in entry bodies that cite old `BS-`
handles stay as prose in the `evidence` field; the dedicated `id:` field is gone.

**Renamed fields (migration note):** old names `system`, `cross_ref`, `recommended_fix` must NOT
appear as live field names. They may appear only in migration notes or historical comments.

---

## Domain Extension — Bug Backlog

The bug domain adds the following fields on top of the base set. Fields marked "required-in-domain"
are validated by `coordinator-queue-append --schema bug-backlog`; they are NOT base-required (the
base required-set is only `{created, title, body, status}`).

| Field | Type | Domain Req? | Semantics | Example |
|---|---|---|---|---|
| `surface` | string | **required-in-domain** | See base field-set. Required here because every bug must name the affected subsystem. Renamed from `system`. | `"setup/publish"` |
| `severity` | enum (string) | **required-in-domain** | Priority classification. See § Severity enum. | `"P1"` |
| `why_blocked` | string | optional | Why the bug is parked in the backlog rather than fixed now. Typical blockers: requires PM design decision, awaits infra, cross-repo fix-locus. Omit if the bug is unblocked (waiting on capacity only). | `"Design decision required: accept scope limitation OR add --full-audit mode."` |
| `repro_steps` | string | optional | Steps to reproduce, if non-trivial. Omit for bugs that are self-evident from the description. | `"Run publish.sh, modify a file, re-run — unchanged file not re-audited."` |
| `environment` | string | optional | Platform or session constraint where the bug manifests, if not universal. | `"Windows Git-Bash only"` |

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

## Severity enum

| Value | Semantics |
|---|---|
| `P0` | Data-loss, boots-broken, or correctness defect with no workaround that blocks primary workflows. Requires immediate fix before next commit. |
| `P1` | Correctness defect; a workaround exists or the blast radius is bounded. Fix this sweep. |
| `P2` | Quality or UX issue; does not block work. Fix at next convenient sweep or session. |
| `P3` | Minor or cosmetic. Fix opportunistically or defer indefinitely. |

---

## Status enum

| Value | Semantics | Liveness |
|---|---|---|
| `open` | Entry is actionable and not yet worked. Default on admission. | LIVE |
| `closed` | Fix landed; `closed_at` and `closed_by` set. Move to archive via `git mv`. | DONE |
| `wontfix` | PM decision: not worth fixing; documented reason in `why_blocked`. Move to archive. | DONE |
| `deferred` | Scope too large for current backlog; candidate for `/debt-triage` migration. | BLOCKED |

Status lifecycle:

```
open  →  closed    (fix landed, closed_by SHA recorded)
open  →  wontfix   (PM decision: not worth fixing, documented reason in why_blocked)
open  →  deferred  (scope too large; candidate for /debt-triage migration)
```

`closed` and `wontfix` entries close via `git mv state/bug-backlog/<slug>.yaml
archive/bug-backlog/<YYYY-MM>/<slug>.yaml` with `status:`, `closed_at:`, `closed_by:` set.
`deferred` entries graduate to `state/debt-backlog/` via `/debt-triage` (capture via
`coordinator-queue-append --schema debt-backlog`, then `git mv` the source bug YAML to archive).

---

## Example entry (complete)

```yaml
created: "2026-06-14"
surface: "setup/publish"
severity: "P1"
status: "open"
title: "publish.sh Phase 4 personal-data audit skips unchanged files"
body: |
  publish.sh Phase 4 audit only covers newly-synced files (AUDIT_FILES populated
  by NEW/UPDATE rows only). Files unchanged since initial sync are never re-audited.
  Improved per-file detection via 8eed9572 (cross-platform home-path audit) does
  not close this structural gap.
why_blocked: >
  Design decision required: accept the scope as a documented limitation OR add a
  --full-audit mode that rescans the entire destination tree. Cannot pick
  unambiguously without PM direction.
evidence: "setup/publish.sh:904-983"
```

---

## Sweep-exclusion contract

`state/bug-backlog/` (directory) and `archive/bug-backlog/` are **never archived** by `/distill` or
`/update-docs`. Per coordinator CLAUDE.md § "state/ vs tasks/", `state/` is load-bearing
substrate — surgical and named sweeps only. These paths are named here explicitly for
greppability. Any future sweep or archive script that encounters `bug-backlog` must confirm
this exclusion before acting.

The `archive/bug-backlog/` path similarly holds historical sweep artifacts and is not a
`/distill` target — it is managed by the bug-sweep skill, not the knowledge archival pipeline.
