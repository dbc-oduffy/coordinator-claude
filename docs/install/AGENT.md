---
manifest: agent-install-manifest.json
contract: ../wiki/agent-install-contract.md
---

# Agent install guide — coordinator-claude

> **Chain position:** coordinator-claude is the **root of the OSS plugin-adoption chain** —
> nothing installs "above" it, and it is always installed first among the peer plugins. Any
> downstream repo that adopts the contract may declare coordinator-claude as a dependency.
> As of **W0.5 Option B+C** (PM-ratified 2026-07-19), coordinator-claude itself declares ONE
> hard direct dep of its own: **claude-klabauter** (the engine) — a mandatory prerequisite of
> coordinator in every environment, including OSS-mirror installs. "DAG root" below means root
> of the plugin chain, not zero dependencies. **claude-klabauter is currently a private repo**
> (open-source release pending); until then, the maintainer grants access directly on
> request — the same distribution model already used for `project-rag`. A denied/404 clone is
> not a broken URL — see § Fail-loud claude-klabauter resolution below.

> **You are an agent reading this file** because the setup skill dispatched you to walk the
> install chain for coordinator-claude. Follow the install contract at
> `docs/wiki/agent-install-contract.md`. Do not improvise. If a step fails, stop and report.

---

## Chain posture

coordinator-claude is the root of the plugin-adoption chain (chain step 5 of 5). As of W0.5
Option B+C, it declares **one hard direct dep**: `claude-klabauter` (`severity: hard`,
`functional_probe_kind: claude_klabauter_seam_resolvable`). The chain-walker visits coordinator-claude,
probes that one dep, and terminates once it is satisfied:

"coordinator install-chain walker — chain step 5 of 5: all deps satisfied."

No upstream probe is needed in the plugin-chain sense — as the root of THAT chain, there is
nothing above coordinator-claude to walk — but the claude-klabauter probe still runs (it is
the walker's own mandatory engine dependency, not a plugin-chain edge). If claude-klabauter is
unresolvable, the walker fails loud: the `claude_klabauter_seam_resolvable` probe kind bypasses the
ordinary sibling-directory check (claude-klabauter is registry/env-resolved via CLAUDE_KLABAUTER_ROOT's
four-rung ladder, not sibling-colocated) — see § Fail-loud claude-klabauter resolution below. Any
downstream consumer that depends on coordinator-claude recurses into this same terminal state;
coordinator is visited exactly once even when reached via multiple paths, via the disk-resident
visited-set per contract § Visited-set protocol.

### Fail-loud claude-klabauter resolution

Because `coordinator/scripts/setup.py` (the chain-walker itself) is a trampoline into
Claude-klabauter-authored `coordinator_core.ops.setup_chain_walker`, CLAUDE_KLABAUTER_ROOT must already be
resolvable just to IMPORT the walker — a genuine chicken-egg constraint. If CLAUDE_KLABAUTER_ROOT cannot
be resolved via any of its four rungs, `setup.py` fails loud at that import step (exit 95, the
dedicated claude-klabauter-transport-failure code) with the four-rung remediation printed to stderr:

1. `CLAUDE_KLABAUTER_ROOT` environment variable.
2. `<settings-home>/machine-local/.claude-klabauter-root` pointer file.
3. `machine-local get repos.claude_klabauter` registry entry.
4. If none resolve: clone `claude-klabauter` as a sibling repo
   (`git clone https://github.com/dbc-oduffy/claude-klabauter`) and register it, or set
   `CLAUDE_KLABAUTER_ROOT` directly, then re-run `/coordinator:setup` or `/coordinator:install`.
   `claude-klabauter` is private until its OSS release — if the clone is denied or 404s, request
   access from the maintainer rather than treating the URL as broken.

---

## Three install verbs — disambiguation

coordinator-claude ships three distinct slash-commands that sound similar but serve different
purposes. Use the right one.

> **For the OSS solo install (the common path), the only post-restart verb you need is
> `/coordinator:install`** (then `/coordinator:repo-setup` to onboard a project). The three-verb
> disambiguation below is for agents arriving in a multi-repo chain-walk context — see
> [`docs/agent-install.md`](../../dist/publish-repo-docs/agent-install.md) for the solo playbook.

- **`/coordinator:setup`** — the **install-chain walker** required by the agent-install contract.
  Reads `agent-install-manifest.json`, walks the `direct_deps` list (one hard entry —
  claude-klabauter, as of W0.5), and terminates cleanly once satisfied. This is the verb you
  invoke when performing a first-time or refreshed install-chain verification. It is specified
  by the contract at `docs/wiki/agent-install-contract.md` and is what the `setup_skill` field
  in the manifest points to.

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

The `/coordinator:setup` skill reads `agent-install-manifest.json` at this path:

1. Reads manifest — confirms `repo_id: coordinator-claude`, `direct_deps: [claude-klabauter]`.
2. Probes the claude-klabauter dep (`claude_klabauter_seam_resolvable` — self-confirms if this walker code
   is running at all; see § Fail-loud claude-klabauter resolution above for the earlier chicken-egg gate).
3. Emits banner: "coordinator install-chain walker — chain step 5 of 5: all deps satisfied."
4. Exits 0.

No spinoff seeding in this plan (coord-as-orchestrator spinoff seeding is a follow-on workstream
per plan §13).

Full walker contract: `docs/wiki/agent-install-contract.md`.

## Packageability contract — v3-additive fields (no version bump)

`agent_install_contract_version` stays `3` — the fleet packageability contract
(`docs/wiki/agent-install-contract.md` § Packageability) landed entirely as **optional additive
fields** on the existing v3 schema. No required-array entry changed; a pre-packageability v3
manifest still validates clean. coordinator-claude's own manifest opts in (see
`packageability_compliance` below) and is the reference instance for the six points.

| Point | Manifest field | Where it lives |
|---|---|---|
| 1 — remediation-on-probe-failure | `direct_deps[].functional_probe.remediation` / `system_prerequisites[].install` | `$defs/Remediation`, `$defs/SystemPrereq.install` |
| 2 — single non-interactive entry point | `programmatic_entry_point.entry_point_contract` (PREFERRED) / `standalone_setup_script.entry_point_contract` (FALLBACK) | layered on the existing `posix`/`windows` pair — extends, does not duplicate |
| 3 — installer-floor split | `installer_floor` (top-level, optional) | cross-references `system_prerequisites[].id` (`git`, `claude_code`) rather than restating them |
| 4 — real tested-platform declaration | `tested_platforms` / `present_platforms` (top-level, optional) | `$defs/PlatformId` enum: `macos`/`linux`/`windows` |
| 6 — configurable-location contract | `configurable_locations` (top-level, optional) | `$defs/ConfigurableLocation`; vocabulary from `machine-local-registry.md` § 4 ladder |

(Point 5 has no manifest-field footprint in this pass.)

**Point-2 precedence rule.** When both `programmatic_entry_point.entry_point_contract` and
`standalone_setup_script.entry_point_contract` are present, `programmatic_entry_point` is the
authoritative Point-2 witness; `standalone_setup_script.entry_point_contract` describes only the
chain-walk invocation and is the Point-2 fallback only when `programmatic_entry_point` is absent.
For coordinator-claude the declared Point-2 entry IS `install-maximalist.py`
(`--non-interactive`/`--check-only`) via `programmatic_entry_point`; `setup.py`
(`--i-am-agent`/`--check`) is the chain-walk dispatch target, not the install entry; see
`docs/wiki/agent-install-contract.md` § Two entries, two roles.

**Opt-in compliance marker.** A v3 manifest declares itself checkable via:

```json
"packageability_compliance": { "declared": true }
```

`validate-install-contract.py` keys its point-1/2/3/4/6 completeness checks on
`packageability_compliance.declared === true`. Omitting the field (or `declared: false`) SKIPS
CLEAN — no packageability checks fire, and the manifest still validates under the plain v3
schema. This is what lets old and new manifests coexist without a coordinated version bump.

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
