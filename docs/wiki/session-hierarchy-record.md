# Session/Workstream Hierarchy Record

**Purpose:** A re-derivable, on-disk projection that answers "which sessions belong to workstream X" and "which workstream/branch/parent does session Y belong to?" without grepping handoff files. Every relationship it encodes is derived from existing handoff frontmatter lineage; only the session-type taxonomy and the unconsumed/handoff-less gap are authored. It is index-class: no write path treats it as the source of truth.

**Spec backlink:** `docs/plans/2026-06-27-ccos-5-session-workstream-hierarchy-record.md`

---

## What This Record Is

The session-hierarchy record is a **materialized projection rebuilt from handoff lineage**, not an authored store. Each record is keyed on the **harness `session_id`** — the UUID a session owns from the moment it calls `cs_claim_handoff` or is assigned one by the framework. That identifier space is shared with `ccos-3 linked_sessions`, `ccos-4 journal` keys, and `ccos-6 ledger` keys.

The derive-bridge is the handoff `consumed_by` field: every handoff that was consumed via `/pickup` carries the consuming session's `session_id` in its `consumed_by` field. This is the only lineage→session_id bridge the derive script uses. Handoffs that were never consumed (no `consumed_by`) have no bridge and produce no record; they fall to the `ccos-4 journal` enumeration to fill the coverage gap.

**Not an authored SoT.** Editing the projection directly is the wrong pattern; modify the handoff frontmatter it was derived from, then re-run the derive script.

---

## Output Shape — Per-Machine Shard

```
state/session-hierarchy.<machine-slug>.json
```

Each machine writes its own shard (full rebuild, atomic temp+rename). The `<machine-slug>` is derived from `hostname` with the coordinator-standard slug transform: lowercase, non-alnum runs replaced with `-`, leading/trailing dashes stripped.

**Why per-machine?** A single global file rebuilt on every machine would produce whole-file git conflicts on every cross-machine merge of the shared workstream branch. The per-machine shard eliminates cross-machine conflicts entirely: each machine rebuilds only its own file, and the union across all shards is the queryable surface.

**Shard format:** a JSON array of record objects conforming to `schemas/session-hierarchy.schema.json`:

```json
[
  {
    "session_id": "d964cd5a-f3db-4d10-b906-9b63701ec4a4",
    "session_type": "session",
    "workstream": "ccos-5",
    "branch": "work/delphipro/2026-06-23to25",
    "parent_session_id": "aaaabbbb-...",
    "linked_handoffs": ["state/handoffs/2026-06-27_...md"],
    "system": {
      "provenance_completeness": "complete",
      "capture_source": "derived_handoff_lineage",
      "completeness": "complete"
    }
  },
  {
    "session_id": "workstream:ccos-5",
    "session_type": "workstream",
    "workstream": "ccos-5",
    "parent_session_id": null,
    "linked_handoffs": [],
    "system": { "provenance_completeness": "complete", "capture_source": "derived_handoff_lineage", "completeness": "complete" }
  }
]
```

**Querying the union:** `query-session-hierarchy.sh` globs all `state/session-hierarchy.*.json` shards and queries them in union. When a session was picked up on one machine and the shard lives there, the local query (on a different machine with no local shard for that session) finds it via the union glob.

---

## How Records Are Derived

The derive script (`bin/derive-session-hierarchy.sh`) runs `bin/query-records.js --type handoff` to read handoff frontmatter without re-parsing YAML. It then applies the handoff↔session map:

| Derived field | Source |
|---|---|
| `session_id` | `handoff.consumed_by` |
| `workstream` | `handoff.workstream` |
| `branch` | `handoff.branch` (approximation — see caveat below) |
| `parent_session_id` | predecessor handoff's `consumed_by` (one-hop predecessor walk) |
| `session_type` | `"blitz"` when workstream slug contains `blitz`/`bug-blitz`/`mise-en-place` (case-insensitive); else `"session"` |

**Synthetic workstream nodes** (one per distinct workstream slug): `session_type: "workstream"`, `parent_session_id: null`, `session_id: "workstream:<slug>"`. These are never in handoffs; the derive script emits them to provide a container node for the grouping invariant.

**Write discipline:** full rebuild on each run; atomic temp+rename; never hand-appended. Latest-wins semantics.

---

## Reverse-Query Interface

`bin/query-session-hierarchy.sh` — read-only; safe to run concurrently.

```bash
# All session_ids in a workstream (one per line):
query-session-hierarchy.sh --workstream ccos-5

# Workstream/branch/parent/type for one session:
query-session-hierarchy.sh --session d964cd5a-f3db-4d10-b906-9b63701ec4a4
```

The `--workstream` output includes leaf session records AND the synthetic workstream-type node (both carry `workstream: <slug>`). The `--session` output is a compact JSON object with `{session_id, session_type, workstream, branch, parent_session_id}`.

---

## Translated ExampleVoiceSystem Invariant — Both Limbs

example-voice-system's `ai_sessions` table carries a DB invariant: *"worktree-resident sessions have no `parent_session_id`; workstream rows have no `worktree_id`"* — because *worktree IS workstream* in example-voice-system's model.

Coordinator has no worktrees and uses one shared branch per machine (carrying many workstreams). The invariant is **translated, not lifted**:

### Limb 1 — Branch-Laterality / Slug-Grouping

In example-voice-system, the worktree is the workstream container. In coordinator, **the `workstream:` slug is the container; `branch` is lateral metadata**.

Concrete consequences:
- Two sessions on different branches with the same `workstream:` slug group together under that slug. Querying `--workstream <slug>` returns all of them regardless of branch.
- No `branch` value is ever a workstream key. `session_id` values are harness UUIDs or `"workstream:<slug>"` — never branch paths.
- example-voice-system's worktree==workstream containment was a **containment** relation. Coordinator's slug-grouping is the structural **inverse**: one branch carries many workstreams; a workstream spans potentially many branches.

### Limb 2 — Role-Exclusivity

In example-voice-system: worktree rows have no `parent_session_id`; workstream rows have no `worktree_id`. Translation:

- **Synthetic `workstream`-type nodes** always have `parent_session_id: null`.
- **Workstream-root leaf sessions** (handoff `kind: spinoff*` OR `predecessor: none`) have `parent_session_id: null`.
- Only non-root `session`-type leaves carry a non-null `parent_session_id` (resolved by the one-hop predecessor walk).

Both limbs are asserted by the bats suite at `bin/tests/test-session-hierarchy.bats`.

---

## Branch Approximation Caveat

The `branch:` field in a session-hierarchy record is derived from the **handoff's `branch:` field**, which is stamped at handoff **authoring time** — meaning it reflects the *predecessor session's branch* at the moment the handoff was written, not the consuming session's branch.

This creates a known mis-attribution in two cases:
1. Daily branch rename between handoff authoring and pickup (the consuming session starts on a new daily branch).
2. Cross-machine pickup (the consumer is on a machine with a different branch name convention).

Where `ccos-4 journal` entries provide the consuming session's actual branch, prefer that and fall back to the handoff-derived value. Until `ccos-4` coverage is complete, treat `branch:` in this record as a best-effort approximation.

---

## Coverage Honesty — The Partial Bucket

The derive bridge (`consumed_by`) is present only on handoffs that went through `/pickup`. In practice this is a minority of all handoffs. The coverage gaps:

- **Unconsumed/active handoffs**: `consumed_by` is absent until pickup; `authoring_session` is free-prose narrative (not a session_id). These produce no record in the handoff-derive pass — they are omitted entirely, not emitted as partial stubs.
- **Handoff-less sessions**: sessions that never authored a handoff have no lineage bridge at all.

The `system.completeness: "complete"` on all emitted records means: *every field in this record was fully derived*. The "partial" bucket — sessions we know exist but couldn't fully characterize — is filled by `ccos-4 journal` enumeration and/or `ccos-2 agent_sessions` as those roll out. Until then, `query-session-hierarchy.sh` answers the consumed-pickup subset of sessions only.

**Negative-spec:** the derive script does NOT emit partial stubs for unconsumed handoffs. The cleaner semantics: a record only appears in the shard when its `session_id` is known (via `consumed_by`). The absence of a record is the signal that a session falls in the ccos-4 coverage gap.

---

## Derive/Author Split

**Derived from handoff lineage (zero authoring required):**
- session → workstream membership (`workstream:` + `consumed_by`)
- session → branch (approximation; `branch:` + `consumed_by`)
- session → `parent_session_id` (one-hop predecessor walk)
- canonical session identity (the `consumed_by` UUID)
- spinoff/fork lineage (`kind: spinoff*` + `predecessor: none`)

**Authored — lineage cannot express:**
- `session_type` enum (`session|workstream|blitz`) — handoff `kind:` is a handoff-fork taxonomy, not a session-role taxonomy; the synthetic workstream container node has no handoff
- mappings for active/unconsumed handoffs and handoff-less sessions — `consumed_by` absent means no bridge; these are filled by `ccos-4` enumeration or left in the partial bucket
- the translated branch/workstream invariant assertion — example-voice-system stored `worktree_id` as a DB column with an enforced constraint; coordinator has no worktree, so "branch is lateral, not container" is an authored translation rule

---

## Negative-Spec

- Does NOT re-parse handoff YAML — consumes `bin/query-records.js` exclusively.
- Does NOT duplicate `ccos-2`'s session→plan relation (`agent_sessions:` on plans).
- Does NOT add a `lifecycle:`/`liveness:`/`live:` key — liveness is derived from `canonical-artifact-shapes.md`, not stored.
- Does NOT lift example-voice-system's `worktree_id` DB invariant — coordinator has no worktrees; the translation is slug-grouping + branch-laterality as documented above.
- Does NOT author a relational store or DB — re-derivable projection only; `ccos-7` indexes this for project-rag.
