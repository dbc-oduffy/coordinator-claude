---
name: workstream-start
description: Orient session — preflight, load context, choose work
allowed-tools: ["Read", "Grep", "Glob", "Bash"]
argument-hint: "[task-description]"
---

# Workstream Start — Preflight and Orientation

Orient this agent: verify the environment, load project context, choose work. Multiple agents may
run concurrently on the same repo — this orients ONE, not exclusive access. Contrast with
`/pickup`: this is general orientation; pickup is artifact-first, for a PM already pointing you
at specific work.

---

## Setup-freshness probe

If `state/.repo-setup-just-ran` exists, `/repo-setup` just ran — delete it immediately (before
printing anything), then emit the notice below and stop:

> Setup just ran — your orientation is current. /workstream-start is for sibling EMs or
> post-restart sessions, not the operator who just set up. Use /workday-start tomorrow; to start
> work now, just describe it.

<!-- engine-gap: field=session.setup_just_ran producer=unknown memo=2026-08-14-doe-claude-em-three-cut-obligations-from-the-corpus-grind.md -->
Single-shot; race window and lifecycle: wiki.

## Orient

The session-cadence orient spine (health, staleness, handoff triage, branch checks, ...) is
computed for you. PowerShell hosts (Shape W,
`snippets/resolve-coordinator-bin.md`):
`& "$env:COORDINATOR_SETTINGS_HOME\bin\orient-assemble.cmd" brief --cadence session`. Read the JSON. Every `directives[]` entry names a CLI to run when not
`already_satisfied`; every `judgment_points[]` entry is an open branch to resolve yourself —
present each with its `dispositions[]`, pick, don't drop any. Don't hand-run what these compute.

**Do NOT load, summarize, or act on any handoff the orient output surfaces** — a `ready-to-fire`
directive naming one is not implicit selection. When the PM indicates they want a handoff picked
up (link, name, or "pick up that handoff"), read the full file; sets `HANDOFF_LOADED=true` for
Engage below — or the PM uses `/pickup` directly. A markdown in `state/handoffs/`, `tasks/`, or
`archive/` may already be addressed by commits landed after it was authored — verify before
treating it as pending.
<!-- engine-gap: field=handoffs.stale_advisory_reconcile producer=unknown memo=2026-08-14-doe-claude-em-three-cut-obligations-from-the-corpus-grind.md -->

**Route-to-baton default:** a memo/finding/triage item inside an active handoff's scope
(`state/handoffs/*.md`, `status: open|claimed`) gets a dated `## Routed from inbox triage
(<YYYY-MM-DD>)` note, committed with pathspec, then closed: `archive-stamp-cli resolve-memo <memo>
--decision accepted --decision-note "routed into <baton>" --realized-by "<baton>"
--in-repo-capture "<baton>"`. Stays `open` only if the capture didn't land or a PM question is
unanswered. Every other fork is `/pickup`'s.

**`tasks/`/`archive/` gitignored?** Warn — must track.

### Session residue not covered above

Bin paths below relative to the coordinator settings-home `bin/` directory — resolve per rung 0 /
Shape W in `snippets/resolve-coordinator-bin.md` (PowerShell hosts) or rung 2 (POSIX hosts).

**One shell call** for the three independent, non-gating probes below (order doesn't matter among
them — none reads another's output):

- **Safety commit**, non-negotiable, don't ask, silent no-op if nothing to commit:
  `CLAUDE_INVOKING_COMMAND=workstream-start coordinator-safe-commit --blanket "chore:
  workstream-start sweep — pre-orientation capture"`.
- **Setup-state self-heal**, silent: `coordinator-setup-state auto-record-if-source-is-live`.
- **Outbox drafts** (inbound staleness is already in the orient output):
  `workday-start-cross-repo-memo-outbox-surface` — non-empty → surface verbatim; empty → skip.

**Branch detection** stays its own call — its outcome (which branch you end up on) gates
everything that follows: main is read-only. Stay on a non-main branch if on one; on main, run
`sync-main --quiet` (report divergence first), then create `work/{machine}/{date}` (`-2` on
collision) — superseded by the branch-day-span directive when present. Diverged from
`main` >2 days → recommend `/merge-to-main`, wait for the PM; ≤2 days → continue silently.

### Context load — not part of the shared spine

**Lessons.** Enumerate `state/lessons/*.yaml` (`query-records --type lesson`); read `CONTEXT.md`
if present. Note the count — `CLAUDE.md` is already in context.

**Action items / roadmap.** Skip if `state/.workday-start-marker` has today's date.
Otherwise read whichever of `ACTION-ITEMS.md`, `ROADMAP.md` (or their `docs/` variants) exist,
first match wins; it gets a brief active/blocked/ready summary feeding the Engage menu.

**Orientation check.** SessionStart already injected orientation context — don't re-read it. No
fresh cache → point at `/workday-start` or `/update-docs`. Surface the most recent
`list-review-trail-records` path so the EM knows where the un-reviewed gap begins.

**Doc index / fan-out.** `docs/README.md` present → note wiki/research/plan counts;
`docs/guides/`/`docs/research/` without an index → note `/update-docs` builds one.
`fan-out-dispatch.py` — use instead of hand-authoring parallel executor prompts.

**Delegation (game-dev).** `project_type: game-dev` + `unreal` in `project_subtypes`
(`coordinator.local.md`) → dispatch `Agent(subagent_type='example-game-repo-control:ue-{domain}')` for
single-domain work (Blueprint graph needs ue-asset-author); 8 tools direct for fact-finding.

**Project-RAG.** MCP available → call `project_subsystem_profile()` (no args), report the count;
prefer `project_subsystem_profile("<name>")` over Explore — deterministic, <200ms.

---

## Engage

Choose work and load task-specific context.

### Work selection

**CRITICAL — handoff loaded?** If `HANDOFF_LOADED=true`: **the handoff IS the work order.** No
menu, no "what should this agent work on?", no listing items and waiting, no "want me to proceed?"
Read any referenced files not yet in context, then **dispatch the first action item — dispatch IS
running**, per pickup's dispatch-economics checklist (`skills/pickup/SKILL.md`). Multiple next
steps → execute in order unless the PM redirects.

**If no handoff loaded — fresh-install branch — fires ONLY when ALL hold:** no handoff loaded
(established above), AND `$HOME/.claude/.coordinator-fresh-install` exists. Consume (delete) the
sentinel BEFORE emitting anything, so this never re-fires on a later no-handoff session, then emit
the fresh-install message: points at `~/.claude` as the live install to evolve (not the upstream
`coordinator-claude` source), the onboarding handoff if present, fallback first steps (co-write
`CLAUDE.md`, `/repo-setup` the first project, `/workday-start` daily). Sentinel lifecycle detail:
wiki.

**Otherwise, the standard work menu** — each option loads its own context once picked:

1. **Implementing** — find/read the relevant plan doc; summarize the first step.
2. **Fixing a bug** — identify the failing test/error/repro; read the relevant source.
3. **Reviewing** — identify the target (commits/files/PR); load review criteria.
4. **Research / exploration** — ask what to explore; no ceremony.
5. **Maintenance** — daily health check, weekly audit, or debt triage.
5a. **Strategy/ceremonies** — `/shape`, `/goal-setting`, `/roadmap-planning`, `/spike` (mechanism
    derisking; PM-gated, never EM/subagent-initiated — gating: `spike/SKILL.md` § Invoke Gating,
    pipeline position: wiki)
6. **Work the backlog** — central (`coordinator-state-root.py --central`) and local
   `state/improvement-queue/*.yaml`, surface depth; `state/bug-backlog/*.yaml` ≥10 open P1/P2, or
   any `status: open` in `state/cross-repo-commitments/`, → advocate `/bug-blitz` (skip silently
   if absent/empty).

   **Red-suite predicate — independent of backlog depth.** Read `state/test-red/<machine-local get
   coordinator.machine_slug>.yaml` if present (absent/malformed → skip silently, no error). Per
   tier, compute the delta against the comparison baseline (`acknowledged.baseline` when live and
   unexpired, else `previous.failing`), and advocate `/bug-blitz` — **naming the tier and
   surfacing the delta counts, never a bare "the suite is red"** — on any of:
   - `new` non-empty → "{tier}: N new failures since the acknowledged baseline" (or "since the
     last run", unacknowledged).
   - `acknowledged` null/voided (independent of whether `new` is also non-empty) AND `failing[]`
     non-empty: **void-on-doubt** (owner unresolvable/unparseable/missing baseline) → "{tier}:
     acknowledgement void: owner `<path>` unresolvable — M failing, unacknowledged." **void-on-
     expiry** (`ran_at` past `expires_at`) → "{tier}: acknowledgement expired `<date>`, owner
     `<path>` still open — M failing." **no acknowledgement at all** → "{tier}: M unacknowledged
     failures."
   - the acknowledged owner artifact is closed/terminal while `failing[]` is still non-empty →
     "{tier}: owning work `<path>` closed but M failures remain."
   - `failing` is `null` → "{tier}: red, failing set unavailable" — never read as clean, never
     folded into a delta.

   An acknowledged, unexpired red set whose delta is all-`persistent` advocates nothing from this
   predicate — correct silence, not a gap. Never runs the test tier itself, never blocks on it —
   only reads the record the engine's emitter already wrote.
   <!-- engine-gap: field=test_red.advisory producer=unknown memo=2026-08-14-doe-claude-em-three-cut-obligations-from-the-corpus-grind.md -->
7. **Other** — ask the user to describe it; load relevant context.

`$ARGUMENTS` provided → use it directly, skip the menu. Surface the tracker's ready/executing
items and project-specific plan docs (`docs/`, `tasks/`, `tasks/plans/`) as concrete options, not
generic categories. A fresh backlog item or ad-hoc ask with no sizing-object yet routes through
`coordinator:sizing` first.

### Status report

Briefly (2 lines): repo state (uncommitted changes may be a peer's), current branch. Orientation,
not ownership.
<!-- engine-gap: field=session.repo_status_summary producer=unknown memo=2026-08-14-doe-claude-em-three-cut-obligations-from-the-corpus-grind.md -->
