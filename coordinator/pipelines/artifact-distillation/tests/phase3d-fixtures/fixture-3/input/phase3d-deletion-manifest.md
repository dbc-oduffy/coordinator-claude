---
schema_version: 3
deletions:
  - artifact_path: archive/completed/2026-06/2026-06-01-workstream-foo.md
    disposition: DELETE
    reason: "EPHEMERAL → DELETE"
    source_nugget_ids: []
deletion_groups:
  - scout_source: fixture-3/input/scout-A-classification.md
    section_anchor: "## EPHEMERAL — archive/completed/* completion logs"
    count: 5
    disposition: DELETE
    reason: "Ephemeral completion logs"
---

## Note

This is a synthetic fixture-3 manifest with schema_version: 3 (unsupported future version).
Expected behavior: Phase 5 (and lib/expand-phase3d-manifest.sh) MUST abort with a named error
identifying the unsupported schema_version. Silent parse of an unknown schema version is
forbidden by the fail-loud invariant (DR-082 / AC12).

Expected error message contains: "unsupported schema_version: 3"
