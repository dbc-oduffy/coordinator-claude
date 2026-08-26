---
segment_id: orientation-refresh
case: shared
class: droppable
order: 60
---

## Step 2.9: Refresh Orientation Documents

Close the read-write loop with `/workstream-start` and `/workday-start` — best-effort, skip if compaction is imminent (the handoff file is the priority).

- **Orientation cache pinboard** — a single append-or-omit line, not a body rewrite: `/handoff` does not author the cache or patch its sections (that's ceremony-writer territory). If the picker-upper of this handoff MUST see a piece of context that won't be obvious from the handoff body or a fresh ceremony regen, append one line via (Shape W, per `snippets/resolve-coordinator-bin.md`)
`& "$env:COORDINATOR_SETTINGS_HOME\bin\regenerate-orientation-cache.cmd" --invoker handoff --pinboard-only "YYYY-MM-DD <writer-slug>: <one-line note>"`. Otherwise do nothing.
- **Action items** (`ACTION-ITEMS.md` / `docs/active/ACTION-ITEMS.md` / `docs/ACTION-ITEMS.md`, first match) — check off any items this session resolved.

Targeted patches to what this session touched, not regeneration — concurrency-safe.
