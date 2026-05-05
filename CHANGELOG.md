# Changelog

All notable changes to coordinator-claude are documented here.

## [Unreleased]

### Changed
- **`codex-review-gate` is now an opt-in add-on.** The skill ships inside the coordinator plugin but is stripped from the install unless the user passes `--enable-codex` (or answers `y` at the new interactive prompt). Default installs no longer reference Codex from `/workweek-complete`, `/workday-complete`, or `/bug-sweep` summaries. `/bug-sweep --codex-verify` and the workweek Codex step both gate on skill presence — when absent, they skip silently and omit the line from their reports rather than printing _"skipped"_. Rationale: Codex was hassle for our setup and the integration was creating noise in routine reports; consumers who run Codex still have the on-ramp via the install flag.

## [1.10.0] — 2026-05-04 (proposed — PM to confirm before tagging)

Two themes in this release: a workday/workweek cadence split for the coordinator workflow surface, and a layered defense against "shape-correct, premise-wrong" plans across the reviewer pipeline.

### Theme A — Workday/workweek cadence split

`/workday-complete` had grown to 306 lines doing double duty: lightweight daily housekeeping AND release-grade ceremony. Multi-day workstreams don't fit a daily wrap, so the heavy half either got skipped or fired at the wrong cadence. This release splits the cadence into daily and weekly bookends, with a structured `tasks/week-changelog/` ledger acting as a thin index over handoffs (which remain the unit of session continuity).

### Added
- **`/workweek-start`** (new) — PM-invoked strategic orient at the start of a week. Reads the prior week's changelog, surfaces stalled workstreams, runs an orphan sweep, prompts the PM for 1–3 priorities, and resets-or-updates `tasks/week-changelog/HEADER.md` based on whether a `/workweek-complete` has occurred since the last `/workweek-start`.
- **`/workweek-complete`** (new) — PM-invoked release-grade close. Reads the week-changelog as canonical record, runs full validation + `/update-docs` + ShellCheck + Codex review + improvement-queue triage + scc snapshot, drafts release notes from changelog + `archive/completed/`, surfaces a version bump, invokes `/merge-to-main`, archives the daily files, and resets the HEADER.
- **`tasks/week-changelog/`** convention — per-machine daily files (`YYYY-MM-DD-{hostname}.md`) + shared `HEADER.md`. Per-machine layout eliminates concurrent-write conflicts when multiple machines wrap the same calendar day.
- **`bin/check-weekly-staleness.sh`** — emits `STALE` / `MILD` / `FRESH` / `UNKNOWN` based on days-since-last-weekly + commits-since-last-weekly thresholds (≥5 days AND ≥15 commits = STALE). Consumed by daily nudge and both weekly commands.
- **`/pickup` "while you were away" surface** — when the named handoff is from a prior day (not a same-day baton pass), surfaces one-line summaries of changelog blocks since the handoff date, capped at ~10 lines. Strengthens the handoff/pickup backbone for multi-workstream weeks.
- **`docs/wiki/workday-workweek-cadence.md`** — tutorial guide for the new cadence.

### Changed
- **`/workday-complete`** rewritten (307 → 210 lines). Drops `/update-docs`, scc, ShellCheck, Codex review gate, and improvement-queue triage action — all moved to `/workweek-complete`. Adds: read-only improvement-queue depth nudge (≥5 entries surfaces a one-liner, no triage), changelog append (synthesises today's block from handoffs + `/daily-review` summary, does NOT re-author), staleness check (surfaces "weekly is stale" when thresholds cross). `Validation:` field on the daily block is auto-filled from gate exit codes, never LLM-authored.
- **`plugins/coordinator/CLAUDE.md`** — new "Workday/Workweek Cadence" doctrine section ("handoffs are the atom, the changelog is the index"); existing improvement-queue triage rule updated to reflect daily-nudge / weekly-action split.

### Migration
- Existing projects do not need to do anything. `tasks/week-changelog/HEADER.md` is shipped as a seed template; first `/workweek-start` populates it. Until then, `bin/check-weekly-staleness.sh` returns `UNKNOWN` (no nudge fires).
- Existing `/workday-complete` workflows continue to work — the command does less, but everything it still does was already there.
- `/pickup` enhancement is additive; same-day handoffs (the common case) are unaffected.

### Design source
`docs/plans/2026-05-04-workweek-cadence-split.md` (Patrik APPROVED_WITH_NOTES — all findings folded in).

### Theme B — Reviewer premise challenge (layered W1–W5 defense)

Closes the "shape-correct, premise-wrong" gap surfaced by the 2026-05-04 holodeck `.uplugin Modules` incident: a plan was empirically refuted post-review because it reintroduced something `tasks/lessons.md` and the wiki had explicitly forbidden 5 days earlier; no checkpoint surfaced the prior prohibition. The layered defense adds challenge points across the pipeline so the same failure mode is caught at multiple stages rather than relying on any single agent.

#### Added
- **W1 — `writing-plans` skill** gains a negative-search step and a reversal-verb hint that suggests a staff-session at PM discretion when a plan reverses a recently-shipped decision.
- **W2 — `repo-specialist` agent** gains a counter-evidence pass with a hard always-read rule for `tasks/lessons.md`.
- **W3 — `staff-eng` (Patrik)** gains "Pass 0 — Premise & Alternatives" with three new structured fields, a `REJECTED` verdict (refuted alone — no architectural-superiority clause), and five hard guardrails. Self-reviewed `REJECTED`-trigger inconsistency caught and integrated.
- **W4 — `staff-game-dev` (Sid)** gets a mirror of W3 so game-dev plans receive the same premise scrutiny.
- **W5 — `review-integrator`** treats `REJECTED` as advisory; EM override requires a verbatim PM quote.

#### Changed
- Calibration block byte-identical across all reviewers (`verify-calibration-sync` clean).

#### Design source
`docs/plans/2026-05-04-reviewer-premise-challenge.md` (Patrik APPROVED_WITH_NOTES — all 7 findings integrated).

#### Note
The `dfdcf8f` commit also carried an early-write probe addition to `plugins/deep-research/agents/repo-specialist.md` — orthogonal to the W1–W5 work but mixed into the same source-side commit and percolated together via `publish.sh`.

---

## [1.9.0] — 2026-05-03

### Removed — `remember` plugin

The `remember` plugin (automatic session memory via Haiku-summarized transcripts) is removed. Its Haiku-summarization PostToolUse and SessionStart hooks fired constantly across every session, burning tokens for no measurable workflow benefit beyond what the existing process guardrails already provide:

- Handoffs (`/handoff`, `/pickup`) carry forward what matters between sessions.
- The orientation cache, lessons file, project tracker, and `tasks/` artifacts cover continuity at the project level.
- Built-in conversation compaction handles in-session context.

Net effect: `remember` was redundant infrastructure for a problem already solved by discipline. Keeping it costs Haiku spend on every tool call with no signal anyone was reading the resulting `memory/sessions/*.md` files.

### Migration

- The plugin entry in `marketplace.json` is gone. Existing installs should run plugin-uninstall (or just delete the plugin dir).
- Accumulated `~/.claude/projects/<slug>/memory/sessions/` data dirs can be deleted; nothing reads from them.
- Five coordinator commands had their `remember`-aware paragraphs removed: `setup`, `session-start`, `session-end`, `update-docs`, `workday-complete`. Each now skips straight to its next step.

### Added (publish tooling)

- `setup/publish.sh` now prunes orphan plugin directories from the target (matching the existing per-file `--delete` semantics). Hidden dirs like `.git` are preserved. Respects `--dry-run`.

## [1.8.0] — 2026-05-03

### Theme — docs-checker as suggested pre-flight + inline-edit authority

Promotes the `docs-checker` Sonnet agent from optional reporting-only to a suggested pre-flight before Opus reviewer dispatch, with authority to apply AUTO-FIX-class corrections inline. Reviewer awareness propagated to all five Opus reviewers via a new sentinel-snippet sync surface, parallel to the existing calibration and project-rag-preamble patterns.

### Added
- **`docs/wiki/docs-checker-pre-review.md`** — full doctrine page: EM Decision Rules table (always-run for C++/UE; EM judgment elsewhere; freshness-marked against the current model), AUTO-FIX allowlist + hard prohibitions, scope constraint (artifact-only, never referenced files), project-RAG staleness rule, sidecar YAML schema, edit-budget cap, integrator-bypass rollback story.
- **`plugins/coordinator/snippets/docs-checker-consumption.md`** — canonical consumer-side block (synced into all five Opus reviewer prompts).
- **`plugins/coordinator/bin/verify-docs-checker-sync.sh`** — sync verifier with `--fix` and `--list` modes; clone of `verify-calibration-sync.sh`.
- **`plugins/coordinator/CLAUDE.md`** new section "Pre-Review Mechanical Verification" (terse rule + pointer to wiki) + tripwire under "Adding a Convention to the Coordinator System".

### Changed
- **`plugins/coordinator/agents/docs-checker.md`** — gains `Edit` tool + seven `mcp__project-rag__*` tools, project-RAG bootstrap subsection, expanded scope (in-repo symbols verifiable when project-RAG present), 5-tier verification source hierarchy with explicit staleness handling, new "Inline Auto-Fix Authority" section (allowlist, scope constraint, edit-budget cap, sidecar YAML schema, hard prohibitions, oscillation stuck-detection), removal of "Apply fixes" from "What You Do NOT Do", verification-table `Action` column.
- **`plugins/coordinator/agents/staff-eng.md`**, **`plugins/game-dev/agents/staff-game-dev.md`**, **`plugins/data-science/agents/staff-data-sci.md`**, **`plugins/web-dev/agents/senior-front-end.md`** — sentinel-block docs-checker-consumption inserted (replaces inline block in staff-eng; new in the others).
- **`plugins/coordinator/commands/review-dispatch.md`** — Phase 2.7 promoted from optional to suggested pre-flight; embeds the EM Decision Rules table; integrator-bypass note + mandatory EM spot-check after Opus review.
- **`plugins/coordinator/skills/requesting-code-review/SKILL.md`**, **`plugins/coordinator/skills/requesting-staff-session/SKILL.md`** — pointer to docs-checker pre-flight in review-setup steps.

### Internal
- Source commit `3a00f18` on `dbc-oduffy/.claude` `main`. Patrik R1 (REQUIRES_CHANGES, 11 findings) → integrator (all 11 AUTO-FIX-applied) → Patrik R2 (APPROVED, 0 findings). Plan + reviews preserved at `tasks/reviews/2026-05-03-docs-checker-pre-flight-*.md` in the source repo.

## [1.7.1] — 2026-05-03

### Theme — Doc refresh

Patch release. README plugin enumeration was stale (still listing 4 plugins and pointing at the retired `deep-research-claude` companion repo); social preview stats were stale; one cross-platform fix and one universal-tier doctrine sync had landed without a release marker.

### Changed
- **README plugin enumeration** updated to reflect the 7 plugins shipped via `marketplace.json` — `deep-research` and `notebooklm` are bundled (not external companions), and `remember` is now surfaced. Directory tree refreshed with current counts (23 commands, 34 skills, 11 coordinator agents).
- **Social preview** (`assets/social-preview.{html,png}`) regenerated — 7 plugins, 36 skills, 26 agents, 4 research pipelines.
- **`plugins/coordinator/.claude-plugin/plugin.json`** bumped 1.6.0 → 1.7.1 (1.7.0 release shipped without a manifest bump).

### Fixed
- **`hooks/scripts/track-tier-usage.sh`** — normalize MSYS/Git-Bash cwd before slug derivation so the W3 telemetry counter writes to the correct per-repo log on Windows (mirror of `dbc-oduffy/.claude` PR #62).

### Internal
- Promoted 5 universal-tier lessons from `/workday-start` triage queue (mirror of `dbc-oduffy/.claude` PR #63).

## [1.7.0] — 2026-05-01

### Theme — Portable Ideas from Obsidian (W1+W2+W3)

Three workstreams percolated from `~/.claude` HEAD as a single bundle (R2 APPROVED_WITH_NOTES, all 7 findings integrated). Schemas + lint belt, live-query primitives, and tiered context-loading doctrine — each tackling a different decay mode in the coordinator pipeline.

### Added
- **W1 — Frontmatter schemas + lint belt + PreToolUse validator.** New `schemas/{handoff,plan,review,decision,worker-run,lesson-entry}.yaml`, shared `bin/lib/schema.{js,test.js}` validator (with code-span / link-text robustness), `bin/lint-frontmatter.{sh,js}` CLI, and `hooks/scripts/validate-frontmatter-schema.{js,test.js}` PreToolUse hook (default WARN mode; `COORDINATOR_SCHEMA_STRICT=1` to deny).
- **W2 — Live queries CLI + sentinel-block primitives.** `bin/query-records.{js,sh}` queries frontmatter-indexed records; `bin/refresh-queries.{js,sh}` regenerates `<!-- BEGIN query: ... -->` callouts in markdown (consumed by `/update-docs` Phase 11c); `bin/lib/sentinel-blocks.{js,test.js,cli.js}` factor out shared sentinel-block extraction (now delegated by `verify-preamble-sync.sh` and `verify-calibration-sync.sh`).
- **W3 — Tiered context loading doctrine + telemetry.** New `docs/wiki/tiered-context-loading.md` canonical guide; `coordinator/CLAUDE.md` "Codebase Investigation" section rewritten to enumerate tiers 0–4 plus the tier-4 rationale rule; `hooks/scripts/track-tier-usage.sh` PostToolUse telemetry counter classifies each tool call by tier and detects the rationale preamble; `/session-end` Step 0 emits a tier-usage report.

### Changed
- **Doctrine + preamble syncs** across `CLAUDE.md`, `agents/staff-eng`, and commands `{distill, handoff, mise-en-place, session-start, session-end, update-docs}` to thread the new tiered-context model and rationale rule through the agent surfaces that consume them.

### Internal
- Test coverage for `schema.js` (code-span / link-text edge cases), `query-records`, and `sentinel-blocks` modules.

## [1.6.0] — 2026-05-01

### Theme — Orphan-Branch Prevention

In response to a 2026-05-01 postmortem (15 commits stranded for 22 hours on a branch whose source-PR had already merged, with downstream sessions actively rewriting docs to claim "shipped"), the coordinator pipeline gains structural defenses against orphan branches and false "shipped" claims. Three shared helpers, six surfaces hardened, one paragraph of doctrine.

### Added
- **`bin/orphan-branch-sweep.sh`** — enumerates `work/*` and `feature/*` branches owned by the user, classifies CRITICAL (commits added after a PR merged from this branch) / WARNING (no PR, ahead, ≥2 days old or >36h) / OK. JSON or text output, `--severity-min` filtering eliminates `| jq` / `| grep` parsing at every call site.
- **`bin/sync-main.sh`** — fetch + ff-only invariant called before any branch creation. Uses `git fetch origin main:main` refspec form so local `main == origin/main` regardless of which branch the working tree is on. Every `git checkout -b` site in the coordinator pipeline now runs this first.
- **`bin/check-shipped-on-main.sh`** — thin wrapper around `git merge-base --is-ancestor` so "shipped" claims have a single authoritative answer.
- **`commands/workday-start.md` Step 0.5** — new orphan sweep surfaces CRITICAL/WARNING branches in the Morning Briefing before any new work begins.
- **`commands/workday-start.md` Step 0 Branch Reconciliation Decision** — when yesterday's branch can't be merged forward, the PM is forced to choose A (consolidate now) / B (defer with re-check date in `tasks/.deferred-branches.md`) / C (archive). TTY-aware: blocks interactively, auto-defers in non-interactive (overnight) sessions.
- **Tracking file `tasks/.deferred-branches.md`** — single-line entries managed by the Branch Reconciliation Decision flow; surfaced when re-check date arrives.

### Changed
- **`commands/handoff.md` Step 3** — pre-flight reachability check on completed-work commits. When commits aren't on `origin/main`, "shipped" wording is replaced with "complete on branch, not yet merged" and a `## Not Yet On Main` section is appended.
- **`commands/update-docs.md`, `commands/distill.md`, `commands/architecture-audit.md`** — explicit DO-NOT-MERGE prohibition inline in Sonnet dispatch prompts. Closes the 2026-05-01 rogue-merge trigger (a doc-maintenance Sonnet ran `gh pr merge` autonomously).
- **`skills/merging-to-main/SKILL.md`** — Step 4 5-min quiet gate (cross-platform `gh`+Python snippet, override via `--force-merge-active-branch`); Step 6 reports other unmerged branches owned by the user.
- **`skills/using-git-worktrees/SKILL.md`, `commands/workday-complete.md`, `commands/session-start.md`** — `sync-main.sh` injected at every branch-creation site.
- **`coordinator/CLAUDE.md`** — one paragraph added to "Verification Before Done" ("Shipped means on `origin/main`, not on a branch tip"), one bullet under "Git Commit Policy" pointing at `sync-main.sh` + the workday-start contract, and a tripwire entry naming the three skills that must carry the gh-merge prohibition. Aggressive compression — ~5 lines total addition, lean per-PM-direction.

### Internal
- **Test fixture** `tests/plugins/orphan-sweep.test.js` covering the three severity classes with stubbed `gh`.

### Why this matters
The git tree is the only authoritative answer to "is this shipped." Handoffs, docs, and orientation cache are downstream artifacts that inherit any lie planted upstream — in the postmortem, a single false "shipped" claim propagated through five layers of artifacts in 24 hours, and a follow-on session struck a real shipped tool from the docs as "never built." This release closes the surfaces where that lie can be authored.

## [1.5.0] — 2026-04-30

### Theme — Build For Someone Else's Machine

A run of small, related changes converging on one principle: the code we ship runs on machines we've never seen, in projects we don't own, in shells we didn't configure. Portability is the baseline, not a feature.

### Added
- **Agent-driven install as first-class path** — `README.md` Quick Start replaces the `git clone && bash install.sh` block with a paste-to-agent prompt pointing at `docs/agent-install.md`. The agent reads the playbook, runs the installer, validates the result, and queues `/project-onboarding` as the immediate post-restart step. New `docs/agent-install.md` is written second-person to the agent — prereq checks, plugin selection guidance, manual fallback section, failure modes. Manual install steps remain in `docs/getting-started.md` but are no longer surfaced from the front page.
- **Doctrine rule: "Build For Someone Else's Machine"** (in `coordinator/CLAUDE.md`) — generalizes the older "Shipped Code Has No Home Field" intuition into a concrete fallback chain: explicit flag → env var → marker auto-discovery → silent skip (opt-in) or hard error with remediation (explicitly invoked). Hardcoded local paths are last-resort only. Project-scoped tools need a cwd-scope guard. Test fixtures and battle-story comments are exempt.
- **Project-RAG project-scope guard** — single-source preamble (`snippets/project-rag-preamble.md`) gains a guard so agents skip project-RAG calls when the indexed repo doesn't match the current working directory. Propagated to all 8 sentinel-fenced consumers via `bin/verify-preamble-sync.sh --fix`. Prevents wrong-project pollution when an agent is dispatched in repo A while project-RAG is indexed against repo B.

### Changed
- **UE distrust hook runbook** (`docs/testing/`) genericized — dropped the machine-specific `Keep_Blank` path that was leaking out of one author's environment. Runbook is now reproducible on any UE project layout.

### Internal
- No surface API changes for end users beyond the README Quick Start. The installer (`setup/install.sh`) is untouched and remains the canonical mechanism — agents and humans both invoke it, the difference is who types the command.

## [1.4.0] — 2026-04-29

### Added
- **Project-RAG readiness (W1–W6)** — generic project-RAG detection hook (cross-platform), single-source preamble snippet with sentinel-fenced inline distribution to 8 consumers + `verify-preamble-sync.sh`, `docs/wiki/rag-bait-conventions.md` (4 patterns including function-level purpose lines), executor RAG-bait stanza, Patrik generic project-RAG block alongside the UE block.
- **Reviewer-routed workers** — four Sonnet workers (`test-evidence-parser`, `security-audit-worker`, `dep-cve-auditor`, `doc-link-checker`) named in reviewer findings; EM dispatches. Generalizes the Patrik→Palí escalation pattern.
- **Mandatory release notes on every merge** — `merging-to-main` Step 1.5 always runs. Detects `CHANGELOG.md`, groups by Added/Changed/Fixed/Deps/Internal, suggests version bump (advisory).
- **Holodeck overlay Phase 1** — Patrik UE-specific workers subsection (`project_type: unreal` gated) and `merging-to-main` Step 1.6 UE check items.

### Changed
- **`/distill` reframed** — trim+archive specs (not delete), allowlist/denylist rubric, mandatory re-homing, Decision Rationale extraction, schema-pinned distillation log, broader link-heal sweep, negative-AC set-diff token check.
- **`/update-docs`** — gates atlas-enumeration + repomap-regen on RAG presence; adds preamble-sync phase; per-run repomap audit log.
- **`/architecture-audit`** — reframed to narrative + judgment with flag-drift-from-RAG check.
- **`atlas-integrity-check`** — repurposed to narrative-drift detection.
- **Three-tier repomap gating** — PM-directed: absent→primary, stale→fallback, fresh→skipped (demote, don't retire).
- **Plan-First Workflow** — adds "investigate before planning" doctrine; bug reports and consumer docs are framing, not ground truth.

### Internal
- Coordinator hook test suite wired as blocking gate in `workday-complete` and `merging-to-main`; reviewer-calibration sentinel sync via `bin/verify-calibration-sync.sh`.

## [1.3.0] — 2026-04-02

### Independence from Superpowers — Conscious Uncoupling (D-032)

Coordinator-claude is now fully self-contained. The soft dependency on [superpowers](https://github.com/obra/superpowers) (obra/superpowers) has been removed.

Superpowers gave us our start — we installed it when plugins first shipped, before coordinator-claude existed as a formal system. Its core skills (TDD, systematic debugging, planning, verification) became the behavioral floor we built on. Over time, the philosophical gap widened: superpowers treats the agent as a system to be hardened against its own optimization tendencies; coordinator-claude treats the agent as a professional with defined authority (the PM/EM model). Both work, but for different reasons — and the layered approach was paying context budget for parallel instructions we were overriding.

**New:**
- **`coordinator:brainstorming` skill** — PM/EM-native design gate. Turns intent into a committed spec through collaborative dialogue. HARD-GATE prevents implementation once brainstorming starts, but the EM has judgment on when to invoke (not "always brainstorm"). Includes targeted rationalization resistance and scope-splitting. Output feeds directly into `coordinator:writing-plans`.
- **`docs/specs/` convention** — brainstorming specs land at `docs/specs/YYYY-MM-DD-<topic>-design.md`.

**Changed:**
- **`skill-discovery` flowchart** — brainstorming gate is now judgment-based ("spec exists or EM judges brainstorming unnecessary?"), not mandatory.
- **`using-git-worktrees`** — removed `~/.config/superpowers/worktrees/` path convention.
- **`README.md`** — coordinator positioned as self-contained; superpowers install recommendation removed.
- **`docs/customization.md`** — `superpowers:writing-skills` → `coordinator:writing-skills`.

**Decision doc:** `docs/decisions/D-032-superpowers-conscious-uncoupling.md`

## [1.2.1] — 2026-04-01

### Path Hygiene — Move Default Output Paths Out of `.claude/`

Anthropic now enforces mandatory user permission grants for any writes inside the `.claude/` directory (recursively). Several default output paths were inside `.claude/`, causing permission friction for autonomous pipelines and subagents.

**Changes:**
- **Research output fallback:** `~/.claude/docs/research/` → `~/docs/research/` in `notebooklm/commands/research.md`, `notebooklm/pipelines/team-protocol.md`, and both cache versions (1.0.0, 1.1.0).
- **`settings.json` permissions:** Added explicit `Edit(~/.claude/**)` and `Write(~/.claude/**)` allow entries to cover platform-owned paths (task storage, plan mode output, team metadata) that cannot be relocated.
- **Task storage documentation:** The `~/.claude/tasks/{team-name}/N.json` reference in `deep-research/pipelines/team-protocol.md` and `structured-team-protocol.md` (source + cache) now notes these are platform-internal and must not be directly read/written by agents.

### `/distill` — Handoffs as First-Class Wiki Sources

Archived handoffs contain valuable architectural knowledge that was being treated as ephemera. The distillation pipeline now explicitly treats them as first-class inputs.

**Changes to `coordinator/pipelines/artifact-distillation/PIPELINE.md` and `agent-prompts.md` (source + cache):**
- **Phase 0 inventory** now includes `docs/research/` and `~/docs/research/` as artifact directories.
- **Special classification rules** added to the Phase 0 reality-check: archived handoffs are always `NEW` (never ephemeral); research outputs are always `NEW`; Pipeline C structured outputs (files containing `manifest_version:`) are `PRESERVE` — copied verbatim, never deleted.
- **Phase 1 scanner prompt** now includes explicit handoff section parsing: `## What Was Accomplished` → `[KNOWLEDGE]`, `## Key Decisions Made` → `[DECISION]`, `## Blockers or Issues` → `[KNOWLEDGE:gotchas]`.
- **New `[PRESERVE]` nugget type** added to the Phase 1 scanner for structured artifacts that should be copied verbatim without synthesis.
- **Phase 3 deletion manifest** now includes a `PRESERVE` disposition: research outputs and Pipeline C artifacts are never deleted, only canonicalized.
- **Distillation log format** updated to include `PRESERVE` as a valid disposition value.

## [1.2.0] — 2026-04-01

### Codex Review Gate — Independent-Model Second Opinion
- **New `codex-review-gate` skill** wraps the Codex plugin's `/codex:review` command with graceful error handling and structured result reporting. Codex (GPT-5.4) provides a different model family's perspective on code changes, catching issues that intra-family reviewers may share blind spots on.
- **`/workday-complete` Step 3.8 — on by default.** The day's full diff against main is reviewed by Codex as a second opinion alongside the existing daily review. Falls back gracefully if Codex CLI is not installed, not authenticated, or credits are exhausted — the existing daily review from Step 3 stands alone when Codex is unavailable. Designed for users on limited ChatGPT plans: one bounded review per end-of-day, not continuous.
- **`/bug-sweep --codex-verify` — opt-in flag.** After Claude's sweep identifies and fixes bugs, Codex reviews the fix diff for regressions or issues that Claude's own reviewers might miss. Captures a pre-fix baseline ref in Phase 2 for precise diff scoping. Codex findings go to the backlog for PM triage, not auto-fix.
- **Why a different model family matters.** Our existing reviewer pipeline (Patrik, Sid, Camelia, Pali) provides thorough domain-specific review, but all reviewers share Claude's model family. Blind spots may be correlated — if Claude misses a pattern, its reviewer personas are more likely to miss it too. Codex mitigates this by providing an independent sample from a different training lineage. The integration is additive (never blocking) and token-conscious (validation of diffs, not codebase discovery).
- **Requirements:** [openai-codex plugin](https://github.com/openai/codex-plugin-cc) installed, Codex CLI authenticated (`codex login`). No Codex API key needed — runs through the CLI.

## [1.1.1] — 2026-04-01

### Strategic Daily Review (new command)
- **`/daily-review` replaces `/code-health` as the default end-of-day check** in `/workday-complete`. The review-heavy build pipeline (plan → enrich → chunk → review) already catches code-level issues; end-of-day now focuses on whether the day's accumulated decisions create technical debt, lock into patterns, or miss opportunities for the product's longer-term direction.
- **Three-phase pipeline.** Haiku scout inventories the day's commits, file changes, plans, and handoffs. Sonnet analyst produces a narrative work summary identifying explicit and implicit architectural decisions. Sonnet reviewer provides a strategic assessment against the project's roadmap and vision.
- **Reusable daily summary artifact.** Output saved to `archive/daily-summaries/YYYY-MM-DD.md` — feeds `/update-docs`, `/distill`, completed work register, and next-morning orientation. Fills the gap between terse commit logs and verbose in-flight handoffs.
- `/code-health` remains available for on-demand detailed code-level review.

### Reviewer Strategic Awareness
- **All five domain reviewers now read project roadmap and vision documents** (when available) before reviewing. Reviewers flag when an implementation — even a correct one — creates accidental lock-in, forecloses a roadmap option, or misses a low-cost bridging opportunity toward planned future capabilities.
- Strategic findings use `minor`/`nitpick` severity with `architecture` category — they inform, they don't block.
- Each reviewer's strategic lens is adapted to their domain: the generalist reviewer focuses on architecture and extensibility; the game development reviewer on engine system choices and scalability; the front-end reviewer on design system evolution; the UX reviewer on user journey trajectories; the data science reviewer on model and pipeline architecture.
- Guardrails prevent false positives: no strategic findings when no roadmap exists, when concerns are purely speculative, or when work is explicitly temporary.

### Orientation Cache Enhancement
- `/workday-start` now includes a "Yesterday's Strategic Review" excerpt in the orientation cache, giving every subsequent session automatic strategic context without reading a separate file.

### Handoff Deletion Policy
- **Explicit policy: `/workday-complete` never deletes handoffs.** Handoffs are archived (moved to `archive/handoffs/`) by `/update-docs`, but only `/distill` may delete them — after careful knowledge extraction and PM approval.

## [1.1.0] — 2026-03-31

### Remember Plugin (new)
- **Temporal memory system.** New `remember` plugin adds session-scoped memory persistence. PostToolUse hooks capture key actions as they happen; SessionStart hooks inject the last N days of session history into context automatically.
- **Haiku-powered compression pipeline.** Raw session events are compressed by `claude-haiku` into structured NDC (Notable Decisions & Changes) summaries, then consolidated into daily memory files. Designed for minimal token overhead at session start.
- **Coordinator integration.** `session-end`, `update-docs`, and `workday-complete` commands now include a `/remember` step to persist session state before closing out.
- **Marketplace registration.** Plugin is registered in `marketplace.json` for one-command install.

### Deep Research — Pipeline A v2.2 (Internet Research)
- **Iterative deepening.** After Team 1 completes, the sweep agent produces a structured gap report (YAML severity scores + Gap Targets table). If significant gaps remain, the EM dispatches a smaller Team 2 (1-3 gap-specialists + merge-mode sweep) for targeted follow-up. Hard cap at 2 passes. `--shallow` flag skips the decision gate for single-pass behavior.
- **Structured gap reporting.** Sweep's gap report now includes machine-readable YAML front-matter (`deepening_recommended`, `coverage_score`, `high_severity_gaps`) and a Gap Targets table with severity, type, and suggested queries.
- **Gap-specialist prompt template.** New specialist variant for Team 2 with Prior Findings context, tighter timing (3 min floor / 8 min ceiling), D-prefixed claim IDs, and `resolves_gap` field linking claims to gap targets.
- **Merge-mode sweep.** Team 2's sweep produces a delta document (`deepening-delta.md`) instead of a full replacement. The EM merges the delta seamlessly into Team 1's synthesis.

### Deep Research — Pipeline A v2.1 (Internet Research)
- **Consolidator eliminated.** Specialists now report directly to the sweep agent, freeing one agent slot and reducing pipeline latency.
- **Adversarial specialist interaction.** Specialists are expected to challenge each other's claims via `SendMessage`. A resolution protocol is defined for contested findings.
- **Structured claims output.** Specialists produce dual output: `{letter}-claims.json` (machine-readable, typed claims with confidence scores) and `{letter}-summary.md` (human-readable).
- **Sweep phased discipline.** Sweep operates in three explicit phases: Assess (inventory specialist claims), Fill (targeted gap research), Frame (executive summary + conclusion).
- **EM scoping checklist.** Sub-question quality gates from published multi-agent research ensure scoping produces decomposable, answerable questions.

### Deep Research — Pipeline B v2.1 (Repo Research)
- **Structural orientation pass.** EM performs a codebase orientation (entry points, key directories, architecture pattern) before scoping, so focus questions are grounded in actual structure.
- **Execution-trace framing.** Specialists frame analysis around execution paths rather than file-by-file inventory, producing more actionable findings.
- **`file:line` citation enforcement.** Specialist prompts now require `file:line` citations for all claims, making findings directly navigable.
- **LLM context file discovery.** Scoping phase now surfaces `CONTEXT.md`, `CLAUDE.md`, `.cursorrules`, and similar files as high-priority reads for specialists.
- **Independent-analysis-first comparison mode.** When comparing two repos, specialists analyze each independently before cross-referencing to avoid anchoring bias.

### Deep Research — Pipeline B v2.2 (Repo Research)
- **`--deeper` mode.** EM generates a dependency-weighted repomap during scoping (Phase 1.5). Language-aware import extraction (Python, JS/TS, Go, Rust, C/C++, Java) with cross-reference counting and tiered output (Tier 1/2/3). Specialists read repomap before inventories for prioritization. Graceful fallback if import graph is thin.
- **`--deepest` mode.** Two-wave pipeline: Wave 1 is the standard 7-agent team (unchanged), Wave 2 dispatches a Sonnet atlas subagent after synthesis. Produces 4 architecture atlas artifacts: file index, system map, connectivity matrix, and architecture summary. `--deepest` implies `--deeper`. Atlas failure is non-blocking.

### NotebookLM — Pipeline D v2
- **Strategist elimination.** Removed the separate Opus strategist agent. EM now scopes directly with baked-in NLM best practices, saving one agent dispatch and ~2 minutes.
- **NLM-adapted claims schema.** Workers now output structured `{letter}-claims.json` with NLM-specific fields (`transcription_suspect`, `source_type`, `nlm_citation`) alongside `{letter}-summary.md`.
- **Synthesizer → sweep rename.** Final agent renamed from "synthesizer" to "sweep" to match Pipeline A naming and reflect its actual role (adversarial coverage check + gap-filling, not just synthesis).
- **Notebook preservation (default).** Notebooks are now kept after research runs by default — they represent significant ingestion work and are valuable for follow-up queries. New `--cleanup` flag opts in to deletion.

### Developer Ergonomics
- **Plugin command naming cleanup.** Removed redundant plugin-name prefixes from all commands: `deep-research-web.md` → `web.md`, `deep-research-repo.md` → `repo.md`, `notebooklm-research.md` → `research.md`, etc. 26 files updated, all cross-references synced.

## [1.0.0] — 2026-03-28

Initial public release. 8 plugins, 24 agents, 37 skills.

