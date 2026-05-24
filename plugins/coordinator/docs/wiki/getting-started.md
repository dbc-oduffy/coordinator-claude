# Getting Started — Your First Session After Install

> **What this is.** The optional "what next?" step at the end of `/coordinator:setup`. Setup wired your environment; this is the guided tour of *how to actually work with it.* Written to be read directly, and to be **facilitated by the EM** — if you ask Claude to walk you through the system, it reads this guide and runs the tour as a conversation, not a lecture.

You didn't just install a set of slash commands. You installed a way of working: an engineering manager (the EM — Claude) who sits *in your reasoning loop* as a thinking partner you brief, push back on, and learn alongside — not a delegate you assign tickets to and grade. Almost everything below pays off under that posture. If a different posture fits you better, the system is built to be slimmed as readily as extended — that's part of the tour too.

There's no rush. This step is elective and re-runnable. Skip it and start working if you'd rather learn by doing.

## How to take the tour

Just say to your EM:

> **"Walk me through the coordinator."**

The EM will pick up this guide and run the three movements below *with* you — orienting, tailoring, and a real test drive — calibrated to your background and how you like to work. Or read on yourself; it stands alone.

---

## Movement 1 — Orient: what you just installed

The headline ideas, in the order they'll matter:

- **First Officer Doctrine.** You're the PM (product authority — what to build, what to ship, what to cut). The EM is the EM (implementation authority — how to build it, when to dispatch, how to review). The EM acts on engineering decisions without hand-holding, *and* pushes back when it disagrees with you. More Sisko and Dax than Picard and Riker.
- **The pipeline.** Non-trivial work flows through *plan → enrich → review → execute → review* rather than straight to code. It's cheaper to catch a wrong assumption in a plan than three sessions after shipping. `/coordinator:plan` is the front door.
- **Reviewer personas.** You have staff-engineer reviewers available at the cost of minutes and tokens — the Staff Engineer (generalist code/architecture), plus domain specialists (the Game Dev Reviewer for game-dev, the Data Science Reviewer for data/ML, the Front-End Reviewer and the UX Reviewer for web/UX) that activate based on your project type. Use them liberally; a second opinion isn't an admission of doubt.
- **The cadence.** `/session-start` and `/session-end` bracket a working session. `/workday-complete` and `/workweek-complete` are daily and weekly ceremonies. They keep context from leaking away unrecorded — the real threat, more than imperfect code.
- **Where the doctrine lives.** Global `~/.claude/CLAUDE.md` (loads everywhere), `~/.claude/CLAUDE.local.md` (loads when you're working in `~/.claude` itself), per-project `CLAUDE.md`, and the plugin's own wikis under `docs/wiki/`. Plugin wikis are *not* auto-loaded — the EM reads them on demand.

**EM facilitation:** don't recite all five. Ask what the operator's background is and what they're hoping to use this for, then lead with the two or three ideas that matter for *them*. Surface the rest only if they pull.

---

## Movement 2 — Make it yours: tailor to taste

**The one rule that matters most:** customize your **live, git-tracked `~/.claude` — your Claude Central — not the upstream `coordinator-claude` repo you installed from.**

Here's why. Claude Code loads doctrine, plugins, and settings from `~/.claude`. That directory *is* your install — editing it changes how every session behaves immediately. The `coordinator-claude` source repo (on GitHub, or a clone you may have made) is a *distribution artifact*: edits there don't touch your sessions, and your next install would overwrite them. So:

- **Edit `~/.claude`.** That's the system you actually run.
- **Git-track `~/.claude`.** Setup offered to `git init` it; if you declined, reconsider. Your `git log` becomes the audit trail of how your working methodology evolved — future-you needs to see what today-you tried and kept or discarded. A private remote means that history survives machine loss.
- **Don't expect edits to a separate clone of the source repo to do anything.** If you operate a fork to distribute *your own* customized coordinator to *your* team, that's a deliberate, separate workflow — not the path for everyday personal tweaks.

**A sibling rule for refresh-managed plugins.** Coordinator is *source-is-live* — `~/.claude` *is* the install, so "edit live" and "edit your copy" are the same act. Some plugins (e.g. `project-rag`) are different: their live runtime is a **managed checkout** that a background refresh periodically resets with `git checkout <track_ref>`. For those, the rule inverts to **"configure through the provided verbs; never hand-edit the wiring or the source."** Edits to a refresh-managed checkout do nothing useful (config lives in the registry, env, and per-project wiring — not the source tree) *and* get silently reverted on the next refresh. Reach configuration through each plugin's verbs (`machine-local set …`, the plugin's `setup` / `wire` commands), not by editing files in the checkout. Same mental model either way: you're configuring an infra tool, not maintaining a fork. → `live-install-drift-audit.md`.

Things worth tweaking on day one (the EM should *offer* the one or two most relevant to your Movement 1 conversation, not dump the whole menu):

- **Persona names.** Don't like "the Staff Engineer"? Rename the reviewers to names that fit your team.
- **`coordinator.local.md` project type.** Sets which domain specialists route in this repo (`general`, `game-dev`, `web-dev`, `data-science`).
- **`CLAUDE.local.md`.** Your meta-repo collaboration doctrine — the template is a starting point. Rewrite the role framing to match how you actually want to work.
- **Slim what you don't want.** Coordinator ships opinionated. If a ceremony or a consult chain doesn't fit you, cut it. The methodology of *how to evolve safely* is itself documented — see `ceremony-calibration.md` (when to add vs strip ceremony) and `lesson-triage.md` (how lessons graduate to doctrine).
- **`settings.json`.** Hooks, permissions, env vars (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` unlocks staff sessions and research pipelines).

The coordinator is yours after install. Make it serve your actual work, not the other way around.

**One exception that runs the other way — when the rough edge is *ours*, not a matter of taste.** Tailoring lives in your `~/.claude` and stays there. But sometimes you'll hit an actual bug, or a `/coordinator:setup` step that doesn't work on your machine. When that happens: patch your live `~/.claude` to get unblocked — that's always the right working copy, and your patch keeps you running until the upstream fix lands — and then send the *same* fix *upstream*, to the `coordinator-claude` source repo. A script-only install was whack-a-mole across machines, so the upstream coordinator mostly gets better when people send back what broke and how they fixed it. Don't polish it; the *what / how / why* matters more than clean code, and your EM can draft the PR or issue for you. → [CONTRIBUTING.md](https://github.com/dbc-oduffy/coordinator-claude/blob/main/CONTRIBUTING.md).

---

## Movement 3 — Take it for a spin: a real test drive

Reading about the loop and *feeling* it are different things. Pick something small and real — not a toy — and run it through the actual machinery so the difference between "assign a ticket" and "brief a partner" lands viscerally.

Good first spins, easiest to most:

1. **`/session-start`**, then ask the EM to orient you in one of your real repos — let it load context and tell you what it sees.
2. **A tiny plan.** Name a small change you actually want and say "let's plan it." Watch `/coordinator:plan` verify substrate against disk, run its pre-flights, and route the plan through a reviewer before any code is written.
3. **A review dispatch.** After (or instead), point a reviewer at a recent diff or the plan — `/review` for plans, `/review-code` for diffs — and read what comes back.
4. **`/session-end`** to close the loop: capture a lesson, update docs, leave the trail tidy.

**EM facilitation:** pick *with* the operator, start at the rung that matches their comfort, and narrate what's happening as it happens — "here's why I'm dispatching a reviewer now," "here's the assumption the plan just checked." The goal is for them to feel the system thinking *with* them.

---

## After the tour

- Run `/session-start` whenever you sit down to real work.
- The system is yours — evolve it. Capture what you learn as lessons (`/coordinator:learn-lessons`) so refinements compound into doctrine instead of evaporating.
- Lost? `/coordinator:setup --check-only` re-reports your environment, and the plugin wikis under `docs/wiki/` are the living reference (`DIRECTORY_GUIDE.md` indexes them).

Welcome aboard.

---

## For the EM facilitating this

Run it as a conversation, not a recital. Concretely:

- **Record the milestones (enduring, idempotent).** At the *start* of the tour — before Movement 1 — record `orientation_started`; when the operator reaches "After the tour" (or signals they're done), record `orientation_completed`. These are per-machine receipts sibling repos read to chain after coordinator setup; the helper is first-occurrence-wins, so re-recording is safe. Use the install-root resolver (`CLAUDE_HOME`, defaults to `~/.claude`):
  ```bash
  bash "${CLAUDE_HOME:-$HOME/.claude}/plugins/coordinator/bin/coordinator-setup-state.sh" record orientation_started
  # …facilitate the three movements…
  bash "${CLAUDE_HOME:-$HOME/.claude}/plugins/coordinator/bin/coordinator-setup-state.sh" record orientation_completed
  ```
  Schema and the cross-repo reader idiom: `coordinator-setup-state-receipt.md`.
- **Calibrate first, then teach.** Open Movement 1 by asking about the operator's background and goals; lead with what's relevant to *them*. A seasoned engineer needs the philosophy; a newcomer needs the happy path.
- **Offer, don't dump.** In Movement 2, propose the one or two customizations that follow from what they told you — not the whole menu. (This is the design-as-offers ethos applied to onboarding.)
- **Make the test drive real.** Movement 3 should use one of *their* repos and *their* actual task. A real spin teaches; a contrived demo doesn't.
- **All customizations land in `~/.claude`, the live install** — never a separate clone of the source repo. This is the load-bearing correctness point of the whole tour; if the operator is about to edit the wrong tree, stop them.
- **It's optional and re-runnable.** If they'd rather learn by doing, point them at `/session-start` and stand down gracefully.
