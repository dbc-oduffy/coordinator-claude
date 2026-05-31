<!-- Layer 0 of agent-install.md substitutes {{DATE}} and {{BRANCH}} when copying this to tasks/handoffs/ -->
---
title: "Continue coordinator onboarding and installation"
created: {{DATE}}
branch: {{BRANCH}}
status: active
predecessor: null
category: infra
summary: "Resume post-install: co-write CLAUDE.md, finish deferred install legs, first dogfood"
workstream: coordinator-onboarding
scope:
  # The operator's live Claude Central is the surface this workstream evolves.
  # Scope is intentionally loose — the install continuation may touch any of these.
  # If {{BRANCH}} is not a claude-central branch, the EM narrows this at pickup.
  - CLAUDE.md
  - CLAUDE.local.md
  - .claude/coordinator.local.md
  - .claude/settings.json
  - tasks/handoffs/**
deployment_state: ready_to_fire
pickup_ready: true
---

# Session Handoff — Continue Onboarding and Installation

## What Was Accomplished

The coordinator install script has run. The environment is wired and the core setup is
complete. The following initial state is confirmed:

- Plugin files present at `~/.claude/plugins/coordinator-claude/`
- `~/.claude/CLAUDE.md` bootstrapped (may be the shipped default — the operator has not yet
  personalized it)
- Git tracking on `~/.claude` offered and either accepted or deferred

This handoff exists because the install intentionally **does not** complete the
collaboration-model conversation. That conversation is a co-creation step that belongs in a
real working session with the operator — not inside the install script.

## Current State

The operator has a running coordinator install but has not yet:

1. Co-written their `CLAUDE.md` / `CLAUDE.local.md` with an EM
2. Encoded their preferred working relationship (PM-EM model vs. direct delegation) into
   their live config
3. Confirmed all install legs completed (some may have been deferred or warned-soft-missing)
4. Taken their first real working spin through the pipeline

The system is functional. The first-session work below shapes it to fit them.

## Recommended Next Steps

### 1. Co-write `CLAUDE.md` and `CLAUDE.local.md` together (lead item — highest leverage)

**This is the single most valuable thing to do first, and the gentlest reversible entry point.**

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

### 2. Finish any deferred install legs

During install, some legs may have been deferred or shown as soft-missing. Check:

```bash
bash "${CLAUDE_HOME:-$HOME/.claude}/plugins/coordinator/bin/coordinator-setup-state.sh" status
```

If any install phase is flagged incomplete or deferred, work through those now. Common
deferred items:

- `~/.claude` git remote not yet set up (create a private repo and push)
- Optional plugins not yet installed (deep-research-claude, project-rag)
- `.mcp.json` wiring for sibling repos not yet done

### 3. Reload plugins and skills if config was changed

If `CLAUDE.md`, `settings.json`, or any plugin files were modified during this session,
restart Claude Code (or the relevant session) to pick up the changes cleanly. Then confirm
with:

```
/coordinator:setup --check-only
```

This re-reports environment state without triggering a re-install.

### 4. Point the operator at `~/.claude` as their evolving surface

Close the session by orienting the operator to their own meta-repo:

- **`~/.claude` is their Claude Central** — the surface they evolve, git-track, and back up.
  All methodology refinements land here. The `coordinator-claude` source repo is a
  distribution artifact; edits there don't change their running sessions.
- **Lessons compound into doctrine.** As they work, `/coordinator:learn-lessons` promotes
  patterns from `tasks/lessons.md` into `docs/wiki/`. The system gets better as they use it.
- **The setup is optional and re-runnable.** If they want to revisit any part of onboarding,
  `docs/wiki/getting-started.md` is the guided-tour wiki, and `/coordinator:setup --check-only`
  re-audits the environment anytime.

---

## Blockers and Issues

None. This handoff is ready to pick up immediately.

---

## Notes for the Picking-Up Session

This is a **fresh-start handoff** — there is no prior session state to reconcile. The
picking-up EM should:

1. Read this handoff at `/pickup tasks/handoffs/continue-onboarding-and-installation.md`
2. Run a quick `/session-start` orient (if the operator is in a real repo) or skip it (if
   they are starting from `~/.claude`)
3. Begin with the "co-write CLAUDE.md" conversation — lead with the partnership-shape offer
   from Step 1, not a feature tour
4. Run the getting-started guided tour (`docs/wiki/getting-started.md`) if the operator
   wants it — the EM facilitates it as a conversation, not a recital

The operator may not know what `/pickup` does yet. The install script's final message should
have told them: "Start a fresh Claude Code session and run: `/pickup tasks/handoffs/continue-onboarding-and-installation.md`"

→ Cross-reference: `docs/wiki/post-install-onboarding-pattern.md` — the pattern doctrine
  (Movement 2 = first dogfood, refinement-target framing) this handoff body follows.
→ Cross-reference: `docs/wiki/getting-started.md` — the guided-tour wiki the EM uses for
  Movement 1–3 facilitation.
