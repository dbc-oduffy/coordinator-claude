---
title: Prior-Art Check — workstream-rename
created: 2026-06-01
author: prior-art-checker
status: implemented
kind: prior-art-check
plan: plugins/coordinator/docs/plans/2026-06-01-workstream-rename.md
---

## Prior-Art Verification

**Plan:** `plugins/coordinator/docs/plans/2026-06-01-workstream-rename.md`
**Verdict:** WARN
**Claims checked:** 22
**Conflicts:** 3 | **Compatible-but-relevant:** 8 | **Silent:** 11
**Corpora consulted:** project-wikis (123+ files indexed) | global-wikis (~/.claude/docs/wiki/, not a separate corpus — same repo) | lessons.md (no session-* hits) | improvement-queue (1 relevant hit)

---

### Conflicts (plan contradicts prior art)

- **Claim #1 — `--blanket` authorized-token list in `scoped-safety-commits.md`:** The plan asserts (D3/C4) that `CLAUDE_INVOKING_COMMAND=session-start` gates `--blanket` and must be updated to `=workstream-start`, with the old token retained for the deprecation window. The canonical allow-list is documented twice in the wiki with explicit enumeration.
  - **Plan asserts:** "CLAUDE_INVOKING_COMMAND=session-start → =workstream-start; coordinator-safe-commit's --blanket gate must accept BOTH old and new tokens (update the two tests to assert both)."
  - **Prior art (`docs/wiki/scoped-safety-commits.md` L91):** "`--blanket` enforcement: The `--blanket` flag is accepted only when `$CLAUDE_INVOKING_COMMAND` is one of: `session-start`, `workday-complete`, `update-docs`, `relay-protocol`, `distillation`. Any other caller gets: [error message]"
  - **Prior art (`docs/wiki/scoped-safety-commits.md` L205):** "Only valid when `$CLAUDE_INVOKING_COMMAND` is one of: `session-start`, `workday-complete`, `update-docs`, `relay-protocol`, `distillation`. The helper rejects `--blanket` from all other callers."
  - **Why this is a conflict:** The wiki enumerates the allow-list explicitly in two places; neither lists `workstream-start`. The plan is correct that the list must be updated, but the wiki itself is also a sweep target — it is not enough to update `bin/coordinator-safe-commit`; `scoped-safety-commits.md` must also enumerate `workstream-start` (and retain `session-start`) or the wiki documents a stale allow-list. The plan's C4 scope covers the binary and tests, and C6 covers wiki prose, but the interaction — the wiki's own enumerated token list — is a functional spec that the prose sweep may treat as a plain rename rather than an additive update (add `workstream-start`, retain `session-start` for deprecation window).
  - **Candidate directions for EM:**
    - `update-plan` — explicitly call out in C4 (or C6 notes for scoped-safety-commits.md) that the allow-list enumerations in the wiki must be updated additively (add new, retain old) not via simple rename, matching the same dual-accept logic the binary gets.
    - `both` — the wiki itself may warrant a note that the token list is dual during the deprecation window.
  - **Lean:** `update-plan`. Narrow addition to C6 scope: for `scoped-safety-commits.md`, the token-list update is additive (add `workstream-start`, retain `session-start`), not a rename.

- **Claim #2 — `coordinator-tripwires.md` Persona-at-Sonnet contact-point path:** The plan (D4/C4) states that "Persona-at-Sonnet contact-point paths" must be updated to the renamed skill dirs. This directly carries over Conflict #2 from the session-complete-rename prior-art sidecar, but the unified plan now renames BOTH skills, creating two stale contact-point paths.
  - **Plan asserts:** "Update the Persona-at-Sonnet contact-point paths to the renamed skill dirs."
  - **Prior art (`docs/wiki/coordinator-tripwires.md` L56):** "the rule is greppable from `CLAUDE.md` + `skills/review-code/SKILL.md` + `skills/session-end/SKILL.md` + `agents/code-reviewer.md`."
  - **Why this is a conflict:** After both renames, `skills/session-end/SKILL.md` becomes the deprecation stub and `skills/session-start/SKILL.md` becomes the deprecation stub. The canonical rule bodies move to `skills/workstream-complete/SKILL.md` and `skills/workstream-start/SKILL.md`. The tripwire's contact-point list must be updated to point to the new canonical locations. Additionally: the plan's D4/C4 mentions "blanket-commit authorized-token list" in `coordinator-tripwires.md` — but the plan needs to confirm that this token list addition is additive (old tokens retained during deprecation window), not a replacement.
  - **Candidate directions for EM:**
    - `update-plan` — C4's tripwires sweep must explicitly (a) update both Persona-at-Sonnet contact-point paths to the new canonical skill dirs, and (b) confirm the blanket-commit authorized-token additions are additive (retain `session-end`, `session-start`; add `workstream-complete`, `workstream-start`). The plan currently says "add both new tokens" for coordinator-tripwires but does not explicitly confirm retention of old tokens in that list.
  - **Lean:** `update-plan`. The plan already names this; the gap is specificity on additive-vs-replace for the token list.

- **Claim #3 — `CLAUDE.md` `/handoff` ↔ `/session-end` mutual-exclusion doctrine:** The plan (AC9) requires the CLAUDE.md `/handoff` ↔ `/workstream-complete` mutex to read correctly after the sweep. This is load-bearing doctrine that the EM reads at every session open — the CLAUDE.md is explicitly cited as "load-bearing — read at every session boot."
  - **Plan asserts:** "AC9: `/handoff` ↔ `/workstream-complete` mutex correct [in CLAUDE.md + CONTEXT.md]."
  - **Prior art (`plugins/coordinator/CLAUDE.md` L139):** "`/handoff` and `/session-end` are mutually exclusive — `/session-end` caps a done workstream, `/handoff` passes an in-flight one. Two workstreams: close each separately, naming which is which."
  - **Prior art (`plugins/coordinator/CLAUDE.md` Review Sequencing section):** "Session-end / weekly marker trail. `/session-end` and `/handoff` run `code-reviewer` (Sonnet) on the diff before commit (large diffs partition across parallel dispatches); records at `state/review-trail/*.json`. `/workweek-complete` Step 7... → `session-end-review.md`."
  - **Why this is a conflict:** CLAUDE.md is load-bearing doctrine read at every session. The second citation also contains a wiki filename cross-reference `→ session-end-review.md` — if C6 `git mv`s `session-end-review.md` → `workstream-complete-review.md` (or similar), the CLAUDE.md inline cite becomes a dead reference. The session-complete-rename prior-art sidecar (Conflict #1) already flagged this exact gap; the unified plan inherits it and should ensure C7's CLAUDE.md sweep explicitly covers both the command-ref update AND the wiki-filename cross-reference update if C6 renames the wiki file.
  - **Candidate directions for EM:**
    - `update-plan` — in C7's CLAUDE.md scope, add an explicit call-out for the `→ session-end-review.md` wiki-filename cross-reference in the Review Sequencing bullet. The keep/mv decision for `session-end-review.md` (which C6 defers to execution) must be resolved before C7 executes, or C7 must conditionally handle both cases.
  - **Lean:** `update-plan`. Narrow. The session-complete-rename prior-art sidecar's Conflict #1 identified this same gap at `update-plan` lean; this plan inherits it.

---

### Compatible-but-relevant (plan should cite or align)

- **Claim #4 — the Staff Engineer's "coin vs. formalize" finding on session-boot-nomenclature plan:** The session-boot-nomenclature plan (cadb320b) carried an integrated the Staff Engineer finding (Finding 2) that the term "session boot" was not a coinage but a formalization of existing organic use across 6+ surfaces. The current plan reverts the coinage entirely. The Staff Engineer finding argued FOR formalizing (not for the coinage per se), but it also established that "session boot" already has 33 organic occurrences across 22 files pre-cadb320b.
  - **Plan covers:** "Eliminate the `session boot` coinage (33 files) → platform vocabulary." Notes that "session boot" pre-existed casually in ~22 of these 33 files before cadb320b.
  - **Prior art (`docs/plans/2026-06-01-session-boot-nomenclature.md`, the Staff Engineer Finding 2, inline comment L21):** "<!-- Review: the Staff Engineer (Finding 2) — 'coin' is factually wrong; 'session boot' already appears in tiered-context-loading.md, implementation-standards-by-domain.md, learn-lessons-routing.md, daily-branch-discipline.md, eager-agent-calibration.md, coordinator/CLAUDE.md L149. The plan formalizes an existing informal convention; 'coin' undercuts a nomenclature plan's authority. -->"
  - **Subtype:** `cite`
  - **Suggested action:** The plan's D5 correctly establishes the elimination as per-occurrence judgment (not a mechanical revert of cadb320b). However, the Staff Engineer's finding confirms that ~22 of the 33 occurrences pre-existed organically — meaning D5's "session boot" → "session start" replacement in temporal-prose contexts may land in files that also have the older pre-cadb320b usage. The executor for C6/D5 should be aware: the pre-existing organic occurrences also need disambiguation (they were left ambiguous pre-cadb320b, which is the original problem). The current plan's D5 sweep covers this, but the Staff Engineer finding is cited evidence that the organic pre-existence was the reason "coin" was wrong. The direction-of-correction (eliminate vs formalize) was PM-ratified; this is informational context for the reviewer.

- **Claim #5 — Deprecation-cycle calibration from `ceremony-calibration.md`:** The plan proposes deprecation stubs (D1) for both `/session-start` and `/session-end`. The `ceremony-calibration.md` wiki establishes a consumer-count-based deprecation calibration doctrine.
  - **Plan covers:** "Aliases preserve the shipped names. Both stubs ship via `setup/publish.sh`." Rationale: "Do NOT hard-break the shipped `/session-start` / `/session-end` names — the two stubs are required."
  - **Prior art (`docs/wiki/ceremony-calibration.md` § Deprecation-cycle calibration):** "When facing a (a) direct ship / (b) opt-in for one cycle / (c) opt-out indefinitely decision, the **first question** is 'how many consumers?' — not 'what's the right posture?'. N ≤ 2 (visible in `git grep`): direct ship. Migrate the consumers in the same commit if needed. No flag, no cycle, no doc note about deprecation... N large (diffuse / external): standard deprecation cycle applies."
  - **Subtype:** `cite`
  - **Suggested action:** The plan's stub rationale ("aliases preserve the shipped names") implicitly invokes a large-consumer-count scenario. The ceremony-calibration wiki would ask: what is the actual consumer count for `/session-start` and `/session-end`? The plan establishes 86 files / 318 occurrences for `session-start` and 95 files / 379 occurrences for `session-end` — these are overwhelmingly **internal coordinator files**, all in-org, visible via `git grep`. Under the ceremony-calibration doctrine, this is arguably the "N small (≤10, all in-org): direct ship with a release note" scenario, where stubs are optional. The PM-ratified decision to use stubs is likely driven by the OSS distribution concern (external operators typing `/session-start`), which IS the diffuse-external case. The plan should note which consumers are in-org (swept by C6) vs. external (OSS operators using the shipped plugin) — the stub rationale properly applies to the external OSS consumers, not to the in-repo references being swept. This is informational; the stub decision is reasonable for OSS consumers and the plan's anti-scope already names this.

- **Claim #6 — `scoped-safety-commits.md` wiki as a sweep target for the ceremony-token table:** The plan's C6 sweeps "all `docs/wiki/**`" but the specific token-enumeration table in `scoped-safety-commits.md` is a functional spec table (the allow-list), not prose. This was raised as a compatible-but-relevant hit from the session-complete-rename prior-art sidecar (Claim #6 of that sidecar named `skill-budget-discipline.md`; analogous concern applies here).
  - **Plan covers:** C4 covers `bin/coordinator-safe-commit` binary and `docs/wiki/scoped-safety-commits.md` (the plan says "CLAUDE_INVOKING_COMMAND=session-start callers (scoped-safety-commits.md L200...)"). However, the sweep of `scoped-safety-commits.md` is under C4 (runtime/commit-gate), not C6.
  - **Prior art (`docs/wiki/scoped-safety-commits.md` L200):** "`CLAUDE_INVOKING_COMMAND=session-start \` ... (code block showing the blanket invocation example)."
  - **Subtype:** `cite`
  - **Suggested action:** Good — the plan explicitly scopes `scoped-safety-commits.md` to C4. Confirm that C4's treatment of this file is additive (update the code example to show `workstream-start`, retain or note the `session-start` tolerance) and that the two allow-list prose paragraphs at L91 and L205 are both updated. No plan change needed if C4's executor brief is clear about both locations.

- **Claim #7 — `ceremony-calibration.md` § Session-end-as-defer uses `/session-end` in doctrine prose:** The ceremony-calibration wiki has a section heading and body that uses `/session-end` as the canonical term for a session-lifecycle pattern.
  - **Plan covers:** C6 sweeps "all `docs/wiki/**`" including ceremony-calibration.md. However this section's meaning is substantive — "session-end-as-defer is hedging in disguise" — and after the rename becomes a `/workstream-complete`-as-defer concept. The section heading itself may need renaming.
  - **Prior art (`docs/wiki/ceremony-calibration.md` § Session-end-as-defer is hedging in disguise, L104–106):** "Mid-session offering to defer non-blocking work to a future session — 'want me to session-end and pick this up next time?' — is the anti-ambition tell... Default: keep going. Only invoke session-end when it's the *cheapest* remaining action, not the easiest *to ask permission for*."
  - **Subtype:** `cite`
  - **Suggested action:** Confirm C6's ceremony-calibration.md sweep renames both the section heading (from "Session-end-as-defer" to "Workstream-complete-as-defer" or similar) and the inline `/session-end` command references in the body, not just the slash-command tokens. The section title is a named pattern, not merely a command name — renaming the command without renaming the pattern-name would leave the calibration vocabulary partially stale.

- **Claim #8 — `improvement-queue.md` entry cites `skills/{session-end,handoff}/SKILL.md` as a target path:** A live improvement-queue entry names `skills/session-end/SKILL.md` as the fix target for a dirty-tree pre-terminate gate extraction.
  - **Plan covers:** C8 ("Update stale improvement-queue path refs.") explicitly covers this.
  - **Prior art (`~/.claude/state/coordinator-improvement-queue.md` L15):** "- 2026-05-27 | self | `skills/{session-end,handoff}/SKILL.md` + `commands/workday-complete.md` | Dirty-tree pre-terminate gate now replicated INLINE across 3 terminators (instance-#3; byte-varied <terminator> tokens make inline correct per ceremony-calibration, NOT snippet-extraction yet); extract to snippets/ + bin/verify-dirty-tree-gate-sync.sh ONLY at a 4th terminator OR byte-identical convergence"
  - **Subtype:** `cite`
  - **Suggested action:** C8 already plans to update this. After the rename, the cited path `skills/session-end/SKILL.md` still exists as a deprecation stub (so it's not a dead path), but `skills/workstream-complete/SKILL.md` is the new canonical target. The queue entry should be updated to `skills/{workstream-complete,handoff}/SKILL.md` so the next `/learn-lessons` or queue triage doesn't follow a stub into the wrong body. C8 is the right scope; this is confirmatory.

- **Claim #9 — `coordinator-tripwires.md` blanket-commit authorized-token list in addition to Persona-at-Sonnet contact points:** The plan (D4) names both the Persona-at-Sonnet contact-point paths AND the blanket-commit authorized-token list in coordinator-tripwires.md. The session-complete-rename prior-art sidecar (Conflict #2, Lean: update-plan) flagged that the tripwire's blanket-commit token list must add `session-complete` — the current plan extends this to also adding `workstream-start` and `workstream-complete`.
  - **Plan covers:** "bin/coordinator-safe-commit (`\bsession-end\b` ceremony regex + blanket authorized-token list) and `docs/wiki/coordinator-tripwires.md` (blanket-commit authorized-token list) must each recognize `workstream-start` and `workstream-complete` alongside the retained `session-start`/`session-end`."
  - **Prior art (session-complete-rename prior-art sidecar Conflict #2 lean):** "Lean: update-plan. Both are clean additions to the existing C5 sweep scope; neither requires PM input."
  - **Subtype:** `cite`
  - **Suggested action:** The plan correctly absorbs the session-complete-rename sidecar's Conflict #2 recommendation. The prior-art sidecar for that plan confirmed both operations (contact-point path update AND blanket-commit token addition) as `update-plan` direction. This is confirmatory.

- **Claim #10 — `disable-model-invocation: true` precedent on stub skills:** The plan uses `disable-model-invocation: true` on both deprecation stubs (D1). The session-complete-rename prior-art sidecar classified this as SILENT (Claim #9) — first use in the coordinator plugin.
  - **Plan covers:** stub SKILL.md template with `disable-model-invocation: true` shown verbatim in D1.
  - **Prior art (`2026-06-01-session-complete-rename.md.prior-art-check.md` Claim #9):** "Claim #9 — `disable-model-invocation: true` frontmatter key on a stub skill: no prior art in any corpus. This appears to be a first use of this mechanism in the coordinator plugin; the plan's spike-confirmed note is the only relevant evidence."
  - **Subtype:** `cite`
  - **Suggested action:** The spike-confirmed research in the superseded plan (`2026-06-01-session-complete-rename.md` — verified via claude-code-guide) is the supporting evidence for this mechanism. The current plan inherits that spike result. The reviewer should confirm the spike evidence is cited or remains accessible (it is in the superseded plan, which the current plan says to retain as audit trail).

- **Claim #11 — `session-end-review.md` wiki rename decision (wiki `git mv` decision for C6):** The plan defers the rename decision for `docs/wiki/session-end-review.md` and `docs/wiki/plugin-session-start-hooks.md` to execution, with per-file reasoning. The `plugin-session-start-hooks.md` keep-filename decision was made in the session-boot-nomenclature plan and confirmed by its prior-art checker.
  - **Plan covers:** "`plugin-session-start-hooks.md` is literally about the `SessionStart` platform hook → likely keep filename, reframe. Triggers C9 doc-link-checker."
  - **Prior art (`2026-06-01-session-boot-nomenclature.md.prior-art-check.md` Claim #8):** "The plan's decision to keep the filename is consistent with naming-discipline doctrine. The plan is NOT doing a rename, so no `doc-link-checker` closeout chunk is required."
  - **Prior art (`docs/wiki/naming-discipline.md` opening):** "Names are cheap to change once, expensive to change twice, and very expensive to change in anticipation of occupants that never arrive. Refuse speculative umbrella renames..."
  - **Subtype:** `cite`
  - **Suggested action:** The `plugin-session-start-hooks.md` no-rename decision is consistent with naming-discipline doctrine AND was already confirmed by the session-boot-nomenclature prior-art sidecar. The plan's default lean here is correct. For `session-end-review.md`, the session-complete-rename prior-art sidecar (Compatible-but-relevant Claim #4) flagged that DIRECTORY_GUIDE.md is a repoint target if `git mv` is chosen — the current plan's C9 doc-link-checker covers this, but confirm DIRECTORY_GUIDE.md is explicitly listed or in-scope.

---

### Silent areas (no prior art found)

- Claim #12 — `{workstream, workday, workweek} × {start, complete}` ceremony grid as a first-class named doctrine replacing `{session, workday, workweek}`: no prior art establishes this grid shape as a codified design constraint; the prior grids were described but not mandated. Session-complete-rename sidecar Claim #13 established this as SILENT; the current plan extends the grid with `workstream-*`, confirming net-new.
- Claim #13 — Reversal of the "session boot" coinage (D5 eliminating cadb320b's formalization): no prior art prescribes that once a terminology formalization is committed it must be retained. The PM ratified the reversal; no prior art prevents it.
- Claim #14 — Dual-accept case arm in `regenerate-orientation-cache.sh` (`workstream-complete|session-end|handoff`): session-complete-rename sidecar Claim #11 established this pattern as SILENT (first use of dual-accept tolerance). The current plan extends the pattern to also cover `workstream-start` — still silent in the corpus.
- Claim #15 — `setup/publish.sh` percolation must carry renamed skills + both stubs + CHANGELOG as a unit: session-complete-rename sidecar Claim #12 established this as SILENT. The current plan inherits the same claim.
- Claim #16 — `reviewed_at_session_end:` schema key retention with documented command-name/field-name split (D2): session-complete-rename sidecar Claim #10 established this as SILENT. No prior art on this split pattern.
- Claim #17 — Anti-scope: Do NOT rename `reviewed_at_session_end:` stored key: confirmed SILENT; no prior art establishing preservation vs. migration as a doctrine for stored field names under command renames.
- Claim #18 — No `git revert cadb320b` (eliminate in-place via C5/C7): no prior art on "in-place elimination preferred over git revert for a coinage commit." The plan's reasoning is structurally sound (revert would also undo disambiguation logic and conflict with sibling commits); no corpus evidence for or against.
- Claim #19 — Chunks C1/C2 are serial-core, C4/C5/C6 are parallel-safe (fan-out shape): no prior art on the specific parallelization shape here; dispatching-parallel-agents.md confirms file-overlap is the gate, and the plan's chunk breakdown is consistent with that doctrine.
- Claim #20 — CONTEXT.md ceremony-grid entry rewrite to `{workstream,workday,workweek}` (D5 / C7): the ceremony-grid entry was created by cadb320b; reverting it is the corollary of the PM-ratified direction. No prior art prevents the update.
- Claim #21 — `hooks/scripts/tests/test-nudge-improvement-queue-write.sh` as a functional-string sweep target: the session-complete-rename plan-coverage sidecar (MISSED-16) flagged this test file as containing a functional string `coordinator:session-end` that may need updating. The current plan's C6 scope says "other fixtures naming the commands → rename, run the touched tests" — this file appears to be in-scope but was identified as a gap in the predecessor.
- Claim #22 — Dogfood: run `/workstream-complete` on this workstream's own landing (C9): no prior art on dogfooding a renamed command on its own landing commit. Consistent with dogfooding-doctrine.md's binary-outcome requirement; silent on self-application.

---

### Verdict logic

**WARN** — three conflicts surfaced:

1. **Conflict #1** (`scoped-safety-commits.md` token allow-list): The wiki's two explicit allow-list enumerations (L91, L205) are functional specs, not merely prose. C6 must treat them additively (add `workstream-start`, retain `session-start`) rather than as a plain rename. Narrow `update-plan` fix to C4's scope note for this file.

2. **Conflict #2** (`coordinator-tripwires.md` dual-gap): Both Persona-at-Sonnet contact-point paths (now TWO stale paths after the unified rename) and the blanket-commit token list need explicit additive treatment. The plan names this in D4/C4 but the "additive vs. replace" framing is underspecified for the token list. Narrow `update-plan` fix.

3. **Conflict #3** (`CLAUDE.md` `/handoff` ↔ `/session-end` mutex + wiki-filename cross-ref): Load-bearing doctrine in CLAUDE.md that changes meaning after the rename; AND a dead-wiki-ref risk if C6 `git mv`s `session-end-review.md`. C7's CLAUDE.md sweep must explicitly resolve the `→ session-end-review.md` filename cite in the Review Sequencing bullet. Inherited from session-complete-rename prior-art Conflict #1.

All three are `update-plan` direction. None require PM input. Neither rises to BLOCKED-SURFACE-TO-PM level — the plan's AC9 gate requires the mutex to read correctly, which is the right net, but the path to getting there needs the three specific additions above.

**Compatible-but-relevant findings** (8 items) are informational or confirmatory; the plan is architecturally sound and the conflicts are narrow.

---

**Cost estimate:** ~9K tokens (22 claims × ~4 corpus reads avg; 5 full wiki/plan reads + prior-sidecar reads + grep passes)
