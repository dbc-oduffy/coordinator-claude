---
name: bug-blitz
description: "Grind the bug backlog and tests; fix small, surface big items to PM."
allowed-tools: ["Agent", "Read", "Write", "Edit", "Bash", "Grep", "Glob", "Skill", "TaskCreate", "TaskUpdate", "TaskGet", "TaskList"]
argument-hint: "[--dry-run | --max=N]"
---

# Bug Blitz — Aggressively Tackle the Bug Backlog and the Test Suite

Verify-then-grind through **two work sources every run**: (1) `state/bug-backlog/` (directory of per-entry YAML files, each at `state/bug-backlog/<id>.yaml`), and (2) **the full test suite** — the configured test command, run under an explicit PM authorization gate (`/bug-blitz` holds no implicit grant for a full-suite invocation — see Phase 0.6), and each genuinely-failing test becomes a first-class fix item that flows through the same triage → wave → fix → verify machinery as a backlog bug. Re-check each backlog item against current code (some have been fixed silently), triage by size, fix the small items autonomously in file-disjoint waves, surface big-item spinoff candidates for PM authorization (per `skills/spinoff/SKILL.md` Step 0 — spinoffs are never EM-initiated). Triage is folded into this skill — there is no separate triage step.

**A green test suite is part of the definition of done, once the PM has authorized the full-suite leg.** The run does not complete on a thin "fixed 2 bugs" note while tests are known red. Failing tests are chased to root cause and fixed (or, when oversized, surfaced as spinoffs) exactly like backlog bugs. If the PM declines full-suite authorization, the run proceeds on the backlog leg only — see Phase 0.6.

**Runs even when the backlog is empty.** An absent or empty `state/bug-backlog/` directory is no longer a halt condition — the (authorized) test-suite leg still runs. The run only short-circuits to a green no-op when the backlog is empty AND the full suite passes clean. (Built from `/bug-sweep` (finds new bugs) + `/mise-en-place` (autonomous waves) but distinct: backlog entries and test failures are NOT pre-spec'd executor stubs, so triage is the spec-creation step.)

**Announce at start:** "Running `/bug-blitz` — I'll ask once for authorization to run the full test suite (it's used twice: a baseline now, a confirm-green pass after fixes), then aggressive autonomous parallel waves through every fixable backlog item AND every failing test. The default is dispatch-and-spot-check; defer requires named evidence. Big items surface as a spinoff candidate list for your authorization before any handoff is written."

## Default Stance — Dispatch, Don't Defer

The skill's job is to *grind the backlog down*, not to produce a triage report. The characteristic failure mode is deferring the large majority of items on lazy grounds — "lacks standalone entry," "judgment-call refactor," "intersects active plan" — and shipping a run that fixes a handful out of dozens. That is failure, not caution. **Fix the lazy defer, not the run.**

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

**Recovery framing.** When a prior run left most of the backlog deferred in "summary form," expand the summary-form entries inline during Phase 1, dispatch them in file-disjoint waves, and converge on a fix-rate of most of the verified-open backlog per run, not a token fraction of it.

## Severity-Tier Dispatch Rules

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

Severity tagging for untagged backlog entries happens at Phase 0.5 step 1 below, not here — this section only sets the resulting dispatch shape once a tag exists.

## Spinoff Phantom Verification

**Spinoffs are last resort, not the size-overflow drawer.** The characteristic failure mode: the PM is offered a candidate-spinoff list where most entries are phantoms (file/symbol already gone from HEAD) or small fixes mis-classified as `big`. Pre-surface verification is mandatory:

For each `big` candidate, BEFORE adding it to the spinoff candidate list shown at Phase 2.1:

1. **Phantom check.** Re-read the cited file:line on HEAD. If the symbol named in the recommended-fix is absent AND the bug pattern is absent, the spinoff is a phantom — close as `already-fixed` (or `file-removed`) with a one-line note, do not surface.
2. **Size sanity-check.** Re-measure the footprint. Open the cited file and the recommended-fix's named imports / call sites. If the fix is genuinely 1-2 file edits totaling <50 lines net change, reclassify as `small` and route to the next wave — `big` is footprint ≥3 files OR new module/interface, not just "I'd need to think about it." Two-line fixes are never `big`.
3. **Already-covered check.** Grep `state/handoffs/` and `docs/plans/*.md` for an existing handoff/plan covering the same fix scope. If one exists with `deployment_state: ready_to_fire` or `status: executing`, the spinoff is duplicate — close with a cite to the existing artifact, do not surface.

Only candidates that survive all three checks go onto the PM-authorization list at Phase 2.1. Surface count must be calibrated to "PM expects ≤2 phantoms in a 5-item list" — if more than 30% of pre-surface candidates flunk a check, the EM's size-classify is mis-calibrated for this run and should be re-tightened mid-run.

## Queue Terminus Alignment — the Four Outcome Classes

`/bug-blitz` is a queue-terminus ceremony: every item this skill disposes of lands in one of
four outcome classes (immediate dispatch, solo baton, close, or themed baton), and a themed
baton is authored to the multi-item shape used at Step 2.15 below (shared thesis, why these
belong together, the picker-up's first move, every constituent id/path). Bug-blitz already
maps three of the four outcome classes to existing machinery; the fourth (themed baton) is the
delta this alignment adds — it is largely naming what already exists as the shared doctrine,
not rebuilding a pipeline:

| Outcome class | Existing `/bug-blitz` mechanism |
|---|---|
| Immediate dispatch | Phase 3 file-disjoint executor waves (`small` items) |
| Solo baton | Phase 2.1's PM-authorized auto-spinoff (`big` items) |
| Close | `already-fixed` / `file-removed` verdicts (Phase 1) and the `wontfix` status value |
| Themed baton | **New — Step 2.15 below.** N `small` items clustered by shared thesis into one handoff, authored to the multi-item shape (shared thesis, why these belong together, the picker-up's first move, every constituent id/path). |

Bug-specific dispositions — severity, repro, the `wontfix` status value — are unchanged by
this alignment. The four classes are the terminus, not a replacement for bug triage's own
semantics. `/bug-sweep` (the queue producer, Phase 4 append) has no PM gate and no triage
terminus of its own — out of scope here; its only touch is whether its append populates the
`initiative` clustering key, which is a producer-side concern, not this file's.

### Step 2.15: Themed-baton clustering (between Step 2.1 and Step 2.2)

After Step 2.1 disposes of `big` items but before Step 2.2 drops already-fixed items, cluster
the verified-`small` set (across all severities, pre-footprint-grouping) by title keyword.
Clustering is a proposal mechanism, not an authority — the op proposes, the EM disposes. No
clustering output is ever written as a baton verbatim; the EM merges, splits, or discards
proposed clusters before a baton is authored. Prefer, in order: (1) a registered engine op
wrapping the clustering leg, if one exists; (2) degraded-but-mechanical — the shipped
`detect-initiative-candidates` CLI in `claude-klabauter`, invoked directly, rather than either
blocking or reinventing the clustering algorithm inline; (3) EM judgment, only if the CLI itself
is unreachable — the fallback of last resort, not the default degrade target. Bug-blitz's own
delta from that ladder: suppress the `directory` clustering signal (degenerate on this single-queue
corpus — it returns one cluster containing everything) and expect only a minority of proposed
clusters to survive EM judgment as genuine themes; merge/split/discard the rest before anything
is surfaced.

A cluster that survives EM judgment becomes a **themed-baton candidate**, added to the same
Phase 2.1 PM-authorization list (see below) — it is never dispatched as if its members were
ordinary `small` items, and it is never surfaced through a second gate.

**Footprint-vs-theme partition — footprint governs dispatch, theme governs authorship.**
Step 2.3 already clusters `small` items by FILE FOOTPRINT to build disjoint executor waves;
thematic clustering is a different partition of the same item set and will disagree with it in
either direction — a real theme can be footprint-**concentrated** (its members collide on write
targets and would have to serialize) or footprint-**scattered** (its members land in different
footprint waves); neither direction is hypothetical. **Resolution: footprint partitioning
governs wave dispatch (Step 2.3 is unchanged); thematic clustering governs baton authorship
only.**

- A themed baton whose members span several footprint waves is authored as **one baton
  referencing multiple wave IDs** — it is never force-dispatched together as a single wave.
- A themed baton whose members collide on one footprint is authored as one baton whose
  constituent fixes dispatch **serially** within that footprint's wave, same as any other
  same-footprint item.

Either way, the baton is one handoff; the wave-dispatch mechanics under it are whatever
footprint partitioning already dictates. A themed baton never overrides Step 2.3's
disjointness analysis to force parallel dispatch of colliding footprints.

**Gate hole closed — themed batons ride the Phase 2.1 gate regardless of constituent size.**
Phase 2.1's PM-authorization gate today fires only for `big` items. A themed baton bundling
several `small` items is the entire point of the new class, and reaching no gate on the
existing path is a defect this alignment closes: DEC-7 forbids adding a second gate, so every
themed-baton candidate — regardless of whether its constituents are `small` or `big` — is
added to the *same* candidate list Step 2.1 already surfaces to the PM (extend that message's
numbered list with themed-baton rows, e.g. `N. <cluster thesis> — themed baton, M items:
<IDs>, footprint: <wave IDs or "serial, footprint X">`), authorized or declined in the same
PM response. **A themed baton is never dispatched as if it were a `small`-class immediate
fix** — even after PM authorization, its constituent items are scaffolded into the baton body
per the multi-item shape above (shared thesis, why these belong together,
the picker-up's first move, every constituent id/path), not routed to Step 2.3's wave-builder.

Declined themed-baton candidates fall back to the size/severity classification their
constituent items already carry from Phase 1 — Step 2.3 wave-building for `small` items, or
Step 2.1 solo-spinoff if any constituent is independently `big`. A decline is a fallback to
the classes the items already qualified for, not a re-park.

### Scaffolding and category (interim)

Themed batons scaffold via `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-doc-new"` with its current default `category: infra`,
hand-edited to the new queue-derived-baton value immediately after scaffolding — the same
interim behaviour `/debt-triage` C4 uses, pending the claude-klabauter category-default change (C9).

## Arguments

| Trigger | Mode |
|---------|------|
| No arguments | Full grind: PM-authorized full test suite + every fix-able item, no stops |
| `--dry-run` | Phases 0-2 only — produce a plan; do not dispatch executors and do not run the Phase 4 gate. **Zero-cost on the suite:** `--dry-run` asks no authorization and executes no Tier-U invocation — Phase 0.7 is a no-op stub, and the plan notes that `TF-*` items are not sourced this mode ("test-failure sourcing requires a live authorized run"). |
| `--max=N` | Cap fixed items at N this run; remainder stays in backlog. `TF-*` items are P0/P1, so they sort ahead of all P2 backlog items; within a severity tier they interleave with backlog items by ID (`TF-*` sorts after `BS-*` lexically). A small `--max` therefore prioritises a red suite over the P2 backlog — not necessarily over equal-severity backlog bugs. |
| `--dry-run --max=N` | Phases 0-2 only, plan capped at N items — produces a capped plan without dispatching executors |

## Out-of-scope actions (autonomous-run prohibition)

Out of scope for this run, no exceptions: `gh pr merge`, `gh pr create` against main, `git push origin main`, hibernate / shutdown / power-off, killing other processes, `--no-verify` / `--no-gpg-sign`. Do not propose; do not request authorization mid-run. Power-state cues ("late", "overnight") authorize urgency only — never hibernate.

## Phase 0: Preflight (~1 min, EM)

1. **Check backlog presence — do NOT halt on absence.** Note whether `state/bug-backlog/` exists and how many `.yaml` files it contains (use `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/query-records" --type bug | wc -l` or `ls state/bug-backlog/*.yaml 2>/dev/null | wc -l`). An absent or empty `state/bug-backlog/` is **not** a halt condition: the test-suite leg (Phase 0.7) runs regardless and supplies its own work items. Record `backlog_present: true|false` and the open count for the Phase 2 plan. (Contrast with the prior behaviour, which halted here and recommended `/bug-sweep` — that gate is removed because a clean backlog with a red suite is exactly the state this skill must still act on.)
2. **Generate run ID.** Format: `YYYY-MM-DD-HHhMM`. Scratch dir: `state/scratch/bug-blitz/{run-id}/`.
3. **Active workstream branch check.** Confirm `git branch --show-current` is an allowed workstream branch: `work/{machine}/{date-or-span}` (span names like `work/machine-a/2026-05-06to07` are accepted; both uppercase and lowercase machine segments are accepted). If not an allowed branch (e.g. on `feature/X` or bare topic branch), halt and report. Bug-blitz commits explicitly (no helper — see Phase 3 commit doctrine) and must run on an active workstream branch. **Note: `/bug-blitz` is fail-closed-only (no override mode).** It does not set `COORDINATOR_OVERRIDE_BRANCH=1` and does not run off the active workstream branch under any circumstance.
4. **Capture branch name.** Run `git branch --show-current` and store its output as `BLITZ_BRANCH`. EM re-confirms this branch immediately before each commit at the wave gate. Executors never commit (see Phase 3) so they don't need this.
5. **Read a sample of backlog entries** (skip if backlog absent) to confirm last_sweep_commit (from any entry's `created` field or a directory-level header file if present) and item counts. If entries are old relative to HEAD, expect more "already-fixed" verdicts in Phase 1.

## Phase 0.6: Full-Suite Authorization Gate (EM, PM ask — skipped under `--dry-run`)

`/bug-blitz` holds no implicit grant for a Tier-U (full-suite) invocation. Ask the PM explicitly, once, before Phase 0.7 fires.

**One ask covers both runs this skill needs.** The premise — chase failing tests to green — structurally requires seeing the suite twice: a baseline now (Phase 0.7) and a confirm-green re-run after fixes land (Phase 4 step 0). These cannot collapse into a single execution; the second run's whole purpose is to observe state that only exists after the first run's fixes are committed. Rather than asking twice, ask once for both, sequenced (never concurrent) under the same grant. This falls out of the grant being **session-scoped** (valid for as long as the granting session lives — no expiry clock, no use counter; see `coordinator/schemas/tier-u-grant.schema.json`), not something this skill engineers around: write the grant once, and both runs read the same live token.

**Ask:** *"This run needs the full test suite — once now to baseline, once after fixes to confirm green. Authorize the full-suite tier for this run?"*

**The ask is not the grant — write the token, don't just narrate the answer.** A PM response only counts as a grant when it is an explicit affirmative reply to *this specific ask* — "yes, run the full suite", "authorized, full-suite tier", "granted — Tier U", "go ahead and run the full suite" said in direct response to the Phase 0.6 question, naming its subject (the full suite / Tier U / the full-suite run) so the stored note is self-contained for a future auditor. Adjacent approval of the blitz run in general ("looks good", "go ahead with bug-blitz", "sounds good, run it") does NOT qualify — that approves running `/bug-blitz` itself, not a Tier-U full-suite invocation, and must NOT be treated as a grant.

**A terse-but-clear reply ("yes" / "authorized" / "granted" alone, with no restated subject) still qualifies as a grant** — refusing a plainly-intended one-word reply to a well-formed ask because it didn't repeat the subject would turn the bar into a password, not an audit aid. What changes is what gets written, not whether it counts: the EM does not store the bare reply as the note. Compose the note from the Phase 0.6 ask's subject plus the PM's reply (e.g. `note: "full-suite tier authorized ('yes')"`) so a fresh reader gets the subject without reconstructing the transcript. A reply that already names its subject can be stored closer to verbatim.

- **Granted (qualifying phrasing above)** → write the grant via `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/tier-u-grant-cli" grant pm <note>`, carrying the composed note (subject + PM's reply, per above) — this is the same CLI Phase 0.7/Phase 4 will read from. No second ask at Phase 4 step 0: the same token, being session-scoped, already covers it — Phase 4 step 0 re-confirms liveness via the same CLI's `check` verb rather than re-asking. Proceed to Phase 0.7.
- **Declined** → write nothing. No token is written and none is left on disk — do not call the grant CLI at all on a decline. Skip Phase 0.7 and the Phase 4 suite gate entirely. Continue on the backlog leg only (Phase 0.5 built from backlog items alone, no `TF-*` items). Note the decline in the final report ("full-suite leg declined by PM this run — backlog-only grind").
- **`--dry-run`** → do not ask, and do not write a grant; the mode runs zero Tier-U invocations by design (see Arguments table). Phase 0.7 becomes a no-op stub.

## Phase 0.7: Full Test-Suite Baseline (EM + test-evidence-parser — the parser never runs the suite itself, ~3 min; no-op unless Phase 0.6 granted)

Run the project's configured test suite up front, once Phase 0.6 has granted authorization (or skip entirely under `--dry-run` / decline). Every genuinely-failing test becomes a synthetic work item that joins the backlog items at Phase 0.5 and rides the same triage → wave → fix → verify machinery.

0. **Consult the grant before firing — do not rely on the Phase 0.6 conversation having happened.** Run `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/tier-u-grant-cli" check`. Exit 0 means granted — proceed. Exit 1 (ungranted) halts this phase regardless of what the transcript above says; a token absent or malformed reads as ungranted, never granted (fail-closed — see the schema's provenance note).

1. **Resolve the test command via the single-owner resolver CLI — do NOT inline a guess.** Bug-blitz wants the FULL suite (it chases every failing test), so it resolves `--full` — the full-tier sibling of the `--fast` mode that `/validate` runs. Both live in the same module, so bug-blitz cannot drift to a hand-rolled test surface. Run the installed forwarder `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-resolve-validation-cmd" --full`, redirecting stderr to a scratch diagnostic path. The forwarder self-resolves the CLI's home repo, so no separate root resolution is needed. Capture the resolver's stdout as `TEST_CMD` and, immediately after (before it is overwritten by any later command), its exit code as `RESOLVER_EXIT`. Branch on `RESOLVER_EXIT` — it tells you the coverage tier so the plan/report can label it honestly:
   - **Exit 0 — full suite resolved** (`full_test_cmd:` in `coordinator.local.md` or `$COORDINATOR_FULL_TEST_CMD`). `suite_state: full`. This is the intended path.
   - **Exit 3 — fast-tier fallback.** No `full_test_cmd` is configured, so the resolver fell back to the fast tier. `suite_state: fast-fallback`. Run it (coverage is real, just narrower), and **report the coverage honestly** — the announce, plan, and final report say "fast tier (no full_test_cmd configured)" plus the remediation (`set full_test_cmd: in coordinator.local.md`). Do NOT call a fast-fallback run "the entire test suite."
   - **Exit 2 — unconfigured.** Neither tier is configured for this repo. `suite_state: unconfigured`. Emit the diagnostic, continue (the backlog leg still runs), name the remediation in the report. Do **not** fabricate a `npm test` / `pytest` guess; an unconfigured suite is a reported gap, not an invented command.
2. **The EM runs the suite directly via `Bash`; a subagent parses the captured output, never invokes.** Running the full suite is a Tier-U (or Tier-F, if scoped to the fast tier) invocation — subagents never invoke it (same rule as `/bug-sweep` Track B). The EM runs the resolved `TEST_CMD` via `Bash`, capturing stdout/stderr to `state/scratch/bug-blitz/{run-id}/suite-baseline-raw.txt`. Then dispatch `coordinator:test-evidence-parser` (`run_in_background: true`), instructing it to skip its own Workflow steps 1-2 (framework auto-detection and running the command) and instead `Read` the captured raw-output file at that path, then classify each failure per its standard rubric: `real` / `flake` / `env` / `timeout` / `known-skip`. On-disk deliverable: `state/scratch/bug-blitz/{run-id}/suite-baseline.md` (table of every failure with classification + the failing test's file:line and assertion excerpt). Inline the disk-first verification preamble (below) verbatim.
3. **Convert `real` failures into synthetic items.** For each `real` failure, mint a work item with ID `TF-{run-id}-{n}`. **The parser does NOT emit a crash-shape class** — its rubric is exactly `real` / `flake` / `env` / `timeout` / `known-skip` (see `agents/test-evidence-parser.md`). So crash-vs-assertion severity is an **EM-side post-classification on the parser's evidence excerpt**, not a column read:
   - Grep the failure's evidence excerpt for crash signals — `SIGSEGV` / `segfault` / `panic` / `abort` / `core dumped` / `unhandled exception` / `fatal` → **P0**.
   - Otherwise (assertion failure / wrong-result / broken-flow) → **P1**.
   The item's citation is the failing test's file:line plus the assertion excerpt **when the parser supplies file:line** (its `Evidence excerpt` column carries file:line only WHERE AVAILABLE). **When file:line is absent** (common for crash-shape and some runners), flag the item `locus-underdetermined`: Phase 1 triage derives the locus from the test name + assertion excerpt by reading the test file, and the Phase 3 executor's pattern-presence gate is relaxed from "confirm the bug pattern at the cited line" to "reproduce the failure, then fix to green." Never mint a TF item whose absent citation will make the executor BLOCK. Its "recommended fix" field is left for Phase 1 triage to derive from the cited code (a test failure does not pre-name its own fix). Write the synthetic items to `state/scratch/bug-blitz/{run-id}/test-failures.md` in the same row schema as the backlog so Phase 0.5 and Phase 1 treat them uniformly.
   - **`flake` / `env` / `timeout` are NOT dispatched as fixes** — they are noted in the final report under a "Suite noise" line with the parser's evidence. A reproducible `flake` across two runs is itself a P1 bug (file it to the backlog via the report), but bug-blitz does not chase it in-wave on a single observation. **`known-skip` is ignored.**
4. **Locus discrimination — failing test ≠ buggy test.** A `real` failure can mean the *code under test* is wrong (fix the code) OR the *test* is wrong (a stale assertion against intended new behaviour). This is the same fix-locus discrimination the bug rules demand: Phase 1 triage reads the cited test AND the code it exercises before classifying, and the executor's P0/P1 verification gate (Phase 3) applies. **Never "fix" a red test by weakening its assertion to green without evidence the assertion was wrong** — that is the cardinal failure mode of automated test-chasing and is treated as a `BLOCKED: assertion-weakening-without-evidence` report, not a fix.

**Disk-first verification preamble (inline verbatim into the test-evidence-parser dispatch):**
> Reply with `DONE: <path>` ONLY after you have confirmed the file exists at the path above (use Read or Bash `ls` to verify). If you find yourself about to summarize the deliverable inline in your reply, STOP — the coordinator reads from disk, not chat. Inline summary without a written file counts as task failure.

**Empty-backlog-and-green-suite short-circuit.** If `state/bug-backlog/` is absent/empty (zero `.yaml` files) AND the suite resolves, runs, and is fully green (zero `real` failures), there is no work: skip Phases 0.5–3, write no commit, and emit this one-line all-clear report — *"Bug-blitz {run-id}: backlog empty/absent, suite green — no work this run."* (Distinct from the Phase 4 step 3 no-op, which covers a *non-empty* backlog where nothing was fixable and points to `/bug-sweep` or `/plan`.) An all-clear is a useful signal, not a failed run. **Under a Phase 0.6 decline or `--dry-run`, this short-circuit cannot fire** (suite state is unknown, not green) — an empty backlog in that mode is simply "no backlog work this run," with the suite leg noted as skipped rather than green.

## Phase 0.5: Severity Split (EM, ~1 min)

Per § Severity-Tier Dispatch Rules above, split the combined work set — backlog items **plus the `TF-{run-id}-*` synthetic test-failure items from Phase 0.7** — by severity before dispatching Phase 1 chunks. Output: three lists (P2, P1, P0) routed to different downstream shapes. Test-failure items arrive already severity-tagged (P0 for crash-shape, P1 for assertion-shape) and slot directly into the P0/P1 lists — they do not get re-tagged, but they DO get Phase 1 triage (a failing test still needs its fix-locus derived from the cited code).

**Invariant — TF items NEVER skip Phase 1, regardless of severity.** Unlike a P2 backlog item (which carries a pre-declared footprint from its citation and may skip Phase 1), a test failure carries NO pre-declared footprint — the fix-locus is triage-derived, never citation-given. The file-disjoint wave-builder (Step 2.3) groups by footprint and has nothing to group on until triage derives it. A `TF-*` item reaching Step 2.3 without a Phase-1 footprint is a routing bug. (This is why TF items are minted P0/P1 only — there is no P2 TF path.)

1. **Tag any untagged items inline.** P2 default unless the entry's shape is `crash` / `data-loss` / `security` / `silent-corruption` (→ P0) or `wrong-behavior` / `breaking-flow` (→ P1). `TF-*` items are pre-tagged by Phase 0.7 — leave them.
2. **Route by tier:**
   - **P2 items skip Phase 1 entirely** — go directly to Phase 3 dispatch with footprint declared from the backlog citation.
   - **P1 items → Phase 1, chunks of ~20**, verify-only Haiku (still-open / already-fixed / file-removed).
   - **P0 items → Phase 1, chunks of ~5**, verify + cited-code-read Haiku with EM spot-check on each verdict.
3. **Emit the three counts** to scratch (`state/scratch/bug-blitz/{run-id}/severity-split.md`) so the wave-plan in Phase 2 can reconcile against them.

## Phase 1: Verify + Triage (parallel Haiku per chunk, severity-conditional)

The backlog has likely drifted. Some items have been silently fixed by other workstreams. Some have changed shape. Some are no longer reachable. Verify before grinding — but only for P1/P0 per Phase 0.5; P2s skip this phase and go straight to Phase 3.

**Chunk size is severity-conditional** (see Phase 0.5): P1s go to chunks of ~20 (verify-only); P0s go to chunks of ~5 (verify + cited-code-read + EM spot-check). For each chunk, dispatch one Haiku agent with `run_in_background: true` and an on-disk deliverable. See disk-first verification preamble below — inline it in every chunk-Haiku dispatch prompt.

**Disk-first verification preamble (inline verbatim into every Phase 1 chunk-Haiku dispatch prompt):**
> Reply with `DONE: <path>` ONLY after you have confirmed the file exists at the path above (use Read or Bash `ls` to verify). If you find yourself about to summarize the deliverable inline in your reply, STOP — the coordinator reads from disk, not chat. Inline summary without a written file counts as task failure.

**Pattern-presence verifier (dispatch alongside each chunk-verify Haiku).** In addition to the standard chunk verifier, dispatch a second Haiku per chunk with `run_in_background: true` to confirm that each `still-open` item's cited pattern is present at the exact file:line described. For each item:
1. Read the cited file at the cited line.
2. Confirm the named variable/symbol from the recommended-fix field is present.
3. If the pattern has shifted ≥3 lines OR the named symbol is no longer present → flag `pattern-shifted`.
Verdict per item: `confirmed` | `pattern-shifted`. Write to `state/scratch/bug-blitz/{run-id}/chunk-N-pattern-check.md`. Reply `DONE: <path>`.

After both chunk verifiers return, EM reviews `pattern-shifted` items inline before adding them to executor dispatch. Items flagged `pattern-shifted` are NOT dispatched to executors automatically — EM reads the cited file and decides: re-classify, update the backlog entry, or proceed with adjusted recommended-fix.

**Pattern-shifted is a dispatch signal, not a defer reason.** A missing symbol at the cited line is rarely a genuinely moved or resolved bug — it is far more often the same bug with the named symbol renamed or the surrounding code reshuffled by an unrelated edit. When the cited symbol is missing at the cited line, the high-prior interpretation is "the bug still exists, the pattern moved" — grep the recommended-fix's central noun-phrase (the buggy condition, not the symbol name) across the cited file and adjacent siblings before classifying as deferral-eligible. Closing as `file-removed` requires `ls` confirming absence; closing as `already-fixed` requires a commit SHA showing the fix. "Pattern shifted, can't find it" with neither evidence is a re-grep task, not a defer.

**Backlog entries written in summary-form paragraphs are actionable items, not noise.** Dense deferred-summary sections with file:line citations are verification candidates — do not skip them at Phase 1 triage.

**Pre-classification eligibility — verify status freshness, not just FIXED tagging.** An entry tagged FIXED months ago may have a fresh IN-PROGRESS continuation underneath; check `git log -- <cited-path>` since the FIXED tag's date before pruning. "Already-fixed ghost" prunes can collateral-damage in-progress work.

**Long-stale backlog — ghost-prune dominates fix-value; trust the header SHA over the per-entry OPEN field.** When Phase 0 step 5 shows `last_sweep_commit` many commits behind HEAD, the dominant value of this run is *pruning ghost entries* (items the backlog still marks OPEN but that are provably fixed or whose cited file is gone on HEAD), not net-new fixes — expect a high `already-fixed` / `file-removed` rate and treat the prune as the deliverable, not a thin run. When a per-entry `OPEN` status field disagrees with the backlog header's SHA attribution (the header is the freshest cross-cutting truth; per-entry status fields drift because they are hand-maintained per item), **trust the header SHA over the OPEN field** — re-verify against HEAD per the cited-file read, and close ghosts as `already-fixed` (commit SHA cited) or `file-removed` (`ls` confirms absence). A per-entry `OPEN` field is not evidence the bug is live; it is a stale assertion the verify step exists to overturn. **Stale per-entry status drifts in both directions** — a stale FIXED tag can hide live in-progress work (paragraph above), and a stale OPEN field can be a ghost (here); the resolution is the same in both cases — the per-entry status field is hypothesis, the HEAD re-verification is ground truth, and the SHA is a verification-triggering prior, never an auto-close.

**Per-item verification + size classification.** Each agent, for each item — read frontmatter from `state/bug-backlog/<id>.yaml` to extract `id`, `severity`, `system`, `title`, `body`, `cross_ref`, and `why_blocked` fields. The `cross_ref` field carries the file:line citation used below:

1. **Verify still-applies:**
   - Read the cited file:line (from the entry's `cross_ref` field) — does the bug pattern still exist in HEAD?
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
| BS-2026-05-06-007 | still-open | small | find-polluter.py | Add `command -v npm` pre-flight + `set -o pipefail` |
| BS-2026-05-06-001 | still-open | big | coordinator-safe-commit, tests/... | Frontmatter parser refactor + new CRLF tests |
| BS-2026-05-06-018 | already-fixed | — | — | Fixed in commit abc1234 |
```

IDs in the table correspond to the YAML filename stems (e.g. `BS-2026-05-06-007` ↔ `state/bug-backlog/BS-2026-05-06-007.yaml`).

**Scratch path:** `state/scratch/bug-blitz/{run-id}/chunk-N-verify.md`. Each agent must end with `DONE: <path>` after writing.

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

Block on PM response. Only authored spinoffs proceed; unauthorized candidates revert to `needs-investigation` in `state/bug-backlog/<ID>.yaml` (update the `why_blocked` field with "PM declined spinoff at bug-blitz <run-id>"). Do not retry without fresh PM direction.

For each PM-authorized `big` item, write a spinoff handoff via the `spinoff-handoff-template` directive (`backlog-grind-assemble`'s `directives.build_spinoff_handoff_template_emission`) rather than hand-assembling the frontmatter and body — the directive renders the canonical schema (the `commands/spinoff.md` frontmatter shape, `status: active` never `pickup-ready`, `predecessor: none`, `deployment_state: ready_to_fire` hard-coded because a bug-blitz spinoff is already triaged as actionable-but-oversized and carries no further PM-gate, and the standard body-section set plus the trailing spinoff marker) from fields this run already holds: title, run-id, the backlog item's ID/footprint, and its `body`/`cross_ref`/`why_blocked`. State the intent — one spinoff handoff per authorized item — and hand the directive the computed fields; do not re-narrate the template's own shape. (`/spinoff <slug>` per-item remains the sibling manual path.)

Path: `state/handoffs/{YYYY-MM-DD}_{HHMMSS}_bug-blitz-spinoff-{slug}.md`

Close the YAML entry via `git mv state/bug-backlog/<ID>.yaml archive/bug-backlog/<YYYY-MM>/<ID>.yaml`, then set `status: closed`, `closed_at: <YYYY-MM-DD>`, and `closed_by: spun-off-<handoff-path>` in the archived file's frontmatter. The item leaves the active `state/bug-backlog/` directory.

### Step 2.2: Drop already-fixed items

Delete already-fixed items from active P1/P2 tables; name them in the Phase 4 commit subject and final report.

### Step 2.3: Build small-item waves (file-disjoint)

**Phase 2 — pre-bundle by file footprint.** Group bug IDs by shared file footprint and dispatch one executor per file (not per bug ID). For Phase 3 verification, prefer batched per-wave verifiers when the EM is reading each DONE line; per-DONE Haiku is overkill at that read-density.

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

Backlog at start: N items (or "backlog empty/absent")
Suite baseline: <suite_state> — <P> real failures (flake/env/timeout: <Q>) → TF-{run-id}-* items
Verified open: V (already-fixed: A, file-removed: R)
Auto-spun-off (big): S → state/handoffs/...
Queued for fix: F across W waves (backlog: Fb, test-failures: Ft)

Wave 1 (parallel, file-disjoint): [item IDs]
Wave 2 (parallel, file-disjoint): [item IDs]
...

Tail: backlog updated with commit SHAs + spinoff paths; full suite re-run at Phase 4 gate. No /update-docs invoked.
```

If `--dry-run`, stop here.

## Phase 3: Execute Waves (Sonnet executors edit; EM serializes commits)

**Commit doctrine — single committer, named op, per-item granularity.** Parallel executors that each call a commit helper produce two known failure modes: (a) **concurrent-commit absorption** — N near-simultaneous `git commit` calls bundle each other's staged work into the first commit, leaving N-1 commit messages orphaned; (b) **scope sweep** — a touched-files commit heuristic in a long-lived session absorbs unrelated dirty work from other workstreams into the bug-blitz commits. Both defects are eliminated by: executors edit-and-report only (no commit), EM commits at the wave gate via `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/backlog-grind-assemble" apply bug-blitz --wave-path <path> [--wave-path <path>]... --granularity per-item --message <message>` (one `--wave-path` per file in the item's footprint — `granularity` governs commit cardinality across items, not files-per-commit; all of one item's files land in that item's single commit regardless of how many `--wave-path` flags it took to name them), one committer at a time. Bug-blitz's per-item audit trail (one commit per item, own message) is the `per-item` granularity's whole point — never collapse this to `per-wave`.

For each wave:

1. **Dispatch all items concurrently.** One Sonnet executor per item, `run_in_background: true`, `mode: "auto"`. Render each prompt via the `executor-dispatch-prompt-template` directive (`backlog-grind-assemble`'s `directives.build_executor_dispatch_prompt_template_emission`) rather than hand-assembling the fixed multi-part prompt every dispatch — the directive emits the disk-first verification preamble, the full backlog entry (severity, file:line, description, recommended fix), the P0/P1 verification gate (relaxed for `TF-*` items flagged `locus-underdetermined`: reproduce the failing test first, confirm it fails, then fix — there is no cited line to anchor on), the assertion-weakening prohibition (required on every `TF-*` test-failure item — fixing the code under test is the default; a genuinely wrong test is `BLOCKED: assertion-weakening-without-evidence`, not an edited assertion), the footprint constraint, the edit-and-report constraint (executors never stage or commit — see the commit doctrine above), and the DONE-summary spec (`state/scratch/bug-blitz/{run-id}/{item-id}.done.md`: `status`, `files`, `before`/`after` snippets, `verified` result, no commit SHA). Feed the directive this item's severity/file:line/description/recommended-fix and footprint; do not re-narrate the template's own fixed parts.

2. **Process completions on arrival.** Read each DONE summary (only). Do NOT pull executor transcripts.

3. **Dispatch Haiku verifier per DONE.** `run_in_background: true`, on-disk verdict. Verifier reads the DONE summary + the unstaged diff for the item's `files` (`git diff -- <paths>`) + cited code; confirms bug pattern is gone, no out-of-footprint changes, tests pass. Verdict: `PASS` | `PATTERN-STILL-PRESENT` | `FOOTPRINT-VIOLATION` | `REGRESSION`. Path: `state/scratch/bug-blitz/{run-id}/{item-id}.verify.md`.

4. **Wave gate — named op, per-item granularity, incremental backlog update.** When all wave verifiers return:
   - **Poll `git branch --show-current` BEFORE any wave-gate action.** If it does not equal `$BLITZ_BRANCH`, halt and reconcile before proceeding.
   - **For each PASS item, in deterministic order (sorted by item ID), the EM commits it via the named op** — one invocation per item, its own message, no interleaving from a sibling session: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/backlog-grind-assemble" apply bug-blitz --wave-path <path1 from DONE.files> [--wave-path <path2 from DONE.files>]... --granularity per-item --message "<item-id>: <one-line description>"` (one `--wave-path` per path in `DONE.files` — `granularity` still governs commit cardinality *across items*, not files-per-commit; all of one item's files land in that item's single commit regardless of how many `--wave-path` flags it took to name them). The op re-verifies `$BLITZ_BRANCH` immediately before its own commit and halts before committing if the branch flipped — this owns the per-commit branch recheck, no separate mid-loop poll needed. Capture the returned `commit_sha` and write it back to the DONE summary as `commit: <sha>`.
   - For PASS items: PASS commits at the wave gate ARE the persistence (commit subject names each item) — a mid-run crash recovers attribution from `git log` rather than file state, so there is no separate per-wave backlog append. PASS items are deleted from the active P1/P2 tables in Phase 4 only.
   - For BLOCKED / non-PASS items: the working tree still carries the executor's edit (unstaged, since executors don't commit). Revert via `git checkout -- <paths from DONE.files>` — the op is a stage-and-commit helper, not a revert helper, so this leg stays direct git (safe under this skill because the EM controls staging and no other agent has unstaged work on these specific paths within the wave). Update `state/bug-backlog/<id>.yaml` — append a note to `why_blocked` field: `re-attempted-{date}: <reason>`, leave the entry in the active backlog directory.
   - Update flight-recorder tasks to `completed`.

5. **Brief status, no question.** "Wave N complete (X fixed, Y blocked). Firing wave N+1."

**Single-item waves execute the same way** — overhead of background dispatch is small and consistent shape simplifies recovery. The EM-serial commit pattern is unchanged for single-item waves (one commit by EM).

## Phase 4: Green-Suite Gate + Update Backlog + Report

After all waves complete:

0. **Green-suite gate — re-run the full suite (mandatory, every run that dispatched any fix, and only reachable when Phase 0.6 was granted).** This re-run is covered by the single Phase 0.6 authorization — do not ask again, but do re-confirm the token is still live via `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/tier-u-grant-cli" check` before firing, rather than trusting that the earlier conversation happened. Same invocation split as Phase 0.7 step 2: the EM re-resolves and re-runs the test command directly via `Bash` against HEAD (post-fix tree), capturing stdout/stderr to `state/scratch/bug-blitz/{run-id}/suite-final-raw.txt`; then dispatch `coordinator:test-evidence-parser` to `Read` and classify that captured file only — it never invokes the suite. Deliverable: `state/scratch/bug-blitz/{run-id}/suite-final.md`. Compare against the Phase 0.7 baseline:
   - **All `real` failures cleared → gate PASS.** Record the green result for the report.
   - **A baseline failure persists** → the TF item's fix did not take. It was committed at the wave gate only if its verifier returned PASS, so a persistent failure means the verifier and the suite disagree — re-read the cited test and code, and either (a) dispatch one more corrective wave this run, or (b) if oversized, `git revert` the non-working fix commit and surface the TF item as a spinoff. Do NOT report the run green with a known-red suite. (This is a *pre-existing* failure that stayed red — reverting the attempted fix returns the suite to its baseline state, which is acceptable; the unfixed test was already red when the run started.)
   - **A NEW failure appeared that was green at baseline → regression introduced by this run's fixes.** This is the highest-priority signal, and its terminal state is **mandatory revert, not surface-and-leave**. Identify the introducing commit (`git log` since baseline over the failing test's exercised paths). Attempt a correction in one more wave; if that wave does not restore green, **`git revert <introducing-sha>`** (NOT `git reset` — the commit is already pushed by the auto-push hook, and the shared-branch doctrine forbids history rewrites on a pushed branch), then re-run the gate to confirm green-restored. Name the reverted regression explicitly in the final report. A bug-blitz must NEVER end with the suite redder than it found it on a self-inflicted regression — reverting the regression is non-negotiable; "stop chasing the original TF item and spin it off" is the acceptable part, "leave the regression on the branch" is not.
   - **Suite `unconfigured`** (Phase 0.7 resolver exit 2): the gate is a no-op; the final report carries the `unconfigured` remediation note. The backlog leg still completes normally.

   **Loop bound — one corrective wave, then a forced terminal state (never an open loop):**
   - *Pre-existing failure still red after one corrective wave:* stop chasing in-wave, leave the (reverted-to-baseline) state, surface the residual red test to the PM as a spinoff candidate. The suite is no worse than at baseline.
   - *Self-inflicted regression still red after one corrective wave:* `git revert` the introducing commit (above), confirm the gate goes green, then surface the original TF item as a spinoff. The suite returns to baseline-or-better. Either way the run does not loop a second corrective wave.

1. **Final backlog update — close-with-paper-trail.** The fixes themselves are the paper trail (each PASS item committed individually in Phase 3 with the item ID in the commit subject); Phase 4 moves the now-resolved YAML files out of the active `state/bug-backlog/` directory so the queue only holds open items. Phase 4:
   - **Archives — does NOT delete in-place — every closed entry** via `git mv`. Three closure shapes, all move to `archive/bug-backlog/<YYYY-MM>/<id>.yaml`:
     - `PASS` (fixed this run) — set `status: closed`, `closed_at: <date>`, `closed_by: <Phase-3-commit-SHA>` in the archived YAML's frontmatter before committing the move
     - `already-fixed` (silent prior fix) — set `status: closed`, `closed_at: <date>`, `closed_by: <prior-commit-SHA>` (this frontmatter field is the attribution's only record — the final report no longer carries an "Already-fixed" line)
     - `spun-off` (auto-spinoff to handoff) — set `status: closed`, `closed_at: <date>`, `closed_by: spun-off-<handoff-path>`
   - **No "Resolved this run" section inside the active backlog directory.** The `state/bug-backlog/` directory holds only `open`-status YAML files. Closed items live in `archive/bug-backlog/`, `git log`, and the final report.
   - The `archive/bug-backlog/<YYYY-MM>/` path is self-indexing — the YAML filenames and frontmatter carry all attribution.
   **Note: last-write-wins hazard.** If two bug-blitz runs overlap they may both attempt to move the same YAML files. Do NOT run concurrent bug-blitzes.
2. **Commit the backlog archive moves** as the final wave, one shared commit via the named op: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/backlog-grind-assemble" apply bug-blitz --wave-path state/bug-backlog/ --wave-path archive/bug-backlog/ --granularity per-wave --message "bug-blitz {run-id}: prune resolved — fixed: <ID1, ID2, ...>, already-fixed: <ID3, ...>, spun-off: <ID4, ...>"`. **The commit subject MUST name every closed ID** (across all three closure shapes). This is the greppable paper trail — `git log --all -- state/bug-backlog/ | grep BS-NNNN` resolves "whatever happened to that bug?" without reading the backlog history. The op re-verifies `$BLITZ_BRANCH` before this commit and halts if it flipped.
3. **If no items closed this run** (all verifications came back blocked / pattern-shifted / nothing fixable), do NOT commit an empty backlog update. Skip to the final report and announce the no-op — that itself is a useful signal that the backlog has reached a state where bug-blitz alone can't make progress and the next step is `/bug-sweep` or `/plan`.
4. **Clean scratch.** Run cleanup only after backlog commit succeeds: remove `state/scratch/bug-blitz/{run-id}/`, tolerating failure with a warning rather than failing the run.
5. **Final report to PM.**

**Report by exception.** Two lines always; everything else appears only when it is *not* clean. A bug-blitz summary is still an EM→PM reply and still owes the ≤200-word budget — a fixed block of per-item sub-bullet lists scales with backlog size and guarantees the all-clean run (the common run) is the maximum-length run. Print what needs a reader or a decision, not what needs a checkbox.

```markdown
## Bug Blitz Complete

**Backlog:** N → M
**Resolved this run:** F items (backlog: Fb, failing tests fixed: Ft)
```

Then append a line **only** if its condition holds:

| Line | Include only when |
|---|---|
| `**Spun off (need plan):**` | S ≥ 1 — list with item ID + handoff path; these need a PM decision |
| `**Re-attempted (still blocked):**` | R ≥ 1 — list with item ID + reason |
| `**Suite gate:**` | the gate ran and did not come back a clean PASS — still-red `<IDs>`, regression-introduced `<IDs>` (name the reverted SHA), or `unconfigured` (remediation: set `fast_test_cmd:` in `coordinator.local.md`) |
| `**Suite noise (not chased):**` | flake/env/timeout counts from baseline are non-zero, with parser evidence; a reproducible flake filed to backlog is named here |

**Negative-spec — these are gone, do not restore them.** `Run: {run-id}` is dropped — the run-id is derivable from the scratch-dir path and the commit trail, and carries no PM decision. `Already-fixed (silent)` is dropped entirely, not demoted to a count — it is a bookkeeping fact about a prior commit, has no PM decision attached, and no reader other than the archive YAML's own `closed_by` field, which already carries the attribution. A clean `Suite gate: PASS` is dropped rather than printed — the gate having run and come back green is already implied by "no `Suite gate:` line" plus the fixed items being committed at wave gate. Their absence is not a signal the step was skipped — the gate and archival directives still run every time, and `git log` / the archived YAML frontmatter are their record. A future reader must not re-add them "for completeness."

## Post-Ship Cleanup

After canonical outputs are committed, delete the working-notes scratch directory (`state/scratch/bug-blitz/<date>-<time>/`). Optionally write a one-line breadcrumb at `state/scratch/bug-blitz/<date>-receipt.txt` referencing the canonical commit SHA. Working notes leaking post-ship as untracked files is noise; commit-then-delete is a two-step waste.

## Failure Modes

| Situation | Action |
|-----------|--------|
| `state/bug-backlog/` missing or empty (zero `.yaml` files) | Do NOT halt — run the (Phase 0.6-gated) test-suite leg if authorized; only short-circuit to green no-op if the suite is also clean. Recommend `/bug-sweep` in the report if the suite was green and the backlog absent. |
| Phase 0.6 authorization declined | Run the backlog leg only; no suite-related work this run; note the decline in the final report. |
| Test command unconfigured (resolver exit 2) | Continue on the backlog leg; report the `unconfigured` remediation (`full_test_cmd:` in `coordinator.local.md`, or `fast_test_cmd:` for fast-tier coverage). Do NOT fabricate a test command. |
| No `full_test_cmd` configured (resolver exit 3) | Run the fast-tier fallback; report coverage honestly as `fast-fallback` with the `set full_test_cmd:` remediation. Do NOT label a fast-fallback run "the entire test suite." |
| `test-evidence-parser` returns text-only (no file) | Re-dispatch with `snippets/text-only-recovery-preamble.md` inlined; on second failure EM runs the suite directly and persists the classification. |
| Suite gate (Phase 4 step 0) still red after one corrective wave | Stop chasing in-wave; leave committed-up-to-last-green; surface residual red tests to PM in the report. Do NOT report green. |
| Fix would weaken a test's assertion to pass | `BLOCKED: assertion-weakening-without-evidence` — never green a test by deleting its check; reclassify (code-bug vs stale-test) with evidence or spin off. |
| Off active workstream branch (not `work/{machine}/{date-or-span}`) | Halt Phase 0 |
| Phase 1 chunk Haiku returns text-only (no file written) | Re-dispatch with `snippets/text-only-recovery-preamble.md` inlined; on second failure, EM persists agent's inline output |
| Executor reports `BLOCKED: pattern-not-as-described` | Update `state/bug-backlog/<id>.yaml` `body` with revised description; do NOT fix anyway |
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

- **`/bug-sweep`** — populates `state/bug-backlog/` (one `<id>.yaml` file per bug). Run periodically; bug-blitz consumes its output.
- **`/mise-en-place`** — for pre-spec'd executor stubs (reviewed-and-sealed plan items). Bug-blitz handles the un-spec'd backlog case where triage is the spec-creation step.
- **`/spinoff`** — convention used by Phase 2.1 to fork big items into pickup-ready handoffs.
- **`/debt-triage`** — separate skill for `state/debt-backlog/` (technical debt, not bugs — directory of per-entry YAML files). Different surface, conversational prioritization.
- **`/validate`** — shares the single-owner resolver CLI, reached through the same `coordinator-resolve-validation-cmd` forwarder in the settings home. `/validate` resolves the **fast** tier (`--fast` / `resolve_fast_test_cmd`) and runs it once, reporting an enum. Bug-blitz resolves the **full** tier (`--full` / `resolve_full_test_cmd`, which falls back to fast with a caveat when no `full_test_cmd` is set), runs it, *chases the failures*, and re-runs as a green-suite gate. Neither inlines its own resolution — the tiers are siblings in one module so they can't diverge.
- **`/learn-lessons`** — if blitz reveals recurring patterns (e.g., 3 different items all flag the same hook bug, or the same test flakes every run), capture the meta-lesson.

## Surface Integration

`/bug-blitz` is wired into the discovery surfaces:

- **`/workstream-start`** — "work the backlog" framing advocates `/bug-blitz` when `state/bug-backlog/` contains ≥10 open P1+P2 `.yaml` files (use `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/query-records" --type bug | wc -l`), OR (independent of backlog depth) a **red-suite predicate** read from `state/test-red/<machine>.yaml` (per-machine shard, a mapping keyed by tier — `fast`, `plugin-ecosystem` — evaluated independently; absent or malformed is skipped silently) — per tier this advocates `/bug-blitz` not on bare redness but on any of: a non-empty `new` delta against the comparison baseline (`acknowledged.baseline` when live and unexpired, else `previous.failing`); `acknowledged` null or voided (on-doubt or on-expiry) with `failing[]` non-empty, **independent of whether `new` is also non-empty**; the acknowledged owner artifact closed/terminal while `failing[]` is still non-empty; or `failing: null` ("red, failing set unavailable"). An acknowledged, unexpired red set whose delta is all-`persistent` advocates nothing.
- **`/workday-start`** — Step 1.65 emits a depth nudge (moderate 10–19, heavy ≥20) before scheduled-rechecks.
- **`/workweek-complete` Step 4** — bug-backlog depth check joins the improvement-queue triage gate; ≥10 open proposes a blitz, otherwise summarised.
- **Coordinator README** — listed adjacent to `/bug-sweep` in the commands table, failure-modes section, and skills section.
