---
name: goal-setting
description: "PM-GATED ceremony that converts raw vision (UI sketches, feature wishlists, enthusiasm) into ratified OKRs plus scaffolded spinoff stubs. Dispatches the VP-Product Reviewer as full OKR critic before any artifact lands on disk. Exit: goal artifact(s) + spinoff-roadmap-creator stubs pre-tagged to the goal. Triggers — 'set goals for this quarter', 'I have a vision for X', 'let's OKR this'."
description-budget: 300
version: 1.0.0
user-invocable: true
---

# Goal-Setting — Vision to OKRs to Spinoff Stubs

> **Posture (load-bearing):** vision-in, OKR-out. Neither obsequious rubber-stamp nor idea-crushing gate — the job is "put enough definition on this that we can win together." Each KR must be weekly-perceptible (can an agent or PM observe it move this week?). KRs that fail this test are later-impact aspirations, not measurement handles; surface them as shaping questions, not rejection verdicts.

**Two entry points:**

1. **Direct invocation** — the PM arrives with raw vision: UI sketches, a feature wishlist, enthusiasm, a rough "I want us to do X this quarter." There is no formed OKR yet.
2. **Pickup-from-spinoff-goal** — a `kind: spinoff-goal` stub was deferred earlier (a vision-slice captured but not yet fleshed); the EM picks it up and runs this skill on the captured vision.

**What this skill produces:**
- A ratified OKR (one Objective + ≤5 Key Results, weekly-perceptible) in a `coordinator-doc-new --type goal` artifact
- `kind: spinoff-roadmap-creator` stubs pre-tagged to the goal, one per roadmap-worth-of-work — the building blocks the PM will later chain through `/roadmap-planning`
- Optionally: `kind: spinoff-goal` stubs for vision-slices identified but not yet fleshed (deferred vision capture, not deferred goal-setting)
- An OFFER to chain into `/roadmap-planning` (PM-gated — offer, never auto-run)

<HARD-GATE>
This skill DOES NOT auto-author roadmap plans. It does not invoke `/roadmap-planning` without PM acknowledgment. It does not bypass the roadmap-planning PM gate. It scaffolds stubs and offers the chain. The PM decides whether and when to fire each stub.
</HARD-GATE>

---

## When NOT to invoke

- **Problem not yet converged** (PM is still deciding *what* to build, not *what to achieve*) → `coordinator:shape` or `coordinator:brainstorming` first.
- **Single-feature scope** (one plan, no broader OKR arc) → straight to `coordinator:plan`.
- **Roadmap already has goals** (picking up an existing spinoff-roadmap-creator stub against an already-ratified goal) → `/roadmap-planning` directly.

---

## Ceremony

### Step 1 — PM states Objective and candidate Key Results

The PM names:
- The **Objective** (qualitative, inspiring, direction-setting — what "winning" looks like)
- One or more **candidate KRs** (what movement means — ideally measurable; raw is fine at this stage)

Do NOT prompt for a specific format. Accept rough inputs. The ceremony imposes structure through critique, not intake.

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
- Weekly-perceptibility notes: either rewrite to weekly-perceptible or explicitly defer to a `kind: spinoff-goal` stub for a future goal cycle

This step is a dialogue, not a unilateral EM rewrite. The EM presents the VP-Product Reviewer's critique, proposes a revised OKR shape, and asks the PM to confirm before moving to Step 4.

**Do NOT proceed to Step 4 without explicit PM confirmation on the revised OKR.**

### Step 4 — Scaffold the goal artifact

Once the PM confirms the revised OKR:

```bash
coordinator-doc-new --type goal --title "<objective-slug>"
```

Fill the scaffold with:
- `objective:` — the ratified Objective text
- `key_results:` — the ratified KR list (≤5, weekly-perceptible)
- `period:` — the goal period (e.g., `Q3-2026`, `week`, `sprint-name`)
- `status: active`

### Step 5 — Spawn spinoff stubs

#### 5a. Spinoff-roadmap-creator stubs (one per roadmap-worth-of-work)

For each distinct roadmap the goal implies, scaffold one stub:

```bash
coordinator-doc-new --type spinoff \
  --kind spinoff-roadmap-creator \
  --goals "<goal-id>" \
  --title "<roadmap-topic>"
```

**What makes a roadmap-worth-of-work boundary?** Roughly: one `/roadmap-planning` invocation, one coherent domain or capability arc, one squad's sprint sequence. When in doubt, err toward fewer, larger stubs — the PM can split at pickup; merged stubs are better than over-fragmented ones.

Each stub must carry:
- `kind: spinoff-roadmap-creator`
- `goals:` FK pointing to the goal artifact created in Step 4
- `deployment_state: awaiting_gate` (awaiting PM fire)
- A one-line `title` that names the capability arc

#### 5b. Spinoff-goal stubs for deferred vision-slices (optional)

When the ceremony surfaces vision-slices that are real aspirations but out-of-scope for this goal period — or KRs that failed the weekly-perceptibility test and the PM chose to defer rather than rewrite — capture each as a `kind: spinoff-goal` stub:

```bash
coordinator-doc-new --type spinoff \
  --kind spinoff-goal \
  --title "<deferred-vision-slice>"
```

Each stub carries:
- `kind: spinoff-goal`
- `deployment_state: awaiting_gate`
- A brief body capturing the vision-slice verbatim (raw is fine — fidelity matters more than polish)

These stubs are the **pickup-from-spinoff-goal** entry point for a future goal-setting invocation. They are NOT roadmap stubs; they are vision preservation.

### Step 6 — Offer the PM-gated chain

Surface:

> _"Goal artifact and {N} spinoff-roadmap-creator stub(s) scaffolded. Want me to chain into `/roadmap-planning` now to begin shaping the first roadmap, or do you want to review the stubs first?"_

**Wait for PM response.** Do NOT invoke `/roadmap-planning` without explicit PM direction. The chain is an offer, not a pipeline step.

### Step 7 — Commit goal + stubs

Once the PM confirms (chain or defer):

```bash
git add -- <goal-artifact-path> <stub-path-1> [<stub-path-N>]
git commit -m "goal-setting: ratify <objective-slug> + scaffold {N} spinoff stubs"
```

Scoped staging only — no blanket add.

---

## Out of scope (architectural reasons)

- **Roadmap authoring** — `/roadmap-planning` owns that; goal-setting produces the stubs that feed it, not the plans themselves. Auto-chaining bypasses the PM's sequencing authority over a multi-wave plan, which is a PM-altitude call.
- **KR tracking infrastructure** — cockpit-contract `goal.schema.json` owns event emission; goal-setting scaffolds the artifact, not the tracking pipeline.
- **Deferred-goal fleshing without PM pickup** — a `kind: spinoff-goal` stub is dormant until the PM picks it up via this skill's second entry point. Auto-fleshing deferred stubs without PM context re-entry violates the vision-in, OKR-out posture.

---

## Skill-scaffold checklist (self-verify before reporting DONE)

- [ ] the VP-Product Reviewer dispatched at Opus altitude via `subagent_type: "coordinator:vp-product"`
- [ ] PM confirmed revised OKR before any artifact written to disk
- [ ] Goal artifact scaffolded with `coordinator-doc-new --type goal`
- [ ] Each spinoff-roadmap-creator stub carries `goals:` FK and `deployment_state: awaiting_gate`
- [ ] `/roadmap-planning` was NOT auto-invoked — it was offered and PM-gated
- [ ] Commit is scoped to goal artifact + stubs only — no blanket add
