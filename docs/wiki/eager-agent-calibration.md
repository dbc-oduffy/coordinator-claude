---
title: Eager-agent calibration
created: 2026-05-20
type: doctrine
related:
  - plugins/coordinator/agents/executor.md
  - plugins/coordinator/snippets/meta-ask-preamble.md
  - ~/.claude/CLAUDE.md  (§ Implementation Standards — Extensions, § First Officer Doctrine ¶ Engagement Modes)
  - docs/plans/2026-05-19-machine-local-registry.md
  - docs/plans/2026-05-20-eager-agent-calibration.md
  - state/lessons.md  (friction-as-warning, 2026-05-17)
---

# Eager-Agent Calibration

<!-- spec-backlink: archive/specs/2026-05/2026-05-20-eager-agent-calibration.md § 5.4 -->

This wiki is the doctrine reference for three coordinated surfaces that together redirect executor agents toward portable, multi-machine code. The plan that designed these surfaces is `docs/plans/2026-05-20-eager-agent-calibration.md`; this wiki is the stable summary for future reference and RAG retrieval. It does not duplicate plan content — it names the surfaces, explains their binding logic, and records the framing that prevents doctrine confusion.

## PM Reframe — Eager, Not Lazy

The trigger for this doctrine (plan trigger memo): code-writing Claudes are not lazy — they are **eager to satisfy**. When a faster route to "code works" exists, the agent takes it. Hardcoded `X:/...` paths and single-machine artifacts are not carelessness; they are eagerness misdirected by two compounding failures: the meta-ask was never spoken, and the wrong shape was shorter to type. <!-- foreign-path-ok: naming the anti-pattern this doctrine exists to prevent -->

The correct intervention is **redirection, not friction**. Change what "done" looks like. Make the right path the easy path. The ethos the PM named explicitly: engagement, enjoyment, opportunity — not mistrust, not control. The `superpowers` guardrail system is the explicit anti-pattern: built on mistrust, felt adversarial, routed agents around it.

The analogous doctrine for EM-PM dialogue (how the EM engages the PM) landed in `~/.claude/CLAUDE.md` § First Officer Doctrine ¶ Engagement Modes at commit 8cc7d6c8. This wiki captures the same ethos for EM-executor and executor-substrate interaction.

## The Three Surfaces

### Surface 1 — Executor Meta-Ask Preamble (snippet-synced)

**What it is.** A short (~150-word) preamble block in `agents/executor.md`, included via snippet-sync markers from `snippets/meta-ask-preamble.md`. Every executor dispatched on this stack receives it verbatim in its prompt — no per-dispatch typing required.

**What it transmits.** The meta-ask that CLAUDE.md cannot transmit (subagents do not see CLAUDE.md): "working" means working on every machine the code will run on; the registry-correct shape for sibling-repo paths is shorter than the hardcoded shape after the import; `from claude_machine_local import repos` and `source claude-machine-local.sh` are the right tools.

**Why it works.** The executor is eager and willing — it just needs the goal stated. Once the meta-ask is in context, an executor that would otherwise type `"X:/project-rag/foo"` instead reaches for `repos.project_rag / "foo"`. <!-- foreign-path-ok: naming the anti-pattern this preamble redirects away from --> The preamble is calibration prose, not a checklist; it shapes the executor's model of what "done" means before the first tool call.

**Sync verifier.** `verify-snippet-sync meta-ask-preamble --check` confirms the block in `executor.md` matches the canonical snippet byte-for-byte. Registered in `coordinator/docs/wiki/coordinator-tripwires/`.

### Surface 2 — Ergonomic Substrate (`claude_machine_local` Python + shell helpers)

**What it is.** Two helpers that make the registry-correct path reference the *shortest* viable form:

- Python: `<settings-home>/bin/claude_machine_local.py` — importable when `<settings-home>/bin` is on `sys.path`; exposes `repos.<key>` as `pathlib.Path` via `__getattr__`. Example: `from claude_machine_local import repos; repos.project_rag / "subdir/file.py"`.
- Shell (bash/zsh): `<settings-home>/bin/claude-machine-local.sh` — source-once helper that exports `$REPO_PROJECT_RAG`, `$REPO_COORDINATOR_CLAUDE`, etc. for every declared registry key.
- Shell (PowerShell): `<settings-home>/bin/claude-machine-local.ps1` — dot-source helper exporting `$env:REPO_*`.

**Why it solves the substrate problem.** Without this surface, telling an executor "use the registry" is telling it to do more typing for the same result. With this surface, `repos.project_rag / "foo"` is comparable in length to `"X:/project-rag/foo"` and works on every machine. <!-- foreign-path-ok: naming the anti-pattern this substrate makes comparably short --> The right way becomes the easy way — the definition of offer-shape tooling.

**Calibration test.** The right-way form must read cleaner than the hardcoded literal — this is a qualitative design heuristic for future ergonomic-substrate decisions, not a numeric ratio. If adding a helper makes the right way measurably harder to read or type than the wrong way, the helper has failed the calibration test regardless of its semantic correctness. (This is the spirit of the dropped AC6 from the plan, folded here per the Staff Engineer's recommendation.)

**Template mirrors.** All three helpers are mirrored in `coordinator/templates/bin/` so `setup/publish_sync.py` ships them to consumer projects. The byte-identity gate is engine-subject — `coordinator_core/ops/verify_templates_bin_sync.py`, in `claude-klabauter` — and enforces byte-identity between `<settings-home>/bin/` and the template counterparts (see `docs/wiki/portable-code-substrate.md § Template Mirrors`).

**Foundation.** This surface wraps `<settings-home>/bin/_machine_local.py` (implemented in `docs/plans/2026-05-19-machine-local-registry.md`). It does not extend the registry schema or reader — it is a thin attribute-access wrapper.

### Surface 3 — Design-as-Offers Heuristic in CLAUDE.md

**What it is.** A one-line heuristic in `~/.claude/CLAUDE.md` § Implementation Standards — Extensions, visible to the EM at every session start:

> **Design agent-facing tooling as offers, not nags.** When adding a hook, validator, doctor, or any tool the agent encounters mid-work, default to offer-shape: lead with the better alternative, not the violation. Assume willing collaboration; mistrust-shape fights agent eagerness rather than redirecting it. → `docs/wiki/eager-agent-calibration.md`.

**Why it is in CLAUDE.md and not just here.** This is a cross-cutting tripwire for every future agent-facing tooling decision. The EM authors hooks, doctors, validators, and substrate helpers. Without this heuristic at boot altitude, each new tool risks defaulting to warn/block/nag because that shape feels "safe." The heuristic must be visible when the EM is designing, not only when they are reviewing an existing system.

**Scope.** CLAUDE.md governs the EM; executors get the meta-ask preamble. The two surfaces are complementary and non-overlapping.

**Applied example.** When `probe-cwd-project-rag-relevance.py` was designed to surface MCP availability at session start, the default implementation instinct was a warning-shape tripwire ("project-rag is available but MCP not configured"). The PM reframe: "take this MCP system!" not "Danger Will Robinson!" The final probe leads with the capability framing — "you have this equipment" — and names restoration as unlocking value, not as remediation of a failure. This is the design-as-offers shape applied to a concrete tool-author decision. The distinction is: what does the agent see first — an asset, or a gap?


## What This Replaces

Nothing. This is a net-new doctrine surface. There was no prior doctrine for executor-calibration or ergonomic-substrate design on this stack.

This doctrine complements but is **distinct from** the just-landed Engagement Modes doctrine (commit 8cc7d6c8, `~/.claude/CLAUDE.md` § First Officer Doctrine ¶ Engagement Modes). Engagement Modes governs how the EM and PM communicate with each other — dialogue altitude, when to ask vs. act, how to frame escalations. Eager-agent calibration governs how the EM designs tooling that executors encounter — substrate ergonomics, preamble transmission, offer-shape vs. nag-shape. The shared word is "engagement" as an ethos; the scopes are non-overlapping.

## Known Limits — Calibration vs. Enforcement

**Dogfood result.** AC10(a) PASS — the preamble is transmitted correctly to every executor dispatch via `verify-snippet-sync meta-ask-preamble`. AC10(b) FAIL on both test runs — the executor still hardcoded `X:/project-rag/CLAUDE.md` literals despite the preamble being present. <!-- foreign-path-ok: dogfood-test evidence quoting the observed anti-pattern output -->

Two hypotheses explain the failure, and both point at the same architectural conclusion:

1. **Soft framing.** The preamble is offer-shape by design: "If you find yourself about to type X:/... in code, reach for the helpers." <!-- foreign-path-ok: quoting the preamble's own anti-pattern example --> An executor optimizing for "small one-off scratch utility" judged the import overhead unnecessary. This is the cost of offer-shape: it tilts behavior, it does not guarantee it.
2. **No in-context examples.** The executor had abstract instruction but no observed usage of `repos.project_rag` in the current session. First-time preamble exposure produces weaker uptake than sessions where the correct shape appears in prior tool calls.

**Conclusion: preamble + substrate together are calibration, not enforcement.** They change the prior toward the right shape; they do not assert invariants. This validates the portability-guard spinoff (warn-at-edit or block-on-merge) as a necessary complement, not an over-engineering. Calibration first; enforcement layer added after dogfood confirms the shape — this sequencing is intentional and correct.

**Re-dogfood triggers:** run AC10 again when any of: (a) portability-guard spinoff lands, (b) preamble extended to other write-capable agents, (c) `repos.*` usage appears in production committed code (giving executors in-context examples).

## Failure Modes This Prevents

**1. Meta-ask invisible to the executor.** CLAUDE.md is not loaded into subagent context (per `coordinator/agents/executor.md`, "Subagents see only their dispatch prompt — project and global CLAUDE.md are invisible to them"). Without Surface 1, every executor operates with no knowledge of the multi-machine, multi-OS, sustainable-code goal. The preamble closes this gap by template — the meta-ask travels with the dispatch, not the CLAUDE.md.

**2. Right-way longer than wrong-way.** Without Surface 2, a compliant executor that understands the meta-ask still faces a substrate that selects against portability: `"X:/project-rag/foo"` (20 chars) vs. the correct form (~80+ chars before the substrate helpers). <!-- foreign-path-ok: naming the anti-pattern being measured against --> Ergonomic APIs flip this — the correct form becomes the comparable or shorter form. An eager agent picks the path of least resistance; Surface 2 makes that path the right one.

**3. Control-shape over offer-shape.** Without Surface 3, future EM-authored tools (hooks, doctors, validators) default to warn/block/nag because that pattern feels protective. The design-as-offers heuristic names the failure mode before it recurs and provides the correct framing at the design decision point, not after.

## Doctrine That Names an Antipattern Path Can Teach the Antipattern

An eager agent reads doctrine for *what to do*, and a concrete path or call-shape named in the prose — even one named as the thing to avoid — is a ready-made template the agent can reach for. "Do not write the body to a temp file under `tasks/<feature>/`" still hands the agent the exact `tasks/<feature>/` path; "never stage in `%TEMP%`" still names `%TEMP%` as a place bodies go. The negation is prose the agent must hold in mind; the concrete path is structure it can copy. Under eagerness the structure wins — the agent pattern-matches on the named path and does the antipattern the doctrine was forbidding.

**Rule.** When authoring doctrine (wiki lines, skill steps, agent prompts), prefer to describe the *correct* surface concretely and the antipattern *abstractly* — name the right path/CLI/subcommand in full, and refer to the wrong shape by its class ("an ad-hoc staging path", "a path of your own choosing") rather than by a copy-pasteable instance. If you must cite a concrete antipattern path (e.g. to make a fix greppable), pair it immediately with the concrete correct replacement so the agent's reach lands on the right surface. This is the design-as-offers principle applied to doctrine prose itself: lead with the better alternative made concrete; do not hand the agent a template for the thing you're warning against. (See `docs/wiki/writing-skills.md` § "CLI doctrine that names an ad-hoc staging path teaches ad-hoc staging" for the worked CLI instance. Source: ~/.claude.)

## Offer-Shape vs. Friction-as-Warning: When Each Applies

These are two valid, distinct intervention shapes for agent behavior. They answer different questions and must not be conflated.

**Offer-shape (this wiki's domain).** Apply when the agent is eager and the failure is *misdirection* — the agent would do the right thing if the right thing were the obvious thing. The intervention is: make the right path the easy path. Lead with the better alternative. Do not block, nag, or warn. Example: the executor preamble and ergonomic substrate helpers. An executor that would type a hardcoded path instead reaches for `repos.project_rag` — not because it was blocked from the wrong path, but because the right path was handed to it.

**Friction-as-warning with typed override (lesson, `state/lessons/`).** Apply when the agent has a *strong incentive to reach for a wrong surface* and we genuinely want that surface to be hard to reach — not just less convenient, but actively resisted. The correct shape there is block-with-typed-justification: require the caller to name why the wrong surface is the right choice in this case. Warn-only is insufficient (agents override soft warnings automatically); silent toggle is worse (no audit trail). Example: a guardrail that blocks a destructive operation unless the caller provides a typed override string.

The fork: offer-shape applies when the agent is eager but misdirected; friction-as-warning applies when the agent has a genuine incentive to take a wrong path and we need an explicit override checkpoint. Both shapes are valid; picking the wrong one produces the wrong outcome — offer-shape on a genuinely-wrong-path surface gives no protection; friction-on-misdirection fights eagerness without redirecting it.

### Which Emissions Owe an Alternative

**Axis A (obligation).** Any emission that asks the agent to change or reconsider the triggering action must name a concrete alternative — deny and advisory alike, no exemption for either envelope. An emission that asks nothing of the agent is a report, and a report is legal without naming an alternative only if it carries state the agent could not already know AND does not repeat with substantively identical text on a later firing (that second condition is `### Repetition Without Novelty` below — cross-referenced, not restated).

**Axis B (bypass).** Withholding the override/bypass incantation is a separate, orthogonal legal axis. A denying guard can satisfy Axis A in full and still legitimately withhold the override string — sometimes it must, under the misdirection carve-out above (`## Doctrine That Names an Antipattern Path Can Teach the Antipattern`): naming the bypass concretely hands the agent a template for evading the guard.

**Why envelope is the wrong discriminator.** A first draft of this rule sorted firing legitimacy by hook envelope — deny owes nothing, advisory owes an alternative — and it does not survive contact with the corpus. The in-process-search guard's `deny` is semantically an allow: it means "already handled, not refused," so a deny-envelope emission can be a report with nothing to redirect. Conversely, the AUTO-PUSH note is an advisory-envelope, allow-path, past-tense emission — it fires after the agent's action already succeeded, states what happened, and asks for no reconsideration; requiring it to name an alternative would be requiring an alternative to nothing. Envelope tells you how the hook responded to the runtime, not whether the emission is asking the agent for something. Obligation — does this text ask the agent to change course — is the only discriminator that survives both cases.

**The sentinel-guard case, named explicitly**, because it is the case that shows the rule cannot be misread as "denies get a pass." `block_worktree_sentinel_creation` leads with its sanctioned alternative — scoped-parallel dispatch into the same tree — and withholds only the override incantation. Axis A: satisfied, an alternative is named. Axis B: withheld, correctly. A blanket "no emission may fire without naming an alternative, full stop" rule would have to either strip this guard's override-withholding (defeating its purpose) or exempt it outright (re-opening the envelope discriminator this rule rejects) — the two-axis split is what lets the sentinel guard stay exactly as strict as it needs to be on Axis B while still being well-formed on Axis A.

**One caution worth recording.** A liveness-extractor in the guard corpus tolerates zero-alternative messages without failing its build. That tolerance is a statement about what the extractor's build step accepts as syntactically valid, not a doctrinal ruling that zero-alternative denies are well-shaped emissions. Reading extractor-tolerance as doctrinal license is the exact error this predicate exists to correct — the extractor not rejecting a shape is not the same claim as this wiki endorsing it.

### Remediation-Size Cap

Both shapes above assume the emission itself is well-formed. It can fail on size alone, independent of which shape it picked. An advisory never echoes back a payload larger than the command that triggered it — the remediation text exists to redirect the agent, not to reproduce its own input back at it. The concrete failure this came from: a bare-scope `git commit` advisory that reprints the caller's full `-m` operand, shlex-quoted, TWICE inside its own remediation text — unbounded in size, so a 20-line commit message produces a 40-line advisory. An offer-shape emission that grows with its trigger stops reading as an offer; it reads as noise the agent learns to skim past, which defeats the whole calibration this wiki argues for. Discharges AC-2.

### Repetition Without Novelty

An emission that would repeat with substantively identical text within a session fires at most once, unless each firing carries new state. This is what makes a per-call footer whose literal text is "Nothing to change on your side." defective independent of Axis A — it asks nothing, so Axis A is satisfied, but it repeats identically with no session latch. Novelty is the missing ingredient the offer-shape/friction fork above doesn't by itself guarantee: an offer can be correctly shaped and still teach the agent to stop reading, purely by saying the same thing every time. It is also the rule that makes the field report's cost argument — an agent learning to skim the guard channel — generalise past the four reported items. Discharges AC-2b.

## Follow-Up Work (Deferred)

## A Check That Speaks Only on Drift Is Free to Run Anywhere

When an agent-facing safety script is silent on the clean state and emits only on drift, adding it to more invocation points costs nothing — every clean run is a no-op (zero noise tax). `check-em-environment.py` 2026-05-30: runs as a step in all three start ceremonies; a clean Opus+medium env prints nothing.

**Rule.** Separating *does the check run* from *does it say anything* lets you scatter the call liberally without noise. Prefer baking such a check into the relevant skills over a per-prompt hook (a `UserPromptSubmit` hook re-introduces the documented Windows stdin-hang and per-prompt overhead for no gain when skills are the real entry points). Extends design-as-offers / silent-on-pass. (Source: ~/.claude.)

## Follow-Up Work (Deferred)

**Preamble extension to other write-capable agents.** The meta-ask preamble ships first in `agents/executor.md`. Future work extends it to `agents/enricher.md`, `agents/review-integrator.md`, and the example-game-repo/web-dev/data-science executor analogues. Deferred to allow dogfood on the `executor.md` instance first — phrasing issues discovered there should be fixed once, not propagated to N places before the first run.
