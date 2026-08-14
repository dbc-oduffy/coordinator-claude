---
name: bug-sweep
description: "Codebase bug hunt — find and fix AI-fixable bugs, defer the rest."
allowed-tools: ["Agent", "Read", "Write", "Edit", "Bash", "Grep", "Glob", "Skill"]
argument-hint: "[path]"
---

# Bug Sweep — Systematic Codebase Bug Hunt

Sweep the codebase for bug patterns, fix everything AI-fixable in-session, defer human-dependent
bugs to the backlog. Not a daily check — use when code churn warrants it. Occupies your context
for ~20-40 min; not background work.

**Not for:** recent-commit review (`daily-code-health`), architectural debt
(`weekly-architecture-audit`), or a single known bug (just fix it — or `/systematic-debugging`).

## Arguments

`$ARGUMENTS` is an optional path to scope the sweep; omitted means full codebase. Announce: "I'm
running `/bug-sweep` — systematic bug hunt [scoped to X / across the full codebase]."

## Phase 0: Scope and Pattern Selection (YOU do this)

1. `bug-sweep-probes detect-stack [path]` → `language_files`, `test_dirs`, `config_files`.
2. **`DOCS_VERIFY`** — compiled/opinionated stack → `true` (enables Track C, makes Phase 3.5
   mandatory); TS/JS/Python → `false`. Calibration: wiki.
3. Select patterns from the Pattern Library (end of this doc) per detected stack; universal
   patterns always apply.
4. Define 3-6 search chunks by directory/system (architecture atlas, else `DIRECTORY.md`/directory
   structure).
5. Hot-zone rank: `query-completions --since "30d" --where "nature=bugfix" --format json`,
   aggregated by path-prefix — hot chunks dispatch first, chunks with a bugfix completion in the
   last 7 days deprioritize; both at once is a real conflict, surface it. Record to
   `tasks/scratch/bug-sweep/{run-id}/hot-zone-ranking.md`; skip if the query returns nothing.
6. Identify the test runner (Track B).
7. Read `state/lessons/` for project-specific patterns to add.
8. Generate run ID (`YYYY-MM-DD-HHhMM`), create `tasks/scratch/bug-sweep/{run-id}/`.
9. Output: chunk table with pattern assignments, hot-zone ranking, test runner command.

## Pre-Dispatch: Verify Backlog Against Current Code

Run `backlog-grind-assemble brief bug-sweep`. Empty/all-closed `state/bug-backlog/` → straight to
Phase 1. Open entries → resolve `j-bug-sweep-pre-dispatch-verification-due` (re-verify cited items
against HEAD before dispatch? — the engine has no opinion here).

If verifying, dispatch one Haiku agent per system: read each cited `file:line` against HEAD, check
<!-- VERBATIM -->`git log --oneline -5 {file}` for resolving commits, return
`still-open`/`already-fixed` (SHA, or `unattributed`). Drop `already-fixed`; record verified-fixed
IDs + SHAs to `pre-dispatch-already-fixed.md` (Phase 4 prunes the backlog from this file).

**A concurrent-EM peer can invert a verdict mid-pipeline** — check
<!-- VERBATIM -->`git log --since="1 hour ago" --remotes='origin/work/*' --oneline` before
dispatching verifiers; non-empty means escalate the verifier to Sonnet and re-verify at Phase 1
launch (<!-- VERBATIM -->`git log --oneline -- <file>` since its read SHA). Detail: wiki.

**Before fixing any P0/P1**, read the cited code yourself (or via a verifier) — never trust the
agent's paraphrase; P0 carries a measured far higher false-positive rate than P2.

## Phase 1: Search + Test (dispatch leaf agents, parallel)

**Track A1 — Mechanical Pattern Grep** (YOU, fast): deterministic grep across all chunks —
`TODO`/`FIXME`/`HACK`/`XXX`/`BUG`, empty catch/except, language-specific mechanical patterns.
<30s; feeds Track A2 as context.

**Track A2 — Semantic Analysis** (one Sonnet per chunk): the sweep's actual purpose, irreducibly a
judgment call. Each agent gets its chunk's file list, patterns, Track A1's results, and hot-zone
ranking (cooldown paths noted). Dispatch prompt, verbatim:

> Cast a wide net. Report bugs AND code smells — both are worth fixing. Err on the side of
> reporting — false positives are cheap, missed issues are expensive. Use P0/P1/P2 severity ONLY —
> do not invent P3, 'info', or 'defer' tiers. A code smell that can be fixed in under 5 minutes is
> P2, not 'informational'. Write your complete findings to `{scratch-path}` using the Write tool.
> Return only a brief summary — the coordinator reads full output from disk.

Per file: review Track A1's grep findings for false positives, run deeper semantic analysis (error
handling gaps, null access, resource leaks, logic errors, dead code, race conditions), and for each
finding give severity (P0/P1/P2), confidence (HIGH/MEDIUM/LOW), file:line, description,
AI-fixable-or-not. Scratch: `{chunk-name}-phase1-sonnet.md`.

<!-- engine-gap: field=directives[d_bug_sweep_track_a2_prompt].fields producer=unknown memo=2026-08-14-doe-claude-em-three-cut-obligations-from-the-corpus-grind.md -->

**Track B — Test Suite** (EM runs; Haiku parses): Tier-U-gated, no implicit grant. Ask the PM
using `backlog-grind-assemble brief bug-sweep`'s exact ask text (`j-bug-sweep-tier-u-grant`) — a
grant names the suite/Tier-U as its subject, not adjacent sweep approval. Granted → `backlog-grind-
assemble apply bug-sweep --decisions '{"j-bug-sweep-tier-u-grant":"granted"}'` (shells to
`tier-u-grant-cli` for you). Declined → apply nothing, skip Track B, report the decline.

Immediately before firing, recheck `tier-u-grant-cli check` live (exit 0 grants, exit 1 halts). Run
the suite via Bash yourself; dispatch one `model: "haiku"` agent to parse the captured output
(never invoke it) into pass/fail/error counts and, per failure, error/file:line/likely source. No
suite → report the gap, skip. Scratch: `tests-phase1-haiku.md`.

**Track C — API Documentation Verification** (`DOCS_VERIFY = true` only): dispatch one
`coordinator:docs-checker` per chunk (`model: "sonnet"`), sidecar path from the dispatch brief.
Scans external API references against example-game-repo-docs (UE) or Context7. `INCORRECT` → P1. `UNVERIFIED`
+ zero RAG hits on a UE-naming symbol → P2 ("possible hallucinated API"). `UNVERIFIED` from server
unavailability → drop. Rationale: wiki. Scratch: `{chunk-name}-phase1-docschecker.md`.

**Scratch verification:** before Phase 2, confirm expected scratch files exist —
<!-- VERBATIM -->`ls tasks/scratch/bug-sweep/{run-id}/`. Re-dispatch once for any missing chunk;
proceed with what's available on a second failure.

## Phase 1.5: Churn-Gated Findings Verification (conditional)

**Gate:** `git rev-list --count <last-sweep-sha>..HEAD -- <chunk-paths>` (SHA from
`state/bug-backlog/.meta.yaml`'s `last_sweep_commit:`) > 200; missing meta/key or ≤200 → skip to
Phase 2. Rationale: wiki.

Dispatch one Haiku verifier per chunk against its `{chunk-name}-phase1-sonnet.md`: read the cited
`file:line` for every P0/P1, return `still-present`/`already-fixed` (SHA/`unattributed`)/
`pattern-shifted`. Write to `{chunk-name}-phase1.5-verification.md`. Phase 2 considers only
`still-present`; the rest drop out, noted in the Phase 4 report.

## Phase 2: Triage (YOU do this)

Read all Phase 1 findings. When `DOCS_VERIFY = true`, merge Track C's `INCORRECT` and suspicious
`UNVERIFIED` findings in first.

**Categorize** (the sweep's other irreducible judgment call) into **Fix now** (default — clear bug
or smell + clear fix), **Backlog** (only genuinely blocked: human verification, plan session, or
intent-ambiguous logic — never "low confidence," never a code smell, never under 10 minutes), or
**False positive** (pattern matched, not a bug). "Needs runtime confirmation" is not itself a
reason to backlog when the fix is free and safe (trivially correct by inspection, reverts cleanly,
no migration, no user-visible change) — apply it now and note "fix applied; runtime confirmation
deferred." Bias toward fixing: same effort to fix as to document, and a code smell is always
fixable — never belongs in backlog. Full worked examples: wiki.

Output: "Fix now"/"Backlog" lists grouped by file, cross-agent duplicates merged. Also write
`phase2-fix-now.json` (Phase 4's diff gate consumes it), minimum field `file`:

```json
[
  {"id": "F-A-03", "file": "src/foo.py", "line": 142, "severity": "P1", "description": "missing threading.Lock on counter"}
]
```

## Phase 3: Fix (dispatch Sonnet executors, parallel)

Dispatch Sonnet executors, grouped by file/system to minimize conflicts. Each receives its finding
group, source files, acceptance criteria per fix, and this verify-first contract, verbatim
(sweepers anchor on historical bug shapes after heavy churn without it):

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

<!-- engine-gap: field=directives[d_bug_sweep_phase3_executor_prompt].fields producer=unknown memo=2026-08-14-doe-claude-em-three-cut-obligations-from-the-corpus-grind.md -->

**Post-fix:** re-run the test suite yourself (same Track B grant, recheck `tier-u-grant-cli check`
live, no second ask). Any newly-failing test → revert that fix, backlog it noting "regression
introduced." Skip if Track B was declined/skipped.

## Phase 3.5: Post-Fix API Verification (YOU do this)

Mandatory when `DOCS_VERIFY = true`; recommended whenever fixes touch external library APIs. Get
the changed-file set (<!-- VERBATIM -->`git diff --name-only`); dispatch one
`coordinator:docs-checker` against it (sidecar path from the brief): "verify all external API
claims in these modified files; report INCORRECT and suspicious-UNVERIFIED only." No `INCORRECT` →
Phase 4. `INCORRECT` in a fix → `git checkout -- {file}` to revert, backlog with the verdict,
original bug stays open. `UNVERIFIED` zero-hit UE-naming pattern → flag in the report, don't block.
Reads only changed files — not a re-sweep.

## Phase 4: Report and Commit (YOU do this)

0. **Mechanical diff gate:** `bug-sweep-probes verify-diff --fix-now
   tasks/scratch/bug-sweep/{run-id}/phase2-fix-now.json` — non-empty `missing` means an executor
   `no-op` claimed a fix; list as **Zero-diff fixes**, doesn't block committing real fixes.
   Rationale: wiki.

1. **Commit fixes** — never narrate the git sequence, never `coordinator-safe-commit`
   (`docs/wiki/scoped-safety-commits.md`): pass each changed path
   (<!-- VERBATIM -->`git diff --name-only`) as a `--wave-path` to `backlog-grind-assemble apply
   bug-sweep --wave-path <path>... --granularity per-wave --message "bug-sweep: fixed N bugs
   across M files"` — one op, one commit, engine-scoped so a concurrent session's staged files
   stay untouched.

2. **Prune already-fixed backlog entries** (separate, paper-trail commit). Read
   `pre-dispatch-already-fixed.md`; per item, stamp `status: closed`, `closed_at:`, `closed_by:
   <SHA or unattributed>`, `git mv` to `archive/bug-backlog/<YYYY-MM>/`, then the same apply op
   (`--wave-path` per renamed file, `--granularity per-wave`, `--message` naming each closed ID
   with its resolving SHA). Skip if nothing was already-fixed.

3. **Append genuinely blocked items** via `coordinator-queue-append --schema bug-backlog --surface
   <subsystem> --severity P1 --status open --title "<title>" --body "<description>" [--why-blocked
   "<reason>"] [--evidence <ref>]` (cross-reference `state/debt-backlog/` where it overlaps). Write/
   update `state/bug-backlog/.meta.yaml` (`last_sweep_commit:`/`last_sweep_at:`, zero counts too),
   then the same apply op scoped to `state/bug-backlog/`.

4. **Report to PM, by exception.** A clean sweep spends its budget on facts the PM can't read off
   the commit — per-`file:line` detail belongs in the commit message, not here.

   ```markdown
   ## Bug Sweep Complete

   **Found:** [total] findings ([X] fixed, [Y] blocked, [Z] false positives)
   **Fixes applied:** [N] fixed — [one-line characterization]. Full file:line list is in the
   commit message.
   ```

   Append a line **only** when its condition holds:

   | Line | Include only when |
   |---|---|
   | `**Tests run:**` | Track B ran and any test failed/errored |
   | `**Zero-diff fixes:**` | the diff gate's `missing` list is non-empty |
   | `**Phase 1.5 verification:**` | churn gate tripped — K still-present, L already-fixed, M pattern-shifted |
   | `**Blocked items:**` | N ≥ 1 — list each with its "why blocked" reason |
   | `**Docs verification (Phase 3.5):**` | `DOCS_VERIFY = true` and an INCORRECT finding was reverted |
   | `**Track C API sweep:**` | `DOCS_VERIFY = true` and it found INCORRECT/suspicious-UNVERIFIED |

   `Scope`, `Patterns applied`, and `Backlog pruned` are never printed — the commits already
   record them. A clean Track B run, an untripped Phase 1.5 gate, and zero blocked items stay
   silent too — absence is the signal. Rationale: wiki.

5. **Leave scratch in place after commit.** `tasks/scratch/bug-sweep/{run-id}/` carries `file:line`
   citations later consumers may need. Delete at `/workstream-complete`'s self-clean step or an
   explicit PM cleanup signal, whichever comes first; note the scratch path in the handoff body if
   the next step is `/handoff`.

## Pattern Library, Cost Profile, Failure Modes

See `pipelines/bug-sweep/pattern-library.md` for the full pattern catalog (universal + per-language:
Python, JS/TS, C++/UE, code smells), the cost profile table, and the full failure-modes matrix.
