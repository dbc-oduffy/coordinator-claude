---
name: atlas-integrity-check
description: "Check today's changed files against the architecture atlas — flags narrative-drift when changes touch systems the atlas description doesn't mention or reflect. On RAG repos: narrative-drift findings. On non-RAG repos: also flags unmapped files as potential new systems. Invoked by /update-docs (Phase 11) or standalone."
version: 2.0.0
---

# Architecture Atlas Integrity Check

## Overview

Detect where the atlas narrative may have drifted from the codebase's current reality.

**Two modes depending on RAG presence:**

- **RAG present** (`mcp__*project-rag*` tool available): **Narrative-drift mode.** File-level coverage is RAG's job. This skill checks whether changed files touch areas the atlas narrative doesn't mention — suggesting the narrative description of that system needs updating.
- **RAG absent**: **Hybrid mode.** Run narrative-drift check AND flag unmapped files (legacy behavior). Unmapped files are potential new systems that the atlas hasn't captured.

**Skip silently if `tasks/architecture-atlas/systems-index.md` does not exist** — the atlas hasn't been bootstrapped yet. No error, no warning.

---

## Steps — RAG Present (Narrative-Drift Mode)

1. **Get today's changed files:**
   ```bash
   git diff --name-only $(git merge-base HEAD origin/main) HEAD 2>/dev/null || git diff --name-only HEAD~10 HEAD 2>/dev/null
   ```

2. **Read `tasks/architecture-atlas/systems-index.md`** — identify the named systems and their descriptions.

3. **For each changed file, determine which system it belongs to:**
   - Use the changed file's directory path to infer its system (e.g., `plugins/coordinator-claude/coordinator/commands/` → coordinator-pipeline).
   - If unsure, skip (don't guess).

4. **Read the narrative description for that system** from `tasks/architecture-atlas/systems/{system-name}.md` — specifically the "System Narrative" or "Purpose" section.

5. **Narrative-drift check:** Does the changed file's module or component appear in the narrative? Ask:
   - Does the narrative mention the subsystem/layer this file belongs to?
   - If the change introduces a new responsibility or capability, does the narrative still accurately describe the system's role?

6. **Emit narrative-drift findings for any mismatches:**
   ```
   NOTE: Narrative drift — [system-name]:
     - [file path]: this file touches [describe what changed — new capability/subsystem/refactor].
       The atlas narrative for [system-name] does not mention [X]. Consider updating the atlas
       narrative to reflect this change.
   ```

7. **If no drift detected:** Note: `"Atlas narrative check: no drift detected for [N] changed files."`

---

## Steps — RAG Absent (Hybrid Mode)

Run Steps 1-7 above (narrative-drift), then additionally:

8. **Read `tasks/architecture-atlas/file-index.md`** — each entry maps a file path (or directory) to a system.

9. **For each changed file, check if it appears in the file-index** (exact path match, or parent directory match).

10. **Collect unmapped files** — changed files not in the index.

11. **If unmapped files exist, flag:**
    ```
    NOTE: Potential new system detected — the following changed files are not mapped in the architecture atlas:
      - [file path] ([parent directory])
    Consider running /architecture-audit --refresh to remap, or manually add these files to the appropriate system in tasks/architecture-atlas/.
    ```

12. **If all changed files are mapped (or no changed files):** Note: `"Atlas file-index check: all changed files mapped."`

---

## Common Mistakes

- **Treating narrative-drift as a hard blocker.** This skill is informational — drift findings are prompts to update the atlas, not reasons to halt work. Flag and continue.
- **Reporting stale health status.** The atlas captures health grades at audit time — don't assume a passing grade from last month still applies after significant churn. Flag for re-audit when many files in a system have changed.
- **Confusing narrative-drift with file-coverage findings.** On RAG repos, the goal is "does the prose still match the system's actual role?" not "does every file have an index entry?" The prose is the deliverable; the file-index is secondary.
- **Missing pages for new systems.** When a new module or directory is added, it won't automatically appear in the atlas. Unmapped files (RAG-absent mode) are candidates for a new system page, not just individual file entries.
- **Forgetting to update grades after audits.** Running `/architecture-audit` generates findings but grades only update when explicitly recorded. An unupdated grade after an audit is misleading.
