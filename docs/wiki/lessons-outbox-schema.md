---
title: "Lessons Outbox — Per-Entry YAML Schema"
kind: wiki
audience: coordinator-em
created: 2026-06-15
last-updated: 2026-07-21
system: learn-lessons
---

# Lessons Outbox Schema

<!-- distilled: run 2026-07-19-synth; sources: archive/specs/2026-06/2026-06-30-lesson-structured-facets-and-emit-metadata-fix.md, archive/specs/2026-06/cockpit-contract-ext-research-corpus/central-queue-restructure.md, archive/specs/2026-06/cockpit-contract-ext-research-corpus/lessons-structuring.md, 2026-05-05-lesson-triage-skill.md -->

<!-- Spec backlink: archive/specs/2026-06/2026-06-15-universal-lesson-routing-mechanical-capture.md § C2 -->
<!-- Spec backlink: cross-repo/archive/2026-07-21-example-cockpit-repo-em-change-kind-enum-lacks-app-source-token.md,
     cross-repo/archive/2026-07-17-claude-klabauter-em-plan-tasks-change-kind-lacks-engine-code-member.md
     (code-edit member added — Option 1 from the claude-klabauter proposal, routes to improvement-queue
     project tier alongside script-edit; cockpit's app-source-token ask resolved by the same member) -->
<!-- Spec backlink: cross-repo/archive/2026-07-29-project-rag-em-three-quiet-failure-modes-in-ceremony-clis.md
     (verification member added — a PM-ratified, hardware-gated follow-on had no routable kind and the
     harvest dropped it on exit 0; the coined `script-port` token was NOT admitted, see § Change-kind enum) -->
<!-- Spec backlink: state/lessons-outbox/2026-07-23T09-33-05-00-00-universal-plan-tasks-change-kind-enum-ha-884866e48d83.yaml
     (config-edit member added — same shape as the code-edit precedent: two independent plan
     task-spine rows edited ignore-rules/settings/per-machine config, no existing member named it,
     and forcing them into an adjacent value would have discarded the author's own classification.
     Routes to improvement-queue project tier alongside script-edit/code-edit.) -->
<!-- Negative-spec: The pre-plan approach of appending [universal] lessons to state/improvement-queue.md is REPLACED by this outbox for central-wiki-target entries. improvement-queue.md remains valid only for project-specific entries. -->

The lessons outbox is a per-entry YAML store at `state/lessons-outbox/<ISO-ts>-<slug>.yaml`
inside each peer repo. Each file represents one lesson ready for DoE-side drain. Entries are
produced mechanically by the claude-klabauter `coordinator/bin/coordinator-lesson-promote` CLI (invoked from
`/learn-lessons` local-mode when a `[universal]` entry has a resolved central-wiki target).
The DoE session consumes the outbox during `/learn-lessons --central` drain and moves drained
entries to `state/lessons-outbox/drained/` as the writeback step. Every peer repo manages its
own outbox; the DoE machine reads across all registered peers via
`~/.claude/machine-local/registry.local.toml`.

---

## Schema (required fields)

| Field | Type | Required | Semantics | Example |
|---|---|---|---|---|
| `id` | string (uuid4) | required | Machine-generated unique identifier. Produced by the CLI at write time; never set manually. | `"a3f2c1d0-4e5b-7f8a-9b0c-1d2e3f4a5b6c"` |
| `created` | string (ISO 8601 UTC) | required | Timestamp of entry creation. Produced by the CLI; never set manually. Format: `YYYY-MM-DDTHH:MM:SSZ`. | `"2026-06-15T14:32:07Z"` |
| `from_repo` | string | required | Registry shortname of the originating repo, resolved from `machine-local/registry.local.toml` `[repos]` table using the cwd git-root match. Not a URL or filesystem path — the short identifier as registered (e.g. `example-repo`, `example-sim-repo`). | `"example-repo"` |
| `title` | string | required | Human-readable lesson title. Same text as the `title:` field on the source `state/lessons/<slug>.yaml` entry. Brief, noun-phrase form. | `"Drain-branch must cut from peer main, not active workstream"` |
| `body` | string | required | Prose explanation of the lesson. Multi-line allowed. "Just enough structure" — a paragraph or two; not a wiki article. The DoE apply step uses this as the raw content for the wiki patch. | `"When the DoE drain step creates a branch on a peer repo, it must cut from the peer's main rather than the current workstream branch. Cutting from the workstream silently entangles unrelated work into the drain commit."` |
| `change_kind` | enum (string) | required | Classification of the target change. Drives apply dispatch in `/learn-lessons --central`. **See § Change-kind enum — this field's closed enum is defined there.** | `"wiki-append"` |
| `target_wiki` | string | required | Named central wiki path under `~/.claude/docs/wiki/<name>.md`, or the literal string `unknown` when the classifier could not resolve a target. The DoE apply step rejects `unknown` entries and queues them for manual triage. | `"docs/wiki/learn-lessons-routing.md"` or `"unknown"` |
| `scope_tags` | list of strings | optional | Free-form tags for filtering and priority. Convention: repo shortname, system name, or symptom label. | `["drain", "cross-repo", "state"]` |
| `evidence` | string or list of strings | optional | Commit SHA, plan path, or lesson-source reference — the per-entry `state/lessons/<slug>.yaml` filename for post-migration captures, or a legacy `state/lessons.md:<N>` line reference on pre-migration entries — that motivated this entry. Used by the DoE apply step for provenance annotation. | `"76130204"` or `["76130204", "docs/plans/2026-06-15-universal-lesson-routing-mechanical-capture.md"]` |
| `trigger` | string | optional | The precondition or symptom under which the lesson fires. Author-supplied at capture only — see § Structured facets (anti-fabrication). | `"drain step invoked from a non-main branch"` |
| `why` | string | optional | The rationale behind the lesson. Author-supplied at capture only. | `"cutting from workstream entangles unrelated work into the drain commit"` |
| `how_to_apply` | string | optional | The corrective action. Author-supplied at capture only. | `"cut the drain branch from peer main, never from the active workstream branch"` |

> **Forward-seam note (post-migration capture):** When a lesson captured post-migration is promoted here, the `evidence` value naturally evolves from a `state/lessons.md:<N>` line reference to the per-entry filename (`state/lessons/<slug>.yaml`).

> **Metadata honesty.** `created` and `from_repo` are emitted as real, non-null values at capture time — not placeholders. If a downstream consumer (e.g. Cockpit date-bounded queries) needs to exclude entries on a promotion-state basis to dodge a null-`created` case, that is a signal the emitter regressed; re-verify against claude-klabauter `coordinator-queue-append` before adding query-side workarounds. <!-- src: plan31-007 -->

### Example entry (complete)

```yaml
id: "a3f2c1d0-4e5b-7f8a-9b0c-1d2e3f4a5b6c"
created: "2026-06-15T14:32:07Z"
from_repo: "example-repo"
title: "Drain-branch must cut from peer main, not active workstream"
body: |
  When the DoE drain step creates a branch on a peer repo, it must cut from
  the peer's main rather than the current workstream branch. Cutting from the
  workstream silently entangles unrelated work into the drain commit and
  makes the drain branch non-mergeable without resolving unrelated conflicts.
change_kind: "wiki-append"
target_wiki: "docs/wiki/learn-lessons-routing.md"
scope_tags: ["drain", "cross-repo"]
evidence: "76130204"
```

---

## Structured facets (trigger / why / how_to_apply)

<!-- src: plan31-008, plan31-009, plan31-010 -->

The three optional facet fields (`trigger`, `why`, `how_to_apply` — see § Schema above) are
**author-supplied at capture only**. They are populated via explicit `--trigger`/`--why`/
`--how-to-apply` flags on claude-klabauter `coordinator-queue-append` at the moment a lesson is first written to
`state/lessons/<slug>.yaml` (the per-entry capture surface upstream of this outbox), not
retrofitted onto the outbox entry during promotion.

**Anti-fabrication prohibition:** facets must NEVER be post-hoc LLM-extracted from existing
prose. An absent flag means the field is absent on the record — honest non-coverage, consistent
with how the rest of the optional field set behaves — not a value inferred from the `body` text
after the fact. This prohibition is also codified in `skills/learn-lessons/SKILL.md`; if you are
editing that skill's facet-handling section, this paragraph is the source of truth to cite.

Each captured lesson also carries a ccos-3 `system` provenance block plus a real `created`
timestamp, both emitted by `coordinator-queue-append` (schema-agnostic — the same emission path
serves `state/lessons/`, `state/lessons-outbox/`, and the improvement/debt/bug queues).

---

## Change-kind enum

<!-- This section is the SINGLE AUTHORITATIVE DEFINITION of the change_kind enum.
     The CLI (claude-klabauter coordinator/bin/coordinator-lesson-promote) and learn-lessons-routing.md § Change-Kind Taxonomy
     both REFERENCE this section rather than defining the enum inline.
     Do NOT duplicate the enum values in those files — point here instead. -->

**Implementation-token convention.** The problem-set at
`docs/problems/2026-06-15-universal-lesson-routing-mechanical-capture.md` used short-form names
(`agent-prompt`, `hook`, `skill`) during PM-EM problem-shape convergence; the implementation
refined to long-form names (`agent-prompt-edit`, `hook-edit`, `skill-edit`) at plan-time per
The Director of Engineering review F6 (single-source-of-truth alignment). This schema doc is the canonical enum; the
CLI (`coordinator-lesson-promote`) validates against the values listed here. The problem-set
stays frozen as the PM-ratified oracle — future readers landing there should consult this doc
for the enum-implementation tokens.

| Value | Semantics | Example |
|---|---|---|
| `doctrine-edit` | A CLAUDE.md body change or a doctrine-altitude wiki change that elevates to CLAUDE.md. Applies when the lesson represents a cross-cutting operating rule, not domain-specific guidance. | Adding the "drain-branch-from-main" rule to coordinator CLAUDE.md § DoE drain. |
| `agent-prompt-edit` | A change to an agent prompt body (files under `agents/`). Applies when the lesson refines how a named agent reasons or what it checks. | Adding a portability-lens row to `agents/code-reviewer.md`. |
| `hook-edit` | A change to a hook script — any `.sh`, `.py`, or `.ps1` file under `hooks/`. Applies when the lesson identifies a missing guard, wrong trigger, or silent failure in a hook. | Adding a `[doe-state-drain]` commit-prefix guard to `hooks/pre-commit`. |
| `script-edit` | A change to a `bin/` utility script that is not a hook. Applies when the lesson identifies a bug, missing flag, or wrong default in a CLI tool. | Fixing claude-klabauter `coordinator/bin/coordinator-lesson-promote` to reject `from_repo: unknown`. |
| `snippet-sync-update` | A snippet body change that requires `bin/verify-<name>-sync.sh --fix` after editing. Applies when the lesson identifies a stale or incorrect snippet that propagates into prompts via sync. | Updating `snippets/drain-preamble.md` and re-running `bin/verify-snippet-sync drain-preamble --fix`. |
| `wiki-new` | A new wiki file under `docs/wiki/`. Applies when the lesson introduces a concept or subsystem that has no existing wiki home. | Creating `docs/wiki/lessons-outbox-schema.md` (this file). |
| `wiki-append` | An append to an existing wiki section. The most common value — use this when the lesson adds a row, paragraph, or named exception to an existing wiki. | Appending a drain-writeback note to `docs/wiki/learn-lessons-routing.md § Change-Kind Taxonomy`. |
| `skill-edit` | A `SKILL.md` body edit. Use when the lesson identifies a missing step, wrong gate, or incorrect procedure in a skill. Previously folded into `wiki-append`; promoted to a distinct value because skill body edits have a different apply path (executor reads current line ranges before patching). | Adding the peer-repo skip-with-warning step to `skills/learn-lessons/SKILL.md` Phase 2.6. |
| `doc-edit` | A change to project-local documentation (README, `docs/README.md`, CONTEXT.md, or similar non-wiki doc surfaces) that is not itself a wiki file. Routes to the **improvement-queue** (project tier), NOT the lessons outbox — `coordinator-lesson-promote` does not accept this value; it is listed here only so this table's enumeration is the complete universal union the task-spine schema's WIDER UNIVERSAL enum cites. | Fixing a stale command name in a repo's `README.md`. |
| `test-edit` | A change to a test file (adding, fixing, or hardening a test) that is not itself a hook/script/agent-prompt edit. Routes to the **improvement-queue** (project tier), NOT the lessons outbox — `coordinator-lesson-promote` does not accept this value; it is listed here only so this table's enumeration is the complete universal union the task-spine schema's WIDER UNIVERSAL enum cites. | Adding a regression test for a schema-enum-parity gap. |
| `code-edit` | An ordinary edit to application or engine source — a `src/` tree, a Python engine module, a new class/feature, or any other non-doctrine executable code that isn't a `bin/` utility script (`script-edit`) or a hook (`hook-edit`). Applies to consumer repos that ship application/engine code, where `script-edit`'s "bin/ utility script" definition doesn't fit. Routes to the **improvement-queue** (project tier), NOT the lessons outbox — `coordinator-lesson-promote` does not accept this value; it is listed here only so this table's enumeration is the complete universal union the task-spine schema's WIDER UNIVERSAL enum cites. | Adding a new `commit_closures` emission module in a Python engine repo; adding a repo-identity-owner-qualified field to a Next.js `src/` component. |
| `config-edit` | Configuration and ignore-rule files — `.gitignore`, settings files, per-machine config — where the change is neither program logic nor documentation. Routes to the **improvement-queue** (project tier), NOT the lessons outbox — `coordinator-lesson-promote` does not accept this value; it is listed here only so this table's enumeration is the complete universal union the task-spine schema's WIDER UNIVERSAL enum cites. | Untracking machine-local files from sync by editing `.gitignore` first; adding a settings-file entry that makes a per-machine path structurally unsyncable. |
| `verification` | A follow-on whose deliverable is **evidence, not a diff** — a hardware-gated or environment-gated verification pass, a re-run on a platform the authoring machine is not, a manual dogfood of a shipped surface. The only row here that does not name a surface to edit, and it exists because deferring exactly this shape is common: the gating resource (a Windows box, a fresh-install machine, real hardware) is not to hand at plan time. If the verification finds a defect, that defect gets its OWN row with a change-shaped kind — a `verification` row never carries the fix. Routes to the **improvement-queue** (project tier), NOT the lessons outbox — `coordinator-lesson-promote` does not accept this value. | Re-running the de-bashed hook surface on Windows hardware before the port may be called portable. |

**Unrecognized values** cause the CLI to exit non-zero with a diagnostic naming the valid set. **`doc-edit`, `test-edit`, `code-edit`, `config-edit`, and `verification` are listed above for completeness of the universal union (every row in this table) but are NOT in `coordinator-lesson-promote`'s own accepted-enum** (that CLI validates against the 8 doctrine-routable rows only — everything above except those five); those five route to the improvement-queue project tier instead (see `docs/wiki/improvement-queue-schema.md`). Treat this table's row count, not any restated numeral, as the source of truth for the union's size.

**A work-shape word is not an enum member.** These values classify *the surface changed*, not the flavour of the change — so a bash-to-Python port of a `bin/` utility is `script-edit`, a rename sweep across agent prompts is `agent-prompt-edit`, and neither gets a coined kind of its own. The failure this warns against is real: a plan row tagged `script-port` (not a member, never was) routed nowhere on harvest and a PM-ratified deferral was dropped on a zero exit. If no member fits, the row is either mis-shaped or the union needs a member — decide that here, in this table, rather than at the point of authoring. A **destination** is not a member either: `central-promote` names where a record goes, not what it edits, and every entry in this outbox is a central promotion by construction — it stays a provenance annotation on a drained lesson, never a `change_kind` (`docs/decisions/DR-184-central-promote-is-provenance-not-a-change-kind.md`).

> **Do not confuse with the `coordinator:lesson-triage` skill's 12-kind action taxonomy.**
> `coordinator:lesson-triage` (the successor to `lessons-trim`) classifies each captured lesson
> as one of 12 change-request *kinds*: the 8 doctrine-routable values above, plus `memory-pointer`,
> `project-structural`, `retag-local`, `strip-local`, and `discard`. The last four are
> triage-local dispositions (re-tag, strip, or drop a lesson without ever reaching the outbox) —
> they are never valid `change_kind` values on an outbox YAML entry. `target_wiki`/`memory-pointer`
> routing decisions happen at triage time, upstream of this schema. <!-- src: plan03-013, plan03-015 -->

---

## Lifecycle

1. **Writer (CLI):** claude-klabauter `coordinator/bin/coordinator-lesson-promote` writes one YAML file per entry to
   `state/lessons-outbox/<ISO-ts>-<slug>.yaml`. The directory is created on first invocation
   (`mkdir -p`). No two entries share a file — each invocation appends a new timestamped file.

2. **Location:** `state/lessons-outbox/` in each peer repo. This path is under `state/`, which
   is never archived by `/distill` or `/update-docs` — see § Sweep-exclusion contract.

3. **Drainer (DoE central run):** `/learn-lessons --central` reads all peer outboxes via
   `~/.claude/machine-local/registry.local.toml`. See § DoE-side consumer notes and plan § C4
   for the full drain procedure.

4. **Archival (peer-side writeback):** After the DoE apply step, drained entries are moved from
   `state/lessons-outbox/` to `state/lessons-outbox/drained/` on the peer repo via `git mv` on
   a `drain/<YYYY-MM-DD>-doe-pull` branch. The branch is created locally on the DoE machine;
   the peer EM pulls and merges on their own schedule.

---

## DoE-side consumer notes

The DoE drain (`/learn-lessons --central`) enumerates peer repos via the `[repos]` table in
`~/.claude/machine-local/registry.local.toml`. For each registered peer repo that is on disk
on the current machine, the drain:

1. Fetches and pulls the peer repo to ensure the outbox is current.
2. Reads all `*.yaml` files under `state/lessons-outbox/` (excluding the `drained/` subdir).
3. **Deduplicates** across repos by the triple `(title, change_kind, target_wiki)`. Multiple
   entries sharing a triple from different repos are not a collision — they are a convergence
   signal. The drain records the source repos as a priority annotation and applies the lesson
   with elevated confidence.
4. Routes each entry through the standard central-mode classifier → verify-gate → apply pipeline
   (per `skills/learn-lessons/SKILL.md` Phase 2 central-mode).
5. Writes back drained entries to each peer's `drained/` subdirectory (see § Lifecycle step 4).

Peers not on disk on the current machine are skipped with a warning. The DoE drain is designed
to run from a machine with all peer repos checked out (typically Machine-a).

---

## Upstream: `coordinator:lesson-triage` modes

<!-- src: plan03-014, plan03-030 -->

`coordinator:lesson-triage` (successor to `lessons-trim`) is the unified surface that decides
whether a captured lesson (`state/lessons/<slug>.yaml`) ever reaches this outbox, and runs in
three modes:

- **project-local** — auto-applies bounded, low-risk dispositions without PM gating:
  `discard-ephemeral`, `migrate-to-existing-wiki`, `re-tag-local`, `dedupe`.
- **cross-project** — every apply is PM-gated. This is the mode that produces outbox entries:
  a `[universal]` lesson with a resolved central-wiki target invokes `coordinator-lesson-promote`,
  writing the YAML this schema describes.
- **recheck** — fires from a `state/lesson-triage-recheck-due-*.md` marker; auto-extends if ≤5
  new universal lessons have accumulated, otherwise escalates to cross-project mode.

Only `doctrine-edit`, `wiki-new`, `agent-prompt-edit`, `hook-edit`, `script-edit`, and
cross-repo `project-structural` changes surface to the PM; the project-local auto-apply set
above never does.

---

## Cockpit consumption (`LessonSummary`)

<!-- src: plan31-016, plan31-017, plan31-019, plan31-028, plan31-029, plan31-030, plan31-031 -->

Separate from the DoE-side drain (§ DoE-side consumer notes), the cockpit contract exposes a
read-only `LessonSummary` view over this same outbox for dashboard consumption.

**Capture surface is lightweight, not cockpit-shaped, by design.** `state/lessons/` is a
per-entry YAML capture queue (`docs/wiki/lessons-schema.md`) — a "capture queue for
`/learn-lessons`," not a record store. Its base shape is small on purpose: `title`, free-form
`body` prose, `status`, and a handful of optional fields (`scope`, facets, provenance); it
carries none of the cockpit-facing fields (`id` as uuid4, `change_kind`, `target_wiki`,
`scope_tags`) this outbox schema defines. Do not expect `LessonSummary` (or any structured
Cockpit view) to read `state/lessons/` directly — it reads the structured outbox instead.

**Full lifecycle, capture → drain:**

1. **Capture** (any session, free-form body) → `coordinator-queue-append --schema lessons`
   (or the `coordinator-lesson-add` wrapper) writes `state/lessons/<date>-<slug>.yaml`.
2. **Triage** (`/learn-lessons`, periodic) → one of the three modes in § Upstream above.
3. **Promote** — a `[universal]` lesson with a resolved central-wiki target invokes
   `coordinator-lesson-promote`, which writes the structured YAML this schema defines to
   `state/lessons-outbox/`.
4. **Drain** (DoE central run) → reads `state/lessons-outbox/*.yaml`, dedupes on
   `(title, change_kind, target_wiki)` (see § DoE-side consumer notes), routes through apply,
   then `git mv`s the entry to `drained/`.

**`LessonSummary` proposed field set (Option B — reads the outbox as the typed artifact
directly, rather than re-deriving a parallel summary contract):**

| Field | Source |
|---|---|
| `repo` | injected by the cockpit connector |
| `coordinator_root_path` | injected by the cockpit connector |
| `id` | outbox `id` |
| `created` | outbox `created` |
| `from_repo` | outbox `from_repo` |
| `title` | outbox `title` |
| `change_kind` | outbox `change_kind` |
| `target_wiki` | outbox `target_wiki` |
| `scope_tags` | outbox `scope_tags` |
| `evidence` | outbox `evidence` |
| `promotion_state` | connector-derived: `pending` (live outbox) or `drained` (moved to `drained/`) |
| `provenance` | `ProvenanceEnvelope` |

Option B was chosen over re-litigating a separate summary contract (Option A) because the
outbox is already the typed artifact and capture is deliberately kept cheap — introducing a
parallel contract would reintroduce ceremony a prior queue-schema decision
deliberately removed.

**Reading `drained/` turns the view into a time-series, not a bursty snapshot.** The connector
reads `state/lessons-outbox/` (pending) alongside `drained/` (promotion history), distinguished
by `promotion_state`, rather than only the live pending set.

**`change_kind` inference heuristic** (used where a `proposed_target` path is available but no
explicit `change_kind` was supplied — e.g. migrating prose entries into structured form):
`.sh` / `bin/` paths → `script-edit`; `hooks/` → `hook-edit`; `docs/wiki/*` → `wiki-append` or
`wiki-new`; `skills/*` → `skill-edit`; `agents/*` → `agent-prompt-edit`.

### Prose-to-YAML field mapping (migration aid)

<!-- src: plan31-017 -->

When migrating a free-form `improvement-queue.md`-style prose entry into structured YAML, the
field-by-field mapping is: `YYYY-MM-DD` → `created`; `<source-repo>` → `from_repo`;
`<source-file>:<line>` → `surface` (queue-append schema field, not an outbox field);
`<one-line summary>` → `title` (plus `body` for fuller prose); `proposed target: <file>` →
`proposed_target` (queue-append field, feeds the inference heuristic above);
`[recurring: N]` → `scope_tags` or a `body` note.

### Open questions (not yet resolved — do not treat as decided)

<!-- src: plan31-018, plan31-033 -->

- **Central-queue directory locus.** Central improvement-queue entries currently live at the
  meta-repo root `~/.claude/`, which is the same directory as the per-project
  `state/improvement-queue/` when cwd is `~/.claude`. Undecided whether to (a) merge them into
  one dir (simplest — cockpit already handles it) or (b) keep a distinct
  `state/central-improvement-queue/` glob for clarity (requires a new `TYPE_TO_GLOB` entry +
  emitter wiring). Note: per the coordinator CLAUDE.md `state/ vs tasks/` doctrine, central
  state has since moved to claude-klabauter (`$(python3 coordinator/lib/coordinator-state-root.py --central)/`) — re-verify this
  open question against that migration before acting on it.
- **Drained-inclusion default.** Whether `LessonSummary` reads only the live outbox (pending
  promotions) or also `drained/` (promotion history) was recommended as "both, with
  `promotion_state`" (see table above) but had not been ratified as of the source spec's date —
  confirm against the current cockpit-contract implementation before assuming it shipped as
  recommended.

> **Adjacent schema, not this one:** the central improvement-queue's cockpit-consumable record
> (`BacklogItemSummary`) is a distinct, intentionally lean field set (`type, id, created, status,
> title, from_repo, coordinator_root_path, severity, risk, provenance`) that the per-project
> improvement-queue already emits under the existing `type: "improvement"` tag — it is not this
> file's schema and lives in `docs/wiki/improvement-queue-schema.md`. <!-- src: plan31-016 -->

---

## Migration audit log format

<!-- Required per plan § C2 and AC8.2 — defines the dry-run output used by
     migrate-improvement-queue-universals.py --apply as its guard input. -->

Claude-klabauter `coordinator/bin/migrate-improvement-queue-universals.py --dry-run` writes its classification output to:

```
state/migrate-universals-dryrun-<ISO-date>.json
```

Example path: `state/migrate-universals-dryrun-2026-06-15.json`

### JSON schema

The file is a JSON array. Each element represents one entry from `state/improvement-queue/`
and has the following fields:

| Field | Type | Semantics |
|---|---|---|
| `source_line` | integer | Line number of the entry in `state/improvement-queue/` (1-indexed). |
| `classification` | string (enum) | One of: `"to-migrate"` (universal entry with resolved central-wiki target, ready to promote via `coordinator-lesson-promote`), `"unmigrated-no-target"` (universal entry with no resolved target — left in place, printed under "unmigrated — manual review"), `"project-specific"` (project-scoped entry — stays in `state/improvement-queue/`). |
| `entry_text` | string | Full text of the entry as it appears in the source file. |
| `proposed_outbox_id` | string or null | UUID4 proposed for the outbox file if `classification` is `"to-migrate"`. `null` otherwise. |
| `reason` | string | Human-readable explanation of the classification decision. |

### Example

```json
[
  {
    "source_line": 14,
    "classification": "to-migrate",
    "entry_text": "[universal] Drain branch must cut from peer main — append to learn-lessons-routing.md § Change-Kind Taxonomy",
    "proposed_outbox_id": "a3f2c1d0-4e5b-7f8a-9b0c-1d2e3f4a5b6c",
    "reason": "Tagged [universal] with resolved central-wiki target docs/wiki/learn-lessons-routing.md"
  },
  {
    "source_line": 22,
    "classification": "unmigrated-no-target",
    "entry_text": "[universal] Some pattern observed but no wiki home identified yet",
    "proposed_outbox_id": null,
    "reason": "Tagged [universal] but no central-wiki target could be resolved — left in place for manual triage"
  },
  {
    "source_line": 31,
    "classification": "project-specific",
    "entry_text": "Review example-repo GameLift Streams session timeout defaults before launch",
    "proposed_outbox_id": null,
    "reason": "No [universal] tag; scope is project-specific to example-repo"
  }
]
```

### `--apply` guard

`--apply` mode reads this file as its required guard input. It will refuse to run if:

- The dry-run output file is absent from `state/`, or
- The file's `<ISO-date>` suffix is older than 24 hours from the current timestamp.

> The 24-hour threshold is the default; `coordinator-lesson-promote`'s migration script
> `--apply` mode honors a `--stale-hours N` flag to override (run
> `migrate-improvement-queue-universals.py --help` for the current default).

This ensures the migration is always preceded by a human-reviewed dry run. The `--apply` step
processes only entries classified as `"to-migrate"`, invoking `coordinator-lesson-promote` for
each and removing the migrated lines from `state/improvement-queue/`.

---

## Sweep-exclusion contract

`state/lessons-outbox/` and `state/lessons-outbox/drained/` are both under `state/`. Per
coordinator CLAUDE.md § "state/ vs tasks/", `state/` is **never archived** by `/distill` or
`/update-docs`. These paths are explicitly named here for greppability — any future sweep or
archive script that encounters `lessons-outbox` must confirm this exclusion before acting.

The `drained/` subdirectory is an archival surface managed by the DoE drain procedure; it is
not a `/distill` target and must not be treated as ephemera.
