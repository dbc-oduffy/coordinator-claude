---
name: learn-lessons
description: "Process lessons/ entries as doctrine change-requests."
version: 1.0.0
allowed-tools: ["Read","Write","Edit","Bash","Grep","Glob","Agent","Skill","AskUserQuestion","TaskCreate","TaskUpdate","TaskGet","TaskList"]
---

# learn-lessons — Lesson Processing and Queue Activation

`learn-lessons` runs the `lessons` family of queue-grind profiles over `state/lessons/*.yaml` (and
`state/lessons-outbox/` in central mode) as change-requests against doctrine, agent prompts, hooks,
scripts, wiki guides, and improvement queues — one destination + change-kind per lesson. Success
metric: did doctrine and queues evolve, not did the file shrink. **Supersedes
`coordinator:lesson-triage`.** Taxonomy, change-kind apply dispatch, promotion-sprint procedure and
phase mechanics: wiki.

**Grinder defaults**: script-first triage
folds duplicate lessons and closes already-applied ones before an agent sees a lesson; every run
carries a default budget passed as `budget_tokens`; the EM reads 25/50/75% checkpoints at its next
turn; each applied lesson lands as a scoped commit per green row.

**Every coordinator CLI named on this page is engine-homed and has a settings-home launcher** —
resolve each by absolute path per `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md` (Shape W on a PowerShell
host, Shape A/B on POSIX). Never a bareword, and never `coordinator/bin/<cli>.py` cwd-relative:
this skill runs with cwd set to the consuming repo, where that path does not exist.

**Announce:** "I'm using the coordinator:learn-lessons skill in `<mode>` mode." Mode default: cwd
`~/.claude` central → `central`; else `local`; PM can override.

## Pre-dispatch

Freshness is a standing invariant (`A-FRESHNESS-THE-OPERATOR-MUST-REMEMBER-IS-NOT-MAINTAINED`).
Before dispatching, run every check registered for `learn-lessons` in
`coordinator/skill-preconditions.yaml` and state each verdict in every dispatched brief. Stale or
missing: the entry's `on_stale` applies (`queue` = one line in the brief and the report, never a
reindex).

## Hard Rules (not engine-enforced)

- **Actor split.** The run's committer stage commits the run's fixes and closes. The EM commits
  everything outside a run: post-run promotes and `promoted_to` stamps, baton minting, `pm_decision`
  writes, and the run stamp. A dispatched lead never commits.
- **No-defer.** A `wiki-append`/`wiki-new` record with a named destination applies THIS run.
  Legitimate deferrals: a structurally-required cross-mode block (e.g. `strip-local` before its
  central commit SHA lands), or a record awaiting an adjudicator verdict.
- **Wikis are the default destination.** `doctrine-edit`/`memory-pointer` are doctrine-plane-only
  — a worker NEVER emits either; downgrade to `wiki-*` + `doe_escalation: true` before the record
  reaches the EM's `pm_decision` write.
- **Extraction never runs through an LLM** (`extract-lessons` — a parse); routing judgment can,
  behind the verify gate.
- **Mechanical-contract lessons need an executable witness** (test, live behavior, official docs)
  — discard if none or one contradicts the claim.
- **Domain-looking universals default to `retag-local`**, never a blind `[universal]` string replace.
- **A `wiki-append`/`wiki-new` target must be reachable** from a real traversal surface (index,
  skill step, dispatch preamble) — not merely exist.
- **Local mode auto-applies** `discard`/`wiki-append`/`retag-local`/dedupe/age-sweep plus tradeoff-free `agent-prompt-edit`, `hook-edit`, `script-edit`, `snippet-sync-update`, `project-structural` rows below plan weight; `doctrine-edit`, `memory-pointer`, `doe_escalation` and product/taste rows go to an adjudicator agent, never the PM.
- **No lesson or distill decision goes to the PM.** Central mode: the EM writes `pm_decision` itself
  from the route run's verify verdict — pass → `apply`; refuted twice as already covered →
  `reject`; any other refutation or `needs-judgment` → an adjudicator agent rules `apply`/`defer`/`reject`.
  Per-cluster allowed. The field name is historical; the EM is its sole writer.
- **A strip run follows the apply run it cites** — no row strips before its central commit exists.
- **Fail-close:** a strip-list id with no routed sibling record blocks the `COMPLETE` sentinel — the EM re-runs the route or apply run for it.
- **Universals-pending is a post-run count, not a pre-run stop:** a local run hands back `route-to-central`; surface ≥ 20 in the Phase 8 report with a central-run recommendation.
- **Never fabricate a routing `id`**, and never hand-correct a router's output — re-dispatch it.
- **An emit refusal is reported, not routed around.**

## Phase Flow (invocation pointers — mechanics: wiki)

Central flows: `coordinator_core.learn_lessons_pipeline`'s `apply` entrypoint emits the Phase 8
`COMPLETE` stamp as an engine directive — read it from the fired decision object, never derive it by
hand. The local flow reads no engine brief and no roots op.

Discovery: the target repo's own `state/lessons`. **Candidates come from the
changelog-first triage `/distill` runs, never a whole-queue model read:** the weekly changelog,
then the condensed daily logs for changes flagged impactful; only the batons joined to those
changes' plans by `deliverable_id` are lifted, each `## What I Learned` bullet a candidate lesson,
never an auto-promote. The since-last-run set is `project-rag doc-delta --json --since <watermark>`, ripeness `doc-corpus-digest`, clusters `doc-topic-groups` one `--group <id>` or `--cursor` page at a time, never a full walk (CLI resolved through `machine-local get repos.project_rag`; exit 3 is a named `no-producer` line, never a git or frontmatter scan). Cluster and dedupe model-free, one synthesis per topic; spend counts against
`whole_backlog_token_bar` in `coordinator/contract/ceremony-budget.json`, one run a `slice`.
Script first, bounded previews (at most ~10k chars per plan), never a fan-out over the whole corpus.

One flow per run kind, each `pre-run directives → emit → fire → consume hand-back → post-run
directive`:

- **local:** `prepare -> triage workflow -> finalize -> bounded grind`; the driver is
  `coordinator/pipelines/learn-lessons/lessons_mechanical.py`, contract and CLI in
  `coordinator/pipelines/learn-lessons/PIPELINE.md`, no agent before the triage workflow.
  (1) `lessons_mechanical.py prepare --repo-root <repo> --run-dir <run_dir>` runs the age-sweep and
  mechanical dispositions (rows missing a required field are reported `malformed`, never triaged), packs the residue into `<run_dir>/prepared.json`. (2) Fire
  `Workflow({scriptPath: coordinator/pipelines/learn-lessons/lessons-triage.workflow.js, args:
  {prepared, budget_tokens}})` with the parsed `prepared.json` and the default budget; save its
  `synth_results` and `budget_ledger` as `<run_dir>/synth-results.json` and
  `<run_dir>/budget-ledger.json`. (3) `lessons_mechanical.py finalize --run-dir <run_dir>` applies
  refute-upheld verdicts and reports `residue_for_grind` and `remaining_budget`. Empty residue: skip
  the grind, go to the Phase 8 report. Non-empty: emit `emit-dispatch-workflow --queue state/lessons
  --profile lessons --appetite standard --out <repo scratch dir>/<run>.workflow.mjs --repo
  <target repo>` over that residue only and fire with the `Workflow({scriptPath, args})` call it
  prints, never `--fire`, passing `budget_tokens: <remaining_budget>` in args: a hard cap on
  measured spend, never the default again. Never write routing records under
  `state/lessons/`; records land under `<run_dir>/records/`. Mechanical rules:
  `coordinator/docs/wiki/lesson-triage/learn-lessons-mechanical-dispositions.md`.
- **central route:** drain the outbox, then assert cross-plane emptiness first (a FAIL stops the
  run; the EM repairs the plane split). Emit `--queue state/lessons-outbox --profile lessons-central-route`,
  fire, then the EM writes `pm_decision` per row from the verify verdict (see Hard Rules) and commits. `defer` rows go to `coordinator-queue-append --schema
  improvement-queue` with `queue_scope: central`; `reject` rows close as `discarded` through
  `backlog-grind-assemble grind-row close`. Cluster rulings: wiki § Phase flow detail.
- **central apply:** emit `--profile lessons-central-apply`, fire, then write the run stamp once
  every apply commit has landed and the fail-close holds.
- **strip:** emit `--profile lessons-strip` per repository after the apply run, with `--where
  promoted_to in [...]` copied from the apply run's settled list. A sibling launch proceeds only under the
  session's standing cross-repo commit assent (given at dispatch, never asked by this skill); without it the strip waits.

Whoever executes this skill (EM or dispatched lead) runs each flow; commit authority stays EM-only.

**Post-run consumption, all runs.** `baton` → cluster and mint batons carrying triage's sizing
evidence, with no second gate (the fire authorized them); `needs-judgment`, `doe-escalation` and
`direction-call` → an adjudicator agent, never the PM; `route-to-central` → `coordinator-lesson-promote` per row with
`--title-file`/`--body-file`, then write `promoted_to` on the row and commit; engine-originated
types → counted in Phase 8, rows left open.

**Cross-repo channel (local mode, run in a sibling).** The sibling EM commits only its own row's
`promoted_to` stamp; the central-mode EM commits the outbox file(s) before the central route run
reads them. **No dry-run mode;** the Phase 8 report cites `state/queue-grind/<profile>/runs/<run-id>.json`.

Emit the Phase 8 end-of-run report (exempt from the ≤200-word budget — the run's only audit trail),
built from the engine's receipt and hand-back document, with the run's total tokens against the
bar, before writing the `COMPLETE` sentinel. `COMPLETE` is blocked while a route-run row carries no
`pm_decision`, or the apply run handed back an engine-originated type — the EM resolves those
first. The top-level EM writes the sentinel last, after every apply/commit lands.

Wrap the report in the marker pair, which declares the exemption to the comms hook
(`em-pm-comms-instrumentation.md` § The ceremony-mandated marker):

```
<!-- ceremony-mandated:start -->
...the Phase 8 report...
<!-- ceremony-mandated:end -->
```

## Anti-Patterns

Applying a central promotion with no EM-written `pm_decision`; `git add -A` for strips; true-deleting a
discard instead of archiving first; default-routing to CLAUDE.md; defer-chaining wiki promotions
(every record is applied, adjudicated, or mode-escalated); a hand-rolled fallback when the emitter
is unavailable. Full list: wiki.

## Related

wiki (full reference) · `${CLAUDE_PLUGIN_ROOT}/queue-profiles/lessons.yaml`,
`lessons-central-route.yaml`, `lessons-central-apply.yaml`, `lessons-strip.yaml` ·
`${CLAUDE_PLUGIN_ROOT}/snippets/em-operating-doctrine.md § How to Plan and Hand
Off, "Improvement Queue"`
