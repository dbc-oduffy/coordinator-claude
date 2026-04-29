---
name: atlas-integrity-check
description: "Check today's changed files against the architecture atlas file-index.md — flags unmapped files as potential new systems. This skill should be used when verifying that new or changed files are mapped in the architecture atlas, or after adding new modules or directories. Invoked by /update-docs (Phase 11) or standalone."
version: 1.0.0
---

# Architecture Atlas Integrity Check

## Overview

If `tasks/architecture-atlas/file-index.md` exists, check whether today's changed files are all mapped to known systems.

**Skip silently if `file-index.md` does not exist** — the atlas hasn't been bootstrapped yet. No error, no warning.

## Steps (only when file-index.md exists)

1. Get today's changed files:
   ```bash
   git diff --name-only $(git merge-base HEAD origin/main) HEAD 2>/dev/null || git diff --name-only HEAD~10 HEAD 2>/dev/null
   ```
2. Read `tasks/architecture-atlas/file-index.md` — each line maps a file path to its system
3. For each changed file, check if it appears in the index
4. Collect changed files that are NOT in the index
5. If any unmapped files exist, flag in your output:
   ```
   NOTE: Potential new system detected — the following changed files are not mapped in the architecture atlas:
     - [file path] ([parent directory])
   Consider running /deep-architecture-audit to refresh the atlas, or manually add these files to the appropriate system in tasks/architecture-atlas/.
   ```
6. If all changed files are mapped (or no changed files), note: `"Atlas check: all changed files mapped."`

**This is informational only** — do not create new atlas entries or modify any atlas files.

## Common Mistakes

- **Reporting stale health status.** The atlas captures health grades at audit time — don't assume a passing grade from last month still applies after significant churn. Flag for re-audit when many files in a system have changed.
- **Missing pages for new systems.** When a new module or directory is added, it won't automatically appear in the atlas. Unmapped files surfaced by this check are candidates for a new system page, not just individual file entries.
- **Frontmatter format errors.** Atlas pages use YAML frontmatter for system metadata. Malformed frontmatter (unquoted colons, missing fields) silently breaks tooling that reads the atlas — validate after any manual edits.
- **Forgetting to update grades after audits.** Running `/architecture-audit` generates findings but grades only update when explicitly recorded. An unupdated grade after an audit is misleading.
- **Treating the check as a hard blocker.** This skill is informational — unmapped files are a prompt to update the atlas, not a reason to halt work. Flag and continue.
