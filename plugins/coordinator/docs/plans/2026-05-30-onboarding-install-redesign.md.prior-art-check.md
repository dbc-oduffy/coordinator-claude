---
title: Prior-Art Check — 2026-05-30-onboarding-install-redesign
created: 2026-05-30
author: prior-art-checker
status: implemented
kind: prior-art-check
plan: plugins/coordinator/docs/plans/2026-05-30-onboarding-install-redesign.md
---

## Prior-Art Verification

**Plan:** `plugins/coordinator/docs/plans/2026-05-30-onboarding-install-redesign.md`
**Verdict:** WARN
**Claims checked:** 22
**Conflicts:** 1 | **Compatible-but-relevant:** 9 | **Silent:** 12
**Corpora consulted:** project-wikis (121 files indexed) | global-wikis (29 files indexed) | lessons.md | improvement-queue

---

### Conflicts (plan contradicts prior art)

- **Claim #6 — Static handoff file staged inside the plugin source tree:** The plan stages a hand-authored static handoff template at `templates/handoffs/continue-onboarding-and-installation.md` (C5), which the install copies to `tasks/handoffs/` at run-time. The plan treats this as a new-file-no-overlap addition.
  - **Plan asserts:** "Author the static handoff with minimal `/pickup`-valid frontmatter (`title, created, branch, status: active, predecessor: null, deployment_state: ready_to_fire, pickup_ready: true`)."
  - **Prior art (`docs/wiki/plugin-extraction-and-distribution.md` § Manifest Scan Includes Authoring-Time Outputs):** "A plugin's release manifest … typically does a recursive walk of the plugin tree to enumerate shipped files. Without explicit excludes, the walk pulls in `tasks/`, `archive/`, `.last-cleanup`, scratch dirs, and `.tmp.*` orphan files from Edit-tool crashes … Defense: anchor the manifest scan to a deliberate include list (`commands/`, `skills/`, `agents/`, `hooks/`, `docs/wiki/`, `bin/`) rather than 'everything under root minus a few excludes.'"
  - **Also (`docs/wiki/plugin-extraction-and-distribution.md` § `dist/publish-repo-docs/` corner):** `coordinator/dist/publish-repo-docs/` is explicitly described as the authoring surface for publish-repo-owned top-level docs, suggesting a pattern for where install-stage template outputs should live. There is no established `templates/handoffs/` sub-tree in the plugin's percolation-include list.
  - **Why this is a conflict:** The plan adds a `templates/handoffs/` directory inside the plugin tree. If the manifest/percolate include list (anchor-to-deliberate-includes doctrine) does not cover `templates/handoffs/`, the handoff template either (a) silently fails to ship to OSS consumers, or (b) ships via an untested path. Neither the plan nor the substrate notes explicitly confirm this directory is in scope for percolation.
  - **Candidate directions for EM** (advisory — EM/reviewer choose):
    - `update-plan` — confirm `templates/handoffs/` is already percolation-included (or add it to the include list) and note in C5's test surface.
    - `update-prior-art` — if the `templates/` tree is already canonically percolated, the wiki's anchor-to-include guidance is incomplete; add `templates/` to the explicit include list example.
    - `both` — the conflict reveals that the templates/ percolation status is underdocumented; worth noting in both the plan and the wiki.
  - **Lean:** The plan's C5 section says "New file — no overlap," which addresses the within-wave write-scope concern but does not address the percolation-completeness question. The plan also explicitly says percolation is PM-gated (claim #22), so the shipping path is deferred — but the percolation question is real and must be addressed before the PM-gate fires. `update-plan` looks more likely than `update-prior-art` here; the wiki rule is sound, and the plan just needs to name the include-list extension.

---

### Compatible-but-relevant (plan should cite or align)

- **Claim #1 — `/reload-plugins` activates plugin without cold restart; restart required for Agent Teams env var:**
  - **Plan covers:** "The restart stays load-bearing — but because of the env var, not plugin registration. Encode the correct reason." Layer 0 docs should note `/reload-plugins` activates the plugin, but the fresh session is needed for the Agent Teams env var.
  - **Prior art (`docs/wiki/plugin-extraction-and-distribution.md` § Bootstrap script — item 13):** "Seeds **both** `extraKnownMarketplaces` in `~/.claude/settings.json` AND the `~/.claude/plugins/known_marketplaces.json` cache, so `/reload-plugins` activates the plugin without requiring a cold Claude Code restart. ... The README order is `clone → run register-claude-plugin → /reload-plugins → /<plugin>:setup`."
  - **Subtype:** `cite`
  - **Suggested action:** C1 (the `agent-install.md` rewrite) should explicitly cite this README-order pattern from item 13. The plan already has the correct technical claim; align vocabulary with the bootstrap-from-clone doctrine so the two surfaces are consistent.

- **Claim #2 — `publish.sh` is outbound-only; percolation is PM-gated:**
  - **Plan covers:** "This plan does NOT auto-run `publish.sh`. Surface 'ready to percolate' to the PM at done-time."
  - **Prior art (`docs/wiki/plugin-extraction-and-distribution.md` § `publish.sh` direction):** "`publish.sh` runs source → publish-repo (sibling) for cross-machine distribution. It does NOT write back to the live install; the 2026-05-20 ban on publish-repo → live install clobber is preserved. These are orthogonal operations."
  - **Also (§ Publish-Repo Content Authoring):** "The publish repo is a percolation target, not a source of truth. All publish-repo content is authored in Claude Central (`~/.claude/`) and percolated outward via `setup/publish.sh`. Editing the publish repo directly is always wrong."
  - **Subtype:** `cite`
  - **Suggested action:** Plan is fully aligned. No change needed; informational citation only. C8 closeout text could mention the wiki reference for the downstream Opus reviewer's confidence.

- **Claim #3 — UE/holodeck/game-dev stack and project-rag excluded from OSS install menu:**
  - **Plan covers:** "Three-tier ecosystem map: core (coordinator) · recommended (deep-research) · specialized — not part of this install (UE/holodeck/game-dev, project-rag)."
  - **Prior art (`docs/wiki/oss-distribution-editorial-principle.md` — global wiki):** "Coordinator ships a coherent operating system for our colleagues, not generic personae as a contribution to the OSS community. ... if a plugin's value is entirely contingent on specialized infrastructure the OSS user does not have, it belongs in the specialized distribution — not the naked OSS coordinator-claude publish."
  - **Also (`docs/wiki/plugin-extraction-and-distribution.md` § Holodeck-owned plugins):** "Plugins whose value is entirely contingent on the holodeck/UE-addon infrastructure flow holodeck-repo → holodeck install, one direction only. Nothing flows them outward to `X:/coordinator-claude` or any OSS distribution target."
  - **Subtype:** `cite`
  - **Suggested action:** Plan is fully aligned with both wiki sources. C3's test surface (`grep:` tier labels present; UE stack not offered) enacts this doctrine correctly. No change needed; the plan's OOS section already cites `CLAUDE.local.md` editorial principle — adding the wiki refs would strengthen the Opus reviewer's confidence.

- **Claim #4 — `/pickup` accepts minimal hand-authored frontmatter; `predecessor: null` OK; no `kind:` required:**
  - **Plan covers:** "Author the static handoff with minimal `/pickup`-valid frontmatter (`title, created, branch, status: active, predecessor: null, deployment_state: ready_to_fire, pickup_ready: true`)."
  - **Prior art (`skills/pickup/SKILL.md` lines 52-59, classification table):** The pickup skill classifies by `status: active|consumed` and `deployment_state:` presence — it does NOT require `kind:`. The `pickup_ready` check (line 191-192) is "non-blocking warning" only, not a gate: "If the handoff frontmatter does NOT contain `pickup_ready: true`, print once to the PM-facing channel: '⚠ handoff … lacks `pickup_ready: true` — proceeding anyway.'"
  - **Subtype:** `cite`
  - **Suggested action:** The plan's C5 frontmatter claim is consistent with pickup doctrine. However, note that `pickup_ready: true` is specifically recommended to suppress the non-blocking warning — the plan already includes it, which is good practice. The plan should also confirm whether `branch:` is a required field or optional in the pickup classification (the SKILL.md shows `scope:` as load-bearing for the `git add` step, not `branch:` specifically). Low-risk; worth verifying in the C5 test surface that the frontmatter passes the actual pickup classification check.

- **Claim #5 — Post-install first dogfood: co-write CLAUDE.md/CLAUDE.local.md; partnership-shape offer:**
  - **Plan covers:** "The first collaborative session should be co-writing the user's CLAUDE.md / CLAUDE.local.md ... which is also where the partnership-shape choice (PM/EM vs. manager-and-team) is offered (strongly-led, not a gate)."
  - **Prior art (`docs/wiki/post-install-onboarding-pattern.md` § The three movements):** "Make it yours — tailor to taste. ... carries the load-bearing correctness point below." And the correctness point: "customizations land in the operator's live install surface, not the upstream source/distribution repo. For coordinator that's 'edit your git-tracked `~/.claude`, not a clone of `coordinator-claude`' — the source-is-live model."
  - **Also (`docs/wiki/getting-started.md` — if present):** The coordinator's operator-facing instance of the post-install onboarding pattern.
  - **Subtype:** `cite`
  - **Suggested action:** C5 and C6 should reference `docs/wiki/post-install-onboarding-pattern.md` (the established doctrine) and align vocabulary. The plan's first-dogfood framing is consistent with Movement 2 ("make it yours"). The wiki's "load-bearing correctness point" — customize the live surface, not the source — matches Claim #10 (refinement target = user's `~/.claude`). Citing the wiki from C5 would make the doctrine trail explicit.

- **Claim #7 / Claim #8 — Design-as-offers; decision-dense over express/DIY binary:**
  - **Plan covers:** "The fix philosophy: the install must enact the collaboration it installs — decision-dense where shape is at stake, fast everywhere else; never the 'press the button, don't think' express analog."
  - **Prior art (`docs/wiki/eager-agent-calibration.md` § Surface 3 — Design-as-Offers):** "Design agent-facing tooling as offers, not nags. When adding a hook, validator, doctor, or any tool the agent encounters mid-work, default to offer-shape: lead with the better alternative, not the violation. Assume willing collaboration; mistrust-shape fights agent eagerness rather than redirecting it."
  - **Also (`docs/wiki/eager-agent-calibration.md` § PM Reframe):** "The correct intervention is redirection, not friction. Change what 'done' looks like. Make the right path the easy path." And: "The `superpowers` guardrail system is the explicit anti-pattern: built on mistrust, felt adversarial, routed agents around it."
  - **Subtype:** `cite`
  - **Suggested action:** The plan is aligned with design-as-offers doctrine. C1's framing of "agentic partnership flow, not a script-is-done run" is the correct shape. C4 (bootstrap-repos vocabulary alignment) directly enacts the doctrine. The plan's authors may find `eager-agent-calibration.md` § Offer-Shape vs. Friction-as-Warning useful for calibrating where the logic tree asks vs. decides. No conflict; citation would strengthen the Opus reviewer context.

- **Claim #10 — Refinement target: user's git-tracked `~/.claude`, never the coordinator clone:**
  - **Plan covers:** "After install, you evolve your own `~/.claude` (git-tracked, backed up) — never the coordinator clone (a delivery truck)." Stated in C1, C3, C6.
  - **Prior art (`docs/wiki/post-install-onboarding-pattern.md` § The load-bearing point):** "customizations land in the operator's live install surface, not the upstream source/distribution repo. ... For coordinator that's 'edit your git-tracked `~/.claude`, not a clone of `coordinator-claude`' — the source-is-live model. ... Get this right and the tour teaches a true mental model; get it wrong and you teach operators to edit a tree that does nothing."
  - **Also (`docs/wiki/coordinator-installer-shape.md` § 8. Central vs publish-target separation):** Confirms the source-is-live model — coordinator's live install IS the canonical source, no separate install step.
  - **Subtype:** `cite`
  - **Suggested action:** Plan is fully aligned. Citing `post-install-onboarding-pattern.md` in C1, C3, and C6 would make the prior-art trail explicit. The wiki names this "the key adaptation decision for each tool" — worth calling out in the plan as the established vocabulary.

- **Claim #14 — Edit canonical source of `agent-install.md`, not the `dist/` artifact:**
  - **Plan covers:** "Confirm source vs `dist/` artifact first; edit source. ⚠ `dist/` files may be GENERATED — every executor must confirm the canonical source the file `publish.sh` copies from before editing."
  - **Prior art (`docs/wiki/plugin-extraction-and-distribution.md` § `dist/publish-repo-docs/` corner):** "A fourth authoring source … handles publish-repo-owned top-level `docs/*.md` files. `coordinator/dist/publish-repo-docs/` controls only `agent-install.md` ... A bidirectional `.percolate-ignore` inside this source dir protects every other top-level publish-repo `docs/*.md` from the flat-mirror delete-not-in-source pass."
  - **Also (§ Publish-Repo Content Authoring):** "The publish repo is a percolation target, not a source of truth. All publish-repo content is authored in Claude Central (`~/.claude/`) and percolated outward via `setup/publish.sh`. Editing the publish repo directly is always wrong."
  - **Subtype:** `cite`
  - **Suggested action:** Plan's ⚠ warning is correct and aligned with prior art. C1 executor should explicitly cite `coordinator/dist/publish-repo-docs/` as the confirmed canonical source path for `agent-install.md`, removing ambiguity for the dispatched executor. The substrate notes reference (`tasks/onboarding-install-redesign/substrate-notes.md`) should include this confirmation.

- **Claim #17 — deep-research default-on-with-opt-out; pulled from GitHub:**
  - **Plan covers:** "deep-research is default-on-with-opt-out — offer to install it (pull from the GH repo), and make its presence/absence explicit."
  - **Prior art (`docs/wiki/coordinator-installer-shape.md` § Phase architecture):** Phase 1 includes "deep-research" as an environment probe. Phase 6 status report includes `deep_research` as a check identifier with status vocabulary `ready`, `missing`, `not_configured`.
  - **Also (`docs/wiki/coordinator-installer-status-schema.md` — referenced by installer-shape):** The `deep_research` check is part of the stable producer-side schema that "holodeck-callable wrappers should pin against."
  - **Subtype:** `cite`
  - **Suggested action:** C3 (setup.md rework) must preserve the existing `deep_research` check identifier in the status-report table (the schema is stable/append-only; rename or removal is a breaking change). The plan should confirm that the Phase 1.d remedial offer in setup.md uses the same check-identifier vocabulary established in `coordinator-installer-status-schema.md`. If the new "offer to install" row changes the status vocabulary (e.g., adds a new enum value like `offered_and_accepted`), that is a schema change that requires a version bump per the schema wiki.

---

### Silent areas (no prior art found)

- Claim #9 — Track B (existing structure) minimal-honest treatment; no cherry-pick engine: no prior art in any corpus. (The ratified OOS in the problem-set covers this; the approach is novel to this plan.)
- Claim #11 — Three-layer bootstrap (Layer 0 / Layer 1 / Layer 2 framing): no prior art in any corpus under these exact layer labels. The problem-set defines them; the plan enacts them.
- Claim #12 — First dogfood = co-write CLAUDE.md/CLAUDE.local.md as an authored step (not advisory prose): no prior art in any corpus for this specific first-dogfood designation. Related to `post-install-onboarding-pattern.md` Movement 3 (test drive), but the co-write-CLAUDE.md specificity is novel to this plan.
- Claim #13 — C8 dogfood is a binary outcome (converge or re-plan): `docs/wiki/dogfooding-doctrine.md` exists and covers binary outcome doctrine. Confirmed COMPATIBLE, not silent — see below.
- Claim #15 — Cross-plan coordination with organic-ramp plan; regression-guard test: no prior art specifically about cross-plan regression guards in this form. Novel to this plan.
- Claim #16 — session-start fresh-install branch (no-handoff path): no prior art in any corpus for a session-start fresh-install orientation branch. This is a new pattern.
- Claim #18 — Partnership-shape offer (PM/EM vs. manager-and-team); strongly-led, not a gate: no prior art for this specific partnership-shape offer as an install-surface concept. The First Officer Doctrine covers the partnership itself but not as an install-stage offer.
- Claim #19 — Chunks C1–C7 fan out in parallel (file-coherent, write scopes disjoint): no prior art on this specific parallel-fan-out configuration. Standard plan decomposition pattern; no conflict.
- Claim #20 — `/pickup` is a skill → plugin must be loaded post-restart: consistent with pickup doctrine. No prior art directly states this constraint; it is an accurate inference from the skill architecture.
- Claim #21 — `lib/detect-existing-claude-home.sh` read-only and idempotent: no prior art in any corpus. New file, new pattern.

**Addendum — Claim #13 (dogfood doctrine, confirmed COMPATIBLE):**

- **Plan covers:** "Run the redesigned install end-to-end in a throwaway `~/.claude`-shaped fixture per `coordinator:dogfood` doctrine — binary outcome: converge or switch gears."
- **Prior art (`docs/wiki/dogfooding-doctrine.md` — from DIRECTORY_GUIDE summary):** "Fix-through validation of new capabilities — smoke → fix → converge or replanning." Binary outcome confirmed as established doctrine.
- **Subtype:** `cite`
- **Suggested action:** C8 is aligned with dogfooding doctrine. No change needed. Informational only.

---

### Install-surface completeness lens (always-on — per `docs/wiki/install-surface-completeness.md`)

The plan is literally about the install story — the `install-surface-completeness.md` wiki is directly in scope. Key checks:

1. **Clean-install dry-run (§ a):** The plan addresses this via C8 (full dogfood in a throwaway fixture). The plan correctly identifies the bootstrap paradox and designs the install to be runnable by a vanilla session. PASS in intent; realization verified by C8.

2. **Doctor surface (§ b):** The plan does not create or modify any `:doctor` skill. This is acceptable (the plan is about the *install surface itself*, not post-install doctor coverage) — but the plan should confirm that the new `lib/detect-existing-claude-home.sh` and the continue-onboarding handoff template do not need a doctor probe to detect their absence on fresh installs. Silent-missing-state is the failure mode; if these artifacts are required for the install to work, the doctor should detect their absence.

3. **New-user mental model (§ c):** The plan explicitly addresses this (the entire motivation is Britt's install experience). The three-tier ecosystem map and the refinement-target framing directly address the mental-model correctness requirement.

4. **Two-layer install altitude (§ Two-Layer Install Surfaces):** The plan implicitly distinguishes script-layer (setup.md, bootstrap-repos.md) from agent-layer (agent-install.md, pickup). This distinction should be explicit in C1's framing to preserve the altitude separation the wiki names.

No new CONFLICTS surfaced from this lens beyond Claim #6 (templates/handoffs/ percolation-include status).

---

### Verdict logic

**WARN** — one conflict surfaced (Claim #6: `templates/handoffs/` percolation-include status is unverified). The conflict is medium-severity: the plan's percolation is explicitly PM-gated and deferred (C8 closeout), so the conflict does not block execution — but it must be resolved before the PM-gate fires on percolation. EM should add a note to C5 confirming that `templates/handoffs/` is in the percolation include list (or will be added to it at C8 closeout time). Once that note lands, the sidecar verdict can be treated as COMPATIBLE for Opus reviewer dispatch.

Compatible-but-relevant items are informational; they strengthen the plan's doctrine trail but none require plan changes to proceed.

---

**Cost estimate:** ~9K tokens (estimated from 22 claims × 8 corpus reads, several short targeted greps)
