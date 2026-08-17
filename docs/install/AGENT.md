---
manifest: agent-install-manifest.json
contract: ../wiki/agent-install-contract.md
---

# Agent install guide — coordinator-claude

> **Chain position:** coordinator-claude is the **root of the OSS plugin-adoption chain** —
> nothing installs "above" it, and it is always installed first among the peer plugins. Any
> downstream repo that adopts the contract may declare coordinator-claude as a dependency.
> As of **W0.5 Option B+C** (PM-ratified 2026-07-19, identity corrected 2026-08-17),
> coordinator-claude itself declares ONE hard direct dep of its own: **claude-klabauter** (the
> engine) — a mandatory prerequisite of coordinator in every environment, including OSS-mirror
> installs. "DAG root" below means root of the plugin chain, not zero dependencies. The
> chain-walker resolves the engine root that backs claude-klabauter at runtime via
> `CLAUDE_KLABAUTER_ROOT`'s four-rung ladder — see § Fail-loud claude-klabauter resolution below for that
> mechanism; it is an internal resolution detail, not a second dependency.

> **You are an agent reading this file** either because you were asked to install this repo, or
> because the setup skill dispatched you to walk the install chain for coordinator-claude — both
> arrivals land here. Follow the install contract at `docs/wiki/agent-install-contract.md`. Do
> not improvise. If a step fails, stop and report.

---

## Chain posture

coordinator-claude is the root of the plugin-adoption chain (chain step 5 of 5). As of W0.5
Option B+C (identity corrected 2026-08-17), it declares **one hard direct dep**:
`claude-klabauter` (`severity: hard`, `functional_probe_kind: claude_klabauter_seam_resolvable`). The
chain-walker visits coordinator-claude, probes that one dep, and terminates once it is
satisfied:

"coordinator install-chain walker — chain step 5 of 5: all deps satisfied."

No upstream probe is needed in the plugin-chain sense — as the root of THAT chain, there is
nothing above coordinator-claude to walk — but the claude-klabauter probe still runs (it is
the walker's own mandatory engine dependency, not a plugin-chain edge). The probe kind's name
(`claude_klabauter_seam_resolvable`) is an internal-mechanism label, not a second dependency identity —
it resolves the engine root that backs claude-klabauter via CLAUDE_KLABAUTER_ROOT's four-rung ladder, not
sibling-colocation. If it is unresolvable, the walker fails loud — see § Fail-loud claude-klabauter
resolution below. Any downstream consumer that depends on coordinator-claude recurses into this
same terminal state; coordinator is visited exactly once even when reached via multiple paths,
via the disk-resident visited-set per contract § Visited-set protocol.

### Fail-loud claude-klabauter resolution

Because claude-klabauter's `coordinator/scripts/setup.py` (the chain-walker itself) is a trampoline into
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
> [`INSTALL.md`](../../../INSTALL.md) for the solo playbook.

- **`/coordinator:setup`** — the **install-chain walker** required by the agent-install contract.
  Reads `agent-install-manifest.json`, walks the `direct_deps` list (one hard entry —
  claude-klabauter, as of W0.5, identity corrected 2026-08-17), and terminates cleanly once
  satisfied. This is the verb you
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

**Naming collision, not synonymous.** A settings-home `bin/coordinator-install` entry is landing
on claude-klabauter's side (a forwarder generated from their own `bin/` listing, with no file
authored in this repo). That entry means the **chain root** — walking the whole install chain,
the scope of `/coordinator:setup` above — not the narrow OSS-plugin-install leg this section's
`/coordinator:install` names. Same name, two scopes, across the two surfaces an installing agent
reads in sequence. The bin entry is not renamed to remove the collision — the grepped name has
to win — so read this paragraph rather than assuming the slash-command and the bin entry are the
same verb.

## Settings-home provisioning

`~/.coordinator-claude-settings` (`$COORDINATOR_SETTINGS_HOME`) must be populated on install —
`bin/` (the agent-helper forwarders plus the `SETTINGS_HOME_BIN` PATH block), `machine-local/`
(the registry substrate), and `.coordinator-venv/` (the coordinator venv). This is a required
post-condition of installing this repo, in **both** delivery shapes — the DoE-maximalist path
(`coordinator/scripts/install-maximalist.py`) and the plugin-layered OSS path
(`/coordinator:install` Phase 3, `coordinator/lib/install-substrate.py` in the engine root).

**The post-condition is outcome-conditional, not "running it installs."** claude-klabauter's ruling
(their installer must provision the interpreters declared consumers resolve to — including the
bare `python3` this repo's `hooks.json` registers hooks under — and must FAIL with named
remediation rather than override a PEP-668 guard) makes a designed refusal a CONFORMING outcome on
a guarded box, not a defect. The install command is expected to refuse there, by design. Read this
section's requirement as: **either** `~/.coordinator-claude-settings` is provisioned as above,
**or** the installer exits with the reserved designed-refusal code below, naming the supported
interpreter — never as an unconditional "the directory gets populated."

**Designed-refusal exit code: `96`** (`entry_point_contract.refusal_exit_code` in claude-klabauter's
own manifest; source constant `scripts/setup.py::EXIT_INTERPRETER_UNSUPPORTED`). 96 never means a
genuine provisioning failure — it is reserved so this post-condition names a discriminator a test
can read rather than parsing stderr prose. Confirmed live on claude-klabauter's side
(`cross-repo/inbox/2026-08-17-claude-klabauter-em-exit-96-reserved-and-your-programmatic-entry-point-is-dangling.md`);
as of that memo the reservation and the manifest field are landed but the raise site itself is not
yet — it is owned by their machine-first-install-surface plan's C2, authorized and executing. If a
reader hits this section before that emitter lands, the refusal path is contracted but not yet
observable end-to-end; the code value itself will not move.

**Both delivery shapes provision identically for these three components — verified by code path,
not by running a fresh install on this (shared, multi-session) machine.** `/coordinator:install`
Phase 3 invokes `coordinator/lib/install-substrate.py` with no flags, which imports and calls
`coordinator_core.install.substrate.main()` → `run(setup_only=False, check_only=...)`.
`coordinator_core/install/maximalist.py` calls the same `substrate.run(setup_only=False, ...)`
(directly, or via the `coordinator/scripts/install-maximalist.py` trampoline that imports it).
Both therefore run
the unconditional `bin/` + PATH-guard-block step (`substrate.py`'s step 3e-bin, which calls
`write_path_entry_guard_blocks` unconditionally whenever `check_only` is false) and the
`machine-local/`/venv steps identically — `setup_only=True` is the only branch that would skip
them, and neither install path passes it. There is no reduced OSS-shape for bin/, machine-local/,
or the venv; the plugin-layered and maximalist paths are the same provisioning code, invoked two
ways.

**Discharge split, by ownership.** DoE declares this post-condition (this section, and
`docs/wiki/agent-install-contract.md`); **claude-klabauter owns the proof** — a test in their own
tree pinning that the plugin-layered invocation shape (no `--setup-only`) provisions the
directory, since a DoE-side paragraph citing their `file:line`s rots on their next refactor
(`install_health_run.py` lives at `coordinator_core/ops/install_health_run.py`, not
`coordinator_core/install/` — a citation drift caught during this chunk's own investigation).
Claude-klabauter has accepted owning that test half
(`cross-repo/inbox/2026-08-17-claude-klabauter-em-coordinator-install-entry-custody-and-what-it-should-invoke.md`
§ Unchanged: "4b is ours and unaffected — you declare the settings-home post-condition, we own the
test"). No gap was found in this investigation that would need a new memo — the mechanism-parity
finding above and the exit-96 answer close out what this section exists to declare; only the
raise-site landing (their C2) is still pending, tracked in the memo thread, not by this plan.

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
For coordinator-claude the declared Point-2 entry IS `coordinator_core/install/maximalist.py`
(`--non-interactive`/`--check-only`) via `programmatic_entry_point`; `setup.py`
(`--i-am-agent`/`--check`) is the chain-walk dispatch target, not the install entry; see
`docs/wiki/agent-install-contract.md` § Two entries, two roles. Both entries now live in
Claude-klabauter, not in this repo (migration `b644d5a9b`) — `programmatic_entry_point.posix`
resolves to `coordinator_core/install/maximalist.py` and `standalone_setup_script.posix` to
`scripts/setup.py`, both repo-root-relative to whichever engine root resolves. A same-purpose
legacy trampoline, `coordinator/scripts/install-maximalist.py`, also exists in claude-klabauter but
not in claude-klabauter — a distinct file that imports the canonical target above, not an alias
for it.

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
[`INSTALL.md`](../../../INSTALL.md) for the full guided install playbook.

---

<!-- spec-backlink: ~/.claude/archive/specs/2026-06/2026-06-15-coordinator-install-chain-application-phase-b.md §7 C1 -->
<!-- spec-backlink: plugins/coordinator/docs/wiki/agent-install-contract.md -->
