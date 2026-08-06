---
name: workstream-start
description: Orient session — preflight, load context, choose work
allowed-tools: ["Read", "Grep", "Glob", "Bash"]
argument-hint: "[task-description]"
---

# Workstream Start — Preflight and Orientation

Orient this agent by verifying the environment, loading project context, and choosing work.

**Design note:** Multiple agents may be running concurrently on the same repo. This command orients ONE agent — it does not assume exclusive access to the codebase or the user's attention.

---

## Setup-freshness probe

If `/coordinator:repo-setup` just ran in this session, `/workstream-start` is the orientation skill being applied to a session that already oriented itself by running setup. Detect this and emit a different one-liner — do NOT proceed through the rest of this skill, which would burn budget on re-orienting an already-oriented session.

**Detection — sentinel file (`state/.repo-setup-just-ran`):** if it exists, delete it immediately
— before printing anything, so a failure mid-output leaves the sentinel already cleared rather
than re-firing the probe — then print the notice below and stop:

> Setup just ran — your orientation is current. /workstream-start is the orientation skill for sibling EMs or post-restart sessions, not for the operator who just set the repo up. Use /workday-start tomorrow morning. To start work now, just describe what you want to do — the EM has full context from setup.
>
> Doctrine: docs/wiki/produce-not-prescribe.md — /coordinator:repo-setup produces the minimum-viable orientation substrate (orientation_cache.md); /workstream-start adds-to it when there's something to add.

**Known limitation:** concurrent `/workstream-start` invocations in the same repo race on this
consume. Single-user / single-machine scope makes the window tiny; both sessions exit-no-op
rather than crash. Accepted as low-impact — don't "fix" with a lock; the file IS the lock.

The sentinel is single-shot: this probe consumes it. Subsequent `/workstream-start` invocations behave normally. The sentinel is `.gitignore`'d — it's a per-session transient marker, never committed.

## Orient

The assembler computes the session-cadence orient spine — EM effort/model drift, addon/doctor
health, inbound cross-repo memo staleness, project-RAG staleness, agent-worktree classification,
handoff triage (ready-to-fire / awaiting-gate / stale-plan advisories), branch-day-span
mismatch, and health-probe drift (exec-bit, claude-klabauter-bin sentinel, ceremony hook, marker
freshness) — and returns one decision object: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/orient-assemble" brief --cadence session`. Read the JSON. Every
`directives[]` entry names an existing atomic CLI to run when not `already_satisfied`; every
`judgment_points[]` entry is an open human/EM branch the assembler could not resolve for
you — present each with its `dispositions[]` and pick, don't silently drop any.

**Don't re-derive what the assembler already computed.** The old per-check narration this skill
used to carry (EM environment check, addon health scan, cross-repo memo surfacing, project-RAG
staleness, agent-worktree sweep, handoff triage, branch-span assert) is now the assembler's job —
reading its `directives[]`/`judgment_points[]` replaces running those checks by hand.

**Do NOT load, summarize, or act on any handoff surfaced by the assembler.** A `ready-to-fire`
directive naming a handoff is not implicit selection — the PM may not want to pick it up this
session, or may have other priorities first. Surface it; don't load it. **When the PM indicates
they want a handoff picked up** — by dropping a link, naming it, or saying "pick up that
handoff" — read the full file into context. This — and only this — sets `HANDOFF_LOADED=true` for
the Engage section below. Alternatively the PM may use `/pickup`, purpose-built for handoff
resumption.

**Stale advisory / call-note markdowns are not pendency.** Files in `state/handoffs/`, `tasks/`,
or `archive/` that look like live work-items may already be addressed by commits that landed
after the file was authored. Before treating any surfaced markdown's body as a live action item,
run `git log --oneline --since="<file-mtime>" -- <cited-paths>` for the paths it cites. Surfacing
un-verified stale advisories to the PM as actionable wastes a question.

**Route-to-baton default:** any surfaced memo — likewise any review finding or triage item
encountered during this ceremony — whose subject falls inside the scope of an active handoff
(`state/handoffs/*.md`, `status: open|claimed`) gets a routing note appended into that handoff
under a dated `## Routed from inbox triage (<YYYY-MM-DD>)` heading (source path cited, handoff
frontmatter untouched), and that edit committed with pathspec, as a matter of course.

**If `tasks/` or `archive/` is gitignored:** Warn the user — these directories must be tracked.

### Session residue the assembler doesn't cover

**Safety commit.** Secure any uncommitted work before touching branches — non-negotiable, don't
ask permission:

`CLAUDE_INVOKING_COMMAND=workstream-start "${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-safe-commit" --blanket "chore: workstream-start sweep — pre-orientation capture"`

If nothing to commit, the CLI is a silent no-op.

**Setup-state self-heal (silent).** On `source_is_live` machines the install-receipt path never
fires normally — self-heal it idempotently:

`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-setup-state" auto-record-if-source-is-live`

No output to surface.

**Branch detection.** main is read-only — all work happens on a work branch, never main directly.
If already on a non-main branch, stay on it. If on main, create `work/{machine}/{date}` (append
`-2` etc. on collision) after running `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/sync-main" --quiet` and reporting any divergence to the PM first. The assembler's
branch-day-span directive (if surfaced above) supersedes hand-computing this — apply it, don't
re-derive it.

**Branch staleness.** If the branch has diverged from `main` more than 2 days
(`git merge-base HEAD origin/main` → commit date → age), recommend `/merge-to-main` and wait for
the PM's answer before proceeding. 2 days or fewer: continue silently.

**Coordinator / project-rag binding spot-check (whoami).** Probe the session adopter directly —
this is daemon-independent, computed from git+fs, and distinct from any plugin-specific binding:

`"${COORDINATOR_PYTHON:-python3}" -m coordinator_whoami.session 2>/dev/null`

Non-zero / unparseable JSON → `whoami: degraded (CLI failed)`. Otherwise report `binding.kind`
(`unbound`, or `bound → <target> (<status.state>)`).
Workstream-start does NOT surface
bound-but-cwd-mismatch — that's `/repo-setup`'s job, and would false-positive for operators
working outside the bound project root.

**Outstanding cross-repo memo outbox drafts.** Inbound memo staleness is in the assembler's
output above; outbox drafts awaiting send are not — surface them separately:

`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/workday-start-cross-repo-memo-outbox-surface"`

Non-empty output → surface verbatim under `#### Outbox drafts awaiting send (DoE attention):`.
Empty → skip silently. Details: `pipelines/workday-start-internals.md § Step 1.46`.

### Context load — not part of the shared spine

**Lessons.** Enumerate `state/lessons/*.yaml` (if present) — one YAML file per learned-pattern
entry; review every entry (`bin/query-records --type lesson` for a structured listing). Read
`CONTEXT.md` (if present) — domain glossary. Project `CLAUDE.md` and global `~/.claude/CLAUDE.md`
are already in system context — don't re-read them. Note the count; principles are in CLAUDE.md,
don't recite them.

**Action items, roadmap, project tracker.** Conditional on `state/.workday-start-marker`
containing today's date — if it does, `/workday-start` already reviewed these this cadence, skip.
Otherwise read whichever of `ACTION-ITEMS.md`/`docs/active/ACTION-ITEMS.md`/`docs/ACTION-ITEMS.md`,
`ROADMAP.md`/`docs/roadmap.md`/`docs/ROADMAP.md`, and `docs/project-tracker.md` exist (first match
per row wins). Load silently; their content speaks for itself, except the tracker gets a brief
active-workstreams/blocked/ready-for-execution summary — it also informs the Engage work menu
below.

**Orientation check.** The SessionStart hook already injected orientation context at boot — don't
re-read those files here. If the hook reported no fresh cache, note it and point at
`/workday-start` or `/update-docs`. Surface the most recent review-trail record if any exist
(`python list-review-trail-records.py | tail -1`), so the EM knows where the un-reviewed gap
begins.

**Documentation index.** If `docs/README.md` exists, note the wiki/research/plan counts briefly.
If `docs/guides/` or `docs/research/` exist without an index, note that `/update-docs` will build
one. Neither → skip silently.

**Fan-out tooling available:** `fan-out-dispatch.py` (overlap pass + scoped prompt compiler) —
use instead of hand-authoring parallel executor prompts.

**Delegation context (game-dev projects).** Conditional on `coordinator.local.md` declaring
`project_type: game-dev` with `unreal` in `project_subtypes` — skip silently otherwise. Two-tier
dispatch: direct (verification, quick fact-finding, one-off mutations) via your 8 visible tools;
dispatch (any real work in a single domain) via `Agent(subagent_type='example-game-repo-control:ue-{domain}')`.
Blueprint graph operations require ue-asset-author — Python can't do them. For multi-domain or
underspecified tasks, decompose and dispatch domain agents sequentially with verification between
steps.

**Project-RAG subsystem context.** Conditional on `project-rag` MCP availability (ToolSearch for
`mcp__project-rag__project_subsystem_profile`) — skip silently otherwise. Call
`project_subsystem_profile()` with no arguments to discover the subsystem map; report the count.
When you need to understand a subsystem before delegating, call
`project_subsystem_profile("<name>")` instead of dispatching an Explore agent — deterministic SQL
at <200ms, replacing 150-300K token Explore dispatches. (Staleness for this project-RAG binding
is already covered by the assembler's session-cadence output above — don't re-check it here.)

---

## Engage

Choose work and load task-specific context.

### Work selection

**CRITICAL — Handoff loaded?** Check whether the PM has directed you to pick up a handoff (by dropping a link, naming it, or saying to pick it up). Track this as a mental flag: `HANDOFF_LOADED=true`. If YES:

> **The handoff IS the work order.** Do NOT present a menu. Do NOT ask "what should this agent work on?" Do NOT list the handoff's action items and wait for the user to pick one. Do NOT ask "want me to proceed?"
>
> Instead: read any files the handoff references that aren't yet in context, then **dispatch the first action item — dispatch IS running.** You're the next relay runner — the baton has been passed. Pick it up and run. "Run" = dispatch an executor by default (below the plan threshold, the common case); EM-inline only when ALL of the following conjunctive criteria hold: the fix locus is known and ≤3 files, estimated EM wall-clock is under 60s on a >30k-file repo, the fix is mechanical (rename, version bump, single-line tweak, import addition), the sub-agent would only re-read context the EM already has loaded, and the fix is in a file the EM is already editing (in the `~/.claude` meta-repo, `coordinator/em-operating-model.md § Escalation tiers` tier-3 carve-out applies for 1-2 line infra edits). No PM round-trip, no plan ceremony for sub-T3 work — see also `skills/pickup/SKILL.md` § Dispatch routing default for the shared anchor.
>
> If the handoff lists multiple next steps, execute them in order unless the PM redirects.

**If NO handoff was loaded** (PM hasn't directed you to one yet, or no handoffs exist), check for the fresh-install sentinel before presenting the generic menu:

### Fresh-install orientation branch (fallback)

**Predicate — fire this branch ONLY when ALL three conditions hold:**

1. No handoff is loaded (already established above).
2. The fresh-install sentinel `~/.claude/.coordinator-fresh-install` exists on disk.
3. (Implicit: the sentinel has not already been consumed — consuming it is the first act of this branch.)

Check whether `$HOME/.claude/.coordinator-fresh-install` exists.

**If the sentinel exists — fresh-install orientation:**

Before doing anything else, consume (delete) the sentinel file `$HOME/.claude/.coordinator-fresh-install` so this branch does NOT re-fire on subsequent no-handoff sessions.

Then orient the operator toward their `~/.claude` meta-repo as the primary surface to evolve:

> **Welcome — coordinator is installed.** Your `~/.claude` directory is a git-tracked repo that is your live coordinator install. It's the surface you evolve — adding project context, capturing lessons, writing your CLAUDE.md — not the upstream `coordinator-claude` source.
>
> The primary path from here is to `/pickup` the continue-onboarding handoff that the installer left in `state/handoffs/` — it walks you through co-writing your CLAUDE.md and running your first `/workstream-start` on a real project. If no handoff is visible above, you can start fresh:
>
> **Suggested first steps:**
> 1. **Co-write your `~/.claude/CLAUDE.md`** — personalize your EM persona, coding conventions, and any project-level extensions with the EM's help (just ask).
> 2. **`/repo-setup` in your first project repo** — sets up tracking, CLAUDE.md, and the post-commit hook.
> 3. **`/workday-start`** — run once per day to orient, sweep, and load the day's context.
>
> _This orientation fires once. The sentinel `~/.claude/.coordinator-fresh-install` has been cleared — subsequent no-handoff sessions will show the standard work menu instead._

**Sentinel lifecycle summary (for documentation clarity):**
- **Created by:** install Layer 0 (chunk C1 of the install plan) at `~/.claude/.coordinator-fresh-install`.
- **Consumed by:** this branch on first activation — deleted before the orientation message is shown.
- **Post-consumption:** absent, so this branch is permanently skipped on all subsequent no-handoff sessions. The second clean session sees the standard work menu below — not this orientation. This is the testable guarantee: if `~/.claude/.coordinator-fresh-install` is absent, this branch does not fire regardless of handoff state.

**If the sentinel does NOT exist**, fall through to the standard work menu:

**What should this agent work on?**

1. **Implementing a feature** — From plan docs or feature specs
2. **Fixing a bug** — From issue tracker, bug report, or failing tests
3. **Reviewing code** — Code review of recent changes
4. **Research / exploration** — No ceremony, just start
5. **Maintenance** — Daily health check, weekly audit, or debt triage
5a. **Strategy and ceremonies** — `/shape` (converge on a problem), `/goal-setting` (OKR goal-setting, initiative altitude), `/roadmap-planning` (week-scoped planning), `/spike` (prove a mechanism is viable before a plan commits to it — bounded, binary-outcome derisking; gating detailed in the "`/spike` gating and pipeline position" paragraph immediately below)

**`/spike` gating and pipeline position (skill body: `coordinator/skills/spike/SKILL.md`).** `coordinator:spike` sits in the pipeline graph as `shape → spike → plan → execute`, with a `plan⇄spike` back-edge — `coordinator:plan` Branch B can trampoline into a spike on an unproven mechanism gate (`coordinator/skills/plan/SKILL.md`), and a viable spike verdict resumes the trampolined plan or routes to a fresh `coordinator:plan`; a not-viable verdict routes to `coordinator:shape`/PM. `coordinator:pickup` also routes a `spike-before-plan` handoff body directive to `/spike` ahead of straight-to-plan (`coordinator/skills/pickup/SKILL.md`).

The bare `/spike <mechanism>` invocation offered in the menu above is **PM-gated, never EM-initiated**, and **NEVER invoked from a subagent.** Gating is structural (DEC-4), not self-asserted — see `coordinator/skills/spike/SKILL.md` § Invoke Gating for the full discriminator (including the one EM-reachable `coordinator:plan` Branch B trampoline path).
6. **Work the backlog** — Improvement queues, deferred items, recurring lessons. Central queue: resolved via `coordinator-state-root.py --central`'s `improvement-queue/*.yaml` (structured per-entry YAML; central state lives in claude-klabauter); local queue: `state/improvement-queue/*.yaml`. Surface current depth when framing this option (e.g., "Central: 17 entries, 3 with recurring ≥ 3. Local: 2 entries. Want to tackle some of these?"). Also check `state/bug-backlog/*.yaml` — if it exists and has ≥10 open P1/P2 entries, advocate `/bug-blitz` as a backlog-grinding option. Also check `state/cross-repo-commitments/` — a directory of YAML entries tracking loops we're owed by sibling repos (`status: open`); if any `status: open` entries exist, surface depth alongside the queues (e.g., "2 open sibling commitments — oldest 12d (computed from `observed`)"). Skip silently when the directory is absent or empty.

   **Red-suite predicate — independent of backlog depth.** Resolve the machine token via
   `machine-local get coordinator.machine_slug` (resolved the same way `/workday-start` Step 1.66
   does — do not invent a divergent spelling), then read `state/test-red/<machine>.yaml` if
   present — a mapping keyed by tier (e.g. `fast`, `plugin-ecosystem`), each tier evaluated
   independently (schema, tri-state `failing`, delta vocabulary, and void-and-expiry rules per
   below). Absent or malformed → skip this predicate silently, no
   error, no narration. When present, for each tier compute the delta against the comparison
   baseline (`acknowledged.baseline` when live and unexpired, else `previous.failing`) per that
   schema, and advocate `/bug-blitz` — **naming the tier and surfacing the delta counts, never a
   bare "the suite is red"** — on any of:
   - `new` is non-empty → "{tier}: N new failures since the acknowledged baseline" (or "since the
     last run", when unacknowledged).
   - `acknowledged` is null or voided — **independent of whether `new` is also non-empty** — and
     `failing[]` is non-empty:
     - **void-on-doubt** (owner unresolvable/unparseable/missing baseline) → "{tier}:
       acknowledgement void: owner `<path>` unresolvable — M failing, unacknowledged."
     - **void-on-expiry** (`ran_at` past `expires_at`) → "{tier}: acknowledgement expired
       `<date>`, owner `<path>` still open — M failing."
     - **no acknowledgement at all** → "{tier}: M unacknowledged failures."
   - the acknowledged owner artifact is closed/terminal while `failing[]` is still non-empty →
     "{tier}: owning work `<path>` closed but M failures remain."
   - `failing` is `null` → "{tier}: red, failing set unavailable" — never read as clean, never
     folded into a `new`/`cleared`/`persistent` delta.

   An acknowledged, unexpired red set whose delta is all-`persistent` advocates nothing from this
   predicate — that is the correct silence, not a gap. This predicate never runs the test tier
   itself and never blocks on its outcome — it only reads the record claude-klabauter's emitter already
   wrote.
7. **Other** — Something else (describe it)

If `$ARGUMENTS` is provided, use it to identify the task directly and skip the menu.

**Adapt this menu to the project:** If the project tracker was loaded, surface its ready/executing items as concrete options. If project-specific plan docs or priority lists exist (check `docs/`, `tasks/`, `tasks/plans/`), surface those too. The menu should reflect what's actually available, not just generic categories.

**Unsized ask?** If the choose-work residue above surfaces a fresh backlog item or an ad-hoc PM ask with no sizing-object yet, `coordinator:sizing` is the entry point — a named cross-reference, not a dependency; no branch logic or schema coupling on its route.

### Load task context

**If continuing from a handoff:** Read any files the handoff references that aren't yet in context, then dispatch the first action item — dispatch is the fast path below the plan threshold; EM-inline only per the same conjunctive EM-inline checklist above (§ Work selection).

**If from the menu:** Based on the user's choice:

- **Implementing:** Find and read the relevant plan doc. Summarize the first implementation step.
- **Fixing a bug:** Identify the failing test, error, or reproduction steps. Read the relevant source.
- **Reviewing:** Identify what to review (recent commits, specific files, PR). Load review criteria.
- **Research:** Ask what to explore. No additional prep needed.
- **Other:** Ask the user to describe the task. Load relevant context.

### Status report

Briefly report:
- **Repo state:** `git status` summary — note that uncommitted changes may belong to other concurrent agents
- **Branch:** Current branch name

Keep this to 2 lines. This is orientation, not ownership.
