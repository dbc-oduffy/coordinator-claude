---
name: coordinator:eval-output
description: Score a research output against the 5-criteria eval rubric. Dispatches a Sonnet evaluator.
---

# Evaluate Research Output

## Usage
/coordinator:eval-output <path-to-research-output>

## Process
1. Read the eval rubric at `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/eval-rubric.md`
<!-- Review: code-reviewer — F3: eval-rubric.md is at pipelines/deep-research/ post-C4 merge; old flat path was dead -->
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
