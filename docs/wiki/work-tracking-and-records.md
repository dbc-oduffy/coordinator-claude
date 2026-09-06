# Work Tracking and Records

<!-- distilled: run 2026-07-19-synth; sources: 2026-05-29-handoff-tracker-system.md, archive/specs/2026-05/2026-05-19-completion-log-phase1-foundational-loop.md, archive/specs/2026-05/2026-05-19-completion-log-phase2-loe-and-handoff-ledger.md, archive/specs/2026-05/2026-05-19-completion-log-phase3-consumer-wiring.md, archive/specs/2026-05/2026-05-06-phase-e-learn-lessons.md -->

How handoffs, completion logs, and level-of-effort (LoE) records are schematized, written, queried, and consumed across the fleet — the durable-records layer underneath session handoffs and workweek rollups.

## Overview

Three related record systems share this domain:

1. **Handoff lifecycle** — `deployment_state` state for in-flight work, queried live via `bin/query-records` (no rendered tracker), auto-archived on completion.
2. **Completion log** — per-entry archival records of finished work, queryable, feeding 11 downstream consumers.
3. **LoE ledger** — session-effort accounting embedded in handoffs, aggregated at chain-terminal, reviewed weekly (not surveilled continuously).

All three are designed around the same principle: **write once at the natural authoring point, read via a uniform query layer, never require a human to manually reconcile state.**

## Key Decisions

### Handoff lifecycle and schema

<!-- src: plan13-016, plan13-017, plan13-019 -->

- The status dimension for a handoff is the `deployment_state` enum: `awaiting_gate | ready_to_fire | in_flight | shipped | continued | closed`. Query results built from this field are **not terminal by design** — do not invent a parallel status field alongside it.
- Auto-archival is covered by four idempotent surfaces, each independently sufficient: handoff chain-archival, session-end Step 2.7 (on `claimed_by`/`consumed_by` match — DR-084 renamed the field, corpus mixed, check both), session-init boot sweep, and `/update-docs` supersession (with a 24h mtime veto to avoid archiving something mid-edit). Canonical archive dir: `archive/handoffs/`.
- Schema additions: `category` (enum: `roadmap|infra|bug|docs|research|refactor`) and `summary` (≤120 chars). Memos use `--type cross-repo-memo` plus `summary`. Chain-point granularity is **workstream-count**, not ticket-count.
- State lives per-repo in `state/handoffs/*.md` frontmatter, queried live via `bin/query-records` (no rendered tracker artifact). Daily rollup view = handoffs/spinoffs/memos; weekly rollup view = plans (explicitly out of scope for the daily query).
- Lineage: `predecessor:` field is effectively dead (one exception found across three repos audited). The real continuity signal is the `workstream:` slug, not a predecessor chain. A separate roadmap ticket DAG (`tc_id`/`blocks`/`blocked_by`/`roadmap_id`/`sprint`/`wave`/`cost`) exists but is `kind:spinoff-roadmap-only` — the schema validator rejects those fields on any other `kind`. Treat the ticket DAG as an optional addon column, not the primary chain-continuity mechanism.

### Handoff completion semantics

<!-- src: plan13-018 -->

`applyConsumedMarker` (in `query-records.js:371`) normalizes a handoff body containing `<!-- consumed: … -->` to `status:consumed` / `deployment_state:shipped` **at read time**. This means completion-pruning is inherited for free by any consumer of the query layer — completed items simply stop appearing in query results without a separate archival write being required for that specific visibility guarantee.

### Completion log schema and filing

<!-- src: plan08-027, plan08-029 -->

- Per-entry completion files live at `archive/completed/YYYY-MM/YYYY-MM-DD-<chain-slug>-<sid6>.md` — one file per completed unit of work, not a monolithic per-month log.
- Required frontmatter: `title`, `created`, `nature` (`roadmap|bugfix|tech-debt|infra`). Optional: `chain`, `commits`, `status`, `released_*`, and (Phase 2) `loe`.
- Legacy entries are quarantined at `archive/completed/legacy/` and excluded from query results.
- Filename collision avoidance: the `<sid6>` suffix is the last 6 characters of `$em_sid`, resolved env-only: `$em_sid` from env if set, else `$CLAUDE_CODE_SESSION_ID`. This makes per-entry filenames deterministically unique per EM session with no race condition — two concurrent session-ends on the same chain/day still produce distinct files.

### Nature inference (avoiding sampling bias)

<!-- src: plan08-028 -->

At session-end, `nature` is auto-inferred via a small Sonnet dispatch (~1KB payload: touched paths, commit messages, workstream-kind, chain slug). The result is tagged `nature_inferred:true`. An EM can override via the `COMPLETION_NATURE` env var. This exists specifically to remove sampling bias that would otherwise creep into autonomous/unattended chains where no human is present to classify the work.

### Legacy monolith migration

<!-- src: plan08-030, plan08-033 -->

- Session-end auto-migrates: if `archive/completed/YYYY-MM.md` exists at repo root, it is idempotently `git mv`'d to `archive/completed/legacy/YYYY-MM.md` before the next per-entry write happens. `COORDINATOR_OVERRIDE_LEGACY_MONOLITH=1` skips this. Fully mechanical — no human judgment needed.
- **No retroactive backfill** of legacy monoliths into the new per-entry schema. Legacy entries lack `nature:` tags because original-author attribution is unavailable after the fact. This is treated as absence-as-signal (presumed minor work) rather than a data-completeness bug — legacy entries remain searchable forensically as-is. A PM may hand-cleanup specific entries if a strong reason emerges, but it's not a default obligation.

### Query interface

<!-- src: plan08-031, plan08-041 -->

- `query-completions` is an **extension** of `query-records.js`, not a standalone tool: it adds `completion: archive/completed/*/*.md` to `TYPE_TO_GLOB` plus a thin bash wrapper. This keeps the query substrate uniform rather than introducing parallel doctrine.
- The plaintext-only-output rule is scoped to the `bin/standup` family specifically — it does **not** apply to `query-records`, which may format output (e.g. markdown-list) for other consumers.
- Cross-repo query pattern: extract from markdown YAML-list blocks wrapped in HTML comment sentinels via awk/grep, per-repo: `query-completions --since 7d --where 'nature=roadmap' --format markdown-list` — gives a one-screen view of sibling-repo roadmap activity without a dedicated cross-repo index.

### LoE (level-of-effort) tracking

<!-- src: plan08-034, plan08-035, plan08-036, plan08-037, plan08-038 -->

- **LoE is explicitly not surveillance telemetry.** It is authored at session-end by the EM, consumed by the EM of the following week, and aggregated at chain-terminal as part of normal workflow — the calendar review is structurally built into the consumption loop, not bolted on. This is a deliberate contrast with the tier-usage tracking pattern, which was ship-and-watch with no scheduled review point.
- Session LoE measurement: `agent_dispatches` (line count in `dispatched-agents.txt`), `opus_dispatches` (subset matching `model=opus*`), `em_tokens` (best-effort from `CLAUDE_SESSION_*`/`OUTPUT_TOKENS` env vars, degrades to `null` if absent). A T-shirt size (XS/S/M/L/XL/XXL) is assigned via a threshold table — the **highest tier where ≥1 criterion is met** wins (not majority-vote across criteria).
- Handoffs carry a mandatory `## Session Ledger` markdown table (not frontmatter — deliberately visible/editable prose) with: `agent_dispatches`, `opus_dispatches`, `em_tokens`, `tshirt`, `commits`, `session_id`, `created`. Idempotent re-pickup of a handoff **appends a new ledger block** rather than overwriting — multiple ledger blocks on one handoff means multiple sessions touched it.
- claude-klabauter `coordinator/bin/aggregate-chain-loe.py` walks the `predecessor:` chain from a terminal handoff backward, reading both `tasks/handoffs/` and `tasks/handoffs/archive/**/`. It maintains a visited-set as a cycle guard, parses *all* Session Ledger blocks per handoff (N blocks → N records), and dedupes on `session_id`. Degrades gracefully on missing/malformed data.
- `workweek-complete` Step 9 runs a **mandatory** (not optional) LoE high-water check: queries `chain_terminal=true AND loe.tshirt IN (XL, XXL)` and surfaces any XL+ entries to the PM. Making this step mandatory is what satisfies the not-surveillance framing in practice — there's a fixed, predictable review cadence rather than continuous background monitoring.

### Completion-log consumer wiring

<!-- src: plan08-039, plan08-040, plan08-042 -->

- Phase 3 wired the completion-log query into 11 downstream consumers: `architecture-audit` (roadmap count + LoE), `bug-sweep` (hot-zone detection), `learn-lessons` (enforcement), `code-health` (scope), `workday-start` (orientation), `spinoff` (related-chain lookup), reviews (pre-flight context), `repo-registry` (cross-repo view), `workweek-complete` (bucketing), `debt-triage` (prioritization) — plus the query interface itself.
- `/distill` consumer wiring was **explicitly dropped** — "oracle was wrong." There is no natural insertion point in the distill pipeline: Phase 0 of distill reads raw artifact files directly, not via the query layer, and adding a query call there would be redundant. (AC-12 in the source plan was updated from 11 to 10 chunks to reflect the drop.)
- UI consistency rule: consumer sections (`workday-start` Step 1.5, project-onboarding) render a **fixed subsection heading even when the query returns zero rows** — zero rows render as `(none)`, the section is never simply absent. This follows the count-always pattern from orientation-surfacing-doctrine — a missing section reads as "not implemented," a `(none)` section reads as "checked, nothing found."

### Write-surface coverage discipline

<!-- src: plan08-032 -->

When retiring a monolithic write pattern, enumerate every write surface explicitly rather than assuming a single choke point. The completion-log migration required covering six total surfaces: three in the main chunk plus three more found in a follow-up sweep (`executor.md` Archive Fallback, `tracker-maintenance.md` Step 2, `workday-start.md` Step 1.4). A tripwire enforces that no surface regresses back to monolith writes.

## Reference — Improvement Queue Schema

<!-- src: plan04-013 -->

Row shape for the improvement-queue record type:

```
YYYY-MM-DD | source-repo | source-file:line | one-line lesson | proposed target
recurring: 0
resolution: pending | in_progress | resolved (YYYY-MM-DD commit | plan)
```

## Gotchas

- Don't add a second status/state field alongside `deployment_state` on handoffs — it already covers the lifecycle; a parallel field is the most common schema-drift mistake here (plan13-016).
- Don't treat `predecessor:` as the source of chain truth for handoffs — it's dead on nearly every live file. Use `workstream:` slug instead (plan13-019).
- Don't try to backfill `nature:` on legacy completion entries — the attribution data doesn't exist, and it's not required (plan08-033).
- LoE data is for the weekly consumption loop, not a dashboard to check ad hoc — building continuous-monitoring tooling on top of it would reintroduce the surveillance framing it was deliberately designed to avoid (plan08-034).
