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
  - tasks/lessons.md  (friction-as-warning, 2026-05-17)
---

# Eager-Agent Calibration

<!-- spec-backlink: docs/plans/2026-05-20-eager-agent-calibration.md § 5.4 -->

This wiki is the doctrine reference for three coordinated surfaces that together redirect executor agents toward portable, multi-machine code. The plan that designed these surfaces is `docs/plans/2026-05-20-eager-agent-calibration.md`; this wiki is the stable summary for future reference and RAG retrieval. It does not duplicate plan content — it names the surfaces, explains their binding logic, and records the framing that prevents doctrine confusion.

## PM Reframe — Eager, Not Lazy

The trigger for this doctrine (plan trigger memo, 2026-05-20): code-writing Claudes are not lazy — they are **eager to satisfy**. When a faster route to "code works" exists, the agent takes it. Hardcoded `X:/...` paths and single-machine artifacts are not carelessness; they are eagerness misdirected by two compounding failures: the meta-ask was never spoken, and the wrong shape was shorter to type.

The correct intervention is **redirection, not friction**. Change what "done" looks like. Make the right path the easy path. The ethos the PM named explicitly: engagement, enjoyment, opportunity — not mistrust, not control. The `superpowers` guardrail system is the explicit anti-pattern: built on mistrust, felt adversarial, routed agents around it.

The analogous doctrine for EM-PM dialogue (how the EM engages the PM) landed in `~/.claude/CLAUDE.md` § First Officer Doctrine ¶ Engagement Modes at commit 8cc7d6c8. This wiki captures the same ethos for EM-executor and executor-substrate interaction.

## The Three Surfaces

### Surface 1 — Executor Meta-Ask Preamble (snippet-synced)

**What it is.** A short (~150-word) preamble block in `agents/executor.md`, included via snippet-sync markers from `snippets/meta-ask-preamble.md`. Every executor dispatched on this stack receives it verbatim in its prompt — no per-dispatch typing required.

**What it transmits.** The meta-ask that CLAUDE.md cannot transmit (subagents do not see CLAUDE.md): "working" means working on every machine the code will run on; the registry-correct shape for sibling-repo paths is shorter than the hardcoded shape after the import; `from claude_machine_local import repos` and `source claude-machine-local.sh` are the right tools.

**Why it works.** The executor is eager and willing — it just needs the goal stated. Once the meta-ask is in context, an executor that would otherwise type `"X:/project-rag/foo"` instead reaches for `repos.project_rag / "foo"`. The preamble is calibration prose, not a checklist; it shapes the executor's model of what "done" means before the first tool call.

**Sync verifier.** `bin/verify-meta-ask-preamble-sync.sh --check` confirms the block in `executor.md` matches the canonical snippet byte-for-byte. Registered in `docs/wiki/coordinator-tripwires.md`.

### Surface 2 — Ergonomic Substrate (`claude_machine_local` Python + shell helpers)

**What it is.** Two helpers that make the registry-correct path reference the *shortest* viable form:

- Python: `~/.claude/bin/claude_machine_local.py` — importable when `~/.claude/bin` is on `sys.path`; exposes `repos.<key>` as `pathlib.Path` via `__getattr__`. Example: `from claude_machine_local import repos; repos.project_rag / "subdir/file.py"`.
- Shell (bash/zsh): `~/.claude/bin/claude-machine-local.sh` — source-once helper that exports `$REPOS_PROJECT_RAG`, `$REPOS_COORDINATOR_CLAUDE`, `$UNREAL_*`, etc. for every declared registry key.
- Shell (PowerShell): `~/.claude/bin/claude-machine-local.ps1` — dot-source helper exporting `$env:REPOS_*` / `$env:UNREAL_*`.

**Why it solves the substrate problem.** Without this surface, telling an executor "use the registry" is telling it to do more typing for the same result. With this surface, `repos.project_rag / "foo"` is comparable in length to `"X:/project-rag/foo"` and works on every machine. The right way becomes the easy way — the definition of offer-shape tooling.

**Calibration test.** The right-way form must read cleaner than the hardcoded literal — this is a qualitative design heuristic for future ergonomic-substrate decisions, not a numeric ratio. If adding a helper makes the right way measurably harder to read or type than the wrong way, the helper has failed the calibration test regardless of its semantic correctness. (This is the spirit of the dropped AC6 from the plan, folded here per the Staff Engineer's recommendation.)

**Template mirrors.** All three helpers are mirrored in `coordinator/templates/bin/` so `setup/publish.sh` ships them to consumer projects. `bin/verify-templates-bin-sync.sh` enforces byte-identity between `~/.claude/bin/` and the template counterparts.

**Foundation.** This surface wraps `~/.claude/bin/_machine_local.py` (implemented in `docs/plans/2026-05-19-machine-local-registry.md`). It does not extend the registry schema or reader — it is a thin attribute-access wrapper.

### Surface 3 — Design-as-Offers Heuristic in CLAUDE.md

**What it is.** A one-line heuristic in `~/.claude/CLAUDE.md` § Implementation Standards — Extensions, visible to the EM at every session boot:

> **Design agent-facing tooling as offers, not nags.** When adding a hook, validator, doctor, or any tool the agent encounters mid-work, default to offer-shape: lead with the better alternative, not the violation. Assume willing collaboration; mistrust-shape fights agent eagerness rather than redirecting it. → `docs/wiki/eager-agent-calibration.md`.

**Why it is in CLAUDE.md and not just here.** This is a cross-cutting tripwire for every future agent-facing tooling decision. The EM authors hooks, doctors, validators, and substrate helpers. Without this heuristic at boot altitude, each new tool risks defaulting to warn/block/nag because that shape feels "safe." The heuristic must be visible when the EM is designing, not only when they are reviewing an existing system.

**Scope.** CLAUDE.md governs the EM; executors get the meta-ask preamble. The two surfaces are complementary and non-overlapping.

## What This Replaces

Nothing. This is a net-new doctrine surface. There was no prior doctrine for executor-calibration or ergonomic-substrate design on this stack.

This doctrine complements but is **distinct from** the just-landed Engagement Modes doctrine (commit 8cc7d6c8, `~/.claude/CLAUDE.md` § First Officer Doctrine ¶ Engagement Modes). Engagement Modes governs how the EM and PM communicate with each other — dialogue altitude, when to ask vs. act, how to frame escalations. Eager-agent calibration governs how the EM designs tooling that executors encounter — substrate ergonomics, preamble transmission, offer-shape vs. nag-shape. The shared word is "engagement" as an ethos; the scopes are non-overlapping.

## Failure Modes This Prevents

**1. Meta-ask invisible to the executor.** CLAUDE.md is not loaded into subagent context (per `coordinator/CLAUDE.md` § Agent Prompts Are Self-Contained). Without Surface 1, every executor operates with no knowledge of the multi-machine, multi-OS, sustainable-code goal. The preamble closes this gap by template — the meta-ask travels with the dispatch, not the CLAUDE.md.

**2. Right-way longer than wrong-way.** Without Surface 2, a compliant executor that understands the meta-ask still faces a substrate that selects against portability: `"X:/project-rag/foo"` (20 chars) vs. the correct form (~80+ chars before the substrate helpers). Ergonomic APIs flip this — the correct form becomes the comparable or shorter form. An eager agent picks the path of least resistance; Surface 2 makes that path the right one.

**3. Control-shape over offer-shape.** Without Surface 3, future EM-authored tools (hooks, doctors, validators) default to warn/block/nag because that pattern feels protective. The design-as-offers heuristic names the failure mode before it recurs and provides the correct framing at the design decision point, not after.

## Offer-Shape vs. Friction-as-Warning: When Each Applies

These are two valid, distinct intervention shapes for agent behavior. They answer different questions and must not be conflated.

**Offer-shape (this wiki's domain).** Apply when the agent is eager and the failure is *misdirection* — the agent would do the right thing if the right thing were the obvious thing. The intervention is: make the right path the easy path. Lead with the better alternative. Do not block, nag, or warn. Example: the executor preamble and ergonomic substrate helpers. An executor that would type a hardcoded path instead reaches for `repos.project_rag` — not because it was blocked from the wrong path, but because the right path was handed to it.

**Friction-as-warning with typed override (2026-05-17 lesson, `tasks/lessons.md`).** Apply when the agent has a *strong incentive to reach for a wrong surface* and we genuinely want that surface to be hard to reach — not just less convenient, but actively resisted. The correct shape there is block-with-typed-justification: require the caller to name why the wrong surface is the right choice in this case. Warn-only is insufficient (agents override soft warnings automatically); silent toggle is worse (no audit trail). Example: a guardrail that blocks a destructive operation unless the caller provides a typed override string.

The fork: offer-shape applies when the agent is eager but misdirected; friction-as-warning applies when the agent has a genuine incentive to take a wrong path and we need an explicit override checkpoint. Both shapes are valid; picking the wrong one produces the wrong outcome — offer-shape on a genuinely-wrong-path surface gives no protection; friction-on-misdirection fights eagerness without redirecting it.

## Follow-Up Work (Deferred)

**Portability-guard spinoff.** `docs/plans/2026-05-20-portability-guard-system.md` is a PM-authorized spinoff that adds a safety-net layer *over* the substrate this wiki describes. That plan layers edit-time or commit-time detection on top of the ergonomic helpers. It is explicitly deferred until after this plan's surfaces are dogfooded — by design (offer-shape first, friction-as-warning second if needed). It should be picked up as a separate workstream.

**Preamble extension to other write-capable agents.** The meta-ask preamble ships first in `agents/executor.md`. Future work extends it to `agents/enricher.md`, `agents/review-integrator.md`, and the holodeck/web-dev/data-science executor analogues. Deferred to allow dogfood on the `executor.md` instance first — phrasing issues discovered there should be fixed once, not propagated to N places before the first run.
