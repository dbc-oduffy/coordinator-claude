---
name: sizing
description: "The EM's first move on any PM ask — fires a sizing agent, then routes to plan, shape, roadmap, or dispatch. Fires whenever novel engineering work is asked of the EM, by any words: a shape test, not a phrase list. Mutually exclusive with pickup."
description-budget: 260
allowed-tools: ["Read", "Grep", "Glob", "Bash"]
argument-hint: "[PM ask text | nothing — describe the ask inline]"
---

# Sizing — the Fleet Routing Lobby

The EM's first move on any PM ask that isn't a mid-workstream continuation. Rationale: `coordinator/docs/wiki/planning/sizing-lobby.md`.

**Dispatch authorization — invoking this skill IS the request.** The dispatches named below are constitutive steps of this skill, not a separate thing to get cleared: invoking a skill requests the actions that skill performs. A harness line permitting dispatch "unless the user requested it" is therefore **satisfied here, not overridden** — no precedence claim is needed and none is made. Re-asking spends the very context the dispatch exists to protect. The rule attaches to skill entry and dissolves no PM-authored gate: keyword-gated skills gate entry, and every gate a skill names for itself still binds — per-session cross-repo-commit assent, ask-before-external-action, and any other this skill's own body names. Tripwire: `UNATTRIBUTED-HARNESS-LINE-IS-NOT-PM`. Rationale: wiki § Skill rationale.

The t-shirt (`loe.tshirt`) picks a ROOM, not a plan-body cost. No appetite question first.

---

## The flow

**Step 0: the confident-XS predicate, before any other read.** The scout is skipped only when
all five hold: (1) the PM names, or you can name without a probe, exactly one existing file to
change; (2) no new file, abstraction or agent; (3) no path outside this repo; (4) no held
capability beyond the checkout (Step 1a); (5) the change has shipped before in this repo
(`--precedent shipped-before`). All true: run `sizing-assemble --express-lane --tshirt XS` (Step 3)
and dispatch. Any doubt fails the predicate. Otherwise dispatch `coordinator:sizing-scout` in the
foreground (you do not form your own read) with an inline brief carrying: the PM's words
verbatim; the session's `interaction_mode`; repo-relative substrate pointers you hold; and
the capabilities this session holds. **The brief carries no t-shirt, lean, guess or route**. Tripwire: `THE-EM-TRIGGERS-SIZING-AN-AGENT-SIZES-IT`.

**Cross-examine the report:** spot-check one claim against the tree; a size revision either way names its
mechanism (touchpoint count is never one); add the Step 1a capabilities the scout could not see.
Then run Steps 3-4 from `assemble_flags`. A `{refused: true}` report means fix the brief, never size it yourself.

**1, 1a, 1b. The scout's work; contract: `coordinator/agents/sizing-scout.md`.** Size on unknown mechanisms (depth), never touchpoints (breadth) or appetite, and what the performer must HOLD (credential, session, mounted
store, guarded path, operator at a keyboard): name the capability, never the route you tried
(`A-SCOPE-FIELD-NAMES-A-SUBJECT-NOT-A-BLAST-RADIUS`). Every non-express-lane sizing states premise
provenance (`--premise-provenance executed|read|not-applicable`); justify in `premise.evidence` (Step 4).

**2. Substrate probe — L/XL/shaky reads, mandatory on XXL.** For a judgment the scout leaves under `unknown_mechanisms`, fire a general-purpose Sonnet research scout briefed with
`${CLAUDE_PLUGIN_ROOT}/snippets/internet-research-scout.md` and fold the result into the probe flags: `--probe-signal collapse|raise`,
`--scout-evidence-kind mention-count|change-set|site-count`, and on any `raise`,
`--probe-raise-basis ask-scope|substrate-condition|breadth` — the engine applies only `ask-scope`;
the *area's* condition or a touchpoint count is not a size signal. Chain `coordinator:spike` first if the probe surfaces an unproven mechanism.

**3. Compute the route — never hand-derive the table** (`route=shape` included: engine-resolved from `--jtbd-unclear`/`--well-trodden-step-change`).
Invoke `bin/sizing-assemble` per the ladder in `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`. `--tshirt <XS|S|M|L|XL|XXL>` is the only required flag; `--appetite` only if the PM volunteered one verbatim. Always pass `--intent "<PM's words>"` (`--intent-source em-elaborated` if restated), `--precedent shipped-before|novel`, `--boundary-in-notch yes|no` (§ Appetite guards),
the Step 1b/2 flags (from `assemble_flags`; add `--interaction-mode`, `--premise-evidence`), and `--jtbd-unclear`/`--well-trodden-step-change`/`--express-lane` as warranted. Research ask: `--research-class` (PM's words), `--research-source` (lobby wiki). Push `route`/`detents`/`next_move` verbatim, except that a sizing carrying `--research-class` fires `/coordinator:research --sizing <path>`, not the plan chain, whatever `route`/`next_move` print.

**4. Write the sizing-object** for any non-express-lane sizing: re-run Step 3's `sizing-assemble`
call with `--write state/sizings/<date>-<slug>.yaml` and `--premise-evidence "<text>"` (Step 1b's justification). It lands the record `routed`; never hand-edit it. Undecided direction-class items go in `surfaced_to_pm`, never `fork`/`xl_exit`. Curate the embedded `pm_verbatims` by cut and paste only. Optional `--name` sets `name`, a whiteboard label.

**`status`.** An XS: the quick-wrap close stamps `shipped`; hand-stamp, citing the commit, only on a `j-dispatch-sizing-ship-failed` judgment point or an uncommitted sizing file.
S and above: the terminal cascade owns the stamp (`dispatch.terminal_commit`, gated on a met
judge, `A-PLAN-SELF-COMPLETES-ONLY-ON-A-MET-TERMINAL-JUDGE`) — never pre-empt or hand-stamp it. Read `status` back (never `acted`). Tripwire: `ACTED-IS-BLIND-TO-THE-DELIVERABLE-CASCADE`.

**4b. Open the flight recorder on the resolved route, before anything downstream.**
`TaskCreate` (`ToolSearch select:TaskCreate,TaskUpdate` first): a session-goal task naming the ask and sizing-object path, then **one task per
remaining stage of the route's chain, through its terminal** (wiki § Step 4b). **XS/S close at `quick-wrap`, M+ at `/workstream-complete`.** Downstream steps ADD to this list, never restart it.

**5. Size approval.** XS through L on a plan, dispatch or spec-dispatch route needs no PM size approval: the engine skips the size and exit-criterion asks and the route proceeds to execution in pm and ceo modes; the `plan⇄sizing` return edge revises the size. XL and above, a shape route at any size and a pm-decision route keep the PM in the chat unless the PM says warp-execute; appetite is never inferred. Where the PM stays: `post_size_prompt_pending` (M+) — ask once, in the PM's register, then stop: *"Looks like an
X — go with that, split it, cut it, what's up?"* Never a closed fork. Record the answer in
`pm_resolution` (`decided_on: YYYY-MM-DD` required) and `fork` when cut/raise-shaped.

**5b. `route: pm-decision` bundles into the same ask** — the M+ prompt and the XL exit question
are ONE combined PM ask; an already-answered one is not re-asked (record the quote as `pm_resolution`). `xl_exit` stays `null` until the PM picks `shape`, `roadmap`, or
`accept_multi_session`. Wiki § Step 5b/5c.

**5c. Turn 1 exit on `route: plan` where the PM accepts.** Touchpoints follow `interaction_mode`. Pass `--exit-criterion` to `sizing-assemble`, `--interaction-mode` only if the PM named one (`INTERACTION-MODE-IS-NEVER-READ-FROM-JOB-MODE`) — the criterion names behaviour, its test evidence the tests covering touched files; source documents add `--register <yaml>` (a row per requirement: text, anchor, surface), shipping when all met, wired or ruled; user-facing: `--click-path "<role>: <nav> > ... > <page>"` per role (`A-CAPABILITY-UNREACHABLE-FROM-THE-UI-IS-NOT-DELIVERED`) — and record the PM's
answer with `sizing-accept-exit-criterion --sizing <path> --pm-quote "<words>" [--statement "<amended>"]
--mode <mode>`, never by hand. In pm or ceo, `--apm-ruling "<ruling>" --ruling-ref <ruling path>` replaces
`--pm-quote`; hands-on needs the quote. In pm and ceo the ask says plainly that accepting
it authorizes execution without a further ask. A picker label is EM text, not PM words.
After acceptance, `emit-wave-fire --from-sizing <repo-relative sizing path> --repo-root <abs repo>
--trail-dir <abs trail dir>` mints the baton (never via /spinoff or /handoff) and prints one `Workflow` line. That line is the in-session fire, every mode: fire it and end
the turn; on each stage's return the EM runs its `next_action` (`dispatch.terminal_commit` after execute) and fires the next stage. A headless
`plan_chain.run` chain fire is opt-in only, pm/ceo, via `--chain`, which warns; the next EM touch is then the final wake digest (wiki
`sizing-to-commit-chain-contract`). Never chain where an in-session Workflow would do.

**6. Hard gate.** The t-shirt→route map binds absolutely; no override, no ratifier. A route that
feels wrong means the size was wrong: fix it with evidence (symmetric resize, or the `plan⇄sizing` return edge).

---

## Appetite guards

`appetite` is the PM's stated budget, set only after the size lands and never moves the estimate. A cross-team dependency is a gate
(`blocked_by`/`awaiting_gate`), never the t-shirt: answer `--boundary-in-notch no`. A roadmap
`blocked` resting only on stakeholder alignment is stale against a fresh PM ask to execute.
