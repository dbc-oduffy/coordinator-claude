# Anthropic Multi-Agent Lessons — Pipeline Improvements

> **For Claude:** REQUIRED SUB-SKILL: Use /execute-plan to implement this plan task-by-task.

**Goal:** Apply lessons from Anthropic's multi-agent research system blog post to improve research Pipelines A (internet) and D (NotebookLM), plus universal improvements (parallel tool calling, extended thinking) to Pipeline B (repo) specialists. Pipeline C (structured) is excluded — its verifier agents have a different interaction model where these heuristics don't apply.

**Status:** Complete — all 9 tasks executed 2026-04-01

**Architecture:** Prompt-level improvements to scout and specialist agents across both repos (`X:/deep-research-claude` for Pipelines A/B, `X:/coordinator-claude/plugins/notebooklm` for Pipeline D). One new capability (LLM-as-judge eval). No structural/architectural changes — the pipelines are sound; we're sharpening the prompts based on Anthropic's production learnings.

**Review:** Reviewed by Patrik on 2026-04-01. 2 major + 4 minor findings applied below. Ready for execution.

**Tech Stack:** Markdown agent definitions, prompt templates, JSON eval specs

**Source:** `X:/coordinator-claude/docs/research/2026-04-01-anthropic-multi-agent-alignment.md` + `2026-04-01-anthropic-claims-verification.md`

---

## Task 1: Scout source quality heuristics — SEO farm detection

**Problem:** Anthropic found agents "consistently chose SEO-optimized content farms over authoritative but less highly-ranked sources like academic PDFs or personal blogs." Our scouts currently say "do NOT make quality judgments" (Pipeline A) or prioritize by media type only (NotebookLM). Neither detects SEO farms.

**Key insight:** This is a Haiku-appropriate mechanical check, not a quality judgment. Haiku can flag indicators without deep analysis.

**Files:**
- Modify: `X:/deep-research-claude/agents/research-scout.md`
- Modify: `X:/deep-research-claude/pipelines/scout-prompt-template.md`
- Modify: `X:/coordinator-claude/plugins/notebooklm/agents/research-scout.md`
- Modify: `X:/coordinator-claude/plugins/notebooklm/pipelines/scout-prompt-template.md`

**Step 1:** In Pipeline A scout agent definition (`research-scout.md`), add a new section after "Vet accessibility" (step 3):

Add as additional sub-bullets under step 3's existing WebFetch accessibility checklist (after paywall detection, before date extraction):
```
   - SEO farm indicators (flag if 3+ present):
     * Generic domain name (e.g., techblogpro.com, datasciencecentral.com)
     * Excessive ads/popups detected in page content
     * Content reads as keyword-stuffed or template-generated
     * No clear author attribution
     * Title is clickbait-formatted ("Top 10 Best..." "Ultimate Guide to...")
   - If flagged: mark source as `SEO-suspect: YES` in corpus output
```

Update the "What You Do NOT Do" section — change "Assess content quality (AI-generated detection, forum quality — that's specialist judgment)" to:
```
- Make deep quality judgments (AI-generated detection, analytical quality — that's specialist judgment)
- NOTE: You DO flag mechanical SEO indicators (see step 3). This is pattern-matching, not judgment.
```

**Step 2:** Add `SEO-suspect` field to the corpus output format, positioned after `Type` and before `Relevant topics`:
```
- **SEO-suspect:** YES / NO (flag if 3+ indicators present)
```

**Step 3:** Apply the same changes to the scout prompt template (`scout-prompt-template.md`), mirroring the agent definition additions.

**Step 4:** For NotebookLM scout (`research-scout.md`), add equivalent SEO detection to the accessibility vetting section. NotebookLM scout already does more quality assessment (media type prioritization), so this fits naturally.

**Step 5:** Update NotebookLM scout prompt template similarly.

**Step 6:** Commit: `scouts: add SEO farm detection heuristics (Anthropic lesson)`

---

## Task 2: Scout "start wide, then narrow" search strategy

**Problem:** Anthropic found "agents often default to overly long, specific queries that return few results." Their fix: "start with short, broad queries, evaluate what's available, then progressively narrow focus." Our scouts currently execute queries from scope.md mechanically — no search strategy guidance.

**Files:**
- Modify: `X:/deep-research-claude/agents/research-scout.md`
- Modify: `X:/deep-research-claude/pipelines/scout-prompt-template.md`
- Modify: `X:/coordinator-claude/plugins/notebooklm/agents/research-scout.md`
- Modify: `X:/coordinator-claude/plugins/notebooklm/pipelines/scout-prompt-template.md`

**Step 1:** In Pipeline A scout agent definition, add a search strategy section after "Execute searches" (step 2):

```
   **Search strategy — start wide, then narrow:**
   - First pass: use SHORT, BROAD queries from scope.md (2-4 words). These cast a wide net.
   - Evaluate what's available: note which topic areas have abundant results vs. sparse.
   - Second pass (if time permits): for sparse areas, try REFINED queries — add qualifiers,
     use different phrasings, try related terms.
   - Do NOT use long, specific queries upfront — they return few results and miss relevant sources.
   - Example: "agent orchestration" first, then "multi-agent coordination patterns LLM" second.
```

**Step 2:** Apply equivalent guidance to scout prompt template.

**Step 3:** For NotebookLM scout, add search strategy guidance tailored to media discovery:
```
   **Search strategy — start wide, then narrow:**
   - First pass: broad topic + media type ("agent orchestration YouTube", "LLM research podcast")
   - Second pass: narrow by specifics if first pass is thin ("multi-agent Claude coordination talk 2025")
   - Do NOT start with long specific queries — they miss good content with different titles.
```

**Step 4:** Update NotebookLM scout prompt template.

**Step 5:** Commit: `scouts: add broad-to-narrow search strategy (Anthropic lesson)`

---

## Task 3: Specialist source quality hierarchy with SEO awareness

**Problem:** Specialists already have a source quality hierarchy (`Primary docs > Peer-reviewed > Well-maintained OSS > Blog > Forum > AI-generated`), but they don't know to treat scout-flagged SEO-suspect sources with extra scrutiny.

**Files:**
- Modify: `X:/deep-research-claude/pipelines/specialist-prompt-template.md`
- Modify: `X:/coordinator-claude/plugins/notebooklm/agents/research-worker.md`

**Step 1:** In Pipeline A specialist prompt template, section "2. Deep-Read and Verify," add after the source quality hierarchy:

```
- **SEO-suspect sources:** If the scout flagged a source as `SEO-suspect: YES`,
  treat it with extra scrutiny. Do NOT use it as a primary source — only use it
  to corroborate claims from higher-quality sources. If it's your only source
  for a claim, mark confidence as LOW and note the SEO flag.
```

**Step 2:** In NotebookLM worker, add equivalent awareness of SEO-suspect sources in the ingestion phase — workers should note if a source appeared SEO-suspect in the scout corpus and weight findings accordingly.

**Step 3:** Commit: `specialists: add SEO-suspect source handling (Anthropic lesson)`

---

## Task 4: Parallel tool calling instruction for specialists

**Problem:** Anthropic found parallel tool calling "cut research time by up to 90% for complex queries." Their subagents use "3+ tools in parallel." Our specialists don't have explicit instruction to parallelize tool calls — they likely run sequential WebFetch calls by default.

**Files:**
- Modify: `X:/deep-research-claude/pipelines/specialist-prompt-template.md`
- Modify: `X:/deep-research-claude/agents/research-specialist.md` (brief mention only)
- Modify: `X:/deep-research-claude/agents/repo-specialist.md` (Pipeline B — universal improvement)
- Modify: `X:/coordinator-claude/plugins/notebooklm/agents/research-worker.md`

**Step 1:** In Pipeline A specialist prompt template, add to section "2. Deep-Read and Verify" adjacent to the existing "Use WebFetch to read the most promising sources in full" instruction:

```
- **Parallel fetching:** When you have multiple sources to deep-read, fetch them
  in parallel (multiple WebFetch calls in a single message) rather than sequentially.
  This significantly reduces research time. Group 3-5 fetches per batch.
```

**Step 2:** In the specialist agent definition (`research-specialist.md`), add only a brief mention to the Key Principles list (the prompt template is the single source of truth — avoid duplicating detailed content):
```
- **Batch WebFetch calls in parallel** when sources are independent — see prompt template for details
```

**Step 2b:** In Pipeline B repo-specialist agent definition (`repo-specialist.md`), add equivalent parallel Read guidance — repo specialists read project files rather than web sources, but parallel Read calls still apply.

**Step 3:** For NotebookLM workers — note that `source_add` must remain sequential (MCP constraint), but `notebook_query` calls for different questions CAN be parallelized. Add:

```
- **Parallel querying:** When running research questions, you may batch multiple
  notebook_query calls in a single message if the questions are independent.
  Do NOT parallelize source_add — ingestion must be sequential.
```

**Step 4:** Commit: `specialists: add parallel tool calling guidance (Anthropic lesson)`

---

## Task 5: Extended thinking guidance for specialists

**Problem:** Anthropic uses extended thinking as a "controllable scratchpad" — lead agents plan in thinking, subagents evaluate tool results in interleaved thinking. Our agents don't explicitly instruct thinking usage, leaving it to model defaults.

**Files:**
- Modify: `X:/deep-research-claude/pipelines/specialist-prompt-template.md`
- Modify: `X:/deep-research-claude/agents/research-synthesizer.md`

**Step 1:** In Pipeline A specialist prompt template, add to section "2. Deep-Read and Verify" under "Forced reflection":

```
- **Use extended thinking deliberately:** After reading each source, use your thinking
  to plan your next move: What gaps remain? Which peers need to hear this? Does this
  change my understanding? This structured reflection improves both reasoning quality
  and efficiency — Anthropic's production data confirms improved instruction-following
  and efficiency from thinking-as-scratchpad.
```

**Step 2:** In synthesizer agent definition (`research-synthesizer.md`), add thinking guidance as a preamble to Phase 1 (Assess) — this is where cross-referencing happens:

```
- **Use extended thinking for cross-reference planning:** Before writing anything,
  use thinking to map: which specialist findings reinforce each other, where
  contradictions exist, what the coverage gaps are. Plan the document structure
  in thinking before writing. This structured pre-planning improves coherence
  and reduces rework in later phases.
```

**Step 3:** Commit: `agents: add extended thinking guidance (Anthropic lesson)`

---

## Task 6: Explicit delegation structure in EM scoping

**Problem:** Anthropic found that vague subagent instructions ("research the semiconductor shortage") led to duplicated work and misinterpretation. They require: objective, output format, tool/source guidance, and clear task boundaries. Our specialist prompt template already has most of this, but the EM scoping phase (in the command files) could reinforce it.

**Files:**
- Modify: `X:/deep-research-claude/commands/web.md`
- Modify: `X:/coordinator-claude/plugins/notebooklm/commands/research.md`

**Step 1:** In the Pipeline A `/web` command, find the specialist dispatch section. Add a scoping checklist item:

```
- [ ] Each specialist assignment has: (a) specific objective, (b) output format reference,
      (c) tool/source guidance, (d) clear task boundaries vs. peers. Vague assignments
      ("research X") lead to duplication — be specific about what each specialist SHOULD
      and SHOULD NOT cover.
```

**Step 2:** Add equivalent checklist item to NotebookLM `/research` command's scoping section.

**Step 3:** Commit: `commands: add delegation clarity checklist (Anthropic lesson)`

---

## Task 7: LLM-as-judge eval framework

**Problem:** We have no automated quality evaluation for pipeline outputs. Anthropic converged on a single LLM call scoring 0.0-1.0 across 5 criteria (factual accuracy, citation accuracy, completeness, source quality, tool efficiency). They started with ~20 test queries.

This is a new capability. Keep it simple — a skill that runs an eval on a completed research output.

**Files:**
- Create: `X:/deep-research-claude/pipelines/eval-rubric.md`
- Create: `X:/deep-research-claude/skills/` (new directory — skills are auto-discovered from `skills/` by the plugin framework, no plugin.json registration needed)
- Create: `X:/deep-research-claude/skills/eval-output.md`

**Step 0:** Create the skills directory:
```bash
mkdir -p X:/deep-research-claude/skills/
```

**Step 1:** Create the eval rubric (`eval-rubric.md`):

```markdown
# Research Output Evaluation Rubric

Adapted from Anthropic's multi-agent research system eval methodology.
Used by the /eval-output skill to score pipeline outputs.

## Criteria (each scored 0.0-1.0)

### 1. Factual Accuracy
Do claims in the output match the cited sources? Are there unsupported assertions?
- 1.0: All claims verified against cited sources, no unsupported assertions
- 0.7: Most claims verified, minor unsupported qualifications
- 0.4: Several claims lack source support or contradict sources
- 0.0: Pervasive unsupported or contradicted claims

### 2. Citation Accuracy
Do cited sources actually say what the output claims they say?
- 1.0: All citations accurately represent source content
- 0.7: Most citations accurate, minor misrepresentations
- 0.4: Several citations misrepresent sources
- 0.0: Citations are decorative, not substantive

### 3. Completeness
Are all aspects of the research question covered?
- 1.0: All requested aspects covered with depth
- 0.7: Most aspects covered, minor gaps acknowledged
- 0.4: Significant aspects missing without acknowledgment
- 0.0: Major portions of the question unanswered

### 4. Source Quality
Did the research use authoritative, primary sources over secondary/SEO content?
- 1.0: Primarily official docs, peer-reviewed, primary sources
- 0.7: Mix of primary and quality secondary sources
- 0.4: Heavy reliance on blogs, forums, or SEO content
- 0.0: Sources are unreliable, outdated, or AI-generated

### 5. Source Diversity
Did the research present multiple perspectives, including criticism?
- 1.0: Multiple viewpoints with adversarial/critical sources included
- 0.7: Some diversity, adversarial perspective present but thin
- 0.4: Single perspective dominates, criticism absent
- 0.0: Echo chamber — only confirming sources used

## Scoring
- **Pass:** Average >= 0.7 AND no single criterion below 0.4
- **Marginal:** Average 0.5-0.7 OR one criterion below 0.4
- **Fail:** Average < 0.5 OR two+ criteria below 0.4

## Usage
The /eval-output skill dispatches a Sonnet agent with this rubric plus
the research output. The agent reads the output, samples 3-5 citations
for verification (WebFetch), and scores each criterion with evidence.
```

**Step 2:** Create the eval skill (`skills/eval-output.md`):

```markdown
---
name: eval-output
description: Score a research output against the 5-criteria eval rubric (factual accuracy, citation accuracy, completeness, source quality, source diversity). Dispatches a Sonnet evaluator.
---

# Evaluate Research Output

## Usage
/eval-output <path-to-research-output>

## Process
1. Read the eval rubric at `${CLAUDE_PLUGIN_ROOT}/pipelines/eval-rubric.md`
2. Read the research output at the provided path
3. Dispatch a Sonnet agent (model: sonnet, tools: Read, WebFetch, Write) with:
   - The rubric
   - The research output
   - Instruction to: read the output, sample 3-5 cited URLs via WebFetch to verify citation accuracy, score each of the 5 criteria with a 0.0-1.0 score and 2-3 sentence justification, provide overall pass/marginal/fail grade
4. Present the scores to the PM

## Notes
- This is a post-hoc quality check, not a gate. Use it to calibrate prompt improvements.
- Start by running it on recent pipeline outputs to establish a baseline.
- Anthropic found a single LLM call with a single prompt was most consistent.
```

**Step 3:** Commit: `eval: add LLM-as-judge evaluation framework (Anthropic lesson)`

---

## Task 8: Sync improvements to coordinator-claude cache

**Problem:** The deep-research plugin is now standalone (`X:/deep-research-claude`), but the coordinator-claude cache at `~/.claude/plugins/cache/coordinator-claude/deep-research/1.0.0/` is what's actually loaded at runtime. Changes to the standalone repo need to be synced.

**Files:**
- Modify: `X:/deep-research-claude/.claude-plugin/plugin.json` — bump version to reflect improvements
- Sync: All modified files from Tasks 1-7 to cache

**Step 1:** Bump version in `plugin.json` (1.0.0 → 1.1.0) with changelog note referencing Anthropic lessons.

**Step 2:** Create new cache directory and mirror the full plugin:
```bash
# Clean mirror — ensures no stale files from old version
mkdir -p ~/.claude/plugins/cache/coordinator-claude/deep-research/1.1.0/
cp -r X:/deep-research-claude/{agents,commands,pipelines,skills,CLAUDE.md} \
      ~/.claude/plugins/cache/coordinator-claude/deep-research/1.1.0/
```

**Step 3:** Remove old cache version:
```bash
rm -rf ~/.claude/plugins/cache/coordinator-claude/deep-research/1.0.0/
```

**Step 4:** Update `~/.claude/plugins/installed_plugins.json` — change deep-research version path from `1.0.0` to `1.1.0`.

**Step 5:** Verify the sync by spot-checking one modified file:
```bash
diff X:/deep-research-claude/agents/research-scout.md \
     ~/.claude/plugins/cache/coordinator-claude/deep-research/1.1.0/agents/research-scout.md
```
Should show no differences.

**Step 6:** Commit in both repos: `deep-research v1.1.0: Anthropic multi-agent lessons applied`

---

## Task 9: Update research doc with implementation notes

**Files:**
- Modify: `X:/coordinator-claude/docs/research/2026-04-01-anthropic-multi-agent-alignment.md`

**Step 1:** Add a "What We Adopted" section after "What We Could Learn From Them":

```markdown
## What We Adopted (2026-04-01)

Based on this analysis, we implemented the following improvements:

1. **SEO farm detection in scouts** — Mechanical flag for SEO content farm indicators,
   with specialists treating flagged sources with extra scrutiny (Tasks 1, 3)
2. **Broad-to-narrow search strategy** — Scouts now start with short broad queries
   before narrowing (Task 2)
3. **Parallel tool calling** — Specialists instructed to batch WebFetch calls (Task 4)
4. **Extended thinking as scratchpad** — Specialists use thinking for structured
   reflection after each source (Task 5)
5. **Delegation clarity checklist** — EM scoping now requires specific objectives,
   boundaries, and output format per specialist (Task 6)
6. **LLM-as-judge eval** — New /eval-output skill scores pipeline outputs on 5
   criteria adapted from Anthropic's methodology (Task 7)

Items deferred:
- **Tool-testing agent** — Systematic testing of MCP tool descriptions. Valuable but
  large scope; tracked for future work.
- **End-state evaluation for executors** — Evaluating final state rather than process.
  Relevant to coordinator executors, not research pipelines.
```

**Step 2:** Commit: `research doc: add implementation tracking section`

---

## Verification

After all tasks complete:

- [ ] Pipeline A scout has SEO detection + broad-to-narrow search strategy
- [ ] Pipeline A specialist has SEO-suspect handling + parallel fetch instruction + thinking guidance
- [ ] Pipeline B repo-specialist has parallel Read instruction
- [ ] NotebookLM scout has SEO detection + broad-to-narrow search strategy
- [ ] NotebookLM worker has SEO-suspect handling + parallel query instruction
- [ ] Pipeline A synthesizer has thinking guidance for cross-reference
- [ ] `skills/` directory exists in deep-research-claude
- [ ] Both commands have delegation clarity checklist
- [ ] Eval rubric exists at `pipelines/eval-rubric.md`
- [ ] Eval skill exists at `skills/eval-output.md`
- [ ] Deep-research plugin version bumped
- [ ] Cache synced
- [ ] Research doc updated with adoption notes
- [ ] Run `/eval-output` on one recent pipeline output to validate the eval framework works
