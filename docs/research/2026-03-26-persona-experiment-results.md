# Persona Prompting Experiment — Controlled Results

> Internal experiment | 400 observations (2 runs x 10 files x 10 repeats x 2 arms) | Sonnet model

---

## Summary

We ran a controlled A/B experiment testing whether detailed reviewer instructions ("staff-level code reviewer with exacting standards" + domain checklists + structured multi-pass process) improve code defect detection compared to a bare "review this code for bugs" prompt. The answer: **no improvement in recall, and a significant increase in false positives.** The detailed prompt produces the same true positives as the bare prompt but generates 1-2 extra false findings per file.

This confirms the academic literature's predictions (see [Named Persona Research Synthesis](2026-03-19-named-persona-performance.md)) and directly informs how the coordinator pipeline uses its reviewer personas.

---

## Experiment Design

**BASELINE prompt (2 lines):**
> Review this code for bugs and issues. Report all issues you find, including security vulnerabilities, logic errors, performance problems, and error handling gaps.

**SPECIALIST prompt (34 lines):**
> Staff-level code reviewer with exacting standards. [...] Assume the code has defects. A review finding no issues is almost certainly incomplete. [Domain focus list] [Code quality checklist] [Architecture checklist] [Security checklist] [Structured multi-pass review process]

Note: the SPECIALIST prompt had already been stripped of persona identity (no name, no backstory, no personality). This tested **functional review instructions**, not identity dressing. The prior literature review established that identity dressing doesn't help; this experiment tested whether the detailed instructions themselves add value.

**Corpus:** 10 TypeScript/JavaScript files with 32 seeded defects across security, logic, error handling, and performance categories. Ground truth via defect manifest. Automated scoring via Hungarian algorithm bipartite matching (keyword + line-proximity).

**Runs:** Two independent experiments (v1 and v2), each with 10 complete runs across all 10 files and both arms. 200 file-level paired observations per experiment, 400 total.

---

## Results

### Defect detection (recall) — null effect

| Experiment | BASELINE | SPECIALIST | Cohen's d | p |
|---|---|---|---|---|
| v2 (N=100) | 0.855 | 0.856 | +0.008 | 0.94 |
| v1 (N=100) | 0.741 | 0.740 | -0.005 | 0.96 |

The model finds exactly the same defects regardless of prompt complexity. d ~ 0.00 in both runs.

### False positives — SPECIALIST significantly worse

| Experiment | BASELINE FP/file | SPECIALIST FP/file | Cohen's d | p |
|---|---|---|---|---|
| v2 | 8.8 | 10.9 | +0.68 | <0.0001 |
| v1 | 7.8 | 8.9 | +0.36 | 0.0004 |

The detailed prompt generates 1-2 more false positives per file — a medium-to-large effect, replicated across both runs.

### Precision and F1 — SPECIALIST significantly worse

| Metric | v2 BASELINE | v2 SPECIALIST | v2 d | v1 BASELINE | v1 SPECIALIST | v1 d |
|---|---|---|---|---|---|---|
| Precision | 0.263 | 0.219 | -0.64 | 0.255 | 0.225 | -0.28 |
| F1 | 0.388 | 0.340 | -0.57 | 0.371 | 0.335 | -0.24 |

---

## Why This Happens

The "assume the code has defects" priming likely lowers the model's reporting threshold. The detailed checklists (naming, SOLID, separation of concerns, etc.) may encourage the model to generate at least one finding per listed category even when no real issue exists. The effect is analogous to turning up a classifier's sensitivity: same true positive rate, more false positives, worse signal-to-noise ratio.

This is consistent with:
- **Mollick et al. (2025):** Expert personas had no significant impact on factual accuracy across 6 models
- **Zheng et al. (EMNLP 2024):** Personas do not improve performance vs. no-persona control; can hurt
- **"Persona is a Double-Edged Sword" (2024):** Role-playing prompts degrade reasoning in 7/12 datasets

---

## What This Means for the Coordinator Pipeline

### Where we do NOT use personas: mechanical bug detection

The `/bug-sweep` pipeline uses bare Sonnet agents for semantic analysis and Haiku agents for mechanical pattern scanning. No reviewer persona is invoked. This experiment validates that design choice — detailed review framing adds no detection value and would increase noise.

Similarly, the Phase 1 agents in `/code-health` scan for patterns mechanically. The reviewer routing in Phase 3 uses personas, but that's reviewing *known diffs* (a quality-gating task), not hunting for unknown bugs.

### Where we DO use personas: review and planning

The coordinator's personas (Patrik, Sid, Camelia, Fru, Pali, Zoli) are used in two contexts:

1. **`/review-dispatch`** — Quality-gating artifacts (plans, code changes, enriched stubs). The reviewer examines a known artifact and provides structured feedback. This is a judgment task, not a detection task.

2. **`/staff-session`** — Multi-perspective planning debates. Multiple personas argue from different perspectives, a synthesizer adjudicates. This leverages *attention direction diversity* (each persona focuses on different concerns) and *structured disagreement* (conservative vs. ambitious framing).

Neither use case was tested by this experiment. The experiment tested single-pass defect detection on unknown code — a task where the model's analytical capability is the bottleneck, and prompt framing doesn't move the needle.

The next experiment to run is **structured disagreement** — does debate between a conservative and ambitious perspective produce better plans than a single balanced perspective? This directly tests the staff session architecture, which is the primary way personas are used in production. Multi-pass sequential bug detection is deprioritized as it doesn't reflect an actual use case.

### Concrete change made

Removed "Assume the code has defects. A review finding no issues is almost certainly incomplete." from the Patrik (staff-eng) agent prompt. This priming was the most likely cause of the false positive increase and provides no detection benefit.

---

## Experimental Infrastructure

The experiment harness lives in the private repo under `experiments/review-experiments/`. Key components:
- **Corpus:** 10 seeded TypeScript files with 32 known defects and a defect manifest
- **Scoring:** Hungarian algorithm bipartite matching (keyword + line-proximity)
- **Storage:** SQLite databases (`persona_v2.db`, `persona_full.db`) with runs, reviews, scores, and file_scores tables
- **Prompts:** `prompts/persona_review/arm_baseline.md` and `arm_specialist.md`

The infrastructure is reusable for the multi-pass coverage diversity experiment.
