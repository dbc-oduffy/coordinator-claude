---
name: goal-setting
description: "PM-GATED. Turns raw vision into ratified OKRs plus roadmap-seed stubs."
version: 1.0.0
user-invocable: true
---

# Goal-Setting — Vision to OKRs to Scaffolded Stubs

> **Posture:** vision-in, OKR-out. Neither rubber-stamp nor idea-crushing gate. Each KR must be
> weekly-perceptible (can an agent or PM observe it move this week?); one that fails is a
> later-impact aspiration, surfaced as a shaping question, not a rejection.

**Entry points:**

1. **Direct invocation** — the PM arrives with raw vision, no formed OKR yet.
2. **Pickup-from-goal-seed** — a deferred `kind: goal-seed` stub; run this skill on the captured
   vision.
3. **Conform intake from a sizing-object** — `coordinator:sizing` hands an optional
   `state/sizings/<id>.yaml` entry contract ahead of Step 1, on three arrival shapes
   (`route: pm-decision`+`xl_exit: roadmap`, legacy `route: roadmap`, or direct-routed
   `route: goal-setting` XXL). No sizing-object present means Step 1 runs exactly as today — see
   wiki for the full field-crossing table.

**What this skill produces:** a ratified OKR (one Objective + ≤5 Key Results, weekly-perceptible)
via `coordinator-doc-new --type goal`; `kind: roadmap-seed` stubs pre-tagged to the goal, one per
roadmap-worth-of-work; optionally `kind: goal-seed` stubs for deferred vision-slices; an OFFER to
chain into `/roadmap-planning` (PM-gated, never auto-run).

<HARD-GATE>
This skill DOES NOT auto-author roadmap plans, invoke `/roadmap-planning` without PM
acknowledgment, or bypass its PM gate. It scaffolds stubs and offers the chain. The PM decides
whether and when to fire each stub.
</HARD-GATE>

---

## When NOT to invoke

- **Problem not yet converged** (still deciding *what* to build) → `coordinator:shape` or
  `coordinator:brainstorming` first.
- **Single-feature scope**, no broader OKR arc → straight to `coordinator:plan`.
- **Roadmap already has goals** — picking up an existing roadmap-seed stub against an
  already-ratified goal → `/roadmap-planning` directly.

---

## Ceremony

### Step 1 — PM states Objective and candidate Key Results

The PM names the **Objective** (qualitative, direction-setting) and one or more **candidate KRs**
(raw is fine). Do NOT prompt for a specific format — the ceremony imposes structure through
critique, not intake.

**When a sizing-object is present** (see Entry point 3), it pre-populates part of this step's raw
framing in body prose only, never new frontmatter: `intent` → opening vision statement;
`appetite` → context only, never a KR or stub `cost:`; `estimate.tshirt`+`estimate.provisional`
together → routing signal only; `scout_evidence` → framing pointers; `route`(+`xl_exit`) → the
recorded reason this ceremony opened. Full field-by-field detail and does/doesn't-cross list:
wiki.

**PM-assent record for a direct-routed XXL:** that shape emits no `xl_exit`, so once this step's
PM utterance happens, write `pm_resolution.xl_route_assent` on the sizing-object recording it as
the assent — this does not reintroduce a PM halt above `goal-setting` (Step 1's own utterance
already is the gate). Detail: wiki.

### Step 1b — Offer to record competitive context (optional)

If the PM's vision names or implies a domain, check `state/strategic/self-description.yaml`'s
`competitors[]` first — skip the offer silently if already populated (same discipline as
`workweek-start`/`repo-setup` Phase 3l nudges). Otherwise offer once:

> This reads like <inferred domain> work — want me to record inspirations / peers / competitors /
> aspirational-targets? Goes in your repo's strategic self-description. (Skip freely.)

On opt-in, record via `coordinator:strategic-self-description-refresh`'s scaffold path (schema:
`coordinator/schemas/strategic-self-description.schema.json`; `provenance: curated`) — never a
second marking store. On decline, proceed to Step 2 without repeating the offer.

### Step 2 — Dispatch the VP-Product Reviewer as full OKR critic

**Dispatch via `Agent(subagent_type: "coordinator:vp-product", model: "opus")`.** Inline verbatim:

> You are the VP-Product Reviewer (VP of Product, they/them). You are reviewing a draft OKR set for strategic rigor.
> Your job is to act as a full OKR critic, not a rubber-stamp.
>
> Assess: (1) Is the Objective a real Objective — qualitative, direction-setting, not a metric or
> tactic in disguise? (2) Are the KRs real Key Results — measurable outcomes, not activity/output
> proxies? (3) Is the SET reasonable — ≤5 KRs; more means the Objective is unfocused? (4)
> Weekly-perceptibility per KR — can an agent or PM observe it move this week? If not, flag as a
> later-impact aspiration with a weekly-perceptible rewrite, or note the PM should defer it.
>
> Return: verdict per element (PASS/FLAG/REJECT), specific rewrite suggestions for
> flagged/rejected elements, a SET-level verdict (GO/REVISE/REFRAME). Give the EM and PM the
> material to revise it themselves — do not rewrite the whole OKR yourself.

### Step 3 — EM+PM integrate the VP-Product Reviewer's critique in-dialogue

The artifact does not exist on disk yet. REJECT items are rewritten or dropped; FLAG items are
rewritten or consciously accepted with a stated rationale; weekly-perceptibility notes are
rewritten or deferred to a `kind: goal-seed` stub. This is a dialogue: EM presents the critique,
proposes a revised shape, and asks the PM to confirm.

**Do NOT proceed to Step 4 without explicit PM confirmation on the revised OKR.**

### Step 4 — Scaffold the goal artifact

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-doc-new" --type goal --title "<objective-slug>"
```

Fill: `objective:` (ratified text), `key_results:` (≤5, weekly-perceptible), `period:` (e.g.
`Q3-2026`), `status: active`.

### Step 5 — Spawn downstream stubs

**5a. Roadmap-seed stubs** — one per roadmap-worth-of-work (roughly: one `/roadmap-planning`
invocation, one coherent capability arc; when in doubt, fewer/larger — the PM can split at
pickup):

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-doc-new" --type roadmap-seed --goals "<goal-id>" --title "<roadmap-topic>"
```

Each stub carries `kind: roadmap-seed`, `origin_goal_id:` FK (via `--goals`), `deployment_state:
awaiting_gate`, a one-line title naming the capability arc.

**5b. Goal-seed stubs (optional)** — for vision-slices out of scope this period, or KRs deferred
rather than rewritten:

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-doc-new" --type goal-seed --title "<deferred-vision-slice>"
```

Each stub carries `kind: goal-seed`, `deployment_state: awaiting_gate`, and a brief body
capturing the vision-slice verbatim — raw over polished. These feed the pickup-from-goal-seed
entry point; they are vision preservation, not roadmap stubs.

### Step 6 — Offer the PM-gated chain

> _"Goal artifact and {N} roadmap-seed stub(s) scaffolded. Want me to chain into
> `/roadmap-planning` now, or review the stubs first?"_

**Wait for PM response.** Never invoke `/roadmap-planning` without explicit PM direction.

### Step 7 — Commit goal + stubs

Stage only the goal artifact and stubs this run scaffolded — no blanket add:

```bash
git add -- <goal-artifact-path> <stub-path-1> [<stub-path-N>]
git commit -m "goal-setting: ratify <objective-slug> + scaffold {N} downstream stubs"
```

---

## Out of scope

- **Roadmap authoring** — `/roadmap-planning` owns it; this skill scaffolds the stubs that feed
  it. Auto-chaining bypasses the PM's multi-wave sequencing authority.
- **KR tracking infrastructure** — cockpit-contract `goal.schema.json` owns event emission.
- **Deferred-goal fleshing without PM pickup** — a `kind: goal-seed` stub is dormant until the PM
  picks it up via entry point 2.

---

## Skill-scaffold checklist (self-verify before reporting DONE)

- [ ] the VP-Product Reviewer dispatched at Opus altitude via `subagent_type: "coordinator:vp-product"`
- [ ] PM confirmed revised OKR before any artifact written to disk
- [ ] Goal artifact scaffolded with `coordinator-doc-new --type goal`
- [ ] Each roadmap-seed stub carries `origin_goal_id:` FK and `deployment_state: awaiting_gate`
- [ ] `/roadmap-planning` was NOT auto-invoked — offered and PM-gated
- [ ] Commit is scoped to goal artifact + stubs only — no blanket add
