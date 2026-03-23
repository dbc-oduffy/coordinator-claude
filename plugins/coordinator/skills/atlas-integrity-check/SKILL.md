---
name: atlas-integrity-check
description: "Check today's changed files against the architecture atlas file-index.md — flags unmapped files as potential new systems. This skill should be used when verifying that new or changed files are mapped in the architecture atlas, or after adding new modules or directories. Invoked by /update-docs (Phase 11) or standalone."
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
