---
schema_version: 2
deletions: []
deletion_groups:
  - scout_source: fixture-1/input/scout-A-classification.md
    section_anchor: "## EPHEMERAL — archive/completed/* completion logs (2026-06 sprint)"
    count: 100
    disposition: DELETE
    reason: "Per-entry status-and-LOE logs; knowledge folded into wiki at execution time"
---

## Derived Prose Preview (PM-readable)

Fixture-1 synthetic Phase 3d manifest — single-Sonnet-grouped mode, N=100.

- `deletions:` row count: 0 (AC14 assertion: must equal 0)
- `deletion_groups:` row count: 1

All 100 artifacts are covered by one deletion_groups: entry citing scout-A-classification.md.
Phase 5 expansion reads the fenced YAML block under the section_anchor heading and produces
100 synthetic DELETE rows — one per artifact_paths: entry.
