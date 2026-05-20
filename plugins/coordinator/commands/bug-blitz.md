---
name: bug-blitz
description: Autonomously grind tasks/bug-backlog.md — verify each item still applies, fix small items in parallel waves, surface big ones to PM for spinoff authorization.
allowed-tools: ["Agent", "Read", "Write", "Edit", "Bash", "Grep", "Glob", "Skill", "TaskCreate", "TaskUpdate", "TaskGet", "TaskList"]
argument-hint: "[--dry-run | --max=N]"
---

# Bug Blitz — Aggressively Tackle the Bug Backlog

Verify-then-grind through `tasks/bug-backlog.md`. Re-check each item against current code (some have been fixed silently), triage by size, fix the small items autonomously in file-disjoint waves, surface big-item spinoff candidates for PM authorization (per `skills/spinoff/SKILL.md` Step 0 — spinoffs are never EM-initiated). Triage is folded into this skill — there is no separate triage step.

**Operates exclusively on `tasks/bug-backlog.md`.** Built from `/bug-sweep` (finds new bugs) + `/mise-en-place` (autonomous waves) but distinct: backlog entries are NOT pre-spec'd executor stubs, so triage is the spec-creation step.

**Announce at start:** "Running `/bug-blitz` — verifying backlog, then aggressive autonomous parallel waves through every fixable item. The default is dispatch-and-spot-check; defer requires named evidence. Big items surface as a spinoff candidate list for your authorization before any handoff is written."

## Default Stance — Dispatch, Don't Defer

The skill's job is to *grind the backlog down*, not to produce a triage report. Empirically (smoke 2026-05-14) the skill defers 90%+ of items on lazy grounds — "lacks standalone entry," "judgment-call refactor," "intersects active plan" — and ships a run that fixes 2 of 47 items. That is failure, not caution. **Fix the lazy defer, not the run.**

**Hard rules — defer ONLY for these reasons, all of which require evidence in the verdict row:**

1. **`already-fixed`** — commit SHA cited; the pattern is provably gone from HEAD.
2. **`file-removed`** — the cited file no longer exists.
3. **`big` (auto-spinoff)** — multi-file refactor, schema/contract change, or new test fixtures required. The footprint must be ≥3 files OR introduce a new module/interface. "I'd need to think about it" is not `big`.
4. **`plan-substrate-collision`** — the fix would edit code an open plan in `docs/plans/` is *actively rewriting* (not merely touching nearby). Cite the plan path + the specific file(s) it claims. If the plan touches `foo.py` but the bug is in `bar.py`, that is not a collision.

**The following are NOT valid defer reasons** (treat as dispatch signal, not skip signal):

- "Summary-form" / "lacks standalone entry" / "not yet expanded into a row." If the backlog text carries file:line + a one-line description, the EM (or a Haiku) expands it into a dispatch brief inline during Phase 1. Summary entries are spec-creation work, not skip work.
- "P2 judgment-call" / "refactor flavor" / "caching strategy" / "god-function decomposition." P2 ≠ skip. If the fix is mechanical (rename, extract, parameterize, replace string) and footprint-bounded, dispatch it. The EM spot-checks the diff at the wave gate — that is the judgment call, applied to concrete code rather than to a backlog row.
- "Intersects active plan" without a named file collision. Mechanical fixes adjacent to in-flight plans are fine; they go through the same wave-gate review as everything else and conflict-out at git-level if they actually collide.
- "Would take careful thought." Careful thought is what the executor + verifier + EM spot-check chain is *for*. Push the judgment into the dispatch, not in front of it.

**Recovery framing.** The 2026-05-14 run resolved 2 items and deferred ~45 P2s in "summary form." On a re-run of that shape: expect to expand the summary-form entries inline during Phase 1, dispatch them in file-disjoint waves, and converge on a fix-rate of 50%+ of the verified-open backlog per run, not 5%.

## Severity-Tier Dispatch Rules (PM doctrine, 2026-05-18)

`/bug-blitz` is intended to be **extremely aggressive**. The failure mode is "great, I took care of 8 bugs out of 1215" — the EM does Phase 1 triage on everything, finds reasons to defer most of it, ships a thin run. Don't. Severity-tier dispatch is the structural fix:

| Severity | Triage shape | Dispatch shape | Rationale |
|----------|--------------|----------------|-----------|
| **P2** | **No triage step** — skip Phase 1 verify for P2s; trust the backlog citation. | Direct executor dispatch in file-disjoint waves, max parallelism. | P2 false-positive rate is low and the fix cost is low — re-verifying is more expensive than just fixing. If a P2 is a phantom, the executor returns "no change needed" cheaply. |
| **P1** | **Bulk-triage** — one Haiku per chunk of ~20 items, verify-only (still-open / already-fixed / file-removed). EM reads triage output, then dispatches aggressively. | Aggressive file-disjoint waves across the still-open set. | P1 hit rate is ~60%; bulk triage filters cheap before expensive dispatch. |
| **P0** | **Smaller-set triage** — one Haiku per chunk of ~5 items, verify AND read the cited code line-by-line. EM spot-checks each verdict. | Aggressive dispatch on confirmed-open set; flag any verdict the EM disagrees with for re-read. | P0 false-positive rate from sweep agents is 100% historically (`bug-sweep` cites this). Need the careful verifier, not the size-classify shortcut. |

**Phase 1 (Verify + Triage) is now severity-conditional, not uniform.** Split the backlog by severity at Phase 0.5 (between Preflight and Phase 1):

- P2s skip Phase 1 entirely — go straight to Phase 3 with footprint declared from the backlog citation.
- P1s get the chunks-of-20 verify-only Haiku from current Phase 1.
- P0s get the chunks-of-5 careful Haiku from current Phase 1 with additional cited-code-read step.

If the backlog lacks severity tags, the EM tags them inline at Phase 0.5 (P2 default unless `crash`, `data-loss`, `security`, or `silent-corruption` shape — those are P0; `wrong-behavior` / `breaking-flow` are P1).

## Spinoff Phantom Verification (PM doctrine, 2026-05-18)

**Spinoffs are last resort, not the size-overflow drawer.** Today's failure mode: PM was offered 7 candidate spinoffs; 4 were phantoms (file/symbol gone from HEAD), 1 was a 2-line fix mis-classified as `big`. Pre-surface verification is mandatory:

For each `big` candidate, BEFORE adding it to the spinoff candidate list shown at Phase 2.1:

1. **Phantom check.** Re-read the cited file:line on HEAD. If the symbol named in the recommended-fix is absent AND the bug pattern is absent, the spinoff is a phantom — close as `already-fixed` (or `file-removed`) with a one-line note, do not surface.
2. **Size sanity-check.** Re-measure the footprint. Open the cited file and the recommended-fix's named imports / call sites. If the fix is genuinely 1-2 file edits totaling <50 lines net change, reclassify as `small` and route to the next wave — `big` is footprint ≥3 files OR new module/interface, not just "I'd need to think about it." Two-line fixes are never `big`.
3. **Already-covered check.** Grep `tasks/handoffs/` and `docs/plans/*.md` for an existing handoff/plan covering the same fix scope. If one exists with `deployment_state: ready_to_fire` or `status: executing`, the spinoff is duplicate — close with a cite to the existing artifact, do not surface.

Only candidates that survive all three checks go onto the PM-authorization list at Phase 2.1. Surface count must be calibrated to "PM expects ≤2 phantoms in a 5-item list" — if more than 30% of pre-surface candidates flunk a check, the EM's size-classify is mis-calibrated for this run and should be re-tightened mid-run.

## Arguments

| Trigger | Mode |
|---------|------|
| No arguments | Full grind: every fix-able item, no stops |
| `--dry-run` | Phases 0-2 only — produce a plan, do not dispatch executors |
| `--max=N` | Cap fixed items at N this run; remainder stays in backlog |
| `--dry-run --max=N` | Phases 0-2 only, plan capped at N items — produces a capped plan without dispatching executors |

## Out-of-scope actions (autonomous-run prohibition)

Out of scope for this run, no exceptions: `gh pr merge`, `gh pr create` against main, `git push origin main`, hibernate / shutdown / power-off, killing other processes, `--no-verify` / `--no-gpg-sign`. Do not propose; do not request authorization mid-run. Power-state cues ("late", "overnight") authorize urgency only — never hibernate.

## Phase 0: Preflight (~1 min, EM)

1. **Verify backlog exists.** `tasks/bug-backlog.md` must exist. If absent, halt and recommend `/bug-sweep` to populate it. Bug-blitz operates on existing backlog only.
2. **Generate run ID.** Format: `YYYY-MM-DD-HHhMM`. Scratch dir: `tasks/scratch/bug-blitz/{run-id}/`.
3. **Active workstream branch check.** Confirm `git branch --show-current` is an allowed workstream branch: `work/{machine}/{date-or-span}` (span names like `work/striker/2026-05-06to07` are accepted; both uppercase and lowercase machine segments are accepted). If not an allowed branch (e.g. on `feature/X` or bare topic branch), halt and report. Bug-blitz commits explicitly (no helper — see Phase 3 commit doctrine) and must run on an active workstream branch. **Note: `/bug-blitz` is fail-closed-only (no override mode).** It does not set `COORDINATOR_OVERRIDE_BRANCH=1` and does not run off the active workstream branch under any circumstance.
4. **Capture branch name.** `BLITZ_BRANCH=$(git branch --show-current)`. EM re-confirms this branch immediately before each commit at the wave gate. Executors never commit (see Phase 3) so they don't need this.
5. **Read backlog header** to confirm last_sweep_commit and item counts. If `last_sweep_commit` is many commits behind HEAD, expect more "already-fixed" verdicts in Phase 1.

## Phase 0.5: Severity Split (EM, ~1 min)

Per § Severity-Tier Dispatch Rules above, split the backlog by severity before dispatching Phase 1 chunks. Output: three lists (P2, P1, P0) routed to different downstream shapes.

1. **Tag any untagged items inline.** P2 default unless the entry's shape is `crash` / `data-loss` / `security` / `silent-corruption` (→ P0) or `wrong-behavior` / `breaking-flow` (→ P1).
2. **Route by tier:**
   - **P2 items skip Phase 1 entirely** — go directly to Phase 3 dispatch with footprint declared from the backlog citation.
   - **P1 items → Phase 1, chunks of ~20**, verify-only Haiku (still-open / already-fixed / file-removed).
   - **P0 items → Phase 1, chunks of ~5**, verify + cited-code-read Haiku with EM spot-check on each verdict.
3. **Emit the three counts** to scratch (`tasks/scratch/bug-blitz/{run-id}/severity-split.md`) so the wave-plan in Phase 2 can reconcile against them.

## Phase 1: Verify + Triage (parallel Haiku per chunk, severity-conditional)

The backlog has likely drifted. Some items have been silently fixed by other workstreams. Some have changed shape. Some are no longer reachable. Verify before grinding — but only for P1/P0 per Phase 0.5; P2s skip this phase and go straight to Phase 3.

**Chunk size is severity-conditional** (see Phase 0.5): P1s go to chunks of ~20 (verify-only); P0s go to chunks of ~5 (verify + cited-code-read + EM spot-check). For each chunk, dispatch one Haiku agent with `run_in_background: true` and an on-disk deliverable. See disk-first verification preamble below — inline it in every chunk-Haiku dispatch prompt.

**Disk-first verification preamble (inline verbatim into every Phase 1 chunk-Haiku dispatch prompt):**
> Reply with `DONE: <path>` ONLY after you have confirmed the file exists at the path above (use Read or Bash `ls` to verify). If you find yourself about to summarize the deliverable inline in your reply, STOP — the coordinator reads from disk, not chat. Inline summary without a written file counts as task failure.

**Pattern-presence verifier (dispatch alongside each chunk-verify Haiku).** In addition to the standard chunk verifier, dispatch a second Haiku per chunk with `run_in_background: true` to confirm that each `still-open` item's cited pattern is present at the exact file:line described. For each item:
1. Read the cited file at the cited line.
2. Confirm the named variable/symbol from the recommended-fix field is present.
3. If the pattern has shifted ≥3 lines OR the named symbol is no longer present → flag `pattern-shifted`.
Verdict per item: `confirmed` | `pattern-shifted`. Write to `tasks/scratch/bug-blitz/{run-id}/chunk-N-pattern-check.md`. Reply `DONE: <path>`.

After both chunk verifiers return, EM reviews `pattern-shifted` items inline before adding them to executor dispatch. Items flagged `pattern-shifted` are NOT dispatched to executors automatically — EM reads the cited file and decides: re-classify, update the backlog entry, or proceed with adjusted recommended-fix.

**Pattern-shifted is a dispatch signal, not a defer reason.** Empirically (2026-05-18, project-rag-ue-addon: 0 of ~6 pattern-shifted deferrals were real moved-bugs — all were the same bug with the named symbol renamed or the surrounding code reshuffled by an unrelated edit). When the cited symbol is missing at the cited line, the high-prior interpretation is "the bug still exists, the pattern moved" — grep the recommended-fix's central noun-phrase (the buggy condition, not the symbol name) across the cited file and adjacent siblings before classifying as deferral-eligible. Closing as `file-removed` requires `ls` confirming absence; closing as `already-fixed` requires a commit SHA showing the fix. "Pattern shifted, can't find it" with neither evidence is a re-grep task, not a defer.

**Backlog entries written in summary-form paragraphs are actionable items, not noise.** Dense deferred-summary sections with file:line citations are verification candidates — do not skip them at Phase 1 triage.

**Pre-classification eligibility — verify status freshness, not just FIXED tagging.** An entry tagged FIXED months ago may have a fresh IN-PROGRESS continuation underneath; check `git log -- <cited-path>` since the FIXED tag's date before pruning. "Already-fixed ghost" prunes can collateral-damage in-progress work.

**Per-item verification + size classification.** Each agent, for each item:

1. **Verify still-applies:**
   - Read the cited file:line — does the bug pattern still exist in HEAD?
   - `git log --oneline -5 <file>` — did a recent commit address it?
   - Verdict: `still-open` | `already-fixed` | `pattern-changed` | `file-removed`
2. **Size classify (only if `still-open` or `pattern-changed`):**
   - `small` — footprint ≤2 files, no new test fixtures, fix shape derivable from cited code + recommended-fix line. **Default classification.** P2 / "refactor flavor" / "judgment-call" items with a bounded mechanical fix shape are `small`, not `big`. AI-fixable in <10 minutes.
   - `big` — footprint ≥3 files OR introduces a new module/interface OR requires schema/contract change OR requires new test fixtures. Triggers auto-spinoff (Phase 2).
   - `needs-investigation` — **NOT a terminal verdict.** A Haiku flagging this must include the file:line range it actually inspected and the specific ambiguity. The EM resolves it at the Phase 2 gate by reading the cited code; it then converts to `small`, `big`, or `already-fixed`. It never stays in the backlog unresolved across this skill.
3. **Footprint declaration (small only):** the file(s) the fix would touch.
4. **Summary-form expansion.** If the backlog entry is a multi-item summary row (e.g. one row covering N file:line citations under a shared theme), the Haiku expands it into one verdict row per cited file:line in the output table. Summary rows do not pass through — they fan out. **Carrying a summary row forward as a single "needs decomposition" defer is a Phase 1 failure.**

**Output schema (per chunk):**

```markdown
| ID | Verdict | Size | Footprint | Notes |
|----|---------|------|-----------|-------|
| BS-2026-05-06-007 | still-open | small | bin/find-polluter.sh | Add `command -v npm` pre-flight + `set -o pipefail` |
| BS-2026-05-06-001 | still-open | big | bin/coordinator-safe-commit, tests/... | Frontmatter parser refactor + new CRLF tests |
| BS-2026-05-06-018 | already-fixed | — | — | Fixed in commit abc1234 |
```

**Scratch path:** `tasks/scratch/bug-blitz/{run-id}/chunk-N-verify.md`. Each agent must end with `DONE: <path>` after writing.

## Phase 2: Plan Waves + Auto-Spinoffs (EM, ~3 min)

Read all chunk verifications from disk. Build the execution plan.

### Step 2.0: Resolve `needs-investigation` rows

Every `needs-investigation` row from Phase 1 gets read by the EM (cited file:line + surrounding context) and converted to `small`, `big`, or `already-fixed` here. **The skill does not exit with `needs-investigation` rows still pending** — that is the "lazy defer" failure mode the Default Stance prohibits. If a row genuinely cannot be classified after the EM reads the code (rare), reclassify as `big` and let the spinoff handoff carry it.

### Step 2.1: Spinoff big items (PM-authorized)

**Spinoffs require explicit PM authorization per `skills/spinoff/SKILL.md` Step 0.** PM-invocation of `/bug-blitz` does NOT pre-authorize the resulting spinoff set — each `big` item is its own authorization.

Surface the candidate spinoff list to the PM as a single message:

```
Candidate spinoffs from this bug-blitz run ({N} items):
1. <slug-1> — <one-line topic> (backlog item #<ID>, footprint: <files>)
2. <slug-2> — <one-line topic> (backlog item #<ID>, footprint: <files>)
...
Authorize all / authorize subset / none?
```

Block on PM response. Only authored spinoffs proceed; unauthorized candidates revert to `needs-investigation` in the backlog with a one-line note ("PM declined spinoff at bug-blitz <run-id>"). Do not retry without fresh PM direction.

For each PM-authorized `big` item, write a spinoff handoff using the canonical schema below (or invoke `/spinoff <slug>` per-item).

**Canonical spinoff frontmatter** (all fields required — do not paraphrase keys):

```yaml
---
title: <one-line title describing the bug and fix scope>
created: <YYYY-MM-DD>
branch: <current branch — git symbolic-ref>
status: active
kind: spinoff
predecessor: none
authoring_session: bug-blitz <run-id>
workstream: bug-backlog item <ID>
deployment_state: ready_to_fire
scope:
  - <pathspec 1>
  - <pathspec 2>
---
```

**`status` MUST be `active`, not `pickup-ready`** — `active` is the canonical value per `commands/spinoff.md`. `predecessor: none` always. `status: pickup-ready` is not a valid value. **`deployment_state: ready_to_fire`** is hard-coded for bug-blitz spinoffs: each is a scoped, actionable fix with no PM-gate by definition (already triaged through the bug-backlog as `big` — actionable but oversized for in-wave fix). Never use `awaiting_gate` here.

**Canonical body sections:**
- `# <title>` (H1 mirrors frontmatter title)
- Opening paragraph: one sentence on why this is its own session
- `## What this covers`
- `## Reference materials (read first)`
- `## Specification` — include the original backlog entry verbatim (file:line, description, recommended fix) plus a brief rationale: "classified `big` because: <reason>"
- `## Acceptance criteria`
- `## Recommended next steps`
- `## Anti-scope`

**Trailing marker (required for greppability):**
```html
<!-- spinoff: <YYYY-MM-DD> by bug-blitz <run-id> -->
```

Path: `tasks/handoffs/{YYYY-MM-DD}_{HHMMSS}_bug-blitz-spinoff-{slug}.md`

Update the backlog entry: `resolution: spun-off-{YYYY-MM-DD} {handoff-path}`. The item leaves the active backlog.

### Step 2.2: Drop already-fixed items

Delete already-fixed items from active P1/P2 tables; name them in the Phase 4 commit subject and final report.

### Step 2.3: Build small-item waves (file-disjoint)

**Phase 2 — pre-bundle by file footprint.** Group bug IDs by shared file footprint and dispatch one executor per file (not per bug ID). For Phase 3 verification, prefer batched per-wave verifiers when the EM is reading each DONE line; per-DONE Haiku is overkill at that read-density. Empirical: 28 executors / 42 items / 3 waves / 0 regressions (2026-05-14 blitz).

Group `small` items by file footprint:

- **Wave 1:** All small items with disjoint footprints. Dispatch concurrently.
- **Wave 2..N:** Subsequent waves where each wave's items have disjoint footprints among themselves AND don't conflict with files modified by prior waves' commits.

If `--max=N` set, cap total fixed items across waves at N. **Ordering: sort by severity (P1 before P2), then by ID ascending within severity.** The N highest-priority items proceed; the rest stay in backlog.

### Step 2.4: Build flight recorder (TaskCreate)

One goal task ("bug-blitz {run-id}: verify N → fix M small / spinoff K big"). Per-wave tasks with item IDs and file footprints. Anti-amnesia field on each: `tried_and_abandoned`.

### Step 2.5: Announce + fire

Output one block, then proceed to Phase 3 immediately. Do not wait for response.

```
## Bug Blitz — Plan

Backlog at start: N items
Verified open: V (already-fixed: A, file-removed: R)
Auto-spun-off (big): S → tasks/handoffs/...
Queued for fix: F across W waves

Wave 1 (parallel, file-disjoint): [item IDs]
Wave 2 (parallel, file-disjoint): [item IDs]
...

Tail: backlog updated with commit SHAs + spinoff paths. No /update-docs invoked.
```

If `--dry-run`, stop here.

## Phase 3: Execute Waves (Sonnet executors edit; EM serializes commits)

**Commit doctrine — single committer, explicit-path, fused add+commit.** Parallel executors that each call a commit helper produce two failure modes empirically observed in the 2026-05-06-22h42 smoke run: (a) **concurrent-commit absorption** — N near-simultaneous `git commit` calls bundle each other's staged work into the first commit, leaving N-1 commit messages orphaned; (b) **scope sweep** — `coordinator-safe-commit` consulted touched-files in long-lived sessions and absorbed unrelated dirty work from other workstreams into the bug-blitz commits. Both defects are eliminated by: executors edit-and-report only (no commit), EM serializes commits at the wave gate using `git reset && git add -- <paths from DONE> && git commit` fused into a single Bash call. No helper invocation; explicit paths only; one committer at a time.

For each wave:

1. **Dispatch all items concurrently.** One Sonnet executor per item, `run_in_background: true`, `mode: "acceptEdits"`. Each prompt must include:
   - **Disk-first verification preamble (verbatim):**
     > Reply with `DONE: <path>` ONLY after you have confirmed the file exists at the path above (use Read or Bash `ls` to verify). If you find yourself about to summarize the deliverable inline in your reply, STOP — the coordinator reads from disk, not chat. Inline summary without a written file counts as task failure.
   - The full backlog entry (severity, file:line, description, recommended fix)
   - **P0/P1 verification gate (verbatim):** *"Before writing any fix: read the cited file:line and confirm the bug pattern is present in the current code. If the pattern is absent or has materially changed, STOP and report `BLOCKED: pattern-not-as-described` with what you actually found. Do not 'fix anyway' based on the description."*
   - **Footprint constraint:** *"You MUST NOT modify any file outside this footprint: [list]. If you discover you need to, STOP and report `BLOCKED: footprint-overflow`."*
   - **Edit-and-report constraint (executors do NOT commit):**
     > After your edit: (1) re-read the cited code and confirm the bug pattern is gone; (2) run any local tests under the same directory as the modified file — if tests fail, revert your edit (`git checkout -- <paths>` is fine here because executors leave the working tree unstaged and the EM has no concurrent unstaged work for this item) and report `BLOCKED: regression`. **Do NOT stage and do NOT commit. Leave changes unstaged in the working tree** — the EM stages and commits each item serially at the wave gate. Helper invocation (`coordinator-safe-commit`) is forbidden in executor scope: empirically (smoke 2026-05-06-22h42) it produced concurrent-commit absorption and scope sweep.
   - **DONE summary:** Write to `tasks/scratch/bug-blitz/{run-id}/{item-id}.done.md` with: `status` (`DONE` | `BLOCKED: <reason>`), `files: [explicit paths]` (newline-separated, exactly the paths the EM should `git add --` — no globs, no parent dirs), `before` snippet, `after` snippet, `verified` result. Do NOT include a commit SHA — committing is the EM's job. Reply `DONE: <path>` only.

   <!-- Review: 2026-05-06-22h42 smoke run — defect 1 (concurrent-commit absorption) + defect 2 (scope sweep) traced to executor self-commit via coordinator-safe-commit. Reverted the Staff Engineer F8 in favor of EM-serial commit at wave gate; per-item commit cadence preserved (still one commit per backlog item) but funneled through a single committer. -->
   <!-- Review: the Staff Engineer F10 — disk-first verification preamble inlined into executor dispatch prompt. -->

2. **Process completions on arrival.** Read each DONE summary (only). Do NOT pull executor transcripts.

3. **Dispatch Haiku verifier per DONE.** `run_in_background: true`, on-disk verdict. Verifier reads the DONE summary + the unstaged diff for the item's `files` (`git diff -- <paths>`) + cited code; confirms bug pattern is gone, no out-of-footprint changes, tests pass. Verdict: `PASS` | `PATTERN-STILL-PRESENT` | `FOOTPRINT-VIOLATION` | `REGRESSION`. Path: `tasks/scratch/bug-blitz/{run-id}/{item-id}.verify.md`.

4. **Wave gate — EM serial commit + incremental backlog update.** When all wave verifiers return:
   - **Poll `git branch --show-current` BEFORE any wave-gate action.** If it does not equal `$BLITZ_BRANCH`, halt and reconcile before proceeding.
   - **For each PASS item, in deterministic order (sorted by item ID), the EM serially commits the item.** Single Bash call per item to fuse stage+commit and avoid sibling-session windows:
     ```bash
     git reset && \
       git add -- <paths from DONE.files> && \
       git -c gpg.program=... commit -m "<item-id>: <one-line description>"
     ```
     The leading `git reset` clears any sibling-session staging so only this item's paths land. Use plain `git commit` (not `coordinator-safe-commit`) — the helper's touched-files heuristic is what produced the smoke-run scope sweep. The auto-push hook fires on commit; capture the resulting SHA from `git rev-parse HEAD` and write it back to the DONE summary as `commit: <sha>`. Re-confirm `git branch --show-current == $BLITZ_BRANCH` before each commit; halt the wave if it flipped mid-loop.
   - For PASS items: PASS commits at the wave gate ARE the persistence (commit subject names each item). No per-wave backlog append — PASS items are deleted from the active P1/P2 tables in Phase 4 only.
   - For BLOCKED / non-PASS items: the working tree still carries the executor's edit (unstaged, since executors don't commit). Revert via `git checkout -- <paths from DONE.files>` (safe under this skill because the EM controls staging and no other agent has unstaged work on these specific paths within the wave). Update the backlog entry with `resolution: re-attempted-{date}: <reason>`, leave in backlog.
   - Update flight-recorder tasks to `completed`.

   <!-- Review: the Staff Engineer F4 — poll git branch --show-current BEFORE each commit at the wave gate. Branch is captured at Phase 0 as $BLITZ_BRANCH; EM re-checks before every commit (per-item granularity, not per-wave, because the loop spans many seconds). -->
   <!-- Review: the Staff Engineer F5 (revised 2026-05-07) — per-wave incremental backlog writes removed; PASS commits at the wave gate ARE the persistence (commit subject names each item), so a mid-run crash recovers attribution from `git log` rather than file state. Doctrine: docs/plans/2026-05-07-prune-resolved-state-bloat.md. -->

5. **Brief status, no question.** "Wave N complete (X fixed, Y blocked). Firing wave N+1."

**Single-item waves execute the same way** — overhead of background dispatch is small and consistent shape simplifies recovery. The EM-serial commit pattern is unchanged for single-item waves (one commit by EM).

## Phase 4: Update Backlog + Report

After all waves complete:

1. **Final backlog update — prune-with-paper-trail.** The fixes themselves are the paper trail (each PASS item committed individually in Phase 3 with the item ID in the commit subject); Phase 4 removes the now-redundant backlog rows so the backlog doesn't bloat. Phase 4:
   - Updates the header: `last_run: bug-blitz-{run-id}`, `last_run_commit: <new-HEAD>`, current open counts.
   - **Deletes — does NOT archive in-place — every closed row** from the active P1/P2 tables. Three closure shapes, all delete:
     - `PASS` (fixed this run) — paper trail is the Phase 3 commit naming the item ID
     - `already-fixed` (silent prior fix) — paper trail is the cited prior commit SHA in the final report
     - `spun-off` (auto-spinoff to handoff) — paper trail is the handoff path
   - **No "Resolved this run" section inside the backlog.** The backlog is the queue of OPEN work. Closed items live in `git log` + the final report — adding them back to the backlog as a "resolved" section defeats the prune.
   - Adds `## Spun off (this run)` section with each spinoff: ID, handoff path. (Spinoffs are pointers to live work elsewhere, not closure records.)
   **Note: last-write-wins hazard.** If two bug-blitz runs overlap, the second run's Phase 4 rewrite will overwrite the first. Do NOT run concurrent bug-blitzes.
2. **Commit the backlog prune** as the final wave (EM-serial, single Bash call):
   ```bash
   git reset && git add -- tasks/bug-backlog.md && \
     git commit -m "bug-blitz {run-id}: prune resolved — fixed: <ID1, ID2, ...>; already-fixed: <ID3, ...>; spun-off: <ID4, ...>"
   ```
   **The commit subject MUST name every closed ID** (across all three closure shapes). This is the greppable paper trail — `git log --all -- tasks/bug-backlog.md | grep BS-NNNN` resolves "whatever happened to that bug?" without reading the backlog history. Verify `git branch --show-current == $BLITZ_BRANCH` immediately before. Plain `git commit`, not `coordinator-safe-commit`, per Phase 3 commit doctrine.
3. **If no items closed this run** (all verifications came back blocked / pattern-shifted / nothing fixable), do NOT commit an empty backlog update. Skip to the final report and announce the no-op — that itself is a useful signal that the backlog has reached a state where bug-blitz alone can't make progress and the next step is `/bug-sweep` or `/plan`.
4. **Clean scratch.** Run cleanup only after backlog commit succeeds:
   ```bash
   rm -rf tasks/scratch/bug-blitz/{run-id}/ 2>/dev/null || { echo "Warning: scratch cleanup failed — tasks/scratch/bug-blitz/{run-id}/ may need manual removal. Not failing the run." ; }
   ```
5. **Final report to PM:**

```markdown
## Bug Blitz Complete

**Run:** {run-id} | **Backlog at start:** N | **Backlog at end:** M

**Resolved this run:** F items
- [list with item ID + commit SHA]

**Spun off (need plan):** S items
- [list with item ID + handoff path]

**Already-fixed (silent):** A items
- [list with item ID + commit SHA where attributable, otherwise "untracked"]

**Re-attempted (still blocked):** R items
- [list with item ID + reason]

**Test status:** [pass/fail counts from final test run]
```

## Post-Ship Cleanup

After canonical outputs are committed, delete the working-notes scratch directory (`tasks/scratch/bug-blitz/<date>-<time>/`). Optionally write a one-line breadcrumb at `tasks/scratch/bug-blitz/<date>-receipt.txt` referencing the canonical commit SHA. Working notes leaking post-ship as untracked files is noise; commit-then-delete is a two-step waste.

## Failure Modes

| Situation | Action |
|-----------|--------|
| `tasks/bug-backlog.md` missing | Halt Phase 0; recommend `/bug-sweep` first |
| Off active workstream branch (not `work/{machine}/{date-or-span}`) | Halt Phase 0 |
| Phase 1 chunk Haiku returns text-only (no file written) | Re-dispatch with `snippets/text-only-recovery-preamble.md` inlined; on second failure, EM persists agent's inline output |
| Executor reports `BLOCKED: pattern-not-as-described` | Update backlog with revised description; do NOT fix anyway |
| Executor reports `BLOCKED: footprint-overflow` | Revert; reclassify item as `big`, auto-spinoff |
| Verifier returns `REGRESSION` | Revert that item's writes; mark backlog row with regression note + commit SHA |
| Concurrent session flips branch mid-run | Halt at next wave gate; report state to PM via final report |
| Context compacts mid-run | TaskList/TaskGet for state; resume from `in_progress` wave; flight recorder is canon |

## When to Stop Early

- Active workstream branch flip + concurrent-session conflict that can't be resolved without PM input
- 3+ consecutive verifier `PATTERN-STILL-PRESENT` verdicts (suggests Phase 1 verification was unreliable; halt and re-verify)
- Executor reports across multiple items reveal a systemic backlog-quality issue (e.g., file:line citations are stale across many items — backlog itself needs refresh)
- File-disjointness analysis was wrong and waves are stepping on each other

In all cases: commit completed waves, update backlog with current state, write a brief status to the final report. Do NOT rollback completed waves.

## Relationship to Other Commands

- **`/bug-sweep`** — populates `tasks/bug-backlog.md`. Run periodically; bug-blitz consumes its output.
- **`/mise-en-place`** — for pre-spec'd executor stubs (reviewed-and-sealed plan items). Bug-blitz handles the un-spec'd backlog case where triage is the spec-creation step.
- **`/spinoff`** — convention used by Phase 2.1 to fork big items into pickup-ready handoffs.
- **`/debt-triage`** — separate skill for `tasks/debt-backlog.md` (technical debt, not bugs). Different file, conversational prioritization.
- **`/learn-lessons`** — if blitz reveals recurring patterns (e.g., 3 different items all flag the same hook bug), capture the meta-lesson.

## Surface Integration

`/bug-blitz` is wired into the discovery surfaces (smoke run 2026-05-06-22h42 follow-up):

- **`/session-start`** — "work the backlog" framing advocates `/bug-blitz` when `tasks/bug-backlog.md` exists with ≥10 open P1+P2 items.
- **`/workday-start`** — Step 1.55 emits a depth nudge (moderate 10–19, heavy ≥20) before scheduled-rechecks.
- **`/workweek-complete` Step 4** — bug-backlog depth check joins the improvement-queue triage gate; ≥10 open proposes a blitz, otherwise summarised.
- **Coordinator README** — listed adjacent to `/bug-sweep` in the commands table, failure-modes section, and skills section.
