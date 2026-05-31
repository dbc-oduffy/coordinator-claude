# Completion-log release-loop

<!-- spec backlink: docs/plans/2026-05-19-completion-log-phase1-foundational-loop.md (Phase 1) -->

Per-entry queryable completion log — the substrate that connects session-end authoring to
workday clustering, workweek editorial bucketing, and merge-to-main release-note consumption.
Replaces the hand-maintained monolithic `archive/completed/YYYY-MM.md` with frontmatter-indexed
per-entry files queryable via `bin/query-completions`.

Phase 2 (LoE + handoff Session Ledger) and Phase 3 (consumer wiring) build on this substrate
without schema changes.

---

## The four-stage loop

```
session-end   →   workday-complete   →   workweek-complete   →   merge-to-main
  (write)           (cluster)              (bucket)               (release + flip)
```

**Stage 1 — session-end writes a per-entry file.**
Each `/session-end` run (Step 2.6) creates one file at
`archive/completed/YYYY-MM/YYYY-MM-DD-<chain-slug>-<sid6>.md`.
Nature is AUTO-INFERed via a small Sonnet dispatch. The entry enters with
`status: pending-release`.

**Stage 2 — workday-complete clusters by chain.**
`/workday-complete` Step 4.5 groups the day's entries by `chain:`. Chains with ≥2 entries
receive a Sonnet-authored `narrative:` field on the lead entry. Single-entry chains are
left as-is (title + body suffices). The pass is idempotent — re-running on an
already-clustered day is a no-op.

**Stage 3 — workweek-complete buckets for release.**
`/workweek-complete` Step 9 queries the past 7 days' `pending-release` entries, dispatches
a Sonnet editorial worker, and writes
`tasks/week-changelog/YYYY-MM-DD-pending-release.md` with three H2 sections:
Highlights / Notable / Other.

**Stage 4 — merge-to-main consumes and flips.**
`/merge-to-main` Step 1.5 reads the pending-release file (or falls back to an inline pass
for emergency releases), formats human-readable release notes, and after the merge commit
flips every `status: pending-release` entry to `status: released`, stamping `released_in`,
`released_at`, and `released_sha`.

---

## Schema reference

Schema lives at `coordinator/schemas/completion-entry.yaml` and is validated by
`bin/lib/schema.js` (same `loadSchemas()` loader as `handoff.yaml`).

### Required fields

| Field | Type | Notes |
|-------|------|-------|
| `title` | string | One-line past-tense description of shipped work |
| `created` | iso-date | Date of session-end authoring |
| `nature` | enum | `roadmap \| bugfix \| tech-debt \| infra` — no `other` slot by design |

### Optional fields (Phase 1)

| Field | Type | Notes |
|-------|------|-------|
| `chain` | string \| null | Plan path, handoff path, or workstream slug. Null for standalone single-session work. `/workday-complete` clusters by this value. |
| `commits` | list-of-string | Commit SHAs landing this work; may be empty if no-commit-yet |
| `status` | enum | `pending-release \| released`. Default `pending-release` on write; `/merge-to-main` flips to `released`. |
| `released_in` | string | Version tag (e.g. `v2.1.0`) — set by `/merge-to-main` |
| `released_at` | iso-date | Date of release cut |
| `released_sha` | string | Merge commit SHA on main |
| `chain_terminal` | bool | Phase 1 default: `true` on all session-end writes. Phase 2 will set `false` for mid-chain handoff ledger entries. |
| `narrative` | string | Sonnet-authored cluster summary, set by `/workday-complete` Step 4.5 on the lead entry of a multi-entry chain. |
| `nature_inferred` | bool | `true` when nature was AUTO-INFERed by Sonnet; `false` when declared via `COMPLETION_NATURE` env var. |
| `authored_by` | string | `session_id` of authoring EM — forensic only |
| `workstream` | string | Free-form slug grouping cross-chain related work; mirrors handoff schema convention |

### Phase 2 / Phase 3 forward-compat fields (shipped as slots, populated later)

| Field | Type | Notes |
|-------|------|-------|
| `loe` | object | Phase 2 populates: `agent_dispatches`, `opus_dispatches`, `em_tokens`, `tshirt` (`XS\|S\|M\|L\|XL`). Phase 1 leaves absent. |

### Example entry

```yaml
---
schema: completion-entry
title: "Add query-completions script extending query-records TYPE_TO_GLOB"
created: 2026-05-19
nature: roadmap
chain: docs/plans/2026-05-19-completion-log-phase1-foundational-loop.md
commits:
  - a1b2c3d4e5f6
  - 9f8e7d6c5b4a
status: pending-release
chain_terminal: true
nature_inferred: true
authored_by: abc123def456
workstream: completion-log-release-loop
---

Added `completion` as a new type in `query-records.js` `TYPE_TO_GLOB`, plus a
thin `query-completions.sh` wrapper. All three plan-specified query shapes
return correct results against the 3-entry fixture.
```

---

## Query primitive recipes

`bin/query-completions` is a thin wrapper over `bin/query-records --type completion`.
It globs `archive/completed/*/*.md` — the month-subdir pattern — and excludes
`archive/completed/legacy/` by glob construction.

> **Citation note (recipes below).** The recipes in this doc are written with the bare
> `query-completions` / `query-records` name for readability — they are *reference shapes*,
> not copy-paste-runnable blocks. When you put one of these in a **runnable** ceremony/skill
> block, cite the full launcher path —
> `"$HOME/.claude/plugins/coordinator-claude/coordinator/bin/query-completions.sh"` — because the
> bare extensionless name does not resolve on PATH (only `.sh`/`.js` ship; `command -v
> query-completions` is MISSING even with `bin/` on PATH). Silent-empty otherwise. See
> `docs/wiki/claude-code-platform-gotchas.md` § "Coordinator scripts are on PATH" (label-vs-executable).

**Cluster pass (workday-complete):**
```bash
query-completions --where "created=2026-05-19" --sort "chain" --format json
```

**Editorial bucketing (workweek-complete):**
```bash
query-completions --since "7d" --where "status=pending-release" --format json
```

**Release-notes consumption (merge-to-main):**
```bash
query-completions --where "status=pending-release" --sort "nature" --format markdown-list
```

**Path list for scoped git-add (merge-to-main release flip):**
```bash
ENTRY_PATHS=$(query-completions --where "status=pending-release" --format paths)
git add -- $ENTRY_PATHS archive/release-notes/<release-file>
```

The `--format markdown-list` display for type `completion` renders as:
```
- **<title>** [<nature>] (chain: <chain|none>) — <commits>
```

Phase 3 will extend the filter vocabulary (e.g. `--where "loe.tshirt=L"`).
See `bin/query-records.js` `TYPE_TO_GLOB` and `TYPE_DISPLAY` for the full
implementation shape.

---

## File layout

```
archive/completed/
  YYYY-MM/                                # per-month subdirectory
    YYYY-MM-DD-<chain-slug>-<sid6>.md     # per-entry file
  legacy/                                 # pre-migration monoliths
    2026-05.md, 2026-04.md, ...           # moved here from archive/completed/
archive/daily-summaries/                  # UNCHANGED — /workday-complete Step 4
  YYYY-MM-DD.md
tasks/week-changelog/
  YYYY-MM-DD-pending-release.md           # /workweek-complete output
archive/release-notes/
  YYYY-MM-DD-vX.Y.Z.md                   # /merge-to-main output
```

**Why month-subdir, not flat:** `archive/completed/2026-05/*.md` globs one month's
entries without filename-prefix-filtering. The month is a natural partition boundary
for parallel query workers. A flat layout would accumulate ~1000 files/year in one
directory and require prefix-filtering to scope to a month — the subdir is the
discriminating shape.

**`<sid6>` uniquifier:** the last 6 characters of `$em_sid`. Sourcing is
env-var-primary: read `$em_sid` from env if set; else `$CLAUDE_CODE_SESSION_ID`
(platform-injected, per-session, unclobberable — Claude Code ≥ ~2.1.150); else
the `.git/coordinator-sessions/.current-session-id` sentinel (last-writer-wins,
fallback for old Claude Code; written by `session-init.sh` on every SessionStart,
per `docs/wiki/claude-code-platform-gotchas.md`).
The `meta.json`-based path is circular — do NOT use it. The `<sid6>` suffix makes the
filename deterministically unique per EM session; two concurrent session-ends in the
same chain on the same day produce two distinct files, not a collision.

---

## AUTO-INFER and COMPLETION_NATURE override

Every session-end run AUTO-INFERs nature via a small Sonnet dispatch (~1KB output).
The dispatch receives: touched paths (from `touched.txt`), commit messages,
workstream-kind (plan-driven, handoff-pickup, spinoff, ad-hoc), and the chain slug.
Sonnet classifies to `[roadmap | bugfix | tech-debt | infra]` and returns a `nature:`
value + one-sentence rationale. The entry is tagged `nature_inferred: true`.

**Why AUTO-INFER, not interactive prompt:** session-end fires in autonomous execution
chains where no human EM is present to answer. Default-skip (the prior shape) produced
un-tagged entries in autonomous sessions and tagged ones in interactive sessions — a
sampling bias that pollutes `--where nature=<x>` queries that Phase 3 consumers depend on.

**Override:** set `COMPLETION_NATURE=<value>` before invoking session-end. The Sonnet
dispatch is skipped; the declared value is written with `nature_inferred: false`. Valid
values: `roadmap`, `bugfix`, `tech-debt`, `infra`.

---

## AUTO-MIGRATE behavior

`/session-end` Step 2.6 checks for a monolith at `archive/completed/YYYY-MM.md` (root
level, not under `legacy/`). If found, it idempotently runs:

```bash
git mv archive/completed/YYYY-MM.md archive/completed/legacy/YYYY-MM.md
```

before writing the per-entry file. The `git mv` is a no-op on subsequent runs (no
monolith-at-root to move). No PM action required for the mechanical move.

**Override:** set `COORDINATOR_OVERRIDE_LEGACY_MONOLITH=1` to skip the `git mv` step
(use when migration was handled manually). Documented in `docs/wiki/coordinator-tripwires.md`.

---

## Absence-as-signal doctrine for legacy entries

Legacy monoliths in `archive/completed/legacy/` are excluded from the
`bin/query-completions` glob by construction. They are not backfilled into per-entry
files automatically. Old entries are presumed minor when consumed by future systems
(Phase 3 consumers). If a specific historical entry needs promoting to the queryable
substrate, a PM or EM can hand-craft a per-entry file with `nature_inferred: false` and
the appropriate `created:` date.

**No automated retroactive backfill** — the monolith parsing complexity (unstructured
prose, inconsistent formatting across repos and time) is not worth the engineering cost
for entries that are "presence in the record" rather than "queryable signal."

---

## Migration steps for new repos

For repos that have existing `archive/completed/YYYY-MM.md` monoliths:

**Option A — AUTO-MIGRATE (recommended, zero-PM-action):**
Run any `/session-end` against the repo. Step 2.6 detects and moves all existing
monoliths to `archive/completed/legacy/` automatically before writing the first
per-entry file.

**Option B — Manual migration helper (PM-invoked):**
```bash
migrate-completion-log-legacy.sh
```
Detects all monoliths at `archive/completed/YYYY-MM.md`, moves them to
`archive/completed/legacy/` via `git mv`, and prints a summary. Idempotent —
running again when `legacy/` is already populated is a no-op.

The helper does NOT backfill per-entry files from legacy monoliths (absence-as-signal
doctrine). After migration, `bin/query-completions` will find no entries for the
legacy period — this is correct and expected.

---

## Tripwire: no monolithic completion append

A static-grep tripwire (`check-no-monolith-completion-append.sh`, registered in
`docs/wiki/coordinator-tripwires.md`) fires on any write path to
`archive/completed/YYYY-MM.md` outside `legacy/`. Contact-points: `/session-end`,
`/workday-complete`, `/update-docs`, `agents/executor.md`.

**Allowed exceptions** (excluded from grep firing):
- Paths under `archive/completed/legacy/`
- `migrate-completion-log-legacy.sh`'s own `git mv` source argument
- Docstrings and comments in `docs/wiki/` (instructional path mentions)
- `COORDINATOR_OVERRIDE_LEGACY_MONOLITH=1` override path in session-end AUTO-MIGRATE block

Call shapes covered by the tripwire: string literal, shell redirect (`>>`/`>`),
here-doc body, `tee -a`, Python/Node `open()`/`writeFileSync()`, and `git mv` source
argument. Full detail in `docs/wiki/coordinator-tripwires.md`.

---

## Cross-references

- **Handoff schema** — `coordinator/schemas/handoff.yaml`. Phase 2 extended the
  completion-entry schema with `loe:` and `chain_loe:` objects, and `chain_terminal: false`
  for mid-chain handoff ledger entries. Handoff.yaml carries a comment block documenting
  the `## Session Ledger` body convention. No frontmatter schema bump required.
- **`bin/query-records`** — the underlying query engine; completion entries are
  registered as `type=completion` in `TYPE_TO_GLOB`. All `query-records` flags
  (`--where`, `--since`, `--sort`, `--format`) work on completion entries via
  `query-completions`.
- **`docs/wiki/coordinator-tripwires.md`** — tripwire registry entry for
  `monolithic-completion-log-write-check`.
- **`docs/wiki/workday-workweek-cadence.md`** — daily/weekly ceremony context.
- **`docs/wiki/session-end-review.md`** — review marker trail that feeds
  `/workday-complete` and `/workweek-complete`.

### Phase roadmap

| Phase | Scope | Status |
|-------|-------|--------|
| Phase 1 | Foundational queryable per-entry log (this wiki) | shipped on branch |
| Phase 2 | LoE tracking + handoff Session Ledger (`chain_terminal: false` entries) | shipped on branch |
| Phase 3 | Consumer wiring: architecture-survey, bug-sweep, distill, learn-lessons, workday-start, workweek-complete, spinoff, Patrik/YK personas, debt-triage | spec complete — awaiting Phase 1 gate |

---

## Phase 2 — LoE Tracking + Handoff Session Ledger

<!-- spec backlink: docs/plans/2026-05-19-completion-log-phase2-loe-and-handoff-ledger.md -->

Phase 2 augments the substrate with two features: (a) per-session level-of-effort (LoE) data written into completion entries, and (b) a Session Ledger convention on handoffs that captures mid-chain LoE without polluting the frontmatter schema.

---

### LoE block in completion-entry.yaml

The `loe` object defined in the Phase 1 schema (§ Phase 2 / Phase 3 forward-compat fields) is now populated by `coordinator-session-loe.sh` at `/session-end` Step 2.6, immediately before the per-entry file is written.

**Schema slot** (from `coordinator/schemas/completion-entry.yaml`):

```yaml
loe:
  agent_dispatches: <int>       # total Agent tool invocations this session
  opus_dispatches: <int>        # subset where model tier was Opus
  em_tokens: <int>              # EM-side token consumption (best-effort; 0 if unavailable)
  tshirt: <XS|S|M|L|XL>        # derived t-shirt size (see sizing table below)
```

**T-shirt sizing heuristic** (implemented in `coordinator-session-loe.sh`):

| Size | Signal |
|------|--------|
| XS | 0 dispatches, session < 10 min |
| S | 1–3 dispatches OR session < 30 min |
| M | 4–10 dispatches OR 1–2 Opus dispatches |
| L | 11–25 dispatches OR 3–5 Opus dispatches |
| XL | > 25 dispatches OR > 5 Opus dispatches OR explicit chain-terminal with ≥ 6 prior S+M sessions |

The `tshirt` field is the primary consumer signal. Raw counts are forensic.

**How `loe` is populated:** `/session-end` Step 2.6 invokes `coordinator-session-loe.sh` (Phase 2 augmentation, Chunk 3) which reads session telemetry and writes the `loe:` block into the completion entry. The script is idempotent — re-running on an entry that already has `loe:` is a no-op.

---

### Session Ledger handoff convention

**Design: body, not frontmatter.** The Session Ledger lives in the handoff body under a `## Session Ledger` H2 heading — NOT as a frontmatter field. This is a deliberate design choice:

- Frontmatter fields are schema-typed and validator-enforced. Ledger entries are per-handoff accumulations written by multiple sessions; adding them to the schema would require a variable-length list type that handoff.yaml does not model.
- Body text is append-friendly. Each picking-up session appends one line to the ledger block without touching frontmatter keys or risking validator rejections.
- The schema comment in `coordinator/schemas/handoff.yaml` documents the body convention without making it a frontmatter field.

**Session Ledger body format** (within the handoff body):

```markdown
## Session Ledger

<!-- Phase 2 LoE accumulator. Each session that picks up this handoff appends one line. -->
<!-- Format: YYYY-MM-DD | <sid6> | <tshirt> | <agent_dispatches>d / <opus_dispatches>o | <one-line summary> -->

2026-05-19 | abc123 | M | 8d / 2o | Implemented query-completions + schema slot
2026-05-20 | def456 | S | 3d / 0o | Docs update + minor fix
```

**Multi-ledger handling:** a handoff chain may span multiple handoff files (each `/pickup` consumes one; `/handoff` authors the next). The Session Ledger in each handoff body accumulates only the sessions that picked up THAT handoff. Chain-terminal aggregation (see below) walks the full chain to sum across ledger blocks.

**`bin/query-records --type handoff-ledger`:** Phase 2 registers `handoff-ledger` as a query type in `bin/query-records.js TYPE_TO_GLOB` (Chunk 5), globs `tasks/handoffs/*.md` and `archive/handoffs/*.md`, and parses `## Session Ledger` blocks. Filter: `--where "tshirt=XL"`. This is the consumer path for workweek-complete's LoE high-water check.

---

### Chain-terminal aggregation via aggregate-chain-loe.sh

When a session-end closes a chain (a completion entry with `chain_terminal: true` AND a non-null `chain:`), `coordinator-session-loe.sh` invokes `aggregate-chain-loe.sh` to produce the chain-level LoE summary.

**Chain walk procedure:**

1. Resolve the chain from the completion entry's `chain:` field (plan path, handoff stem, or workstream slug).
2. Walk `archive/handoffs/` and `tasks/handoffs/` for handoffs whose `chain:` or `workstream:` matches — ordered by `created:` frontmatter date.
3. For each handoff, parse the `## Session Ledger` block (if present) and collect all ledger lines.
4. Sum `agent_dispatches`, `opus_dispatches`, and `em_tokens` across all lines.
5. Re-derive a chain-level `tshirt` from the aggregate counts using the same sizing heuristic as per-session sizing.
6. Write the aggregate summary as a `chain_loe:` block into the chain-terminal completion entry (alongside the per-session `loe:` block).

**Completion entry after chain-terminal aggregation:**

```yaml
loe:
  agent_dispatches: 8
  opus_dispatches: 2
  em_tokens: 45000
  tshirt: M

chain_loe:
  sessions: 6
  agent_dispatches: 47
  opus_dispatches: 9
  em_tokens: 210000
  tshirt: XL
```

The `chain_loe.tshirt` is the field `query-records --type completion --where "chain_terminal=true AND loe.tshirt=XL"` filters against at workweek-complete Step 8.5.

---

### Not-surveillance framing

LoE tracking is session-scoped aggregate counts, not individual tool call recordings. The data answers "how expensive was this chain of work?" — a calibration input for planning future work of similar scope — not "who called what when."

**Primary precedent:** `tasks/lessons.md` lesson at line ~361 (2026-05-18): *"Ship-and-watch telemetry needs a calendared review or it's not real."* The tier-usage telemetry lesson established that instrumentation without a concrete consumer path is ceremony. Phase 2 LoE tracking ships with a concrete consumer (workweek-complete Step 8.5 LoE high-water check) and a concrete PM-facing output (XL chain-terminal entries in the weekly summary) — not a "we'll glance if drift appears" design.

The workweek-complete Step 8.5 check is the calendared review: it fires weekly, surfaces XL chain-terminal entries to the PM, and requires an explicit "No XL chain-terminal entries this week" note when absent. The chain-terminal aggregation step closes the loop — the data is read on a known schedule, not accumulated write-only.

**What is NOT tracked:** individual tool call sequences, per-tool breakdown, inter-tool timing, or any data that would identify behavioral patterns at sub-session granularity. The unit of measurement is the session (via the ledger line) and the chain (via aggregation) — both are already meaningful planning units in the coordinator workflow.

---

### Worked examples

**Example A — Single-session XL roadmap entry.**

A single `/session-end` on a large executor-heavy session produces:

```yaml
---
title: "Implement parallel-code-review gate with 4-reviewer fanout"
created: 2026-05-19
nature: roadmap
chain: docs/plans/2026-05-19-parallel-code-review.md
status: pending-release
chain_terminal: true
loe:
  agent_dispatches: 31
  opus_dispatches: 7
  em_tokens: 95000
  tshirt: XL
---

Dispatched Patrik, Sid, security-audit-worker, and dep-cve-auditor in a
4-reviewer fanout. Integration pass by review-integrator. Gate wired into
workweek-complete Step 7. 31 agent dispatches across the session, 7 Opus.
```

This entry appears in workweek-complete Step 8.5's XL chain-terminal list.

**Example B — Chain-terminal XL aggregated from 6 S+M sessions.**

Six handoffs across two weeks, each individually M or S. The chain-terminal session-end runs `aggregate-chain-loe.sh` and produces:

```yaml
---
title: "Complete completion-log Phase 1 foundational loop"
created: 2026-05-26
nature: roadmap
chain: docs/plans/2026-05-19-completion-log-phase1-foundational-loop.md
status: pending-release
chain_terminal: true
loe:
  agent_dispatches: 6
  opus_dispatches: 1
  em_tokens: 18000
  tshirt: S                   # this session alone was small

chain_loe:
  sessions: 6
  agent_dispatches: 47
  opus_dispatches: 9
  em_tokens: 210000
  tshirt: XL                  # the chain as a whole was XL
---

Chain terminal for the 6-session completion-log Phase 1 build. Individual
sessions were M/S; the aggregate across all 6 sessions reaches XL tier.
```

The `chain_loe.tshirt: XL` is what workweek-complete Step 8.5 surfaces to the PM with the chain span ("6 sessions, 2026-05-19 to 2026-05-26").

---

### Phase 2 cross-references

- **Handoff schema** — `coordinator/schemas/handoff.yaml` carries a comment block documenting the `## Session Ledger` body convention (not a frontmatter field).
- **`bin/query-records --type handoff-ledger`** — parse Session Ledger blocks from handoff files; filter by `tshirt`, `opus_dispatches`, etc.
- **`aggregate-chain-loe.sh`** — chain-walk script invoked at session-end for `chain_terminal: true` entries.
- **`coordinator-session-loe.sh`** — per-session LoE collector; called by `/session-end` Step 2.6 (Chunk 3 augmentation).
- **`workweek-complete` Step 8.5** — LoE high-water check; mandatory before Step 9 Release Notes; surfaces XL+ chain-terminal entries to PM.

---

## Phase 3 — Consumer Wiring

<!-- spec backlink: docs/plans/2026-05-19-completion-log-phase3-consumer-wiring.md -->

Phase 3 wires the queryable completion substrate into downstream skills and personas so
that coordinators and reviewers operate on signal rather than reconstructing it from git log.
All Phase 3 changes share a single contract-coupling risk (see § Contract-coupling guard below).

### Per-skill changes

**architecture-audit / architecture-rotation:**
Score candidates by count of `nature:roadmap` entries + sum of `loe.tshirt` weights
(XS=1, S=2, M=4, L=8, XL=16), not by commit churn. Churn-based scoring conflates
active-maintenance repos with architecturally significant ones; LoE-weighted roadmap
entries capture intentional investment.

**bug-sweep:**
Hot-zone identification via:
```bash
query-completions --since "30d" --where "nature=bugfix"
```
Cooldown rule: deprioritize paths that shipped a bugfix in the last 7 days — recent
fix activity signals either a live regression loop (don't poke it without new info) or
resolved debt (don't re-fix).

**learn-lessons:**
Verify structural enforcement of a tripwire or lesson by querying:
```bash
query-completions --where "title~<tripwire-name>"
```
If an entry appears after the lesson was supposed to be codified, the enforcement is
working. If the lesson fires repeatedly with no corresponding "fix-codified" entry, the
structural fix hasn't landed.

**code-health:**
Scope to today's completion entries instead of all of HEAD:
```bash
query-completions --where "created=<today>"
```
This focuses the health pass on surfaces actually touched this session rather than
running a broad sweep over the full working tree.

**workday-start Step 1.5:**
Query recent roadmap entries to orient the session:
```bash
query-completions --since "90d" --where "nature=roadmap" --sort "-loe.tshirt" --limit 10 --format markdown-list
```
Zero-row rendering: always emit the count ("0 roadmap entries in the last 90 days") —
do not skip the step silently.

**spinoff:**
Surface related-chain discovery at spinoff-authoring time via:
```bash
query-completions --where "workstream=<slug>"
```
Gives the PM context on how much prior work exists under the same workstream slug
before authorizing a new spinoff.

**Patrik + YK personas:**
Pre-review chain query for incremental review orientation:
```bash
query-completions --where "chain=<plan-path>" --sort "created"
```
Lets the reviewer see what prior sessions shipped under the same plan before reviewing
the current diff — avoids re-litigating settled decisions.

**workweek-complete bucketing (LoE-aware):**
The editorial bucketing rules in Step 9 are extended with LoE signals. Final precedence
order (applied after Phase 2 XL chain-terminal check):

| nature | tshirt | Bucket |
|--------|--------|--------|
| roadmap | L or XL | Highlights |
| roadmap | S or M | Notable |
| roadmap | XS | Other (likely doc/spec) |
| bugfix | XL | Notable (call out explicitly) |
| bugfix | S/M/L | Other (unless user-visible) |
| tech-debt or infra | XL | Other (flag for PM awareness) |
| tech-debt or infra | XS/S/M/L | Other |

EM judgment override is always permitted. The table is a default bucketing heuristic,
not a hard rule.

**debt-triage:**
LoE-weighted prioritization: surface tech-debt and infra entries with `tshirt=XL` or
`chain_loe.tshirt=XL` as highest-priority triage candidates. High-LoE debt entries
represent the most expensive ongoing drag.

### Dropped chunk: /distill

`/distill` is implemented in `commands/distill.md` + `pipelines/artifact-distillation/PIPELINE.md`
— no `skills/distill/SKILL.md` exists. Phase 3's original Chunk 3 assumed a skill insertion point.
Phase 0 of the distill pipeline reads raw artifact files directly, not via query primitive; adding
`query-completions` would be structurally redundant. **Resolution: Chunk 3 dropped from Phase 3 slate.**
This is an oracle-was-wrong resolution, not an appetite-based deferral.

### Cross-repo query recipe

When a Phase 3 consumer needs to query completion entries across sibling repos registered in
`tasks/repo-registry.md`, DO NOT use `yq` to parse the registry. The registry is markdown
with YAML-list blocks inside HTML comment sentinels — it is not a top-level YAML document,
and `yq` is not in the coreutils dependency surface (DR-016).

Correct parsing pattern:
```bash
awk '/<!-- BEGIN repo-registry -->/,/<!-- END repo-registry -->/' tasks/repo-registry.md \
  | grep -E '^\s*path:' \
  | awk '{print $2}'
```

Then iterate paths and invoke `query-completions` with `--root <path>` in each sibling repo.

### Contract-coupling guard

All Phase 3 chunks depend on the query-completions flag surface shipped by Phase 1:
`--where`, `--since`, `--sort`, `--limit`, `--format` (accepting `json` and `markdown-list`).

**Before dispatching any Phase 3 executor:** verify Phase 1's actual delivered flag surface
against the assumed shape above. If Phase 1 shipped a different flag name or omitted a flag,
all consumer chunks must be re-targeted as a single coordinated edit pass — per-chunk drift
would produce an inconsistent query interface across consumer skills. A partial re-target
(fixing some skills but not others) is worse than the original inconsistency.

---

## Version Bumps Communicate User-Noticeable Change — One Bump Per Release

*Source: project-rag-ue-addon, 2026-05-29. [universal]*

A version bump is a user-facing signal: "something you'd notice has changed." When multiple user-visible changes accumulate across sessions before a release, the correct posture is ONE version bump that covers the full delta since the last user-visible release — not a bump per session or per feature. Multiple micro-bumps for a single release window dilute the signal and make changelogs noisy.

**Rule.** Before bumping the version at `/workweek-complete`, query `pending-release` completion entries to enumerate the full delta since the last released version. The bump communicates the user-noticeable surface of ALL those entries together, not just the current session's work. If the delta is entirely infra/tech-debt with no user-visible change, consider whether a version bump is warranted at all — or hold until a user-visible change is included. Composes with the four-stage loop: Stage 4 (`/merge-to-main`) is the natural version-bump gate because it represents the full delta being released, not an intermediate session.

## track-dispatched-agents.sh dedup fix

<!-- spec backlink: docs/plans/2026-05-19-completion-log-phase2-loe-and-handoff-ledger.md -->

The dispatched-agents tracker file uses tab-delimited records in Phase 2:
```
<agentId>\t<model>\t<subagent_type>
```

Legacy 1-column records (bare agentId, no tabs) are treated as `model: unknown → Sonnet`
(conservative default). The dedup guard MUST compare on column 1 only:

```bash
cut -f1 "$DISPATCHED" | grep -qxF "$AGENT_ID"
```

**Why:** bare `grep -qxF "$AGENT_ID"` on tab-delimited lines always mismatches against
tab-appended records, causing unbounded re-append of the same agent — inflating
`agent_dispatches` counts and corrupting the LoE t-shirt derivation. The column-1-only
comparison handles both legacy bare-agentId records and new tab-delimited records uniformly.
