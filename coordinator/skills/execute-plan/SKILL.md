---
name: execute-plan
description: Execute a PM-approved implementation plan directly in the coordinator session
allowed-tools: ["Read", "Edit", "Write", "Bash", "Grep", "Glob", "Agent", "Skill"]
argument-hint: <plan-path>
---

# Execute Plan — Direct In-Session Plan Execution

Run a PM-approved implementation plan **end-to-end to full completion** without stopping for permission between tasks. The PM's approval of the plan is the authorization — this command executes it diligently and in its entirety, commits the work, and reports. Here "PM approval" means an explicit **post-review** authorization to execute — the PM said "execute"/"proceed" after seeing the review output — NOT the initial "plan this" ask, and NOT review-completion on its own. Exception: in `/autonomous` mode (sentinel `/tmp/autonomous-run-${SESSION_ID}` present), the checkpoint was already bypassed at `coordinator:review`; execute-plan proceeds without a separate authorization utterance.
<!-- Review: code-reviewer — "NOT review-completion on its own" created a false stop condition in /autonomous mode where the checkpoint was already bypassed upstream; autonomous exception added. -->
It does **not** chain into branch disposition (merge / PR / keep): finishing a development branch involves the PM-gated `/merge-to-main` and is a separate decision. The natural next step after the **last** chunk of the **last** phase ships is `/workstream-complete` (cap the workstream — lessons, docs, workstream-complete review), which execute-plan offers but does not auto-invoke. See Phase 4.

**Core principle:** Write-ahead every task (both plan document on disk AND task list via TaskUpdate), execute autonomously through every phase, **make every engineering decision the plan leaves to execution-time**, stop only on a genuine PM-only emergency (Phase 5). A task being hard, a sub-decision being non-obvious, or a workaround being needed are EM decisions — not stop conditions. **Phase boundaries are not stop boundaries**: when Phase N ships green, immediately dispatch Phase N+1 — do not pause to offer the PM a checkpoint, do not parrot `/workstream-complete` after a partial-phase completion (the 2026-06-15 lesson named this failure explicitly).

**Stance — execute = restructure-then-dispatch.** Executing a plan is not "type the plan's steps." It is: read the plan, build the dispatch-gate graph (Phase 1.5), and then **decompose into per-chunk dispatches** — one executor per chunk, fanned out in parallel where the gates allow and run in sequence where they don't. Decomposition is unconditional; parallelism is only the time-overlap axis. **A serial chain is still N dispatches (a fresh agent per chunk, EM-verify between), never one long-lived executor walking the chain** — that bundling is the failure this skill exists to prevent. This whole shape is the fan-out methodology execution follows (`docs/wiki/dispatching-parallel-agents.md` § Executing a Fan-Out Wave), not a separate command, and it governs serial waves as much as parallel ones (serial = depth-1 cohorts). The default outcome of executing is a dispatched wave.

**Self-execute vs. dispatch is a token-economics call, not a vibe.** A Sonnet executor burns ~¼ the tokens of an Opus EM doing the same edits, and finishes faster — so dispatch wins almost every time. Self-executing inline is the rare carve-out, justified only when you can name why it is genuinely cheaper *here* (loci already loaded, tight cross-file coherence on a small surface). Ground that against the `When to EM-Inline` checklist in `docs/wiki/agent-dispatch-economics.md`; the full criterion lives at Phase 1.5 § Self-execute escape hatch. If the plan contains enriched stubs with known file paths, exact line numbers, and code sketches, the dispatch is even cheaper — fan out Sonnet executors per `docs/wiki/delegate-execution.md`.

---

## Arguments

`$ARGUMENTS` is the path to the plan document to execute — e.g., `tasks/my-feature/todo.md` or an absolute path. The file must be readable and contain a structured implementation plan.

If no path is provided, report: _"Usage: /execute-plan <plan-path>. Provide the path to the plan document you want to execute."_ and stop.

---

## Phase 1: Load and Review

1. Read the plan document at `$ARGUMENTS` in full
2. Review it critically — identify any gaps, ambiguities, or concerns:
   - Missing file paths or unclear scope?
   - Steps that assume context not captured in the plan?
   - Dependencies on external state that may have changed?
   - Anything that would require an architectural decision mid-execution?
3. **Resolve concerns at EM altitude.** If a concern is mechanical (unclear path → grep; ambiguous default → pick the better one and note rationale in the plan body; missing context → dispatch a read-only scout), resolve it and continue. **The execute-plan invocation is not the moment to surface EM-resolvable concerns to the PM** — that's planning work that should have happened at `/plan` time. If a concern reveals that the plan is *not actually executable* (see Phase 1.4), bounce back to `/plan` — do not start a half-executable plan.
4. Announce _"I'm running `/execute-plan` to implement this plan end-to-end."_ and continue to Phase 1.4.

---

## Phase 1.4: Executability Gate — Refuse Plans That Aren't Actually Plans

<!-- spec-backlink: 2026-06-15 PM directive — "execute-plan is for when we know what we're doing and can dispatch all the way through to the end" — if a plan has a 'fact-find then stop and reconsider' phase, that's planning, not execution -->

Before building the gate graph, the plan must clear an **end-to-end-executable** check. A plan that contains an embedded decision gate, a fact-finding stub with no fix-locus, or a downstream phase whose chunk shapes are undecided is planning work masquerading as execution work — bounce it back to `/plan`.

**Refuse-to-execute signals** (any one is sufficient — stop and route back to `/plan`):

| Signal | What it looks like in the plan body |
|---|---|
| **Embedded decision gate** | "Evaluate X before continuing", "spike Y then reconsider", "decide N at chunk-write time" where N is a non-mechanical architectural choice (which module, which seam, which paradigm), "Phase 0 — investigate", "TBD pending Phase 1 outcome" |
| **Fact-finding chunk with no fix-locus** | A chunk whose deliverable is a recommendation, a report, or "options for Phase 2", rather than code/config/doc landing at a named path |
| **Unpopulated downstream ledger** | The Dispatch Ledger has rows for early phases but later phases appear as `TBD` / `pending realization for chunk shape` / a prose paragraph instead of typed rows |
| **In-prose deferral of EM-resolvable decisions to the PM** | "PM to decide between A and B before Phase 2" on a choice that is engineering-tactical (file split, helper naming, refactor mechanics, internal sequencing). PM-altitude product decisions (privacy, user-visible behavior, external trust surface) are legitimate; engineering decisions are not. |
| **Open questions that gate execution** | An `## Open questions` section whose answers determine whether downstream chunks can be authored at all (vs. flagged-for-reviewer-challenge, which is fine — the reviewer's already run by the time execute-plan fires) |

**What is NOT a refuse-signal:**
- A `Phase 0` that ships independently valuable code (a prereq chunk) with a populated ledger — that's a normal phase, not a decision gate.
- A chunk whose brief says "resolve the exact list of methods at chunk-write time from `<file>:<line>`" — that's mechanical lookup, not architectural decision.
- A reviewer-named `## Open questions for plan review` block carrying EM-decided defaults — those resolved at plan review, the block is paper trail.
- A future-phase chunk whose write-files are pinned but whose internal implementation is sketched — execution refines the sketch.

**Action on a refuse-signal:** Stop, name the specific signal verbatim, and tell the PM: _"This plan contains <signal> at <location>. That's planning work, not execution work. Routing back to `/plan` to resolve before execute-plan can dispatch end-to-end."_ Then invoke `coordinator:plan` on the gap.

---

## Phase 1.5: Dispatch-Gate Graph

<!-- spec-backlink: docs/plans/2026-05-27-fan-out-default-doctrine.md § Chunk 5b — responsibility-split table; the mechanical steps (overlap pass, scoped-prompt emission) route to the helper + fan-out skill; budget-sizing and gate-type discrimination are EM-judgment steps retained here -->

This phase is the EM's named responsibility at the seam between plan-approved and first executor dispatch. It applies whether execution is direct (Phase 3) or via dispatched executors — the gate-graph is identical in either case.

**Three real gate types** determine what can run concurrently vs. must be serial (narrative causality, aesthetic ordering, and "I'd rather review A before B" are NOT gates):
- **File-write overlap** — two tasks edit the same path.
- **Output-consumption** — Task B reads a file Task A writes.
- **Contract-change dependency** — Task A bumps a schema, helper signature, or shared surface Task B depends on; promote shared-API work to a predecessor wave.

**Output-consumption and contract-change gate *verification*, not *authoring*.** When B's only dependency on A is consuming its output or contract, B can be *authored* concurrently with A if the interface is pinned (the full signature written down, precise enough to author against without asking the producer) — only B's green-verification waits for A to land. File-write overlap is the sole unconditional serial gate. Default to concurrent-with-pinned-interface, verify-at-merge: pin the interface, fan out producer + consumers in one wave, verify at merge. Hard gate: no pinnable interface → fall back to predecessor-wave shape.

→ Full taxonomy and rationale: `docs/wiki/dispatching-parallel-agents.md` § Dispatch-Gate Taxonomy (incl. Author vs. verify) and § Peer-Scope Prohibition in Parallel-Wave Prompts.

**Execute-time premise/overlap reconcile (before gate-type discrimination).** Plans drafted hours or days ago may be invalidated by work that concurrent EMs shipped in the interval. Before classifying gates, run `git fetch` and diff the plan's `write-files` against commits landed since the plan-draft date:

```bash
git fetch --quiet
git log --oneline --since="<plan-draft-date>" -- <write-file-1> <write-file-2> ...
```

If any write-file has been touched by a commit not in this session, reconcile before fan-out: verify the plan's premise for that file still holds (the function/schema/path the plan assumes still exists in the expected shape), adjust the affected chunk brief to account for the landed work, and note the reconciliation in the ledger. **Do not dispatch on a plan whose substrate was modified by a concurrent EM without checking.** The pickup Step 3.4e premise-verification catches this at handoff time; this step catches it at execute time for plans dispatched in the same session they were authored and for re-entries after compaction. [source: queue-triage-2026-06-21 chunk-3, queue line 86]

**EM-judgment step 1 — Gate-type discrimination (helper cannot do this):** Classify every task-pair relationship as one of the three gate types above, or as truly independent. The helper detects file-write overlap automatically; output-consumption and contract-change dependencies require EM reading the plan's per-task scope. Do not outsource this classification — the helper sees file paths, not semantic contracts.

**Build the wave shape from the file-write graph, NOT from the plan's section/phase/cluster structure.** Plans are written for *readers* — grouped by theme, by subsystem, by narrative arc. Those are reader-axes, not dispatch-axes. The mechanical step at the top of ledger construction (Phase 1.6) is: enumerate every write-target the plan touches, group by *write-overlap*, then map chunks onto the resulting lanes. A plan with 6 thematic clusters across ~6 disjoint file-lanes is **one parallel wave of ~6 lanes**, not 6 sequential phases — even if the plan document presents the clusters as Phases 1–6. **Recurring failure mode** (2026-06-02; instance #2 2026-06-09): mapping the plan's narrative phases directly onto execution phases and serializing them. The 2026-06-09 fix moves the discriminator into the **Phase 1.6 `gate-kind` column** so the artifact, not the EM's discipline, is what fails-loud. Recheck before dispatching: for each gate you imposed, name its kind (`none` / `file-write-overlap` / `output-consumption-content` / `output-consumption-runtime` / `contract-change`); only `file-write-overlap` and `output-consumption-runtime` actually gate *authoring*. Anything else recorded as `after #N` is malformed by default — see Phase 1.6 § gate-kind table.

**EM-judgment step 2 — Budget-sizing (helper cannot do this):** Aim for ~5–10 min per executor on a single coherent surface, 15 min hard ceiling. **Rule of thumb: a series of small-remit executors beats one executor with a large remit — in parallel where the gates allow, in sequence where they don't.** The budget axis is **orthogonal** to the parallelism gates above: file-overlap answers *can these run concurrently*, NOT *how many dispatches*. When overlap (or output-consumption, or contract-change) forces serial execution, apply the budget check independently at each serial position — `"can't parallelize" ≠ "one dispatch."` Over-budget coupled work chunks into a **fresh agent per chunk** (`dispatch B2 → EM verifies → dispatch fresh C1 → EM verifies → dispatch fresh C2/D`), never one agent handed chunk after chunk. → `docs/wiki/dispatching-parallel-agents.md` § Coupling Rules Out Concurrency, Not Decomposition.

**Mechanical step — follow the fan-out methodology:** Once gate-type discrimination and budget-sizing are done, **follow the canonical fan-out methodology** at `docs/wiki/dispatching-parallel-agents.md` § Executing a Fan-Out Wave. Fan-out is a methodology execution follows, **not a skill to invoke** — there is no `/fan-out` command. This Phase 1.5 *is* the plan-mediated entry to that methodology.

Compile the wave spec (one TSV row per chunk: `<chunk-id>\t<brief>\t<comma-separated-files>`) from the gate-graph analysis above, then walk the methodology's steps: **Step 0.5** fan-out suitability gate (HARD STOP — re-chunk any fat chunk before dispatch), **Step 1** run `fan-out-dispatch.sh` for the overlap pass + scoped-prompt compilation (hard-stop on collision), **Step 2** organic ramp, **Step 3** dispatch the compiled blocks via `Agent` (`mode: "acceptEdits"`, all concurrent), **Step 4** EM-serial commit. **Do NOT duplicate wave-map logic here** — the helper + the wiki methodology are the single source for that ceremony.

**Self-execute escape hatch — gated on token-economics, not vibe.** The default is to dispatch. **Self-execute only when you can articulate why it is genuinely cheaper *here*** — e.g. the loci are already loaded in your context and re-loading them into N executors would cost more than typing, or cross-file coherence across a small surface is the dominating constraint. Ground that articulation against the concrete `When to EM-Inline` checklist in `docs/wiki/agent-dispatch-economics.md` (fix-locus ≤3 files / <60s on a >30k-file repo / mechanical / context-already-loaded / mid-edit-hazard) — "articulably cheaper" is self-graded by the same agent that wants to skip the work, so the checklist is the guard. **Self-execute is the one path that skips the Step 0.5 suitability gate** (the EM holds the gate in its own judgment instead). The gate-graph still applies either way. Self-executed chunks still appear in the Phase 1.6 ledger as `inline (EM)` rows — one row per chunk, never a bundle. The escape hatch requires ALL `When to EM-Inline` checklist criteria in `docs/wiki/agent-dispatch-economics.md` to hold simultaneously — a favorable wall-clock estimate alone is not sufficient. When the EM takes an authorized inline carve-out, it writes the session-scoped sentinel file `/tmp/coordinator-dispatch-nudge-ok-${SESSION_ID}` so the dispatch-nudge PreToolUse hook stays silent for that authorized inline work.

---

## Phase 1.6: Dispatch Ledger — Mandatory Pre-Dispatch Gate

<!-- spec-backlink: this skill's 2026-05-30 failure — gate graph correctly produced 4 chunks (1 / 3b / 2 / 3a); EM narrated "delegate the chunker to a focused executor" then dispatched "3b + 3a + 2" as ONE 23-minute executor. The prose rule in Phase 1.5 ("can't parallelize ≠ one dispatch") was present and ignored; this ledger converts it into a mechanical artifact where the bundle is malformed on its face. -->

> **Schema-coupling pointer:** the per-chunk write-overlap decomposition this ledger consumes is the plan-author obligation in [`skills/plan/SKILL.md`](../plan/SKILL.md) § Branch B — fan-out-shaped chunking row. The ledger here is the late-correction surface; the plan-author row is the prevention surface. Both link to `docs/wiki/dispatching-parallel-agents.md` § Coupling Rules Out Concurrency for the doctrine root — no schema lives in two prose blocks.

**Before issuing *any* `Agent` call, WRITE a dispatch ledger INTO the plan document on disk** — a `## Dispatch Ledger` section, one row per chunk from the Phase 1.5 gate graph. **This is a disk write, not a chat emission.** A ledger narrated to chat is ephemeral and the EM can rationalize around it mid-flow; a ledger written into the plan file is the contract the EM dispatches against — crash-durable, PM-visible, and re-readable after compaction. It is the same write-ahead discipline as Phase 3a, applied to the dispatch decomposition. The failure it prevents: the EM narrates an intent and then silently bundles several gate-graph chunks into one open-ended dispatch because they happen to be serial. A ledger on disk makes that bundle visibly malformed before it is dispatched.

Edit the plan document (the file at `$ARGUMENTS`) to add:

```markdown
## Dispatch Ledger

| dispatch # | chunk-id | one-line brief | write-files | AC-paths | gate-kind | runs | est-min | status |
|---|---|---|---|---|---|---|---|---|
| 1 | … | … | … | AC1, AC2 / — | none / file-write-overlap / output-consumption-content / output-consumption-runtime / contract-change | inline (EM) / parallel / after #N | … | pending |
```

**Per-chunk flight-recorder sidecars.** Each ledger row has a companion sidecar at `tasks/<plan-slug>/flight/<chunk-id>.md`. `fan-out-dispatch.sh --plan <path>` creates each sidecar at dispatch time with starter `status: dispatched` frontmatter and injects `sidecar_path:` into each executor brief. Executor lifecycle: flip `dispatched` → `in_flight` on first action, then `complete | blocked | thrashing` at exit, with `## Observations` body and `commits:` frontmatter list. EM is read-only on the sidecar until the executor returns. At `/workstream-complete`, fold noteworthy observations into a `## Execution Observations` plan-body section, then delete the `tasks/<plan-slug>/flight/` directory (per `docs/wiki/scratch-lifecycle.md` § Pattern A); `blocked` and `thrashing` sidecars survive. The dispatch ledger remains the canonical EM-side surface — the sidecar is the executor-side companion.

**The `AC-paths` column maps each chunk to the `gate-bound` AC row IDs whose typed-prefix Test cell path argument its `write-files` cell owns** — a comma-separated list of AC IDs (e.g. `AC1, AC3`) or `—` as a positive assertion that the chunk authors no AC-bound tests (infra, doc-only, and fixture-only chunks use `—`; a blank cell on a non-infra chunk is an a-soft opt-out that is a reviewer-visibility gap worth a one-line ask). The column covers `gate-bound` ACs only — `reviewer-judgment` and `cited:` ACs are out of scope because their coverage is asserted by a human reviewer, not by a chunk authoring a test artifact. Added 2026-06-15 (a-soft variant per `docs/plans/2026-06-15-ac-paths-ledger-column.md`): there is no validator binding under a-soft — the `validate-ac-chunk-ownership.js` hook remains the mechanical gate, validating AC paths against the union of `write-files` cells; this column is a reviewer-visibility complement, not a redundant validator on the same invariant. The hook and column are deliberately overlapping layers with distinct roles (hook = edit-time mechanical gate; column = review-time comprehension surface) per `docs/wiki/writing-plans.md § Defense-in-Depth Framing — Deliberate Overlap, Not Necessary-and-Sufficient`.

**Hardware/editor-gated verification: author now, spinoff the verification.** When an AC row's verification step requires hardware that isn't in the dispatch environment (device attached to the target machine, editor open, runtime that can't be headless), the correct shape is: author the work in the current wave AND create a `/spinoff` for the verification step. The oracle MUST treat `cited:` rows as NOT equal to `verified:` rows for these ACs — a `cited:` AC asserts that the artifact was authored and the claim is documented, but does NOT assert the verification ran. When authoring the ledger row for such a chunk, mark the corresponding AC-paths entry with `cited:` prefix rather than a bare `pytest:` or `bash:` prefix; the acceptance-oracle script (`check-acceptance-oracle.sh`) distinguishes these classes. Failure mode to prevent: treating a `cited:` row as green at Step 3.8 without having run the verification. [source: queue-triage-2026-06-21 chunk-4, queue line 129]

**The `gate-kind` column is the mechanical author/verify discriminator** — added 2026-06-09 to force the EM to name the dependency kind rather than writing `after #N` and never asking whether it gates authoring or only verification:

| Value | What it means | Does it serialize authoring? |
|---|---|---|
| `none` | Chunk is independent — no dependency on any other ledger row | No. Goes in the earliest possible wave. |
| `file-write-overlap` | The chunk writes to a path another chunk writes to | **Yes.** The only authoring gate; producer must land before consumer authors. |
| `output-consumption-content` | The chunk reads another chunk's output as static content (file text, schema, fixture) | **No** if the producer's interface can be pinned (signature/schema/path written down up front). Author concurrently; verification gates at merge. |
| `output-consumption-runtime` | The chunk needs another chunk's artifact to *exist at runtime* (e.g. a dry-run that exercises a not-yet-shipped pipeline) | **Yes.** Producer must ship before consumer can execute. |
| `contract-change` | The chunk depends on another chunk landing a contract change (rename, signature edit, schema migration) | **No** if the new contract can be pinned in writing up front. Authoring concurrent against the pinned contract; verification gates at merge. |

**The rule the column enforces:** any row with `gate-kind` ∈ {`output-consumption-content`, `contract-change`} written as `after #N` is malformed by default — the EM must either (a) downgrade `runs` to `parallel` (with verification deferred to merge against the pinned interface) or (b) record a one-line rationale why pinning the interface is infeasible *here*. The failure mode this catches: noticing "C2 needs C1's output" → writing "after #1" → never asking "is this authoring-gating or verification-gating?"

**`output-consumption-runtime` is the genuine serial case** — the consumer's *execution*, not its *authoring*, depends on the producer. A dry-run that needs to invoke a real pipeline is the canonical example; a dispatch that reads a schema file is not.

**The invariant — one chunk per row, one chunk per dispatch:** the number of distinct dispatch-numbers (counting `inline (EM)` rows) **equals** the number of chunks. **If any single dispatch number spans more than one chunk-id, the ledger is malformed — STOP and split before dispatching.** "These chunks are serial, so one executor can just walk them in order" is the exact rationalization this gate rejects: serial coupling removes *concurrency*, never *decomposition* (Phase 1.5 EM-judgment step 2; wiki § Coupling Rules Out Concurrency).

**Global-coverage test mandate for gated-artifact chunks.** When a chunk's `write-files` includes a gated artifact (a test file, registry entry, or oracle row that other chunks or the acceptance gate consume), its dispatch brief MUST name and invoke the **global** coverage or registry test — not only the chunk's own unit tests. Chunk-local green while the global registry is red is the failure mode: the new artifact doesn't register, the gate still fails, and the error surfaces only at workstream-complete. How to apply: (1) identify whether the chunk writes to a registry / oracle / shared test fixture; (2) add a post-fix step to the brief: "run `<global-coverage-command>` after your chunk's tests pass"; (3) if the global command is absent, note that gap in the chunk's DONE report rather than silently skipping. [source: queue-triage-2026-06-21 chunk-2]

**Disjoint-write-target expansion rule — applied AT ledger construction, not after PM prompting.** Before writing a row, list every path in `write-files` for that chunk. **If those paths split into K mutually-disjoint groups** (no path in group A is co-edited with any path in group B by the chunk's own logic), the chunk fans out into K rows — one per group — at ledger-write time. A plan-chunk like "C7 — update three docs (A.md, B.md, C.md)" with three independent docs is **C7a / C7b / C7c**, three parallel rows, not one row that walks them. The bar for keeping N disjoint write-targets in one row is *tight cross-file coherence* the chunk's own brief names; thematic affinity ("they're all docs") does NOT meet it. Recurring failure (2026-06-02): 9 parallel-safe chunks dispatched as 9 executors when 3 of them each owned 3 disjoint surfaces — the correct shape was 17.

- **`runs` column** records each row's gate: `parallel` (same wave), `after #N` (serial — a fresh agent that fires only after dispatch #N has landed *and* the EM has verified it on disk), or `inline (EM)` (the token-economics self-execute carve-out).
- **`est-min` > 15 on any row → re-split that chunk before dispatch.** The per-executor ceiling is 15 min on one coherent surface; aim for 5–10.
- **A serial chain is N sequentially-dispatched rows** (`after #1`, `after #2`, …) — each a fresh agent on a clean context with EM verify-and-commit between, **never one long-lived executor**. This still routes through the fan-out methodology's Step 0.5 suitability gate; serial just means depth-1 cohorts.
- **`status` column is write-ahead state, updated on disk as Phase 3 proceeds:** `pending` → `dispatched` → `verified` → `committed`. Edit the row in place at each transition — the same crash-insurance Edit Phase 3a does for task state. A post-compaction or post-crash agent re-reads this table to see exactly which chunks shipped and which are still owed.

**Runtime tripwire — the EM owns the clock.** If any dispatched executor runs past ~15 min wall-clock, that is a dispatch-sizing failure surfacing late: **stop it, recover partial work from disk (it persists — shared working tree), and re-split into fresh per-chunk dispatches** (add the split rows to the ledger on disk). Do not wait for it to finish, and do not wait for the PM to flag the runaway.

---

## Phase 2: Create Flight Recorder

Create a task list (TaskCreate) for this execution session:

- **One session-goal task** — titled with the overall objective and the plan path, so a post-compaction agent can re-orient without re-reading the conversation
- **One task per plan phase or major task** — enough granularity that "what is in progress" is unambiguous at any point
- **Mark the session-goal task `in_progress`** immediately via TaskUpdate

This flight recorder is your compaction insurance — tasks persist through compaction by design. Keep it current throughout execution.

---

## Phase 3: Execute All Tasks

**Default behavior: execute every task in sequence without stopping to ask permission.**

For each task in the plan:

### 3a. Write-Ahead (before starting the task)

Update BOTH:
1. **The plan document on disk** — mark the current task as `In progress (started YYYY-MM-DD HH:MM)`. Edit the file directly. This is crash insurance — if the session dies, the plan shows where execution stopped.
2. **Task list** — mark the corresponding task `in_progress` via TaskUpdate

### 3b. Execute

- Follow the plan's steps exactly — do not improvise or extend
- Run verifications as the plan specifies
- Fix routine errors (type errors, missing imports, lint) immediately and move on — these are expected noise, not blockers

### 3c. Mark Complete (after the task passes verification)

Update BOTH:
1. **The plan document on disk** — update the task to `Complete (YYYY-MM-DD HH:MM)`
2. **Task list** — mark the corresponding task `completed` via TaskUpdate

### 3d. Proceed — Including Across Phase Boundaries

Move immediately to the next task. **Phase boundaries are not stop boundaries.** When the last chunk of Phase N ships green, dispatch the first chunk of Phase N+1 — same session, same flight recorder, no PM check-in, no offer of `/workstream-complete`. Brief status updates at natural milestones are fine (_"Phase 2 complete, dispatching Phase 3"_); these are informational, not permission requests, and never end in a wrap-ceremony offer until Phase 4.

**Decisions encountered mid-dispatch are EM decisions, made and recorded inline.** When an executor returns BLOCKED on a sub-question, when a chunk reveals an architectural micro-fork the plan didn't pin, when a default needs picking — the EM picks, appends a one-line rationale (`<!-- decided 2026-MM-DD: chose X over Y because Z -->` or an `## Execution Notes` row), and continues dispatching. PM-altitude decisions (the narrow Phase 5 list) are the only carve-out.

---

## Phase 5: When to Stop — PM-Only Emergencies

The default is **complete the plan**. Stop only when continuing would cross a line the EM cannot cross without the PM. This list is intentionally narrow — "I'd like the PM to weigh in" is not on it; "this is hard" is not on it.

**Stop and escalate to the PM only when:**

- **External trust surface change** — the plan, when executed faithfully, would alter user-visible behavior, privacy posture, security boundary, billing/pricing/onboarding, or any externally-observable contract that the plan body did not call out explicitly. Discovering this mid-execution = stop, surface, get explicit PM auth before proceeding.
- **Plan-invalidating substrate change** — something on disk has changed since the plan was written that makes the plan structurally wrong (not just tactically inconvenient). The fix requires re-shaping the problem. Bounce back to `/plan`.
- **Scope explosion that changes the deal** — the work has revealed itself to be ≥3× the plan's anticipated size and the EM cannot articulate a 5-15min-chunk decomposition for the remainder. Route back to `/plan`.
- **Unauthorized irreversible action required** — completing the plan literally requires a destructive op, a force-push, a cross-repo write to a sibling repo's code surface, a credential/cookie write, or any other action gated by `~/.claude/CLAUDE.md` § Executing actions with care. Stop; ask.
- **Discovery the plan would ship something the PM clearly did not authorize** — the plan was approved on premise X, execution reveals it would also do Y, and Y is not a mechanical consequence of X. Surface Y; do not silently ship it.

**Not on the list — these are EM decisions, made inline:**

- ~~Accumulating patches~~ — re-split the remaining ledger rows and continue.
- ~~Ambiguity spreading~~ — resolve by EM judgment with rationale in the plan body, or dispatch a read-only scout for substrate evidence.
- ~~Structural verification failure~~ — root-cause via `/systematic-debugging`, fix at source.
- ~~Routine fixable errors~~ — fix and continue.
- ~~Minor judgment calls~~ — make the call, note it, continue.
- ~~Wanting to check in~~ — not a reason; status lands in commit messages and at Phase 4.

**When you do stop (one of the five above):** Record in both the plan document AND the relevant task's `metadata.tried_and_abandoned` field (via TaskUpdate) what was tried and why it failed. Format: `"Tried: [approach] — Failed: [reason]"`. Surface to the PM with a recommendation, not a question — _"I think we should X because Y — want me to proceed?"_ beats _"X or Z?"_

---

## Phase 4: Finalize and Report

**Precondition: every ledger row's `status` is `committed` AND every Acceptance Criterion is green.** If any row is still `pending` / `dispatched` / `verified` (uncommitted), or any AC is `pending realization`, return to Phase 3 and dispatch the remaining chunks. Restate the AC table verbatim in the completion report with green/pending status — if any row is `pending`, route back to Phase 3, do not advance.

**Execute-plan ends here — it does not chain into branch disposition.** Implementing a plan is EM-remit engineering work; deciding what happens to the branch (merge / PR / keep) reaches the PM-gated `/merge-to-main` and is a separate, PM-invoked decision.

### Phase 4a: Early Acceptance-Oracle Feedback (non-authoritative)

<!-- spec-backlink: archive/specs/2026-05-24-acceptance-oracle-with-teeth.md §2.3 — execute-plan Phase 4 early non-authoritative gate -->

Run the acceptance oracle as early advisory feedback. The plan path is `$ARGUMENTS` (the plan document this skill was invoked with).

```bash
bash check-acceptance-oracle.sh "$ARGUMENTS"
```

**This gate is advisory only at this surface** — the authoritative gate is at `coordinator:workstream-complete` Step 3.8. Do NOT hard-block here regardless of exit code.

- **Exit 0:** Log _"Acceptance oracle: all gate-bound tests pass."_ and continue to Phase 4b.
- **Non-zero exit:** Log the verdict from the script (it will name which rows are red), then continue to Phase 4b. Frame the output as early feedback: _"Acceptance oracle reports red tests — iterate on these before reaching /workstream-complete, where the gate is authoritative."_
- **Script not found or no plan path:** Skip silently and continue to Phase 4b.

### Phase 4b: Commit, Report, and Offer the Next Step

1. **Commit any uncommitted work** with a scoped, explicit-path commit (plain `git add -- <paths> && git commit`, per the concurrent-EM commit doctrine). Commits are EM-remit quick-saves; don't ask permission to commit.

<!-- mandatory-commit-shape -->
**Mandatory commit shape (concurrent-EM safe).** Plain explicit-path git is the default per SC-DR-008; the helper is reserved for sweep ceremonies + the executor's branch-pin path. Use ONE of:

```bash
# Default — explicit-path commit (SC-DR-008 baseline):
git add -- <paths> && git commit -m "<subject>" -- <paths>

# OR, for handoff-scoped sessions, the helper (defaults to em-only as of 2026-06-15):
coordinator-safe-commit --scope-from <handoff> "<subject>"
```

Plain-git is listed first deliberately — the helper is the carve-out, not the primary path. **Never `git add -A` / `git add .` / `git add --all`** — the `block-blanket-git-add.sh` PreToolUse hook enforces this; see `docs/wiki/coordinator-tripwires.md § BLOCK-BLANKET-GIT-ADD` and `docs/wiki/scoped-safety-commits.md § SC-DR-014`.
2. **Report completion** — restate the plan's Acceptance Criteria table with green/pending status per row, name what landed, the acceptance-oracle verdict from Phase 4a, and the branch the work is committed on.
3. **Offer the next step as a phase-aware offer, never a parroted default.** Two branches:

   **(A) Full plan shipped** — every ledger row `committed` AND every AC green (the Phase 4 precondition above). Offer:

   > _Plan executed end-to-end and committed on `<branch>`. The natural next step is `/workstream-complete` to cap the workstream (lessons, docs, workstream-complete review). When you want to ship it, `/merge-to-main` or `/workday-complete` carries the branch to main._

   **(B) Execution halted on a Phase 5 PM-only emergency** — some ledger rows still `pending`, ACs partially green. Do **NOT** offer `/workstream-complete`. Offer:

   > _Execution halted at `<chunk-id>` on `<emergency-class from Phase 5>`. Remaining ledger: <list pending rows>. Options: (a) resolve the blocker and resume (I'll re-enter Phase 3 at the same chunk); (b) `/handoff` to save state for a fresh session; (c) commit-and-stop without a handoff (this branch carries the partial work). `/workstream-complete` is not offered — it caps the full plan, not a partial run._

   Do **not** invoke `/workstream-complete`, `/merge-to-main`, `/workday-complete`, or `coordinator:finishing-a-development-branch` automatically. `/merge-to-main` is keyword-gated (the PM invokes it by name); `/workstream-complete` vs `/handoff` vs `/workday-complete` depends on workstream state, which the PM picks.

---

## Failure Modes

| Situation | Action |
|---|---|
| Multiple gate-graph chunks about to go to one executor | Malformed ledger (Phase 1.6) — STOP, one chunk per dispatch, split before dispatching |
| Wave shape mirrors the plan's section/phase/cluster structure | Theme is not a gate. Rebuild from the file-write graph per Phase 1.5; strip any gate that isn't write-overlap / output-consumption / contract-change |
| A ledger row has N internally-disjoint write-targets | Under-expanded. Split into N rows (Phase 1.6 disjoint-write-target expansion rule) before dispatching; thematic affinity is not a coherence reason |
| A row reads `after #N` with `gate-kind` = `output-consumption-content` or `contract-change` | Author/verify conflation. The gate is verification, not authoring — either pin the producer's interface up front and downgrade to `parallel`, or record a one-line rationale why pinning is infeasible. "C2 narratively follows C1" is not a gate. |
| A row's `gate-kind` is blank or "after #N" stands alone | Pre-2026-06-09 ledger shape — surface the missing discriminator and refuse to dispatch until the column is filled. |
| A dispatched executor runs past ~15 min wall-clock | Dispatch-sizing failure — stop it, recover partial work from disk, re-split into fresh per-chunk dispatches |
| Plan path not provided | Report usage and stop |
| Plan file not found | Report the path that was tried and stop |
| Plan has no concerns but looks unreviewed | Surface the observation; proceed only if PM confirms |
| Task fails with fixable error (type error, import, lint) | Fix immediately, continue |
| Task fails with structural error after 2 attempts | Stop, record what was tried, consult PM |
| Verification step in plan fails | Stop and report — do not skip verifications |
| Plan's approach is invalidated mid-execution | Stop, record `Tried/Failed`, flag for PM to update plan |
| Tests fail at Phase 4 | Report failures in the completion report; do not offer `/workstream-complete` as a clean next step until they're green. Fix routine failures and re-run; stop and consult the PM on structural failures |

---

## Relationship to Other Commands

- **Fan-out methodology (`docs/wiki/dispatching-parallel-agents.md` § Executing a Fan-Out Wave)** — the dispatch ceremony execution follows, **not a skill** (the `/fan-out` command was demoted 2026-05-30; the verb collided with native Claude Code vocabulary). Phase 1.5 is the plan-mediated entry to it; ad-hoc parallel work (≥2 tasks, no plan doc) follows the same methodology inline. Stance: **execute = restructure-then-dispatch; fan-out = the dispatch methodology**.
- **Executor dispatch (`docs/wiki/delegate-execution.md`)** — the model-selection rubric for the executors a fan-out dispatches; use when the plan consists of enriched stubs with exact code sketches, file paths, and line numbers. Dispatch is the default; self-execute inline only on the token-economics carve-out (see Phase 1.5 § Self-execute escape hatch).
- **`/enrich-and-review`** — should be run before executor dispatch; not required before `/execute-plan` (plans that route here are typically less chunked).
- **`/review-code`** — optional post-execution code quality pass on the implemented work. If the plan called for it, route through `/review-code` before reporting completion in Phase 4b.
- **`coordinator:plan`** — creates the plan that this command executes. A plan produced by that skill is the ideal input here.
- **`coordinator:workstream-complete`** — the natural next step after a plan is executed, offered (not auto-invoked) in Phase 4b. Caps the workstream: lessons, docs, workstream-complete review.
- **`coordinator:finishing-a-development-branch`** — **not** chained from here. Branch disposition (merge / PR / keep) is a separate, PM-invoked decision that reaches the keyword-gated `/merge-to-main`. The PM invokes it directly when ready to ship.
