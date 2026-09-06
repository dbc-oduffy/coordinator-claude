---
name: sizing
description: "The EM's first move on any PM ask — size it, then route to plan, shape, roadmap, or dispatch. Fires whenever novel engineering work is asked of the EM, by any combination of words: this is a shape test, not a phrase list. Mutually exclusive with pickup."
description-budget: 260
allowed-tools: ["Read", "Grep", "Glob", "Bash"]
argument-hint: "[PM ask text | nothing — describe the ask inline]"
---

# Sizing — the Fleet Routing Lobby

Novel work enters via this sizing lobby, not directly into plan/shape/dispatch.

The EM's first move on any PM ask that isn't a mid-workstream continuation — before
`coordinator:plan`, `coordinator:shape`, or direct dispatch. Full framing and every worked
incident: `${CLAUDE_PLUGIN_ROOT}/docs/wiki/sizing-lobby.md`.

**Dispatch authorization — invoking this skill IS the request.** The dispatches named below are constitutive steps of this skill, not a separate thing to get cleared: invoking a skill requests the actions that skill performs. A harness line permitting dispatch "unless the user requested it" is therefore **satisfied here, not overridden** — no precedence claim is needed and none is made. Re-asking spends the very context the dispatch exists to protect. The rule attaches to skill entry and dissolves no PM-authored gate: keyword-gated skills gate entry, and every gate a skill names for itself still binds — per-session cross-repo-commit assent, ask-before-external-action, and any other this skill's own body names. Tripwire: `UNATTRIBUTED-HARNESS-LINE-IS-NOT-PM`.

Reuses `loe.tshirt` (XS–XXL) one altitude earlier than chunk-sizing, to pick a ROOM, not a
plan-body cost. No appetite question ahead of the size.

---

## The flow

**1. Form a t-shirt read** (XS–XXL) of engineering complexity only, never appetite. Calibration
table and the tentativeness guard: wiki. A confident XS/S with a clear PM express-lane signal
skips to Step 3.

**1b. Premise-provenance, every non-express-lane sizing.** Does the ask rest on a mechanism
EXECUTED, one only READ, or no mechanism claim at all (`not-applicable`, narrow)? Pass
`--premise-provenance executed|read|not-applicable`; there is no `--evidence` flag — the written
justification goes in the sizing-object's own `premise.evidence` at Step 4. The engine's
`next_move` carries the discharge text, never hand-derive it.

**2. Substrate probe — L/XL/shaky reads, mandatory on XXL.** Reuse cartography output
(`architecture-survey`/`-audit`); for judgment the engine can't emit, dispatch the
`internet-research-scout` payload. Feed `--probe-signal collapse|raise`,
`--scout-evidence-kind mention-count|change-set|site-count`, and on any `raise`,
`--probe-raise-basis ask-scope|substrate-condition|breadth` — the engine applies only `ask-scope`;
a finding about the *area's* condition, or a uniform touchpoint count, is not a size signal
(discriminator detail: wiki). Chain `coordinator:spike` first if the probe surfaces an unproven
mechanism.

**3. Compute the route — never hand-derive the table.**
Invoke `sizing-assemble` per the ladder in `snippets/resolve-coordinator-bin.md` — rung 0 (Shape W,
the `.exe` launcher through the call operator) on a PowerShell host:

    `& "$env:COORDINATOR_SETTINGS_HOME\bin\sizing-assemble.exe" --tshirt <XS|S|M|L|XL|XXL>`
`--tshirt` is the only required flag; never pass/invent `--appetite` unless the PM volunteered one
verbatim. Always pass `--intent "<PM's words>"` (`--intent-source em-elaborated` if it's your own
restatement), `--precedent shipped-before|novel`, `--boundary-in-notch yes|no` (§ Appetite guards
has the discriminator), the Step 1b/2 flags as answered, and
`--jtbd-unclear`/`--well-trodden-step-change`/`--express-lane` as the ask warrants. Push the
returned `route`/`detents`/`next_move` verbatim — it already carries the discharge text.

**4. Scaffold the sizing-object** (`coordinator-doc-new --type sizing-object`) for any
non-express-lane sizing, populating `intent`/`estimate`/`route`/`detents`/`scout_evidence` and the
property-attests verbatim from the returned fields. Undecided direction-class items go in
`surfaced_to_pm`, never folded into `fork`/`xl_exit`. Optionally populate `name` — a few words,
whiteboard length; never a slice of `intent`.

**`status`.** An XS routes to dispatch and has no plan: stamp it `shipped` yourself the moment the
work lands, citing the commit. S and above route into a plan, where the terminal cascade owns the
sizing-object stamp: never pre-empt it, and never hand-stamp instead of triggering it. The cascade
fires from `plan-status-transition stamp-implemented` — **from the stamping op, not from the
landing**. A plan whose `status: implemented` was hand-edited and committed directly never fires
it. **Then read `status` back** — that is the field the cascade writes, and the only one that
answers whether it fired. A sizing still `routed` under a plan stamped through the op is a finding.
Under a hand-landed plan it is expected, and the repair is to stamp the plan through
`plan-status-transition stamp-implemented`, not to hand-write the sizing row. Hand-write ONLY on a
status that did not advance under a plan stamped through the op, citing the landing commits and
this rule inline. Never hand-write on one that did — that races a live writer and loses unsafely.
Do not read `acted`: it belongs to a different op and is empty either way. Tripwire:
`ACTED-IS-BLIND-TO-THE-DELIVERABLE-CASCADE`.

**4b. Open the flight recorder on the resolved route — every route, before anything downstream.**
`TaskCreate`: one session-goal task naming the ask and the sizing-object path, then **one task per
remaining stage of the chain the route implies, through its terminal**. The chain is the route's,
not your judgment: `dispatch` → the work → `quick-wrap`. `spec-dispatch` → light plan → executor
dispatch → scoped `code-reviewer` + `review-integrator` → `quick-wrap`. `plan` → plan → plan review
→ `execute-plan` → `/workstream-complete`. `shape`/`roadmap`/`pm-decision` → the named room owns
its own chain; record the entry task and stop. **Terminal by size, not by feel: XS/S close at
`quick-wrap`, M and above at `/workstream-complete`.** Where the harness tool is absent, the
`coordinator-tasks-mirror` fallback carries it.

The point is that the whole chain is visible from the lobby — a PM or an EM can see at a glance
what a route commits the session to, and a stage nobody reached is a pending row rather than a
thing everyone forgot. **Downstream steps ADD to this list, they do not restart it**: `execute-plan`
Phase 2 and the `spec-dispatch` light terminal open per-chunk tasks beneath these stage rows, and a
second session-goal task means one of them re-created a recorder that was already open.

**5. `post_size_prompt_pending` (M+) — ask once, in the PM's register, and stop:** *"Looks like an
X — go with that, split it, cut it, what's up?"* Never a closed fork. Record the answer in
`pm_resolution` (and `fork` when cut/raise-shaped). Expires at plan ratification.

**5b. `route: pm-decision` bundles into the same ask.** `xl_exit` stays `null` (open, never
"accept") until the PM actually picks one, by test: `shape` (JTBD not stated, or the EM can't
falsifiably restate the problem in the PM's words), `roadmap` (spans ≥2 named workstreams, or
carries/needs an initiative FK — `split` is retired into this exit), or `accept_multi_session`
(neither above holds — one coherent job, clear JTBD, one workstream, simply large — **and** the PM
has explicitly assented; writing `xl_exit: accept_multi_session` IS that record, never a silent
fallthrough default).

**6. Hard gate — the only override that exists.** The t-shirt→route map binds absolutely; no
named-reason override, no ratifier. If a route feels wrong, the size read was wrong: fix the size
with evidence (symmetric resize, or the `plan⇄sizing` return edge) and let the table re-resolve.
`pm-decision` is a routed outcome, not an exception.

---

## Appetite guards — judgment the engine's flags cannot resolve alone

`appetite` is the PM's stated budget, populated only after the size lands. Rationale and
incidents: wiki § `appetite`, § The newer guard flags.

- **A volunteered appetite never moves the estimate.** Size from the work alone.
- **A cross-team dependency is a gate, not a size.** The boundary *ceremony* goes in
  `blocked_by`/`awaiting_gate`, never the t-shirt. A memo doesn't move the notch; negotiated
  co-design (the shared contract is itself the unknown) does — answer `--boundary-in-notch`
  accordingly.
- **A touchpoint count is not a depth read** (`--probe-raise-basis breadth`, § Step 2).

## Shape is a conditional room, not a second lobby

`route=shape` fires only when the size is large AND the JTBD is unclear, or the space is
well-trodden and the ask wants a step-change — both engine-resolved from
`--jtbd-unclear`/`--well-trodden-step-change`, never an EM gut-call.
