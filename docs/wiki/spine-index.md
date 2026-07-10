# Spine Index — derived query tier over coordinator's spine records

> **Purpose.** Defines the *contract* for a derived index over coordinator's four on-disk "spine" record types — a structured (relational) **and** semantic query tier. This is the coordinator-side of roadmap stub **ccos-7**. The contract is coordinator-owned (the record shapes and query needs are ours); **project-rag is the index generator** (the generator, storage substrate, retrieval surface, and rebuild test are theirs). Coordinator does **not** build parallel indexing machinery.

> **Negative-spec.** The index is **never authoritative** — the on-disk records are the source-of-truth; the index is a derived, re-derivable, throwaway cache. No coordinator write path may read the index as a source for mutating records. Coordinator does NOT implement the generator, the storage, or the retrieval surface — those are project-rag's domain (PM direction 2026-06-30: "I don't want coordinator to get into their business; it's fine to depend on them").

## Why "contract here, generator there"

The roadmap (OVERVIEW § ccos-7, `2026-06-27-ccos-fork-recommendation.md` Fork-A §5) named project-rag as the index home and marked it *certain*. A 2026-06-30 scout of project-rag confirmed it is a **code-intelligence** system (structural symbol-graph + semantic vector search) with hard-coded source kinds (`core/project_type.py:55`, no plugin seam) and no relational row-store — so a *relational* index is invasive for it, while *semantic* embedding of records is native. The reconciliation (PM-directed) is **not** "coordinator builds its own index": it is **SoT + plural derived indexes**, with project-rag as the *generator* every repo depends on. Fork-A §4 already frames this: *"query is a read/index concern, not a SoT concern."* The model: **every repo holds its own derived index; project-rag generates and regenerates it.**

## The records (source-of-truth — all in `~/.claude`)

JSON-Schema files: `plugins/coordinator/schemas/`.

| Record (stub) | On-disk location | Schema | Key fields |
| --- | --- | --- | --- |
| provenance work-items (ccos-3) | `state/{improvement-queue,debt-backlog,bug-backlog}/*.yaml` (`system:` block) | queue/backlog schemas | `created_by_session`, `created_by_agent`, `provenance_completeness` |
| session/workstream hierarchy (ccos-5) | `state/session-hierarchy.<machine>.json` | `session-hierarchy.schema.json` | `session_id`, `workstream`, `branch`, `parent_session_id`, `session_type` |
| file-attribution (ccos-6) | on-demand Python derivation over `~/.claude/projects/<project>/*.jsonl` (bin/derive-file-attribution.py — no producer, no persisted ledger) | derived; no row schema | `session_id`, `file_path`, `link_type` ∈ {edited, referenced, read, unknown} |

**Join keys.** `session_id` is the spine (every record keys on it). `workstream`, `file_path`, and `agent_id`/`agent_type` are the secondary axes.

> **File-attribution is derived-on-demand** — no producer, no Stop-hook, zero `state/file-attribution-ledger/` writes. Attribution is computed at query time directly from natural Claude Code transcripts (`~/.claude/projects/<project>/*.jsonl`) via `bin/derive-file-attribution.py`.

## The two query surfaces

**Structured (exact / relational)** — marquee cross-record joins the three bespoke CLIs (`query-file-attribution.py`, `query-session-hierarchy.sh`, …) cannot do:

- `workstream <slug>` → session tree (via `parent_session_id`) + per-session event count + file-churn count + token/cost rollup.
- `file <path>` → every session that touched it (with `link_type`) + each session's workstream + when.
- `work-item <id>` → provenance chain: creating session → its workstream → files that session touched → its cost.
- `cost-by-workstream` → token/cost rollup grouped by workstream.
- `session <id>` → full profile: workstream, parent, events by kind, files touched, cost, subagents spawned.

**Semantic (intent)** — e.g. "find sessions semantically about X", "where the agent struggled with cross-platform shell portability." Raw JSONL embeds as opaque text; a record-aware rendering indexes far better. Surfacing is project-rag's design call.

## Invariants (the contract project-rag honors)

1. **Derived & re-derivable** — a full rebuild from the record files reproduces the index (rebuild test on project-rag's side).
2. **Never authoritative** — the records are SoT; the index is a throwaway cache.
3. **Per-repo** — every repo holds its own index; coordinator's spine is the first instance. (Physical location — in-tree vs project-rag-hosted-but-repo-scoped — is part of project-rag's design.)

## Open question (project-rag scopes; not assumed)

The retrieval path is unscoped by design. A co-tenancy constraint applies (`state/improvement-queue/2026-06-23-project-rag-co-tenant-addon-handler-can.yaml`): an addon handler can read an external SQLite but cannot retrieve over a `CorpusBand` without the host getter. **How a consumer (coordinator's `/workday-start`, cockpit's dashboard) queries the structured tier — new MCP tool / external-SQLite read / host getter — is project-rag's to name.**

## Consumers & division of labor

- **Coordinator** owns this contract + consumes the structured tier (e.g. `/workday-start` cost/churn surfaces). Does not build the index.
- **project-rag** owns the generator, storage, retrieval surface, and rebuild test. North-star: a generic per-repo structured-record index generator across the fleet.
- **cockpit** is a likely downstream consumer (structured + semantic) for its dashboard. cockpit does not *need* this (it reads `cockpit-emission.json` per the 2026-06-27 spike) — it is an additional, optional surface it may *want*.

## Cross-repo memos (the asks)

- → **project-rag-em** (`ask`, sent 2026-06-30): be the index generator; full contract enclosed. `X:\project-rag\cross-repo\inbox\2026-06-30-spine-index-generation.md`.
- → **example-cockpit-repo-em** (`fyi`, sent 2026-06-30): the tier is coming via project-rag; align your dashboard read path / loop into the retrieval-path design if you want to consume.

Both delivered via PM-relay. The working index is tracked by the project-rag memo, not re-opened coordinator-side.
