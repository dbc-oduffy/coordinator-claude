# Upgrading coordinator-claude to v3

> Consumer-facing migration guide for moving a coordinator-claude install from a
> 2.x release to 3.0.0. Covers what changed, the concrete upgrade steps, what
> happens to your existing plugin selection, and what advanced consumers with
> tooling built against v2 record shapes need to re-check. See `CHANGELOG.md`
> for the full, authoritative list of breaking changes.

## At a glance

coordinator-claude 3.0.0 consolidates distribution: **five separately-installed
plugins become one.**

The v2 marketplace shipped `coordinator`, `web-dev`, `data-science`,
`deep-research`, and `notebooklm` as five separate plugins, each installed and
versioned independently. v3 folds all of them into a single `coordinator`
plugin with a flat repository layout (the plugin now lives at the repository
root instead of in a subdirectory).

The front-end reviewer agents and skills (formerly `web-dev`), the
data-science reviewer (formerly `data-science`), and the research pipelines
(formerly `deep-research` and `notebooklm`) all ship *inside* `coordinator`
now. Nothing about their functionality changed — they're reachable the same
way, from the same commands and skills. What changed is that you install one
plugin instead of five, and you get everything in a single, versioned unit.

## How to upgrade

1. **Install the single `coordinator` plugin at 3.0.0.** If you're setting up
   fresh, or updating an existing install, follow the install path described
   in the repo's `README.md` (Quick Start) and `AGENTS.md` / `docs/agent-install.md` —
   these are the authoritative, versioned sources for the exact
   marketplace-add and plugin-install commands, and they're kept current as
   the install mechanics evolve. In short: register the coordinator-claude
   GitHub repo as a marketplace, then install the `coordinator` plugin from
   it; a restart completes the install.

2. **Remove the retired standalone plugins.** If you previously installed
   `web-dev`, `data-science`, `deep-research`, and/or `notebooklm` as separate
   marketplace entries, those entries are retired in v3 — their functionality
   now lives inside `coordinator`, so keeping the old standalone plugins
   installed alongside the new `coordinator` would be redundant (and,
   depending on your Claude Code version, could register duplicate
   agents/skills). Remove them via whatever plugin-management surface your
   Claude Code version exposes for uninstalling a plugin — check your
   `README.md`'s troubleshooting/plugin-management section for the current
   command shape.

3. **Restart Claude Code** so the new plugin registration takes effect, same
   as any plugin/marketplace change.

If your install predates the native plugin-CLI flow described in the current
`README.md`, follow that README's Quick Start rather than any older
instructions you may have bookmarked — the install mechanics are actively
maintained there and are the right vocabulary to use.

## Layout change

In v2, each plugin lived under its own subtree of the repository (a
`coordinator/` folder, a `web-dev/` folder, and so on, each independently
versioned and each with its own `.claude-plugin/plugin.json`). In v3, the
`coordinator` plugin's source sits at the repository root — a flat layout,
one plugin, one version.

If you (or any tooling, scripts, or documentation you maintain) referenced
paths under the old per-plugin subtrees — for example, anything that assumed
a `web-dev/` or `data-science/` top-level folder in the coordinator-claude
repo — those paths no longer exist in the same shape. The equivalent content
now lives under the flat `coordinator` plugin tree. If you cloned the repo
directly rather than installing via the plugin marketplace, re-check any
hardcoded paths against the current repository layout before assuming they
still resolve.

## Contract / schema notes for advanced consumers

coordinator-claude's internal record/schema contract (the versioned shapes
used by coordinator's own tracked artifacts) advanced a major epoch in 3.0.
If you've built tooling, scripts, or automation that reads or parses
coordinator's record shapes directly — rather than going through the
documented commands and skills — re-check your assumptions against the
current schema before upgrading.

This guide intentionally keeps this section brief; the authoritative,
itemized list of breaking contract changes lives in `CHANGELOG.md` under the
3.0.0 entry's **Breaking changes** section. Read that section if you maintain
any tooling downstream of coordinator's record shapes.

## Engine — why v3 is lighter

If you install v3 and notice it's a smaller, leaner footprint than the
accumulated v2 surface, that's deliberate — and it's the leading edge of a
longer-term architectural direction, not a one-off trim.

The design principle going forward: **the plugin is the contract and the
doctrine — the rules — while execution is carried out by a separate,
dedicated engine — the machine that runs them.** Historically, a large amount
of the coordinator-claude plugin surface was execution machinery: shell
scripts and helper tooling that installed directly into your environment
alongside the doctrine, skills, and agent prompts. Going forward, that heavy
execution layer is being extracted out of the plugin and into a dedicated,
separately-maintained, performant engine — built in Python, living in its own
repository — rather than being carried as resident script weight inside the
plugin you install.

The plugin you install stays focused on what a coordinator-claude consumer
actually interacts with: the doctrine, the skills, the agent prompts, the
reviewer personas, the record schemas. The machinery that executes against
that contract becomes a separate, faster, purpose-built component rather than
bulk shipped alongside it. This is a direction-of-travel note, not a shipped
feature in 3.0.0 — but it's the reason v3's plugin footprint is lighter, and
the trend to expect in future releases.
