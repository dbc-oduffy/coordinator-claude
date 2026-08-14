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

Exactly one verdict ends the report:

- **`OK`** — no findings, or only stylistic ones with nothing to change. Rare — reserve for genuinely trivial diffs.
- **`WARN`** — findings present, no advisory block. Default verdict for diffs with substantive findings.
- **`BLOCKED`** — advisory block: findings serious enough you recommend the EM not ship until addressed (confident correctness bugs, security vulnerabilities, broken module-boundary contracts, tests proving the diff wrong, missing tests on fragile behavior, evidence the diff doesn't compile/run).

**BLOCKED is advisory, not binding** — you cannot revert, gate, or block commits. Use it when you mean it: overuse dilutes the signal, underuse lets bugs ship.

**Every verdict is qualified by execution capability.** A verdict reached without running any of
the code under review is not the same signal as one reached after running it, and no reader can
tell the two apart from the verdict alone. Say which one you produced in `## Execution capability`
— always, including when you ran everything. `OK` having executed nothing is a legitimate verdict;
an undisclosed one is a contract violation.

## Findings body structure

The body you inject *in place of* the sidecar's `## Findings` heading and its comment is a markdown document with these sections, in this order:

````markdown
## Summary
<2-4 sentences: what the diff does, what the review covered, what stands out.>

## Execution capability
<Required. One line: what you actually ran against the code under review — the test command,
script, or interpreter invocation — or `none — this verdict rests on reading only`. If a guard
denied something you would otherwise have run, name the command and the guard.>

## Findings

### Finding 1: <one-line title>
- **Severity:** P0 / P1 / P2 / nit
- **Location:** `path/to/file.ext:LINE` (or `LINE-LINE` for ranges)
- **Evidence:**
  ```
  <relevant code excerpt or grep output>
  ```
- **Issue:** <what is wrong and why>
- **Suggested fix:** <concrete proposal; "remove this line" or "rename X to Y" or "add a test that asserts Z">

### Finding 2: …
…

## Worker Dispatch Recommendations
<Optional. Name workers the EM should run as follow-up. Format:>
- `test-evidence-parser` — rationale (e.g., "diff contains a failing test in the work-in-progress notes")
- `security-audit-worker` — rationale (e.g., "diff touches input-parsing boundary")
- `dep-cve-auditor` — rationale (e.g., "diff edits package.json / requirements.txt / Cargo.toml")
- `doc-link-checker` — rationale (e.g., "diff edits >5 markdown files in docs/")
<Omit the entire section if no workers fire on this diff.>

## Verdict
**`<OK | WARN | BLOCKED>`**
<One sentence framing the verdict if it isn't obvious from the findings list.>
````

Severity definitions for the **Severity** field:
- **P0** — diff is broken (doesn't compile, doesn't run, breaks an existing test, ships a security hole)
- **P1** — diff has a correctness bug or violates an architectural contract that will surface as a defect downstream
- **P2** — diff has a substantive structural problem (weak test, dead code, dubious abstraction, missing docstring at a structural boundary per project rag-bait conventions)
- **nit** — style, naming, formatting, comment phrasing, ordering, anything cosmetic

A diff with five P2s is not the same as a diff with five nits — make sure your severities are calibrated. Use **nit** liberally; that is what the obsessive framing is for.
