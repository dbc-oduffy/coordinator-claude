---
name: mise-en-place
description: "Autonomous backlog run — flight-recorder prep, then run-through."
allowed-tools: ["Read", "Edit", "Write", "Bash", "Grep", "Glob", "Agent", "Skill"]
argument-hint: "[baton-path [AND baton-path]...] [--hibernate]"
---

# Mise-en-Place — Autonomous Backlog Execution

Flight-record the backlog, then run it straight through — implicit PM authorization, messy parts
included. From Phase 5 on, never pause to ask; stop only for a `pm_only` question (important, urgent, no clear answer; scope, direction and priority go to `coordinator:apm`, code to `coordinator:staff-eng`) or § When to Stop.
Not plan-as-you-go — decisions are made before the run.

**Announce:** "Running /mise-en-place — prepping flight recorder, then straight shot through the
backlog."

## Arguments

| Trigger | Mode | Tail |
|---|---|---|
| none / no explicit hibernate phrase | Standard (default) | per-wave commit+push, no /update-docs |
| `--hibernate` / "hibernate"/"shut down"/"power off" | Hibernate | verify push, then hibernate |

Soft signals ("overnight," "it's late") do not authorize hibernate. Default standard; never ask.

## Phase 0a: Baton Intake

`/pickup`'s auto-fire claims batons on the invocation line — **check that it did, don't assume
it.** No claimed-baton list in `additionalContext` means the hook did not fire, and its bootstrap
fails OPEN: a missing or unresolved script produces silence, not an error, so a run that skipped
this phase's engine inputs reads exactly like one that had them. Claim by hand
(`pickup-assemble apply <path>`), say so in the announcement, and carry on. Then resolve open judgment points and claim residue. Not ready → `pickup-assemble drop <path>`;
readiness-routed but still coherent → keep the claim, name routed items in the Phase 1 ledger and
the successor handoff. No brief → `pickup-assemble brief <path> [AND <path>]...`. Announce:
"Claimed N batons: [paths]. [M put back down: reason.]" Detail: wiki.

**Aggregate execution baton** (a baton carrying an `aggregate_execution` block): read the roll-up,
never infer it — `python3 "${CLAUDE_PLUGIN_ROOT:-${_content_root}/coordinator}/skills/pickup/aggregate-rollup.py" <baton>`. `FIRE` (exit 0)
fires every constituent; `PARTIAL-FIRE` (exit 1) fires the named subset, and its `excluded` and
`withheld` rows enter the Phase 1 inventory as items with a named non-terminal disposition;
`NO-FIRE` (exit 2) fires nothing — put the baton back down. **Exit 1 is a membership fact, not an
error**, and a PARTIAL-FIRE forces CONTINUANCE at Phase 6: a partial fire that reads as completion
is the drop this shape exists to stop. Contract: wiki.

## Resolving the scripts this ceremony runs

These live in the doctrine repo's `setup/doe-tools/` or the engine's `coordinator/bin/` and get no settings-home launcher, so
rung 2 404s. Open every fence below with the fence in
`snippets/resolve-coordinator-bin.md` § CLIs with no launcher (`_content_root` does not survive between Bash calls).

## Phase 0: Readiness Gate

**Stranded-run sweep — before anything else on a resume.** For each emitted
`state/mise-inventory/*.workflow.mjs` whose run has no completion receipt (its run died: usage limit,
container reclaim): settled waves are already landed by their wave commits. A run that reached review lands through
`dispatch.terminal_commit` with `script_path` and `task_output_path` (the digest carries
`inline_review`). One that died before review: same session, resume with `resumeFromRunId`; new
session, land its DONE rows with `emit-dispatch-workflow --inventory <inv> --review-only --rows <ids>
--run-base <sha>` (fire it; its digest yields the `terminal_commit_cli` line), then re-emit the
rest with `--only-incomplete` (a plan) or `--resume-from <run-id>-continuance.md` (an inventory). Never hand-stage a dead run's files. `a-dead-run-strands-its-done-rows-uncommitted`.

**Certification leg — runs first, and the bypass below does not reach it.** Plan-sourced items
only; an item with no plan has nothing to certify and is not refused for it. One command runs it:
`<settings-home>/bin/mise-certify <plan>... --json` prints each plan's state, then the census; a
nonzero exit means STALE, MALFORMED or DRIFT. One revalidation step, two ordered legs: recompute the plan body sha against `mise_prepped_sha` (pure, spawn-free);
only if that passes, re-run each `census[].command` and diff against `result`. Fire on sha-leg
CERTIFIED with no entry-level census DRIFT; an unclosed census leg (`UNDECIDABLE` / `REFUSED` /
`UNRUNNABLE`, per-entry or rolled up) does not block the fire — record it as a named,
non-blocking finding in the Phase 1 ledger. STALE → re-gate (`<settings-home>/bin/mise-prep-gate <plan>`, `<settings-home>` resolved per `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`), then re-stamp;
UNSTAMPED → gate and stamp; MALFORMED → a hand-written stamp, repair the frontmatter; census
drift → the premise moved, re-plan — unless format-only (same value, different formatting) or caused by the plan's own landed rows: the EM records entry and reason as a Phase 1 ledger finding and fires. **Name the state** — "not certified" sends an author to the
wrong repair. A handoff can assert executability; it cannot assert a sha. States, recipe and the
four repairs: `coordinator/docs/wiki/lesson-triage/mise-prepped-attest.md`.

`mise-certify` also runs the seam leg over the fire set: `SEAM-REFUSED` is a named state beside
those, repaired by routing the finding and re-prepping the set. `capabilities-undeclared` blocks
here and its repair is the `capabilities` frontmatter key (no re-stamp). Detail:
`coordinator/docs/wiki/lesson-triage/mise-seam-check.md`.

Bypass only if the invoking handoff asserts **executability** (not merely pickup-readiness) for
the named items in its body — a stated stop condition or `deployment_state: awaiting_gate` always
wins. Uncertain → don't bypass.

Otherwise, gate every item before Phase 1:

| # | Criterion |
|---|---|
| 1 | Decisions made — AC explicit/verifiable; unwritten detail is fine, an undecided fork is not |
| 2 | Downstream contracts sequenced — decided-but-unbuilt legal, undecided is not |
| 3 | Pure-executor — a Sonnet/inline executor alone can finish it |
| 4 | Footprint declarable and data-reachable at dispatch time |
| 5 | Verification mechanical — checkable, not "looks right" |

Failing item → route out with a named reason, run the rest; decline the whole run only if the
residue isn't coherent or routing needs a `pm_only` call. Patterns/examples: wiki.

## Phase 1: Inventory

`backlog-grind-assemble brief mise-en-place --run-id <run-id>` computes the empty-backlog judgment
point and the `d-mise-executor-dispatch-prompt-template` directive; not Phase 0.

Quote the `additionalContext`-minted run-id (`backlog-grind-assemble mint-run-id mise-en-place`
if the hook didn't fire on either entry path — typed `UserPromptExpansion` or a model-invoked
`Skill` call through the `preuse-skill-dispatch.py` fan-in). **`mint-run-id` is a subcommand of
`backlog-grind-assemble`, never a CLI of its own** — no launcher carries that name, so the bare
verb exits 127. If two engine-minted run ids are in context, use the first.
Capture `git rev-parse HEAD` as start SHA before dispatching.

>3 items → backgrounded Sonnet scout writes `state/mise-inventory/<run-id>.md` (frontmatter
`run_id`, `start_sha`; one row/item under a literal `## Chunk table` heading, first column named
exactly `id`, then: spec path | summary | footprint | deps | verification | complexity |
disposition), sourced from `tasks/*/todo.md`, enriched stubs,
`$ARGUMENTS`, claimed batons — not `tasks/`. `disposition` updates every wave gate: a live row
reads `pending`, `queued` or `in_progress`; a terminal one opens with a § Phase 6 verb. ≤3 items
already read → inline instead. Template/sources: wiki.

**Chunk-table grammar** (the emitter refuses anything else, naming the row):
- `disposition`: live `pending` / `queued` / `in_progress`; withheld `routed-out: <reason>`; closed
  `already-fixed`, `landed`, `dropped`. `deferred` is refused — write `routed-out: <reason>`.
- `footprint`: backticked repo-relative file paths. A directory whose filenames are minted at run
  time is written ``writes_under: `dir/` ``; a bare directory or glob is refused.
- `deps`: row ids of this table, never a plan's own chunk ids (a plan row expands into
  `<item-id>.<chunk-id>` chunks).
- A plan needing another same-repo plan's chunk declares `depends_on_plan: [{plan, chunk,
  gate_kind}]` on its spine row. The emitter withholds the row (and its dependents) until that
  chunk is `coded`; inside one inventory the dependent waits for the next run. A missing plan,
  unknown chunk, `..` path or terminal non-coded predecessor stops the emit.
- The inventory lives under `<repo>/state/mise-inventory/`; one outside it is refused.
- Emitted script over 524288 bytes: the emitter splits the inventory into whole-plan parts, run ids
  `<run>-pN`, scripts `<out>-pN.workflow.mjs`. The EM fires each part; `--fire` refuses a split.
  Detail: wiki.

## Pre-Dispatch Verification

The emitted Workflow runs it ahead of Execute on every emit (Haiku, per item, `still-open` vs
`already-fixed` at HEAD) and drops `already-fixed` rows; the digest lists them under
`predispatch.already_done`. The EM runs no separate pass.

**Falsifier integrity is the emitted Workflow's own phase, not an EM pass.** The inventory emit
reviews every plan whose frontmatter carries `prime_exit_criterion.falsifier`, writing each
can-report-red report itself; the EM runs no review, hand-sent or Workflow, before firing — a
second pass is a second sample of the same non-deterministic reader, and the two disagree.
Verdict `SOUND` | `BROKEN` | `UNREVIEWABLE`, naming the tell; it reports and never refuses. The reviewer stays on Sonnet: a cheaper reader fails toward a false `SOUND`, which lets the judge self-stamp; cost is a per-plan verdict cache's job, never a tier cut.
**`BROKEN` is advisory, never a route-out:** the plan executes, and its terminal judge may not
self-stamp `implemented` (the task output's `next_action.params.falsifier_broken` names it) —
close-out goes through the re-judge route in
`coordinator/docs/wiki/reviewer-pipeline/terminal-judge.md`. A weak falsifier costs the run its
self-stamp, not its execution. Inputs and the blinding invariant:
`coordinator/docs/wiki/reviewer-pipeline/falsifier-integrity.md`.

## Phase 2: Sequence and Parallelize

Max concurrency, zero overlap within a wave. Sort by dependency then size. Footprint =
write-targets from the spec (stub `touches:` overrides a cached README graph; a consumer-layer
item's data source is part of its footprint). Wave 1 = no deps/overlap; Wave N = depends on or
overlaps earlier. All-overlap → N waves of 1, fine. N-plan convergence and risk-flagging: wiki. No
worktrees, ever.

## Phase 3: Flight Recorder

`TaskCreate`: goal task (item list, tail mode); per-item task (id, spec path, wave, footprint,
verification, `pending`, empty `tried_and_abandoned`); hibernate-only tail tasks ("Verify pushes,"
"Hibernate PC").

<!-- BEGIN task-tool-availability (synced from snippets/task-tool-availability.md) -->
`TaskCreate` absent from this session's surface
(`ToolSearch("select:TaskCreate")` returns nothing) → fall back to `coordinator-tasks-mirror` for
the same flight-recorder role; do not assume either state without checking. When Task* is
unavailable, dispatch the phases in order, waiting on each completion notification — that is the
ordering a `blockedBy` chain would otherwise express.
<!-- END task-tool-availability -->

Update `tried_and_abandoned` before any new approach; read it back after compaction before retrying
anything.

## Phase 4: Confirm and Fire

Output, then start Phase 5 immediately:

```
## Mise-en-Place — Ready to Fire

**Items queued:** [N items] across [M waves]
**Wave 1** (parallel): [items] — file-disjoint ✓
**Wave 2** (parallel): [items] — depends on Wave 1
**Aggregate:** [FIRE | PARTIAL-FIRE, N of M plans — excluded: [plan (state)]; withheld: [plan rows]]
**Risks:** [...]
**Tail:** [standard | hibernate line]
**Estimated scope:** [...]

Proceeding.
```

## Phase 5: Execute

Default: ONE background Workflow for the whole run, carrying the Phase 2 DAG across every wave —
executors, verifiers, and the one terminal commit alike. `model: 'sonnet'` on every `agent()` whose `subagent_type` is UNPINNED — never alongside a
`coordinator:*` type, which pins its own tier and whose pin guard refuses the override.
Width is the spine's DAG; admission is by measured load
(`coordinator_core/ops/dispatch_emit/admission.py :: await_admission`), not a count. **No
hand-dispatch, and no single-wave carve-out:** manual
`Agent` calls spend EM context, which is the binding constraint in a mise run, and "only one wave"
is not a shape a Workflow cannot express. Verifiers ride inside the Workflow — call
`provision-sidecar --agent-type <type>` for any phase whose `report_type_map` row is not
`run-report`.

**Pre-fire anchor.** Primary cwd outside the target repo (a managed-remote container starts at
the repos' common parent) → `cd <abs repoRoot>` as its own standalone Bash call, and confirm the
harness reports the new primary directory before firing.
`A-CD-OUT-OF-A-REPO-DISARMS-EVERY-DISPATCHED-COMMIT-FOR-THE-SESSION`.

Don't hand-author the script — mint and emit:
`COORDINATOR_AGENT_TYPE_HOST=coordinator <settings-home>/bin/emit-dispatch-workflow --inventory state/mise-inventory/<run-id>.md --out state/mise-inventory/<run-id>.workflow.mjs --repo-root <abs repo>`
(resolve `<settings-home>` per `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`; `COORDINATOR_AGENT_TYPE_HOST=coordinator` is a runtime input to the emitter and must be set in the invocation's environment on every host)
writes the spine (item-id → chunk-id, footprint → `writes`) plus the `.mjs`; fire it with the
`Workflow({scriptPath, args: {repoRoot}})` call the emitter prints on stderr. An inventory row whose
spec path is itself a plan carrying a `` ```yaml plan-tasks `` spine expands into that plan's own
chunk DAG — `<item-id>.<chunk-id>` per chunk — inside this SAME emitted Workflow, never a second
`--plan` emit; a plain row with no such spine stays one executor.

**Tranche step.** One inventory does not run a cross-plan DAG in one go: `depends_on_plan`
dependents wait for the next run, so a set with plan-to-plan chains runs as successive tranches.
The EM chooses how aggressive each tranche is and what it includes: emit the combined inventory
with `--row-budget N` (N ≤ 100), trimming the inventory first to leave plans out. The emitter takes
plans whose `depends_on_plan` predecessors are `coded`, keeps same-path writers together, writes
`<inventory>-t<N>.md` and reports `tranche.deferred`, `skipped` and `remaining.passes_remaining`.
Fire it; after it lands, emit the next. `a-cross-plan-mise-set-runs-as-tranches`.

**Ignore the Stop-hook's "commit and push" advisory mid-run** — the dirt it flags is a live
wave's footprint. Commit only by § Who commits; never widen it to satisfy the hook.
A path still held dirty after the run drains, because landing it asserts what only the PM can, gets
a committed withhold record; the hook does not
read it yet, so its advisory on that path is expected and is not an instruction.

**Who commits.** When a wave settles, one `coordinator:git-commit-agent` leg commits the union of
that wave's DONE rows via `ceremony.commit_v2`; the next wave does not wait (wave commits chain only
among themselves), and a wave with no DONE rows emits no leg. A failed wave commit is named at run
end. After each landed wave commit a non-awaited `git push origin HEAD:refs/heads/<branch>` follows
(never forced, one ref, no retry; skipped on main/master/detached HEAD; failures named in the final
log line). The EM's `dispatch.terminal_commit` still lands receipts, review stamps, `coded` flips,
prefix-claimed files and rows declaring over 20 paths — scoped (`snippets/scoped-commit-route.md`),
never the wave union, never `git add -A`.

**Halt routing.** A chunk whose stop rule fires, or that returns `decision_required`, halts its
plan. Move that plan's row to `## Withheld / routed out` with the reason, re-emit with `--force`,
and resume with `resumeFromRunId` of the same run so finished agents replay from cache.
Across sessions, `emit-dispatch-workflow --resume-from <run-id>-continuance.md --out
<run-id>.workflow.mjs` re-emits each lane without the rows already `coded`; an empty lane reports
`nothing_unlanded`.

`SEAM-DRIFT` at a wave boundary holds the implicated plans' rows inside the Workflow; move those
plans to `## Withheld / routed out` with the finding and the run continues. Never override it by
re-emitting with `--force`; `capabilities-undeclared` is reported there and holds nothing.
`coordinator/docs/wiki/lesson-triage/mise-seam-check.md`.

**Resume admitted by the classifier.** Check and allowlist edits land in their own earlier commit.
State the resume as resuming this run's own workflow (`resumeFromRunId` of the run just fired),
never as a follow-on to a check change. Tripwire:
`A-RESUME-RIDING-A-CHECK-EDIT-IS-DENIED-AS-CI-BYPASS`.

**Limit deaths.** An executor reply opening "You've hit your … limit" is a usage-limit death, not
a chunk failure and not a halt. Do not route the plan out or re-dispatch by hand: wait for the
reset, then resume with `resumeFromRunId` (same session) or `--resume-from` (new session). It is
identified by that text plus `tool_uses=0`. `coordinator/docs/wiki/skills-corpus/usage-limit-pause.md`.

**Classifier-blocked residue.** When the auto-mode classifier denies an executor's revert of its
own mistaken files, the EM does not revert them in its place (permission laundering). Leave the
paths out of every commit, record them as residue in the continuance or tail record, and file a
`state/bug-backlog/` row naming them for the PM.

**Then stay awake while it runs — on a managed-remote host, ending the turn to wait kills the
run** (the container is reclaimed on inactivity; `resumeFromRunId` is same-session-only). Hold the
turn with a `Monitor` on a poll interval, re-armed at expiry; checkpoint pushes land per row. File/commit
counts cannot see a stall; size the Monitor per `[[a-compaction-can-kill-a-background-workflow]]`,
and check for a compaction kill after any `/compact`. Detail: wiki.
`a-quiet-session-gets-its-container-reclaimed-under-running-work`,
`A-COMPACTION-CAN-KILL-A-BACKGROUND-WORKFLOW`.

**The env var is not optional, and omitting it does not fail — it downgrades.** The script probes
for a plugin root to decide whether `coordinator:*` agent types resolve, and a Bash subprocess
carries neither `CLAUDE_PLUGIN_ROOT` nor a roster, so it degrades every `coordinator:executor`,
`git-commit-agent` and `test-runner` in the run to `general-purpose` — no do-not-commit snippet,
no pathspec discipline, no sandbox preamble — and says so in one stderr line. Assert it. Pass
`host` instead if your roster genuinely lacks the `coordinator:*` types, never to silence the
narration. In PowerShell set `$env:COORDINATOR_AGENT_TYPE_HOST = "coordinator"` first. It reads the `## Chunk table` heading and its `id`
column and nothing else — both names are literal, and a record spelling either differently is
refused, not guessed at. It refuses too on an unrecognized disposition or a footprint naming no
backticked path — fix the record, don't work around it. Both artifacts archive with the record.

Enable the sentinel first: `misc-session-and-guards autonomous-sentinel enable --mode
mise-en-place` (disable at Phase 6). Executors always background; only the EM commits, once per
wave, from the DONE summary — never the transcript.

Per wave:
1. Mark `in_progress`, tracker-sweep the item (wiki). The Workflow's executor phase carries each
   item's spec, footprint, and the executor **return** contract — done-summary path, touched-files
   set, self-verify constraint — in its emitted row prompt. The brief surfaces that same contract
   as `d-mise-executor-dispatch-prompt-template`; the two are rendered from one definition, not
   passed from one to the other, so reading it in the brief is not what puts it on an executor.
   The wave gate's pathspec and the verifier's first evidence source both read what it produces. Never a hand-rolled `Agent` call to attach
   them: a run that drops the contract reports narrative where the committer needs paths
   (`AN-ORPHANED-RETURN-CONTRACT-IS-A-DROPPED-ONE`).

<!-- engine-gap: field=tracker_sweep.item_state producer=unknown memo=2026-08-27-claude-klabauter-em-doe-unmarked-obligations-and-four-lost-markers.md -->
2. On DONE (verify via disk — DONE path + `dirty-tree-gate --terminator mise-item-done`, which
   classifies every dirty path as session-authored, known-peer, or unattributable rather than a
   hand-parsed status line; never trust idle-alone; never double-dispatch onto a live footprint):
   the Workflow's verifier phase runs a Haiku verifier per
   item from the brief's `d-mise-haiku-verifier-dispatch` fields. Batch per wave; gate on all-`PASS`.
   Non-PASS → re-dispatch, revert+re-plan, defer, or early-stop. **Peers write concurrently to
   this same checkout — footprint verification is scoped to the item's own declared paths.** A
   bare unscoped status/diff read shows every live peer's work; a path outside the item's
   declared footprint is another item's and is not evidence about this one.

   **Partial wave landing** — some items landed, some did not. Commit the PASSed items' footprint
   paths only, never the wave's union; an unlanded item returns to `pending` with
   `tried_and_abandoned` updated, and the wave is not announced complete. Reverting an unlanded
   item's residue is scoped to that item's own declared footprint paths — never a bare
   `git checkout`/`git clean`, which reaches a peer's work. Unlanded items are non-terminal, so
   the run's verdict is CONTINUANCE.
3. Wave gate: the wave's DONE rows are committed once by § Who commits; the EM's terminal commit
   covers what the wave commits do not. Verify the expected branch read-only before committing;
   `ceremony.commit_v2` or a plain scoped `git commit -- <paths>` is the whole allow surface. No
   ledger call — `commit_v2` writes the row itself, so adding one duplicates it.
   Bookkeeping stays EM-side, outside the Workflow: `backlog-grind-assemble apply mise-en-place
   --run-id <id>` with **no** `--wave-path` (that form builds no commit directive).

   **A partial wave still commits, and the pathspec comes from the reports, not the wave.** The
   wave's declared union is INTENT — it names what the wave set out to write; the DONE executors'
   reports are the CLAIM. Derive the pathspec from the reports and commit it. A blocked or
   non-`PASS` item contributes no paths and blocks nothing: its chunk id drops out of the subject
   alongside its paths, and § Partial wave landing above governs the rest. **Refusing to commit
   because one item of N is blocked is the failure mode, not the safe choice** — it strands every
   other executor's work uncommitted.

   **Peer-session commit collision**, checked before the commit:
   `git log <wave-dispatch-sha>..HEAD --name-only -- <this wave's footprint paths>`. Non-empty
   means a peer landed **inside** this wave's footprint (distinct from the churn in § When to
   Stop, which lands outside it): re-dispatch the verifier over the merged state for the colliding
   items only; still-`PASS` commits, non-`PASS` routes out with the collision named. **Never
   revert, rebase, amend or force-push over the peer's commit.**
4. "Wave N complete ([items]). Firing wave N+1 ([items])." — never a question.

No worktrees.

## Phase 6: Tail

Mark tasks `completed`, disable the sentinel, then in order: subtractive adjudication, exhaustion
check, anti-vacuity gate, diff freeze, inventory archival (COMPLETE only), tracker sweep.

- **Subtractive adjudication** — the terminal pass over what the review layer added, run before
  the exhaustion check because its coverage feeds it. Build the revocation candidate ledger from
  **review-layer artifacts in this run's own sha range only** — integrator disposition blocks
  bucketed `applied`/`deferred` and their reviewer sidecars, keyed `<sidecar-stem>#finding-N`,
  each stamped `costRank` by the size of the integrated change. **The ledger is the address
  space**: sourcing it from the run diff or an executor report widens the adjudicator's authority
  silently, which is the thing to check in review, not its wording. Empty ledger →
  `NO-CANDIDATES`, no dispatch, recorded — a `/mise` run runs no review of its own, so empty is
  the ordinary reading. Non-empty → one `subtractive-adjudicator` dispatch, then land its return
  under the seven landing rules in the wiki. Every candidate — revoked, accepted, refused,
  unadjudicated — lands in `state/mise-inventory/<run-id>-adjudication.md`. Any `unadjudicated`
  candidate makes the phase INCOMPLETE, and the verdict line may not read COMPLETE while it is.
  Enforcement detail: `coordinator/docs/wiki/test-design-discipline/subtractive-adjudication.md`.
- **Exhaustion check** (live disposition ledger): COMPLETE if every item terminal
  (PASSed/routed-out/already-fixed/dropped), else CONTINUANCE — wording only, tail always runs
  full. Three inputs force CONTINUANCE regardless of the item ledger: an aggregate PARTIAL-FIRE
  (its excluded plans ride a successor, so they are not terminal), an unlanded item from a partial
  wave, and an INCOMPLETE adjudication. CONTINUANCE → `state/mise-inventory/<run-id>-continuance.md`
  naming the resume invocation, a Phase-0-bypass assertion, the wave map — committed+pushed before
  hibernating. That record IS the discharge; `/handoff` is keyword-gated, so it is the PM's
  follow-up, and the tail summary names it as such.
- **Anti-vacuity:** scoped `git status --porcelain -- <this run's footprint paths>`, never bare
  unscoped. Non-empty → repair via the wave-commit op before freezing.
- **Review routing:** no review gate of its own (PM ruling). Freeze:
  `freeze-review-diff --range "<start-sha>..HEAD" --slice-id "mise-<run-id>"`; name
  `/workstream-complete` or a review-and-cap `/handoff` in the tail summary. An aggregate baton's
  membership inherits this discharge unchanged — the obligation is keyed on the diff range, which
  every constituent lands inside; `/workstream-complete`'s chain diff covers a different object
  and is untouched. **The frozen diff and its `.head.sha` (`state/review-trail/`) and executor
  evidence (`.coordinator-local/plan-sidecars/`) are gitignored by design — absence from the commit is EXPECTED
  and is not a missing step.** An item can legitimately go DONE while its sidecar record contributes nothing to the
  wave commit, so DONE is never inferred from commit contents. Tripwire:
  `A-GITIGNORED-DELIVERABLE-IS-INVISIBLE-TO-EVERY-COMMIT-BASED-READER`.
- **Orphan check**, on that same range and inside this phase, never a mechanism of its own: read
  the `.diff` file § Review routing just froze — a plain unified diff, not `--name-status` — and
  take the added paths (each `--- /dev/null` / `new file mode` hunk) off it (never a fresh raw
  diff re-run — the freeze already materialized this range to disk one bullet above), intersect with
  the run's declared `writes:`, and ask of each whether any other file in the tree references it.
  Zero
  referencers → **ORPHAN-CANDIDATE**, named in the tail summary with its path. Necessary, not
  sufficient, never a correctness verdict; it gates nothing and never moves the verdict line.
- **End-of-run verification:** run every test file the cumulative diff touched, once, EM-only,
  naming each path literally. Never the repo's fast- or full-suite command — the suite guard
  refuses it without a PM grant; say which files you ran instead.
- **Tracker sweep:** final pass, same procedure as the per-wave sweep (wiki); commit
  (`--message "mise: tracker sync"`).
- **Baton disposition (whenever Phase 0a ran):** the terminal commit (or the inventory-run op) writes a receipt per Phase 0a baton; the tail lists each path and verdict. No receipt, or live status left, is a **defect**: report, never hand-write. Unstarted → `pickup-assemble drop <path>`; mid-stream → `/handoff`. `coordinator/docs/wiki/release-and-distribution/completion-receipts.md`.
- **Verdict line** reads exactly `COMPLETE` or `CONTINUANCE` — never a bare "done."
  The run-level verdict line MUST read exactly COMPLETE or CONTINUANCE; the word 'complete'
  may not appear as the run's disposition unless the exhaustion check passed. Item-level,
  wave-level and task-level uses of 'completed' (TaskUpdate, tracker sweep, baton
  disposition) are unaffected.
- **Composite disclaimer, once, beside the verdict.** Four instruments feed this line and each
  is honest alone: `mise_prepped_*` certifies a defect-class floor and attests nothing about
  completion; the orphan check is necessary-not-sufficient; an all-`accept` adjudication is a
  null result; the seam check reads declared paths and capabilities, not behaviour. Nothing
  composes them, so a reader seeing `COMPLETE` from a run that was prepped, orphan-checked,
  adjudicated and seam-checked reads a strong claim no constituent makes. Print the
  composition, not four caveats in four contracts nobody reads together:
  `COMPLETE — entry floor certified, no orphan found, nothing revoked, seam check clean. None of
  the four is a correctness verdict.`

**Close:** scoped footprint clean, commit residue, report the verdict, discharge review routing.
Standard stops there. Hibernate additionally verifies+pushes (never on push failure), authors+
pushes the CONTINUANCE record first if applicable, then `shutdown /h` / `systemctl hibernate`.

Never merge to main; never worktrees, any phase. Full mechanics for every bullet above: wiki.

## When to Stop

**Do NOT stop for:**
- Routine fixable errors — fix and continue.
- Minor ambiguity resolvable with one judgment call — make the call, note it.
- A single item being harder than expected — push through.
- Wanting to "check in" — the PM authorized the full run.
- **Agent recovery** (rate-limited/crashed agents, auth failures, uncommitted disk state left by a
  stalled executor, missing subsystem registrations) — routine operational handling. Re-dispatch,
  audit what's on disk, finish the work; recovery IS the work the PM authorized, and asking
  whether to finish tractable, scoped, roadmap-aligned work is a failure of the role.
- **Concurrent-session churn** (another session's commits sweeping staged changes, attribution
  splits, shared-file merges) — the ordinary agree-case, closed per `snippets/scoped-commit-route.md`.
  Then continue.
- **Subsystem registration gaps** — a handler on disk but unregistered in `Subsystem.h`/`.cpp` is
  a routine finish-the-work case, not a PM question.

Full worked rationale for each: wiki. Context exhaustion with backlog remaining is non-failure:
run the full Phase 6 tail, take CONTINUANCE.

**Stop when the usage-limit advisory has fired.** Fire nothing new, let in-flight fires land, run
the Phase 6 tail and take CONTINUANCE with the advisory's reset time in the baton's next steps. An
agent's rate-limit error is recovered; the account's threshold advisory ends the run cleanly. See
`coordinator/docs/wiki/skills-corpus/usage-limit-pause.md`,
`A-DRIVER-PAST-ITS-USAGE-THRESHOLD-FIRES-NOTHING-NEW`.

| Situation | Action |
|---|---|
| Ambiguous spec / scope far larger / breaking change / 2+ workaround pattern / structural verification failure | Stop early: commit current work, update tasks/plan status, verify pushed, hibernate anyway if invoked |
| Fixable verification error | Fix and continue |
| Executor BLOCKED | Spec-fixable → update+re-dispatch; architectural → stop early |
| Executor wrote outside its footprint | Revert, re-analyze overlap, adjust waves, re-execute |
| Peer commit landed INSIDE this wave's footprint (a collision, not churn) | Re-verify the merged state for the colliding items; PASS commits, non-PASS routes out. Never revert the peer's commit |
| Wave landed partially | Commit the PASSed items' paths only; unlanded items return to `pending`; verdict is CONTINUANCE |
| Push fails before hibernate | Do NOT hibernate — stop and report |
| Compacted mid-run | Re-orient via TaskList/TaskGet; check `tried_and_abandoned`; resume `in_progress` |

## Relationship to Other Commands

`/fire-and-forget` is a separate ceremony that fires a whole sizing-to-commit run and does not
enter this body; the engine vocabulary here (sentinel mode, the cadence passed to `mint-run-id`/`brief`,
`handoff.schema.json`'s cadence key) stays `mise-en-place`.

`/update-docs`, `/workday-complete`, `/merging-to-main` are PM-run afterward, never auto-invoked.
`/autonomous` composes with this run: it governs the unattended posture (sentinel, nudge
suppression), this command governs the backlog sequence — the sentinel is enabled here with
`--mode mise-en-place` precisely so a reader can tell a `/mise` run's sentinel from an
`/autonomous` one.
`pipelines/mise-en-place/PIPELINE.md` carries this sequence at greater depth, where shipped.
