---
title: Coordinator onboarding/install redesign — the front door must enact the system it installs
date: 2026-05-30
ratified_by: Dónal O'Duffy
ratified_date: 2026-05-30
status: ratified
kind: problem-set
---

# Coordinator onboarding/install redesign

> Ratified by PM Dónal O'Duffy 2026-05-30. Frozen before any solution. This is the external coverage oracle for plans that cite it.
>
> Origin: first real external user (Britt O'Duffy, CS PhD candidate, Oxford) installed coordinator cold; the install surface failed in linked ways. Root cause is a **bootstrap paradox** — a vanilla, doctrine-less Claude is asked to install the coordinator doctrine, so it cannot behave like the system it is installing. The fix philosophy: **the install must enact the collaboration it installs** — decision-dense where shape is at stake, fast everywhere else; never the "press the button, don't think" express analog, which contradicts a system whose value is that Claude pushes back on half-formed work.

## Problems

- **P1 — Discovery: a cold Claude can't find the agentic install surface.** A fresh session landing on the repo / marketplace listing does not discover that an *agentic* install exists (an `agent.md`-shaped entrypoint, the flow, the decision gates). Britt's install only proceeded because the PM supplied that knowledge. The discovery surface (repo README, top-level agent-facing install doc, how the GitHub/marketplace listing reads *to an agent*) is in scope.
- **P2 — The front-door philosophy contradicts the product.** "Express = lob it all in, don't think" is a philosophical mismatch with coordinator, which *is* thoughtful collaboration where Claude pushes back on yeet-agents-at-a-problem operation. The express/DIY binary must be replaced by a single install **logic tree** in which the user is an active participant in the *shape* of what they get (shape lives mostly in CLAUDE.md / CLAUDE.local.md, not specific agents) — without becoming an interrogation marathon.
- **P3 — "Done" is defined as scripts-ran, not partnership-entered.** The install frames completion at "a script ran," when it is actually a multi-step agentic flow with decision gates. The real definition of done is *the user is comfortable in the partnership and can evolve it on their own terms.* The installing Claude must adopt the agentic flow (flight recorder + todo-tracked install front), not treat a single script as terminal.
- **P4 — The restart gate strands the user.** The installing Claude is unaware of its own transience: "restart Claude Code" is a death-without-resurrection boundary with no resumption. Today it walks the user up to that gate with no handoff. The restart is *load-bearing* (plugin/marketplace registration requires it) and must be reframed as "start a fresh session and paste one `/pickup` command" — applying our own handoff/mortality doctrine reflexively to the install. A `continue-onboarding-and-installation.md` handoff must be staged before the gate.
- **P5 — The wrong refinement surface is pointed at.** Post-install, the canonical target for continued evolution is the user's own `~/.claude` (git-tracked, backed up to cloud) — **never** the downloaded coordinator clone (a delivery truck). Britt was wrongly encouraged to modify the coordinator repo, then told it would need forking — exactly the wrong surface from that point on.
- **P6 — Ecosystem opacity.** It was never clear to agent or user whether deep-research was installed. The install must present a **three-tier ecosystem map**: core (coordinator); recommended-optional, default-on-with-opt-out (deep-research, from `github.com/dbc-oduffy/deep-research-claude`, whose install pulls from that repo); and specialized-not-part-of-this-install (UE/holodeck/game-dev stack, project-rag). deep-research's presence/absence must be explicit to both agent and user.
- **P7 — Post-install orientation aims at the wrong first task.** The default "now let's plan your new project" is wrong. The first collaborative session should be co-writing the user's CLAUDE.md / CLAUDE.local.md — the highest-leverage, gentlest, most reversible first dogfood — which is *also* where the partnership-shape choice (PM/EM vs. manager-and-team-of-agents) is **offered** (strongly-led, not a mandatory gate) and encoded. This teaches the partnership by enacting it.
- **P8 — Existing-structure users are unhandled.** No detection of Track A (install-from-zero, the majority) vs Track B (existing structure: non-default plugins, a substantially-edited CLAUDE.md, OR git-tracking). Track B day-one must be **minimal-honest**: detect, tell the user plainly we install cleanly from zero and that merging into their existing setup is their + their agents' job, and offer the same kernel.

## Scope notes (confirmed inferences)

- **Build surface:** authored and dogfooded in the meta-repo (`~/.claude` source), percolated to OSS `coordinator-claude` via `publish.sh` — not edited in the publish repo directly.
- **No kernel extraction; frontload everything pre-restart that can smooth post-restart.** The Layer-1 "kernel" (handoff + pickup + plan-concept + todo-tracked install front) is a **flow/sequencing concept**, not a separable pre-restart mini-install. Plugin registration and most skill capability require the restart and cannot run before it. But Layer 0 is **not** "bare-minimum then restart" — it does everything a vanilla session *can* do to make the post-restart experience smooth: register plugin/marketplace, stage the `continue-onboarding-and-installation.md` handoff, pre-write the todo-tracked install front / mini-plan, drop any files and capture any decisions that don't require the plugin loaded — so the post-restart session resumes into a prepared, low-friction state rather than a cold one. Three layers: Layer 0 (vanilla-runnable, maximally frontloaded — assumes zero doctrine), Layer 1 (kernel concepts, alive once the now-registered plugin loads), Layer 2 (post-restart — `/pickup` the handoff, load everything-that-doesn't-conflict, `/reload-plugins` + `/reload-skills`, then collaborative work).
- **First-dogfood is an authored step**, not advisory prose.

## Out of scope (architectural reasons)

- **Bespoke cherry-pick / merge engine for Track B (install-atop-existing).** Comparative extraction of "what's useful in coordinator vs. your existing setup" is unbounded judgment work we cannot stand behind as a supported path; the user and their own agents own it. We support install-from-zero only.
- **Carving the kernel into a standalone pre-restart mini-install.** Architecturally unnecessary — registration requires the restart, so the kernel is functional post-restart regardless; a separable install would duplicate substrate for no capability gain.
- **Offering the UE/holodeck/game-dev stack or project-rag to a generic OSS user.** Per `CLAUDE.local.md` OSS editorial principle: holodeck-owned content percolates holodeck→holodeck one-way; it is not on the OSS coordinator menu.
