---
title: "Lessons Outbox — Per-Entry YAML Schema"
kind: wiki
audience: coordinator-em
created: 2026-06-15
last-updated: 2026-06-15
system: learn-lessons
---

# Lessons Outbox Schema

<!-- Spec backlink: archive/specs/2026-06/2026-06-15-universal-lesson-routing-mechanical-capture.md § C2 -->
<!-- Negative-spec: The pre-plan approach of appending [universal] lessons to state/improvement-queue.md is REPLACED by this outbox for central-wiki-target entries. improvement-queue.md remains valid only for project-specific entries. -->

The lessons outbox is a per-entry YAML store at `state/lessons-outbox/<ISO-ts>-<slug>.yaml`
inside each peer repo. Each file represents one lesson ready for DoE-side drain. Entries are
produced mechanically by the `bin/coordinator-lesson-promote` CLI (invoked from
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
| `from_repo` | string | required | Registry shortname of the originating repo, resolved from `machine-local/registry.local.toml` `[repos]` table using the cwd git-root match. Not a URL or filesystem path — the short identifier as registered (e.g. `example-repo`, `exampleSimRepo`). | `"example-repo"` |
| `title` | string | required | Human-readable lesson title. Same text as the bold title in `state/lessons.md`. Brief, noun-phrase form. | `"Drain-branch must cut from peer main, not active workstream"` |
| `body` | string | required | Prose explanation of the lesson. Multi-line allowed. "Just enough structure" — a paragraph or two; not a wiki article. The DoE apply step uses this as the raw content for the wiki patch. | `"When the DoE drain step creates a branch on a peer repo, it must cut from the peer's main rather than the current workstream branch. Cutting from the workstream silently entangles unrelated work into the drain commit."` |
| `change_kind` | enum (string) | required | Classification of the target change. Drives apply dispatch in `/learn-lessons --central`. **See § Change-kind enum — this field's closed enum is defined there.** | `"wiki-append"` |
| `target_wiki` | string | required | Named central wiki path under `~/.claude/docs/wiki/<name>.md`, or the literal string `unknown` when the classifier could not resolve a target. The DoE apply step rejects `unknown` entries and queues them for manual triage. | `"docs/wiki/learn-lessons-routing.md"` or `"unknown"` |
| `scope_tags` | list of strings | optional | Free-form tags for filtering and priority. Convention: repo shortname, system name, or symptom label. | `["drain", "cross-repo", "state"]` |
| `evidence` | string or list of strings | optional | Commit SHA, plan path, or lesson-source file (`state/lessons.md` line reference) that motivated this entry. Used by the DoE apply step for provenance annotation. | `"76130204"` or `["76130204", "docs/plans/2026-06-15-universal-lesson-routing-mechanical-capture.md"]` |

> **Forward-seam note (post-migration capture):** When a lesson captured post-migration is promoted here, the `evidence` value naturally evolves from a `state/lessons.md:<N>` line reference to the per-entry filename (`state/lessons/<slug>.yaml`).

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

## Change-kind enum

<!-- This section is the SINGLE AUTHORITATIVE DEFINITION of the change_kind enum.
     The CLI (bin/coordinator-lesson-promote) and learn-lessons-routing.md § Change-Kind Taxonomy
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
| `script-edit` | A change to a `bin/` utility script that is not a hook. Applies when the lesson identifies a bug, missing flag, or wrong default in a CLI tool. | Fixing `bin/coordinator-lesson-promote` to reject `from_repo: unknown`. |
| `snippet-sync-update` | A snippet body change that requires `bin/verify-<name>-sync.sh --fix` after editing. Applies when the lesson identifies a stale or incorrect snippet that propagates into prompts via sync. | Updating `snippets/drain-preamble.md` and re-running `verify-drain-preamble-sync.sh --fix`. |
| `wiki-new` | A new wiki file under `docs/wiki/`. Applies when the lesson introduces a concept or subsystem that has no existing wiki home. | Creating `docs/wiki/lessons-outbox-schema.md` (this file). |
| `wiki-append` | An append to an existing wiki section. The most common value — use this when the lesson adds a row, paragraph, or named exception to an existing wiki. | Appending a drain-writeback note to `docs/wiki/learn-lessons-routing.md § Change-Kind Taxonomy`. |
| `skill-edit` | A `SKILL.md` body edit. Use when the lesson identifies a missing step, wrong gate, or incorrect procedure in a skill. Previously folded into `wiki-append`; promoted to a distinct value because skill body edits have a different apply path (executor reads current line ranges before patching). | Adding the peer-repo skip-with-warning step to `skills/learn-lessons/SKILL.md` Phase 2.6. |
| `doc-edit` | A change to project-local documentation (README, `docs/README.md`, CONTEXT.md, or similar non-wiki doc surfaces) that is not itself a wiki file. Routes to the **improvement-queue** (project tier), NOT the lessons outbox — `coordinator-lesson-promote` does not accept this value; it is listed here only so this table is the complete 10-value universal union the task-spine schema's WIDER UNIVERSAL enum cites. | Fixing a stale command name in a repo's `README.md`. |
| `test-edit` | A change to a test file (adding, fixing, or hardening a test) that is not itself a hook/script/agent-prompt edit. Routes to the **improvement-queue** (project tier), NOT the lessons outbox — `coordinator-lesson-promote` does not accept this value; it is listed here only so this table is the complete 10-value universal union the task-spine schema's WIDER UNIVERSAL enum cites. | Adding a regression test for a schema-enum-parity gap. |

**Unrecognized values** cause the CLI to exit non-zero with a diagnostic naming the valid set. **`doc-edit` and `test-edit` are listed above for completeness of the 10-value universal union but are NOT in `coordinator-lesson-promote`'s own accepted-enum** (that CLI validates against 8 doctrine-routable values only — everything above except `doc-edit`/`test-edit`); those two route to the improvement-queue project tier instead (see `docs/wiki/improvement-queue-schema.md`).

---

## Lifecycle

1. **Writer (CLI):** `bin/coordinator-lesson-promote` writes one YAML file per entry to
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
to run from a machine with all peer repos checked out (typically Striker).

---

## Migration audit log format

<!-- Required per plan § C2 and AC8.2 — defines the dry-run output used by
     migrate-improvement-queue-universals.py --apply as its guard input. -->

`migrate-improvement-queue-universals.py --dry-run` writes its classification output to:

```
state/migrate-universals-dryrun-<ISO-date>.json
```

Example path: `state/migrate-universals-dryrun-2026-06-15.json`

### JSON schema

The file is a JSON array. Each element represents one entry from `state/improvement-queue.md`
and has the following fields:

| Field | Type | Semantics |
|---|---|---|
| `source_line` | integer | Line number of the entry in `state/improvement-queue.md` (1-indexed). |
| `classification` | string (enum) | One of: `"to-migrate"` (universal entry with resolved central-wiki target, ready to promote via `coordinator-lesson-promote`), `"unmigrated-no-target"` (universal entry with no resolved target — left in place, printed under "unmigrated — manual review"), `"project-specific"` (project-scoped entry — stays in `improvement-queue.md`). |
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
each and removing the migrated lines from `state/improvement-queue.md`.

---

## Sweep-exclusion contract

`state/lessons-outbox/` and `state/lessons-outbox/drained/` are both under `state/`. Per
coordinator CLAUDE.md § "state/ vs tasks/", `state/` is **never archived** by `/distill` or
`/update-docs`. These paths are explicitly named here for greppability — any future sweep or
archive script that encounters `lessons-outbox` must confirm this exclusion before acting.

The `drained/` subdirectory is an archival surface managed by the DoE drain procedure; it is
not a `/distill` target and must not be treated as ephemera.
