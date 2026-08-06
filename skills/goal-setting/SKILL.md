---
name: goal-setting
description: "PM-GATED. Turns raw vision into ratified OKRs plus roadmap-seed stubs."
version: 1.0.0
user-invocable: true
---

# Goal-Setting — Vision to OKRs to Scaffolded Stubs

> **Posture (load-bearing):** vision-in, OKR-out. Neither obsequious rubber-stamp nor idea-crushing gate — the job is "put enough definition on this that we can win together." Each KR must be weekly-perceptible (can an agent or PM observe it move this week?). KRs that fail this test are later-impact aspirations, not measurement handles; surface them as shaping questions, not rejection verdicts.

**Entry points:**

1. **Direct invocation** — the PM arrives with raw vision: UI sketches, a feature wishlist, enthusiasm, a rough "I want us to do X this quarter." There is no formed OKR yet.
2. **Pickup-from-goal-seed** — a `kind: goal-seed` stub was deferred earlier (a vision-slice captured but not yet fleshed); the EM picks it up and runs this skill on the captured vision.
3. **Conform intake from a sizing-object (roadmap-routed)** — the sizing lobby (`coordinator:sizing`) resolves initiative-scale asks to the PM-decision route with an `xl_exit: roadmap` pick, or — on an older sizing-object — directly to `route: roadmap`, and hands the receiving ceremony a `state/sizings/<id>.yaml` sizing-object as an optional entry contract before Step 1 runs, either way. This is a conform intake, not a replacement for entry points 1-2 above — no sizing-object present means Step 1 runs exactly as today; the sizing lobby never gates or refuses a `goal-setting` invocation absent one, by explicit anti-scope ruling ("do not build a wall").

**What this skill produces:**
- A ratified OKR (one Objective + ≤5 Key Results, weekly-perceptible) in a `coordinator-doc-new --type goal` artifact
- `kind: roadmap-seed` stubs pre-tagged to the goal, one per roadmap-worth-of-work — the building blocks the PM will later chain through `/roadmap-planning`
- Optionally: `kind: goal-seed` stubs for vision-slices identified but not yet fleshed (deferred vision capture, not deferred goal-setting)
- An OFFER to chain into `/roadmap-planning` (PM-gated — offer, never auto-run)

<HARD-GATE>
This skill DOES NOT auto-author roadmap plans. It does not invoke `/roadmap-planning` without PM acknowledgment. It does not bypass the roadmap-planning PM gate. It scaffolds stubs and offers the chain. The PM decides whether and when to fire each stub.
</HARD-GATE>

---

## When NOT to invoke

- **Problem not yet converged** (PM is still deciding *what* to build, not *what to achieve*) → `coordinator:shape` or `coordinator:brainstorming` first.
- **Single-feature scope** (one plan, no broader OKR arc) → straight to `coordinator:plan`.
- **Roadmap already has goals** (picking up an existing roadmap-seed stub against an already-ratified goal) → `/roadmap-planning` directly.

---

## Ceremony

### Step 1 — PM states Objective and candidate Key Results

The PM names:
- The **Objective** (qualitative, inspiring, direction-setting — what "winning" looks like)
- One or more **candidate KRs** (what movement means — ideally measurable; raw is fine at this stage)

Do NOT prompt for a specific format. Accept rough inputs. The ceremony imposes structure through critique, not intake.

**When a roadmap-routed sizing-object is present (conform intake, entry point 3 above — either `route: pm-decision` with `xl_exit: roadmap`, or a legacy `route: roadmap` object):** it
pre-populates part of this step's raw-vision framing, in body prose only — never as new
frontmatter on the goal artifact or the downstream stubs. What crosses, and where it lands:
- `intent` — the PM's raw ask, verbatim — becomes the opening vision statement this step expects.
- `appetite` — context only, a Shape-Up budget signal that may bound ambition. Never a KR, never
  a downstream stub's `cost:` value.
- `estimate.tshirt` + `estimate.provisional` — both together, never `tshirt` alone. A coarse
  routing signal that the ask is roadmap-scale, explicitly not a promoted level-of-effort.
- `scout_evidence` — pointers only, feeding this step's framing.
- `route` (plus `xl_exit` when `route` is `pm-decision`) — together become the recorded reason
  this ceremony was opened (sizing-routed vs. direct invocation). On the current shape, `route`
  alone (`pm-decision`) doesn't say why roadmap-planning is the destination — `xl_exit: roadmap`
  is the actual PM pick that carries that meaning, so record both, not just the route name. On a
  legacy `route: roadmap` object, `route` alone already carries that meaning. Either way, any
  rationale is sourced from the sizing exchange itself — the sizing-object carries no rationale
  slot. Body prose only.

Does NOT cross: `detents` (lobby-internal record-keeping; this ceremony has its own gates — the VP-Product Reviewer's
critique, PM confirmation), `status` (the sizing-object's own lifecycle field), and a resolved
`fork` — which on this artifact means exactly `fork: null`, since the schema defines the field as
unresolved-by-construction whenever it is non-null. An UNRESOLVED `fork` (non-null: `cut_to_fit` /
`raise_appetite`) DOES cross — as an open question the PM resolves in this step, not something
that resolves itself by having been raised once.

This is a receive-and-use-if-present detent, never a wall: Step 1 runs exactly as today whenever
no sizing-object is present, and the sizing lobby never gates or refuses a `goal-setting`
invocation absent one, by explicit anti-scope ruling ("do not build a wall").

### Step 1b — Offer to record competitive context (optional)

Vision talk routinely surfaces who else is in the space — inspirations, peers, competitors, aspirational targets — before the OKR even exists. Once the PM's raw vision names or implies a domain, offer once — but first check whether this repo already has positioning data captured: read `state/strategic/self-description.yaml` (if present) and check its `competitors[]` array. **Skip this offer silently if `competitors[]` is already populated** — same absent-OR-empty gating discipline the `workweek-start`/`workweek-complete` nudges and `repo-setup` Phase 3l apply, so a repo that already has curated competitor data (from a prior ceremony, `repo-setup`, or a workweek nudge) is never re-asked here. Only when the file is absent or `competitors[]` is empty:

> This reads like <inferred domain> work — want me to record which inspirations / peers / competitors / aspirational-targets you have in mind? It goes in your repo's strategic self-description (`state/strategic/self-description.yaml`) and makes later deliverable planning easier. (Skip freely — it's an offer, not a gate.)

On opt-in, record each named entity as a `competitors[]` entry in `state/strategic/self-description.yaml` (schema: `coordinator/schemas/strategic-self-description.schema.json`) via the same scaffold/authoring path Phase 3l of `repo-setup` uses (`coordinator:strategic-self-description-refresh`'s skeleton-authoring surface) — do not invent a second marking store. Each entry carries `name`, `relationship` (one of `competitor | peer | aspirational-target | complement | prior-art | superseded-by | supersedes`), `note`, and `provenance: curated` (this is a human-in-the-loop naming, not a generated guess).

On decline, proceed to Step 2 without further prompting — this is a single offer per ceremony, not a repeated nudge.

### Step 2 — Dispatch the VP-Product Reviewer as full OKR critic

**Dispatch via `Agent(subagent_type: "coordinator:vp-product", model: "opus")`.**

The VP-Product Reviewer's OKR critique mandate — inline in the dispatch prompt verbatim:

> You are the VP-Product Reviewer (VP of Product, they/them). You are reviewing a draft OKR set for strategic rigor. Your job is to act as a full OKR critic, not a rubber-stamp.
>
> Assess:
> 1. **Is the Objective a real Objective?** Qualitative, inspiring, direction-setting — not a metric disguised as a direction, not a tactic.
> 2. **Are the KRs real Key Results?** Measurable outcomes that signal the Objective is being achieved — not activity metrics ("we shipped X"), not output proxies that can hit green while the Objective misses.
> 3. **Is the SET reasonable?** ≤5 KRs per Objective. More than 5 means the Objective is unfocused or the team is spread too thin.
> 4. **Weekly-perceptibility test per KR:** Can an agent or PM observe this KR move in a given week? If not, it is a "later-impact" aspiration — a shaping question, not a rejection. Flag it as such with a proposed rewrite that IS weekly-perceptible, or a note that the PM should decide whether to defer it to a future goal cycle.
>
> Return: a structured critique with (a) verdict per element (PASS / FLAG / REJECT), (b) specific rewrite suggestions for flagged/rejected elements, (c) a SET-level verdict (GO / REVISE / REFRAME). Do not rewrite the entire OKR for the EM — give the EM and PM the material to revise it themselves.

### Step 3 — EM+PM integrate the VP-Product Reviewer's critique in-dialogue

The VP-Product Reviewer's critique is a co-shaping input. The artifact does NOT exist on disk yet. The EM and PM work through:

- REJECT items: must either be rewritten to pass or dropped
- FLAG items: rewrite or consciously accept with a rationale (acceptable to carry a flagged KR if the PM understands the tradeoff)
- Weekly-perceptibility notes: either rewrite to weekly-perceptible or explicitly defer to a `kind: goal-seed` stub for a future goal cycle

This step is a dialogue, not a unilateral EM rewrite. The EM presents the VP-Product Reviewer's critique, proposes a revised OKR shape, and asks the PM to confirm before moving to Step 4.

**Do NOT proceed to Step 4 without explicit PM confirmation on the revised OKR.**

### Step 4 — Scaffold the goal artifact

Once the PM confirms the revised OKR:

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-doc-new" --type goal --title "<objective-slug>"
```

Fill the scaffold with:
- `objective:` — the ratified Objective text
- `key_results:` — the ratified KR list (≤5, weekly-perceptible)
- `period:` — the goal period (e.g., `Q3-2026`, `week`, `sprint-name`)
- `status: active`

### Step 5 — Spawn downstream stubs

#### 5a. Roadmap-seed stubs (one per roadmap-worth-of-work)

For each distinct roadmap the goal implies, scaffold one stub:

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-doc-new" --type roadmap-seed --goals "<goal-id>" --title "<roadmap-topic>"
```

**`--type` and `kind` now agree.** Both are `roadmap-seed`. The retired doc-type spelling
`--type spinoff-roadmap-creator` is still accepted as a permanent alias for in-flight callers, but
`--type roadmap-seed` is the canonical form going forward.

**What makes a roadmap-worth-of-work boundary?** Roughly: one `/roadmap-planning` invocation, one coherent domain or capability arc, one squad's sprint sequence. When in doubt, err toward fewer, larger stubs — the PM can split at pickup; merged stubs are better than over-fragmented ones.

Each stub must carry:
- `kind: roadmap-seed`
- `origin_goal_id:` FK (array, `goal-`-prefixed entries — passed via `--goals` on the CLI) pointing to the goal artifact created in Step 4
- `deployment_state: awaiting_gate` (awaiting PM fire)
- A one-line `title` that names the capability arc

#### 5b. Goal-seed stubs for deferred vision-slices (optional)

When the ceremony surfaces vision-slices that are real aspirations but out-of-scope for this goal period — or KRs that failed the weekly-perceptibility test and the PM chose to defer rather than rewrite — capture each as a `kind: goal-seed` stub:

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-doc-new" --type goal-seed --title "<deferred-vision-slice>"
```

**`--type` and `kind` now agree** — both are `goal-seed`. The retired doc-type spelling
`--type spinoff-goal` is still accepted as a permanent alias, but `--type goal-seed` is canonical.

Each stub carries:
- `kind: goal-seed`
- `deployment_state: awaiting_gate`
- A brief body capturing the vision-slice verbatim (raw is fine — fidelity matters more than polish)

These stubs are the **pickup-from-goal-seed** entry point for a future goal-setting invocation. They are NOT roadmap stubs; they are vision preservation.

### Step 6 — Offer the PM-gated chain

Surface:

> _"Goal artifact and {N} roadmap-seed stub(s) scaffolded. Want me to chain into `/roadmap-planning` now to begin shaping the first roadmap, or do you want to review the stubs first?"_

**Wait for PM response.** Do NOT invoke `/roadmap-planning` without explicit PM direction. The chain is an offer, not a pipeline step.

### Step 7 — Commit goal + stubs

Once the PM confirms (chain or defer), stage only the goal artifact and the stubs this run scaffolded — scoped staging only, no blanket add:

```bash
git add -- <goal-artifact-path> <stub-path-1> [<stub-path-N>]
```

Then commit; the staged set is already exactly those paths, so no pathspec is needed on the commit itself:

```bash
git commit -m "goal-setting: ratify <objective-slug> + scaffold {N} downstream stubs"
```

---

## Out of scope (architectural reasons)

- **Roadmap authoring** — `/roadmap-planning` owns that; goal-setting produces the stubs that feed it, not the plans themselves. Auto-chaining bypasses the PM's sequencing authority over a multi-wave plan, which is a PM-altitude call.
- **KR tracking infrastructure** — cockpit-contract `goal.schema.json` owns event emission; goal-setting scaffolds the artifact, not the tracking pipeline.
- **Deferred-goal fleshing without PM pickup** — a `kind: goal-seed` stub is dormant until the PM picks it up via this skill's second entry point. Auto-fleshing deferred stubs without PM context re-entry violates the vision-in, OKR-out posture.

---

## Skill-scaffold checklist (self-verify before reporting DONE)

- [ ] the VP-Product Reviewer dispatched at Opus altitude via `subagent_type: "coordinator:vp-product"`
- [ ] PM confirmed revised OKR before any artifact written to disk
- [ ] Goal artifact scaffolded with `coordinator-doc-new --type goal`
- [ ] Each roadmap-seed stub carries `origin_goal_id:` FK and `deployment_state: awaiting_gate`
- [ ] `/roadmap-planning` was NOT auto-invoked — it was offered and PM-gated
- [ ] Commit is scoped to goal artifact + stubs only — no blanket add
