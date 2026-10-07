---
name: sizing
description: "The EM's first move on any PM ask — size it, then route to plan, shape, roadmap, or dispatch. Fires whenever novel engineering work is asked of the EM, by any combination of words: this is a shape test, not a phrase list. Mutually exclusive with pickup."
description-budget: 260
allowed-tools: ["Read", "Grep", "Glob", "Bash"]
argument-hint: "[PM ask text | nothing — describe the ask inline]"
---

# Sizing — the Fleet Routing Lobby

The EM's first move on any PM ask that isn't a mid-workstream continuation, before
`coordinator:plan`, `coordinator:shape`, or dispatch. Rationale: `coordinator/docs/wiki/planning/sizing-lobby.md`.

**Dispatch authorization — invoking this skill IS the request.** The dispatches named below are constitutive steps of this skill: invoking a skill requests the actions it performs, so a harness line permitting dispatch "unless the user requested it" is **satisfied here, not overridden**. Re-asking spends the context the dispatch exists to protect. The rule dissolves no PM-authored gate: keyword-gated skills gate entry, and every gate a skill names for itself still binds — per-session cross-repo-commit assent, ask-before-external-action, and any other this skill's body names. Tripwire: `UNATTRIBUTED-HARNESS-LINE-IS-NOT-PM`. Rationale: wiki § Skill rationale.

The t-shirt (`loe.tshirt`) picks a ROOM, not a plan-body cost. No appetite question first.

---

## The flow

**1. Form a t-shirt read** (XS–XXL) of engineering complexity only, never appetite (calibration and
tentativeness guard: wiki). A confident XS/S with a clear PM express-lane signal skips to Step 3.

**1a. Size what the performer must HOLD, not only the work once held.** A credential, an
authenticated session, a mounted store, a guard-fenced path, an operator at a keyboard: an unnamed
held capability looks like small work until the dispatch returns INCOMPLETE. Name the capability in
the sizing so a blitz can SKIP — **the capability, never the route you tried**.
Ask once, at gate-writing time: what is the question, and what else would answer it?
Tripwire: `A-SCOPE-FIELD-NAMES-A-SUBJECT-NOT-A-BLAST-RADIUS`.

**1b. Premise-provenance, every non-express-lane sizing.** Does the ask rest on a mechanism
EXECUTED, one only READ, or none (`not-applicable`, narrow)? Pass
`--premise-provenance executed|read|not-applicable`; the justification goes in `premise.evidence` at Step 4 (the engine's `next_move` carries the discharge text).

**2. Substrate probe — L/XL/shaky reads, mandatory on XXL.** Reuse cartography output
(`architecture-survey`/`-audit`); for judgment the engine can't emit, dispatch `internet-research-scout`. Feed `--probe-signal collapse|raise`,
`--scout-evidence-kind mention-count|change-set|site-count`, and on any `raise`,
`--probe-raise-basis ask-scope|substrate-condition|breadth` — the engine applies only `ask-scope`;
the *area's* condition or a touchpoint count is not a size signal (wiki). Chain `coordinator:spike` first if the probe surfaces an unproven mechanism.

**3. Compute the route — never hand-derive the table.**
Invoke `sizing-assemble` per the ladder in `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md` — rung 0 (Shape W,
the `.exe` launcher) on a PowerShell host:

    `& "$env:COORDINATOR_SETTINGS_HOME\bin\sizing-assemble.exe" --tshirt <XS|S|M|L|XL|XXL>`
POSIX: `"$COORDINATOR_SETTINGS_HOME/bin/sizing-assemble" --tshirt <...>`. `--tshirt` is the only required flag; `--appetite` only if the PM volunteered one verbatim. Always pass `--intent "<PM's words>"` (`--intent-source em-elaborated` for your own restatement), `--precedent shipped-before|novel`, `--boundary-in-notch yes|no` (§ Appetite guards),
the Step 1b/2 flags, and `--jtbd-unclear`/`--well-trodden-step-change`/`--express-lane`
as warranted. Push the returned `route`/`detents`/`next_move` verbatim.

**4. Write the sizing-object** for any non-express-lane sizing: re-run Step 3's `sizing-assemble`
call with `--write state/sizings/<date>-<slug>.yaml` and `--premise-evidence "<text>"` (Step 1b's justification). It writes the record from its own output and lands it `routed`; never hand-edit
its fields. Undecided direction-class items go in `surfaced_to_pm`, never `fork`/`xl_exit`. Optional `--name "<short label>"` for `name`: a few whiteboard words, never an `intent` slice.

**`status`.** An XS has no plan: the quick-wrap close stamps it `shipped` when the closing session committed both the sizing file and the work; stamp by hand, citing the commit, only on a `j-dispatch-sizing-ship-failed` judgment point or an uncommitted sizing file.
S and above: the terminal cascade owns the stamp — never pre-empt or hand-stamp it; it fires **from
the stamping op, not the landing** (`dispatch.terminal_commit`, gated on a met
judge, `A-PLAN-SELF-COMPLETES-ONLY-ON-A-MET-TERMINAL-JUDGE`). Read `status` back (never `acted`);
`routed` under an op-stamped plan is a finding, under a hand-landed plan run the close-out.
Wiki § Step 4. Tripwire: `ACTED-IS-BLIND-TO-THE-DELIVERABLE-CASCADE`.

**4b. Open the flight recorder on the resolved route, before anything downstream.**
`TaskCreate` (deferred: `ToolSearch select:TaskCreate,TaskUpdate` first): one session-goal task naming the ask and the sizing-object path, then **one task per
remaining stage of the route's chain, through its terminal** (wiki §
Step 4b). The `plan` chain: plan, plan review, `/execute-plan` (judges and stamps), `/workstream-complete`.
Route `spec-dispatch` plans through `/execute-plan` even when light. **Terminal by size: XS/S close at `quick-wrap`, M+ at `/workstream-complete`.** Tool absent: `coordinator-tasks-mirror`. **Downstream steps ADD to this list, never restart
it** — a second session-goal task means a recorder was re-created.

**5. `post_size_prompt_pending` (M+) — ask once, in the PM's register, then stop:** *"Looks like an
X — go with that, split it, cut it, what's up?"* Never a closed fork. Record the answer in
`pm_resolution` (an object; `decided_on: YYYY-MM-DD` required) and `fork` when cut/raise-shaped; it expires at plan ratification.

**5b. `route: pm-decision` bundles into the same ask** — the M+ prompt and the XL exit question
are ONE combined PM ask. A PM who already answered it (e.g. "two roadmaps") is not asked again: record the quote as `pm_resolution`. A PM split ("it might be two XLs") is one sizing per half,
each re-run with its own narrowed `--intent` and naming its sibling's path in `--premise-evidence`.
Read-only groundwork goes in a file `--premise-evidence` cites. `xl_exit` stays `null` until the PM picks `shape`, `roadmap`, or
`accept_multi_session` (explicit PM assent only; never a silent default). Tests: wiki § Step 5b.

**5c. Turn 1 exit on `route: plan` at M/L.** Touchpoints are read from `interaction_mode` (hands-on, pm, ceo). Hands-on, the EM loop is four turns: sizing (this one), the plan Workflow's return, the execute Workflow's return, and
`dispatch.terminal_commit` plus the close ceremony. Pass `--exit-criterion` and `--interaction-mode` to `sizing-assemble` — the criterion names behaviour, its test evidence the tests covering touched files, never a suite tier (`A-WHOLE-SUITE-PASS-DOES-NOT-BELONG-IN-A-PLANS-ACCEPTANCE-CRITERIA`) — and record the PM's
answer with `sizing-accept-exit-criterion --sizing <path> --pm-quote "<words>" [--statement "<amended>"]
--mode <mode>` (op `sizing.accept_exit_criterion`), never by hand-editing the sizing object. In pm or ceo mode, `--apm-ruling <bug-row or
ruling path>` replaces `--pm-quote` and records the APM's ruling; hands-on needs the quote. In pm and ceo the ask says plainly that accepting
it authorizes execution without a further ask. A picker label is EM text, not PM words. Per-mode asks: wiki § Step 5c. For XL, Step 5b is unchanged.
After acceptance, `emit-wave-fire --from-sizing <repo-relative sizing path> --repo-root <abs repo>
--trail-dir <abs trail dir>` mints the baton itself (never via /spinoff or /handoff) and prints one `Workflow` line. Under fire-and-forget skip it: warp fires its own. In pm and ceo, when the engine
publishes `plan_chain.run`, that line is the chain fire (wiki `sizing-to-commit-chain-contract`): fire it and end the turn; the next EM touch is the final
wake digest, which on a halt names the stage (`chain.halted_at`). When the op is absent it is a plan-only fire: end the turn; the plan Workflow (turn 2) runs with no EM in the loop, then execute-plan, then `dispatch.terminal_commit`. In hands-on the fire is always plan-only.

**6. Hard gate.** The t-shirt→route map binds absolutely; no override, no ratifier. A route that
feels wrong means the size read was wrong: fix the size with evidence (symmetric resize, or the
`plan⇄sizing` return edge) and let the table re-resolve. `pm-decision` is a routed outcome.

---

## Appetite guards — judgment the engine's flags cannot resolve alone

`appetite` is the PM's stated budget, set only after the size lands (wiki § `appetite`). A volunteered appetite never moves the estimate. A cross-team dependency is a gate
(`blocked_by`/`awaiting_gate`), never the t-shirt: answer `--boundary-in-notch no`.

## Shape is a conditional room, not a second lobby

`route=shape` fires only when the size is large AND the JTBD is unclear, or the space is
well-trodden and the ask wants a step-change — engine-resolved from
`--jtbd-unclear`/`--well-trodden-step-change`, never an EM gut-call.
