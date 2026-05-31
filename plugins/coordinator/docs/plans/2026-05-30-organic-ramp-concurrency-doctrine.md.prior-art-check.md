---
title: Prior-Art Check — 2026-05-30-organic-ramp-concurrency-doctrine
created: 2026-05-30
author: prior-art-checker
status: implemented
kind: prior-art-check
plan: plugins/coordinator/docs/plans/2026-05-30-organic-ramp-concurrency-doctrine.md
---

## Prior-Art Verification

**Plan:** `plugins/coordinator/docs/plans/2026-05-30-organic-ramp-concurrency-doctrine.md`
**Verdict:** WARN
**Claims checked:** 20
**Conflicts:** 2 | **Compatible-but-relevant:** 5 | **Silent:** 13
**Corpora consulted:** project-wikis (100+ files indexed, key files read) | global-wikis (docs/wiki/ sampled) | lessons.md (searched) | improvement-queue (searched)

---

### Conflicts (plan contradicts prior art)

- **Claim #10 — machine-local registry: env-var resolution priority:** The plan's pinned contract states the resolution order as "`LARGE_WAVE_THRESHOLD` env var → `machine-local get fan_out.large_wave_threshold` → fallback `16`", with env var winning.
  - **Plan asserts:** "Resolution order for the threshold (helper reads, highest priority first): `LARGE_WAVE_THRESHOLD` env var → `machine-local get fan_out.large_wave_threshold` (written once at setup, § C6) → fallback `16`."
  - **Prior art (`docs/wiki/machine-local-registry.md` §4):** "5. `MACHINE_LOCAL_<KEY>` env override (intentional one-off escape — NOT highest precedence; env-vars are ambient, registry is deliberate) … Layers 1–4 are all `.toml` files and all outrank the env layer. The env layer (5) sits below all `.toml` layers because env-vars in a parent process are *ambient*, not deliberate — any export in a parent shell, IDE launch configuration, `.envrc`, or CI step would silently shadow the operator's registry values if env ranked above them. The registry's authority comes precisely from being the audited, operator-set source."
  - **Why this is a conflict:** The machine-local registry doctrine explicitly places env-var overrides *below* the registry in resolution precedence; the plan places the `LARGE_WAVE_THRESHOLD` env var *above* the registry value. The plan's `LARGE_WAVE_THRESHOLD` is a **custom script-level env var** (not a `MACHINE_LOCAL_<KEY>`-namespaced var), so the conflict may be definitional rather than operational — the machine-local §4 chain governs what the `machine-local get` CLI resolves, not what the shell script reads before calling it. However, the surface-level contradiction is real: the wiki's governing philosophy (registry is deliberate, env-vars are ambient and should rank lower) is the opposite of the plan's "env var wins" framing, and any reader applying the wiki's resolution doctrine to the plan's helper would conclude the two disagree.
  - **Candidate directions for EM:**
    - `update-plan` — add a clarifying note in the plan that `LARGE_WAVE_THRESHOLD` is a **script-level** env var read before the `machine-local get` call, and is therefore not part of the `MACHINE_LOCAL_<KEY>` chain. This explains why env-first is correct here without violating the registry doctrine (the registry's chain governs what `machine-local get` returns, not what the caller reads before calling it).
    - `update-prior-art` — amend `machine-local-registry.md §4` to distinguish "script-level env vars that callers may check before calling `machine-local get`" from the `MACHINE_LOCAL_<KEY>` override within the reader chain itself. These are two different layers; the wiki only documents the inner reader chain.
    - `both` — the distinction (script-level vs reader-chain env vars) is worth codifying on both surfaces.
  - **Lean:** `update-plan` with a clarifying note is the lighter fix — the underlying semantics are not broken (script-level env-first is an established pattern in bash tooling; it's the registry doctrine's philosophical framing that reads as contradicting it). The wiki addition would make future scripts cleaner.

---

- **Claim #18 — `coordinator:fan-out` skill and `dispatching-parallel-agents.md:187` cite the 6-8 cap as a live constraint:** The plan correctly identifies that `:187` says "Respects the 6–8 concurrency cap" and must be updated, and that C3 (skills/fan-out/SKILL.md) must be updated. However, the plan's out-of-scope list says both CLAUDE.md files are "already cap-number-free — no edit needed" and has been "Verified 2026-05-30." The prior art at `dispatching-parallel-agents.md:187` (read in full for this check) contains the live text: "**`coordinator:fan-out` (dispatcher skill)** — … Respects the 6–8 concurrency cap; halts and reports on any helper collision …"
  - **Plan asserts:** C5 out-of-scope carve-out: "Explicitly OUT of scope … `docs/wiki/dispatching-parallel-agents.md:168` — generic 'a concurrency cap' as an example … Re-read at edit time; touch only if it now reads as stale." And in-scope: "C1 | `docs/wiki/dispatching-parallel-agents.md` | 19-28 (§ Concurrency Budget), 187 | Rewrite the section … fix the `6–8` reference at :187."
  - **Prior art (`docs/wiki/dispatching-parallel-agents.md` line 187):** "**`coordinator:fan-out` (dispatcher skill)** — the in-the-moment verb for kicking off a fan-out without a written plan doc. Invokes the helper for the overlap pass + prompt compilation, dispatches via `Agent`, and holds the EM-serial commit between waves. **Respects the 6–8 concurrency cap**; halts and reports on any helper collision — never dispatches past a collision."
  - **Why this is a conflict:** The plan correctly identifies `:187` as in-scope and to be updated (C1). This is therefore NOT a genuine conflict between the plan and prior art on intent — the plan acknowledges the citation and scopes it for change. The conflict is a **substrate-verification gap**: the plan's C2 chunk description (`bin/fan-out-dispatch.sh`) contains the AC3 criterion "The helper prints the 6–8 concurrency cap reminder" which is from the OLD contract. The new AC3 in the plan (not the 2026-05-27 plan's AC3) has the NOTE language. The 2026-05-27 plan's shipped AC3 (`dispatching-parallel-agents.md`, line ~187) says "Respects the 6-8 concurrency cap" — this text was shipped and is live on disk. The current plan's C1 scope includes `:187` and must update it. The concern is that the 2026-05-27 plan declared the 6-8 cap "out-of-scope-to-change" — and that shipped plan's AC3/AC9 shaped the live wiki text at `:187`. The current plan's `supersedes_assumption` frontmatter correctly records this, but executors unfamiliar with this history may treat the wiki's `:187` as authoritative and not update it.
  - **Candidate directions for EM:**
    - `update-plan` — in C1's executor brief, quote the exact live text at `:187` verbatim so the executor cannot miss it. The plan correctly scopes C1 to include `:187` but does not quote it, creating ambiguity for an executor who reads the plan.
    - No prior-art update needed — this is the surface the plan is superseding.
  - **Lean:** `update-plan` with a verbatim quote of `:187` content in C1's brief. Low-effort, removes ambiguity.

---

### Compatible-but-relevant (plan should cite or align)

- **Claim #1 — the 6-8 cap has no recorded primary crash incident:** The plan asserts this confidently as a basis for removing the cap. Prior art in `dispatching-parallel-agents.md` § Concurrency Budget (line 28) says: "This rule is a heuristic calibrated from observed crash thresholds, not a platform-documented limit." The wiki does NOT cite a specific dated incident — it says "observed crash thresholds" without naming them.
  - **Plan covers:** "The **'6-8 hard cap'** in `docs/wiki/dispatching-parallel-agents.md § Concurrency Budget` has **no recorded primary crash incident.** It is self-described as *'a heuristic calibrated from observed crash thresholds, not a platform-documented limit'* — but the crash event was never written to any lesson, decision record, or dated incident."
  - **Prior art (`docs/wiki/dispatching-parallel-agents.md` lines 22-28):** "**Hard cap: 6-8 concurrent background agents in a single dispatch wave.** Exceeding this risks platform-level crashes — each Opus orchestrator spawns sub-agents, so a wave of orchestrators can inflate to 200+ real agents under the hood. … This rule is a heuristic calibrated from observed crash thresholds, not a platform-documented limit. Treat it as a ceiling, not a target."
  - **Subtype:** `cite`
  - **Suggested action:** The plan's assertion that no crash incident was ever documented is corroborated by this check — no dated incident exists in `tasks/lessons.md`, `coordinator-improvement-queue.md`, any `docs/wiki/` entry, or `docs/plans/` that records a real over-dispatch crash. The wiki's "observed crash thresholds" phrasing is the sole source, and it's self-referential. The plan's claim is verified as COMPATIBLE. For completeness, the Opus reviewer should be aware: the plan can assert "no crash incident documented" with confidence.

- **Claim #3 / #13 — converting WARNING HARD STOP to soft NOTE:** The design-as-offers doctrine in `docs/wiki/eager-agent-calibration.md` is directly on-point for this conversion and should be cited in the plan.
  - **Plan covers:** "The mechanism's nudges all become **soft, offer-shaped NOTEs** ('this is large — ramp it'), never a `WARNING` HARD STOP demanding PM authorisation." And AC4: "Large-wave nudge is offer-shaped (`NOTE:`, names the ramp), not mistrust-shaped (`WARNING:`/PM-auth)."
  - **Prior art (`docs/wiki/eager-agent-calibration.md`):** "**Design agent-facing tooling as offers, not nags.** When adding a hook, validator, doctor, or any tool the agent encounters mid-work, default to offer-shape: lead with the better alternative (*'did you mean X?'*), not the violation. Assume willing collaboration; mistrust-shape (warn / block / nag without alternative) fights agent eagerness rather than redirecting it." And: "**Offer-shape (this wiki's domain).** Apply when the agent is eager and the failure is *misdirection* — the agent would do the right thing if the right thing were the obvious thing. The intervention is: make the right path the easy path. Lead with the better alternative. Do not block, nag, or warn."
  - **Subtype:** `cite`
  - **Suggested action:** Add a cross-reference to `docs/wiki/eager-agent-calibration.md` in the plan's § Converged design #7 ("Legibility reframe") and in the wiki C1 rewrite. The plan's rationale for `NOTE:` over `WARNING:` is the offer-shape doctrine stated verbatim — citing it would make the architectural rationale explicit and greppable.

- **Claim #10/#15 — machine-local registry idempotency rule "never clobber an existing value":** The machine-local registry wiki explicitly documents how setup writes values idempotently, which the plan's C6 must follow.
  - **Plan covers:** "C6 — In the setup skill/command, add an idempotent step: … write `[fan_out]\nlarge_wave_threshold = <N>` to `registry.local.toml` **only if the key is absent** (re-run-safe; never clobber an operator's manual override)."
  - **Prior art (`docs/wiki/machine-local-registry.md` §5b):** "Per-machine path that varies across your machines. Append a key to `registry.local.toml`. No declaration step required. The reader is schemaless…" And from `commands/setup.md` Phase 3 Step 2: "If `~/.claude/machine-local/registry.toml` or `~/.claude/machine-local/registry.local.toml` exists, leave both untouched regardless of `.example` updates. Same rule for any `<concern>.toml` and `<concern>.local.toml`. The operator's machine-local values are theirs."
  - **Subtype:** `cite`
  - **Suggested action:** C6's idempotency implementation should follow the `machine-local set` pattern established in `commands/setup.md` Phase 3 Step 3 — which uses `machine-local set <key> <value>` as the atomic, idempotent primitive — rather than hand-editing the TOML file. The plan says "write to `registry.local.toml` via the machine-local registry" but does not name the mechanism. The wiki's anti-pattern §5b note says "**Do NOT write paths to `registry.local.toml` by hand-editing or heredoc.** `machine-local set` is atomic, idempotent, and sets the example for every future script that needs to populate the registry." The correct idempotent check is: `machine-local has fan_out.large_wave_threshold || machine-local set fan_out.large_wave_threshold <N>`.

- **Claim #15 — the `coordinator:setup` command already has a Phase 3 machine-local substrate step:** The plan says "C6 — `commands/setup.md` (or the setup skill) + a small helper | new step". Prior art confirms `commands/setup.md` already has Phase 3 with five steps (Steps 1-5 + Step 6) that covers machine-local substrate. The plan's C6 must insert cleanly into this existing structure.
  - **Plan covers:** "C6 | `commands/setup.md` (or the setup skill) + a small helper | new step | Measure logical cores once, write `fan_out.large_wave_threshold` to `registry.local.toml` via the machine-local registry. Idempotent/reentrant (setup is re-run-safe)."
  - **Prior art (`commands/setup.md` Phase 3):** "## Phase 3 — Machine-local registry substrate. Lay down the `~/.claude/machine-local/` substrate and the `bin/{machine-local, claude-home}` resolvers. Idempotent — safe to re-run; never overwrites a live `registry.toml`, `registry.local.toml`, or operator-customized file. … ### Step 5 — Register coordinator plugin in `plugin.mirrors` (idempotent)" [Steps 1-5 are all existing machinery; no Step 6 is shown in the visible portion — the plan implies it will add one.]
  - **Subtype:** `cite`
  - **Suggested action:** The C6 executor brief should read the full `commands/setup.md` Phase 3 before editing, confirm the existing step numbering, and insert the new step at the correct position (likely Step 6 or appended). The plan currently says "Step 5 — Register coordinator plugin" is the last documented step; the executor must verify the actual current last step number at edit time so the numbering is correct.

- **Claim #8 — "Count your own fanout" surviving rule (orchestrators multiply):** The existing `dispatching-parallel-agents.md` § Concurrency Budget already states this rule, and it must survive verbatim in the rewrite.
  - **Plan covers:** "(b) Count your own fanout. Orchestrators multiply (8 orchestrators × 6 sub-agents = a 48-agent wave you own); leaf workers don't. This is the one piece of arithmetic that survives."
  - **Prior art (`docs/wiki/dispatching-parallel-agents.md` lines 22-26):** "If any agents in the wave are themselves orchestrators (Opus delegating to subagents), divide the budget by the expected fanout before dispatching. A wave of 4 orchestrators each spawning 6 sub-agents is a 24-agent wave, not a 4-agent wave."
  - **Subtype:** `cite`
  - **Suggested action:** The C1 wiki rewrite should carry this arithmetic example verbatim or in equivalent precision — it is the load-bearing signal for what "count your own fanout" means operationally. The plan restates the math at a different example (8×6=48) but the wiki example (4×6=24) is currently established. Either example works; the executor should know the prior wording so they preserve the intent rather than accidentally weaken it.

---

### Peer prior art

*(No `peer_repos` supplied in the dispatch brief — section omitted.)*

---

### Silent areas (no prior art found)

- Claim #4 — organic ramp-until-degradation as the replacement model: no prior art in any corpus establishing this specific pattern for agent dispatch.
- Claim #5 — no cap on concurrent coordinators (top-level sessions): no prior art covering top-level session count governance.
- Claim #6 — each EM reasons only about its own session (no cross-session accounting): no prior art governing cross-session accounting.
- Claim #7 — pure organic ramp within a session (no fixed per-session numeric cap): no prior art establishing this as the dispatch model.
- Claim #9 — `min(16, cpu_cores - 2)` Workflow-runtime backstop is platform-enforced (not coordinator-computed): no prior art documenting this Workflow-runtime contract. (Note: this claim is worth the Opus reviewer verifying against Claude Code platform docs — it's a factual assertion about the Workflow runtime's behavior that the plan has not cited to a source.)
- Claim #11 — env var → machine-local → fallback `16` resolution order as a script-level pattern: no prior art establishing this three-tier pattern for script-level configuration beyond the machine-local reader's own chain.
- Claim #12 — `2 × logical_cores` as the derivation formula for `fan_out.large_wave_threshold`: no prior art. Plan correctly flags this as an open question.
- Claim #14 — file-overlap collision as the only surviving HARD GATE in the fan-out path: compatible with existing gate taxonomy, and consistent with `dispatching-parallel-agents.md` § Dispatch-Gate Taxonomy. Not a conflict, and not a novel claim — but no prior art *explicitly* frames file-overlap as the only surviving HARD GATE after cap removal. The reviewer may want to confirm no other gates were inadvertently dropped.
- Claim #16 — C2/C3/C4/C5 write-disjoint fan-out: analysis consistent with the plan's own file-overlap table; no prior art to check.
- Claim #17 — `coordinator:fan-out` skill description line 3 update: no prior art conflict beyond the live `:187` text already flagged above.
- Claim #19 — OSS portability: organic-ramp is more portable than flat 6-8: no prior art documenting OSS portability concerns for the cap value.
- Claim #20 — both CLAUDE.md files are already cap-number-free (verified 2026-05-30): this check corroborates — neither the global `~/.claude/CLAUDE.md` nor the coordinator `CLAUDE.md` carries a "6-8" number in its concurrency doctrine. The CLAUDE.md HARD RULE says "Size each executor ~5-10 min on one coherent surface (15 min hard ceiling; split before dispatch if a chunk would exceed it)" with no cap number. Verified SILENT (no conflict).

---

### Verdict logic

Two CONFLICTs surfaced:

- **Conflict #1 (Claim #10)** — the plan places a custom env var above the machine-local registry value, which contradicts the registry doctrine's "env-vars are ambient, registry is deliberate" philosophy. The operational semantics may be sound (the `LARGE_WAVE_THRESHOLD` var and `MACHINE_LOCAL_<KEY>` vars are different layers), but the framing is contradictory and will confuse future readers applying the wiki's resolution order to the plan's contract. EM should add a clarifying note to the plan.

- **Conflict #2 (Claim #18)** — the `coordinator:fan-out` skill's live text at `dispatching-parallel-agents.md:187` says "Respects the 6–8 concurrency cap" — born from the 2026-05-27 plan's shipped AC9. The current plan correctly scopes C1 to fix `:187`, but the C1 brief does not quote the live text verbatim, creating an execution gap. EM should strengthen C1's brief with the verbatim live text.

**Verdict: WARN** — both conflicts are clarification-class (neither blocks execution), but the resolution order conflict (Claim #10) is the kind that propagates into executor confusion when C6 is authored. Resolve before Opus reviewer dispatch.

**Neither conflict is load-bearing doctrine (scoped-safety-commits, daily-branch-discipline, round-trip-contract-tests, sequential-review HARD RULE) — BLOCKED-SURFACE-TO-PM does not apply.**

---

**Cost estimate:** ~8,500 tokens (20 claims × ~425 tokens average: 2 full wiki reads ~5K tokens + 1 plan read ~2K tokens + targeted searches ~1.5K tokens)
