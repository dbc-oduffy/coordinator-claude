- **`/handoff` and `/spinoff`:** gate text MUST be subsystem-named, never file-pathed (the schema
  rejects a path-shaped `gate_dependency`): baton dependency → `blocked_by` slug, prose →
  `gate_notes`.
- **`/repo-setup`** — orientation flow mentions roadmap-planning when the tracker has roadmap entries.
- **`/workstream-start`** — query callout covers `kind: roadmap-baton` via `deployment_state=ready_to_fire`.
- **`/workstream-complete`** — plan-doc update step covers roadmap stubs.
- **`/workday-start`** — Step 1.1 groups `kind: roadmap-baton` with spinoffs, clustered by `roadmap_id` when >3 per group.
- **Hooks:** the boot-time archival sweep (`session.boot_sweep`) archives consumed handoffs whose session is dead, covering orphaned roadmap stubs.
- **Discovery:** `bin/query-records --list-schemas`, `bin/lint-frontmatter --list-schemas`.
