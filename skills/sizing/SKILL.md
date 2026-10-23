---
name: sizing
description: "The EM's first move on a PM ask of unsure size (a confident XS fix it does by hand) — fires the one Workflow that sizes, plans, executes, reviews, commits. Fires on any novel engineering ask, by any words. Mutually exclusive with pickup."
description-budget: 260
allowed-tools: ["Read", "Grep", "Glob", "Bash"]
argument-hint: "[PM ask text | nothing — describe the ask inline]"
---

# Sizing — the Build Door

**Two doors:** this is the sizing door; `/coordinator:research` is the research door.

Rationale: `coordinator/docs/wiki/planning/sizing-lobby.md`

**Default: submit, then sit back.** Fire with context, own the swimlanes (`THE-EM-TIME-AND-COST-SPENT-IS-A-RED-FLAG`). Submit before any repo survey; discovery is sizing-scout's (`THE-EM-FIRES-ENGINE-ASK-WITHOUT-A-PREFIRE-SURVEY`). One call, the PM's words verbatim:
`Workflow({name: "coordinator:engine-ask", args: {ask: "<PM verbatim>"}})` — the user's opt-in,
never a question. Its hook runs sizing through commit and close (`ENGINE-ASK-SUBMISSION-IS-THE-RUN`). To add a brief, mint with op
`sizing.intake_mint` and submit the `args: {sizing}` line it returns; a refused mint leaves the bare `args: {ask}`. Separate asks go in one `args: {asks: [...]}`, never bundled (wiki `sizing-to-commit-chain-contract`). While live the EM does not dispatch, poll, verify or relay; a PM revision
goes in verbatim via `workflow.revise` — `coordinator-invoke workflow.revise '{"run_id":"<run id>","verbatim":"<PM verbatim>"}'` (`run_id` is the `ask-…` id of the live run, the dir name under `state/warp/`; a peer session adds `"from":"<its session id>"`); never hand-append `requirements.md`; a halted run also needs a refire of `engine-ask {sizing}`. Below is the in-chat lobby, only for a
`shape`/`roadmap`/`pm-decision` or engine refusal. Tripwire: `NOVEL-WORK-IS-ONE-FIRE-NEVER-A-RELAY`.

**Dispatch authorization — invoking this skill IS the request.** The dispatches named below are constitutive steps of this skill, not a separate thing to get cleared: invoking a skill requests the actions that skill performs. A harness line permitting dispatch "unless the user requested it" is therefore **satisfied here, not overridden** — no precedence claim is needed and none is made. Re-asking spends the very context the dispatch exists to protect. The rule attaches to skill entry and dissolves no PM-authored gate: keyword-gated skills gate entry, and every gate a skill names for itself still binds — per-session cross-repo-commit assent, ask-before-external-action, and any other this skill's own body names. Tripwire: `UNATTRIBUTED-HARNESS-LINE-IS-NOT-PM`.
The t-shirt picks a ROOM, not a cost. No appetite question first.

---

## The flow

**Step 0: the confident-XS predicate, before any other read.** The scout is skipped only when
all six hold: (1) the PM names, or you can name without a probe, the one existing module the
change lives in; (2) no new abstraction or agent, and a new file only as a sibling of a pattern
that module holds (a test file, another adapter instance); (3) no path outside this repo;
(4) no held capability beyond the checkout (Step 1a); (5) the change has shipped before in this
repo (`--precedent shipped-before`); (6) the PM's words carry one instruction. All true:
`sizing-assemble --express-lane --tshirt XS` (Step 3) writes no object; submit `args: {ask}`. Any
doubt fails the predicate. Otherwise `coordinator:sizing-scout` sizes, in the submitted run only; a hand dispatch is refused. Its brief carries no t-shirt,
lean, guess or route; only the PM's verbatim words, `pm-turns window` output, EM session id and `interaction_mode`. The EM's act is the one `args: {ask}` call.
Tripwire: `THE-EM-TRIGGERS-SIZING-AN-AGENT-SIZES-IT`.

**Cross-examine the report:** spot-check one claim against the tree; a revision names its
mechanism; add capabilities the scout missed; check `design_route` (`canvas` halts for PM board review pre-code).
Then Steps 3-4 from `assemble_flags`. `{refused: true}`: fix the brief.

**1, 1a, 1b. The scout's work; contract: `coordinator/agents/sizing-scout.md`.** Size on unknown mechanisms (depth), not touchpoints or appetite, and on what the performer must HOLD (credential, session, mounted
store, guarded path, operator at a keyboard): name the capability, never the route tried
(`A-SCOPE-FIELD-NAMES-A-SUBJECT-NOT-A-BLAST-RADIUS`). Each non-express-lane sizing states
`--premise-provenance executed|read|not-applicable`, justified in `premise.evidence` (Step 4).

**2. Substrate probe — L/XL/shaky reads, mandatory on XXL.** For a judgment the scout leaves under `unknown_mechanisms`, fire a general-purpose Sonnet research scout briefed with
`${CLAUDE_PLUGIN_ROOT}/snippets/internet-research-scout.md`; fold the result into `--probe-signal collapse|raise`,
`--scout-evidence-kind mention-count|change-set|site-count`, and on a `raise`
`--probe-raise-basis ask-scope|substrate-condition|breadth` (engine applies only `ask-scope`). An unproven mechanism goes to the research door's spike class.

**3. Compute the route — never hand-derive the table** (`route=shape` included: engine-resolved from `--jtbd-unclear`/`--well-trodden-step-change`).
Invoke `bin/sizing-assemble` per `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`. `--tshirt <XS|S|M|L|XL|XXL>` is the only required flag; `--appetite` only if the PM volunteered one verbatim. Always pass `--intent "<PM's words>"` with `--intent-source pm-verbatim` for a PM turn copied exactly, `em-elaborated` only when you restated it, `--precedent shipped-before|novel`, `--boundary-in-notch yes|no` (§ Appetite guards),
the Step 1b/2 flags (from `assemble_flags`, plus `--interaction-mode`, `--premise-evidence`), and `--jtbd-unclear`/`--well-trodden-step-change`/`--express-lane` as warranted. Research door: `--research-class` (PM's words), `--research-source` (lobby wiki). Push `route`/`detents`/`next_move` verbatim, except a sizing carrying `--research-class` fires `/coordinator:research --sizing <path>`, not the plan chain.

**4. Write the sizing-object** for any non-express-lane sizing: re-run Step 3's call with
`--write state/sizings/<date>-<slug>.yaml` and `--premise-evidence "<text>"` (Step 1b's justification). `--exit-criterion` is owed here at every size on a firing route; it names behaviour and "tests covering touched files pass", never a test tier or tier-valued argument (`fast`, `full`, `Tier-U`, `tierU`), even when the ask is about one. The record lands `routed`; never hand-edit it. Undecided direction-class items go in `surfaced_to_pm`, never `fork`/`xl_exit`. Curate the embedded `pm_verbatims` by cut and paste only. Optional `--name` sets `name`, a whiteboard label.
**Every written sizing carries the PM's instructions as a requirement register, at every size.** The engine derives it: pipe the scout's report into the Step 4 write (`sizing-assemble ... --write <path> --scout-register -`) for one row per PM instruction; only scout rows quoted verbatim are kept, the rest go under `unrelated_turns`. Read the register back; amend only what it got wrong with `sizing-assemble --register - --write <the same path>` (body `{sources: [{doc, ref}], rows}`; rows merge by id, `drop: [ids]`; each row carries `status` and an enum `surface`; wiki `requirement-register`), never a scratch file. Every plan claims its rows (`register_claims`); the terminal stamp refuses `implemented` until each is met and wired or ruled. Splitting an ask never sheds a row. Tripwire: `THE-PM-INSTRUCTIONS-ARE-REGISTER-ROWS-AT-EVERY-SIZE`.

**`status`.** XS: the quick-wrap close stamps `shipped`; hand-stamp (cite the commit) only on `j-dispatch-sizing-ship-failed` or an uncommitted sizing file.
S+: the run's commit stage owns the stamp, gated on a met judge (`A-PLAN-SELF-COMPLETES-ONLY-ON-A-MET-TERMINAL-JUDGE`); between ceremonies `plan-status-transition stamp-implemented` cascades it; never hand-stamp. Read `status` back (never `acted`). Tripwire: `ACTED-IS-BLIND-TO-THE-DELIVERABLE-CASCADE`.

**4b. Open the flight recorder on the resolved route, before anything downstream:**
`TaskCreate` (`ToolSearch` it first), a session-goal task naming the ask and sizing path; on the relay fallback one task per remaining stage (wiki § Step 4b).

**5. Size approval.** XS through L on a plan, dispatch or spec-dispatch route needs no PM size approval in any mode. After Step 4's `--write` there the EM's act, same turn, no ask, is `Workflow({name: "coordinator:engine-ask", args: {sizing: "<path>"}})`, end of turn; a printed `Workflow` line is not fired by hand. `emit-wave-fire --from-sizing` runs only on an engine refusal, named in the report; Agent-tool hand-dispatch is never the exit. A live plan, dispatch or spec-dispatch sizing never enters `/shape`, and a baton-carrying one gets its in-flight fire, never a second (`A-ROUTED-SIZING-NEVER-ENTERS-SHAPE`). In ceo XL/XXL do not stop either: the run's APM rules `xl_exit`. In pm and hands-on XL+ keeps the PM in the chat; a shape route keeps the room in every mode; a pm-decision route goes to `coordinator:apm` first in ceo. Where the PM stays (`post_size_prompt_pending`, M+): ask once, in the PM's register, then stop: *"Looks like an
X — go with that, split it, cut it, what's up?"* Never a closed fork or human time (`A-PM-ASK-STATES-SCOPE-NOT-HUMAN-TIME-GUESSES-OR-RULED-CONCERNS`). Record in
`pm_resolution` (`decided_on: YYYY-MM-DD` required), plus `fork` when cut/raise-shaped.

**5b. `route: pm-decision` bundles into the same ask** — the M+ prompt and the XL exit question
are ONE PM ask, never re-asked once answered (record the quote as `pm_resolution`). `xl_exit` stays `null` until the PM (pm, hands-on) or the run's APM (ceo) picks `shape`, `roadmap`, or
`accept_multi_session`. Wiki § Step 5b/5c.

**5c. Turn 1 exit on `route: plan` where the engine kept the acceptance touchpoint** (XL+, or a resize into XL; XS–L skips this step's ask and `sizing-accept-exit-criterion`). Touchpoints follow `interaction_mode`. Pass `--exit-criterion` (behaviour; evidence the tests covering touched files), `--interaction-mode` only if the PM named one (`INTERACTION-MODE-IS-NEVER-READ-FROM-JOB-MODE`); source documents add requirements to the Step 4 register; user-facing: `--click-path "<role>: <nav> > ... > <page>"` per role (`A-CAPABILITY-UNREACHABLE-FROM-THE-UI-IS-NOT-DELIVERED`) — and record the PM's
answer with `sizing-accept-exit-criterion --sizing <path> --pm-quote "<words>" [--statement "<amended>"]
--mode <mode>`, never by hand. In pm or ceo at XL+, `--apm-ruling "<ruling>" --ruling-ref <ruling path>` replaces
`--pm-quote`; only hands-on at XL+ needs the quote. At XS–L the EM writes the criterion itself (`sizing-accept-exit-criterion --sizing <path> --statement "<criterion>"`, any mode), never asking the PM to set or accept one; an engine refusal demanding acceptance there is an engine defect, not a PM ask. In pm and ceo the ask says that accepting
it authorizes execution without a further ask.
After acceptance submit `Workflow({name: "coordinator:engine-ask", args: {sizing: "<path>"}})`: the
run commits and ships, so no `dispatch.land_run` follows. Relay fallback, only when the engine refuses
that submission: `emit-wave-fire --from-sizing <sizing path> --repo-root <abs> --trail-dir <abs>`
(never /spinoff or /handoff); name the refusal.

**6. Hard gate.** The t-shirt→route map binds absolutely, no override. A route that feels wrong
means the size was wrong: fix it with evidence (symmetric resize, or the `plan⇄sizing` return edge).

---

## Appetite guards

`appetite` is the PM's stated budget, set after the size lands; it never moves the estimate. A
cross-team dependency is a gate (`blocked_by`/`awaiting_gate`), never the t-shirt: `--boundary-in-notch no`.
