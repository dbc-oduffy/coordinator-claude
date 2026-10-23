---
name: workstream-start
description: Orient session — preflight, load context, choose work
allowed-tools: ["Read", "Grep", "Glob", "Bash"]
argument-hint: "[task-description]"
---

# Workstream Start — Preflight and Orientation

Multiple agents may
run concurrently on the same repo — this orients ONE. Orientation is not research: a build ask is fired, not surveyed; fire with context, own the swimlanes (`THE-EM-TIME-AND-COST-SPENT-IS-A-RED-FLAG`). Unlike `/pickup` (artifact-first, for a PM
already pointing you at work), this is general orientation.

---

## Setup-freshness probe

If `state/.repo-setup-just-ran` exists, `/repo-setup` just ran. Delete it first, print one line —
`Setup just ran: running orientation once now.` — and continue with Orient; the sentinel never
suppresses orientation.

<!-- engine-gap: field=session.setup_just_ran producer=unknown memo=engine-gap-markers-name-a-memo-that-was-never-filed.md -->

**Machine profile.** A consumer box: `machine-local get coordinator.machine_profile` prints
`consumer`, or nothing and no `repos.*` path holds a `.coordinator-dev-repo` file. Skip
author-only steps there without comment.

## Orient

The session-cadence orient spine (health, staleness, handoff triage, branch checks, ...) is
computed for you. PowerShell hosts (Shape W, `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`):
`& "$env:COORDINATOR_SETTINGS_HOME\bin\orient-assemble.exe" brief --cadence session`. Read the
JSON. Every `directives[]` entry names a CLI to run when not `already_satisfied`; on a consumer
box skip any that reads fleet state (group-EM watch, cross-repo memo inbox, fleet registries,
Cockpit). Every `judgment_points[]` entry is an open branch: resolve it yourself — present each
with its `dispositions[]`, pick, drop none. Don't hand-run what these compute.

**Do NOT load, summarize, or act on any handoff the orient output surfaces** — a `ready-to-fire`
directive naming one is not implicit selection. When the PM asks for one, read the full file and
set `HANDOFF_LOADED=true` for Engage (or the PM uses `/pickup`). A markdown in `state/handoffs/`,
`tasks/`, or `archive/` may already be addressed by later commits: verify.
<!-- engine-gap: field=handoffs.stale_advisory_reconcile producer=unknown memo=engine-gap-markers-name-a-memo-that-was-never-filed.md -->

**Route-to-baton default:** a memo/finding/triage item inside an active handoff's scope
(`state/handoffs/*.md`, `status: open|claimed`) gets a dated `## Routed from inbox triage
(<YYYY-MM-DD>)` note, committed with pathspec, then closed: `archive-stamp-cli resolve-memo <memo>
--decision accepted --decision-note "routed into <baton>" --realized-by "<baton>"
--in-repo-capture "<baton>"`. Leave the memo open only if the capture didn't land. Other forks are `/pickup`'s. **`tasks/`/`archive/` gitignored?**
Warn — must track.

### Session residue not covered above

Bin paths below are relative to the settings-home `bin/` directory (resolve per
`${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`). **One shell call** for the three
independent, non-gating probes below:

- **Safety commit**, non-negotiable, don't ask, no-op if nothing to commit:
  `coordinator-safe-commit --blanket --invoking-command workstream-start "chore:
  workstream-start sweep — pre-orientation capture"`.
- **Setup-state self-heal**, silent: `coordinator-setup-state auto-record-if-source-is-live`.
- **Outbox drafts:** `coordinator_core/workday_start/outbox_drafts.py` — non-empty → surface
  verbatim; empty → skip.

**Branch detection** stays its own call — it gates everything after: main is read-only. Stay on
a non-main branch if on one (including `coordinator.dayBranch`). On main, run `sync-main --quiet`
(report divergence first), then — author box only — create `work/{machine}/{date}` (`-2` on
collision), unless the branch-day-span directive supersedes. A consumer box stays on the branch it is on and cuts nothing.
Diverged from `main` >2 days → recommend `/merging-to-main`, wait for the PM; ≤2 days → continue.

### Context load — not part of the shared spine

**Lessons.** Enumerate `state/lessons/*.yaml` (`query-records --type lesson`); read `CONTEXT.md`
if present. Note the count.

**Action items / roadmap.** Skip if `state/.workday-start-marker` has today's date. Otherwise read
the first of `ACTION-ITEMS.md`, `ROADMAP.md` (or `docs/` variants) that exists; give a brief
active/blocked/ready summary feeding the Engage menu.

**Orientation check.** SessionStart already injected orientation context — don't re-read it. No
fresh cache → point at `/workday-start` or `/update-docs`. Review-trail: glob
`state/review-trail/**/*.json` and `archive/review-trail/**/*.json`, sort by basename, surface the last path
(a frozen corpus, not a live gap).

**Doc index.** `docs/README.md` present → note wiki/research/plan counts; else note `/update-docs`
builds one. Parallel executor prompts: `fan-out-dispatch.py`.

**Author box only.** `project_type: game-dev` + `unreal` in `project_subtypes` → single-domain
work goes to `Agent(subagent_type='example-game-repo-control:ue-{domain}')`. `project-rag` MCP available →
`project_subsystem_profile()`, report the count; prefer `project_subsystem_profile("<name>")` over
Explore.

---

## Engage

### Work selection

**CRITICAL — handoff loaded?** If `HANDOFF_LOADED=true`: **the handoff IS the work order.** No
menu, no "what should this agent work on?", no listing items and waiting, no "want me to proceed?" Read any referenced files
not yet in context, then **dispatch the first action item — dispatch IS running**, per pickup's
dispatch-economics checklist (`skills/pickup/SKILL.md`). Multiple next steps → execute in order
unless the PM redirects.

> **Do not ask whether to dispatch** — invoking this skill IS the request for the dispatch this
> step names; it dissolves no gate this skill's own body names.

**Fresh-install branch — fires ONLY when no handoff is loaded AND
`$HOME/.claude/.coordinator-fresh-install` exists.** Delete the sentinel BEFORE emitting, then
emit: `~/.claude` is the live install to evolve, the onboarding handoff if present, fallback first
steps (co-write `CLAUDE.md`, `/repo-setup`, `/workday-start` daily).

**Otherwise, the standard work menu** — each option loads its own context once picked:

1. **Implementing** — read the relevant plan doc; summarize the first step.
2. **Fixing a bug** — identify the failing test/error/repro; read the source.
3. **Reviewing** — identify the target (commits/files/PR); load review criteria.
4. **Research / exploration** — ask what to explore; no ceremony.
5. **Maintenance** — daily health check, weekly audit, or debt triage.
5a. **Strategy/ceremonies** — `/shape`, `/goal-setting`, `/roadmap-planning`, `/spike` (PM-gated,
    never EM/subagent-initiated: `spike/SKILL.md` § Invoke Gating; pipeline position: wiki)
6. **Work the backlog** — surface depth of central (`coordinator-state-root.py --central`) and
   local `state/improvement-queue/*.yaml`; `state/bug-backlog/*.yaml` ≥10 open P1/P2, or any
   `status: open` in `state/cross-repo-commitments/`, → advocate `/bug-blitz` (skip if absent/empty).

   **Red-suite predicate — independent of backlog depth.** Read `state/test-red/<machine-local get
   coordinator.machine_slug>.yaml` if present (absent/malformed → skip). Per tier, delta against
   `acknowledged.baseline` (live, unexpired) else `previous.failing`; advocate `/bug-blitz` —
   **naming the tier and delta counts, never a bare "the suite is red"** — when `new` is
   non-empty, the acknowledgement is null/void/expired or its owner closed while `failing[]` is
   non-empty, or `failing` is `null` (never read as clean). Wordings: wiki. An acknowledged,
   unexpired, all-`persistent` set advocates nothing. Reads the record only; never runs the tier
   or blocks.
   <!-- engine-gap: field=test_red.advisory producer=unknown memo=engine-gap-markers-name-a-memo-that-was-never-filed.md -->
7. **Other** — ask the user to describe it; load relevant context.

`$ARGUMENTS` provided → use it directly, skip the menu. Offer the tracker's ready/executing items
and plan docs (`docs/`, `tasks/`, `tasks/plans/`) as concrete options. A fresh backlog item or
ad-hoc ask with no sizing-object routes through `coordinator:sizing` first.

### Status report

Two lines: repo state (uncommitted changes may be a peer's), current branch.
<!-- engine-gap: field=session.repo_status_summary producer=unknown memo=engine-gap-markers-name-a-memo-that-was-never-filed.md -->
