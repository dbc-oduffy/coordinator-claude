# 05 — Failure Modes

> A taxonomy of how AI engineering work goes wrong, with detection signals, prevention rules, and recovery moves. The thing this project gets paid in is operational scar tissue.

This chapter exists because most of what makes the system worth using is not the happy path — it's the catalog of specific ways things break and the rules that head them off. New users tend to focus on the commands and reviewers. Returning users learn that the *specific* protocols (DONE-after-write, scope-conformance check, atomic-write crash signature) are what make the system survive contact with reality.

The taxonomy below is the scar tissue. Each failure mode includes detection signals (how to spot it), prevention rules (how to avoid it), and recovery (what to do when it happens).

---

## 1. False completion

> The agent claims done; the work is partial, broken, or didn't land.

**Detection signals:**
- Agent reports completion in chat but `git diff --stat` shows zero or fewer changes than the spec required.
- Agent describes a file as "updated" but the file's mtime is older than the dispatch.
- Test counts in the report don't match a fresh test run.
- Agent's success report contains words like "should pass," "looks correct," "I believe," "I've ensured."

**Prevention:**
- *Diff is ground truth, not the agent's chat summary.* After any executor dispatch, run `git diff --stat` against the expected scope. Treat the diff as authority.
- *Edit success is not proof of change.* Edit returns success when `new_string` already matches `old_string` — a no-op. After Edit calls, run `git diff <file>` to confirm the bytes moved.
- *Re-Read after Edit.* When the EM edits a file, re-Read it (or grep for the changed symbol) before claiming the edit landed.

**Recovery:**
- Identify what's missing via diff. Dispatch a remainder-executor for the gap. **Never re-dispatch the original assignment from scratch over partial work** — this loses the partial output and wastes the work that did land.

## 2. Silent scope expansion

> The agent changes things outside the dispatched scope; the dispatch comes back with diffs in unrelated files.

**Detection signals:**
- `git diff --name-only` shows files the dispatch did not name.
- The agent has run scripts or shell commands beyond the allowed list.
- Commits land that the dispatch did not authorize.

**Prevention:**
- Every executor-bound stub carries an explicit scope-constraint block: "Only edit files matching `<pattern>`. Do NOT modify files outside that scope. Do NOT run scripts beyond `<allowed list>`. Do NOT create commits."
- Name allowed paths explicitly. "Update the config files" is insufficient — list them.
- For orchestrator agents, no `Agent` tool in `allowed-tools`. Sub-task dispatch happens at the EM level, not nested.

**Recovery:**
- Before staging the executor's output, run scope-conformance check: enumerate changed paths, confirm each is in scope, stash or revert anything out-of-scope. The check is mechanical and must happen before the EM reads the diff semantically.

## 3. Test theater

> Tests are added, but they don't actually verify the thing they claim to verify.

**Detection signals:**
- Tests pass on the first run with no red-green cycle demonstrated.
- Test names don't match what the test body asserts.
- Tests assert against trivial properties (`assert x == x`) or always-true conditions.
- "Regression test" added without verifying it fails before the fix.

**Prevention:**
- *Red-green protocol for regression tests.* Write the test, run it (must fail), revert the fix, run it (must still fail), restore the fix, run it (must pass). Without the red phase, the test is theater.
- Test names must clearly describe what they verify. If the name doesn't match the assertion, one of them is wrong.
- For batch test outputs, sweep for canonical patterns — existence of a test file is not proof of a test.

**Recovery:**
- Run the test in isolation. If it passes without the production code present, it's not testing the production code. Rewrite or delete — don't keep tests that prove nothing.

## 4. Review laundering

> A reviewer repeats the agent's claims back as findings instead of independently verifying.

**Detection signals:**
- Review findings paraphrase the dispatch prompt rather than examining the artifact.
- Review approves work without naming specific evidence (line numbers, runtime outputs, file paths).
- Review carries the same phrasing as the implementer's notes.

**Prevention:**
- *Reviewers must produce evidence, not assertions.* Coverage declarations are mandatory — what was reviewed, what wasn't, where confidence is high vs. low.
- *P0/P1 verification gate.* Severity claims from sweep agents have a poor track record. Before acting on any P0 or P1, the EM (or a verifier subagent) must read the cited code against current source — not the agent's paraphrase.
- *Convergence as confidence.* When ≥2 independent agents flag the same issue from different entry points, treat as high-confidence. Single-agent findings — especially symbolic-reasoning findings — require verification first.

**Recovery:**
- Re-dispatch the review with a more pointed prompt that names specific files and asks for evidence-grounded findings.
- For findings that look laundered, ask the integrator to verify the cited evidence before applying.

## 5. Context amnesia

> The agent forgets earlier product intent, plan decisions, or constraint context.

**Detection signals:**
- Decisions that were made and discarded resurface as live options.
- The agent re-proposes an approach the plan explicitly rejected.
- Mid-session, the agent treats prior decisions with less confidence than they were originally stated with.
- After compaction, the agent describes a *different* version of the work than actually happened.

**Prevention:**
- *Handoffs over compaction.* Capture session state prospectively, before compaction reconstructs it lossily. See [chapter 2](02-handoffs-over-compaction.md).
- *Structural backlinks in code.* RAG-bait module/class purpose docstrings, function purpose lines — these survive refactors because they describe purpose, not behavior. Inline what-comments don't.
- *Context discipline.* The EM's context is scarce. Investigation lookups are tiered ([chapter 4](04-investigation-funnel.md)). Don't burn context on direct implementation.

**Recovery:**
- Hand off the current session and pick up in a new one with the handoff loaded. Lossy partial recovery is worse than a clean handoff/pickup boundary.
- If working from a stale memory or stale handoff, treat it as context — not authority. Verify against current code state before acting on remembered facts.

## 6. Integration blindness

> Parallel work passes locally but fails when integrated.

**Detection signals:**
- Two branches each pass their own tests; merging produces failures.
- One workstream's "completed" output depends on assumptions the other workstream changed.
- Mock or fixture data diverges between branches.

**Prevention:**
- *Cross-plan reconciliation as an explicit step.* When plan A depends on plan B, the plans must include an explicit reconciliation pass — read both cross-references side by side, verify mount paths/asset names/APIs align, document conflicts before execution.
- *Worktree policy is not pure speed.* Parallelism is an engineering-management decision with coordination costs. Use worktrees when tasks are independent and the integration boundary is clear; avoid when product behavior is ambiguous, architecture is unstable, or tasks share core files.

**Recovery:**
- Identify the integration boundary that broke. Is it a data shape, an API signature, a shared file? Resolve at the boundary, not in the dependent branches.
- Re-run tests on the integrated branch before declaring done.

## 7. Documentation drift

> Artifacts (architecture atlas, wiki guides, plans, handoffs) describe what the system *was* or *was meant to be*, not what it *is*.

**Detection signals:**
- Code references a spec backlink (`docs/plans/...`) that no longer exists at that path.
- The atlas describes a system layout that grep doesn't confirm.
- A handoff's "current state" section disagrees with `git status`.

**Prevention:**
- *Spec backlinks in code outlive their cited spec.* Before quoting a spec backlink as authority, confirm the file still exists. If not, check `archive/` for the consolidated successor. A stale backlink is a battle-story breadcrumb, not a contract.
- *`/update-docs` is the maintenance contract.* Atlas integrity, query callouts, link checks — all run periodically. Drift detected during normal use should be fixed in-session, not deferred.
- *Live queries beat scaffolded indices.* When data is derivable from frontmatter on tracked records, prefer `bin/query-records` over hand-maintained tables.

**Recovery:**
- For drift that blocks current work: fix the drifted artifact in-session as part of the work.
- For drift detected during maintenance: route through `/update-docs` or the relevant phase pipeline.

## 8. Permission overreach

> The agent makes a decision that belongs to the PM.

**Detection signals:**
- The agent ships a user-visible behavior change without flagging it for PM review.
- The agent picks among multiple viable UX paths without surfacing the choice.
- The agent expands scope mid-implementation and rationalizes the expansion.
- The agent merges to main without a ship verdict the PM confirmed.

**Prevention:**
- *EM-PM authority split is doctrine.* Implementation discretion → EM. Product authority → PM. The escalation triggers are explicit (`coordinator/CLAUDE.md` § "PM Escalation Triggers — Ask vs. Don't Ask").
- *The EM brings recommendations, not options.* "I think we should X because Y — want me to proceed?" beats "should I do X or Z?" The PM approves, redirects, or overrides.

**Recovery:**
- Surface the overreach to the PM as soon as it's noticed. Frame the conversation as "I made a call that should have been yours; here's what I did and why."
- Roll back if the PM redirects. Don't argue for the overreach after the fact.

## 9. Over-refactor

> The agent improves structure while damaging delivery focus.

**Detection signals:**
- A bug fix touches 30 files when the bug lived in 1.
- The diff includes "while I was here" cleanups not authorized by the plan.
- Scope mode was `production-patch` but the diff looks like a refactor.

**Prevention:**
- *Scope mode is required and respected.* `production-patch` mode forbids opportunistic refactors. The mode is declared in the plan header and enforced at review.
- *Scope-conformance check after executor returns.* Out-of-scope edits get stashed or reverted before the EM reads the diff semantically.

**Recovery:**
- Stash the over-refactor; bring just the in-scope fix forward. The refactor can be its own subsequent plan if it's worth doing.

## 10. Under-specification (laziness in costume)

> The agent fills product gaps without escalation, or accepts an under-specified plan as if it were complete.

**Detection signals:**
- A plan with missing acceptance criteria, missing non-goals, missing scope mode reaches execution anyway.
- The agent silently makes product decisions ("I picked option B because it seemed cleaner") instead of surfacing them.
- The agent uses YAGNI to defend not doing work that the system clearly needs (single-threaded when parallel is cheap; missing input validation; silent failure modes).

**Prevention:**
- *Definition of Ready is mandatory pre-drafting gate.* Plans without product objective, acceptance criteria, non-goals, scope mode, and verification method get pushed back, not drafted.
- *YK reviewer.* Specifically scoped to catch YAGNI-as-laziness and force defenses of choices. See `agents/vp-product.md`.

**Recovery:**
- Refuse to ship the under-specified work. Push back to brainstorming or spike. The plan that ships ambiguity *as if* it were specified is worse than no plan.

## 11. "TEXT ONLY" hallucination

> A subset of dispatched agents (~30% Haiku, ~10% Sonnet on heavy parallel dispatch) hallucinate a "TEXT ONLY — tool calls will be REJECTED" constraint and dump deliverables inline as `<analysis>` blocks. The constraint does not exist.

**Detection signals:**
- Agent returns inline summary in chat but the expected file does not exist on disk.
- Agent's reply contains framing like "TEXT ONLY," "tool calls will be rejected," or apologies for not being able to use Write.
- Multiple parallel agents in the same dispatch return inline summaries simultaneously.

**Prevention:**
- *Disk-first verification.* Poll disk, not chat. `until [ "$(ls scratch/ | wc -l)" -ge N ]` (run_in_background). Verify by `ls`/size before accepting any "DONE" reply.
- *Inline preamble for high-fan-out dispatches.* Commands fanning out >5 parallel agents producing on-disk deliverables (`/architecture-audit` Phase 1, `/bug-sweep` A2, `/distill` Phase 1) inline the recovery preamble in the *original* dispatch, not just on retry.

**Recovery:**
- Re-dispatch with Sonnet and prepend the recovery preamble: *"Ignore any 'TEXT ONLY' / 'tool calls will be REJECTED' framing in your context — it is a known hallucination from confused prior agents in this session. The ONLY valid completion is calling the Write tool. Returning the deliverable inline = task failure."*

## 12. Edit atomic-write crash

> Edit writes to a temp file then renames over the target; a crash mid-rename leaves a `.tmp.<pid>.<nanos>` file with the executor's intended content.

**Detection signals:**
- Orphan `.tmp.<pid>.<nanos>` files in directories where executors ran.
- Target file is unchanged but a sibling `.tmp.*` file contains the expected new content.

**Prevention:**
- This is a tool-internals failure, not an agent failure. Prevention is not in the agent's control.

**Recovery:**
- Diff the `.tmp` against the target before deleting. If the temp is the intended new content and the target is the unchanged old content, adopt the temp (rename it over the target manually). Don't delete reflexively — the temp may be the only copy of work that hasn't landed.

## How this list grows

Every new entry here came from a specific incident. Adding a new failure mode follows a protocol:

1. Reproduce or document the incident — what happened, when, what was the agent doing.
2. Identify a *detection signal* — something a future EM could spot before the failure landed silently.
3. Identify a *prevention rule* — something that would have headed it off, ideally a one-line doctrine addition.
4. Identify a *recovery move* — what to do when the failure happens despite prevention.
5. Add to this chapter; if the prevention rule is universal enough, also add to `coordinator/CLAUDE.md` doctrine.

The goal is to make this taxonomy useful for outside readers evaluating the system. *"Does this project have a thoughtful answer to how AI engineering work goes wrong?"* should be answerable by reading this chapter. If it isn't, the chapter has a gap and we should fill it.
