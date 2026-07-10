---
manifest: agent-install-manifest.json
contract: ../wiki/agent-install-contract.md
---

# Agent install guide — coordinator-claude

> **Chain position:** coordinator-claude is the **DAG root** of the agent install contract.
> It declares zero direct upstream dependencies and is always installed first. Any downstream
> repo that adopts the contract may declare coordinator-claude as a dependency; coordinator-claude
> itself declares none.

> **You are an agent reading this file** because the setup skill dispatched you to walk the
> install chain for coordinator-claude. Follow the install contract at
> `docs/wiki/agent-install-contract.md`. Do not improvise. If a step fails, stop and report.

---

## Chain posture

coordinator-claude is the **DAG root**: it declares **zero direct deps** (`direct_deps: []`).
The chain-walker visits coordinator-claude, observes the empty dep list, and terminates
immediately:

"chain walk complete — coordinator-claude is DAG root".

No upstream probe is needed — as the root, there is nothing above it to walk. Any downstream
consumer that depends on coordinator-claude recurses into this same terminal state; coordinator
is visited exactly once even when reached via multiple paths, via the disk-resident visited-set
per contract § Visited-set protocol.

---

## Three install verbs — disambiguation

coordinator-claude ships three distinct slash-commands that sound similar but serve different
purposes. Use the right one.

> **For the OSS solo install (the common path), the only post-restart verb you need is
> `/coordinator:install`** (then `/coordinator:repo-setup` to onboard a project). The three-verb
> disambiguation below is for agents arriving in a multi-repo chain-walk context — see
> [`docs/agent-install.md`](../../dist/publish-repo-docs/agent-install.md) for the solo playbook.

- **`/coordinator:setup`** — the **install-chain walker** required by the agent-install contract.
  Reads `agent-install-manifest.json`, walks the `direct_deps` list (empty for this DAG root),
  and terminates cleanly. This is the verb you invoke when performing a first-time or refreshed
  install-chain verification. It is specified by the contract at
  `docs/wiki/agent-install-contract.md` and is what the `setup_skill` field in the manifest
  points to.

- **`/coordinator:install`** — the **OSS plugin install** verb. Installs the coordinator plugin
  into a Claude Code environment from scratch (sets up hooks, skills, agents, CLAUDE.md). Not a
  chain-walker; not contract-mandated. Use this when bootstrapping the coordinator plugin for the
  first time in a new Claude Code environment.

- **`/coordinator:repo-setup`** — the **consumer-project first-time setup** verb. Configures a
  specific consumer project to use the coordinator (creates project CLAUDE.md, registers the
  project with the coordinator, sets up project-level hooks). Not a chain-walker; not a plugin
  installer. Use this when onboarding a new repo into the coordinator ecosystem.

In short: `/coordinator:setup` walks the install chain (contract); `/coordinator:install` installs
the plugin; `/coordinator:repo-setup` onboards a project. All three coexist; none replaces another.

## Install via the chain-walker

The `/coordinator:setup` skill reads `agent-install-manifest.json` at this path. Because
`direct_deps` is empty, the chain-walker takes the DAG-root terminal path immediately:

1. Reads manifest — confirms `repo_id: coordinator-claude`, `direct_deps: []`.
2. Emits banner: "chain walk complete — coordinator-claude is DAG root".
3. Exits 0.

No upstream probe, no consent gate, no spinoff seeding in this plan (coord-as-orchestrator
spinoff seeding is a follow-on workstream per plan §13).

Full walker contract: `docs/wiki/agent-install-contract.md`.

## Override flags

Both flags must be passed together; either alone exits with code 93. For this DAG root, no dep
check fires — override flags exist for schema-conformance only.

| Flag (key in manifest) | CLI string (value in manifest) | Purpose |
|---|---|---|
| `skip_dep_check` | `--skip-dep-check` | First flag of the override pair |
| `accept_hallucination_risk` | `--accept-missing-deps-risk` | Second flag; signals explicit accept of missing-dep risk |

> **Authority boundary note.** These flag values are upstream-authored — coordinator-claude
> declares them here. A consumer chain-walker reads them from this manifest at dispatch time
> rather than hard-coding them, so a rename propagates automatically. The key names
> (`skip_dep_check`, `accept_hallucination_risk`) are schema-canonical per the v2 contract.

## What the coordinator plugin provides

The coordinator plugin is the session-management spine of the Claude Code agentic ecosystem:

- **Session orchestration** — handoffs, spinoffs, workday/workweek cadence, fan-out dispatch
- **Review pipeline** — named Opus reviewers (the Staff Engineer, the Game Dev Reviewer, the Data Science Reviewer, the Front-End Reviewer, the UX Reviewer, the Director of Engineering), code-reviewer,
  review-integrator
- **Skills** — plan, enrich, review, workstream-complete, pickup, repo-setup, and more
- **Hooks** — PreToolUse tripwires, commit guards, auto-push, session-init
- **Agents** — executor, enricher, reviewer personas, scouts

Install the plugin first before walking the chain via `/coordinator:setup`. The plugin itself is
installed with the native Claude Code CLI (coordinator's canonical runtime — preferred over the
desktop app; install via `npm install -g @anthropic-ai/claude-code` if absent) from the public
GitHub repo — `claude plugin marketplace add dbc-oduffy/coordinator-claude` then `claude plugin
install coordinator@coordinator-claude` — after which a fresh session loads the commands and
`/coordinator:install` finishes the environment wiring. To start that fresh session: open a terminal,
`cd ~/.claude`, run `claude` (that is what "restart your session from `~/.claude`" means throughout
the install docs).
(Registering the GitHub repo rather than a clone path keeps the install self-contained under
`~/.claude`; the clone is only a build-time input.) See
[`docs/agent-install.md`](../../dist/publish-repo-docs/agent-install.md) for the full guided install playbook.

---

<!-- spec-backlink: ~/.claude/archive/specs/2026-06/2026-06-15-coordinator-install-chain-application-phase-b.md §7 C1 -->
<!-- spec-backlink: plugins/coordinator/docs/wiki/agent-install-contract.md -->
