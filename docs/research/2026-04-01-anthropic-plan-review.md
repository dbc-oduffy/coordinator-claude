# Plan Review: Anthropic Multi-Agent Lessons — Pipeline Improvements

**Reviewer:** Patrik
**Date:** 2026-04-01
**Plan:** `~/.claude/plans/compiled-exploring-snail.md`
**Review type:** LOW-EFFORT structural review

---

```json
{
  "reviewer": "patrik",
  "verdict": "APPROVED_WITH_NOTES",
  "summary": "Well-structured plan that correctly maps Anthropic's production learnings to concrete prompt-level changes across both repos. File targets are accurate, insertion points are realistic, and the scope is appropriately conservative (prompt edits, not architectural changes). Three structural issues worth addressing before execution: the eval skill creates a directory that doesn't exist, Task 8's sync step is fragile and underspecified, and Pipeline B/C are silently excluded without justification.",
  "findings": [
    {
      "file": "plans/compiled-exploring-snail.md",
      "line_start": 276,
      "line_end": 301,
      "severity": "major",
      "category": "correctness",
      "finding": "Task 7 creates `skills/eval-output.md` but no `skills/` directory exists in deep-research-claude (only agents/, commands/, pipelines/, docs/). The skill references `${CLAUDE_PLUGIN_ROOT}/pipelines/eval-rubric.md` which assumes the plugin framework resolves this variable — but since `skills/` is a new directory, the plugin.json may also need a `skills` entry to register it. The plan doesn't address either the directory creation or the plugin registration.",
      "suggested_fix": "Add a step to mkdir skills/ and verify plugin.json's skill discovery mechanism. If the plugin framework auto-discovers .md files in skills/, just add the mkdir. If it requires explicit registration, add the plugin.json update to Task 7 instead of deferring all plugin.json changes to Task 8."
    },
    {
      "file": "plans/compiled-exploring-snail.md",
      "line_start": 309,
      "line_end": 325,
      "severity": "major",
      "category": "architecture",
      "finding": "Task 8 (cache sync) is a manual copy step that will silently become stale. The plan says 'Copy all modified agent definitions, prompt templates, and new files to the cache' but doesn't enumerate which files or provide a script. Given 4 tasks modify Pipeline A files and 3 modify Pipeline D files, a manual sync is error-prone. Additionally, if the version path changes from 1.0.0 to 1.1.0, the old cache directory may still be referenced.",
      "suggested_fix": "Either (a) write a sync script that copies the full plugin directory to cache deterministically, or (b) note explicitly that the executor should use rsync/robocopy with a delete flag to ensure the cache is a clean mirror. Also specify whether the old 1.0.0 cache directory should be removed."
    },
    {
      "file": "plans/compiled-exploring-snail.md",
      "line_start": 1,
      "line_end": 9,
      "severity": "minor",
      "category": "completeness",
      "finding": "Plan header says 'all four research pipelines (A, B, C, NotebookLM D)' but Pipelines B (repo research) and C (structured research) are never touched. All tasks modify only Pipeline A and Pipeline D files. Pipeline B has its own scout (repo-scout.md) and specialist (repo-specialist.md) prompt templates, and Pipeline C has structured-scout-prompt-template.md. If the lessons don't apply to B/C (they're different enough), that's fine — but the plan claims coverage it doesn't deliver.",
      "suggested_fix": "Either (a) add tasks for Pipeline B/C scouts and specialists (the SEO detection and broad-to-narrow search strategy are less relevant to repo research, but parallel tool calling and extended thinking guidance are universal), or (b) change the header to say 'Pipelines A and D' and add a note explaining why B/C are excluded."
    },
    {
      "file": "plans/compiled-exploring-snail.md",
      "line_start": 29,
      "line_end": 47,
      "severity": "minor",
      "category": "correctness",
      "finding": "Task 1 Step 1 says to add SEO detection 'after Vet accessibility (step 3)' in the scout agent definition. But the actual agent definition has step 3 as 'Vet accessibility via WebFetch' which is a numbered list item with sub-bullets. The plan's insertion point is correct conceptually, but the instruction to add it as sub-bullets of step 3 vs. a new step 3b is ambiguous. The plan also says to update the corpus output format (Step 2) to add an `SEO-suspect` field, but the existing format already has specific fields (URL, Accessible, Date, Type, Relevant topics, Snippet) — the new field needs to be shown in the correct position.",
      "suggested_fix": "Specify that SEO detection is added as additional sub-bullets under step 3's existing WebFetch checklist, and show the SEO-suspect field's position in the output format (e.g., after 'Type' and before 'Relevant topics')."
    },
    {
      "file": "plans/compiled-exploring-snail.md",
      "line_start": 127,
      "line_end": 149,
      "severity": "minor",
      "category": "correctness",
      "finding": "Task 4 adds parallel fetching guidance to the specialist prompt template under section '2. Deep-Read and Verify' — but the existing template already instructs specialists to 'Use WebFetch to read the most promising sources in full' (line 68 of specialist-prompt-template.md). The parallel instruction should be placed adjacent to that existing instruction, not just 'added to section 2' generically. Also, Step 2 says to add the same to 'the specialist agent definition' (research-specialist.md), but that file's content is minimal — it says 'Read the specialist prompt template... Follow its instructions.' Adding detailed parallel fetch guidance there would create drift between two sources of truth.",
      "suggested_fix": "For Step 2, either skip the agent definition reinforcement (the prompt template is the single source of truth the agent reads) or add only a brief mention like 'Batch WebFetch calls in parallel when sources are independent' to the Key Principles list in research-specialist.md."
    },
    {
      "file": "plans/compiled-exploring-snail.md",
      "line_start": 159,
      "line_end": 182,
      "severity": "minor",
      "category": "correctness",
      "finding": "Task 5 adds extended thinking guidance but only to the specialist prompt template and synthesizer agent definition. The specialist agent definition (research-specialist.md) is not listed, which is fine since it defers to the template. However, the synthesizer agent definition (research-synthesizer.md) is a substantial file — the plan says to add thinking guidance 'for the cross-reference phase' but doesn't specify which section of the synthesizer file to insert it in. The synthesizer has 'Phase 1: Assess', 'Phase 2: Fill gaps', 'Phase 3: Frame' — the cross-reference planning fits before Phase 3.",
      "suggested_fix": "Specify insertion point: add the thinking guidance before Phase 3 (Frame) in research-synthesizer.md, or as a preamble to Phase 1 since assessment is where cross-referencing happens."
    },
    {
      "file": "plans/compiled-exploring-snail.md",
      "line_start": 209,
      "line_end": 301,
      "severity": "nitpick",
      "category": "architecture",
      "finding": "Task 7's eval skill dispatches a Sonnet agent via the generic Agent tool, but the skill file doesn't specify which model or tool surface the evaluator needs. The evaluator needs WebFetch (to verify citations) but the skill just says 'Dispatch a Sonnet agent.' The deep-research plugin's agents don't include an evaluator agent definition — this will be an ad-hoc subagent dispatch, which is fine but should be explicit about the tool list.",
      "suggested_fix": "Add to the skill: 'Dispatch with tools: [Read, WebFetch, Write] and model: sonnet' so the executor doesn't have to infer the configuration."
    }
  ]
}
```

---

## Narrative

### First Pass — Structure

The plan is well-organized: 9 tasks with clear dependency ordering (Tasks 1-6 are independent prompt edits, Task 7 is a new capability, Task 8 is deployment, Task 9 is documentation). Each task lists the files it modifies, provides inline content for the changes, and ends with a commit message. The verification checklist at the end covers all deliverables. This is a clean, executable plan.

The scope claim is slightly overstated — the header says "all four research pipelines" but Pipelines B and C are untouched (Finding 2). This is likely intentional (SEO detection is irrelevant to repo research) but should be stated explicitly.

### Second Pass — Implementation Correctness

The plan's assumptions about file structure are accurate. I verified all target files exist at the stated paths and the insertion points described in the plan correspond to real sections in those files. The content to be inserted is well-crafted and consistent with the existing style.

Two correctness concerns: the `skills/` directory doesn't exist (Finding 0), and the specialist agent definition is thin enough that duplicating prompt template content there creates a drift risk (Finding 4).

### Third Pass — Completeness

Task 8 (cache sync) is the weakest task — it's described as a manual copy without a script or file list (Finding 1). Given 7 tasks worth of changes across two repos, a manual sync is where errors creep in.

The eval framework (Task 7) is appropriately scoped as a simple first version. The rubric criteria are well-chosen and the scoring thresholds are reasonable.

### Fourth Pass — Risk

The highest risk is Finding 1 — a bad cache sync means the changes don't take effect at runtime despite being committed to the source repo. The second highest is Finding 0 — the executor may create the skill file but forget the directory, or create both but miss plugin registration.

### Verdict: APPROVED_WITH_NOTES

The plan is sound and ready for execution after addressing the two major findings (skills directory creation and cache sync specification). The remaining findings are refinements that improve execution clarity but won't cause rework if missed.

---

## Coverage
- **Reviewed:** structural completeness, file target accuracy (verified all 12 target files exist), insertion point correctness (spot-checked against actual file contents), scope coverage claims, deployment/sync mechanism, new capability design
- **Not reviewed:** prose quality of the prompt additions (low-effort review), whether the Anthropic lessons were correctly interpreted from the source blog post, whether the deferred items (tool-testing agent, end-state evaluation) were correctly deprioritized
- **Confidence:** HIGH on findings 0-1 (verified against filesystem); HIGH on finding 2 (verified Pipeline B/C files exist and are untouched); MEDIUM on findings 3-6 (insertion point ambiguity depends on executor interpretation)
- **Gaps:** Did not verify the NotebookLM command file's scoping section structure (Finding 5 references it but I only read the first 60 lines); did not check plugin.json to confirm skill discovery mechanism
