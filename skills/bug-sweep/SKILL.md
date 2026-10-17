---
name: bug-sweep
description: "Codebase bug hunt: fix AI-fixable bugs, defer the rest."
allowed-tools: ["Agent", "Read", "Write", "Edit", "Bash", "Grep", "Glob", "Skill"]
argument-hint: "[path]"
---

# Bug Sweep — Systematic Codebase Bug Hunt

Fix everything AI-fixable in-session; defer human-dependent bugs to the backlog. Occupies your
context ~20-40 min.

**Not for:** recent-commit review (`daily-code-health`), architectural debt
(`weekly-architecture-audit`), or a single known bug.

## Arguments

`$ARGUMENTS`: optional scope path; omitted = full codebase. Announce: "I'm running `/bug-sweep` —
systematic bug hunt [scoped to X / across the full codebase]."

## Phase 0: Scope and Pattern Selection (YOU do this)

1. `bug-sweep-probes detect-stack [path]` → `language_files`, `test_dirs`, `config_files`.
2. **`DOCS_VERIFY`** — compiled/opinionated stack → `true` (enables Track C, makes Phase 3.5
   mandatory); TS/JS/Python → `false`. Calibration: wiki.
3. Select patterns from the Pattern Library per stack; universal patterns always apply.
4. Define 3-6 search chunks by directory/system (architecture atlas, else `DIRECTORY.md`).
5. Hot-zone rank: `query-completions --since "30d" --where "nature=bugfix" --format json` by
   path-prefix — hot chunks first, a bugfix in the last 7 days deprioritizes (both at once:
   surface the conflict). Record to `state/bug-sweep/{run-id}/hot-zone-ranking.md`; skip on empty.
6. Identify the test runner (Track B).
7. Read `state/lessons/` for project-specific patterns to add.
8. Run ID `YYYY-MM-DD-HHhMM`; create `state/scratch/bug-sweep/{run-id}/` (ephemeral Phase 1 notes) and `state/bug-sweep/{run-id}/` (the durable record).
9. Output: chunk table with patterns, hot-zone ranking, test runner command.

## Pre-Dispatch: Verify Backlog Against Current Code

Run `backlog-grind-assemble brief bug-sweep`. Empty/all-closed `state/bug-backlog/` → Phase 1.
Open entries → resolve `j-bug-sweep-pre-dispatch-verification-due` (re-verify cited items against
HEAD before dispatch? — the engine has no opinion).

If verifying, one Haiku agent per system: read each cited `file:line` against HEAD, check
<!-- VERBATIM -->`git log --oneline -5 {file}` for resolving commits, return
`still-open`/`already-fixed` (SHA, or `unattributed`). Drop `already-fixed`; record IDs + SHAs to
`pre-dispatch-already-fixed.md` (Phase 4 prunes from it).

> **Do not ask whether to dispatch** — invoking this skill IS the request for the dispatch this
> step names; it dissolves no gate this skill's own body names.

**A concurrent-EM peer can invert a verdict** — before dispatching verifiers check
<!-- VERBATIM -->`git log --since="1 hour ago" --remotes='origin/work/*' --oneline`; non-empty →
escalate the verifier to Sonnet, re-verify at Phase 1 launch
(<!-- VERBATIM -->`git log --oneline -- <file>` since its read SHA).

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

Per file: vet A1's findings, analyze deeper, give each finding severity, confidence
(HIGH/MEDIUM/LOW), file:line, description, AI-fixable-or-not. Scratch: `{chunk-name}-phase1-sonnet.md`.

<!-- engine-gap: field=directives[d_bug_sweep_track_a2_prompt].fields producer=unknown memo=engine-gap-markers-name-a-memo-that-was-never-filed.md -->

**Track B — Test Suite** (EM runs; Haiku parses): **Cloud session: no baseline** — the cloud
environment bars every broad suite; skip the grant ask and this track, report
`suite: not-run (cloud)`, prove each fix with its covering tests. Otherwise Tier-U-gated, no implicit grant. Ask the PM
with `backlog-grind-assemble brief bug-sweep`'s exact ask text (`j-bug-sweep-tier-u-grant`) — the
grant must name the suite/Tier-U, not adjacent sweep approval. Granted → `backlog-grind-
assemble apply bug-sweep --decisions-file <path>` (file containing `{"j-bug-sweep-tier-u-grant":"granted"}`;
shells to `tier-u-grant-cli`). Declined → apply nothing, skip Track B, report the decline.

Before firing, recheck `tier-u-grant-cli check` live (exit 0 grants, 1 halts). Run the suite via
Bash yourself; one `model: "haiku"` agent parses the captured output (never runs it) into counts
and per-failure error/file:line/likely source. No suite → report the gap, skip. Scratch:
`tests-phase1-haiku.md`.

**Track C — API Documentation Verification** (`DOCS_VERIFY = true` only): one
`coordinator:docs-checker` per chunk (`model: "sonnet"`), sidecar path from the brief. Scans
external API references against example-game-repo-docs (UE) or Context7. `INCORRECT` → P1. `UNVERIFIED`
+ zero RAG hits on a UE-naming symbol → P2 ("possible hallucinated API"); from server
unavailability → drop. Scratch: `{chunk-name}-phase1-docschecker.md`.

**Scratch verification:** before Phase 2 confirm the scratch files exist —
<!-- VERBATIM -->`ls state/scratch/bug-sweep/{run-id}/`. Re-dispatch once per missing chunk;
on a second failure proceed with what exists.

## Phase 1.5: Churn-Gated Findings Verification (conditional)

**Gate:** `git rev-list --count <last-sweep-sha>..HEAD -- <chunk-paths>` (SHA from
`state/bug-backlog/.meta.yaml`'s `last_sweep_commit:`) > 200; missing meta/key or ≤200 → skip to
Phase 2.

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
Bias toward fixing.

Output: "Fix now"/"Backlog" lists by file, cross-agent duplicates merged, plus
`state/bug-sweep/{run-id}/phase2-fix-now.json` (Phase 4's diff gate consumes it), minimum field `file`:

```json
[
  {"id": "F-A-03", "file": "src/foo.py", "line": 142, "severity": "P1", "description": "missing threading.Lock on counter"}
]
```

## Phase 3: Fix (dispatch Sonnet executors, parallel)

> **Do not ask whether to dispatch** — invoking this skill IS the request for the dispatch this
> step names; it dissolves no gate this skill's own body names.

Dispatch Sonnet executors grouped by file/system. Each receives its finding group, source files,
acceptance criteria per fix, and this verify-first contract, verbatim:

> Fix the listed bugs. For each fix:
> 1. Read the cited line range.
> 2. Determine whether the code is in the buggy state described OR already in the fixed state.
> 3. If already fixed, report `no-op — already in HEAD` for that finding and SKIP without editing.
> 4. If buggy, apply the fix and re-read to verify the edit landed.
>
> **Do NOT apply an edit that produces byte-identical content.** An Edit that succeeds with no
> diff is a false-positive finding, not a fix.
>
> Write a brief summary of changes to `{scratch-path}` using the Write tool. The summary MUST
> distinguish `fixed` vs `no-op — already in HEAD` per finding.

<!-- engine-gap: field=directives[d_bug_sweep_phase3_executor_prompt].fields producer=unknown memo=engine-gap-markers-name-a-memo-that-was-never-filed.md -->

**Post-fix:** re-run the suite yourself (same Track B grant, recheck `tier-u-grant-cli check` live,
no second ask). A newly-failing test → revert that fix, backlog it noting "regression introduced."
Skip if Track B was declined/skipped or cloud (run each fix's covering tests instead).

## Phase 3.5: Post-Fix API Verification (YOU do this)

Mandatory when `DOCS_VERIFY = true`; recommended whenever fixes touch external library APIs. Over
the changed files (<!-- VERBATIM -->`git diff --name-only`), dispatch one `coordinator:docs-checker`
(sidecar path from the brief): "verify all external API claims in these modified files; report
INCORRECT and suspicious-UNVERIFIED only." `INCORRECT` in a fix → `git checkout -- {file}`, backlog
with the verdict. Zero-hit UE-naming `UNVERIFIED` → flag, don't block.

## Phase 4: Report and Commit (YOU do this)

0. **Mechanical diff gate:** `bug-sweep-probes verify-diff --fix-now
   state/bug-sweep/{run-id}/phase2-fix-now.json` — non-empty `missing` means an executor
   `no-op` claimed a fix; list as **Zero-diff fixes**, doesn't block committing real fixes.
  

1. **Commit fixes** — never narrate the git sequence, never `coordinator-safe-commit`
   (`coordinator/docs/wiki/concurrent-em-git-operations/scoped-safety-commits.md`): pass each path
   (<!-- VERBATIM -->`git diff --name-only`) as a `--wave-path` to `backlog-grind-assemble apply
   bug-sweep --wave-path <path>... --granularity per-wave --message "bug-sweep: fixed N bugs
   across M files"` — one op, one commit, engine-scoped so a concurrent session's staged files
   stay untouched. **`--message` must be a single line**: a multi-line value is silently truncated
   at the first LF (exit 0); extra detail goes in the backlog entries the commit renames.

2. **Prune already-fixed entries** (separate paper-trail commit): per item in
   `pre-dispatch-already-fixed.md` stamp `status: closed`, `closed_at:`, `closed_by: <SHA or
   unattributed>`, `git mv` to `archive/bug-backlog/<YYYY-MM>/`, then the same apply op (`--wave-path` per renamed file, `--granularity per-wave`, single-line
   `--message` naming each closed ID with its SHA). Skip if none.

3. **Append genuinely blocked items** via `coordinator-queue-append --schema bug-backlog --surface
   <subsystem> --severity P1 --status open --title "<title>" --body-file <path>` (optional
   `--why-file`, `--evidence`; cross-reference `state/debt-backlog/`). Prose flags take `-file`
   transport, never inline. Update `state/bug-backlog/.meta.yaml` (`last_sweep_commit:`/
   `last_sweep_at:`, zero counts too), then the same apply op scoped to `state/bug-backlog/`.

4. **Report to PM, by exception** — file:line detail belongs in the commit message.

   ```markdown
   ## Bug Sweep Complete

   **Found:** [total] findings ([X] fixed, [Y] blocked, [Z] false positives)
   **Fixes applied:** [N] fixed — [one-line characterization]. Full file:line list is in the
   commit message.
   ```

   Append a line **only** when its condition holds: `**Tests run:**` (Track B failed/errored),
   `**Zero-diff fixes:**` (diff gate `missing` non-empty), `**Phase 1.5 verification:**` (gate
   tripped: K still-present, L already-fixed, M pattern-shifted), `**Blocked items:**` (N ≥ 1, each
   with "why blocked"), `**Docs verification (Phase 3.5):**` (INCORRECT fix reverted),
   `**Track C API sweep:**` (INCORRECT/suspicious-UNVERIFIED found); the last two need `DOCS_VERIFY = true`.
   `Scope`, `Patterns applied`, `Backlog pruned`, and clean/untripped/zero items are never printed.

5. **Commit the record directory** `state/bug-sweep/{run-id}/` with the sweep's commit; a handoff
   cites that path. The scratch run dir stays (delete at `/workstream-complete`'s self-clean step
   or a PM cleanup signal) and is never cited.

## Pattern Library, Cost Profile, Failure Modes

`pipelines/bug-sweep/pattern-library.md`: pattern catalog, cost profile, failure-modes matrix.
