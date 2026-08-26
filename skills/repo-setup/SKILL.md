---
name: repo-setup
description: "First-time setup for an EXISTING repo, single or fleet-wide (--batch)."
version: 2.0.0
allowed-tools: ["Read","Write","Edit","Bash","Grep","Glob","Agent","Skill","AskUserQuestion","TaskCreate","TaskUpdate","TaskGet","TaskList"]
---

# Repo Setup

## When to Use

- Starting work in a new project repository for the first time
- `/update-docs` reports `tracker_missing` — the project lacks coordination infrastructure
- PM asks to set up project tracking in an existing repo
- **Marketplace first-run** — new coordinator plugin user setting up their first project
- **Creating a NEW repo from scratch** (not onboarding an existing folder)? → use `coordinator:new-project`, which creates + scaffolds a stack + delegates the onboarding half back to this skill.

**`claude-klabauter` is a hard prerequisite** — resolved via `CLAUDE_KLABAUTER_ROOT` / the machine-local
`repos.claude_klabauter` registry entry — for coordinator-claude itself, so it must already
resolve before this skill's own fences will run (private repo until its OSS release; the
maintainer grants access on request, same model as `project-rag`).

**Setup is sufficient — downstream skills add-to, never create-from-scratch.** This skill produces minimum-viable versions of all coordinator artifacts the operator will rely on (`state/orientation_cache.md`, `docs/README.md`, `CLAUDE.md`). Downstream skills (`/update-docs`, `/workstream-start`) add to these artifacts as content accumulates, and self-gate against fresh substrate — underlying principle: wiki (`produce-not-prescribe`). (`/workday-start` runs unconditionally as session orientation; the produce-not-prescribe axis doesn't apply to it.)

## Lanes

Every invocation fires exactly one of three lanes, each a pre-answered round-trip set — see
`lanes/CONTRACT.md` for the shape and `lanes/<lane>.yaml` for the canonical values; `residue/<lane>.md`
carries the rationale for a human reading the flow:

| Lane | Data | Rationale |
|---|---|---|
| `new-project` | `lanes/new-project.yaml` | `residue/new-project.md` |
| `add-existing-project` | `lanes/add-existing-project.yaml` | `residue/add-existing-project.md` |
| `add-repo` | `lanes/add-repo.yaml` | `residue/add-repo.md` |

Which lane fires is an input to this skill, not a decision it makes: the op parameter (or, until
the engine op lands, the caller's own answer to `p1.repo-classification-ask`) names the lane.
`--batch` (§ Batch Mode) is an entry-point mode, not a fourth lane — it drives the
`add-existing-project` lane's answers per repo; see `residue/batch-mode.md`.

## Flag contract

- **Default (no flag) — single-repo, `new-project` or `add-existing-project` lane.** Runs from inside one repo's cwd.
- **`--root <path>` (alias `--target <path>`) — single-repo only, optional.** Onboards a sibling repo by absolute or relative path without cd-ing the session into it — defaults to `$(pwd)` when omitted. Orthogonal to `--batch` — `--batch` reads paths from `working-repos.yaml` and loops the fleet; `--root`/`--target` targets exactly one repo named on the command line. Resolution mechanic: § Procedure below.
- **`--batch` — fleet non-interactive.** See `residue/batch-mode.md`.
- **`--check-only` and `--non-interactive` are batch-mode-only.** If passed to the default single-repo mode (without `--batch`), the skill exits with the one-line remediation: `"--check-only and --non-interactive are only valid with --batch; for non-interactive single-repo setup, set coordinator.local.md first and re-run /repo-setup."`

## Prerequisites

- You are in the project's working directory (not `~/.claude`) — OR pass `--root <path>` (alias `--target <path>`) to onboard a sibling repo from a parent repo's session context without cd-ing the session.
- The firing lane's pre-answered values (`lanes/<lane>.yaml`) or, for `add-repo`, an already-decided classification.

## Procedure

**1. Resolve `$_TARGET_ROOT`** (run before everything else). (shape per `snippets/resolve-coordinator-bin.md`; PowerShell shown) `& "$env:COORDINATOR_SETTINGS_HOME\bin\repo-setup-args-and-register.cmd" resolve-target-root`. It validates the resolved path is an existing directory inside a git repo, printing the absolute path to stdout on success or a fail-loud `ERROR: ...` line on stderr with exit 1 on failure — mirror that idiom, never silently fall back to cwd. When an explicit `--root`/`--target` was passed, change the shell's working directory to `$_TARGET_ROOT` as the first action; every downstream cwd-relative step then transparently targets the sibling repo. When `--root`/`--target` is absent, `$_TARGET_ROOT` resolves to `$(pwd)` and this step is a no-op beyond the resolver call.

**2. Load the firing lane's directives.** Read `lanes/<lane>.yaml` in full: its `round_trip_directives[]` supply every value the mechanical procedure below would otherwise need to prompt for, its `terminal_offer_defaults[]` supply the policy default for every terminal offer, and `second_phase_deferred[]` names the agent-work steps that stay unresolved for a later phase. Load once, apply throughout — this skill does not re-derive or select among any of these values.

**3. Run the lane-independent mechanical procedure.** Read `residue/mechanics.md` and execute it in full — detection, rendering/scaffolding, substrate seeds, optional tripwire installs, and the Phase 4 report shape all run the same way regardless of which lane fired. Substitute the loaded lane's directive/default values wherever the mechanical procedure names a judgment point; take no value from a prompt.

**4. UNATTENDED-HALT SET.** `p3j.1-test-cmd-detect`, `p3m.verify-reachability`, `tw.windows-console-verify-run`, `batch.hook-respect` are never pre-answered by any lane (`lanes/CONTRACT.md`) — return them unresolved to the calling agent/PM exactly as mechanics.md's own procedure surfaces them.

**5. Roster.** Report the firing lane's `roster_slots[]` verbatim in the Phase 4 output. Materializing the roster into batons is a later skill/ceremony's job, out of this skill's scope.

**6. Sentinel — signal that setup just ran.** As the final action, write a session-scoped sentinel so `/workstream-start` (if invoked in this same session) detects that setup just ran and emits the produce-not-prescribe one-liner instead of re-orienting: create the `state/` directory if absent, then touch `state/.repo-setup-just-ran`. The sentinel is single-shot: `/workstream-start`'s Preflight consumes it on first read (`rm -f`). It MUST be gitignored — see `residue/mechanics.md` for the `.gitignore` line. Per-machine transient marker, never committed.

## Optional Tripwire Installs

Install steps are mechanical and lane-independent — see `residue/mechanics.md` § Optional tripwire
installs — mechanical half. Whether an offer fires at all is a value the firing lane's
`terminal_offer_defaults[]` already carries (`tw.windows-console-offer`, `tw.ci-offer`); this skill
does not decide it inline.

## Notes

- This skill creates the **skeleton**; `/update-docs` handles ongoing coordination-artifact maintenance, in the same format.
- Any onboarding bug fix needs all three layers to not recur: prevention (fix the install script), reactive repair (`doctor`-style recovery for users who already hit it), searchable docs (a troubleshooting row keyed on the literal error text). Rationale: wiki.
- Rationale for the extended-substrate seeds and the CLAUDE.md template architecture: wiki.
- Peer-repo citations belong to the workstream record: when a scout dispatch or substrate read
  yields a `file:line` citation for a peer repo, land it in the relevant `state/workstreams/<id>.yaml`
  entry's `specs[]` or `deliverables[].text` (free-text fields per `coordinator/schemas/workstream.schema.json`)
  — never in `state/orientation_cache.md`, whose `## Active workstreams` heading is name-only, capped
  at 10 entries, and schema-forbidden from carrying free-form prose or citations
  (`coordinator/pipelines/workday-start-internals.md:265`, `coordinator/docs/wiki/tiered-context-loading.md:57`).
