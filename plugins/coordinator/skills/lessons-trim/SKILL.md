---
name: lessons-trim
description: "DEPRECATED ALIAS — invokes coordinator:lesson-triage in project-local mode. Periodic maintenance of lessons files (trim stale entries, merge duplicates, clean feature-scoped files). Invoked by /update-docs (Phase 6) or standalone. Removal due 2026-05-26 (one cadence cycle after lesson-triage ship)."
version: 2.0.0
---

# Lessons Trim — Deprecated Alias

This skill is a thin shim. All processing logic lives in `coordinator:lesson-triage`.

**Invoke:** `/lesson-triage --mode project-local` (or simply `/lesson-triage` from a project repo — auto-detects mode from cwd).

**Removal due:** 2026-05-26 — see `tasks/lessons-trim-removal-due-2026-05-26.md`. After that date, `/update-docs` Phase 6 should invoke `/lesson-triage --mode project-local` directly and this shim should be deleted.
