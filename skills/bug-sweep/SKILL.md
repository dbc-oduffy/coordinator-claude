---
name: bug-sweep
description: "Codebase bug hunt: fix AI-fixable bugs, defer the rest."
allowed-tools: ["Agent", "Read", "Write", "Edit", "Bash", "Grep", "Glob", "Skill"]
argument-hint: "[path]"
---

# Bug Sweep — Systematic Codebase Bug Hunt

Fix everything AI-fixable in-session; defer human-dependent bugs to the backlog. **Not for:**
recent-commit review (`daily-code-health`), architectural debt (`weekly-architecture-audit`), or
a single known bug.

`$ARGUMENTS`: optional scope path; omitted = full codebase. Announce the run, naming the scope.

## Phase 0: Scope and Pattern Selection (YOU do this)

1. `bug-sweep-probes detect-stack [path]` → `language_files`, `test_dirs`, `config_files`.
2. **`DOCS_VERIFY`** — compiled/opinionated stack → `true` (enables Track C, makes Phase 3.5
   mandatory); TS/JS/Python → `false`. Calibration: wiki.
3. Select patterns from the Pattern Library per stack; universal patterns always apply.
4. Define 3-6 search chunks by directory/system (architecture atlas, else `DIRECTORY.md`).
5. Hot-zone rank: `query-completions --since "30d" --where "nature=bugfix" --format json` by
   path-prefix — hot chunks first, a bugfix in the last 7 days deprioritizes (both: surface the
   conflict). Record to `state/bug-sweep/{run-id}/hot-zone-ranking.md`; skip on empty.
6. Identify the test runner (Track B); read state/lessons/ for project patterns to add.
7. Run ID `YYYY-MM-DD-HHhMM`; create `state/scratch/bug-sweep/{run-id}/` (Phase 1 notes) and `state/bug-sweep/{run-id}/` (the durable record).

## Pre-Dispatch: Verify Backlog Against Current Code

Run `backlog-grind-assemble brief bug-sweep`. Empty/all-closed `state/bug-backlog/` → Phase 1.
Open entries → resolve `j-bug-sweep-pre-dispatch-verification-due` (re-verify against HEAD?).
If verifying: first check
<!-- VERBATIM -->`git log --since="1 hour ago" --remotes='origin/work/*' --oneline`; non-empty (a
peer can invert a verdict) → verifier is Sonnet and re-verifies at Phase 1 launch
(<!-- VERBATIM -->`git log --oneline -- <file>` since its read SHA); else Haiku. One agent per
system: read each cited `file:line` against HEAD, check
<!-- VERBATIM -->`git log --oneline -5 {file}` for resolving commits, return
`still-open`/`already-fixed` (SHA, or `unattributed`). Drop `already-fixed`; record IDs + SHAs to
`pre-dispatch-already-fixed.md` (Phase 4 prunes from it).

> **Do not ask whether to dispatch** — invoking this skill IS the request for it; it dissolves no
> gate this skill's body names.

**Before fixing any P0/P1**, read the cited code yourself or via a verifier, never the agent's paraphrase.

## Phase 1: Search + Test (dispatch leaf agents, parallel)

**Track A1 — Mechanical Pattern Grep** (YOU, <30s): `TODO`/`FIXME`/`HACK`/`XXX`/`BUG`, empty
catch/except, language-specific patterns across all chunks; feeds A2.

**Track A2 — Semantic Analysis** (one Sonnet per chunk), given its file list, patterns, A1's
results, and hot-zone ranking (cooldown paths noted). Prompt, verbatim:

> Cast a wide net. Report bugs AND code smells — both are worth fixing. Err on the side of
> reporting — false positives are cheap, missed issues are expensive. Use P0/P1/P2 severity ONLY —
> do not invent P3, 'info', or 'defer' tiers. A code smell that can be fixed in under 5 minutes is
> P2, not 'informational'. Write your complete findings to `{scratch-path}` using the Write tool.
> Return only a brief summary — the coordinator reads full output from disk.

Per file: vet A1's findings; give each finding severity, confidence (HIGH/MEDIUM/LOW), file:line,
description, AI-fixable-or-not. Scratch: `{chunk-name}-phase1-sonnet.md`.

<!-- engine-gap: field=directives[d_bug_sweep_track_a2_prompt].fields producer=unknown memo=engine-gap-markers-name-a-memo-that-was-never-filed.md -->

**Track B — Test Suite** (EM runs; Haiku parses): **Cloud session: no baseline** — skip the grant
ask and this track, report `suite: not-run (cloud)`, prove each fix with its covering tests.
Otherwise Tier-U-gated: ask the PM with `backlog-grind-assemble brief bug-sweep`'s exact ask text
(`j-bug-sweep-tier-u-grant`; the grant must name the suite/Tier-U). Granted → `backlog-grind-assemble
apply bug-sweep --decisions-file <path>` (`{"j-bug-sweep-tier-u-grant":"granted"}`). Declined →
apply nothing, skip Track B, report the decline. Recheck `tier-u-grant-cli check` live before
firing (exit 0 grants, 1 halts). Run the suite via Bash yourself; one `model: "haiku"` agent parses
the captured output (never runs it) into counts and per-failure error/file:line/likely source. No
suite → report the gap, skip. Scratch: `tests-phase1-haiku.md`.

**Track C — API Documentation Verification** (`DOCS_VERIFY = true` only): one
`coordinator:docs-checker` per chunk (`model: "sonnet"`), sidecar path from the brief, against
Example-game-repo-docs (UE) or Context7. `INCORRECT` → P1. `UNVERIFIED` + zero RAG hits on a UE-naming
symbol → P2 ("possible hallucinated API"); from server unavailability → drop. Scratch:
`{chunk-name}-phase1-docschecker.md`.

**Scratch verification:** before Phase 2 run
<!-- VERBATIM -->`ls state/scratch/bug-sweep/{run-id}/`. Re-dispatch once per missing chunk;
on a second failure proceed with what exists.

## Phase 1.5: Churn-Gated Findings Verification (conditional)

**Gate:** `git rev-list --count <last-sweep-sha>..HEAD -- <chunk-paths>` (SHA from
`state/bug-backlog/.meta.yaml`'s `last_sweep_commit:`) > 200; missing meta/key or ≤200 → Phase 2.
One Haiku verifier per chunk reads each P0/P1's `file:line` from `{chunk-name}-phase1-sonnet.md`,
returns `still-present`/`already-fixed` (SHA/`unattributed`)/`pattern-shifted` into
`{chunk-name}-phase1.5-verification.md`. Phase 2 considers only `still-present`.

## Phase 2: Triage (YOU do this)

Read all Phase 1 findings; with `DOCS_VERIFY = true`, merge Track C's findings in first.

**Categorize** into **Fix now** (default — clear bug or smell + clear fix), **Backlog** (only
genuinely blocked: human verification, plan session, or intent-ambiguous logic — never "low
confidence," never a code smell, never under 10 minutes), or **False positive**. "Needs runtime
confirmation" never backlogs a free, safe fix (correct by inspection, reverts cleanly, no
migration, no user-visible change): apply it, note "fix applied; runtime confirmation deferred."

Output: "Fix now"/"Backlog" lists by file, cross-agent duplicates merged, plus
`state/bug-sweep/{run-id}/phase2-fix-now.json` (Phase 4's diff gate consumes it): a JSON array of
`{"id","file","line","severity","description"}`, minimum field `file`.

## Phase 3: Fix (dispatch Sonnet executors, parallel)

No-ask rule as Pre-Dispatch. Dispatch Sonnet executors grouped by file/system, each with its
finding group, source files, acceptance criteria per fix, and this contract, verbatim:

> Fix the listed bugs. For each fix:
> 1. Read the cited line range.
> 2. Determine whether the code is in the buggy state described OR already in the fixed state.
> 3. If already fixed, report `no-op — already in HEAD` for that finding and SKIP without editing.
> 4. If buggy, apply the fix and re-read to verify the edit landed.
>
> **Do NOT apply an edit that produces byte-identical content** — that is a false-positive
> finding, not a fix. Write a brief summary to `{scratch-path}` using the Write tool,
> distinguishing `fixed` vs `no-op — already in HEAD` per finding.

<!-- engine-gap: field=directives[d_bug_sweep_phase3_executor_prompt].fields producer=unknown memo=engine-gap-markers-name-a-memo-that-was-never-filed.md -->

**Post-fix:** re-run the suite yourself (same Track B grant, recheck `tier-u-grant-cli check` live,
no second ask). A newly-failing test → revert that fix, backlog it noting "regression introduced."
Skip if Track B was declined/skipped or cloud (run each fix's covering tests instead).

## Phase 3.5: Post-Fix API Verification (YOU do this)

Mandatory when `DOCS_VERIFY = true`; recommended when fixes touch external library APIs. Over
<!-- VERBATIM -->`git diff --name-only`, dispatch one `coordinator:docs-checker` (sidecar path from
the brief) to report INCORRECT and suspicious-UNVERIFIED API claims only. `INCORRECT` in a fix → `git checkout -- {file}`, backlog with the
verdict. Zero-hit UE-naming `UNVERIFIED` → flag, don't block.

## Phase 4: Report and Commit (YOU do this)

0. **Mechanical diff gate:** `bug-sweep-probes verify-diff --fix-now
   state/bug-sweep/{run-id}/phase2-fix-now.json` — non-empty `missing` means an executor
   `no-op` claimed a fix; list as **Zero-diff fixes**, doesn't block committing real fixes.

1. **Commit fixes** — never narrate the git sequence, never `coordinator-safe-commit`
   (`coordinator/docs/wiki/concurrent-em-git-operations/scoped-safety-commits.md`): pass each path
   (<!-- VERBATIM -->`git diff --name-only`) as a `--wave-path` to `backlog-grind-assemble apply
   bug-sweep --wave-path <path>... --granularity per-wave --message "bug-sweep: fixed N bugs
   across M files"`. **`--message` must be a single line** (a multi-line value is silently
   truncated at the first LF); extra detail goes in the backlog entries the commit renames.

2. **Prune already-fixed entries** (separate commit; skip if none): close each item in
   `pre-dispatch-already-fixed.md` (`status: closed`, `closed_by: <SHA or unattributed>`, `git mv`
   to `archive/bug-backlog/<YYYY-MM>/`), then the same apply op, single-line `--message`.

3. **Append genuinely blocked items** via `coordinator-queue-append --schema bug-backlog`
   (`--body-file`, never inline prose; cross-reference `state/debt-backlog/`). Update
   `state/bug-backlog/.meta.yaml` (`last_sweep_commit:`/`last_sweep_at:`, zero counts too), then
   the same apply op scoped to `state/bug-backlog/`. Background: bug-sweep-residue § Phase 4 apply-op recipes.

4. **Report to PM, by exception** — file:line detail belongs in the commit message. Print
   `## Bug Sweep Complete`, `**Found:** [total] findings ([X] fixed, [Y] blocked, [Z] false
   positives)`, `**Fixes applied:** [N] fixed — [one-line characterization]`. Append only a
   tripped line: `**Tests run:**` (Track B failed), `**Zero-diff fixes:**`, `**Phase 1.5
   verification:**` (K still-present, L already-fixed, M pattern-shifted), `**Blocked items:**`
   (each with "why blocked"), `**Docs verification (Phase 3.5):**` / `**Track C API sweep:**`
   (INCORRECT found). Never print `Scope`, `Patterns applied`, `Backlog pruned`, or clean items.

5. **Commit the record directory** `state/bug-sweep/{run-id}/` with the sweep's commit; a handoff
   cites that path. The scratch run dir is never cited.

## Pattern Library, Cost Profile, Failure Modes

`pipelines/bug-sweep/pattern-library.md`: pattern catalog, cost profile, failure-modes matrix.
