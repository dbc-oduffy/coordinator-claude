---
name: execute-plan
description: "Executes a PM-approved plan via dispatched per-chunk executor waves."
allowed-tools: ["Read", "Edit", "Write", "Bash", "Grep", "Glob", "Agent", "Skill"]
argument-hint: <plan-path>
---

# Execute Plan — End-to-End Plan Execution

Run a PM-approved implementation plan **end-to-end to full completion** without stopping for permission between tasks. The PM's approval of the plan is the authorization — this command executes it diligently and in its entirety, commits the work, and reports. Here "PM approval" means the disk-persisted **plan-frontmatter `execution_authorized_at` stamp** (set on the plan document's YAML frontmatter by the reviewing session at the `coordinator:review` Exit gate, ONLY after the PM approves execution) — NOT an in-conversation utterance. A fresh execution session cannot rely on chat history; it reads this stamp as the authorization of record. Phase 1 reads and confirms the stamp is present before proceeding. Exception: in `/autonomous` mode (sentinel `/tmp/autonomous-run-${SESSION_ID}` present), the checkpoint was already bypassed at `coordinator:review`; execute-plan proceeds without the stamp-ask.
It does **not** chain into branch disposition (merge / PR / keep): finishing a development branch involves the PM-gated `/merge-to-main` and is a separate decision. The natural next step after the **last** chunk of the **last** phase ships is `/workstream-complete` (cap the workstream — lessons, docs, workstream-complete review), which execute-plan offers but does not auto-invoke. See Phase 4.

**Core principle:** Write-ahead every task (both plan document on disk AND task list via TaskUpdate), execute autonomously through every phase, **make every engineering decision the plan leaves to execution-time**, stop only on a genuine PM-only emergency (Phase 5). A task being hard, a sub-decision being non-obvious, or a workaround being needed are EM decisions — not stop conditions. **Phase boundaries are not stop boundaries**: when Phase N ships green, immediately dispatch Phase N+1 — do not pause to offer the PM a checkpoint, do not parrot `/workstream-complete` after a partial-phase completion.

**Stance — execute = restructure-then-dispatch.** Executing a plan is not "type the plan's steps." It is: read the plan, build the dispatch-gate graph (Phase 1.5), and then **decompose into per-chunk dispatches** — one executor per chunk, fanned out in parallel where the gates allow and run in sequence where they don't. Decomposition is unconditional; parallelism is only the time-overlap axis. **A serial chain is still N dispatches (a fresh agent per chunk, EM-verify between), never one long-lived executor walking the chain** — that bundling is the failure this skill exists to prevent. This whole shape is the fan-out methodology execution follows (Phase 1.5 § Mechanical step, below), not a separate command, and it governs serial waves as much as parallel ones (serial = depth-1 cohorts). The default outcome of executing is a **background Workflow** carrying that dispatched wave (one wave or many) — not hand-orchestrated `Agent` calls; see Phase 1.6 § Vehicle default.

**Self-execute vs. dispatch is a token-economics call, not a vibe.** A Sonnet executor burns ~¼ the tokens of an Opus EM doing the same edits, and finishes faster — so dispatch wins almost every time. Self-executing inline is the rare carve-out, justified only when you can name why it is genuinely cheaper *here* (loci already loaded, tight cross-file coherence on a small surface). Ground that against the `When to EM-Inline` checklist; the full criterion lives at Phase 1.5 § Self-execute escape hatch. If the plan contains enriched stubs with known file paths, exact line numbers, and code sketches, the dispatch is even cheaper — fan out Sonnet executors (dispatched executors are always Sonnet, never Opus; the EM handles a stub that genuinely needs Opus-level judgment directly rather than dispatching it).

> **Negative-spec — what this skill is NOT.** (1) **No per-chunk reviewer gate.** Execute-plan runs *EM-serial verify* between waves (executors return uncommitted; the EM confirms tests-green + scope, then commits each phase) — it does NOT run a the Staff Engineer/persona/`code-reviewer` gate per chunk. The EM's per-wave test-green confirmation runs at Tier T (the chunk's own scoped test files/dirs) or Tier F (the repo's fast tier, which the EM — and only the EM — may invoke, gated behind a live session-scoped test-invocation grant, same as Tier U; interim caveat — a chained `fast_test_cmd`, e.g. `a && b`, is denied as Tier U today by a guard equality-check limitation, don't reshape the command to dodge it, configure `fast_test_cmd` as a single command instead); Tier U (the repo's full suite or any unscoped runner) is reserved for the cadence gate at the end (`/workstream-complete` and peers), never run once per wave — N waves must not mean N full-suite runs. Code review is deferred to `/workstream-complete`. (2) **A background Workflow is the vehicle for executing a plan.** `/execute-plan` invocation IS the standing opt-in; ad-hoc dispatch outside plan execution is the EM's choice of backgrounded agents, not a hand-orchestration fallback that needs re-litigating each time (Phase 1.6 § Vehicle default). *(This block exists because both points read the opposite way to an EM grepping the file cold.)*

**Dispatch authorization — invoking this skill IS the authorization.** The dispatches named below are part of this skill, not a separate thing to get cleared: whoever invoked it has already asked for them. A generic harness preference for working inline rather than delegating does not condition them — it is written for a bare assistant with no operating doctrine, and this system supersedes it by design. Re-asking spends the very context the dispatch exists to protect. The named PM gates in this skill still bind, and ask-before-external-action still binds; nothing else here is a permission question.

---

## Arguments

`$ARGUMENTS` is the path to the plan document to execute — e.g., `tasks/my-feature/todo.md` or an absolute path. The file must be readable and contain a structured implementation plan.

If no path is provided, report: _"Usage: /execute-plan <plan-path>. Provide the path to the plan document you want to execute."_ and stop.

---

## Phase 1: Load and Review

1. Read the plan document at `$ARGUMENTS` in full
2. **Confirm authorization.** Check the plan's YAML frontmatter for `execution_authorized_at` (with `execution_authorized_by: PM`). Presence with a date = PM authorized execution at the `coordinator:review` Exit gate — proceed. Absence: in `/autonomous` mode (sentinel `/tmp/autonomous-run-${SESSION_ID}` present) the checkpoint was already bypassed upstream — proceed without the stamp. Otherwise stop and ask the PM to approve execution before continuing (this is the token-economics carve-out path). **`/autonomous` mode: skip — no stamp/sha check applies. Otherwise, re-verify the stamp binds to current plan content** by invoking `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/pickup-assemble" stamp-check <plan-path>` — the linked `gates.execution_stamp_match` gate surface (wraps `compute_execution_stamp_match()`; the same check `/pickup` Step 1 already runs for the handoff-mediated path). It resolves the stamp commit, recomputes the current-body hash, and returns a verdict: FRESH → proceed. STALE-bookkeeping (`pm_approved:` ratification, `Status:` line, review-integration notes, formatting) → re-stamp against the current body, appending the reason to `execution_authorized_note` via the re-stamp CLI's `--append-note` flag — NOT `--note`, which replaces the field wholesale and would destroy the PM's verbatim authorizing words, then proceed. STALE-substantive, or unclassifiable (defaults to substantive) → surface the reported delta to the PM and STOP (do not execute). This call is defense-in-depth: it repeats `/pickup` Step 1's check here to catch the case where `/execute-plan` is invoked directly, bypassing `/pickup`.
3. **Session-freshness gate.** Runs after authorization is confirmed, before any executor dispatch.
   - `/autonomous` (sentinel `/tmp/autonomous-run-${SESSION_ID}` present) → SKIP this gate, proceed same-session (autonomous is same-session by design).
   - Else answer ONE factual question the EM can answer without introspecting context saturation: **did THIS session author/review this plan (same-session invocation), or did it pick the plan up fresh (fresh execution session — e.g. via `/pickup` of an execution handoff)?**
     - **Fresh session** → proceed to execute at ANY plan size. This is the intended default path; the ≤3-task bound stated in the Same-session bullet below does NOT apply to fresh sessions.
     - **Same session that authored/reviewed this plan** → this is the token-economics carve-out. Permitted ONLY if BOTH (a) no auto-compaction has occurred in this session yet AND (b) the plan's task-spine is ≤ 3 tasks. If both hold → log the carve-out to the flight recorder (plan-size + compaction-count) and proceed same-session. If EITHER fails → STOP, do NOT execute here: the plan is already stamped, so write an execution handoff via `/handoff` and stop — a fresh session picks it up and runs `/execute-plan`. Announce: _"This session isn't fresh enough to execute cleanly (compaction occurred / plan has >3 tasks) — handing off so a fresh session executes."_
4. Review it critically — identify any gaps, ambiguities, or concerns:
   - Missing file paths or unclear scope?
   - Steps that assume context not captured in the plan?
   - Dependencies on external state that may have changed?
   - Anything that would require an architectural decision mid-execution?
5. **Resolve concerns at EM altitude.** If a concern is mechanical (unclear path → grep; ambiguous default → pick the better one and note rationale in the plan body; missing context → dispatch a read-only scout), resolve it and continue. **The execute-plan invocation is not the moment to surface EM-resolvable concerns to the PM** — that's planning work that should have happened at `/plan` time. If a concern reveals that the plan is *not actually executable* (see Phase 1.4), bounce back to `/plan` — do not start a half-executable plan.
6. Announce _"I'm running `/execute-plan` to implement this plan end-to-end."_ and continue to Phase 1.4.

---

## Phase 1.4: Executability Gate — Refuse Plans That Aren't Actually Plans

Before building the gate graph, the plan must clear an **end-to-end-executable** check. A plan that contains an embedded decision gate, a fact-finding stub with no fix-locus, or a downstream phase whose chunk shapes are undecided is planning work masquerading as execution work — bounce it back to `/plan`.

**Refuse-to-execute signals** (any one is sufficient — stop and route back to `/plan`):

| Signal | What it looks like in the plan body |
|---|---|
| **Embedded decision gate** | "Evaluate X before continuing", "spike Y then reconsider", "decide N at chunk-write time" where N is a non-mechanical architectural choice (which module, which seam, which paradigm), "Phase 0 — investigate", "TBD pending Phase 1 outcome" |
| **Fact-finding chunk with no fix-locus** | A chunk whose deliverable is a recommendation, a report, or "options for Phase 2", rather than code/config/doc landing at a named path |
| **Unpopulated downstream wave-map** | The wave-map (or `## Tasks` spine) has entries for early phases but later phases appear as `TBD` / a prose paragraph instead of concrete entries |
| **In-prose deferral of EM-resolvable decisions to the PM** | "PM to decide between A and B before Phase 2" on a choice that is engineering-tactical (file split, helper naming, refactor mechanics, internal sequencing). PM-altitude product decisions (privacy, user-visible behavior, external trust surface) are legitimate; engineering decisions are not. |
| **Open questions that gate execution** | An `## Open questions` section whose answers determine whether downstream chunks can be authored at all (vs. flagged-for-reviewer-challenge, which is fine — the reviewer's already run by the time execute-plan fires) |
| **Unbuilt external prerequisite** | A chunk's write target, verification, or acceptance criterion depends on an artifact, API, or contract owned by another repo/team that does not yet exist and carries no landed commit/date — the chunk is mechanically authorable today but cannot reach a terminal `done` state, because "done" is defined by someone else's unshipped work |

Five of the six signals above test *authorability* — can this chunk be written and dispatched today. The external-prerequisite signal instead tests *reachability of done* — even a fully authorable chunk refuses if its terminal state depends on someone else's unshipped work with no landed commit/date to point to.

**What is NOT a refuse-signal:**
- A `Phase 0` that ships independently valuable code (a prereq chunk) with a populated wave-map — that's a normal phase, not a decision gate.
- A chunk whose brief says "resolve the exact list of methods at chunk-write time from `<file>:<line>`" — that's mechanical lookup, not architectural decision.
- A reviewer-named `## Open questions for plan review` block carrying EM-decided defaults — those resolved at plan review, the block is paper trail.
- A future-phase chunk whose write-files are pinned but whose internal implementation is sketched — execution refines the sketch.
- A chunk depending on external work that has already landed — cite the commit/date and proceed; the signal is for *unshipped* dependencies, not shipped ones cited for provenance.

**Action on a refuse-signal:** Stop, name the specific signal verbatim, and tell the PM: _"This plan contains <signal> at <location>. That's planning work, not execution work. Routing back to `/plan` to resolve before execute-plan can dispatch end-to-end."_ Then invoke `coordinator:plan` on the gap.

---

## Phase 1.5: Dispatch-Gate Graph

This phase is the EM's named responsibility at the seam between plan-approved and first executor dispatch. It applies whether execution is direct (Phase 3) or via dispatched executors — the gate-graph is identical in either case.

**Four real gate types** determine what can run concurrently vs. must be serial (narrative causality, aesthetic ordering, and "I'd rather review A before B" are NOT gates):
- **File-write overlap** — two tasks edit the same path.
- **Output-consumption** — Task B reads a file Task A writes.
- **Contract-change dependency** — Task A bumps a schema, helper signature, or shared surface Task B depends on; promote shared-API work to a predecessor wave.
- **Epistemic/premise gate** — Task A decides whether Task B's chunks should EXIST AT ALL (not merely what their interface looks like). See below — this one gates *authoring*, not verification, and takes its own predecessor wave.

**Output-consumption and contract-change gate *verification*, not *authoring*.** When B's only dependency on A is consuming its output or contract, B can be *authored* concurrently with A if the interface is pinned (the full signature written down, precise enough to author against without asking the producer) — only B's green-verification waits for A to land. File-write overlap and the epistemic/premise gate are the two unconditional gates on *authoring* with no verify-at-merge escape hatch — distinct from `output-consumption-runtime`'s unconditional seriality on *execution* (see the discriminator table and "genuine serial case" below). Default to concurrent-with-pinned-interface, verify-at-merge: pin the interface, fan out producer + consumers in one wave, verify at merge. Hard gate: no pinnable interface → fall back to predecessor-wave shape.

**The epistemic/premise gate — a predecessor that decides whether the successors should exist.** This is distinct from output-consumption and contract-change, and the concurrent-with-pinned-interface default does NOT reach it. Its defining properties:
- It gates **authoring**, not merely verification — unlike `output-consumption-content` and `contract-change`, where authoring can proceed concurrently against a pinned interface and only verification waits.
- Concurrent authoring with its successors is **forbidden**, because an unproven premise has **no interface to pin yet**. The pin-and-verify-at-merge default is conditioned on pinnability; a premise still in question has nothing pinnable — there is no signature, schema, or contract to write down, because whether the successor chunks should be authored at all is exactly what is undecided.
- A premise/epistemic gate therefore takes its own **predecessor wave**: it must land, and its verdict must be read, before any successor chunk is even drafted for dispatch — not just before its execution/verification.

Example: a chunk that investigates whether a proposed refactor's premise holds (e.g. "does this abstraction actually eliminate the duplication the plan claims?") gates every chunk that would build on that abstraction — if the premise fails, those chunks shouldn't be authored at all, not just re-verified.

This gate type discharges, at the plan-execution altitude where it actually binds, the doctrine-rule leg of a ratified lesson's `how_to_apply(4)`: "gating chunk ships alone in its own authorized wave."

**Peer-scope discipline.** Concurrent executors see disk state, not each other's intent — a parallel executor may "helpfully" extend scope onto a peer chunk's not-yet-landed output. Every dispatch prompt in a parallel wave must carry an explicit In-scope / Out-of-scope block naming peer chunks by ID (including the plan document's own `status:`/`progress:` frontmatter, which is EM-owned, never executor-owned); `fan-out-dispatch.py` injects this automatically.

**Step 0 — Acquire the plan execution claim (fail-loud on live peer or infra error).**

Before any reconcile or gate-graph work, acquire an exclusive execution claim for this plan. This is the fail-loud *prevention* layer above the detect-after-the-fact reconcile below: the reconcile catches a peer that legitimately took a disjoint remainder; this claim catches a peer that is actively driving the SAME plan right now, before either session burns tokens on duplicate review/dispatch work.

Compute the plan's slug from its filename stem (basename minus `.md`). Invoke `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/session-claim-cli" claim-plan <slug>`, capturing its combined stdout+stderr and exit code.

On success (exit 0), proceed to record the active session (below). On a non-zero exit — EITHER live-peer contention OR an infra error (no session id, etc.) — pipe the captured combined output into `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/misc-session-and-guards" claim-classify` (reads the captured output on stdin). That subcommand echoes the `STOP: plan claim error — execute-plan halted.` banner plus the raw output to stderr, prints `peer-contention` or `infra-error` to stdout, and always exits 1 — the caller (this step) treats a claim `rc!=0` as fail-loud either way; the classification only tells the EM which failure kind it is. If `peer-contention`, reconcile with the peer session before dispatching — do NOT race. If `infra-error`, surface the raw message and stop; do not mis-report it as a phantom peer.

On the successful claim path (rc==0), record the active session into the plan's `agent_sessions:` frontmatter (ccos-2) via `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/append-plan-session" "$ARGUMENTS"`. This call is advisory/best-effort and never aborts plan execution — treat a non-zero exit as a non-fatal warning (_"warn: append-plan-session failed (non-fatal); session link not recorded."_), not a plan-execution blocker.

`session-claim-cli claim-plan` trampolines into `coordinator_core.session.claims.claim_plan`, which wraps `claim_artifact("plan", ...)` and carries the full claim machinery: dead-PID reaper, inline stale-takeover, and TOCTOU guards. Two behavioral properties matter here:

- **Re-entrant for the same session** — if this session already holds the claim (e.g. re-entry after compaction or a second pass through Phase 1.5), `claim-plan` returns 0. Re-entry after compaction is safe: a compacted session gets a fresh session-id, so the stale claim is reaped and taken over cleanly rather than re-entered.
- **Fail-loud on a DIFFERENT live session** — non-zero + stderr naming the holder. If stderr contains "held by session", a peer EM is actively driving this plan: reconcile with it before dispatching, do not race. Any other non-zero indicates an infra failure (unresolvable session-id, git-root error, etc.) — surface the raw stderr and STOP; do not mis-report an infra failure as a phantom peer.

The claim is released at the two clean terminals: `workstream-complete` (plan capped and shipped) and `/handoff` (deliberate PAUSE). Do not re-implement release logic here — cross-reference those terminals (C4 and C5 of the plan).

Note: this step dogfoods the very primitive `claim_plan` ships — the execute-plan skill is its first consumer.

**Execute-time premise/overlap reconcile (before gate-type discrimination).** Plans drafted hours or days ago may be invalidated by work that concurrent EMs shipped in the interval. Before classifying gates, `git fetch --quiet` and diff the plan's `write-files` against commits landed since the plan-draft date (`git log --oneline --since="<plan-draft-date>" -- <write-files>`).

If any write-file has been touched by a commit not in this session, reconcile before fan-out: verify the plan's premise for that file still holds (the function/schema/path the plan assumes still exists in the expected shape), adjust the affected chunk brief to account for the landed work, and note the reconciliation in the wave-map. **Do not dispatch on a plan whose substrate was modified by a concurrent EM without checking.** The pickup Step 1 (Classify, Load, and Reconcile Against Reality) premise-verification catches this at handoff time; this step catches it at execute time for plans dispatched in the same session they were authored and for re-entries after compaction. [source: queue-triage-2026-06-21 chunk-3, queue line 86]

**EM-judgment step 1 — Gate-type discrimination (helper cannot do this):** Classify every task-pair relationship as one of the four gate types above, or as truly independent. The helper detects file-write overlap automatically; output-consumption, contract-change, and epistemic/premise dependencies require EM reading the plan's per-task scope. Do not outsource this classification — the helper sees file paths, not semantic contracts.

**Build the wave shape from the file-write graph, NOT from the plan's section/phase/cluster structure.** Plans are written for *readers* — grouped by theme, by subsystem, by narrative arc. Those are reader-axes, not dispatch-axes. The mechanical step at the top of wave-map construction (Phase 1.6) is: enumerate every write-target the plan touches, group by *write-overlap*, then map chunks onto the resulting lanes. A plan with 6 thematic clusters across ~6 disjoint file-lanes is **one parallel wave of ~6 lanes**, not 6 sequential phases — even if the plan document presents the clusters as Phases 1–6. **Recurring failure mode:** mapping the plan's narrative phases directly onto execution phases and serializing them. The fix moves the discriminator into the **Phase 1.6 `gate-kind` discriminator** so the artifact, not the EM's discipline, is what fails-loud. Recheck before dispatching: for each gate you imposed, name its kind (`none` / `file-write-overlap` / `output-consumption-content` / `output-consumption-runtime` / `contract-change` / `epistemic-premise`); `file-write-overlap`, `output-consumption-runtime`, and `epistemic-premise` actually gate *authoring*. Anything else gated as a serial dispatch is malformed by default — see Phase 1.6 § gate-kind discriminator.

**EM-judgment step 1.5 — Shared-Expensive-Substrate (SES) detection (helper cannot do this):** Before sizing chunks, scan the draft chunk set for a shared expensive read-surface that would cause every fresh executor to re-pay the same exploration tax in full. Failure mode prevented: N fresh executors each spending their entire budget re-exploring a shared unfamiliar substrate and writing zero lines.

**Compute each chunk's read-set** — the files it must *understand* to author (distinct from its `write-files`). Derive the read-set from the chunk's brief, plan "read first" lists, or reference sections. The read-set DERIVATION is EM judgment (extracted from chunk context, not from a tool); only the threshold EVALUATION on the derived set is mechanical.

Evaluate the SES predicate: (1) **Shared** — same source file in the read-set of ≥2 chunks; AND (2) **Expensive** — a cold-substrate signal (shared read-set files unfamiliar/unloaded this session) OR a `needs-bespoke-fixture` chunk; count-based signals are secondary. **Brief-authoring companion rule — pin the spec, never go-read:** executor briefs for exploration-heavy work MUST pin the spec inline (literal CLI signatures, algorithm pseudocode, fixture template) rather than instructing "read the source files"; a "go read" brief is an instruction to spend the budget exploring.

**On a SES fire — enrich-once routing (do NOT dispatch per-chunk executors directly):**

1. Dispatch **one** enrich-once pass: set `enrich_once: true` in the dispatch brief to activate the enricher's Enrich-Once Decomposition Mode (`enricher.md § Enrich-Once Decomposition Mode`). The extended enricher reads the shared substrate once and emits, into a `## Enriched Dispatch Stubs (enrich-once)` section in the plan body, (a) **pinned per-chunk stubs** — exact CLI signatures, `file:line` loci, algorithm sketch — and (b) a **proposed chunk-boundary block** (NEEDS_COORDINATOR format — the EM ratifies). The enricher *proposes*; the EM *decides*.
2. When any chunk is flagged `needs-bespoke-fixture: true`, dispatch a **separate verify-capable executor** alongside the enricher (as part of the enrich-once pass) to produce AND certify-passing the worked fixture template. The read-only enricher cannot run tests and does not author the fixture (`enricher.md § Tools Policy`); an unverified fixture propagated to N executors is strictly worse than re-exploring (every executor inherits the same latent break).
3. The **EM ratifies** the proposed boundaries, authors the Phase 1.6 wave-map, then dispatches per-chunk executors against the pinned stubs. Those executors *only type* — near-zero exploration. The exploration tax is paid once (by the enricher) and its product survives to every executor.

**SES does not modify the decompose-unconditionally mandate.** It inserts a pre-dispatch enrichment wave; per-chunk decomposition still proceeds at Phase 1.6 after the EM ratifies the enricher's proposed boundaries. The enricher proposes and enriches; the EM authors the wave-map and dispatches. SES is a cost signal, not a dispatch gate — chunks sharing an expensive read-surface still parallelize freely once they hold pinned stubs (disjoint write-targets are unchanged).

**EM-judgment step 2 — Budget-sizing (helper cannot do this):** Aim for ~5–10 min per executor on a single coherent surface, 15 min hard ceiling. **Rule of thumb: a series of small-remit executors beats one executor with a large remit — in parallel where the gates allow, in sequence where they don't.** The budget axis is **orthogonal** to the parallelism gates above: file-overlap answers *can these run concurrently*, NOT *how many dispatches*. When overlap (or output-consumption, or contract-change) forces serial execution, apply the budget check independently at each serial position — `"can't parallelize" ≠ "one dispatch."` Over-budget coupled work chunks into a **fresh agent per chunk** (`dispatch B2 → EM verifies → dispatch fresh C1 → EM verifies → dispatch fresh C2/D`), never one agent handed chunk after chunk.

**Within-wave width check (checkable count, not appetite):** a single wave with **more than 5 write-capable executors** chunks into sub-waves of ≤5. This is a checkable count, **not a flat agent-count cap**: write-capable sub-waves carry write-contention / commit-serialization pressure on the shared branch that read-only or cheap-leaf-worker waves don't, so 5 (paired with the wiki's "≤5 files per executor" guidance) is the right bound specifically for the write-capable case. Cheap leaf-worker width (read-only scouts, mechanical verifiers, no shared-branch write contention) stays unbraked by this check.

**Mechanical step — follow the fan-out methodology:** Once gate-type discrimination and budget-sizing are done, **follow the canonical fan-out methodology** (Step 0.5–4, spelled out just below). Fan-out is a methodology execution follows, **not a skill to invoke** — there is no `/fan-out` command. This Phase 1.5 *is* the plan-mediated entry to that methodology.

Compile the wave spec (one TSV row per chunk: `<chunk-id>\t<brief>\t<comma-separated-files>`) from the gate-graph analysis above, then walk the methodology's steps: **Step 0.5** fan-out suitability gate (HARD STOP — re-chunk any fat chunk before dispatch), **Step 1** run `fan-out-dispatch.py` for the overlap pass + scoped-prompt compilation (hard-stop on collision), **Step 2** organic ramp, **Step 3** dispatch the compiled blocks via `Agent` (`mode: "auto"`, all concurrent) — but the **default vehicle for these blocks is a background Workflow**: encode the wave-map as Workflow `phase()`/`agent()` calls and fire it (survives your compaction, deterministic gates); plain concurrent `Agent` dispatch is the licensed carve-out for a genuine single wave you will finish in one uncompacted pass, and is REQUIRED (not merely licensed) whenever a chunk's agent depends on its `contract_blocks` prose — see Phase 1.6 § Vehicle default QUALIFIES list, **Step 4** EM-serial commit. **Do NOT duplicate wave-map logic here** — the helper + the wiki methodology are the single source for that ceremony.

> **One line stamps a conformant, green-by-construction `Workflow` skeleton — no boilerplate to hand-write.** `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-doc-new" --type workflow --name <kebab> --description "<line>" --phase "Title::Detail" [--phase ...] --out <path.mjs>` gives you the `phase()`/`agent()` shape ready to fill in against the wave map; worth reaching for before hand-authoring one from scratch.

**Self-execute escape hatch — gated on token-economics, not vibe.** The default is to dispatch. **Self-execute only when you can articulate why it is genuinely cheaper *here*** — e.g. the loci are already loaded in your context and re-loading them into N executors would cost more than typing, or cross-file coherence across a small surface is the dominating constraint. Ground that articulation against the concrete `When to EM-Inline` checklist (fix-locus ≤3 files / <60s on a >30k-file repo / mechanical / context-already-loaded / mid-edit-hazard) — "articulably cheaper" is self-graded by the same agent that wants to skip the work, so the checklist is the guard. **Self-execute is the one path that skips the Step 0.5 suitability gate** (the EM holds the gate in its own judgment instead). The gate-graph still applies either way. Self-executed chunks still appear in the Phase 1.6 wave-map as `inline (EM)` entries — one entry per chunk, never a bundle. The escape hatch requires ALL `When to EM-Inline` checklist criteria above to hold simultaneously — a favorable wall-clock estimate alone is not sufficient. When the EM takes an authorized inline carve-out, it writes the session-scoped sentinel file `/tmp/coordinator-dispatch-nudge-ok-${SESSION_ID}` so the dispatch-nudge PreToolUse hook stays silent for that authorized inline work.

---

## Phase 1.6: Wave-Map Authoring — Mandatory Pre-Dispatch Gate

> **Vehicle default — author the wave-map AS a Workflow, not as plan-body prose you then hand-orchestrate.** Per CLAUDE.md § Subagent Dispatch, a background Workflow is the vehicle for executing a plan — one wave or many; ad-hoc dispatch outside plan execution is the EM's choice of backgrounded agents (a base-harness backgrounded `Agent` call, self-limiting in scope). Workflow doctrine concentrates at `/execute-plan`: this is where it's checkable, one wave or many. The Workflow script IS the wave-map; its `phase()`/`agent()` calls ARE the decomposition contract. Do NOT default to hand-orchestrated `Agent` dispatch by talking yourself out of the Workflow with a rationalization that does not name a shape a Workflow cannot express (for example *"I need EM eyes on each wave"* — the Workflow returns each phase's results to you; or *"I control the commits"* — executors return **uncommitted**, you commit each phase serially; neither is surrendered). Hand-orchestration is licensed only when you can name a concrete reason a Workflow cannot express the shape; the `NUDGE-MULTIWAVE-WORKFLOW` hook is a bounded burst OFFER (once per session, burst-triggered) that leads with what a Workflow gives and blesses the ad-hoc alternative — not a backstop-enforcer, and not an authorization override.
>
> **QUALIFIES:** a shape a Workflow genuinely cannot express — e.g. a mid-run pause for interactive PM input that gates the very next dispatch, or a tool only the main-loop (EM) can call. **A dispatch whose agent depends on its `contract_blocks` prose also qualifies: a Workflow `agent()` spawn is not an `Agent` tool call, so the injected blocks never arrive on that path** (measured, not theoretical — full mechanism and how to check a given `subagent_type` at `docs/wiki/dispatching-parallel-agents.md § Workflow-Spawned Agents Never Receive contract_blocks`). This is a named, legitimate QUALIFIES entry, not one more rationalization to resist — 32 of 33 coordinator-typed agents carry a `contract_blocks` row, so in practice a plan wave of coordinator-typed agents belongs on the `Agent` path until this seam is closed. It is a live defect being worked around, not a settled design — a future reader should delete this qualifier once the seam closes, not cement it. Workflow stays correct for shape/orchestration where the agents are contract-block-free, and for its other virtues (survives compaction, deterministic gates).
>
> **Not on the list — these do NOT license hand-dispatch:**
>
> - ~~A downstream step is EM-inline regardless~~ — does not preclude a Workflow for the *dispatched* chunks; scope the Workflow to those and run the EM-inline step after it returns.
> - ~~Small / few dispatches / one uncompacted pass~~ — the vehicle holds for a single agent (a one-`agent()` script) exactly as it does for a multi-wave plan; "small" is not a reason to hand-orchestrate.
> - ~~I want EM eyes between waves~~ — the Workflow returns each phase's results to the EM; structure the waves as phases. Not surrendered.
> - ~~I control the commits~~ — executors return uncommitted; the EM commits each phase serially. Not surrendered.
>
> The carve-out test is self-graded by the same agent that wants to skip the Workflow — exactly the hazard the `When to EM-Inline` checklist guards against for the self-execute hatch (§ Self-execute escape hatch above). This explicit list is the guard.
>
> **Seam discriminator — single Workflow is the default; segment into per-wave sub-Workflows only on a named reason.** A single Workflow carrying the plan's full wave-map is the default even across multiple waves. Segment into per-wave sub-Workflows ONLY when (a) a downstream wave's briefs **cannot be pinned from plan text** — the same interface-unpinnability test as the `output-consumption-content` gate (Phase 1.5 above), or (b) a **named EM decision branch** gates the next dispatch (an architectural fork the plan leaves open, resolvable only after an earlier wave's output lands). **"I want eyes between waves" is explicitly NOT a valid reason to segment** — a single Workflow already returns each phase's results to the EM (§ Vehicle default above).

> **Schema-coupling pointer:** the per-chunk write-overlap decomposition this wave-map consumes is the plan-author obligation in [`skills/plan/SKILL.md`](../plan/SKILL.md) § Branch B — fan-out-shaped chunking row. The wave-map here is the late-correction surface; the plan-author row is the prevention surface — no schema lives in two prose blocks.

**Before issuing *any* `Agent`/Workflow call, AUTHOR the wave-map AS the execution vehicle's own on-disk input artifact — never as a separate plan-body table.** On the default (Workflow) path, that artifact IS the background Workflow script itself (`phase()`/`agent()` calls) — one `agent()` per chunk from the Phase 1.5 gate graph. On the rare hand-orchestrated carve-out (§ DEC-1a), that artifact is the `fan-out-dispatch.py` TSV. **This is a disk write, not a chat emission.** A decomposition narrated to chat is ephemeral and the EM can rationalize around it mid-flow; the wave-map is the contract the EM dispatches against — crash-durable, and (for the Workflow path) re-readable after compaction via the script's own persisted, resumable state. It is the same write-ahead discipline as Phase 3a, applied to the dispatch decomposition — the difference is WHERE it is written, not WHETHER. The failure it prevents: the EM narrates an intent and then silently bundles several gate-graph chunks into one open-ended dispatch because they happen to be serial. A wave-map on disk makes that bundle visibly malformed before it is dispatched. There is no separate `## Dispatch Ledger` markdown table written into the plan body — the plan body stays PM-facing; the wave-map lives on the execution vehicle's own input surface.

**Chunk-SET derivation — the plan's `## Tasks` spine is the source of the WHICH-chunks-exist question; Phase 1.5/1.6 answer the HOW-to-dispatch-them question.** When the plan carries a `## Tasks` machine-parseable spine (the single fenced ```yaml plan-tasks``` block directly under `## Tasks`), the wave-map's starting chunk set is derived, not hand-enumerated: take every spine row with `deferred: false` (absent `deferred` defaults to `false`); each such row is one candidate chunk, identified by its `id`. **Deferred rows (`deferred: true`) are excluded from derivation entirely** — they are harvest candidates (see the harvest call-site below), never dispatch candidates. If the plan has no `## Tasks` spine (a pre-spine-format plan, or one still mid-authoring), fall back to hand-enumerating chunks from the plan body as before — the spine is an input when present, not a hard requirement of this phase.

**The derived set is a floor, not a ceiling — Phase 1.5 gate-graph analysis and the Phase 1.6 disjoint-write-target expansion rule (below) still run UNCHANGED on top of it, and MAY increase the `agent()`-count.** One spine task never yields fewer than 1 wave-map entry and, per the disjoint-write-target expansion rule, frequently yields more: a spine row whose `surface`/write-scope splits into K mutually-disjoint write-target groups still expands into K wave-map entries (K `agent()` calls) at wave-map-authoring time exactly as it would if hand-enumerated. **A literal 1:1 mapping from spine task to wave-map entry is itself malformed** — it would silently reverse the disjoint-write-target fix (§ below) by treating "the spine said one task" as license to skip the expansion check. Derive the candidate set from the spine, then run every existing Phase 1.5/1.6 rule (gate-type discrimination, SES detection, disjoint-write-target expansion, budget-sizing) against that candidate set exactly as if it had been hand-enumerated.

**`agent()`-count check (mechanical checkpoint, analogous to the `est-min > 15` rule below): the wave-map's final `agent()`-count MUST be ≥ the spine's non-deferred task count, and MUST exceed it whenever the disjoint-write-target expansion rule fires on any entry — a wave-map whose `agent()`-count == spine-task-count on a plan containing any multi-target `write-files` list is malformed; re-run the expansion check before dispatching.**

**Forward-reference — NOT-YET-WIRED (spec only, no live call-site today).** Once the foundations wave-map-derivation chunk lands (currently pending) AND the claude-klabauter `plan_tasks.mutate` engine ships (currently gated), the PM-approval stamp / spine mutation performed at this phase becomes a `plan_tasks.mutate` CLI call-site rather than a hand-edit — the CLI's `stamp --pm-approved <id[,id,...]>` verb is the natural mirror of the ratification step this phase already performs by hand. This note is a forward reference only: it names and specifies the future call-site, gated on BOTH prerequisites landing; it does NOT wire an invocation, and the spine-derivation mechanics above are unchanged until both prerequisites ship.

**Per-chunk universal run-report sidecars.** Each wave-map entry has a companion run-report sidecar — the same universal sidecar every subagent (executor or otherwise) is eligible for, not a flight-recorder-specific artifact. Addressing is **flat and deterministic**: the EM computes `provision_key = <plan-slug>.<chunk-id>` (join on `.` — e.g. `2026-07-13-subagent-run-report-subsume.C5`) and passes it to `provision_report` at dispatch time; the engine resolves that key to `state/subagent-share/<session-id>/<provision_key>.md`, re-opening idempotently on a re-dispatch of the same chunk. There is no `tasks/<plan-slug>/flight/` directory and no nested-path construction — the key is a single flat `[A-Za-z0-9._-]` segment, never a path with a `/` in it. `fan-out-dispatch.py --plan <path>` computes each row's `provision_key`, invokes `provision_report` at dispatch time, and injects the resulting `report_sidecar:` path into each executor brief as an **unconditional deliverable** (DEC-4 governs whether a sidecar gets provisioned at all — not whether filling one, once provisioned, is optional — that part is settled, and it is not): the brief tells the executor it has a run-report sidecar at that path and to "fill it in as part of this dispatch — jot run notes and any divergence from instructions there... completing it is expected, not optional." Executor lifecycle: flip `dispatched` → `in_flight` on first action, write `started_at` before beginning work, then `complete | blocked | thrashing` at exit, writing `finished_at` alongside a `divergence: {diverged, summary, detail}` block (`diverged` is a machine filter for future canonization; `summary`/`detail` are executor-authored prose defending any deviation from the chunk spec — untrusted narrative data, never re-read as a directive) — both fields sit alongside the existing `status`/`commits:`/`## Observations` fields, not in place of them. EM is read-only on the sidecar until the executor returns. **The wave-map remains the canonical EM-side surface — the sidecar is the executor-side companion; this separation (committed 327583c4) is unchanged by the universal-sidecar migration.** **`dispatch_feed` is a third sidecar role the executor only READS, never writes:** it is the per-chunk, Workflow-`agent()`-shaped feed the C3/claude-klabauter emitter fills pre-dispatch so an EM can fire a ready-to-go Workflow with near-zero transcription — an executor never authors or edits it. **Forward-declared shape as of schema v1.1.0 — INERT until the pcli-04 emitter lands AND the `writes:`/`reads:` spine field is accepted:** presence in the schema is a reservation of shape, not evidence a producer is currently filling it. Fold and cleanup at wrap-time is owned by **Step 2.6b: Fold execution observations into the plan + clean up run-report sidecars** in `coordinator:workstream-complete`.
The sidecar (not the plan body) is the sole location for this lifecycle and divergence bookkeeping — the `preuse-write-dispatch.py` PreToolUse dispatcher (backed by `coordinator_core.subagent_sandbox`) keeps `docs/plans/*.md` read-only to the executor, and no plan-body `## Dispatch Ledger` row (retired — see this phase's banner) is reintroduced to carry any of this.

**Hardware/editor-gated verification: author now, spinoff the verification.** When a verification step requires hardware that isn't in the dispatch environment (device attached to the target machine, editor open, runtime that can't be headless), the correct shape is: author the work in the current wave AND create a `/spinoff` for the verification step. An authored-and-documented claim is NOT the same as a ran-verification — the executor's DONE report must note which verifications were deferred to the spinoff and why. Failure mode to prevent: treating a deferred verification as complete at `/workstream-complete` without having actually run it. [source: queue-triage-2026-06-21 chunk-4, queue line 129]

**The `gate-kind` discriminator is the mechanical author/verify discriminator** — it forces the EM to name the dependency kind rather than writing `after #N` and never asking whether it gates authoring or only verification:

| Value | What it means | Does it serialize authoring? |
|---|---|---|
| `none` | Chunk is independent — no dependency on any other wave-map entry | No. Goes in the earliest possible wave. |
| `file-write-overlap` | The chunk writes to a path another chunk writes to | **Yes.** The only authoring gate; producer must land before consumer authors. |
| `output-consumption-content` | The chunk reads another chunk's output as static content (file text, schema, fixture) | **No** if the producer's interface can be pinned (signature/schema/path written down up front). Author concurrently; verification gates at merge. |
| `output-consumption-runtime` | The chunk needs another chunk's artifact to *exist at runtime* (e.g. a dry-run that exercises a not-yet-shipped pipeline) | **Yes.** Producer must ship before consumer can execute. |
| `contract-change` | The chunk depends on another chunk landing a contract change (rename, signature edit, schema migration) | **No** if the new contract can be pinned in writing up front. Authoring concurrent against the pinned contract; verification gates at merge. |
| `epistemic-premise` | The chunk depends on another chunk **deciding whether it should exist at all** — not just what its interface looks like | **Yes.** No interface exists to pin — the premise itself is unproven, so there is nothing to write down and author against. The gating chunk takes its own predecessor wave; successors are not even drafted for dispatch until its verdict lands. |

**The rule the discriminator enforces:** any wave-map entry with `gate-kind` ∈ {`output-consumption-content`, `contract-change`} gated as a serial `agent()` awaiting a predecessor's landing (illustrative shorthand for the Workflow-await shape, not a literal TSV/JS column — see the TSV carve-out clause above) is malformed by default — the EM must either (a) downgrade its dispatch classification to `parallel` (with verification deferred to merge against the pinned interface) or (b) record a one-line rationale why pinning the interface is infeasible *here*. The failure mode this catches: noticing "C2 needs C1's output" → writing "after #1" → never asking "is this authoring-gating or verification-gating?" **`epistemic-premise` is exempt from this malformed-set check** — it is legitimately serial by construction, belonging with `file-write-overlap` and `output-consumption-runtime` as an authoring gate, never swept into the pin-and-downgrade set: there is no pinnable interface to downgrade against.

**`output-consumption-runtime` is the genuine serial case** — the consumer's *execution*, not its *authoring*, depends on the producer. A dry-run that needs to invoke a real pipeline is the canonical example; a dispatch that reads a schema file is not.

**The invariant — one `agent()` per chunk, one chunk per dispatch:** one `agent()` call (or, on the hand-orchestrated carve-out, one dispatch) per chunk-id. The number of distinct dispatches (counting `inline (EM)` entries) **equals** the number of chunks. **If any single `agent()` call or dispatch spans more than one chunk-id, the wave-map is malformed — STOP and split before dispatching.** "These chunks are serial, so one executor can just walk them in order" is the exact rationalization this gate rejects: serial coupling removes *concurrency*, never *decomposition* (Phase 1.5 EM-judgment step 2; wiki § Coupling Rules Out Concurrency).

**Global-coverage verification is EM-owned, never a chunk-brief instruction.** A dispatch brief names and invokes only the chunk's own scoped tests (Tier T — the files/dirs the chunk authored or touched) — it MUST NOT name or invoke the repo's fast tier or full suite; a chunk brief carrying either is malformed, full stop, no exception for gated artifacts. When a chunk's `write-files` includes a gated artifact (a test file, registry entry, or oracle row that other chunks or the acceptance gate consume), the obligation this used to push into the brief moves up to the EM: after the wave's chunks land and Tier T is green, the EM itself runs the **global** coverage or registry check once, at the wave boundary, before committing the phase — this is Tier F if the global check is the fast tier, or Tier U if it is the full suite, and both now require a live session-scoped test-invocation grant before the EM invokes them (Tier U's cadence-only reservation is otherwise unchanged) — Tier F's chained-command caveat applies here too, see line ~19. This wave-boundary check is not one of the three implicit-grant ceremonies, so an ungranted refusal here is reachable in normal execution; on refusal, see `coordinator/skills/validate/SKILL.md` § Grant-consuming for the honest exits (ask the PM for a session grant, run under a ceremony that already holds the implicit grant, or defer and report the check skipped) rather than re-enumerating them here. Chunk-local green while the global registry is red is the failure mode this guards against: the new artifact doesn't register, the gate still fails, and the error surfaces only at workstream-complete. How to apply: (1) identify whether the wave writes to a registry / oracle / shared test fixture; (2) after the wave's chunks return, the EM runs `<global-coverage-command>` itself as part of its own wave-boundary verification — never delegated into a chunk brief; (3) if the global command is absent, note that gap in the wave's verification record rather than silently skipping. [source: queue-triage-2026-06-21 chunk-2]

**Disjoint-write-target expansion rule — applied AT wave-map authoring time, not after PM prompting.** Before authoring a wave-map entry, list every path in `write-files` for that chunk. **If those paths split into K mutually-disjoint groups** (no path in group A is co-edited with any path in group B by the chunk's own logic), the chunk fans out into K wave-map entries (K `agent()` calls) — one per group. A plan-chunk like "C7 — update three docs (A.md, B.md, C.md)" with three independent docs is **C7a / C7b / C7c**, three parallel entries, not one entry that walks them. The bar for keeping N disjoint write-targets in one entry is *tight cross-file coherence* the chunk's own brief names; thematic affinity ("they're all docs") does NOT meet it. Recurring failure: 9 parallel-safe chunks dispatched as 9 executors when 3 of them each owned 3 disjoint surfaces — the correct shape was 17.

**Plan-body-amendment chunks are NOT `coordinator:executor` work.** If a chunk's deliverable is editing a `docs/plans/*.md` body (reconciling plan text, applying a decision into the plan, editing a section — as opposed to shipping code/docs elsewhere), route it at wave-map-authoring time by what the input actually is, never reflexively to `coordinator:review-integrator`:

- **`coordinator:review-integrator`** — only when the input is reviewer findings already on disk in a sidecar. Findings handed inline in the dispatch prompt, rather than read from a sidecar, are an intake violation review-integrator is required to refuse — and a mechanical guard now denies that dispatch shape outright, so a mis-routed dispatch will not merely come back with concerns.
- **`coordinator:enricher`** — the default for plan-body maintenance that is not sidecar-findings application: recording measured results, PM decisions, and verified corrections into a live plan body or register. This is execute-time enrichment, the same gather-don't-decide discipline enricher already runs pre-execution, pointed at a later phase.
- **`inline (EM)`** — the narrow carve-out, gated by the `When to EM-Inline` checklist above (§ Self-execute escape hatch) — not a default fallback when the other two don't obviously fit. Research-plus-judgment plan maintenance during a long execution is exactly the context-expensive case that checklist exists to keep out of the EM's own context; do not pull it inline just because it touches the plan the EM is already looking at.

The `preuse-write-dispatch.py` PreToolUse dispatcher (backed by `coordinator_core.subagent_sandbox`) hard-denies executor plan-body writes — dispatching one there burns a dispatch and returns BLOCKED. Mark the wave-map entry's classification as `inline (EM)` or note the correct agent type in a dispatch annotation.

- **Each wave-map entry's dispatch classification** records its gate: `parallel` (same wave), serial (a fresh agent that fires only after its predecessor has landed *and* the EM has verified it on disk), or `inline (EM)` (the token-economics self-execute carve-out). On the Workflow path this is the `phase()`/`await`-gate structure around the `agent()` call, gated as a serial agent awaiting predecessor `// chunk: <id>` (the DEC-4 label convention — below); on the TSV carve-out the serial gate is NOT mechanized — the TSV schema carries no predecessor-ordinal column (verified against `fan-out-dispatch.py`'s 3-4 field input format); serial sequencing on that path is EM-judgment, expressed by dispatching the predecessor's row in an earlier wave and the successor's row only after the EM has verified the predecessor on disk, exactly as before any mechanization (DEC-1/DEC-4).
- **`est-min` > 15 on any entry → re-split that chunk before dispatch.** The per-executor ceiling is 15 min on one coherent surface; aim for 5–10.
- **A serial chain is N sequentially-dispatched entries** (`after #1`, `after #2`, …) — each a fresh agent on a clean context with EM verify-and-commit between, **never one long-lived executor**. This still routes through the fan-out methodology's Step 0.5 suitability gate; serial just means depth-1 cohorts.

**Runtime tripwire — the EM owns the clock.** If any dispatched executor runs past ~15 min wall-clock, that is a dispatch-sizing failure surfacing late: **stop it, recover partial work from disk (it persists — shared working tree), and re-split into fresh per-chunk dispatches** (add the split rows to the wave-map on disk). Do not wait for it to finish, and do not wait for the PM to flag the runaway.

**A background Workflow is the vehicle for executing a plan** (see banner above); ad-hoc dispatch outside plan execution reverts to base-harness backgrounded `Agent` calls, the EM's choice when a Workflow doesn't fit the shape. Whether the plan carries one wave or many, or any plan the EM cannot drive to completion in one uncompacted session pass, **default to a background Workflow script** — do NOT grind ad-hoc serial `Agent` waves, and do NOT stop to ask the PM for a separate opt-in. **The `/execute-plan` invocation IS the standing opt-in for the Workflow vehicle.** The Workflow tool's own gating recognizes "the user invoked a skill or slash command whose instructions tell you to call Workflow" as a valid opt-in source alongside `ultracode` and explicit request — so this instruction satisfies that gate directly; the PM saying `/execute-plan` on any plan is the authorization, and a second ask re-litigates a settled decision (false-choice anti-pattern). The wave-map IS the Workflow's own input: wave groups transcribe directly onto workflow `phase()` groups, and the `gate-kind` discriminator maps onto serial `await`/`if`-gate constructs vs. `parallel()` fan-out in the script. Each `agent()` task observes the same ≤~10 min sizing ceiling this discipline enforces. **Serial/ad-hoc `Agent` dispatch is the carve-out, not a co-equal default — licensed only when the EM can name a concrete reason a Workflow cannot express the shape, or for genuinely non-plan work.** (The Workflow tool is a standard Claude Code capability present in every session — do NOT gate on "is it available"; it is.) **Every `agent()` call in the workflow script MUST set `model: 'sonnet'` explicitly** — the Workflow default inherits the session model, so on an Opus session an un-modeled fan-out runs entirely on Opus (~4x burn). Sonnet is the default for all workflow agents (porters, executors, per-wave commit agents, mechanical verifiers); Opus is rare and PM-gated — surface the intent and get explicit approval before launching any Opus-tier workflow agent.

**Crash/compaction-recovery surface (DEC-2) — no recovery gap.** The retired plan-body table's cited virtue was "re-readable after compaction to see which chunks shipped." Its replacement is a named triple, not a single surface:

1. **Git commit log by chunk-id prefix** — `git log --oneline -- <plan-path>`; a subject beginning `<chunk-id>:` means that chunk shipped. This is already the co-equal closure signal at `pickup` Step 1 (Classify, Load, and Reconcile Against Reality).
2. **The Workflow's own resumable script** — persisted to the session dir automatically, re-readable after compaction, and resumable via `resumeFromRunId` (cached `agent()` results replay rather than re-running).
3. **The Task-list flight recorder** (Phase 2 below) — persists through compaction by design.

After a crash or compaction, re-derive "which chunks shipped" from this triple — never from a re-read of a plan-body table, because none exists.

**DEC-1a — the single-chunk carve-out (named, not a silent gap).** Any hand-orchestrated dispatch of MORE THAN ONE chunk MUST emit an on-disk wave-map — either the Workflow script or the `fan-out-dispatch.py` TSV; there is no third door for a multi-chunk bundle. A genuinely SINGLE-chunk inline-EM / self-execute dispatch — already gated on the When-to-EM-Inline checklist (≤3 files, context-loaded, mechanical) — is EXPLICITLY PERMITTED to have no separate on-disk wave-map, because a single chunk cannot itself be an under-decomposed multi-chunk bundle: the malformed-bundle-visibility guarantee this phase exists to enforce is vacuous for it. This is a justified, named carve-out, not a hole in the discipline. A serial CHAIN of single-chunk dispatches (N ≥ 2 against the same plan) is NOT covered by the single-chunk exemption — each dispatch being individually one chunk does not exempt the sequence; the chain of 2+ hand-orchestrated dispatches is itself the decomposition and still requires an on-disk wave-map (the DEC-4-labelled Workflow phases, or the fan-out-dispatch.py TSV), consistent with the "serial chain is N sequentially-dispatched entries" bullet above.

**DEC-4 — every `agent()` call MUST carry a greppable chunk label.** Every `agent()` call in the Workflow-script wave-map MUST carry a greppable `// chunk: <id>` label (or an equivalent `label:`/`phase:` naming that encodes the chunk-id), so "one `agent()` per chunk-id" (the invariant above) remains mechanically greppable, and so the DEC-3 repointed `classify-dispatch-shape.py` observer has a greppable Workflow-path signal to read. Trade-off named honestly: a free-form script is not statically checkable the way a grep-parseable markdown table row was — the `// chunk:` label is what recovers that checkability.

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

**That license covers a fork you resolved, never a residual you didn't.** Work this plan will not close — a site the sweep missed, a fix wider than the AC — has a closed exit set: dispatch it, add a spine row for the Phase 4 harvest, `coordinator-queue-append --schema bug-backlog|debt-backlog|improvement-queue`, or take it to the PM. Plan prose may accompany any of those; it is never the disposition. Nothing reads a plan body once it stamps `implemented`, and the harvest selects on spine rows — so a residual discovered mid-execution isn't one, and `Queued 0` reads as "nothing was left behind."

**Named wrong action — plan-body-only discharge.** A residual written up with a reason and no queue id, spine row, or commit behind it. It survives review because it feels like diligence: *a written reason is what a routed item carries, never what routing it consists of.*

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

- ~~Accumulating patches~~ — re-split the remaining wave-map entries and continue.
- ~~Ambiguity spreading~~ — resolve by EM judgment with rationale in the plan body, or dispatch a read-only scout for substrate evidence.
- ~~Structural verification failure~~ — root-cause via `/systematic-debugging`, fix at source.
- ~~Routine fixable errors~~ — fix and continue.
- ~~Minor judgment calls~~ — make the call, note it, continue.
- ~~Wanting to check in~~ — not a reason; status lands in commit messages and at Phase 4.

**When you do stop (one of the five above):** Record in both the plan document AND the relevant task's `metadata.tried_and_abandoned` field (via TaskUpdate) what was tried and why it failed. Format: `"Tried: [approach] — Failed: [reason]"`. Surface to the PM with a recommendation, not a question — _"I think we should X because Y — want me to proceed?"_ beats _"X or Z?"_

---

## Phase 4: Finalize and Report

**Precondition: every chunk in the wave-map has landed a commit.** Confirm via the DEC-2 recovery triple (Phase 1.6): git-log-by-chunk-id (`git log --oneline -- <plan-path>`, expecting a `<chunk-id>:` subject per chunk) and the Task-list flight recorder. If any chunk has no matching commit and no flight-recorder `completed` mark, return to Phase 3 and dispatch the remaining chunks.

**Harvest call-site — before any cleanup phase.** With the wave-map's chunks committed, invoke the deferral harvest against this plan, before any wrap/cleanup step (including the `/workstream-complete` offer below):

`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-harvest-deferrals" --plan "$ARGUMENTS"`

This parses the plan's `## Tasks` spine and selects deferral candidates for harvest, then routes each by `change_kind` to `coordinator-queue-append` (improvement-queue-eligible kinds) or `coordinator-lesson-promote` (doctrine-class kinds) — idempotent on `(plan_id, task id)`, so a re-run after a prior harvest is a no-op for already-queued rows. **Which rows are candidates depends on whether the plan is governed** (its frontmatter carries a `grouping_approvals` key — bare presence, nothing else) **or legacy** (no such key): on a governed plan, a candidate is a row with `disposition: backlogged` whose `defer` grouping reads `status: approved` with a digest matching a fresh recomputation over the spine's current membership — the per-row `pm_approved` flag is not consulted at all. On a legacy plan the harvest keeps the prior rule: `disposition: backlogged && pm_approved: true`, or — for a row carrying no `disposition` field at all — `deferred: true && pm_approved: true` read-tolerated as the legacy-equivalent shape. Surface its one-line `"Queued N deferred items: ..."` output in the completion report (item 2 below). If the plan has no `## Tasks` spine, the harvest call is a no-op — skip silently rather than treating its absence as a blocker.

**A `defer` grouping approval — or, on a legacy plan, `pm_approved: true` — is a claim of ratification, not proof of one; do not stamp either here.** The harvest selects on that state, so whoever sets it decides what gets promoted; an approval the executing agent grants one command earlier is a gate checking its own output. If a row needs to close mid-execution, the cut goes to the PM for an answer before the grouping is approved (or, on a legacy plan, before the flag is set) — **the plan's execution authorization does not extend to it.** Authorization to build what the plan says is not approval of a scope decision the plan makes afterwards, and closing a row is a scope decision. The same holds for a changed deliverable. An EM concluding the PM would have approved is exactly what this step must not launder into the queue.

**Non-zero exit disposition:** if the harvest command exits non-zero — a row failed to write to its target seam, or a `pm_approved` row carried a `change_kind` that routes nowhere and was skipped — surface the failure in the completion report alongside the queued-count line. **A `Queued 0` run can still be a failure**; read the exit code, not the count — do not silently swallow it, and do not block the completion report on retrying it (the harvest is best-effort and idempotent; a fresh `/execute-plan` re-entry or manual re-run will retry the failed rows).

**Execute-plan ends here — it does not chain into branch disposition.** Implementing a plan is EM-remit engineering work; deciding what happens to the branch (merge / PR / keep) reaches the PM-gated `/merge-to-main` and is a separate, PM-invoked decision.

### Phase 4: Commit, Report, and Offer the Next Step

1. **Commit the chunk work yourself, THEN close out and stamp.** These are two separate commits by construction — `close-out-and-stamp` does NOT commit your code.

   **`close-out-and-stamp` stages exactly one path: the plan document.** Its `stage_paths` is a literal `[plan_path_rel]` — the plan's own `status:` frontmatter is the only thing the op ever writes, so the plan path alone is its complete, defensible scope. It never auto-detects a broad scope and never sweeps a peer session's concurrently-dirty files. **Negative-spec — it does NOT stage "every changed path plus the plan doc."** That phrasing described a superseded draft, is contradicted by the op's own docstring, and reading it either way costs you: believing it commits your code leaves the code uncommitted, and believing it sweeps peer files talks you out of a safe tool on exactly the shared-branch repos where it is safest.

   So the Phase 4 sequence is:

   - **First, land the chunk work in your own scoped commit(s)** — explicit pathspec over the paths your wave-map's chunks actually touched (`git add -- <paths>` / `git commit -- <paths>`, or `ceremony.scoped_git_commit`). **Never `git add -A` / `git add .` / `git add --all`**, per coordinator scoped-commit doctrine (`docs/wiki/scoped-safety-commits.md`); the `preuse-bash-dispatch.py` PreToolUse hook enforces this independently. On a shared branch, drop any path you did not write from the pathspec rather than reverting it.
   - **Then invoke** `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/close-out-and-stamp" "$ARGUMENTS"` (naked Python; runs the commit in-process via `run_commit_pipeline`, not by shelling out to `coordinator-safe-commit`) to stamp and commit the plan doc:
     - **Full-plan-shipped path** (every chunk committed — the DEC-2 recovery triple confirmed above): stamps the plan's frontmatter `status:` to `implemented` (guarded — only non-terminal source statuses flip; already-`implemented`/`superseded`/`abandoned`/`deferred` is a no-op, so safe to re-invoke even if a prior run already stamped this plan), then commits the plan path. There is no separate, later commit for the stamp.
     - **Phase-5-halted path** (some chunks still uncommitted): skips the stamp entirely and reports which chunks remain uncommitted.
     - The commit leg is gated on the op having actually written something, so re-invoking against an already-stamped plan is a genuine end-to-end no-op rather than a "nothing to commit" failure.

   Folding the stamp into your own chunk commit instead is acceptable and equivalent — state that you did, rather than leaving it ambiguous whether the plan was ever stamped.

2. **Report completion** — name what landed and the branch the work is committed on. If the plan includes an AC table, summarize coverage in the completion report.
3. **Offer the next step as a phase-aware offer, never a parroted default.** Two branches:

   **(A) Full plan shipped** — every chunk committed (git-log-by-chunk-id; the Phase 4 precondition above). Offer:

   > _Plan executed end-to-end and committed on `<branch>`. The natural next step is `/workstream-complete` to cap the workstream (lessons, docs, workstream-complete review). When you want to ship it, `/merge-to-main` or `/workday-complete` carries the branch to main._

   **(B) Execution halted on a Phase 5 PM-only emergency** — some chunks still uncommitted. Do **NOT** offer `/workstream-complete`. Offer:

   > _Execution halted at `<chunk-id>` on `<emergency-class from Phase 5>`. Remaining chunks: <list uncommitted chunks>. Options: (a) resolve the blocker and resume (I'll re-enter Phase 3 at the same chunk); (b) `/handoff` to save state for a fresh session; (c) commit-and-stop without a handoff (this branch carries the partial work). `/workstream-complete` is not offered — it caps the full plan, not a partial run._

   Do **not** invoke `/workstream-complete`, `/merge-to-main`, `/workday-complete`, or `coordinator:finishing-a-development-branch` automatically. `/merge-to-main` is keyword-gated (the PM invokes it by name); `/workstream-complete` vs `/handoff` vs `/workday-complete` depends on workstream state, which the PM picks.

---

## Failure Modes

| Situation | Action |
|---|---|
| Multiple gate-graph chunks about to go to one executor | Malformed wave-map (Phase 1.6) — STOP, one chunk per dispatch, split before dispatching |
| Wave shape mirrors the plan's section/phase/cluster structure | Theme is not a gate. Rebuild from the file-write graph per Phase 1.5; strip any gate that isn't write-overlap / output-consumption / contract-change / epistemic-premise |
| A wave-map entry has N internally-disjoint write-targets | Under-expanded. Split into N entries (Phase 1.6 disjoint-write-target expansion rule) before dispatching; thematic affinity is not a coherence reason |
| A wave-map entry is gated serial with `gate-kind` = `output-consumption-content` or `contract-change` | Author/verify conflation. The gate is verification, not authoring — either pin the producer's interface up front and downgrade to `parallel`, or record a one-line rationale why pinning is infeasible. "C2 narratively follows C1" is not a gate. |
| A wave-map entry's `gate-kind` is blank or an unqualified serial gate stands alone | Pre-2026-06-09 wave-map shape — surface the missing discriminator and refuse to dispatch until it is filled. |
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

- **`/handoff` (execution handoff) + `/pickup`** — the DEFAULT upstream entry. After review-integration, the reviewing session stamps the plan's `execution_authorized_at` and writes an execution handoff via `/handoff`; a fresh session picks it up via `/pickup` and invokes `/execute-plan` here, reading the stamp confirmed in Phase 1. Same-session invocation straight off `coordinator:review` is the token-economics carve-out only (narrow, named-reason required — see Phase 1 § Session-freshness gate); `/autonomous` bypasses to same-session as today.
- **Fan-out methodology (Phase 1.5 § Mechanical step)** — the dispatch ceremony execution follows, **not a skill** (the verb collides with native Claude Code vocabulary). Phase 1.5 is the plan-mediated entry to it; ad-hoc parallel work (≥2 tasks, no plan doc) follows the same methodology inline. Stance: **execute = restructure-then-dispatch; fan-out = the dispatch methodology**.
- **Executor dispatch** — dispatched executors are always Sonnet, never Opus; use when the plan consists of enriched stubs with exact code sketches, file paths, and line numbers. Dispatch is the default; self-execute inline only on the token-economics carve-out (see Phase 1.5 § Self-execute escape hatch).
- **`/enrich-and-review`** — should be run before executor dispatch; not required before `/execute-plan` (plans that route here are typically less chunked).
- **`/review-code`** — optional post-execution code quality pass on the implemented work. If the plan called for it, route through `/review-code` before reporting completion in Phase 4.
- **`coordinator:plan`** — creates the plan that this command executes. A plan produced by that skill is the ideal input here.
- **`coordinator:workstream-complete`** — the natural next step after a plan is executed, offered (not auto-invoked) in Phase 4. Caps the workstream: lessons, docs, workstream-complete review.
- **`coordinator:finishing-a-development-branch`** — **not** chained from here. Branch disposition (merge / PR / keep) is a separate, PM-invoked decision that reaches the keyword-gated `/merge-to-main`. The PM invokes it directly when ready to ship.
