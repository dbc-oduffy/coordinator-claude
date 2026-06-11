---
title: Coordinator onboarding/install redesign — the front door enacts the system
date: 2026-05-30
author: the Coordinator Authors (EM)
problem_set: docs/problems/2026-05-30-coordinator-onboarding-install-redesign.md
scope_mode: feature
status: implemented
depends_on:
  - docs/plans/2026-05-30-organic-ramp-concurrency-doctrine.md  # shares commands/setup.md + README.md (different sections)
---

# Coordinator onboarding/install redesign

**Amended 2026-06-08 by 2026-06-08-repo-setup-consolidation:** the "three surfaces, unify vocabulary" architectural choice in this plan (line 57: "Command names unchanged") is reversed under PM dogfood-driven authorization. `/project-onboarding` and `/bootstrap-repos` are consolidated into a single `/repo-setup` command (single-repo by default, `--batch` for fleet mode). Full reversal rationale in `docs/plans/2026-06-08-repo-setup-consolidation.md` § Decision-#0. This plan's status remains `implemented` as a historical record of the now-superseded architecture.

> SDD half. The PRD half is frozen in the ratified problem-set (`docs/problems/2026-05-30-coordinator-onboarding-install-redesign.md`, P1–P8 + 3 architectural OOS). This plan covers all eight problems and honours the OOS; it does not re-derive the architecture, which converged through `/shape`.

## Origin

First real external user (Britt O'Duffy, CS PhD candidate, Oxford) installed coordinator cold. The install surface failed in six linked ways rooted in one **bootstrap paradox**: a vanilla, doctrine-less Claude is asked to install the coordinator doctrine, so it cannot behave like the system it installs. The fix philosophy: **the install must enact the collaboration it installs** — decision-dense where shape is at stake, fast everywhere else.

## Substrate (verified against disk 2026-05-30 — see `tasks/onboarding-install-redesign/substrate-notes.md`)

- **Discovery surface already exists** but is fragile: `dist/publish-repo-docs/agent-install.md` ("Audience: Claude, not a human") reached via a README one-liner (`dist/publish-repo-toplevel/README.md:23-32`). P1 is "make robustly discoverable + followable," not "build from zero." ⚠️ `dist/` files may be GENERATED — every executor must confirm the canonical source (the file `publish.sh` copies *from*) before editing, and edit the source, not the artifact.
- **`/setup` and `/bootstrap-repos` are commands** (`coordinator/commands/setup.md`, `coordinator/commands/bootstrap-repos.md`), not skills. `/project-onboarding` is a skill (`skills/project-onboarding/SKILL.md`).
- **Express/DIY binary** lives as "EXPRESS vs CUSTOM" in `bootstrap-repos.md:48-79`; setup uses implicit `--non-interactive`; project-onboarding is detection-driven. Vocabulary is inconsistent across the three surfaces.
- **deep-research invisibility is real:** setup Phase 1.d (`setup.md:76-91`) checks presence and reports status but never *offers to install*. Bundled `install.sh --non-interactive` default-installs it; marketplace-only path does not.
- **Restart mechanism correction:** `/reload-plugins` (a real command) activates a freshly-registered plugin *without* a cold restart; the genuinely restart-requiring thing is the **Agent Teams env var** (`setup.md:42-55`), which deep-research needs. The restart stays load-bearing — but because of the env var, not plugin registration. Encode the correct reason.
- **`/pickup` accepts an arbitrary path** (`pickup/SKILL.md:69`), mutates frontmatter in place, and accepts minimal hand-authored frontmatter (`predecessor: null` OK, no `kind:` required). A static `state/handoffs/continue-onboarding-and-installation.md` is hand-authorable. Constraint: `/pickup` is a skill → the plugin must be loaded (post-restart) for it to exist. This *is* the three-layer sequencing.
- **`session-start` has no fresh-install orientation hook** (`session-start/SKILL.md`); its work menu offers nothing about "co-write your CLAUDE.md." When a handoff is loaded, `/pickup` pre-empts the menu — so the continue-onboarding handoff drives the first-dogfood; a session-start fresh-install branch covers the no-handoff case.
- **OSS marketplace tier** (`plugins/coordinator-claude/.claude-plugin/marketplace.json` — the *marketplace root*, one level above the coordinator plugin's own `.claude-plugin/`, which holds only `plugin.json`): coordinator, web-dev, data-science, deep-research, notebooklm. game-dev correctly absent. UE stack / project-rag are OUT for generic OSS users per `CLAUDE.local.md` editorial principle.

## Prior art consulted (from `.prior-art-check.md` sidecar)

- `docs/wiki/post-install-onboarding-pattern.md` — established post-install onboarding doctrine. **Movement 2 = the first-dogfood; the refinement-target framing is already established here.** C5/C6 CITE and ALIGN with this wiki rather than reinventing it.
- `docs/wiki/plugin-extraction-and-distribution.md` — confirms `/reload-plugins` (item 13), publish.sh outbound-only direction, and the mirror-mode vs. manifest-mode distinction. Prior-art-checker Conflict #6 cited the wiki's "anchor to deliberate include-list" guidance, but that guidance describes the MANIFEST surface (deep-research-claude, holodeck) — it does **not** apply to coordinator-claude, which is registered as MIRROR mode. Conflict #6 was a mode mismatch; resolved by verifying mirror-mode shipping: the template ships automatically unless `.percolate-ignore` excludes it.
<!-- the Staff Engineer F0: corrected prior-art note — include-list doctrine is manifest-mode-specific; coordinator-claude is mirror mode; Conflict #6 was a mode mismatch, not an include-list gap -->

- `docs/wiki/eager-agent-calibration.md` — the design-as-offers ethos the logic tree's "decision-dense, not interrogation" framing rests on.
- `docs/wiki/install-surface-completeness.md` — the doctrine the C5 percolation-include fix serves.

## Architecture (converged in problem-set — honour, don't re-derive)

Single decision-dense install **logic tree** replacing the express/DIY binary; Track A (install-from-zero) vs Track B (existing structure → minimal-honest, NO cherry-pick engine); **three-layer bootstrap** (Layer 0 vanilla-runnable + maximally frontloaded; Layer 1 kernel-as-flow-concept, no extraction; Layer 2 post-restart `/pickup`); restart reframed as load-bearing "fresh session + paste one `/pickup` command"; refinement target = the user's git-tracked `~/.claude`, never the clone; three-tier ecosystem map; first post-install dogfood = co-write CLAUDE.md/CLAUDE.local.md, where the partnership-shape choice (PM/EM vs. manager-and-team) is offered and encoded.

## The keystone: `agent-install.md` IS the logic tree

The agent-facing playbook (`agent-install.md`) is where the whole redesign lives — it is the document a cold Claude reads and *follows* as a coordinator-shaped flow. The commands (`setup.md`, `bootstrap-repos.md`) are the mechanism the playbook drives; the templates and session-start branch are the post-restart continuation. Chunks are **file-coherent** to keep the two hot files (`agent-install.md`, `setup.md`) each owned by exactly one executor.

## Pinned interfaces (enable fan-out; every chunk treats these as frozen contracts)

- **Agent front door:** top-level `AGENTS.md` (the emerging cross-tool convention filename agents look for unprompted) is the discovery entrypoint; it routes a fresh clone into the detailed `agent-install.md` playbook. README points at it with a loud early line `🤖 Agents: start here → AGENTS.md`. AGENTS.md = front door; agent-install.md = detailed flow.
- **Continue-onboarding handoff path:** `state/handoffs/continue-onboarding-and-installation.md` (written by the install, consumed by `/pickup`); its template source `templates/handoffs/continue-onboarding-and-installation.md` **ships automatically under mirror mode** — coordinator-claude is registered as mirror (everything-minus-excludes via `.percolate-ignore`), so the template ships unless a `.percolate-ignore` pattern excludes `coordinator/templates/`. The install-surface-completeness requirement INVERTS to: confirm `coordinator/templates/` is NOT excluded by `.percolate-ignore` (and any future `.percolate-ignore` edit must not exclude it). See C5 for the verification form.
<!-- the Staff Engineer F0: percolation mechanism was inverted — coordinator-claude is mirror mode, not manifest mode; fixed to reflect mirror-mode shipping logic and negative-exclusion verification -->

- **Track A/B detection helper:** `lib/detect-existing-claude-home.sh` → emits `track=A` | `track=B` with a one-line reason on stdout (idempotent, read-only).
- **Three ecosystem tiers (verbatim labels):** `core` (coordinator) · `recommended` (deep-research, default-on-with-opt-out, from `github.com/dbc-oduffy/deep-research-claude`) · `specialized — not part of this install` (UE/holodeck/game-dev, project-rag).
- **Partnership-shape offer** is authored in the continue-onboarding handoff's first "Recommended Next Step" (PM/EM vs. manager-and-team — offered, strongly-led, not a gate).
- **Command names unchanged:** `/coordinator:setup`, `/coordinator:bootstrap-repos`, `/project-onboarding`, `/pickup`, `/reload-plugins`, `/reload-skills`.

## Chunks

### C1 — `agent-install.md`: rewrite the playbook as the decision-dense logic tree (P1, P2, P3, P4, P5, P6)
**Owns:** the canonical source of `agent-install.md` (confirm source vs `dist/` artifact first; edit source). This is the detailed flow that `AGENTS.md` (C2) routes into — keep the entry framing consistent with the front door.
- Open with explicit framing: *this is an agentic install of a collaboration system — you (Claude) follow this playbook in partnership with the human; you do not just run a script and declare done.* Kill any "run install.sh = done" reading (P3).
- Encode the **logic tree**: detect Track A/B (call `lib/detect-existing-claude-home.sh`); for Track B, the minimal-honest message (install cleanly from zero; merging into existing setup is the user + their agents' job; offer the same kernel) (P2, P8).
<!-- the Staff Engineer F5: pin registration entrypoint by concrete script name so the Layer 0 frontload list is verifiable, not aspirational — plugin-extraction-and-distribution.md item 13 gives the canonical order; register-claude-plugin is the confirmed script name -->
- Encode the **three layers** (P3, P4): Layer 0 vanilla-runnable + *maximally frontloaded* (run `bin/register-claude-plugin` — the canonical registration entrypoint per `docs/wiki/plugin-extraction-and-distribution.md` item 13, order: `clone → bin/register-claude-plugin → /reload-plugins → /coordinator:setup`; then stage the continue-onboarding handoff, pre-write the install todo/mini-plan); the restart as **"start a fresh Claude Code session and paste `/pickup state/handoffs/continue-onboarding-and-installation.md`"** — with the corrected reason (Agent Teams env var; note `/reload-plugins` activates the plugin without a cold restart, but the env var needs the fresh session). Layer 2 resumes via the handoff.
- Embed the **three-tier ecosystem map** (P6) and the **refinement-target framing** (P5): after install, you evolve *your own `~/.claude`* (git-tracked, backed up) — never the coordinator clone (a delivery truck).
- **Test surface:** `grep:` assertions — playbook contains the three tier labels verbatim; the `/pickup state/handoffs/continue-onboarding-and-installation.md` string; the "fresh session" reframing; an explicit "edit your ~/.claude, not this clone" line; no "installation complete" line gated solely on a script exit.

### C2 — Discovery surface: `AGENTS.md` front door + README pointer (P1)
**Owns:** `README.md` and a NEW top-level `AGENTS.md` (canonical sources of the publish-repo-toplevel surface; confirm source vs `dist/`). Coordinate with organic-ramp C5 (README ramp text — different section).
- **Add `AGENTS.md`** as the agent-facing front door — the emerging cross-tool convention filename a cold agent looks for *unprompted*, so discovery degrades gracefully even when the human never pastes the one-liner (the exact P1 failure). It is thin: frame "you are installing an agentic collaboration system" and route into the detailed `agent-install.md` playbook (C1). Post-install it can double as the pointer to the user's working agent-guidance.
- **README** gets a loud early line: `🤖 Agents: start here → AGENTS.md`, plus a crisper human-facing "you don't install this, your agent does." The one-liner stays as the belt-and-braces path; `AGENTS.md` is the no-one-liner-needed path.
- **Test surface:** `cited:` `AGENTS.md` exists at top level and routes to `agent-install.md`; `grep:` README contains the `🤖 Agents: start here → AGENTS.md` pointer; `cited:` a cold Claude can route README → AGENTS.md → playbook, OR land on AGENTS.md directly, in one hop.

### C3 — `commands/setup.md`: logic-tree mechanism, deep-research remedial, refinement-target close (P2, P5, P6, P8)
**Owns:** `commands/setup.md`. ⚠️ **Preserve organic-ramp C6's Phase 3/Step 8 hardware-capture step (`capture-fan-out-threshold.sh`) — do not remove or reorder it.**
- Replace the implicit `--non-interactive`-vs-interactive framing with the unified decision-dense tree vocabulary (shared with C4); wire Track A/B detection via the pinned helper (P2, P8).
- Make Phase 1.d **remedial**, not observational: deep-research is **default-on-with-opt-out** — offer to install it (pull from the GH repo), and make its presence/absence explicit in the status table (P6). Honour the OSS editorial principle: do not offer the UE stack / project-rag.
- Add the **refinement-target close** to Phase 7 next-steps: "your `~/.claude` is the surface you evolve — git-track it and back it up; never edit the coordinator clone" (P5).
- **Test surface:** `cited:` Phase 1.d offers install when absent; `grep:` status table has an explicit deep-research presence row; `grep:` Phase 7 carries the refinement-target line; `grep:` `capture-fan-out-threshold` call still present (regression guard for cross-plan coexistence).

### C4 — `commands/bootstrap-repos.md`: align choice vocabulary to the unified tree (P2)
**Owns:** `commands/bootstrap-repos.md`.
- Reconcile EXPRESS/CUSTOM with the unified decision-dense vocabulary established by the playbook + setup, so the user meets one consistent model of "where you participate in shape" across all surfaces.
- **Test surface:** `grep:` vocabulary matches the pinned tree terms; `cited:` no orphan "express = don't think" framing remains.

### C5 — Continue-onboarding handoff template + first-dogfood + partnership-shape offer (P3, P4, P7)
<!-- the Staff Engineer F0: dropped "publish.sh manifest include-list entry" from Owns — no manifest for this mirror-mode target; C5 owns only the new template file -->
**Owns:** new `templates/handoffs/continue-onboarding-and-installation.md` (the install copies it to `state/handoffs/`). New file — no overlap.
- **Align with `docs/wiki/post-install-onboarding-pattern.md`** (Movement 2 = first-dogfood; refinement-target framing already established there) — cite and extend it, do not reinvent.
<!-- the Staff Engineer F4: added scope: to the frontmatter list — pickup's commit step reads scope: (not branch:) for git add scoping; omitting it may cause a broad add on first /pickup -->
- Author the static handoff with minimal `/pickup`-valid frontmatter (`title, created, branch, status: active, predecessor: null, deployment_state: ready_to_fire, pickup_ready: true, scope:`). Before finalizing, read `skills/pickup/SKILL.md` lines 181-207 (commit step) to confirm the exact field set pickup's `git add` / scoped-commit step consumes — add any additional required fields. The test-surface must assert frontmatter passes the ACTUAL pickup commit-step field requirements, not just the classification table.
- Body "Recommended Next Steps": (1) **the first dogfood** — co-write the user's CLAUDE.md / CLAUDE.local.md together, *which is where the partnership-shape choice is offered* (PM/EM vs. manager-and-team — strongly-led offer, not a gate, framed as reversible/modifiable); (2) finish any deferred install legs; (3) `/reload-plugins` + `/reload-skills` if needed; (4) point at `~/.claude` as the evolution surface.
<!-- the Staff Engineer F0+F1: percolation mechanism corrected — coordinator-claude is mirror mode (everything-minus-excludes via .percolate-ignore), NOT manifest mode. The install-surface-completeness concern is valid; the verification shape INVERTS to a negative assertion: confirm .percolate-ignore does NOT exclude templates/. -->
- **Percolation verification (prior-art conflict #6 — install-surface-completeness, mechanism corrected):** coordinator-claude ships via **mirror mode** governed by `.percolate-ignore` — NOT a `publish.sh` manifest include-list (manifest mode only applies to deep-research-claude and holodeck). `coordinator/templates/handoffs/` is NOT currently excluded by `.percolate-ignore` (`coordinator/tasks/` is excluded at line 60, but `coordinator/templates/` is not). The install-surface-completeness requirement is therefore a NEGATIVE guard: confirm `plugins/coordinator-claude/.percolate-ignore` contains NO pattern matching `coordinator/templates/` or `templates/handoffs/`. A future `.percolate-ignore` edit that adds such a pattern would silently break delivery — add this as an executor verification step before C8. A template that ships to the user's machine is the whole point; one blocked by a rogue exclude re-creates the 2026-05-20/21 clean-install failure. This MUST be verified before the C8 PM-gated percolation fires.
- **Test surface:** `cited:` frontmatter is `/pickup`-valid per `pickup/SKILL.md`; `grep:` body contains the partnership-shape offer and the co-write-CLAUDE.md first step; `grep:` `.percolate-ignore` contains NO pattern matching `coordinator/templates/` or `templates/handoffs/` (negative assertion confirming mirror-mode shipping).

### C6 — session-start fresh-install branch + project-onboarding refinement-target touch (P5, P7)
**Owns:** `skills/session-start/SKILL.md`, `skills/project-onboarding/SKILL.md`.
<!-- the Staff Engineer F3: session-start fresh-install branch must be (a) reachable on the no-handoff path (primary path resumes via /pickup, so this branch is the fallback for users who diverge from instructions) and (b) self-limiting via a consumed-on-first-fire sentinel — without this, every no-handoff session-start for the life of the install re-offers "co-write your CLAUDE.md." -->
- Add a fresh-install orientation branch to session-start's Engage step: when a just-installed `~/.claude` with no loaded handoff is detected, orient toward "work on your `~/.claude` / co-write your CLAUDE.md" rather than the generic new-project menu (P7, no-handoff case). Align the orientation copy with `docs/wiki/post-install-onboarding-pattern.md`.
- **The branch predicate MUST be concrete and self-limiting.** Fire ONLY when (a) no handoff is loaded AND (b) a fresh-install sentinel exists (e.g. `~/.claude/.coordinator-fresh-install` written by Layer 0 during install) AND (c) that sentinel is consumed/cleared on first fire — so the branch does not re-offer on every subsequent no-handoff session. Name the sentinel file and its lifecycle (created by C1 Layer 0; cleared by C6's Engage branch on first activation). Add a test-surface assertion that the branch does NOT fire on a second clean session after the sentinel is cleared.
- Add the refinement-target framing to project-onboarding's next-steps (P5) so it does not point a new user at the clone.
- **Test surface:** `cited:` session-start has a fresh-install branch reachable on the no-handoff path; `cited:` the branch does NOT fire when the sentinel is absent (second clean session); `grep:` both skills carry the refinement-target line.

### C7 — `lib/detect-existing-claude-home.sh` + test (P8)
**Owns:** new `lib/detect-existing-claude-home.sh`, `lib/detect-existing-claude-home.test.sh`. New files — no overlap.
- Read-only, idempotent. Emit `track=A` (vanilla / install-from-zero) or `track=B` (existing structure) with a one-line reason. Track B triggers on ANY of: non-default plugins present, a substantially-edited `~/.claude/CLAUDE.md`, OR `~/.claude` is git-tracked.
- **Test surface:** `bash:` `detect-existing-claude-home.test.sh` green — A on a vanilla fixture, B on each of the three triggers independently.

### C8 — Dogfood the full flow end-to-end + closeout (all P)
**Owns:** none (read/run only; fixes route back to the owning chunk).
- Run the redesigned install end-to-end in a throwaway `~/.claude`-shaped fixture per `coordinator:dogfood` doctrine — vanilla session → discovery → logic tree → frontloaded Layer 0 → fresh session → `/pickup` → first dogfood. Binary outcome: converge or re-plan.
<!-- the Staff Engineer F6 (nitpick) + Worker Dispatch Recommendation: broaden doc-link-checker trigger from "git mv / rename only" to include link-introduction and link-retargeting — C2 adds AGENTS.md with new inbound links (README->AGENTS.md->agent-install.md) and C1 may retarget links during playbook rewrite; these are exactly the discovery path P1 is about. Schedule unconditionally for this plan. -->
- **doc-link-checker:** schedule a post-execution `doc-link-checker` closeout dispatch after C1/C2 land, covering the README → AGENTS.md → agent-install.md relative-link chain. Trigger applies to: git mv / path rename (original trigger) OR introduction of new cross-doc relative links (C2 — new AGENTS.md) OR retargeting of existing links (C1 — playbook rewrite). All three trigger shapes apply here — the doc-link-checker pass is unconditional for this plan, not conditional on rename only.
- **Percolation is PM-gated** — this plan does NOT auto-run `publish.sh`. Surface "ready to percolate to OSS coordinator-claude" to the PM at done-time.

## File-overlap analysis (parallel-dispatch gate)

| Chunk | Owns (write scope) | Overlap |
|-------|--------------------|---------|
| C1 | `agent-install.md` (source) | none |
| C2 | `README.md` (source) + new top-level `AGENTS.md` | organic-ramp C5 edits a different README section — coordinate, no conflict; AGENTS.md is new |
| C3 | `commands/setup.md` | organic-ramp C6 edits different section (Step 8) — **preserve it**; no write conflict |
| C4 | `commands/bootstrap-repos.md` | none |
| C5 | `templates/handoffs/continue-onboarding-and-installation.md` (new) | none (mirror mode ships automatically; no manifest to edit) |
<!-- the Staff Engineer F0: dropped "publish.sh manifest include-list entry" — no manifest exists for this mirror-mode target -->
| C6 | `session-start/SKILL.md`, `project-onboarding/SKILL.md` | none |
| C7 | `lib/detect-existing-claude-home.sh` (+test) (new) | none |
| C8 | — (read/run only) | n/a |

Write scopes are disjoint. With interfaces pinned (above), C1–C7 fan out; verify at the seam (C1 references the handoff path, detection helper, tiers, command names — confirm consistency at merge). C8 runs after the merge. Per-chunk size ~5–15 min; C1 and C3 are the largest — if either exceeds the 15-min ceiling at dispatch, split by problem-tag within the file.

## Cross-plan coordination

- **`2026-05-30-organic-ramp-concurrency-doctrine.md`** (in review) shares `commands/setup.md` (its C6 hardware-capture step) and `README.md` (its C5 ramp text). Both overlaps are different sections of the same files — coexist. This plan's C3 carries a regression-guard test that the `capture-fan-out-threshold` call survives. No assumption of theirs is amended → no sibling-plan body edit required.
- Scanned `docs/plans/*.md` — no other overlapping file scope or seam citations.

## Acceptance Criteria

| ID | Criterion (prose) | Test | Binding-Class | Status |
|----|-------------------|------|---------------|--------|
| AC1 | The discovery chain is structurally present: README carries the `🤖 Agents: start here → AGENTS.md` pointer AND AGENTS.md contains a link to `agent-install.md` AND `agent-install.md` exists (P1) | `grep:` README contains the `🤖 Agents: start here → AGENTS.md` line; `grep:` AGENTS.md contains a relative link to `agent-install.md`; `cited:` `agent-install.md` exists at expected source path | gate | pending realization |
<!-- the Staff Engineer F2: AC1 rewritten from unfalsifiable "a cold Claude can route in one hop" (reviewer attestation) to structural artifact assertions; behavioral discovery claim moved to AC10 dogfood -->
| AC2 | The playbook frames the install as an agentic partnership flow, not a script-is-done run (P2, P3) | `grep:` no script-gated "complete" line; partnership framing present | gate | pending realization |
| AC3 | Track A/B detection exists, is read-only/idempotent, and Track B is minimal-honest with no cherry-pick engine (P8, OOS) | `bash:` `detect-existing-claude-home.test.sh` green | gate | pending realization |
| AC4 | Three-layer bootstrap is encoded; restart reframed as "fresh session + paste `/pickup <path>`" with the correct (env-var) reason (P3, P4) | `grep:` playbook contains the `/pickup` string + fresh-session reframing | gate | pending realization |
| AC5 | The continue-onboarding handoff is `/pickup`-valid and drives the co-write-CLAUDE.md first dogfood with the partnership-shape offer (P4, P7) | `cited:` frontmatter validity + `grep:` body content | gate | pending realization |
| AC6 | Refinement target is the user's git-tracked `~/.claude`, stated across playbook + setup + project-onboarding; never the clone (P5) | `grep:` refinement-target line in all three surfaces | gate | pending realization |
| AC7 | Three-tier ecosystem map present; deep-research is default-on-with-opt-out and visible; UE stack / project-rag not offered (P6, OOS) | `grep:` tier labels + deep-research status row; `cited:` Phase 1.d remedial | gate | pending realization |
| AC8 | Choice vocabulary is unified across playbook, setup, and bootstrap-repos (P2) | `grep:` consistent terms; no orphan express/DIY binary | gate | pending realization |
| AC9 | organic-ramp C6 hardware-capture step survives the setup.md rework | `grep:` `capture-fan-out-threshold` call present | gate | pending realization |
| AC10 | Full flow dogfooded end-to-end; converges or re-plans (binary) | `cited:` C8 dogfood record | gate | pending realization |
| AC11 | `AGENTS.md` front door exists at top level, routes to the playbook, and README carries the `🤖 Agents: start here → AGENTS.md` pointer (P1) | `grep:` README pointer + `cited:` AGENTS.md routes to agent-install.md | gate | pending realization |
| AC12 | The continue-onboarding template ships under mirror mode — `plugins/coordinator-claude/.percolate-ignore` contains NO pattern matching `coordinator/templates/` or `templates/handoffs/` (install-surface-completeness; prior-art conflict #6, mechanism corrected to mirror mode) | `grep:` `.percolate-ignore` has no `templates/` exclusion (negative assertion); `bash:` `publish.sh --dry-run` shows the template in coordinator-claude NEW/UPDATE audit lines | gate | pending realization |
<!-- the Staff Engineer F0+F1: AC12 rewritten — original test greps a nonexistent manifest file (coordinator-claude is mirror mode, no publish-manifest.txt); replaced with falsifiable negative assertion on .percolate-ignore + dry-run confirmation -->

## Worker Dispatch Recommendations

<!-- the Staff Engineer reviewer: preserved verbatim per review-integrator doctrine; EM dispatches in follow-up -->
- **doc-link-checker** — after C1/C2 land, validate the README → AGENTS.md → agent-install.md relative-link chain. Rationale: C2 introduces a new top-level AGENTS.md with new inbound links; C1 may retarget links during the playbook rewrite. The "rename-only" trigger in C8 (as originally written) missed link-introduction, which is exactly the P1 discovery path. Substrate precondition: these are in-repo relative links, not private-repo absolute self-URLs, so the doc-link-checker substrate precondition is satisfied.

## Out of scope (from ratified problem-set — architectural)

- Bespoke cherry-pick / merge engine for Track B (install-atop-existing). We support install-from-zero only.
- Carving the kernel into a standalone pre-restart mini-install (registration needs the restart; kernel is functional post-restart regardless).
- Offering the UE/holodeck/game-dev stack or project-rag to a generic OSS user (`CLAUDE.local.md` editorial principle).
- Auto-percolation to OSS (`publish.sh`) — PM-gated, surfaced at done-time, not executed by this plan.

## Dispatch Ledger

> Phase 1.6 gate. One chunk per dispatch. Wave 1 = C1–C7 (file-disjoint write scopes, pinned interfaces → fan out); dispatched in an organic ramp (pilot C7+C5 → verify → expand to C1/C2/C3/C4/C6). EM-serial commit after the wave. Wave 2 = C8 after C1–C7 land + verify. Pinned cross-chunk contracts: AGENTS.md (C2) ← linked by C1; handoff path `state/handoffs/continue-onboarding-and-installation.md` (C5) ← referenced by C1; `bin/register-claude-plugin` ← cited by C1; fresh-install sentinel `~/.claude/.coordinator-fresh-install` ← created by C1 Layer 0, cleared by C6; detection helper `lib/detect-existing-claude-home.sh` (C7) ← called by C1/C3.

| dispatch # | chunk-id | one-line brief | write-files | runs | est-min | status |
|---|---|---|---|---|---|---|
| 1 | C7 | Track A/B detection helper + test | `lib/detect-existing-claude-home.sh`, `lib/detect-existing-claude-home.test.sh` | parallel (wave1 pilot) | 8 | committed |
| 2 | C5 | continue-onboarding handoff template | `templates/handoffs/continue-onboarding-and-installation.md` | parallel (wave1 pilot) | 8 | committed |
| 3 | C1 | agent-install.md playbook → logic tree | `dist/publish-repo-docs/agent-install.md` | parallel (wave1 expand) | 15 | committed |
| 4 | C2 | README pointer + new AGENTS.md front door | `dist/publish-repo-toplevel/README.md`, `dist/publish-repo-toplevel/AGENTS.md` | parallel (wave1 expand) | 10 | committed |
| 5 | C3 | setup.md logic-tree + deep-research remedial + refinement close | `commands/setup.md` | parallel (wave1 expand) | 13 | committed |
| 6 | C4 | bootstrap-repos choice-vocabulary align | `commands/bootstrap-repos.md` | parallel (wave1 expand) | 6 | committed |
| 7 | C6 | session-start fresh-install branch + project-onboarding refinement | `skills/session-start/SKILL.md`, `skills/project-onboarding/SKILL.md` | parallel (wave1 expand) | 12 | committed |

> Pinned install vocabulary (EM, shared across C1/C3/C4 to prevent seam divergence): flow = "guided install"; execution dial = **agent-led** (default) vs **hands-on**; structural fork = **Track A / Track B**; principle = "you participate in the shape decisions; the agent moves fast on mechanism." Drop "express/DIY" and "EXPRESS/CUSTOM" naming.
| 8 | C8 | dogfood full flow + doc-link-checker closeout | (read/run only) | after #1–7 | 15 | converged (3 ref bugs fixed; live-restart leg + post-publish doc-link-check deferred — see report) |

## Outcome

All 8 chunks shipped on `work/striker/2026-05-26to30` (commits `8ca90fe4`…`8a2cba1d`). Pipeline: `/shape` → ratified problem-set → `/plan` → prior-art ∥ coverage pre-flights → the Staff Engineer (REQUIRES_CHANGES→resolved) → integrator → `/execute-plan` (pilot wave C7+C5 → expand wave C1–C4+C6 → C8 dogfood). The dogfood caught 3 phantom references four prior review passes missed. **Not yet percolated to OSS** (PM-gated). Live restart→`/pickup` round-trip needs a real fresh session to validate (static flow fully verified on disk).

## Deviations

| deviation | reason | commit |
|-----------|--------|--------|
| Percolation fix inverted in-plan: C5/AC12 specified a `publish.sh` manifest include-list, corrected to a `.percolate-ignore` negative-guard | coordinator-claude is **mirror** mode, not manifest mode; prior-art Conflict #6 cited manifest-mode doctrine. Caught by the Staff Engineer (disk-verified) | `7a15b088` |
| C1 Layer 0 registration: `bin/register-claude-plugin` → reframed to `setup/install.sh` | That script does not exist for coordinator (wiki prescribes it generically; coordinator registers via the installer). Caught by C8 dogfood | `8a2cba1d` |
| `coordinator-setup-state.sh` subcommands: `record-complete`→`record setup_concluded`, `last-status`→`status` | Playbook + template cited non-existent subcommands. Caught by C8 dogfood | `8a2cba1d` |
| AC1–AC12 test cells left as backtick-prose (`pending realization`), not parser-bare | Two-altitude flow: realization is `/merge-to-main` Step 0a work; all 12 criteria verified by hand at execute time | pending |
| doc-link-checker closeout deferred to post-publish | dev-tree `AGENTS.md`/README links use *published-layout* relative paths that only resolve in the OSS repo; running it on the source tree false-positives | pending |
