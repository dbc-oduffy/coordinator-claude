<!-- Layer 0 of agent-install.md substitutes {{DATE}} and {{BRANCH}} when copying this to state/handoffs/ -->
---
title: "Continue coordinator onboarding and installation"
created: {{DATE}}
branch: {{BRANCH}}
status: active
predecessor: null
category: infra
summary: "Resume post-install: lay the install-chain spine, reload the live surfaces, then begin the collaboration contract by co-writing CLAUDE.md together"
workstream: coordinator-onboarding
scope:
  # The operator's live Claude Central is the surface this workstream evolves.
  # Scope is intentionally loose — the install continuation may touch any of these.
  # If {{BRANCH}} is not a claude-central branch, the EM narrows this at pickup.
  - CLAUDE.md
  - CLAUDE.local.md
  - coordinator.local.md
  - .claude/settings.json
  - state/handoffs/**
deployment_state: ready_to_fire
pickup_ready: true
---

# Session Handoff — Continue Onboarding and Installation

## What Was Accomplished

The coordinator install script has run. The *whole* system went in — not a cherry-picked
subset, not "like installing Linux, not that deep." What was installed is not really software;
it is a **collaboration contract** the operator and their now-Coordinator-shaped Claude will
customize together, starting in this session. The following initial state is confirmed:

- Plugin files present at `~/.claude/plugins/coordinator-claude/`
- `~/.claude/CLAUDE.md` bootstrapped (still the shipped default — the contract every agent reads
  before it even speaks to the operator, not yet personalized)
- Git tracking on `~/.claude` offered and either accepted or deferred

This handoff exists because the install intentionally **does not** write the collaboration
contract for the operator. That first edit — co-writing CLAUDE.md — is the opening demonstration
of Coordinator-Claude improving itself, and it belongs in a real working session with the
operator, not inside an install script.

## Current State

The operator has a running coordinator install but has not yet:

1. Reloaded the live plugin/skill surfaces so the things they are about to edit are the
   fully-present, live ones — this happens *before* any customization, on purpose: you do not
   shape a contract against a half-loaded copy of it (see Step 1)
2. Co-written their `CLAUDE.md` / `CLAUDE.local.md` with an EM — the **first** customization of the
   contract, and the opening demonstration of Coordinator-Claude improving itself (see Step 2)
3. Encoded their preferred working relationship (PM-EM model vs. direct delegation) into
   their live config
4. Confirmed all install legs completed (some may have been deferred or warned-soft-missing)
5. Laid out and followed through any *other* install spinoffs they queued before the restart
   (deep-research, or downstream repos) — see Step 0
6. Taken their first real working spin through the pipeline

The system is functional. The order below — **install → reload the live surfaces → orient,
starting with the contract** — is not a setup checklist. It is the operator and their
Coordinator-shaped Claude beginning to shape the contract to fit them, with the very first edit
serving as the opening self-improvement demo.

## Recommended Next Steps

### 0. Lay a durable spine before anything else

Coordinator installs and runs **standalone** — it is not part of any mandatory chain. But it is also
the natural *first* thing to install when an operator wants several related tools, precisely because
the durability below is what a vanilla session lacks. The whole collaboration contract is now in
place; before the operator and their Coordinator-shaped Claude start customizing it, make the install
survivable across compaction. The spine tracks each leg along three sub-axes — **installed /
provisioning / oriented** — so a long-running step (e.g. a downstream repo's background index) and a
not-yet-oriented leg are both legible at a glance and neither is silently dropped.

1. **Open a flight recorder** (Tasks API) for this session: goal = "complete coordinator onboarding
   and any queued install legs", with a task per step below.
2. **Look for the install spinoffs the operator queued.** The operator may have chosen to install
   `deep-research` (the recommended OSS add-on) and/or other downstream repos before the restart.
   Each such choice was seeded as a **spinoff** — a fork of a *different* install topic, authorized
   by the operator at the pre-restart question. Spinoffs live in the **standard handoff folder**
   (`state/handoffs/`, same as `/spinoff`'s output), tagged `kind: spinoff` with an
   `install_chain_order:`; that tag is what distinguishes them from this onboarding handoff:

   ```bash
   grep -l 'install_chain_order:' "${CLAUDE_HOME:-$HOME/.claude}/state/handoffs/"*.md 2>/dev/null
   ```

   There may be **zero, one, or several**. Read what is actually there — do **not** assume a fixed
   set, order, or that any particular downstream repo is present. Coordinator knows only
   `deep-research` by name; everything else is whatever the operator queued. These are install
   spinoffs, not this session's continuation — `predecessor: none` is native to a spinoff, so there
   is no lineage to reconcile; you are stitching a set of authorized forks. (Because they carry
   `kind: spinoff`, `/workday-start` already surfaces them as "spinoffs awaiting pickup" and
   `/pickup` classifies them correctly — no special handling needed.)
3. **Write a lightweight install-chain spine to disk** — start from the pre-made template at
   `${CLAUDE_HOME:-$HOME/.claude}/plugins/coordinator/templates/plans/install-chain-tracking.md`,
   copy it to `tasks/<feature>/install-chain.md`, and edit it to list each install spinoff you found
   (coordinator onboarding — this handoff — first; the spinoffs in whatever order each declares via
   `install_chain_order:`, else discovered order). Fill the spine's per-leg **install / provision /
   orient** status as you go, so a leg that is installed-but-still-provisioning (a background index,
   say) or installed-but-not-yet-oriented is visibly distinct from a finished one. The spine exists
   for one reason: **guarantee every queued install spinoff is followed to conclusion before the
   workstream is completed**, so nothing the operator asked for is silently dropped when context
   turns over. This is the same spine-plus-spinoffs shape `coordinator:roadmap-planning` produces;
   lay out the whole chain ahead of you even if it is just this one item.

4. **Resolve any supersession relationships in the spine.** Some spinoffs carry a `supersedes:`
   field that conditionally replaces an earlier orientation or install-leg baton. The mechanism is
   the shipped one — `supersedes:` on a `kind: spinoff` baton — documented in full at
   `docs/wiki/agent-install-contract.md § Orientation-supersession`. Do **not** re-derive it here;
   apply it. For each baton present in `state/handoffs/` that declares `supersedes: <X>`, drop or
   defer `<X>`'s entry from the install-chain spine in favor of the declaring baton's. If no present
   baton declares `supersedes: <X>`, then `<X>` stands as-is — it is the correct default for that slot.

   ```bash
   # Generic over supersedes:<any-id>; names no specific repo/orientation/order.
   grep -l 'supersedes:' "${CLAUDE_HOME:-$HOME/.claude}/state/handoffs/"*.md 2>/dev/null
   ```

   Read each match to identify which orientation or leg baton it supersedes, then update the
   spine accordingly before beginning execution. This pass is a spine-edit only — do not yet
   pick up the superseding baton; that happens in sequence order below.

Then proceed through the steps below. As you finish coordinator onboarding, pick up each install
spinoff (`/pickup state/handoffs/<leg>.md`) in turn and check it off the spine as it completes.

### 1. Reload the live surfaces first

Before the operator edits anything, make the surfaces they are about to shape the **live,
fully-present** ones. The install wrote the whole system to disk, but a session started before (or
during) the install may be running against a half-loaded copy. You do not co-write a contract
against a stale image of it — so reload before customizing, not after:

```
/reload-plugins
/reload-skills
```

(If the session predates the install entirely, a clean Claude Code restart is the surer reload.)
Then confirm the environment without triggering a re-install:

```
/coordinator:install --check-only
```

This re-reports environment state. With the live surfaces confirmed present, the customization in
Step 2 lands against the real thing.

### 2. Co-write `CLAUDE.md` and `CLAUDE.local.md` together — the first customization

**This is the first customization of the contract, and the highest-leverage one.** `CLAUDE.md` is
the contract every agent reads before it even speaks to the operator — so editing it together,
right after reload, *is* the opening demonstration of Coordinator-Claude improving itself. Framing
changes before details: shape how you work together before tuning any single knob.

The coordinator ships with an opinionated default `CLAUDE.md`. Before doing real work in any
repo, the operator and EM should write the version that actually fits how *they* want to work.

**Partnership-shape offer (offer, not gate — offer this explicitly and let the operator choose):**

When beginning this conversation, surface the two main working-relationship framings and ask
which fits better — or whether they want a hybrid:

> "The coordinator is designed around two different postures, and neither is wrong. Which
> feels closer to how you think about this?
>
> **Option A — PM and Engineering Manager.** You're the PM: you own product direction, scope,
> and ship decisions. I'm the EM: I own implementation, dispatch, delegation, and review
> orchestration. You brief me like a product manager would brief a strong engineering partner —
> direction and goals, not step-by-step instructions. I push back when I think you're wrong.
> This is the 'First Officer Doctrine' the shipped CLAUDE.md describes.
>
> **Option B — You direct a team of agents.** You stay more hands-on in implementation
> choices. I'm more of a senior IC who executes clear briefs and flags issues, rather than an
> EM who takes over the engineering function. The same pipeline and reviewer infrastructure
> applies — you just stay closer to the wheel.
>
> Both are reversible — we can update the CLAUDE.md framing at any time as you learn what
> actually fits. Which feels more like where you want to start?"

Once the framing is chosen, encode it in `CLAUDE.md` (or `CLAUDE.local.md` for the
meta-repo). Key surfaces to co-write:

- The collaboration framing section (PM-EM doctrine vs. adjusted variant)
- Communication style and preferences
- Any domain-specific context (project type, stack, constraints)
- Whether the operator wants explicit review dispatches or prefers the EM to judge silently

**Important: all customizations land in `~/.claude` — the live, git-tracked install surface.
Do NOT edit the `coordinator-claude` source repo or any clone of it.**

→ Cross-reference: `docs/wiki/getting-started.md` Movement 2 for the full customization menu.

### 3. Finish any deferred install legs

During install, some legs may have been deferred or shown as soft-missing. Check:

```bash
bash "${CLAUDE_HOME:-$HOME/.claude}/plugins/coordinator/bin/coordinator-setup-state.sh" status
```

If any install phase is flagged incomplete or deferred, work through those now. Common
deferred items:

- `~/.claude` git remote not yet set up (create a private repo and push)
- Optional plugins not yet installed (deep-research-claude, project-rag)
- `.mcp.json` wiring for sibling repos not yet done

A leg may install instantly but **provision** slowly — a downstream repo's first RAG index can
run for the better part of an hour. That provision step runs in the background and does **not**
block this chain; record it as `provisioning` in the spine (Step 0) and move on, returning to
orient that leg once it reports ready.

(If co-writing the contract in Step 2 changed `CLAUDE.md`, `settings.json`, or plugin files, a
quick `/reload-plugins` + `/reload-skills` — or a restart — picks the edits up cleanly; the
*initial* reload already happened in Step 1.)

### 4. Point the operator at `~/.claude` as their evolving surface

Close the session by orienting the operator to their own meta-repo:

- **`~/.claude` is their Claude Central** — the surface they evolve, git-track, and back up.
  All methodology refinements land here. The `coordinator-claude` source repo is a
  distribution artifact; edits there don't change their running sessions.
- **Lessons compound into doctrine.** As they work, `/coordinator:learn-lessons` promotes
  patterns from `state/lessons.md` into `docs/wiki/`. The system gets better as they use it.
- **The setup is optional and re-runnable.** If they want to revisit any part of onboarding,
  `docs/wiki/getting-started.md` is the guided-tour wiki, and `/coordinator:install --check-only`
  re-audits the environment anytime.

---

## Blockers and Issues

None. This handoff is ready to pick up immediately.

---

## Notes for the Picking-Up Session

This is a **fresh-start handoff** — there is no prior session state to reconcile. The
picking-up EM should:

1. Read this handoff at `/pickup state/handoffs/continue-onboarding-and-installation.md`
2. Lay the install-chain spine (Step 0), then **reload the live surfaces (Step 1) before any
   customization** — the order is install → (spine-build, Step 0) → reload → orient, and you do not
   shape the contract against a half-loaded copy of it
3. Run a quick `/workstream-start` orient (if the operator is in a real repo) or skip it (if
   they are starting from `~/.claude`)
4. With the live surfaces confirmed, open the "co-write CLAUDE.md" conversation (Step 2) — lead
   with the partnership-shape offer as the **first** customization of the contract, not a feature
   tour
5. Run the getting-started guided tour (`docs/wiki/getting-started.md`) if the operator
   wants it — the EM facilitates it as a conversation, not a recital

The operator may not know what `/pickup` does yet. The install script's final message should
have told them: "Start a fresh Claude Code session and run: `/pickup state/handoffs/continue-onboarding-and-installation.md`"

→ Cross-reference: `docs/wiki/post-install-onboarding-pattern.md` — the pattern doctrine
  (Movement 2 = first dogfood, refinement-target framing) this handoff body follows.
→ Cross-reference: `docs/wiki/getting-started.md` — the guided-tour wiki the EM uses for
  Movement 1–3 facilitation.
