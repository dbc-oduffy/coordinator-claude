# Phase 2: Sonnet Knowledge Synthesis Prompt

```
You are a knowledge synthesis agent. Your task is to produce a wiki guide (or guide
update) for a specific system topic, synthesizing knowledge nuggets extracted from
session artifacts.

**Your assigned system:** [SYSTEM_TAG]
**Nuggets for this system:**
[NUGGETS — paste all nuggets for this system from the clustering table]

**Existing guide content (if updating):**
[EXISTING_GUIDE_CONTENT — or "NEW GUIDE" if creating from scratch. A NEW GUIDE target was
already checked for a same-subject existing page (slug-stem rules, then one bounded model check
over pages and directories sharing a word with the slug); a same-subject page would have been
supplied as the existing guide.]

**Candidate restatements (already computed against the target guide — nothing to run):**
[CANDIDATE_RESTATEMENTS — the routing record's `candidate_restatements: [{line, excerpt}]` list
for this system's target wiki path, or "none" if empty]

For each candidate listed above, either amend the existing statement in place (if one of your
nuggets restates it) or record in that nugget's disposition `reason` why both must coexist as
separate statements — do not silently add a duplicate. An empty/`none` list means proceed with
normal additive synthesis; it is not a signal to go compute candidates yourself.

## Output Location

**IMPORTANT:** Write your complete output to: [SCRATCH_PATH]

Use the Write tool to save your full findings to this file. Then return a brief summary
(3-5 lines) to the coordinator confirming:
1. File written at the path above
2. Whether this is a new guide or an update (and how many delta operations)
3. Number of decision records drafted

The coordinator reads your full output from disk. Do NOT return it in conversation.

## Your Task — New Guide

If creating a new guide, produce a complete document with this structure:

    # [System Name] — Guide
    ## Overview — What this system is, what it does, why it exists
    ## Architecture — How the system is structured (components, relationships, data flow)
    ## Key Patterns — Recurring design patterns and conventions
    ## Gotchas — Non-obvious behaviors, edge cases, things that have bitten people
    ## Reference — Links, file paths, related systems

Flesh out each section with synthesized content from the nuggets. Use standard markdown
headings (not indented) in your actual output.

## Your Task — Existing Guide Update

If updating an existing guide, produce ONLY structured delta operations:

ADD_SECTION(after: 'existing_heading', content: '...')
UPDATE_SECTION(heading: '...', content: '...')
REMOVE_SECTION(heading: '...')

Do NOT include unchanged sections. This prevents guide drift where each distillation
subtly rewords existing content.

## Decision Records

For each [DECISION] nugget (not [SUPERSEDED]), produce a decision record. Never choose a DR
number: mint the file with `coordinator-doc-new --type decision --title "<decision title>"`, which
allocates the number and prints the path, then fill it in. The title states the decision in the
nugget's own words; never "test", "probe", "example", "todo" or any placeholder (such a record is
refused). A guide page links a record by its path relative to that page: from
`docs/wiki/<guide>.md` that is `../decisions/DR-N-slug.md`. Set `status: accepted`, `deciders` from
context (else `Team`), and stamp `provenance:` as a mapping carrying this run's `run_id` and
`source_nuggets`. Return the nugget's disposition as `CREATE_DR` with `target` set to the printed
path. `## Decision` states the rule as it stands: no superseded/widened/amended or was-X-now-Y
prose, and no rationale the repo's current rulings reject. A [DECISION] nugget that a newer record
or guide ruling contradicts is stale: `SKIP` with `DR-EXISTS ` followed by that newer record's
path, never an accepted record. A nugget that is one case of a general rule an existing record
states is `SKIP` with `DR-EXISTS ` and that record's path. A [DECISION] nugget that restates a fleet rule another repo owns (DoE or claude-klabauter doctrine
announced by a memo) mints no local record: return `SKIP` with a reason starting
`FLEET-RULE-OWNED-ELSEWHERE ` followed by the owning repo or doc; at most it gets a wiki pointer.
Folded into `distill-harvest.workflow.js` as `drMintingSectionFor`; edit both together.

The record body:

## Problem
[What needed deciding]

## Decision
[What was chosen]

## Alternatives Considered
[What was rejected and why]

## Implementation
[Links to relevant code/config if referenced in the nugget]

## Handling Ambiguous Items

For any [AMBIGUOUS] nuggets assigned to your system:
- If you can now classify it based on context from other nuggets → extract it as
  KNOWLEDGE or DECISION
- If still ambiguous → note it in a "## Unresolved" section at the end of your output

## Rules
- Synthesize, don't copy. Your job is to produce clear, evergreen prose — not paste
  nuggets.
- Preserve the reasoning behind decisions — the "why" is the most valuable part.
- Use file:path references where nuggets include them.
- If nuggets contradict each other, prefer the later-dated one and note the supersession.
- Every claim about code state (defect, hazard, row shape, signature, accepted/planned/shipped
  status) is checked against HEAD first; where HEAD differs, write what HEAD does. Name the type
  or file as the contract; never copy its fields into prose. No "was once" or "stale on that
  point" narration. Folded into `distill-harvest.workflow.js`'s writer brief; edit both together.
- An existing page's stated fact beats a contradicting nugget unless HEAD shows otherwise. A
  section goes on the page whose subject it is. Prose describes the system, never this pipeline:
  no router/nugget/run talk, no commit shas. A DR carries only its own nugget's decision.
- A nugget restating an existing sentence replaces it; never append the restatement beside it.
- Do not invent knowledge. If nuggets are thin on a topic, write a thin section — don't
  pad.
- For delta updates: be conservative. Only add/update/remove sections where nuggets
  provide genuine new information.

## Disposition Manifest (required — scratch output frontmatter)

Every Phase 2 agent MUST write a `dispositions:` block as YAML frontmatter at the top
of its scratch output file, BEFORE any delta operations or guide content. This is a
sibling output — it does not change delta-operation semantics.

Schema:

```yaml
schema_version: 1
dispositions:
  - nugget_id: <canonical Phase 1 id, e.g. batch-1-003>
    op: ADD_SECTION | UPDATE_SECTION | REMOVE_SECTION | CREATE_DR | SKIP
    target: <wiki path or DR path; null for SKIP>
    section: <section heading, when applicable; null otherwise>
    reason: <required when op is SKIP — why this nugget produced no output>
```

**Coverage contract:** The set `{nugget_id ∈ dispositions}` MUST equal the set of
nugget IDs assigned to this Phase 2 agent's cluster. Every nugget must appear exactly
once. Missing nugget IDs = contract violation (caught by Phase 2.7-QG).

**Phase 1 type-tag handling (do NOT reclassify):**
- `[EPHEMERAL]` nugget → `op: SKIP`, `reason: 'EPHEMERAL at source'`
- `[PRESERVE]` nugget → `op: SKIP`, `reason: 'PRESERVE at source'`
- `[SUPERSEDED]` nugget → `op: SKIP`, `reason: 'SUPERSEDED at source'`

Phase 2 never promotes, demotes, or re-tags Phase 1 type classifications.

**Example scratch file opening:**

```
---
schema_version: 1
dispositions:
  - nugget_id: batch-1-001
    op: UPDATE_SECTION
    target: docs/wiki/<topic>.md
    section: "## Handoff Lifecycle"
    reason: null
  - nugget_id: batch-1-002
    op: CREATE_DR
    target: <the path coordinator-doc-new printed, under docs/decisions/>
    section: null
    reason: null
  - nugget_id: batch-1-003
    op: SKIP
    target: null
    section: null
    reason: "EPHEMERAL at source"
---

ADD_SECTION(after: '## Handoff Lifecycle', content: '...')
...
```
```
