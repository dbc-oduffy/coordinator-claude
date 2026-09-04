# Getting Started — Your First Session After Install

> **What this is.** The optional "what next?" step at the end of `/coordinator:install`. Setup wired your environment; this is the guided tour of *how to actually work with it.* Written to be read directly, and to be **facilitated by the EM** — if you ask Claude to walk you through the system, it reads this guide and runs the tour as a conversation, not a lecture.

You didn't install software. You installed a **collaboration contract** — a way of working with an engineering manager (the EM — Claude) who sits *in your reasoning loop* as a thinking partner you brief, push back on, and learn alongside, not a delegate you assign tickets to and grade. The whole system went in (it's not a pick-and-choose of parts — *though it's not like installing Linux, nothing that deep*), and now the real work begins: you and your now-Coordinator-shaped Claude **customize it together**. This tour is the start of that, and the very first thing you tailor — your `CLAUDE.md` — is itself the opening demonstration of the system improving itself. Framing changes before details.

Almost everything below pays off under the thinking-partner posture. If a different posture fits you better, the system is built to be slimmed as readily as extended — that's part of the tour too.

There's no rush, and this step is genuinely optional *right now* — re-runnable any time you say "walk me through the coordinator" later. But re-runnable later isn't the same as safe to skip indefinitely: until you take the tour, `CLAUDE.md` stays the generic, un-tailored default, and you forfeit the single highest-leverage customization this system exists to demonstrate. If you'd rather learn by doing, skip it and start working — just know what you're deferring, not declining.

## How to take the tour

Just say to your EM:

> **"Walk me through the coordinator."**

The EM will pick up this guide and run the four movements below *with* you — orienting, tailoring, a real test drive, and onboarding your first repo — calibrated to your background and how you like to work. Or read on yourself; it stands alone.

---

## Movement 1 — Orient: what you just installed

The headline ideas, in the order they'll matter:

- **First Officer Doctrine.** You're the PM (product authority — what to build, what to ship, what to cut). The EM is the EM (implementation authority — how to build it, when to dispatch, how to review). The EM acts on engineering decisions without hand-holding, *and* pushes back when it disagrees with you. More Sisko and Dax than Picard and Riker.
- **The pipeline.** Non-trivial work flows through *plan → enrich → review → execute → review* rather than straight to code. It's cheaper to catch a wrong assumption in a plan than three sessions after shipping. `/coordinator:plan` is the front door.
- **Reviewer personas.** You have staff-engineer reviewers available at the cost of minutes and tokens — the Staff Engineer (generalist code/architecture), plus domain specialists (the Game Dev Reviewer for game-dev, the Data Science Reviewer for data/ML, the Front-End Reviewer and the UX Reviewer for web/UX) that activate based on your project type. Use them liberally; a second opinion isn't an admission of doubt.
- **The cadence.** `/workstream-start` and `/workstream-complete` bracket a working session. `/workday-complete` and `/workweek-complete` are daily and weekly ceremonies. They keep context from leaking away unrecorded — the real threat, more than imperfect code.
- **Where the doctrine lives.** Global `~/.claude/CLAUDE.md` (loads everywhere), per-project `CLAUDE.md`, per-repo `.claude/em-context.md` (your posture surface — see Tier 1 below), and the plugin's own wikis under `docs/wiki/`. Plugin wikis are *not* auto-loaded — the EM reads them on demand.

**You do not need to learn the machinery.** Coordinator ships dozens of agent types and a whole dispatch apparatus — which reviewer for which diff, when to parallelize, how the pipeline routes. *That's the EM's job, not yours.* You brief the EM in plain language; it picks the agents and runs them. Don't try to memorize the roster.

**EM facilitation:** don't recite all five. Ask what the operator's background is and what they're hoping to use this for, then lead with the two or three ideas that matter for *them*. Surface the rest only if they pull. This whole orientation is itself the system demonstrating how it improves itself — name that throughline when it helps.

---

## Movement 2 — Make it yours: tailor to taste

**Start with `CLAUDE.md` — the contract every agent reads before it even speaks to you.** Before any session does anything, before the EM forms its first sentence to you, it reads `CLAUDE.md`. It is the operating contract for the whole collaboration: who has authority over what, how you like to be pushed back on, what "done" means here. Editing it is the single highest-leverage customization you can make — and the *first*, because framing changes before details.

And edit it **together**, not solo. Hand-editing `CLAUDE.md` alone is fine, but co-writing it with your now-Coordinator-shaped Claude is the better move and the *opening demonstration of Coordinator-Claude improving itself*: you describe how you want to work, the EM proposes contract language, you refine it, and the very next session reads the result. The system tuning the rules it runs under, with you — that is the whole ethos in one act. Do this first.

Once the contract reflects how you actually work, the rest is detail.

**Edit your live `~/.claude`, not the `coordinator-claude` repo you installed from.** Claude Code loads doctrine, plugins, and settings from `~/.claude` — that directory *is* your install, and editing it changes how every session behaves. The source repo is a distribution artifact: edits there don't touch your sessions, and your next install overwrites them.

**A sibling rule for refresh-managed plugins.** Coordinator is *source-is-live* — `~/.claude` *is* the install, so "edit live" and "edit your copy" are the same act. Some plugins (e.g. `project-rag`) are different: their live runtime is a **managed checkout** that a background refresh periodically resets with `git checkout <track_ref>`. For those, the rule inverts to **"configure through the provided verbs; never hand-edit the wiring or the source."** Edits to a refresh-managed checkout do nothing useful (config lives in the registry, env, and per-project wiring — not the source tree) *and* get silently reverted on the next refresh. Reach configuration through each plugin's verbs (`machine-local set …`, the plugin's `setup` / `wire` commands), not by editing files in the checkout. Same mental model either way: you're configuring an infra tool, not maintaining a fork, and drift between a live install and its source is worth auditing periodically for either kind of plugin.

Things worth tweaking on day one (the EM should *offer* the one or two most relevant to your Movement 1 conversation, not dump the whole menu):

- **Persona names — and why the spellings are odd.** The reviewers carry unusual names ("the Staff Engineer", not "Patrick") on purpose: each name is a **hot-word**. Saying *"ask the Staff Engineer"* does two things at once — it triggers the reviewer fast (one token, no ambiguity), and it *disambiguates your intent*. *"Ask a staff engineer to look at this"* could send an eager Claude off to literally **email a staff engineer**; *"ask the Staff Engineer"* cannot be misread as anything but "run the reviewer." The deliberately unusual spelling, saved in your memory, keeps that intent unambiguous every time. Don't like "the Staff Engineer"? Rename them — the EM will run `name-personas.sh` for you: it shows you a dry-run preview of every name that will change *before* applying anything, so you can see exactly what you're agreeing to, then prompts for confirmation. Whatever you choose, **coin your own odd names** rather than plain words, so they keep working as hot-words. The unusualness is the feature.
- **`coordinator.local.md` project type.** Sets which domain specialists route in this repo (`general`, `game-dev`, `web-dev`, `data-science`).
- **How you want to work — the relationship is yours to tune.** The collaboration style (EM acts on engineering calls and keeps you briefed; you own product direction) is a starting point, not a fixed contract. Tuning it is the intended, supported path — and the EM can work through this with you right now, as part of the tour. Two tiers, drawn far apart:

  - **Tier 1 — supported and reversible (start here):** you didn't start from a blank page. During install, the installer already asked you to choose one of three named posture anchors — **precision** (you're in the planning and the detail, low tolerance for doubling back), **default** (the technical-PM starting point: EM acts on engineering decisions, surfaces tradeoffs, pushes back when it disagrees), or **substrate-free** (briefed at milestones — "you own the code; just surface me when it's done") — three points on one axis: how closely you're consulted, never how technical you are. The anchors select engagement *distance*, not technical altitude. That choice persists per-machine, in `~/.claude/coordinator-identity.yaml`; the rendered overlay itself lands in *this repo's* `.claude/em-context.md`, delivered only to your main session — never the global `~/.claude/CLAUDE.md`, which every dispatched subagent also reads and has no business carrying prose about how the two of you work together (a subagent has no operator to have a posture with). Run the installer in another repo later and it renders that same persisted choice there, at that repo's own setup time — the anchor travels with you; the rendered overlay is per-repo. The installer seeds a marker-delimited managed block (`<!-- coordinator:posture:start -->` … `:end -->`) containing a `## Posture` heading as content, inside `.claude/em-context.md`. That seed is a starting point, not the end of the conversation: edit it, refine it, co-author it with the EM right now — hand-edits go inside the markers, and re-rendering swaps the block in place rather than duplicating it. (If a pre-existing bare `## Posture`/`## Working Style` heading is already there from an earlier hand-edit, the installer detects that as a collision to resolve, not something it silently duplicates.) Want less ceremony? More transparency into reasoning? A different anchor entirely, or a hand-tuned blend? Write it into `.claude/em-context.md`. It is git-tracked; any change is one revert away. This is first-class, encouraged, COMPOSE-not-replace behaviour — the installer seeds it, and this tour is how you and the EM co-evolve it from there, together, over time.

  - **Tier 2 — deep structural surgery (cliff drawn far out):** Only if you restructure the system's own machinery — agent prompts, hook wiring, skill files — does anything here become unsupported. Past that line, coordinator updates won't preserve your changes, and you are effectively maintaining your own fork. This is a deliberate choice for teams building a truly custom install, not an everyday move. Keep "unsupported" and "fork" for this tier only — posture edits via `.claude/em-context.md`, including choosing or hand-refining one of the three seeded anchors, never land here. This is the same boundary this doctrine draws elsewhere: prose/posture is yours to tune, machinery is not.

  If a different working posture fits you better, this two-tier path is what "that's part of the tour too" points at.

- **Slim what you don't want.** Coordinator ships opinionated. If a ceremony or a consult chain doesn't fit you, cut it. The methodology of *how to evolve safely* is itself documented — see `ceremony-calibration.md` (when to add vs strip ceremony).
- **`settings.json`.** Hooks, permissions, env vars (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` unlocks staff sessions and research pipelines).

The coordinator is yours after install. Make it serve your actual work, not the other way around.

**One exception that runs the other way — when the rough edge is *ours*, not a matter of taste.** Tailoring lives in your `~/.claude` and stays there. But sometimes you'll hit an actual bug, or a `/coordinator:install` step that doesn't work on your machine. When that happens: patch your live `~/.claude` to get unblocked — that's always the right working copy, and your patch keeps you running until the upstream fix lands — and then send the *same* fix *upstream*, to the `coordinator-claude` source repo. A script-only install was whack-a-mole across machines, so the upstream coordinator mostly gets better when people send back what broke and how they fixed it. Don't polish it; the *what / how / why* matters more than clean code, and your EM can draft the PR or issue for you. → [CONTRIBUTING.md](https://github.com/dbc-oduffy/coordinator-claude/blob/main/CONTRIBUTING.md).

---

## Movement 3 — Take it for a spin: a real test drive

Reading about the loop and *feeling* it are different things. Pick something small and real — not a toy — and run it through the actual machinery so the difference between "assign a ticket" and "brief a partner" lands viscerally.

Good first spins, easiest to most:

1. **`/workstream-start`**, then ask the EM to orient you in one of your real repos — let it load context and tell you what it sees.
2. **A tiny plan.** Name a small change you actually want and say "let's plan it." Watch `/coordinator:plan` verify substrate against disk, run its pre-flights, and route the plan through a reviewer before any code is written.
3. **A review dispatch.** After (or instead), point a reviewer at a recent diff or the plan — `/review` for plans, `/review-code` for diffs — and read what comes back.
4. **`/workstream-complete`** to close the loop: capture a lesson, update docs, leave the trail tidy.

**EM facilitation:** pick *with* the operator, start at the rung that matches their comfort, and narrate what's happening as it happens — "here's why I'm dispatching a reviewer now," "here's the assumption the plan just checked." The goal is for them to feel the system thinking *with* them. **If the operator reshaped toward a milestone-surfacing (substrate-free) posture in Movement 2:** adapt the test drive to match that rhythm — demo a brief-then-report at a meaningful checkpoint rather than the full plan/review/workstream-complete ceremony. Show them the mode they signed up for, not the one they opted out of.

---

## Movement 4 — Point it at a project

The tour ends by putting coordinator on real work. Every operator leaves with one repo onboarded,
not a tailored install and nothing to use it on.

Ask which they have:

- **An existing repo** → `/coordinator:repo-setup`, run from inside it. Scaffolds the
  project-local surfaces, captures `project_type` so the right domain specialists route, and
  renders their posture overlay there from the anchor install already persisted.
- **Something new** → `/coordinator:new-project`, which scaffolds the repo and onboards it in one
  pass.

**EM facilitation:** ask, don't offer a menu — "which repo do you want to start with?" is the
whole question. If Movement 3's test drive already ran in one of their repos, that repo is the
obvious answer; confirm it and run `repo-setup` there rather than asking again. If they have
nothing in mind, `new-project` on a small real idea beats onboarding a repo they don't intend to
touch this week. Don't end the tour without one of the two having run.

## After the tour

- Run `/workstream-start` whenever you sit down to real work.
- The system is yours — evolve it. Capture what you learn as lessons (`/coordinator:learn-lessons`) so refinements compound into doctrine instead of evaporating.
- Onboard further repos with `/coordinator:repo-setup` as you get to them — the posture anchor travels; each repo gets its own overlay.
- Lost? `/coordinator:install --check-only` re-reports your environment, and the plugin wikis under `docs/wiki/` are the living reference.

Welcome aboard.

---

## For the EM facilitating this

Run it as a conversation, not a recital. Concretely:

- **Record the milestones (enduring, idempotent).** At the *start* of the tour — before Movement 1 — record `orientation_started`; when the operator reaches "After the tour" (or signals they're done), record `orientation_completed`. These are per-machine receipts sibling repos read to chain after coordinator setup; the helper is first-occurrence-wins, so re-recording is safe. Use the settings-home forwarder, the same surface `/coordinator:install` Phase 7 records through:
  One invocation each, through the settings-home forwarder. PowerShell host: `& "$env:COORDINATOR_SETTINGS_HOME\bin\coordinator-setup-state.exe" record orientation_started` (likewise for `orientation_completed`). POSIX hosts take Shape A/B — resolution ladder and both shapes: `snippets/resolve-coordinator-bin.md`.
  Schema and the cross-repo reader idiom are documented alongside `coordinator-setup-state`'s own implementation.
- **Calibrate first, then teach.** Open Movement 1 by asking about the operator's background and goals; lead with what's relevant to *them*. A seasoned engineer needs the philosophy; a newcomer needs the happy path.
- **Offer, don't dump.** In Movement 2, propose the one or two customizations that follow from what they told you — not the whole menu. (This is the design-as-offers ethos applied to onboarding.)
- **Make the test drive real.** Movement 3 should use one of *their* repos and *their* actual task. A real spin teaches; a contrived demo doesn't.
- **All customizations land in `~/.claude`, the live install** — never a separate clone of the source repo. This is the load-bearing correctness point of the whole tour; if the operator is about to edit the wrong tree, stop them.
- **It's optional and re-runnable.** If they'd rather learn by doing, point them at `/workstream-start` and stand down gracefully.
