---
name: repo-setup
description: First-time setup for an existing repo, single or --batch.
version: 2.0.0
allowed-tools: ["Read","Write","Edit","Bash","Grep","Glob","Agent","Skill","AskUserQuestion","TaskCreate","TaskUpdate","TaskGet","TaskList"]
---

# Repo Setup

## When to Use

- Starting work in a new project repository for the first time
- `/update-docs` reports `tracker_missing` — the project lacks coordination infrastructure
- **Creating a NEW repo from scratch**? → `coordinator:new-project` (scaffolds a stack, delegates onboarding back here).

**The engine repo is a hard prerequisite** — resolved via `CLAUDE_KLABAUTER_ROOT` / the machine-local
`repos.claude_klabauter` registry entry — and must already resolve before this skill's own fences
will run.

**Setup is sufficient — downstream skills add-to, never create-from-scratch.** This skill produces minimum-viable versions of the coordinator artifacts (`state/orientation_cache.md`, `docs/README.md`, `CLAUDE.md`) — the **skeleton**. Downstream skills (`/update-docs`, `/workstream-start`) add to them in the same format and self-gate against fresh substrate (wiki: `produce-not-prescribe`).

## Lanes

Every invocation fires exactly one of three lanes — `new-project`, `add-existing-project`,
`add-repo` — each a pre-answered round-trip set: `lanes/CONTRACT.md` for the shape,
`lanes/<lane>.yaml` for the canonical values, `residue/<lane>.md` for the rationale a human
reading the flow wants.

The lane is an input, not a decision: the op parameter (or the caller's own answer to
`p1.repo-classification-ask`) names it. `--batch` is an entry-point mode, not a fourth lane — it
drives the `add-existing-project` lane's answers per repo (`residue/batch-mode.md`).

## Flag contract

- **Default (no flag) — single-repo, `new-project` or `add-existing-project` lane.** Runs from inside one repo's cwd.
- **`--root <path>` (alias `--target <path>`) — single-repo only, optional.** Onboards a sibling repo by path without cd-ing into it; defaults to `$(pwd)`. Orthogonal to `--batch` (which loops the fleet); names exactly one repo. Resolution: § Procedure.
- **`--batch` — fleet non-interactive.** See `residue/batch-mode.md`.
- **`--non-interactive` (single repo, valid without `--batch`).** Asks nothing: every judgment point takes the firing lane's `lanes/<lane>.yaml` value, and the unattended-halt set (§ Procedure step 4) returns unresolved to the caller. The name comes from `coordinator.local.md` or the directory name, the type from detection.
- **`--answers <file.json | inline-json>` (single repo).** A JSON object keyed by lane `step_id` (`p2.ask-project-name`, `p2.ask-project-type`, `p2.ask-workstreams`, ...) overriding that step's lane value; every unlisted step takes its lane value. Implies `--non-interactive`; an unknown key fails loud, naming it.
- **`--check-only` is batch-mode-only.** Passed to the default single-repo mode (without `--batch`), the skill exits with the one-line remediation: `"--check-only is only valid with --batch; for a single repo use --non-interactive or --answers."`

## Optional `coordinator.local.md` key: `ceremony_day_anchor`

`ceremony_day_anchor: local|utc` is a flat frontmatter key in `coordinator.local.md`: absent or `local` anchors the ceremony day on local date, `utc` on the UTC date. Repo-setup does not seed it; add it by hand only for a repo that wants `utc`.

## Prerequisites

- You are in the project's working directory (not `~/.claude`), or pass `--root`/`--target` (§ Flag contract).
- The firing lane's pre-answered values (`lanes/<lane>.yaml`) or, for `add-repo`, an already-decided classification.

## Procedure

**1. Resolve `$_TARGET_ROOT`** (run before everything else). (shape per `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`; PowerShell shown) `& "$env:COORDINATOR_SETTINGS_HOME\bin\repo-setup-args-and-register.exe" resolve-target-root`. It validates the resolved path is an existing directory inside a git repo, printing the absolute path to stdout on success or a fail-loud `ERROR: ...` line on stderr with exit 1 on failure — mirror that idiom, never silently fall back to cwd. When an explicit `--root`/`--target` was passed, change the shell's working directory to `$_TARGET_ROOT` as the first action, so every downstream cwd-relative step targets the sibling repo. Absent, `$_TARGET_ROOT` resolves to `$(pwd)`.

**2. Load the firing lane's directives.** Read `lanes/<lane>.yaml` in full: `round_trip_directives[]` supplies every value the procedure would otherwise prompt for, `terminal_offer_defaults[]` the default for every terminal offer, `second_phase_deferred[]` the steps left unresolved for a later phase. Load once, apply throughout.

**3. Run the lane-independent mechanical procedure.** Read `residue/mechanics.md` and execute it in full (detection, rendering/scaffolding, substrate seeds, optional tripwire installs, Phase 4 report). Substitute the loaded lane's directive/default values at every judgment point; take no value from a prompt.

**4. UNATTENDED-HALT SET.** `p3j.1-test-cmd-detect`, `p3m.verify-reachability`, `tw.windows-console-verify-run`, `batch.hook-respect` are never pre-answered by any lane (`lanes/CONTRACT.md`) — return them unresolved to the calling agent/PM exactly as mechanics.md's own procedure surfaces them.

**5. Roster.** Report the firing lane's `roster_slots[]` verbatim in the Phase 4 output. Materializing the roster into batons is a later skill/ceremony's job.

**5a. Posture overlay.** Read `engagement_posture` from `${CLAUDE_HOME:-$HOME}/.claude/coordinator-identity.yaml`; when set, run `render-posture-overlay <posture> "$_TARGET_ROOT/.claude/em-context.md"` (the same call as `commands/install.md`'s engagement-posture step, including its `.gitignore` check). Absent, skip silently. The op swaps in place, so re-running on a repo that already carries an overlay is safe.

**6. Sentinel — signal that setup just ran.** As the final action, write a session-scoped sentinel so `/workstream-start` (if invoked in this same session) prints its one-line setup notice and then runs orientation once: create `state/` if absent, then touch `state/.repo-setup-just-ran`. It is single-shot (Preflight consumes it) and MUST be gitignored (`residue/mechanics.md`).

## Optional Tripwire Installs

Install steps are mechanical and lane-independent — see `residue/mechanics.md` § Optional tripwire
installs — mechanical half. Whether an offer fires is a value the firing lane's
`terminal_offer_defaults[]` already carries (`tw.windows-console-offer`); this skill
does not decide it inline. A Perforce workspace registers per `contract/p4-provider-fragment.md` § Registration.

## Notes

- **Embedding-class check.** Where this flow touches project-rag indexing setup, ask: "does this
  corpus need `text`-class embedding?" — project-rag otherwise defaults prose corpora to a code-embedding model.
- Any onboarding bug fix needs all three layers to not recur: prevention (fix the install script), reactive repair (`doctor`-style recovery for users who already hit it), searchable docs (a troubleshooting row keyed on the literal error text).
- Peer-repo `file:line` citations land in the `state/workstreams/<id>.yaml` entry's `specs[]` or
  `deliverables[].text`, never in `state/orientation_cache.md` (name-only, capped at 10 entries;
  `coordinator/docs/wiki/skills-corpus/tiered-context-loading.md:57`).
