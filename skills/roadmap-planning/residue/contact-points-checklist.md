- **`/handoff` and `/spinoff`:** gate text MUST be subsystem-named, never file-pathed (the
  gate-meaningfulness audit reads it from git history; a path goes stale on archive). The schema
  rejects a path-shaped `gate_dependency` — baton dependency → `blocked_by` slug, prose →
  `gate_notes`. Rationale: wiki `roadmap-planning-residue.md` § Contact points.
- **`/repo-setup`** — orientation flow mentions roadmap-planning when the tracker has roadmap entries.
- **`/workstream-start`** — query callout already covers `kind: roadmap-baton` via `deployment_state=ready_to_fire`.
- **`/workstream-complete`** — plan-doc update step covers roadmap stubs (shared handoff lifecycle).
- **`/workday-start`** — Step 1.1 groups `kind: roadmap-baton` with spinoffs, clustered by `roadmap_id` when >3 per group.
- **Hooks:** the boot-time archival sweep (`session.boot_sweep`, `bin/sweep-boot.py`) silently
  archives consumed handoffs whose session is dead, covering orphaned roadmap stubs.
- **Discovery:** `bin/query-records --list-schemas`, `bin/lint-frontmatter --list-schemas`.
