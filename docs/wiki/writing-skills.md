# Writing Skills — TDD Applied to Process Documentation

> Spec backlink: `docs/plans/2026-05-06-skill-budget-structural-cleanup.md` (demote writing-skills → wiki).

Writing skills is Test-Driven Development applied to process documentation. Skills live at
`${CLAUDE_PLUGIN_ROOT}/skills/{skill-name}/SKILL.md`. Write pressure scenarios with subagents
(test cases), watch them fail (baseline), write the skill, watch tests pass, refactor to close
loopholes.

**Core principle:** If you didn't watch an agent fail without the skill, you don't know if the
skill teaches the right thing.

---

## Overview

**What is a Skill?** A reference guide for proven techniques, patterns, or tools. Skills are
reusable; they are NOT narratives about how you solved a problem once.

## Decision-Tree Skills vs Narrative Skills

Coordinator skills come in two shapes. **Narrative skills** (the original pattern) contain prose explaining principles and examples — the EM is expected to absorb them at boot. **Decision-tree skills** (new pattern from 2026-05-06) contain a tree the EM walks at trigger time, with each branch terminating in a single concrete action.

For skills about *how to use the coordinator workflow* (planning, reviewing, etc.), prefer the decision-tree shape. For wiki pages containing long-form reference doctrine, keep as narrative. See `docs/wiki/super-skill-architecture.md` for the full decision-tree skill contract (7 rules).

### TDD Mapping

| TDD Concept | Skill Creation |
|---|---|
| Test case | Pressure scenario with subagent |
| Production code | SKILL.md |
| RED | Agent violates rule without skill (baseline) |
| GREEN | Agent complies with skill present |
| Refactor | Close loopholes while maintaining compliance |

---

## When to Create a Skill

**Anti-proliferation gate — check FIRST.** Search the skills directory for related names. If a
related skill exists, **extend it**. New files need justification.

**Create when:** the technique wasn't intuitively obvious, you'd reference it across projects, the
pattern applies broadly, no existing skill covers the territory.

**Don't create for:** one-off solutions, well-documented standard practices, project-specific
conventions (use CLAUDE.md), mechanical constraints enforceable with regex/validation.

### Skill Types

- **Technique** — concrete method with steps (`condition-based-waiting`, `root-cause-tracing`)
- **Pattern** — way of thinking (`flatten-with-flags`, `test-invariants`)
- **Reference** — API docs, syntax guides

---

## SKILL.md Structure

### Directory Layout

```
skills/
  skill-name/
    SKILL.md              # Main reference (required)
    supporting-file.*     # Heavy reference or reusable tools only
```

Flat namespace, all skills searchable. Inline principles, concepts, and short code patterns
(<50 lines). Separate files for heavy reference (100+ lines) or reusable scripts/templates.

### Frontmatter

Only `name` and `description` supported. Max 1024 chars total.

- `name`: letters, numbers, hyphens only.
- `description`: third-person, **describes ONLY when to use, NOT what it does** — start with "Use when..."

**The `name:` field controls bare slash invocation.** Plugin skills/commands without `name:` in frontmatter require the fully-qualified `/<plugin>:<skill>` form (e.g. `/coordinator:pickup`). Adding `name: <slug>` to the frontmatter exposes the skill as `/<slug>` bare in the slash picker, while the qualified form continues to work. Verified empirically 2026-05-09 across both `commands/*.md` and `skills/<name>/SKILL.md` surfaces — same mechanism for both.

- **Default to adding `name:`** for any skill you'd type often. The `/coordinator:` prefix is friction; the bare form is the natural shape.
- **Omit `name:` to avoid collisions across plugins.** If two enabled plugins both expose a generic verb (`/setup`, `/doctor`), keep at least the non-primary ones qualified. Coordinator's `/coordinator:setup` is intentionally prefixed because holodeck and deep-research also have setup commands.
- **Scheduled wakeups and skill-to-skill calls** that reference a bare `/name` only resolve once `name:` is set. A `/loop` or scheduled invocation written against the bare form will fail with "Unknown command" until the prefix is added or `name:` is set in the target skill.

```markdown
---
name: skill-name-with-hyphens
description: Use when [specific triggering conditions and symptoms]
---

# Skill Name

## Overview
What is this? Core principle in 1-2 sentences.

## When to Use
Bullet list with symptoms/use cases. When NOT to use.

## Core Pattern (techniques/patterns)
Before/after comparison.

## Quick Reference
Table or bullets for scanning.

## Implementation
Inline code OR link to file.

## Common Mistakes
What goes wrong + fixes.
```

---

## Description Discipline (Claude Search Optimization)

**Description = When to Use, NOT What the Skill Does.** Empirically: descriptions that summarize
workflow create a shortcut Claude takes instead of reading the skill body. A description saying
"code review between tasks" caused Claude to do ONE review even though the skill flowchart
specified TWO. When changed to just triggering conditions, Claude correctly read the flowchart.

```yaml
# BAD: workflow summary creates shortcut
description: Use when executing plans - dispatches subagent per task with code review between tasks

# GOOD: triggering conditions only
description: Use when executing implementation plans with independent tasks
```

**Keyword coverage** — use words Claude would search for: error messages ("Hook timed out"),
symptoms ("flaky", "hanging"), synonyms ("timeout/hang/freeze"), tool names.

**Descriptive naming** — active voice, verb-first. `creating-skills` not `skill-creation`.
`condition-based-waiting` not `async-test-helpers`.

**Token efficiency** — frequently-loaded skills should be <200 words total; others <500. Move flag
details to `--help`. Cross-reference rather than duplicate. Compress examples ruthlessly. Verify
with `wc -w`.

**Cross-referencing other skills** — name only with explicit requirement marker:
- `**REQUIRED BACKGROUND:** see docs/wiki/test-driven-development.md`
- Do NOT use `@skills/...` syntax — it force-loads files immediately, burning context.

### Flowcharts

Use ONLY for: non-obvious decision points, process loops where you might stop too early, "when to
use A vs B" decisions. Never for reference material (use tables), code examples (use markdown), or
linear instructions (use numbered lists).

### Code Examples

One excellent example beats many mediocre ones. Choose the most relevant language; complete,
runnable, well-commented explaining WHY, from a real scenario. Don't implement in 5+ languages,
don't write fill-in-the-blank templates, don't write contrived examples.

---

## The Iron Law and the RED-GREEN-REFACTOR Cycle

```
NO SKILL WITHOUT A FAILING TEST FIRST
```

Applies to NEW skills AND EDITS. Wrote skill before testing? Delete it, start over. Same for
edits. No exceptions for "simple additions," "just adding a section," "documentation updates," or
"I'm confident it's good." Deploying untested skills = deploying untested code.

**Violating the letter of the rules is violating the spirit of the rules.** This cuts off the
entire class of "I'm following the spirit" rationalizations.

### Rationalization Table

Skills that enforce discipline need to resist rationalization. Agents are smart and will find
loopholes under pressure.

| Excuse | Reality |
|---|---|
| "Too simple to test" | Simple code breaks. Test takes 30 seconds. |
| "I'll test after" | Tests passing immediately prove nothing. |
| "Tests after achieve same goals" | Tests-after = "what does this do?" Tests-first = "what should this do?" |
| "I already manually tested it" | Manual testing ≠ tests. Delete it. Start over. |
| "Keep as reference while writing tests first" | You'll adapt it. That's testing after. Delete means delete. |
| "I'm following the spirit not the letter" | See Iron Law above. |
| "Being pragmatic not dogmatic" | Bright lines exist precisely because pressure degrades judgment. |
| "This case is different because..." | It isn't. |

### RED: Write Failing Test (Baseline)

Run pressure scenario WITHOUT the skill. Document exact behavior:
- What choices did the agent make?
- What rationalizations did they use (verbatim)?
- Which pressures triggered violations?

This is "watch the test fail" — you must see what agents naturally do before writing the skill.

### GREEN: Write Minimal Skill

Write the skill addressing those specific rationalizations. Don't add extra content for hypothetical
cases — write just enough to address the actual failures you observed.

Run same scenarios WITH skill. Agent should now comply. If agent still fails: skill is unclear or
incomplete. Revise and re-test.

### REFACTOR: Close Loopholes

Agent found a new rationalization? Add an explicit counter. Re-test until bulletproof. For each new
rationalization, add:

1. **Explicit negation in rules**

   ```markdown
   # Before
   Write code before test? Delete it.

   # After
   Write code before test? Delete it. Start over.

   **No exceptions:**
   - Don't keep it as "reference"
   - Don't "adapt" it while writing tests
   - Don't look at it
   - Delete means delete
   ```

2. **Entry in rationalization table** — add the exact wording the agent used.

3. **Red flag entry** — "Keep as reference" or "I'm following the spirit not the letter."

4. **Updated description** — add symptoms of ABOUT to violate: `Use when you wrote code before tests, when tempted to test after, or when manually testing seems faster.`

---

## Testing Skills With Subagents

### When to Test

Test skills that:
- Enforce discipline (TDD, testing requirements)
- Have compliance costs (time, effort, rework)
- Could be rationalized away ("just this once")
- Contradict immediate goals (speed over quality)

Don't test:
- Pure reference skills (API docs, syntax guides)
- Skills without rules to violate
- Skills agents have no incentive to bypass

### Different Skill Types Need Different Tests

**Discipline-enforcing skills** (rules/requirements — TDD, verification-before-completion):
- Academic questions: do they understand the rules?
- Pressure scenarios: do they comply under stress?
- Multiple pressures combined: time + sunk cost + exhaustion
- Success: agent follows rule under maximum pressure.

**Technique skills** (how-to guides — condition-based-waiting, root-cause-tracing):
- Application scenarios: can they apply the technique correctly?
- Variation scenarios: do they handle edge cases?
- Missing information tests: do instructions have gaps?
- Success: agent successfully applies technique to new scenario.

**Pattern skills** (mental models):
- Recognition scenarios: do they recognize when the pattern applies?
- Counter-examples: do they know when NOT to apply?
- Success: agent correctly identifies when/how to apply pattern.

**Reference skills** (documentation/APIs):
- Retrieval scenarios: can they find the right information?
- Gap testing: are common use cases covered?
- Success: agent finds and correctly applies reference information.

### Writing Pressure Scenarios

**Bad scenario (no pressure):**
```markdown
You need to implement a feature. What does the skill say?
```
Too academic. Agent just recites the skill.

**Good scenario (single pressure):**
```markdown
Production is down. $10k/min lost. Manager says add 2-line fix now.
5 minutes until deploy window. What do you do?
```

**Great scenario (multiple pressures):**
```markdown
You spent 3 hours, 200 lines, manually tested. It works.
It's 6pm, dinner at 6:30pm. Code review tomorrow 9am.
Just realized you forgot TDD.

Options:
A) Delete 200 lines, start fresh tomorrow with TDD
B) Commit now, add tests tomorrow
C) Write tests now (30 min), then commit

Choose A, B, or C. Be honest.
```

Multiple pressures: sunk cost + time + exhaustion + consequences. **Best tests combine 3+
pressures.**

### Pressure Types

| Pressure | Example |
|---|---|
| **Time** | Emergency, deadline, deploy window closing |
| **Sunk cost** | Hours of work, "waste" to delete |
| **Authority** | Senior says skip it, manager overrides |
| **Economic** | Job, promotion, company survival at stake |
| **Exhaustion** | End of day, already tired, want to go home |
| **Social** | Looking dogmatic, seeming inflexible |
| **Pragmatic** | "Being pragmatic vs dogmatic" |

### Key Elements of Good Scenarios

1. **Concrete options** — force A/B/C choice, not open-ended
2. **Real constraints** — specific times, actual consequences
3. **Real file paths** — `/tmp/payment-system` not "a project"
4. **Make agent act** — "What do you do?" not "What should you do?"
5. **No easy outs** — can't defer to "I'd ask your human partner" without choosing

### Verify GREEN: Meta-Testing

After agent chooses wrong option, ask:

```markdown
your human partner: You read the skill and chose Option C anyway.

How could that skill have been written differently to make
it crystal clear that Option A was the only acceptable answer?
```

Three possible responses:

1. **"The skill WAS clear, I chose to ignore it"** — not a documentation problem; add stronger
   foundational principle ("Violating letter is violating spirit").
2. **"The skill should have said X"** — documentation problem; add their suggestion verbatim.
3. **"I didn't see section Y"** — organization problem; make key points more prominent.

### When a Skill is Bulletproof

Signs of a bulletproof skill:
1. Agent chooses correct option under maximum pressure
2. Agent cites skill sections as justification
3. Agent acknowledges temptation but follows rule anyway
4. Meta-testing reveals "skill was clear, I should follow it"

Not bulletproof if agent finds new rationalizations, argues the skill is wrong, creates "hybrid
approaches," or asks permission while arguing strongly for violation.

### Example: TDD Skill Bulletproofing

```
Scenario: 200 lines done, forgot TDD, exhausted, dinner plans

Iteration 1 — Initial test:
  Agent chose C (write tests after). Rationalization: "Tests after achieve same goals."

Iteration 2 — Added "Why Order Matters" section:
  Agent STILL chose C. New rationalization: "Spirit not letter."

Iteration 3 — Added "Violating letter is violating spirit":
  Agent chose A (delete it). Cited new principle directly.
  Meta-test: "Skill was clear, I should follow it." → Bulletproof achieved.
```

6 RED-GREEN-REFACTOR iterations to bulletproof the real TDD skill. Baseline testing revealed 10+
unique rationalizations. Each REFACTOR closed specific loopholes.

---

## Persuasion Principles for Descriptions and Compliance Prompts

LLMs respond to the same persuasion principles as humans. Understanding this psychology helps
design more effective skills — not to manipulate, but to ensure critical practices are followed
even under pressure.

**Research foundation:** Meincke et al. (2025) tested 7 persuasion principles with N=28,000 AI
conversations. Persuasion techniques more than doubled compliance rates (33% → 72%, p < .001).

### The Seven Principles

**1. Authority** — Deference to expertise, credentials, or official sources.
- Imperative language: "YOU MUST", "Never", "Always"
- Non-negotiable framing: "No exceptions"
- Eliminates decision fatigue and rationalization
- Best for: discipline-enforcing skills, safety-critical practices

**2. Commitment** — Consistency with prior actions, statements, or public declarations.
- Require announcements: "Announce skill usage"
- Force explicit choices: "Choose A, B, or C"
- Use tracking: TaskCreate for checklists
- Best for: ensuring skills are actually followed, multi-step processes

**3. Scarcity** — Urgency from time limits or limited availability.
- Time-bound requirements: "Before proceeding"
- Sequential dependencies: "Immediately after X"
- Prevents procrastination
- Best for: immediate verification requirements, preventing "I'll do it later"

**4. Social Proof** — Conformity to what others do or what's considered normal.
- Universal patterns: "Every time", "Always"
- Failure modes: "X without Y = failure"
- Best for: documenting universal practices, warning about common failures

**5. Unity** — Shared identity, "we-ness", in-group belonging.
- Collaborative language: "our codebase", "we're colleagues"
- Best for: collaborative workflows, non-hierarchical practices

**6. Reciprocity** — Use sparingly; can feel manipulative. Rarely needed in skills.

**7. Liking** — **Do NOT use for compliance.** Conflicts with honest feedback culture; creates
sycophancy.

### Principle Combinations by Skill Type

| Skill Type | Use | Avoid |
|---|---|---|
| Discipline-enforcing | Authority + Commitment + Social Proof | Liking, Reciprocity |
| Guidance/technique | Moderate Authority + Unity | Heavy authority |
| Collaborative | Unity + Commitment | Authority, Liking |
| Reference | Clarity only | All persuasion |

### Why This Works

**Bright-line rules reduce rationalization.** "YOU MUST" removes decision fatigue. Absolute
language eliminates "is this an exception?" questions. Explicit anti-rationalization counters close
specific loopholes.

**Implementation intentions create automatic behavior.** "When X, do Y" is more effective than
"generally do Y." Reduces cognitive load on compliance.

**LLMs are parahuman.** Trained on human text containing these patterns. Authority language
precedes compliance in training data. Commitment sequences and social proof patterns are frequently
modeled.

**Ethical use test:** Would this technique serve the user's genuine interests if they fully
understood it?

### Research Citations

**Cialdini, R. B. (2021).** *Influence: The Psychology of Persuasion (New and Expanded).* Harper
Business.

**Meincke, L., Shapiro, D., Duckworth, A. L., Mollick, E., Mollick, L., & Cialdini, R. (2025).**
Call Me A Jerk: Persuading AI to Comply with Objectionable Requests. University of Pennsylvania.

---

## Anthropic Best Practices

> Anthropic's official guidance on skill authoring. Source: Anthropic docs site → "Agents and
> tools / Agent Skills / Authoring".

**Concise is key.** SKILL.md shares the context window with everything else. Default assumption:
Claude is already smart — only add context Claude doesn't already have. Challenge each paragraph:
"does this justify its token cost?"

**Set appropriate degrees of freedom.** Match specificity to the task's fragility:
- High freedom (text instructions) — multiple valid approaches, judgment-driven.
- Medium freedom (pseudocode/templates) — repeatable shape, varying details.
- Low freedom (scripts) — deterministic, fragile, must-not-vary outputs.

**Test with every model you plan to ship to.** Description quality, file-resolution, and tool-use
behavior diverge across models. A skill that triggers on Sonnet may not trigger on Haiku.

### Progressive Disclosure

SKILL.md loads when the skill triggers; referenced files load only as Claude follows links. Three
working patterns:

1. **High-level guide + references** — short SKILL.md links to deeper files for advanced features.
2. **Domain-specific organization** — SKILL.md is a router, with one file per domain.
3. **Conditional details** — SKILL.md handles the common case inline, links to a "rare cases" file.

Avoid deeply nested references — one hop is normal, two hops is the limit, three hops means
restructure. Long reference files need a table of contents at the top.

### Content Guidelines

- Avoid time-sensitive content (versions, dates, "current" vs "old" patterns) — they rot. Reference
  external authoritative sources when versions matter.
- Use consistent terminology — pick one term per concept, stick to it.
- Template pattern is fine for repeatable artifacts (commit messages, report structures).
- Examples pattern is fine for capturing nuance (good/bad pairs).
- Conditional workflow pattern for branching — make the branch condition explicit and observable.

### Skills With Executable Code

When the skill ships a script (`scripts/*.py`, `bin/*.sh`):
- The script does the work; the skill describes when to invoke it, not how to reimplement its logic.
- Pin runtime expectations — Python version, required packages, OS scope. State them at SKILL.md top
  and inside the script's docstring.
- Test the script outside the skill before shipping — `pytest`, `bats`, or a manual invocation
  that asserts exit code 0.
- Name the exact MCP tool (`mcp__server__tool`); do not rely on Claude inferring it from a
  description.
- Don't assume tools are installed — check, error with a remediation pointer, or supply install
  instructions.

### Anti-Patterns to Avoid

- **Windows-style paths** (`C:\foo\bar`) in cross-platform skills. Use forward-slash relative
  paths or POSIX `~/` shorthand.
- **Offering too many options** — a skill with 8 modes and a decision tree at the top is a skill
  no one will use correctly. Pick a default; expose alternatives via a subskill or follow-up file.
- **Pairing destruction with construction in one menu option** — each menu option exposes ONE
  primary verb. Pairing destruction (delete/discard/abandon) with construction (create/extend) in
  the same option forces an irreversible decision the user can't preview. Split into two adjacent
  options if both gestures are needed.
- **Punting to the user** — "ask the user which option they want" mid-skill is almost always wrong.
  The skill should have made the decision.

---

## Agent Smoke Loop

> See coordinator/CLAUDE.md § Agents and Subagents for boot-context notes on agent registration.

Newly-shipped agents are not discoverable by the parent EM until the Claude Code session restarts. This creates a validation gap: you ship a new agent, try to verify it in the same session, and the agent simply doesn't appear — not because it's broken, but because the session hasn't re-indexed the plugin.

**The in-session workaround:** simulate the new agent using a `general-purpose` Sonnet dispatch. Copy the agent's `allowed-tools`, identity, and prompt body verbatim into the `general-purpose` prompt. This exercises the agent's logic and instruction set in-session, before the restart that would properly register it.

**What the smoke loop confirms:**
- The agent's instructions produce the expected output shape.
- The `allowed-tools` list is sufficient for the task (no silent tool-missing failures).
- The output template / sidecar format is well-formed.

**What it does NOT confirm:**
- That the agent triggers correctly from description-based routing (requires restart + real dispatch).
- That frontmatter name/description fields are valid YAML (run a YAML linter separately).

**Protocol:**
1. Ship the agent file.
2. Dispatch a `general-purpose` Sonnet with the agent body verbatim as the prompt, using a representative scenario.
3. Verify the output shape matches the expected deliverable.
4. Restart the session before claiming the agent is production-ready.

**Failure mode:** if you skip step 4 and dispatch the agent by name in the same session, the parent EM will either fail to route to it or fall back to a different registered agent with a similar description — silent and hard to diagnose.

### Sidecar-emitting agents must include frontmatter in the output template

If your agent writes a sidecar markdown file (verdict report, resolution log, review findings), the output template must specify YAML frontmatter — `generated_by`, `generated_at`, and any schema-relevant fields. Without it, the frontmatter linter nags on first write and the EM gets a noisy block instead of a clean handoff. Treat the frontmatter as part of the agent's contract, not a post-hoc decoration.

## Common Footguns

**`allowed-tools` must be a YAML list, not a scalar.** `allowed-tools: Write` silently passes YAML
parsing but fails schema check. Correct form:
```yaml
allowed-tools:
  - Write
```

**`access-mode: read-only` silently overrides the tools list.** An agent with `Write` in `tools:`
but `access-mode: read-only` cannot write — the deliverable disappears. Default agents that
produce file output to `access-mode: read-write`.

**Prompts live in one place.** A driver/skill/command MUST `@`-reference the canonical prompt
template, never inline its body. Drift between inlined copy and template is a silent correctness
bug.

**Slash commands in subagent prompts do not expand.** Slash commands embedded in a subagent
dispatch prompt are NOT expanded — the subagent sees the literal `/skillname args` string, not
the underlying skill body. To compose skills, the caller must inline the relevant skill
instructions or dispatch the orchestrator skill that knows how to spawn the chain.

**Use contrastive voice anchors in agent prompts.** Pairing the desired tone with an anti-example
("respond like a senior reviewer, NOT like a sycophant") reduces drift toward
sycophancy/over-elaboration. Single-sentence anti-examples beat paragraph-long style guides.

**Hook authoring** — see `coordinator/docs/hook-authoring-notes.md` for SubagentStop agent_type
gating and stderr-as-error-channel footguns.

**Install / onboarding docs are written *to* the agent, not *about* the install.** When the supported install path is "PM pastes a prompt to their agent" or "agent reads a runbook," the canonical install doc is a **runbook addressed to the agent** — imperative voice, "you" = the agent, explicit verification steps, named failure modes, exact commands to run. Prose written for a human reader (background, motivation, narrative arc, design rationale) gets summarized and drifts when an agent consumes it, because agents follow runbooks reliably and infer poorly from explanatory prose. Same principle as dispatch-prompt-as-API at the subagent layer, applied to the install layer. Keep the agent-facing brief separate from any human-readable narrative; promote the brief to the front-door file, demote the human walkthrough to a sibling location a skeptic can find but isn't the default surface.

**Null-result audits — fold rule into producer skill, not just the report.** When an audit yields
a "don't do X" rule, write it into the skill that would otherwise produce X. Cross-reference
relevant sibling skills so the rule is greppable from the action site.

**Authorial-latitude conventions must bind sub-disciplines at the latitude site.** When a skill
grants authorial latitude on phrasing/shape, name the disciplined vocabulary or constraint inline
at that latitude — don't defer to a distant doctrine page.

---

## Skill Creation Checklist

**RED — Write Failing Test:**
- [ ] Create pressure scenarios (3+ combined pressures for discipline skills)
- [ ] Run WITHOUT skill — document baseline verbatim
- [ ] Identify patterns in rationalizations/failures

**GREEN — Write Minimal Skill:**
- [ ] Name: letters, numbers, hyphens only
- [ ] Frontmatter: name + description, max 1024 chars
- [ ] Description starts "Use when...", third person, specific triggers
- [ ] Keywords throughout (errors, symptoms, tools)
- [ ] Address specific baseline failures from RED
- [ ] One excellent example (not multi-language)
- [ ] Run WITH skill — verify agents comply

**REFACTOR — Close Loopholes:**
- [ ] Identify new rationalizations from testing
- [ ] Add explicit counters (discipline skills)
- [ ] Build rationalization table; create red flags list
- [ ] Re-test until bulletproof

**Quality:**
- [ ] Flowchart only if decision non-obvious
- [ ] Quick reference table
- [ ] Common mistakes section
- [ ] No narrative storytelling

**Dependency discipline (hard-dep vs soft-dep):**
- [ ] For each external reference, classify: would this skill produce *wrong* output without the
      reference, or just *less-sharp* output?
- [ ] Hard-dep (wrong without it) → keep an explicit pointer (`Run /X first if not configured`)
- [ ] Soft-dep (less-sharp without it) → swap explicit pointer for vague prose referencing the
      *output* (`if a project tracker exists`); never name the producing skill
- [ ] Default to soft-dep when uncertain

**Deployment:**
- [ ] Commit and push to your fork (if configured)
- [ ] Consider contributing back via PR
- [ ] Run Anthropic's checklist: description triggers correctly, loads under smallest target model,
      referenced files exist and reachable in one hop, code/scripts have a smoke test, no
      Windows-only paths, no time-sensitive claims without pinned dates
