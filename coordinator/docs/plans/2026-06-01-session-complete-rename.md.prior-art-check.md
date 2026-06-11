---
title: Prior-Art Check — session-complete-rename
created: 2026-06-01
author: prior-art-checker
status: implemented
kind: prior-art-check
plan: plugins/coordinator/docs/plans/2026-06-01-session-complete-rename.md
---

## Prior-Art Verification

**Plan:** `plugins/coordinator/docs/plans/2026-06-01-session-complete-rename.md`
**Verdict:** WARN
**Claims checked:** 13
**Conflicts:** 2 | **Compatible-but-relevant:** 6 | **Silent:** 5
**Corpora consulted:** project-wikis (123 files indexed) | global-wikis (minimal overlap, 5 files matched, none relevant) | lessons.md (no session-end/session-complete hits) | improvement-queue (3 hits, see below)

---

### Conflicts (plan contradicts prior art)

- **Claim #1 — CLAUDE.md § `session-end` contact points:** The plan's C6 chunk renames `/session-end` refs in `coordinator/CLAUDE.md` at L38, L139, L141, L159, L182. The CLAUDE.md doctrine text currently reads: `"/handoff` and `/session-end` are mutually exclusive" and "Session-end / weekly marker trail. `/session-end` and `/handoff` run `code-reviewer`..."
  - **Plan asserts:** All `/session-end` refs in CLAUDE.md except none are swept to `/session-complete`.
  - **Prior art (`plugins/coordinator/CLAUDE.md` — Handoff Lineage section, L182-ish):** `"/handoff` and `/session-end` are mutually exclusive — `/session-end` caps a done workstream, `/handoff` passes an in-flight one."`; and Review Sequencing section: `"Session-end / weekly marker trail. `/session-end` and `/handoff` run `code-reviewer` (Sonnet) on the diff before commit ... → `session-end-review.md`."`
  - **Why this is a conflict:** CLAUDE.md is load-bearing doctrine read at every session boot; the plan's AC6 already names this exact sweep as a gate criterion ("AC6: `/handoff` ↔ `/session-complete` mutual-exclusion doctrine reads correctly in CLAUDE.md + all wikis"), but the plan's intentional-keep list does NOT include CLAUDE.md as requiring the literal `/session-end` token to be preserved. This is compatible-direction (the rename is right), but CLAUDE.md also has a cross-ref to `→ session-end-review.md` by filename — and if C5 `git mv`s `session-end-review.md` → `session-complete-review.md`, the CLAUDE.md link in Review Sequencing (`→ session-end-review.md`) becomes a dead reference unless C6 also renames it. The plan's C6 scope says "rename command refs at L38, L139, L141, L159, L182" but does not explicitly call out the wiki-filename reference `→ session-end-review.md` at CLAUDE.md's Review Sequencing bullet. If C5 renames the wiki file and C6 misses that inline cite, CLAUDE.md becomes stale.
  - **Candidate directions for EM:**
    - `update-plan` — add `→ session-complete-review.md` to the explicit C6 sweep list if C5 does the `git mv`; ensure C6's scope explicitly covers wiki-filename cross-references in CLAUDE.md, not just command-name references.
    - `both` — the plan correctly identifies L38/L139/L141/L159/L182 but the wiki-filename cite is a distinct category that warrants its own keep/sweep call in the intentional-keep list or C6 scope note.
  - **Lean:** `update-plan`. The fix-locus is narrow: add one note to C6 scope covering the `session-end-review.md` filename reference in CLAUDE.md § Review Sequencing.

- **Claim #2 — `coordinator-tripwires.md` references `skills/session-end/SKILL.md` as a static-grep contact point:** The coordinator-tripwires wiki names `skills/session-end/SKILL.md` as a greppable contact point for the Persona-at-Sonnet block rule. The plan sweeps tripwires in C5 ("All wikis: ... `coordinator-tripwires.md` (12)") but does not mention that the tripwire entry's *contact-point path* (`skills/session-end/SKILL.md`) is itself a path that will no longer be the canonical skill location after the rename.
  - **Plan asserts:** C5 will rename every `/session-end` / `session-end` command ref → `/session-complete` in `coordinator-tripwires.md`; KEEP spec-backlink filenames intact.
  - **Prior art (`plugins/coordinator/docs/wiki/coordinator-tripwires.md` L56):** `"the rule is greppable from `CLAUDE.md` + `skills/review-code/SKILL.md` + `skills/session-end/SKILL.md` + `agents/code-reviewer.md`."` (Persona-at-Sonnet block rule contact points)
  - **Why this is a conflict:** After the rename, `skills/session-end/SKILL.md` becomes the deprecation stub, not the canonical skill. The tripwire's contact-point list should point to `skills/session-complete/SKILL.md` — the new canonical location. The old path still exists as the stub, so it will not become a dead file, but the greppability guarantee decays: the canonical rule body is now in `skills/session-complete/SKILL.md`. Also in the same file, the Blanket-commit destructive-shape gate (L68) lists `session-end` as an authorized reference token in commit subjects; after the rename, `session-complete` should also be in that list or the gate will start warning on legitimate `/session-complete` sweep commits.
  - **Candidate directions for EM:**
    - `update-plan` — C5's tripwires sweep should explicitly (a) update the Persona-at-Sonnet contact-point path from `skills/session-end/SKILL.md` → `skills/session-complete/SKILL.md`, and (b) add `session-complete` to the blanket-commit authorized reference token list in L68.
    - `both` — the tripwire wiki itself may need a note distinguishing `skills/session-end/` (deprecation stub, still greppable for the stub rule) from `skills/session-complete/` (canonical rule body).
  - **Lean:** `update-plan`. Both are clean additions to the existing C5 sweep scope; neither requires PM input.

---

### Compatible-but-relevant (plan should cite or align)

- **Claim #3 — `/handoff` ↔ `/session-end` mutual-exclusion doctrine:** Plan AC6 correctly identifies that the mutual-exclusion doctrine must be updated. Prior art in CLAUDE.md uses the specific phrasing "mutually exclusive" with `/session-end` named explicitly, and this phrasing recurs across `session-end-review.md`, `em-pm-collaboration-extras.md`, and `spinoff-handoffs.md`.
  - **Plan covers:** C5 and C6 sweep all wiki and CLAUDE.md refs; AC6 gates on CLAUDE.md L139 + handoff/SKILL.md + session-end-review wiki reading correctly.
  - **Prior art (`plugins/coordinator/docs/wiki/em-pm-collaboration-extras.md` L56):** `"The PM signals session closure by invoking /session-end, /handoff, /merge-to-main, or commit-and-stop."`
  - **Subtype:** `cite`
  - **Suggested action:** Confirm `em-pm-collaboration-extras.md` is in the C5 sweep list (the plan names it under "3" references, which aligns). The rename is compatible. Note that `em-pm-collaboration-extras.md`'s section heading "PM owns session-end determination" will itself need renaming (or a note that the heading uses the historical name) — this heading is not just a command ref but a section title. The plan's per-group rule in C5 says "rename every `/session-end` / `session-end` command ref" but the section heading `### PM owns session-end determination` is a descriptive title, not a command invocation token. Worth an explicit call in the C5 sweep rule.

- **Claim #4 — `session-end-review.md` wiki filename rename decision:** The plan notes in C5: "Wiki rename consideration: `docs/wiki/session-end-review.md` — decide at execution whether to `git mv`... Default lean: `git mv` + repoint."
  - **Plan covers:** Decision deferred to execution with a default lean.
  - **Prior art (`plugins/coordinator/docs\wiki\DIRECTORY_GUIDE.md` row 62):** `"| [session-end-review](session-end-review.md) | session-end-review | Post-executor code review at /session-end and /handoff; marker trail..."` — the DIRECTORY_GUIDE links to `session-end-review.md` by relative path.
  - **Subtype:** `cite`
  - **Suggested action:** If C5 does the `git mv`, DIRECTORY_GUIDE.md is also a repoint target. The plan's C5 scope says "Reconcile referrers in the same chunk" but does not explicitly name DIRECTORY_GUIDE.md. Add DIRECTORY_GUIDE.md to C5's referrer-reconciliation list (or confirm C8 doc-link-checker will catch it).

- **Claim #5 — `sibling-surface-parity-testing.md` parity test hardcodes `skills/session-end/SKILL.md`:** The parity testing wiki contains a live grep snippet that names `skills/session-end/SKILL.md` explicitly as a parity-test path.
  - **Plan covers:** C5 sweeps all wikis including this file (it appears in the 31-file match set). However, the plan's per-group rule is "rename every `/session-end` / `session-end` command ref." The parity test snippet uses the path `coordinator/skills/session-end/SKILL.md` — after the rename this path refers to the deprecation stub, not the canonical skill.
  - **Prior art (`plugins/coordinator/docs/wiki/sibling-surface-parity-testing.md` L84):** `` "grep 'schema_version' coordinator/skills/session-end/SKILL.md coordinator/skills/handoff/SKILL.md \" ``
  - **Subtype:** `cite`
  - **Suggested action:** The C5 sweep in `sibling-surface-parity-testing.md` should update this path to `coordinator/skills/session-complete/SKILL.md`. This is a path-in-a-code-snippet, not a prose command ref, and the plan's per-group rule ("command ref") may not catch it. Add an explicit note in C5 for snippet-embedded paths.

- **Claim #6 — `skill-budget-discipline.md` usage-count entry names `coordinator:session-end`:** The skill-budget wiki contains a usage-count table that names `coordinator:session-end` (366 invocations/30d). This is factual/historical data, not a command invocation, but it will become a stale name after the rename.
  - **Plan covers:** Not explicitly named in the plan's file list.
  - **Prior art (`plugins/coordinator/docs/wiki/skill-budget-discipline.md` L32):** `"coordinator:session-end (366)"` listed under heavy-invocation skills.
  - **Subtype:** `cite`
  - **Suggested action:** Include `skill-budget-discipline.md` in the C5 sweep. The count row should either be updated to `coordinator:session-complete` or marked as historical. The plan's keep-list item 4 covers "historical spec-backlink filenames" but not historical usage-count entries — this file is not currently in the plan's named sweep list.

- **Claim #7 — `cross-repo-communication.md` names `skills/session-end/SKILL.md` in a code-sample sentence:** The cross-repo communication wiki names `skills/session-end/SKILL.md § Step 2.66` as an operative rule location.
  - **Plan covers:** C5 lists `cross-repo-communication.md` (8 refs) in the prose sweep.
  - **Prior art (`plugins/coordinator/docs/wiki/cross-repo-communication.md` L278):** `"Operative rule lives in skills/session-end/SKILL.md § Step 2.66."` — this is a path+section reference, not just a command token.
  - **Subtype:** `cite`
  - **Suggested action:** This reference requires a path update to `skills/session-complete/SKILL.md § Step 2.66`. Confirm C5's sweep of this file covers skill-path references, not only `/session-end` command tokens. The plan's per-group rule may need a carve-out for "skill path refs" as a distinct category.

- **Claim #8 — improvement-queue entry references `skills/{session-end,handoff}/SKILL.md` as a contact point:** The coordinator improvement queue contains an entry naming `skills/{session-end,handoff}/SKILL.md` as a target file for a future dirty-tree gate extraction.
  - **Plan covers:** Not in scope — the improvement queue is not a sweep target in this plan.
  - **Prior art (`state/coordinator-improvement-queue.md` L15):** `"- 2026-05-27 | self | skills/{session-end,handoff}/SKILL.md + commands/workday-complete.md | Dirty-tree pre-terminate gate now replicated INLINE across 3 terminators..."` — this queue entry names `skills/session-end/SKILL.md` as the fix target.
  - **Subtype:** `cite`
  - **Suggested action:** After the rename lands, the improvement-queue entry's cited path becomes stale (the path still exists as the stub, but the canonical target is `skills/session-complete/SKILL.md`). This is low-urgency — the stub file remains a valid path — but the next `/learn-lessons` or `/workday-complete` queue triage should update this path. No plan change needed; informational for the EM.

---

### Silent areas (no prior art found)

- Claim #9 — `disable-model-invocation: true` frontmatter key on a stub skill: no prior art in any corpus. This appears to be a first use of this mechanism in the coordinator plugin; the plan's spike-confirmed note is the only relevant evidence.

- Claim #10 — Stored data-field / command-name split (D2 — `reviewed_at_session_end:` key retention): no prior art establishing a precedent for this pattern in any corpus. The plan correctly identifies this as a load-bearing call worth documenting inline.

- Claim #11 — `--invoker session-complete|session-end` dual-accept case arm (D3 deprecation tolerance): no prior art on dual-accept case arms in `bin/regenerate-orientation-cache.sh` or analogous scripts. First use of this tolerance pattern.

- Claim #12 — `setup/publish.sh` percolation must carry renamed skill + stub + CHANGELOG as a unit: no prior art specifically governing multi-artifact coherence constraints on percolation. `docs/wiki/plugin-extraction-and-distribution.md` covers the percolation workflow but not this specific atomicity requirement. The plan's "do NOT execute" note is correct; the claim is novel.

- Claim #13 — `{session, workday, workweek} × {start, complete}` ceremony grid as an explicit design principle: no prior art in any corpus establishes this grid as a named doctrine or a design constraint. `docs/wiki/ceremony-calibration.md` and `docs/wiki/workday-workweek-cadence.md` describe the ceremonies but do not codify the naming grid as a rule. The plan introduces this framing; the wiki may benefit from a note after landing.

---

### Verdict logic

**WARN** — two conflicts surfaced:
1. C6 scope may miss the `→ session-end-review.md` wiki-filename cross-reference in CLAUDE.md § Review Sequencing when C5 performs the `git mv`.
2. `coordinator-tripwires.md` Persona-at-Sonnet contact-point path and blanket-commit authorized token list are both affected by the rename in ways the plan's C5 per-group rule ("command ref") may not catch.

Both conflicts are `update-plan` direction — narrow, mechanical additions to existing chunk scopes. Neither requires PM input. EM should confirm these two additions before dispatching C5/C6 executors.

**Compatible-but-relevant findings** (6 items) are informational; the plan is structurally sound and the conflicts are fixable inline before execution.

---

**Cost estimate:** ~7K tokens (13 claims × ~5 corpus reads average; 3 full wiki reads + 8 grep passes + plan read)
