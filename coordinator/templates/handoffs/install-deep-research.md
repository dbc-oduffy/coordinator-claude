<!-- Seeded into state/handoffs/ by the coordinator install (agent-install.md Step 1f) ONLY when the
     operator opts into deep-research at the pre-restart question. That operator choice IS the spinoff
     authorization (see docs/wiki/spinoff-handoffs.md § Install-leg spinoffs). Layer 0 substitutes
     {{DATE}} and {{BRANCH}}. It is a `kind: spinoff` baton in the standard handoff folder — the same
     place /spinoff writes — so /pickup + /workday-start handle it with no special wiring.
     COORDINATOR-OWNED because deep-research ships bundled (no separate DR repo on disk to seed
     itself); revisit this template when the `/deep-research setup` flow changes. This is install
     spinoff order 1; the post-restart EM discovers it via the Step 0 sweep in
     continue-onboarding-and-installation.md and tracks it on the install-chain spine. -->
---
title: "Install deep-research (recommended OSS add-on)"
created: {{DATE}}
branch: {{BRANCH}}
kind: spinoff
status: active
predecessor: none
authoring_session: "coordinator install — operator opted into deep-research at the pre-restart question"
category: infra
summary: "Activate the bundled deep-research plugin and run /deep-research setup; verify a pipeline can dispatch"
workstream: install-deep-research
repo: deep-research-claude
install_chain_order: 1
scope:
  - .claude/settings.json
  - state/handoffs/**
deployment_state: ready_to_fire
pickup_ready: true
---

# Install deep-research

The operator opted into **deep-research** at the coordinator install's pre-restart question (that
choice is the authorization for this spinoff). It ships in the coordinator marketplace bundle, so
the plugin files are already present — "installing" it is activation plus first-run setup, not a
separate clone.

## Steps

1. **Confirm the plugin is enabled.** `deep-research@coordinator-claude` should be in
   `enabledPlugins`. If it is not, enable it and `/reload-plugins`.
2. **Confirm Agent Teams is live.** The deep-research multi-agent pipelines need
   `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` — this is the env var the fresh-session restart was
   for. If `/deep-research` pipelines report Agent Teams unavailable, the operator started this
   session without the env var; have them restart Claude Code from a shell where it is exported.
3. **Run first-run setup.** `/deep-research setup` — this also plants the `version.txt` baseline the
   boot currency-notification hook compares against (so the operator gets honest "update available"
   nudges later).
4. **Verify.** Run a tiny real query through one pipeline (e.g. a single-topic
   `/deep-research-web`) to confirm dispatch works end-to-end — a smoke test proves wiring, not
   useful results, so keep it small and real.

## Done

Check this spinoff off the install-chain spine, then continue the chain (or close out the install
workstream if this was the last leg).

## Note — no orientation baton, no supersedes

Deep-research carries **no `supersedes:` field and no orientation baton**. Its use is situational
(operator opts in at install time; later sessions invoke `/deep-research` when they need it) — there
is no persistent "current state of deep-research" to hand forward, so no orientation handoff is
seeded and no prior handoff is superseded.

After pickup, the only ceremony needed is `/reload-plugins` + `/reload-skills` — deep-research is
then live. It is worth noting why you would reach for it over a plain "Claude, research X": the
`/deep-research` pipelines run multi-source, adversarially cross-verified synthesis with full
citations, not a single-pass answer from training knowledge. Use it when the question is
consequential enough to want independent sources checked against each other, not just recalled.
