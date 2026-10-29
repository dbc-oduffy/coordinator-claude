<!-- canonical source for review-findings-body-contract — edit here, then run bin/verify-snippet-sync review-findings-body-contract --fix -->
<!-- consumers: fixed list in snippets/registry.toml [snippet.review-findings-body-contract] -->
<!-- INJECTED block, not paste-governed: assembled into the dispatched child prompt at dispatch -->
<!-- time via the `contract_blocks:` grammar, keyed by `subagent_type`. Carries the findings-body -->
<!-- markdown template, the P0/P1/P2/nit severity schema, and the verdict enum for -->
<!-- `review-findings`-typed reviewers — the output-shape specification. Not to be -->
<!-- reworded, merged, reordered, or "tidied" relative to its source — a reworded severity -->
<!-- definition is a silent contract change to every review this agent has ever produced. -->
<!-- PLACEHOLDER-FREE BY CONSTRUCTION: do not add any placeholder here. The closed set is -->
<!-- {kind, sidecar_path, subagent_type} and this block needs none of them; the closed placeholder -->
<!-- set is enforced by coordinator/tests/test_contract_blocks.py. -->

## Verdict enum

One verdict ends the report: `OK` (no findings, or only stylistic ones; rare), `WARN` (findings; the default), `BLOCKED` (the EM should not ship until addressed). Every verdict is qualified by execution capability.

## Findings body structure

The body replacing the sidecar's `## Findings` heading has these sections, in order:

````markdown
## Summary
<2-4 sentences.>

## Execution capability
<Required. One line: what you ran against the code, or `none — this verdict rests on reading only`. Name any command a guard denied.>

## Findings

### Finding 1: <one-line title>
- **Severity:** P0 (broken) / P1 (correctness) / P2 (structural) / nit (cosmetic)
- **Location:** `path/to/file.ext:LINE` (or `LINE-LINE` for ranges)
- **Evidence:**
  ```
  <relevant code excerpt or grep output>
  ```
- **Issue:** <what is wrong and why>
- **Suggested fix:** <concrete proposal>

### Finding 2: …

## Verdict
**`<OK | WARN | BLOCKED>`**
<One sentence if not obvious.>
````