---
name: repo-setup
description: "First-time setup for an EXISTING repo, single or fleet-wide (--batch)."
version: 1.0.0
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

## Flag contract

- **Default (no flag) — single-repo interactive.** Runs from inside one repo's cwd. PM-present; asks the 3 cold questions when needed; full Phase 1 → Phase 4 flow as documented below.
- **`--root <path>` (alias `--target <path>`) — single-repo only, optional.** Onboards a sibling repo by absolute or relative path without cd-ing the session into it — defaults to `$(pwd)` when omitted. Orthogonal to `--batch` — `--batch` reads paths from `working-repos.yaml` and loops the fleet; `--root`/`--target` targets exactly one repo named on the command line. Resolution mechanic: § Phases preamble below.
- **`--batch` — fleet non-interactive.** Reads `~/.claude/working-repos.yaml` and loops the single-repo flow per repo. Phase-2 cold-asks substituted by detected defaults (Phase 1 marker scan + Phase 1.5 substrate) OR skipped via lazy-creation discipline when the target artifact already exists. See § Batch Mode below.
- **`--check-only` and `--non-interactive` are batch-mode-only.** If passed to the default single-repo mode (without `--batch`), the skill exits with the one-line remediation: `"--check-only and --non-interactive are only valid with --batch; for non-interactive single-repo setup, set coordinator.local.md first and re-run /repo-setup."` Never silently pick a meaning for an ambiguous flag combination — detect it and fail loud instead.

## Batch Mode (--batch)

Batch mode runs fleet-wide setup non-interactively, driving the single-repo phases per repo read from `~/.claude/working-repos.yaml`. For the full per-repo flow, idempotency contract, hook-respect, and the summary table shape, read `residue/batch-mode.md` before running with `--batch`.

## Prerequisites

- You are in the project's working directory (not `~/.claude`) — OR pass `--root <path>` (alias `--target <path>`) to onboard a sibling repo from a parent repo's session context without cd-ing the session; see § Phases preamble below.
- PM is available for 3 questions (Step 2)

## Phases

**Target-root resolution (run before Phase 1).** Resolve `$_TARGET_ROOT` — the `--root`/`--target` value extracted from `${ARGUMENTS:-}` if given, else cwd — via `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/repo-setup-args-and-register" resolve-target-root`. It validates the resolved path is an existing directory inside a git repo, printing the absolute path to stdout on success or a fail-loud `ERROR: ...` line on stderr with exit 1 on failure — mirror that idiom, never silently fall back to cwd.

When an explicit `--root`/`--target` was passed, change the shell's working directory to
`$_TARGET_ROOT` as the first action, before Phase 1 begins. Every downstream cwd-relative step
then transparently targets the sibling repo — no per-site path-variable threading. Only the shell
cwd for scaffolding moves; the session's conversational and plan context stays put. When
`--root`/`--target` is absent, `$_TARGET_ROOT` resolves to `$(pwd)` and this preamble is a no-op.

### Phase 1: DETECT — Survey Existing State

Before scaffolding, check what already exists. **Never overwrite existing files.**

Check for each of these and record status (exists / missing / incomplete):

```
├── CLAUDE.md                           — project conventions
├── docs/README.md                      — documentation index (wikis, research, specs, reference)
├── docs/wiki/                          — wiki guides (EAGER, seeded — see audit table below)
├── docs/wiki/DIRECTORY_GUIDE.md        — guide index with decision record mapping
├── docs/plans/                         — implementation plans (EAGER, seeded — see audit table below)
├── docs/research/                      — research outputs (EAGER, seeded — see audit table below)
├── state/lessons/                      — engineering patterns, one per-entry YAML file (LAZY — created by coordinator:workstream-complete on first lesson)
├── archive/completed/                  — completion archive (LAZY — created by coordinator:workstream-complete on first completion)
├── state/handoffs/                     — session continuity (EAGER, seeded — see audit table below)
├── CONTEXT.md                          — domain glossary (LAZY — never scaffold; produced when first term is resolved)
├── DIRECTORY.md                        — source index
└── .gitignore                          — check for .claude/settings.local.json entry
```

**If `CLAUDE.md` already exists:** its presence alone does not prove the scaffold is complete — a repo can carry a hand-authored `CLAUDE.md` while the load-bearing scaffold (`docs/coordinator-currency.yaml`, `cross-repo/inbox/`) never ran. Check BOTH for presence.

- **Tracker exists AND both markers present:** the scaffold is genuinely complete. This skill becomes a health check — verify the tracker format matches the standard template, flag deviations, and skip to Phase 4 (REPORT).
- **Tracker exists but either marker is absent:** the repo is only partially onboarded. Do NOT skip to Phase 4 — proceed through Phase 2/Phase 3 scaffolding as normal to fill the gap. This is safe: every Phase 3 helper is idempotent / no-clobber, so re-running scaffolding against a partially-onboarded repo only creates what's missing and never overwrites the existing tracker or `CLAUDE.md`.

**Global detection:** Check if `~/.claude/CLAUDE.md` exists. If yes, the generated CLAUDE.md will include an "extends global" reference. If not, the template is fully self-contained — no dependency on global config.

**Repo classification (PM ask):** Check if `.gitignore` excludes session infrastructure directories (`tasks/`, `archive/`, `state/handoffs/`). Capture this as a hint string — do not make a decision from it:

- 2+ of these are gitignored → hint = `_(detected: 2+ of 3 session dirs gitignored — looks like a distribution repo)_`
- Fewer or none gitignored → hint = `_(detected: standard working-tree layout)_`

Always ask the PM:

> **Is this repo:**
> - **(a) a working repo** — for active development, with session artifacts tracked
> - **(b) a published artifact / template** — distributed for downstream consumers; no session infrastructure
> - **(c) both** — a working repo that publishes itself as the artifact
>
> _(detected: {hint})_

**Branch on the PM's answer:**

- **(a)** → proceed to Phase 1.5 / Phase 2 unchanged. No injection.
- **(b)** → STOP. Do not proceed to Phase 2. Report:
  > _"You answered (b) — distribution repo. Onboarding infrastructure doesn't belong here. Track work on this repo from your parent project's tracker instead."_
- **(c)** → proceed exactly like (a), AND inject a one-line note in the generated CLAUDE.md (Phase 3a) and the generated tracker (Phase 3b):
  > _"This repo is published as its own working artifact — consumers see the full directory shape including `tasks/` and `archive/`."_

Report what exists and what needs to be created before proceeding.

**Project type short-circuit, `cross_platform` inference, the runtime marker scan, the derived-type rules, and `coordinator_whoami` availability** — read `residue/phase1-detection-details.md` before running Phase 1 against a repo you haven't onboarded before. Short version: `coordinator.local.md`'s `project_type` (if present) short-circuits Phase 2 question 2; cross-platform-ness is detected then offered, never auto-written; the runtime marker scan and derived-type rules feed the PM's Phase 2 prompt as advisory detection; and the `coordinator_whoami` package is probed and installed idempotently so the Phase 4 binding probe works.

### Phase 1.5: INVESTIGATE — Read substrate, draft proposals

Skip when Phase 1 found a genuinely empty repo (no README, no CONTRIBUTING, no top-level manifest).

**Substrate-first onboarding.** Read the project's accumulated institutional memory before asking the PM cold: `README.md`, `CLAUDE.md`, `state/lessons/`, `state/improvement-queue/` if present (1.5a); most-recent 5 handoffs for stack/tooling clues if `state/handoffs/` exists (1.5b); sibling `CLAUDE.md` files for stack-shared conventions via the central state repo-registry (resolved via `coordinator-state-root.py --central`'s `<central-state>/repo-registry.md`, claude-klabauter-resident) `stack_tags` (1.5c). Output: a 5–10 line substrate snapshot. Cold-ask is the fallback when substrate is empty.

**Roadmap orientation (run immediately after the substrate snapshot):** Query the completed archive for recent roadmap items — especially valuable when joining cold. Resolve the claude-klabauter root the same way the rest of this skill does (`REPO_CLAUDE_KLABAUTER` / `CLAUDE_KLABAUTER_ROOT` / the machine-local registry pointer; fail loud with remediation if unresolved), then invoke `<claude-klabauter-root>/coordinator/bin/lib/records_query.py completion "nature=roadmap" markdown-list 10 --sort "-loe.tshirt" --since "90d"` via `${COORDINATOR_PYTHON:-python3}`.

Render under `#### Recent roadmap (last 90d, top-10 by size)` in the Phase 4 REPORT — count-always, so `(none)` is expected and rendered explicitly on new repos, never omitted. Otherwise:

1. Read top-level `README.md` / `README.rst` / `README.txt` if present.
2. Read `CONTRIBUTING.md` if present.
3. Read top-level manifests: `package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, `*.uplugin`, `*.uproject`, etc. — whichever exist.
4. Skim recent commit subjects: `git log --oneline -20`.

Draft proposals from what you read:

- **Project name** — from README H1 or repo directory name.
- **Project type + subtypes** — from manifest signals + README role description, reconciled with Phase 1 runtime-marker output. If proposal differs from `detected_type`, surface both with proposal winning and emit:

  > *Detected stack suggests `{detected_type}`. README/manifests suggest `{proposed_type}`. Going with `{proposed_type}` — confirm or override.*
- **Initial workstreams (1-3)** — derived from README "what this does" + recent commit subjects + any "Roadmap" / "TODO" / "Status" sections. If the repo names sibling repos (path on disk, GitHub URL, or "split" / "addon" / "upstream" / "downstream" language), capture each as `peer_repo_candidates`.

Present proposals to the PM for ratification:

> Before I scaffold, here's what I found:
>
> **Project name:** {proposed}
> **Project type:** {proposed}{, subtypes: [...] if any}
> **Workstreams (proposed):**
> 1. {WS1} — {2-3 deliverables}
> 2. {WS2} — {...}
>
> **Sibling repos referenced:** {list with file:line citations from README/CONTRIBUTING}
>
> Ratify, correct, or say "go cold" to skip this and ask from scratch.

On ratification: skip Phase 2's name + workstreams questions; only ask if PM corrected something or said "go cold."

On peer-repo presence: ask once whether to dispatch parallel Explore scouts (recommended). If yes, dispatch each with: *"Read README, CONTRIBUTING, and recent commits. Identify shared schemas, integration contracts, and shipped vs in-flight work relevant to {this repo's name}. Reply with file:line citations."* Wait for results before drafting tracker workstreams.

### Phase 2: ASK — PM Input

**Skip questions Phase 1.5 already ratified. Phase 1.5 may have already pinned project name and/or workstreams; only ask the questions whose answers are still missing.** **If `coordinator.local.md` was found in Phase 1**, skip question 2 — project type already pinned. Ask:

> **1. Project name** — short name (e.g., "example-repo MVP", "example-sim-repo")
> **2. Initial workstreams** (1-3) — name, 2-3 deliverables, optional deps/blockers. Say "stubs" for placeholders.

**If `coordinator.local.md` was NOT found** (cold-ask path), present all three:

> **1. Project name** — short name (e.g., "example-repo MVP", "example-sim-repo")
> _(detected stack: <one-line summary>)_
> **2. Project type:**
>    - `game-dev` — Game development (adds the Game Dev Reviewer reviewer, game-dev domain agents)
>    - `web-dev` — Web frameworks (adds the Front-End Reviewer for front-end review, the UX Reviewer for UX)
>    - `data-science` — Notebooks, pipelines (adds the Data Science Reviewer reviewer)
>    - `general` — Standard conventions only
> **3. Initial workstreams** (1-3) — name, 2-3 deliverables, optional deps/blockers. Say "stubs" for placeholders.

Wait for PM response before proceeding.

### Phase 3: GENERATE — Create Missing Files

Create only what's missing. Use the templates in this skill's `templates/` directory as the base.

#### Lazy-creation discipline

Only scaffold files that have **meaningful day-1 content**. A placeholder header trains agents to ignore the directory; empty scaffolding has zero signal value. Create files and directories only when there is a real artifact to write.

A seed clears that bar — and is EAGER rather than LAZY — only when it satisfies **all four**
conditions: it (a) names what writes into the directory, (b) names what event fills it, (c) names
which skill owns it, and (d) carries NO frontmatter — schema-inert by construction, so it cannot
trip the directory's own schema'd consumer (plan scanner, review-trail parser, handoff hook) on
day one.

**Phase 3 scaffold classification.** EAGER items (`CLAUDE.md`,
`docs/README.md`, `docs/exec-summary.md`, `.gitignore` entry, post-commit hook, `cross-repo/`,
`state/orientation_cache.md`, `state/handoffs/`, `docs/wiki/`, `docs/plans/`, `docs/research/`,
`state/review-trail/`) are scaffolded now from `canonical-structure.yaml`'s `readme:` block.
LAZY items are NOT created here — each is created on first use by its owner: `state/lessons/`
(first session), `archive/completed/` (first ship). Full per-item audit and
reasoning: wiki.

**Phases 3a–3g — CLAUDE.md, docs/README.md, docs/exec-summary.md, and DIRECTORY.md.** Read `residue/phase3-core-docs.md` before scaffolding any of these; it carries the render-template invocations, the workstream-block formatting, and the exec-summary generator contract.

**Phases 3e–3f.6 — directories, .gitignore, and the git-hook installs.** Read `residue/phase3-infra-hooks.md` before running the `canonical-structure.yaml` scaffold or touching `.gitignore`, the post-commit hook, the session-id trailer hook, git config hardening, the meta-repo pre-commit gate, or the VS Code read-only guard.

**Phases 3h–3m and 3x — the currency stamp, orientation cache, extended substrate seeds, install manifest, strategic self-description skeleton, guard-regression tripwire tests, and fleet memo-destination registration.** Read `residue/phase3-substrate-seeds.md` before running any of these — they are ALWAYS-run, idempotent seeds, not optional offers, so skipping the reference is not the same as skipping the step. This is also where the extended substrate seeds land: `fast_test_cmd`/`full_test_cmd`, `state/health-ledger.md`, the RAG-index decision, and the fnm Node-version pin.

---

### Phase 4: REPORT

Read `residue/phase4-report-template.md` before writing this report — it carries the declared word-budget exemption (this is a once-per-repo walkthrough, not a recurring status report; do not shorten it), the `coordinator_whoami` status-row routing, the report-by-exception rule for `### Already Existed`, the full report template (`### Created` / `### Already Existed` / `### Needs Attention` / `### Recent Roadmap` / `### What's next`), and the coordinator-binding verification procedure.

### Sentinel — signal that setup just ran

As the final action of `/coordinator:repo-setup`, write a session-scoped sentinel so `/workstream-start` (if invoked in this same session) detects that setup just ran and emits the produce-not-prescribe one-liner instead of re-orienting: create the `state/` directory if absent, then touch `state/.repo-setup-just-ran`.

The sentinel is single-shot: `/workstream-start`'s Preflight consumes it on first read (`rm -f`). It MUST be gitignored — see Phase 3f for the `.gitignore` line. Per-machine transient marker, never committed.

## Optional Tripwire Installs

After Phase 3 scaffolding completes, offer to install coordinator-standard tripwire tests into the consuming repo's test suite — the Windows console-subprocess tripwire (offered), the widened `.py`/`.ps1` spawn tripwire (always installed, non-optional), and the cross-platform CI reference (offered when `cross_platform` is declared or inferred-and-confirmed). Read `residue/tripwire-installs.md` for the install steps, suppression-marker conventions, exemption mechanisms, and the language-aware install branch for the CI reference before running any of these — it carries no inline steps here, to avoid duplicating that file.

## Notes

- This skill creates the **skeleton**; `/update-docs` handles ongoing tracker maintenance, in the same format.
- Any onboarding bug fix needs all three layers to not recur: prevention (fix the install script), reactive repair (`doctor`-style recovery for users who already hit it), searchable docs (a troubleshooting row keyed on the literal error text). Rationale: wiki.
- Rationale for the Phase 3j extended-substrate seeds and the CLAUDE.md template architecture: wiki.
