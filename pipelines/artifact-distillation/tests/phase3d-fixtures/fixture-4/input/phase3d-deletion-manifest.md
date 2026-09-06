---
schema_version: 1
deletions:
  - artifact_path: archive/completed/2026-03/2026-03-01-workstream-alpha.md
    disposition: DELETE
    reason: "DISTILLED → DELETE — nuggets extracted: b1-001, b1-002"
    source_nugget_ids: [b1-001, b1-002]
  - artifact_path: archive/completed/2026-03/2026-03-02-workstream-beta.md
    disposition: DELETE
    reason: "EPHEMERAL → DELETE — pure task list"
    source_nugget_ids: []
  - artifact_path: archive/completed/2026-03/2026-03-03-workstream-gamma.md
    disposition: BLOCKED
    reason: "Actively referenced by state/handoffs/2026-03-workstream-gamma-followup.md"
    source_nugget_ids: []
  - artifact_path: archive/completed/2026-03/2026-03-04-workstream-delta.md
    disposition: DELETE
    reason: "DISTILLED → DELETE — nuggets extracted: b1-003"
    source_nugget_ids: [b1-003]
  - artifact_path: archive/completed/2026-03/2026-03-05-workstream-epsilon.md
    disposition: PRESERVE
    reason: "Research output — always PRESERVE"
    source_nugget_ids: []
  - artifact_path: archive/completed/2026-03/2026-03-06-workstream-zeta.md
    disposition: DELETE
    reason: "EPHEMERAL → DELETE — session tracking log"
    source_nugget_ids: []
  - artifact_path: archive/completed/2026-03/2026-03-07-workstream-eta.md
    disposition: DELETE
    reason: "DISTILLED → DELETE — nuggets extracted: b1-004, b1-005, b1-006"
    source_nugget_ids: [b1-004, b1-005, b1-006]
  - artifact_path: archive/completed/2026-03/2026-03-08-workstream-theta.md
    disposition: DELETE
    reason: "EPHEMERAL → DELETE — pure handoff log, already consumed"
    source_nugget_ids: []
---

## Note

This is a synthetic fixture-4 manifest with schema_version: 1 (flat deletions: only,
no deletion_groups: key). Expected behavior: the v2 consumer MUST parse this successfully
as flat deletions-only — no error, no warning. Backward-compat invariant per AC15 and
PIPELINE.md § Phase 5 step 5.

Expected delete set (disposition: DELETE rows only, .md-only):
  archive/completed/2026-03/2026-03-01-workstream-alpha.md
  archive/completed/2026-03/2026-03-02-workstream-beta.md
  archive/completed/2026-03/2026-03-04-workstream-delta.md
  archive/completed/2026-03/2026-03-06-workstream-zeta.md
  archive/completed/2026-03/2026-03-07-workstream-eta.md
  archive/completed/2026-03/2026-03-08-workstream-theta.md

BLOCKED and PRESERVE rows are excluded. No deletion_groups: expansion occurs.
