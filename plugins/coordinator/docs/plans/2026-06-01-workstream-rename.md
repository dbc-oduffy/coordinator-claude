---
title: "Unified workstream-* rename + platform-vocabulary alignment"
date: 2026-06-01
slug: workstream-rename
scope_mode: feature
status: draft
workstream: workstream-rename
picked_up_from: tasks/handoffs/2026-06-01_132000_05c3317c.md
supersedes:
  - plugins/coordinator/docs/plans/2026-06-01-session-boot-nomenclature.md  # front-half; coinage now reverted
  - plugins/coordinator/docs/plans/2026-06-01-session-complete-rename.md     # back-half; retargeted to workstream-complete
problem_set: PM-ratified (2026-06-01) — dissolve the /session-* skill ↔ Session* platform-hook collision at its source by renaming the skills off "session"
---

# Unified `workstream-*` rename + platform-vocabulary alignment

Rename **both** session-scoped lifecycle skills off the word "session" so no coordinator skill name can ever shadow a Claude Code `Session*` platform-hook event, and revert the now-obsolete "session boot" coinage in favour of strict platform vocabulary. One coherent operation, three sweep dimensions:

1. **`/session-start` → `/workstream-start`** (86 files / 318 occ) + deprecation alias.
2. **`/session-end` → `/workstream-complete`** (95 files / 379 occ) + deprecation alias.
3. **Eliminate the `session boot` coinage** (33 files) → platform vocabulary (`SessionStart` for machinery, "session start" for temporal prose).

**Why (PM-ratified).** The collision (`/session-start` *skill* vs `SessionStart` *platform hook*) existed only because our skills *shared the word "session"* with platform hook events (`SessionStart` AND `SessionEnd` both exist, verified 2026-06-01 against https://code.claude.com/docs/en/hooks). Coining "session boot" papered over the shared word with a third term — more confabulation surface, not less. Renaming the skills off "session" dissolves the collision at its source: no coinage, no glossary bridge, zero shadow risk. The ceremony grid becomes a clean uniform **`{workstream, workday, workweek} × {start, complete}`** family.

**Consistency with the prior anti-scope.** The original back-half handoff said "do NOT rename `/session-start`" — but that reservation was specifically against *purpose-naming* (`/orient`) that would break the positional grid. `/workstream-start` *preserves* the positional grid (parallel to `/workday-start`), so this is a coherent evolution of the original intent, not a contradiction. PM ratified the reversal 2026-06-01.

## Scope mode

`feature` — bulk mechanical rename, but with (a) a new deprecation-alias mechanism (two stub skills), (b) a stored-data-field decision with schema-validation implications, (c) commit-gate machinery that must recognize the new ceremony tokens, and (d) a high-judgment per-occurrence disambiguation sweep. Feature-depth review (the Staff Engineer) is warranted.

## Substrate verified at plan-write time (2026-06-01, HEAD 07deb77b)

**Platform-vocabulary ground truth (the disambiguation oracle):**
- `SessionStart` (PascalCase, no hyphen) — literal platform hook event, **160 occurrences, MUST NOT rename**. Distinguished from the renamable `session-start` by the absence of a hyphen. The key insight: **`Session-start` (hyphenated, any casing) can NEVER collide with `SessionStart` (no hyphen)** — so the sweep guard should be **case-insensitive on the HYPHENATED token**, then exclude only the no-hyphen PascalCase `SessionStart`/`SessionEnd`. This catches capitalized-prose forms (`Session-start`, `Session-End`, `Session-end`) that are skill/ceremony references and SHOULD rename. Confirmed sites carrying these forms: `skills/pickup/SKILL.md:12`, `skills/session-start/SKILL.md:191`, `commands/workday-start.md:479`, `docs/wiki/session-end-review.md:9` (heading), `docs/wiki/cross-plugin-whoami-contract.md:231`, `bin/probe-cwd-project-rag-relevance.sh:2`.
<!-- Review: the Staff Engineer F0 — original "case-sensitive lowercase" guard silently skips leading-cap hyphenated prose forms (Session-start, Session-End) that DO refer to the skill. Safe because Session-start (hyphen) can never collide with SessionStart (no hyphen) at any casing. -->
- `SessionEnd` (PascalCase, no hyphen) — also a real platform hook event (verified). The renamable tokens are `session-end` AND `Session-end`/`Session-End` (all hyphenated, any casing); the platform `SessionEnd` (no hyphen) is KEEP. (No `Stop`/`SessionEnd` matcher is wired in our `hooks.json` — confirmed; the back-end "auto-fire" of the skill is doctrine prose, not machinery.)
- Bare spaced **"session start"** (temporal) — platform-sanctioned loose prose for "the moment a session begins"; KEEP as the replacement target for temporal `session boot`.

**Skills (both invoked by `name:` frontmatter; dir name is convention only):**
- `skills/session-start/SKILL.md`, `name: session-start`, `description: Orient session — preflight, load context, choose work`.
- `skills/session-end/SKILL.md`, `name: session-end`.
- **Alias mechanism (spike-resolved):** Claude Code has **no native skill-alias support** (no `aliases:`/`redirect:` frontmatter key; verified via claude-code-guide against official plugins docs). The only mechanism to keep an old name resolving is a **thin stub skill** at the old dir/`name:` that redirects to the renamed skill. Two stubs needed (one per renamed skill).

**Runtime / commit-gate tokens (the functional surface — broader than prose):**
- `bin/regenerate-orientation-cache.sh`: `--invoker session-end` case arm (`session-end|handoff) TIER=mid-session`, L44 + doc comments L9/14/18/38/45). `session-start` is NOT in this case list.
- `CLAUDE_INVOKING_COMMAND=session-start` is a **commit-gate token**: it gates `coordinator-safe-commit --blanket` (allows blanket staging when invoked from the orientation skill). Live in `skills/session-start/SKILL.md` L26, `docs/wiki/scoped-safety-commits.md` L200, and TWO tests (`bin/tests/test-coordinator-safe-commit.sh` T9 L292, `tests/plugin-ecosystem/hooks-behavior.test.js` L148).
- `bin/coordinator-safe-commit` carries **TWO distinct, independent mechanisms** (do not conflate — pre-flight correction):
  - **(a) `do_blanket` caller-authorization list** (~L671-673): `session-start, workday-complete, update-docs, relay-protocol, distillation`. Authorizes which ceremonies may call `--blanket`. **`session-end` was never in this list** — `/session-start` IS (the pre-orientation blanket sweep). Renaming `session-start` must update THIS list, additively.
  - **(b) commit-subject ceremony-detection regex** (~L738): includes `session-end` alongside `handoff`/`spinoff`. Detects ceremony commit subjects. Renaming `session-end` adds `workstream-complete` HERE, additively.
  - Whether `workstream-complete` (renamed `session-end` skill) needs to JOIN list (a) depends on whether that skill actually invokes `--blanket` — **RESOLVED: `workstream-complete` does NOT need to join the do_blanket list** (the Staff Engineer confirmed via grep that the session-end skill never invokes `coordinator-safe-commit --blanket` — the conditional verify-gate resolves to NO).
  <!-- Review: the Staff Engineer F1 — do_blanket has FOUR touchpoints, not one; missing the ppid-fallback and error-string touchpoints would break /workstream-start --blanket when the env var is unset. -->
  - **IMPORTANT — `do_blanket` has FOUR touchpoints, all must be updated (F1 correction):**
    1. **L671-673 env-var match** — additive: add `workstream-start`, retain `session-start`.
    2. **L685 ppid-FALLBACK** — string-matches the literal caller filename `*"session-start.md"*`; add `*"workstream-start.md"*` alongside retained `*"session-start.md"*`. **This is the critical gap:** if the env var is unset (common in ad-hoc invocations), only the ppid-fallback authorizes the call — if it isn't updated, `/workstream-start --blanket` silently fails authorization after C2 renames the skill dir.
    3. **L694 user-facing ERROR string** — lists authorized ceremonies; add `/workstream-start` alongside retained `/session-start`.
    4. **L19 header-comment doc** — additive description update.
- The allow-list is ALSO documented in `docs/wiki/scoped-safety-commits.md` (L91, L205) — additive doc update, must match the code.

**Stored data field:** `reviewed_at_session_end:` — real frontmatter key in `schemas/handoff.yaml` (L101) and `schemas/handoff-archived.yaml` (L48). Every other `session_end` token in those schemas is prose or a spec-backlink filename, not the key.

**`session boot` footprint:** 33 files (excl. `.pyc` and the to-be-superseded plan docs). Overwhelmingly **temporal prose** ("at/on/every session boot" = when a session opens) plus a handful of **machinery-naming** uses (the `SessionStart` hook firing). `cadb320b` *formalized* the coinage (glossary + reframes) but the phrase pre-existed casually in ~22 of these files. Elimination is a per-occurrence judgment sweep, NOT `git revert cadb320b`.

**Baselines to converge against:** `session-start` ~318 occ / 86 files; `session-end` ~379 occ / 95 files; `session boot` 33 files. Reconcile against the keep-list, not raw counts.

## Design decisions

### D1 — Two deprecation-alias stub skills (spike-confirmed)
For each rename: `git mv skills/<old>/ skills/<new>/`, update dir + `name:`, then create a NEW `skills/<old>/SKILL.md`:
```markdown
<!-- VERBATIM (substitute old/new per skill) -->
---
name: session-start
description: "[DEPRECATED] Renamed to /coordinator:workstream-start. Run that instead."
disable-model-invocation: true
argument-hint: "[task-description]"
---

# `/session-start` — Renamed to `/workstream-start`

Renamed to **`/coordinator:workstream-start`** to align with the
`{workstream, workday, workweek} × {start, complete}` ceremony grid and to stop
shadowing the `SessionStart` platform hook event. Behavior is identical.
Run `/coordinator:workstream-start`.

(Deprecation stub — remove after the deprecation window; see CHANGELOG.)
```
Aliases preserve the **shipped** names (`/session-start`, `/session-end`). `/session-complete` never shipped → no alias for it. Both stubs ship via `setup/publish.sh`.

### D2 — Keep the `reviewed_at_session_end:` key; document the split
KEEP the key (renaming it invalidates existing handoff records against the schema). Add a one-line comment in both schemas documenting that the stored field retains the historical `session_end` token by design while the command renamed to `/workstream-complete`. No back-compat reader needed (key never changes).

### D3 — Runtime/commit-gate tokens: rename to `workstream-*`, tolerate old tokens
- `--invoker session-end` → `--invoker workstream-complete`; case arm accepts BOTH (`workstream-complete|session-end|handoff`) for the deprecation window.
- `CLAUDE_INVOKING_COMMAND=session-start` → `=workstream-start`; `coordinator-safe-commit`'s `--blanket` gate must accept BOTH old and new tokens (update the two tests to assert both).
- `bogus` token still errors.

### D4 — Commit machinery: additive ceremony-token recognition (two mechanisms, never replace)
ALL commit-gate updates are **additive** — add the new `workstream-*` token, RETAIN the old for the deprecation window. Per the two-mechanism distinction in § Substrate:
<!-- Review: the Staff Engineer F1 — the do_blanket gate has FOUR touchpoints, not one; the ppid-fallback at L685 is independent of the env-var list and must also be updated. Conditional resolved: workstream-complete does NOT join do_blanket (session-end never calls --blanket). -->
- `coordinator-safe-commit` (a) `do_blanket` — **FOUR touchpoints, all additive:**
  1. L671-673 env list: add `workstream-start` (retain `session-start`)
  2. L685 ppid-fallback: add `*"workstream-start.md"*` (retain `*"session-start.md"*`)
  3. L694 error string: add `/workstream-start` (retain `/session-start`)
  4. L19 header-comment doc: additive description update
  - `workstream-complete` does **NOT** join this list — **RESOLVED NO** (the Staff Engineer confirmed via grep that `session-end`/`workstream-complete` never invokes `coordinator-safe-commit --blanket`).
- `coordinator-safe-commit` (b) subject-detection regex: add `workstream-complete` (retain `session-end`).
- `docs/wiki/scoped-safety-commits.md` L91/L205: additive allow-list doc update matching the code.
- `docs/wiki/coordinator-tripwires.md`: blanket-commit token list additive; update **BOTH** stale Persona-at-Sonnet greppable contact-point paths (`skills/session-end/SKILL.md` AND `skills/session-start/SKILL.md` — both become deprecation stubs; the canonical skills are now `skills/workstream-complete/` and `skills/workstream-start/`).

A non-additive (replace) edit would break the deprecation window — a `/session-end` alias commit would fail the gate. Without the additive update at all, a real `/workstream-complete` ceremony commit silently fails the branch-gate.

### D5 — `session boot` elimination = per-occurrence platform-vocab sweep
For each `session boot` occurrence, resolve by context:
- **Temporal** ("at/on/every session boot", "fires on session boot", "runs at session boot") → "session start" (the moment) or "session open" where it reads better.
- **Machinery-naming** (naming the `SessionStart` hook firing specifically) → `SessionStart` hook / the SessionStart hook block.
- **Hook-firing-temporal** (a NON-SessionStart hook that fires at session open — the hook is temporal but does NOT name the `SessionStart` platform event itself) → "session start" / "session open" temporal prose, NEVER `SessionStart`. Example: `bin/check-rag-state.sh` L12/L26 name the W1 hook (project-rag-detect) firing at session open — applying "machinery → `SessionStart`" here would inject a factually-wrong platform token (W1 ≠ the SessionStart platform event). Keep these as lowercase temporal prose.
<!-- Review: the Staff Engineer F2 — binary Temporal/Machinery classification mislabels hook-firing-temporal prose; sites check-rag-state.sh:12/:26 name the W1 hook (project-rag-detect) firing at session open — applying "machinery→SessionStart" would be factually wrong. Third branch required. -->
- **The CONTEXT.md glossary entry** for "session boot" → REMOVE; rewrite the 2026-06-01 `## Flagged ambiguities` entry to record the *workstream rename + platform-alignment* decision instead of the boot coinage; update the "ceremony grid" glossary entry to `{workstream, workday, workweek}` and to name `/workstream-start`/`/workstream-complete` (alias old names).
- Target: `grep -ri "session boot"` returns nothing in the coordinator tree + CONTEXT.md.

### D6 — Front-skill semantic ratified
`/workstream-start` ("orient at the start of a stream of work") was presented to and selected by the PM (2026-06-01 AskUserQuestion, "This session owns both" option naming `/session-start → /workstream-start`). The handoff's open-confirm is satisfied — no re-ask.

## Intentional-keep list (the convergence oracle)

After all three sweeps, `grep` for the old tokens must return ONLY these:
1. **Platform hook events** `SessionStart` (160×) and `SessionEnd` — literal Claude Code identifiers; KEEP every occurrence.
2. **Temporal "session start"** (spaced) — platform-sanctioned prose for the moment a session begins; KEEP (it is also the *replacement* for temporal `session boot`).
3. **The stored data-field key** `reviewed_at_session_end:` — schemas/handoff.yaml L101, handoff-archived.yaml L48 (D2).
4. **Deprecation-tolerance tokens** — `session-start` / `session-end` retained in `regenerate-orientation-cache.sh` case arm, `coordinator-safe-commit` regex + token list, and tripwires token list (D3/D4), for the deprecation window.
5. **The two deprecation stub skills** `skills/session-start/SKILL.md` + `skills/session-end/SKILL.md` — `name:` is the whole point (D1).
6. **Historical spec-backlink filenames** (`2026-05-08-session-end-review-and-marker-trail.md`) and **CHANGELOG history entries** describing past `/session-end`/`/session-start` behavior — historical record; KEEP. ADD new CHANGELOG entries for both renames + the coinage reversal.
7. **`session boot` → ZERO** (no keep — full elimination per D5).

## Chunks

Coupling: the two skill renames each have a serial core (mv → name → token). The three dimensions touch heavily overlapping prose files (CLAUDE.md, wikis, CONTEXT.md), so the **prose sweep is unified** (one pass handling all three token families per file) to avoid re-editing the same file three times. Functional/machinery chunks are disjoint and parallel-safe. Reconcile after all.

### C1 — Rename `/session-end` skill core (serial)
- `git mv skills/session-end/ skills/workstream-complete/`; Edit: `name: workstream-complete`; rewrite internal body refs; coordinate the `--invoker` caller with C3.
- **Test:** `grep:name: workstream-complete`; skill invokable as `/coordinator:workstream-complete`.

### C2 — Rename `/session-start` skill core (serial)
- `git mv skills/session-start/ skills/workstream-start/`; Edit: `name: workstream-start`; rewrite internal body refs; coordinate the `CLAUDE_INVOKING_COMMAND` token with C3.
- **Test:** `grep:name: workstream-start`; skill invokable as `/coordinator:workstream-start`.

### C3 — Deprecation stub skills (after C1, C2)
- Create `skills/session-end/SKILL.md` + `skills/session-start/SKILL.md` per D1 (old dirs freed by the mv).
- **Test:** both stubs present with old `name:` + `disable-model-invocation: true` + redirect line.

### C4 — Runtime + commit-gate token machinery (functional; ADDITIVE; parallel-safe after C1/C2)
<!-- Review: the Staff Engineer F1 — C4 must update ALL FOUR do_blanket touchpoints, not just L671-673. The ppid-fallback at L685 is the critical gap: if env var is unset, only the fallback authorizes the call, and it filename-matches the skill dir name — which C2 renames. Conditional (workstream-complete in do_blanket?) resolved NO: session-end never calls --blanket (confirmed grep). -->
<!-- Review: the Staff Engineer F5 — AC4 must bind the ppid-fallback path too; new test fixture needed. See AC4/AC4b update. -->
- `bin/regenerate-orientation-cache.sh`: case arm → `workstream-complete|session-end|handoff` (additive); doc comments → `workstream-complete`.
- `bin/coordinator-safe-commit` — **two mechanisms, per D4:** (a) `do_blanket` — update **all four touchpoints** (per § Substrate F1 correction): L671-673 env list (add `workstream-start`, retain `session-start`); L685 ppid-fallback (add `*"workstream-start.md"*`, retain `*"session-start.md"*`); L694 error string (add `/workstream-start`); L19 header comment (additive). `workstream-complete` does NOT join this list (verified NO). (b) subject-detection regex (~L738): add `workstream-complete`, retain `session-end`.
- `CLAUDE_INVOKING_COMMAND=session-start` callers (`scoped-safety-commits.md` L200, the renamed `workstream-start` skill) → `=workstream-start`. The skill is the canonical caller; the stub does not sweep.
- `docs/wiki/scoped-safety-commits.md` L91 + L205: additive allow-list doc update (add new token(s), retain old) — must match the code.
- Tests: `bin/tests/test-coordinator-safe-commit.sh` T9 (L292) + `tests/plugin-ecosystem/hooks-behavior.test.js` (L148) → assert BOTH old and new tokens gate-pass (run them); see AC4b for ppid-fallback test.
- `docs/wiki/coordinator-tripwires.md`: blanket-commit token list additive; update BOTH Persona-at-Sonnet contact-point paths → `skills/workstream-complete/` and `skills/workstream-start/`.
- **Test:** `bash:` ceremony dry-runs with new tokens are gate-recognized; old tokens still tolerated; bogus errors; touched tests green.

### C5 — Schema data-field (parallel-safe; schemas only)
- handoff.yaml + handoff-archived.yaml: KEEP `reviewed_at_session_end:` key + D2 comment; rename prose `/session-end` comments → `/workstream-complete`; KEEP spec-backlink filename.
- completion-entry.yaml: rename prose `/session-end` refs → `/workstream-complete`.
- **Test:** `grep:` key unchanged; existing record still schema-validates.

### C6 — Unified prose sweep (fan-out by disjoint file-group; the bulk; handles ALL THREE token families per file)
<!-- Review: the Staff Engineer F3 — partition specified by directory root so fan-out executors receive non-overlapping file sets; D5 high-judgment "session boot" resolution pulled into its own small executor to avoid smearing high-judgment work across groups. -->
<!-- Review: the Staff Engineer F0 — per-occurrence guidance expanded to cover capitalized-prose hyphenated forms that refer to the skill and must rename. -->
- Per file, apply all applicable: `/session-end`→`/workstream-complete`; `/session-start`→`/workstream-start`; `session boot`→platform vocab per D5. Also rename capitalized-prose hyphenated forms: `Session-start`→`Workstream-start`, `Session-End`→`Workstream-complete`, `Session-end`→`Workstream-complete`. KEEP platform `SessionStart`/`SessionEnd` (no hyphen), temporal "session start", spec-backlink filenames.
- **Fan-out partition (by directory root — disjoint, executor-safe):**
  - **Group A:** `docs/wiki/**`
  - **Group B:** `skills/*/SKILL.md` (EXCEPT the two stubs) + `commands/**`
  - **Group C:** `agents/**` + `pipelines/**` + `hooks/scripts/**`
  - **Group D:** `lib/**` + root (`README.md`, `canonical-structure.yaml`) + `dist/**`
  - **Group E (D5 only — separate small executor):** per-occurrence `session boot` judgment sweep across all groups — high-judgment, must NOT be smeared into the mechanical-rename groups. Pull the D5 `session boot` resolution into this dedicated executor before dispatching the mechanical groups.
- Surfaces (enumeration is a density guide, sweep ALL files under each root): all `docs/wiki/**`, all `skills/*/SKILL.md` (EXCEPT the two stubs), `commands/**`, `hooks/scripts/**`, `pipelines/**`, `agents/**`, `bin/**` prose refs (functional gates owned by C4), `lib/**`, root `README.md`, `canonical-structure.yaml`, `dist/oss-only-skills/**`.
- **Heading renames (not just inline refs):** `docs/wiki/ceremony-calibration.md` § Session-end-as-defer (and `em-pm-collaboration-extras.md` `### PM owns session-end determination` from the prior sidecar) — rename the SECTION HEADINGS, then repoint any anchor links to them.
- **Ambiguous files confirmed in-scope (pre-flight):** `bin/aggregate-chain-loe.sh` and `agents/code-reviewer-weekly.md` carry `session-end` prose refs — covered by the `bin/**`/`agents/**` clauses; verify prose-only (no functional gate) then rename.
- **Test fixture dispositions:** `bin/tests/test-coordinator-safe-commit.sh` + `hooks-behavior.test.js` (token tests → C4); other fixtures naming the commands → rename, run the touched tests.
- **Wiki renames:** `docs/wiki/session-end-review.md` and `docs/wiki/plugin-session-start-hooks.md` — decide per-file whether to `git mv` (repoint all referrers incl. DIRECTORY_GUIDE.md + CLAUDE.md inline cross-refs) or keep filename + reframe intro. `plugin-session-start-hooks.md` is literally about the `SessionStart` platform hook → likely keep filename, reframe. Triggers C9 doc-link-checker.
- **Test:** `grep:` each swept file carries no non-keep old token.

### C7 — CONTEXT.md + CLAUDE.md + CHANGELOG + published artifacts
- `CONTEXT.md`: remove "session boot" glossary entry (D5); rewrite ceremony-grid entry to `{workstream,...}` + new skill names; rewrite the Flagged-ambiguities entry to the workstream-rename decision.
- `coordinator/CLAUDE.md`: rename command refs (L38/139/141/159/182 for session-end + the session-start refs incl. L7-8 and L149 "session boot"→platform vocab). **L139 is the load-bearing `/handoff` ↔ `/session-end` mutual-exclusion doctrine** → becomes `/handoff` ↔ `/workstream-complete`; verify it still reads correctly. The Review Sequencing bullet's inline `→ session-end-review.md` cross-ref → repoint IFF C6 `git mv`'d that wiki (conditioned on C6's decision; inherited-unresolved from the superseded session-complete sidecar).
- `dist/publish-repo-toplevel/CHANGELOG.md`: KEEP history; ADD entries for both renames + the coinage reversal + deprecation window. `README.md`: rename live command refs.
- **Test:** `grep:` CONTEXT.md + CLAUDE.md carry no non-keep old token; `grep -ri "session boot"` empty; CHANGELOG gained the entries.

### C8 — Reconcile against the keep-list (after C1–C7)
- Re-run greps for all three token families; diff against the keep-list. Residual outside list → fix. Update stale improvement-queue path refs. Document final keep-set.
- **Test:** every remaining old-token occurrence maps to a keep-list item; `session boot` count = 0.

### C9 — Post-execution closeout
- **doc-link-checker** over moved skill paths + any `git mv`'d wikis — **REQUIRED (not conditional) if any wiki is `git mv`'d** (the Staff Engineer confirmed: the CLAUDE.md `→ session-end-review.md` inline cross-ref becomes a dead link if C6 `git mv`'s that wiki, so doc-link-checker is a hard requirement in that case, not a "dispatch only if" conditional). For skill-path moves only (no wiki mv), apply normal substrate precondition (dispatch only if relative inbound links not covered by `run-all-checks`).
<!-- Review: the Staff Engineer (Worker Dispatch Recommendations) — doc-link-checker is a hard C9 requirement if any wiki is moved; the CLAUDE.md inline →session-end-review.md cross-ref becomes a dead link after a git mv. -->
- **Percolation note (do NOT execute):** next `/percolate` carries both renamed skills + both stubs + CHANGELOG together.
- **Dogfood:** run `/workstream-complete` on this workstream's own landing.

## Reverse-reference scan (shared-symbol rename)

Greppped shapes per renamed token: bare (`session-end`/`session-start`), slash (`/session-end`/`/session-start`), `--invoker <tok>`, `CLAUDE_INVOKING_COMMAND=<tok>`, `name: <tok>`, the `reviewed_at_session_end` key, `session boot` (all casings), and spec-backlink filename form. **Also include capitalized-prose hyphenated forms:** `Session-start`, `Session-end`, `Session-End` (skill/ceremony references that SHOULD rename → `Workstream-start`/`Workstream-complete`). The keep-list IS the documented residual. Disambiguation guard: sweep is **case-insensitive on the HYPHENATED token**, then exclude only the no-hyphen PascalCase `SessionStart`/`SessionEnd` (160+ refs) — hyphenated tokens can never collide with the no-hyphen platform tokens at any casing.
<!-- Review: the Staff Engineer F0 — adding capitalized-prose hyphenated forms to the grep shape list so sites like docs/wiki/session-end-review.md:9 (heading "Session-End-Review") and bin/probe-cwd-project-rag-relevance.sh:2 are caught by the sweep. -->

## Cross-plan coordination

- **SUPERSEDES** `2026-06-01-session-boot-nomenclature.md` (coinage reverted by C5/C7) and `2026-06-01-session-complete-rename.md` (retargeted to `/workstream-complete`). Both old plans + their sidecars marked `status: superseded`; do NOT execute either. This plan absorbs their substrate.
- `cadb320b` (front-half "session boot" formalization) is NOT git-reverted — its disambiguation logic partly survives (three-token taxonomy → two-token after rename); the coinage is removed in-place by C5/C7.
- **Reviewer note (reversal is PM-directed, not an oversight):** the superseded front-half plan's the Staff Engineer review (Finding 2) argued FOR *formalizing* "session boot" (noting it pre-existed organically in ~6 surfaces). This plan reverses that by **explicit PM direction** (2026-06-01): the skill-rename dissolves the collision at its source, so the machinery no longer needs a local term — platform `SessionStart` + temporal "session start" suffice. The reviewer should weigh whether full elimination (vs. retaining "session boot" as informal prose) is correct, but the *direction* (no new coinage) is ratified. Note: full elimination (rather than retention as informal prose) re-surfaces the pre-cadb320b organic ambiguity that front-half Finding 2 named — D5 resolves each organic occurrence on its own merits (temporal / hook-firing-temporal / machinery-naming / CONTEXT.md), which is the correct disposition regardless of the coinage decision.
<!-- Review: the Staff Engineer F4 — close the reversal loop: full elimination re-surfaces the organic ambiguity front-half F2 named; D5 resolves per-occurrence on merits regardless of coinage direction. -->
- No other live plan references these command names in a file-overlapping way (re-scan at execution).

## Acceptance criteria

| ID | Criterion (prose) | Test (typed-prefix) | Binding-Class | Status |
|----|-------------------|---------------------|---------------|--------|
| AC1 | `skills/workstream-complete/` + `name: workstream-complete`; invokable as `/coordinator:workstream-complete`. | `grep:name: workstream-complete skills/workstream-complete/SKILL.md` | gate | pending realization |
| AC2 | `skills/workstream-start/` + `name: workstream-start`; invokable as `/coordinator:workstream-start`. | `grep:name: workstream-start skills/workstream-start/SKILL.md` | gate | pending realization |
| AC3 | Both old names resolve via deprecation stubs (D1). | `grep:` both stub SKILL.md present with old `name:` + redirect | gate | pending realization |
| AC4 | All runtime/commit-gate tokens renamed; old tolerated; bogus errors; touched tests pass. `CLAUDE_INVOKING_COMMAND=workstream-start` env path authorizes `--blanket`. | `bash:` regenerate-cache + coordinator-safe-commit dual-token gate-pass; T9 + hooks-behavior tests green | gate | pending realization |
| AC4b | `do_blanket` ppid-fallback path authorizes `--blanket` for `workstream-start.md`-parented invocations when env var is UNSET; retained `session-start.md` fallback still works; new test fixture exercises the ppid path. | `bash:` coordinator-safe-commit invoked with env var unset from a `workstream-start.md`-named parent → authorized; same for `session-start.md`; bogus parent → denied. New fixture in C4's test list. | gate | pending realization |
<!-- Review: the Staff Engineer F5 — T9 and hooks-behavior.test.js both set the env var explicitly so neither exercises the L685 ppid-fallback path; "tests green" can pass while workstream-start fallback is broken. AC4b binds the ppid path. -->
| AC5 | `reviewed_at_session_end:` key unchanged; existing records validate; split documented. | `cited:` schema-validate a real record + comment present | gate | pending realization |
| AC6 | `grep -ri "session boot"` returns NOTHING in coordinator tree + CONTEXT.md. | `grep:` empty result | gate | pending realization |
| AC7 | All non-keep `session-start`/`session-end` refs renamed; residual maps to keep-list only. | `cited:` reviewer diffs grep output vs keep-list | gate | pending realization |
| AC8 | Platform `SessionStart`/`SessionEnd` (160+) untouched; temporal "session start" preserved. | `grep:` SessionStart count unchanged pre/post | gate | pending realization |
| AC9 | Ceremony-grid doctrine reads `{workstream,workday,workweek}×{start,complete}` in CONTEXT.md + CLAUDE.md; `/handoff`↔`/workstream-complete` mutex correct. | `cited:` reviewer reads CONTEXT.md + CLAUDE.md | gate | pending realization |
| AC10 | Published artifacts coherent; CHANGELOG notes both renames + coinage reversal + deprecation window. | `cited:` reviewer reads CHANGELOG + README | gate | pending realization |
| AC11 | Percolation noted, not executed. | `cited:` C9 closeout | advisory | pending realization |

## Anti-scope

- Do NOT rename `/workday-*` or `/workweek-*` — already correct `work-*` members.
- Do NOT touch the literal platform hook keys `SessionStart` / `SessionEnd` / `PreCompact` / etc.
- Do NOT invent any new machinery term — platform vocabulary only (this is why "session boot" is being removed, not replaced with another coinage).
- Do NOT rename the `reviewed_at_session_end` stored key (D2).
- Do NOT hard-break the shipped `/session-start` / `/session-end` names — the two stubs are required.
- Do NOT rewrite historical artifacts — spec-backlink filenames + CHANGELOG history keep the old tokens.
- Do NOT `git revert cadb320b` — the coinage is removed in-place (D5); a revert would also undo still-useful disambiguation and conflict with sibling commits.
- Do NOT pre-execute the `setup/publish.sh` percolation — note it only.

## Dispatch Ledger

Gate graph: Wave 1 = disjoint structural/functional cores (parallel). Wave 2 = stubs (need freed dirs). Wave 3 = prose sweep groups (after skill dirs settle; each disjoint by directory root, excluding C4/C7-owned files). Wave 4 = EM reconcile. Wave 5 = closeout. Every prose executor carries the verbatim disambiguation recipe + 7-item keep-list. 145 unique files total.

| # | chunk | one-line brief | write-files | runs | est-min | status |
|---|-------|----------------|-------------|------|---------|--------|
| 1 | C1 | rename session-end skill core (git mv + name + body) | skills/workstream-complete/** (mv from skills/session-end/) | parallel (W1) | 8 | committed |
| 2 | C2 | rename session-start skill core (git mv + name + body) | skills/workstream-start/** (mv from skills/session-start/) | parallel (W1) | 8 | committed |
| 3 | C4 | commit-gate machinery (additive, 4 do_blanket touchpoints) | bin/coordinator-safe-commit, bin/regenerate-orientation-cache.sh, docs/wiki/coordinator-tripwires.md, docs/wiki/scoped-safety-commits.md, bin/tests/test-coordinator-safe-commit.sh, tests/plugin-ecosystem/hooks-behavior.test.js | parallel (W1) | 12 | committed |
| 4 | C5 | schema data-field (keep key, rename prose) | schemas/handoff.yaml, schemas/handoff-archived.yaml, schemas/completion-entry.yaml | parallel (W1) | 6 | committed |
| 5 | C7 | CONTEXT/CLAUDE/dist | CONTEXT.md, plugins/.../coordinator/CLAUDE.md, dist/publish-repo-toplevel/**, dist/oss-only-skills/** | parallel (W1) | 12 | committed |
| 6 | C3 | two deprecation stub skills | skills/session-end/SKILL.md, skills/session-start/SKILL.md (new) | after #1,#2 (W2) | 5 | committed |
| 7 | C6-wA | prose sweep — docs/wiki group A | docs/wiki/** (group A, ~16 files; excl tripwires+scoped-safety-commits) | after W1+W2 (W3) | 13 | dispatched |
| 8 | C6-wB | prose sweep — docs/wiki group B | docs/wiki/** (group B, ~16) | after W1+W2 (W3) | 13 | dispatched |
| 9 | C6-wC | prose sweep — docs/wiki group C | docs/wiki/** (group C, ~14) | after W1+W2 (W3) | 12 | dispatched |
| 10 | C6-sk | prose sweep — skills | skills/*/SKILL.md (~17, excl renamed cores + stubs) | after W1+W2 (W3) | 12 | dispatched |
| 11 | C6-cmd | prose sweep — commands | commands/** (7) | after W1+W2 (W3) | 8 | dispatched |
| 12 | C6-aph | prose sweep — agents+pipelines+hooks | agents/**, pipelines/**, hooks/scripts/** (~18) | after W1+W2 (W3) | 12 | dispatched |
| 13 | C6-bin | prose sweep — bin+lib+root | bin/** prose (excl C4 funcs), lib/**, root README.md (~18) | after W1+W2 (W3) | 12 | dispatched |
| 14 | C8 | reconcile against keep-list (grep all 3 token families) | (verification + targeted fixes) | inline (EM), after W3 | — | committed |
| 15 | C9 | closeout — doc-link-checker + dogfood | (worker dispatch + dogfood) | after #14 (W5) | — | committed (doc-link-checker skipped per precondition; percolation noted) |

Invariant check: 15 distinct dispatch rows = 13 executor chunks + 1 EM-inline + 1 closeout. No row spans >1 chunk. ✓

## Deviations

| deviation | reason | commit |
|-----------|--------|--------|
| Wiki filenames KEPT (not `git mv`'d) — `session-end-review.md`, `plugin-session-start-hooks.md` retain old names; content/intros swept | EM execution call: link-stability across referrers > nominal consistency; matches front-half's own call on plugin-session-start-hooks.md | 470eef78 |
| 4 files missed by initial file-enumeration (case-SENSITIVE grep skipped capitalized-only `Session-start`/`Session-end`) | caught at C8 reconcile via case-insensitive grep; fixed (probe-cwd, canonical-structure.yaml, install.sh, AGENTS.md) | 4a7ca62c |
| Cross-references between the two simultaneously-renamed skills fell between per-skill chunks | C6-skills excluded the renamed cores; reconciled as an explicit C8 pass | aab8924b, 4a7ca62c |
| C6 prose sweep edited 99 files vs ~87 estimate | several files carried more cross-family occurrences than the per-group enumeration suggested; no scope change, all in-tree | 470eef78 |
