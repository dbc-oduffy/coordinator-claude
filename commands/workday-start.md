---
name: workday-start
description: "Morning orient — triage handoffs, surface staleness, align priorities."
allowed-tools: ["Read", "Write", "Grep", "Glob", "Bash", "Agent"]
argument-hint: "[optional day focus]"
---

# Workday Start — Morning Orientation

**Announce:** "Running workday-start to prepare the day's context."

`orient-assemble brief --cadence day` computes the cadence-invariant orient spine in one pass (same
computation `workstream-start`/`workweek-start` name for their own cadences). `directives[]`
execute unconditionally, rendering `detail` into the matching Morning Briefing section;
`judgment_points[]` are EM/PM calls, resolved before their gated directive, never auto-picked;
`narration`/`next_move` surface verbatim when non-empty. Everything below is residue the op doesn't
compute.

**Advisory-probe convention:** most steps run a bare-named CLI; empty output/exit 0 means clean and
skips silently, non-empty (or a stated exit code) renders under the named heading. Stated once.

## Step -1 / -0.45 / -0.4 — Hygiene

Reaper first, log to file, don't echo into the briefing: `workday-start-day-branch-resolve
reap-log`. Then heal git hooks, idempotent, note only on actual repair:
`coordinator-ensure-prepare-commit-msg-hook`, `coordinator-ensure-post-commit-hook`,
`install-meta-repo-precommit-hook "$HOME/.claude"`. Then `untested-platform-advisory`, relay
verbatim.

## Step 0: Branch Setup

**Reconcile with origin/main daily, never rotate.** Canonical branch or a PM-authorized long-lived
bus. `workday-start-step0` handles sync + the precedence switch + reconcile; off-daily ref ops need
`COORDINATOR_OVERRIDE_BRANCH=1 COORDINATOR_OVERRIDE_BRANCH_REASON="workday-start step 0 <action>"`.
Surface both stdout lines. Exit `0` success; `2` `STALE-NEEDS-ABC` → conflict flow below; `3`
`RECONCILE-CONFLICT` → PM; `1` → halt. Not EM-skippable beyond the script's own reported outcomes
(`IN-SPAN`/`NAMED-WORKSTREAM`/`FRESH-CUT`).

**Span assertion:** `d-branch-span-mismatch` fires → top-line `### Branch Span Mismatch`, above
`### Context Freshness`. Never auto-rename.

**Conflict** (`git merge --no-ff` fails): abort, name each branch. Interactive — hard-block for PM:
**A** consolidate (`/consolidate-git`); **B** defer (`tasks/.deferred-branches.md`: `{branch} |
reason | re-check:{+7d} | deferred-by`); **C** archive+push+delete-old-ref. Non-interactive:
auto-defer, force A/B/C next interactive run.

## Step 0.5 / 0.6 / 0.7 / 0.8

`orphan-branch-sweep --format text --severity-min warning`: CRITICAL → `### Orphan Sweep`
(branch, PR#, post-merge commits), investigate-first; WARNING → same section, open-a-PR nudge.
Render after `### Alignment Check`, before `### Priority Suggestions`.

`d-worktree-reap-*` directives — execute the named `agent-worktree-sweep --reap` as reached; dirty
non-benign worktrees raise a judgment point, never hand-classified. `### Agent Worktrees` only when
something fired.

`normalize-consumed-frontmatter` — idempotent frontmatter/status sync. Stale-executing-plan
directive — surface `detail`, triage implemented/abandoned/pick-back-up. Surface
`tasks/orphan-sweep-notes.md` if present, rotate via `workday-start-handoff-triage trim-notes`.

## Step 1: Handoff Triage

Actionable-now/awaiting-gate triage are Step -0.9 directives (`d-handoff-triage-*`) — surface
`detail`, don't re-query.

**1.1** Route on `kind:` — `spinoff`/`spinoff-roadmap` → "Spinoffs awaiting pickup" (cluster by
`roadmap_id:` when count > 3); `session-handoff`(or absent)/`recovery` → "Continuation handoffs"
(`recovery` suffixed).

**1.2** Any `awaiting_gate` → "Gated handoffs" (titles + gate_dependency); >6d → stuck-gate flag.
`draft-plan-aging docs/plans`: exit `1` → "Stale draft plans" + decision prompt; any other non-zero
→ stderr verbatim, never dropped.

**1.3 Git reconciliation (mandatory before declaring any item actionable):** no CLI derives "closed
since this handoff was written" from commit history — treat every `ready_to_fire` item as
unverified rather than hand-deriving closure. Degraded pending an engine producer.

**1.4** `query-completions --where "created>=<30d ago>" --sort created --format json` (legacy
fallback: `archive/completed/legacy/<YYYY-MM>.md`) — match on workstream/feature/commit-hash/
keyword, flag likely-shipped items.

**1.47/1.473/1.475** In order, idempotent, safe every run: `sweep-shipped-handoffs`,
`promote-shipped-in-flight-stubs` (must precede the reaper, so a shipped deliverable isn't mistaken
for a crash orphan), `d-reaper-orphaned-handoffs` (Step -0.9; dry-run then live). Surface verbatim
under `### Handoffs`. Reaper never touches frontmatter directly — releases a dead holder's claim to
the pool, never abandons/archives.

**1.5** _"{N} actionable ({K} continuations, {S} spinoffs incl. {R} roadmap in {G} groups). {G}
awaiting_gate ({M} >6d). {X} verified-closed."_ Omit zero clauses.

## Step 1.45: Cross-Repo Memos

Inbound-memo judgment points (`j-memo-*`) — resolve Accept/Decline/Surface-to-PM before proceeding.

**Route-to-baton default:** any memo/finding/triage item inside an active handoff's scope gets a
routing note appended (`## Routed from inbox triage (<date>)`) and committed with pathspec, as a
matter of course, then closed: `archive-stamp-cli resolve-memo <memo> --decision accepted
--decision-note "routed into <baton>" --realized-by "<baton>" --in-repo-capture "<baton>"`. Stays
open: capture didn't land, or an unanswered PM question.

`workday-start-cross-repo-memo-outbox-surface` — outbox drafts awaiting send.

**1.45a Inbox blitz:** `workday-start-inbox-blitz-assemble` routes on `state`: `skipped`/
`inventory` (plain roster stands)/`escalate` (open-count or oldest-age over threshold — surface
counts, run the blitz). On `escalate`, dispatch one Sonnet agent per `dispatches[]` entry, `brief`
and `memos[]` passed **verbatim**, never paraphrased. `supersession_candidates[]` are candidates,
never confirmations. Group PLAN-WEIGHT items by problem/solution space, one baton per space,
routed via the default above.

There is deliberately no `/inbox-blitz` skill (skill-accumulation aversion) — do not re-house
this.

## Step 1.5x — 1.11: Advisory Rollup

Each: named CLI, non-empty/stated-exit-code surfaces under its heading, else silent.

- **1.55** `records_query.py completion "nature=roadmap" markdown-list 10 --sort "-loe.tshirt" --since 90d` → `#### Recent roadmap (last 90d, top-10)`, `(none)` on zero, heading always present.
- **1.6** `workday-start-advisory-counters improvement-queue` → notable at central ≥5/oldest
  >14d/`recurring≥3`/local ≥1 (judgment, not a trigger). Also cross-repo-commitments open count ≥1.
- **1.65** `query-records --type bug --where 'severity in (P1,P2) AND status=open'` → ≥10
  `/bug-blitz` suggestion, ≥20 stronger nudge.
- **1.66 Test-red delta:** `state/test-red/<machine>.yaml`; absent/malformed → silent (pending the
  emitter). `failing` tri-state — `[]` authoritative-clean, `null` red-but-undeterminable, never
  green/`cleared`. Baseline: `acknowledged.baseline` if unvoided else `previous.failing`; VOID
  (owner unresolvable, or `expires_at` past) → full current red set. One line per cause (`new`,
  void-on-doubt, void-on-expiry, unacknowledged, owner-closed-but-red, `failing:null`), never
  collapsed. All-`persistent` under a live ack → silent. Never run the test tier here; never block
  the ceremony on this step's outcome.
- **1.7** Glob 4 `*-recheck-due-*-YYYY-MM-DD.md` families → due-today suggestion, due-within-7d
  heads-up. PM-actioned, never auto-executed.
- **1.72** `check-provisional-expiry.py docs/plans` — expired `provisional_until:`/`revisit_by:` →
  ratify/extend/flip-terminal prompt. Read-only — never auto-resolves a flagged plan.
- **1.75** `central-run-due` — `[universal]` volume over threshold (150) → Priority Suggestion w/
  per-repo breakdown. Read-only, PM-actioned — never auto-dispatch a central run.
- **1.8** `verify-snippet-sync project-rag-preamble` — MISMATCH/MISSING_END → **Preamble Drift**;
  never auto-fix.
- **1.82** No detector CLI for CLAUDE_PLUGIN_ROOT source-guard drift — degraded, no check this cadence.
- **1.85** `workday-complete-backfill-scan --lookback 7` — commits-but-no-summary gap → **Daily-Wrap
  Coverage**. Read-only, never auto-backfills — trivial-only days are an EM skip call.
- **1.86** `workday-start-reconcile-sweep` (today + prior day only) → **Completion Reconcile**,
  detect-only.
- **1.9** `workday-start-advisory-counters push-failures` (`recent_24h≥1`/`total≥5`) → `### Auto-Push
  Health`; cleanup `> .git/push-failures.log` (truncate, never delete).
- **1.91** `... local-ahead` (`ahead_count≥1`) → `### Local-Only Branch Warning`; recover `git push
  origin <branch>`, GH007 fix `git config user.email '<id>+<user>@users.noreply.github.com'`.
- **1.92** `... stale-stashes` → `### Stale Stashes`, then `advice` verbatim — leads with the safe
  forward action, never a scold (a stash may hold a sibling's only copy of real work). Read-only,
  never `pop`/`apply`/`drop`.
- **1.11** `cruft-sweep --class all --dry-run --quiet` — >1GB reclaimable or >14d stale → one-line
  surface. PM-actioned, never auto `--apply` (already runs in `/workday-complete`).

## Step 1.10: Addon Health Sentinels

Heal `~/.claude` structure drift first (idempotent, additive-only):
`coordinator_core.install.scaffold_structure --root "$HOME/.claude" --manifest-root
"$CLAUDE_PLUGIN_ROOT"`. Then `coordinator-doctor-sentinel --full` (writes the sentinel, silent
GREEN, brief AMBER/RED). The health scan itself is a Step -0.9 `d-addon-health-*` directive —
render `detail` under `### Addon Health`.

Append to the same section, non-empty only: `check-plugin-drift.py` (live-install git/venv drift);
`check-claude-klabauter-doctor-sentinel` (engine health); `check-engine-drift` (checkout freshness);
`check-forwarder-drift` (derived-vs-installed CLIs, both directions); `check-deferral-orphan-memo`
(unowned aged ask/proposal); `check-deferral-partial-strangle` (partial-strangler); `check-global-doctrine-mirror
2>&1` (byte-compare `~/.claude/CLAUDE.md` vs. `global-doctrine/`, remediate `--sync`
mirror→`~/.claude` only, after re-authoring in the tracked mirror). All silent-skip when the engine
root/op is unresolvable — a fleet-topology fact, never a health regression.

**1.10.5** MCP registration: per `~/.claude.json mcpServers` entry, skip disabled/off-project,
count `mcp__<server>__` matches; 0 → `### MCP Tool Registration` line + `/<server>:doctor`.

**1.10.6** `handoff.reconcile_open` is a Step -0.9 judgment point, resolved like any other, never
rubber-stamped. `### Auto-Reconcile`, after `### Addon Health`.

**1.10.64** `workday-start-health-probes observer-sidecar-scan --dir archive/daily-summaries` —
mirrors the 1.11 WARN shape, naming dates.

**1.10.7** `bin/check-fixture-sync.sh` if present/executable — exit 1 `FIXTURE DRIFT:` under
`### Cross-Repo Fixture Sync`, re-pin via `cross-repo-memo`, never a direct sibling edit.

**1.10.9** `d-claude-klabauter-bin-sentinel` (Step -0.9) → `### Coordinator-Bin Sentinel` when fired.

## Step 2 / 3 / 3.5: Freshness Checks

No CLI yet derives commit-delta staleness for docs, tests, or the bug sweep from git history —
degraded pending engine producers on all three:
- Doc freshness: `check-harvest-debt` alone, surface verbatim if non-empty (flag only, never
  auto-run `/distill`).
- Test staleness: skip this cadence.
- Bug-sweep staleness: `state/bug-backlog/.meta.yaml` date signal only (no commit-count trigger) —
  no backlog and >50 tracked source files suggests a first sweep.

**3.6** `d-rag-staleness-regen` (Step -0.9) → **Project-RAG** line when fired. Flag-only, PM
invokes manually (a reindex can race an open editor).

## Step 4: Priority Alignment

`whats-next` → § Priority Suggestions as-is. Reconcile against the Step 1.4 completed-archive query
— fuzzy match to a tracker Ready/Executing row or open handoff flags _"Tracker shows [X] as
[status], but archive/completed records it shipped [date]."_ Unsure → "possible match — verify,"
never auto-resolved. Report under **Alignment Check**.

## Step 5: Morning Briefing

```markdown
## Good Morning — Workday Start

**Date:** YYYY-MM-DD | **Branch:** [current]

### Branch Span Mismatch
_(Only if Step 0's span-assert fired — verbatim, above Context Freshness.)_

### Context Freshness
Handoffs / Docs / Tests / Bug backlog / Bug sweep / Cross-repo commitments (omit if empty) /
Project-RAG (omit if current) / Tools — one line each.

### Tool Availability
`scc`/`shellcheck` PATH check, install hint per missing tool; silent if both present. **Fan-out:**
`fan-out-dispatch.py` — compiled wave, EM-serial commit — for any multi-chunk dispatch.

### Handoffs
Continuation / Shipped sweep / Spinoffs awaiting pickup / Stale spinoffs (≥14d) — each omitted if
empty.

#### Recent roadmap (last 90d, top-10)
_(Step 1.55 rows; "(none)" on zero; heading always present.)_

### Alignment Check
Mismatches or "all aligned" — each names tracker status + archive ship date.

### Orphan Sweep / Agent Worktrees / Auto-Push Health / Addon Health / Test-Red Delta
Each section omitted unless its own step produced findings.

### Priority Suggestions
Bugs first, then stale sweep/tests, tracker Ready rows, deep debt backlog — by urgency.

### What should today's focus be?
Tracker Ready items, handoff action items, PM-facing options.
```

Per suggestion (outside the fence, avoiding nested-fence parse failure): `append-goal-event
--period day --period-value <today> --text "<suggestion>"`.

**Marker:** `d-workday-marker-write` (Step -0.9) — write `state/.workday-start-marker` once
complete; `/workstream-start` checks this file.

## Step 5.5 / 5.6

Generate `state/orientation_cache.md` (40-60 lines, SessionStart hook injects it instead of raw
repomap content); skip if `tasks/` absent. Full derivation: wiki.

`d-ceremony-hook-output` (Step -0.9) — print verbatim as a standalone trailing line, after the
briefing (this ceremony's summary settles before this step, unlike the other three). Silent no-op
absent a `workday_start_post_command:` key in `coordinator.local.md`.

## What This Does NOT Do

Bug-sweep / daily-code-health / deep-architecture-survey / update-docs (dedicated invocations).
Merge to main. Choose work (`/workstream-start`'s Engage section).

## Relationship & Concurrent Safety

Once/day; `/workstream-start` skips redundant checks on a fresh marker. `/workday-complete` is the
evening counterpart. `/update-docs` and `/bug-sweep` are recommended, never auto-dispatched from
here — a PM call. Read-only except `state/.workday-start-marker`. Avoid acting on a stale item a
concurrent session already shipped — Step 1.3 is the (currently degraded) prevention.

If `$ARGUMENTS` is provided: _"Requested focus: {arguments}"_
