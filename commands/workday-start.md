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

**Batching convention:** every step below that lists more than one CLI names them as ONE shell
invocation — run them together in a single tool call, in the listed order, and route each
command's own output to its own heading. Only a step whose exit code gates the next step (Step 0)
stays solo.

**Weekly-cadence convention:** several steps below run weekly, not daily, gated on a marker file's
mtime rather than a spawn: `state/.workday-start-weekly-marker` (single shared marker for the
group). If its mtime is within 7 days, skip the whole group silently; otherwise run it and touch
the marker.

## Step -1 / -0.45 / -0.4 — Hygiene

One shell call: `workday-start-day-branch-resolve reap-log` (log to file, don't echo into the
briefing), then `coordinator-ensure-hooks-fleet` (both hooks, EVERY registered repo — the per-repo
`coordinator-ensure-*-hook` entrypoints heal only the cwd repo, leaving the rest of the fleet
silently un-pushed and un-trailered — idempotent, note only on actual repair), then
`install-meta-repo-precommit-hook "$HOME/.claude"`, then
`python3 <plugin-root>/bin/check-gitignore-template-drift.py` (report-only; renders its output under
the advisory-probe convention — the `/coordinator:install` Phase 4 diff only fires on a full
install, so this is the daily cadence that catches drift between installs;
see `coordinator/docs/wiki/coordinator-tripwires/gitignore-template-drift-is-a-cadence-gate-not-an-install-only-step.md`),
then `python3 <plugin-root>/bin/check-watch-state-gitignore-fleet.py` — the per-repo twin,
report-only, never untracks
(`…/tripwire-registry/a-setup-time-gitignore-block-never-reaches-a-repo-onboarded-before-it.md`).

`untested-platform-advisory` moves to the install surface — it changes only on new-platform
install, never on a normal morning. Not part of this ceremony.

## Step 0: Branch Setup

**Reconcile with origin/main daily, never rotate.** Canonical branch or a PM-authorized long-lived
bus. `workday-start-step0` handles sync + the precedence switch + reconcile; off-daily ref ops need
`COORDINATOR_OVERRIDE_BRANCH=1 COORDINATOR_OVERRIDE_BRANCH_REASON="workday-start step 0 <action>"`.
Surface both stdout lines. Exit `0` success; `2` `STALE-NEEDS-ABC` → conflict flow below; `3`
`RECONCILE-CONFLICT` → PM; `1` → halt. Not EM-skippable beyond the script's own reported outcomes
(`IN-SPAN`/`NAMED-WORKSTREAM`/`FRESH-CUT`). Runs solo — its exit code gates everything after it.

**Span assertion:** `d-branch-span-mismatch` fires → top-line `### Branch Span Mismatch`, above
`### Context Freshness`. Never auto-rename.

**Conflict** (`git merge --no-ff` fails): abort, name each branch. Interactive — hard-block for PM:
**A** consolidate (`/consolidate-git`); **B** defer (`tasks/.deferred-branches.md`: `{branch} |
reason | re-check:{+7d} | deferred-by`); **C** archive+push+delete-old-ref. Non-interactive:
auto-defer, force A/B/C next interactive run.

## Step 0.5 / 0.7 / 0.8

**0.5 `orphan-branch-sweep`** moves to the weekly group (below) — a branch orphaned overnight is
not urgent.

**0.6 `agent-worktree-sweep --reap`** is inert in this repo — no git worktrees run here
(`CLAUDE.md`). Skip its execution only; the step stays in the shipped ceremony for repos that do
use worktrees.

One shell call: `normalize-consumed-frontmatter` (idempotent frontmatter/status sync — surface the
stale-executing-plan directive's `detail`, triage implemented/abandoned/pick-back-up; surface
`tasks/orphan-sweep-notes.md` if present), then `workday-start-handoff-triage trim-notes` (rotates
the same notes file).

## Step 1: Handoff Triage

Actionable-now/awaiting-gate triage are Step -0.9 directives (`d-handoff-triage-*`) — surface
`detail`, don't re-query.

**1.1** Route on `kind:` — `spinoff`/`spinoff-roadmap` → "Spinoffs awaiting pickup" (cluster by
`roadmap_id:` when count > 3); `session-handoff`(or absent)/`recovery` → "Continuation handoffs"
(`recovery` suffixed).

**1.2** Any `awaiting_gate` → "Gated handoffs" (titles + gate_dependency); >6d → stuck-gate flag.
`draft-plan-aging docs/plans` moves to the weekly group — precondition it further there on
`docs/plans` having ≥5 entries; skip the spawn entirely below that.

**1.3 Git reconciliation (mandatory before declaring any item actionable):** no CLI derives "closed
since this handoff was written" from commit history — treat every `ready_to_fire` item as
unverified rather than hand-deriving closure. Degraded pending an engine producer.

<!-- engine-gap: field=handoffs.ready_to_fire_commit_closure producer=unknown memo=2026-08-27-claude-klabauter-em-doe-unmarked-obligations-and-four-lost-markers.md -->

**1.4** `query-completions --where "created>=<30d ago>" --sort created --format json` (legacy
fallback: `archive/completed/legacy/<YYYY-MM>.md`) — match on workstream/feature/commit-hash/
keyword, flag likely-shipped items.

**1.47** One shell call, in this order (idempotent, safe every run): `sweep-terminal-handoffs`,
`promote-shipped-in-flight-stubs` (must precede the reaper, so a shipped deliverable isn't mistaken
for a crash orphan — ordering preserved inside the batch), `reap-orphaned-in-flight-handoffs` (Step
-0.9; dry-run then live), `handoff-housekeeping`. Surface verbatim under `### Handoffs`. Reaper
never touches frontmatter directly — releases a dead holder's claim to the pool, never
abandons/archives.

**This is the on-demand drain, not the owner.** The abandoned-session case — a session that dies
mid-close and never stamps its baton — belongs to the `/workday-complete` spine's
`reap-orphaned-in-flight-handoffs` + `handoff-housekeeping` pair, which reclaims dead-holder claims
and archives everything terminal in one batch. This step covers the same population on demand, so
that residue does not wait on the day's close. **`session.boot_sweep` is not behind either** — its
archival composite was killed (`sweep-boot.py` carries `never dispatches an op` as a negative spec).
Skipping this step is survivable; skipping `/workday-complete` is what lets residue accumulate.
Measured 2026-08-30: five terminal batons unswept and the gem-01 roadmap reading seven batons behind
its real state, on a stretch where `/workday-complete` had not run.
→ `coordinator/docs/wiki/coordinator-tripwires/terminal-batons-are-swept-at-close-not-left-to-the-next-ceremony.md`

**1.5** _"{N} actionable ({K} continuations, {S} spinoffs incl. {R} roadmap in {G} groups). {G}
awaiting_gate ({M} >6d). {X} verified-closed."_ Omit zero clauses.

## Step 1.45: Cross-Repo Memos

Inbound-memo judgment points (`j-memo-*`) — resolve Accept/Decline/Surface-to-PM before proceeding.

**Route-to-baton default:** any memo/finding/triage item inside an active handoff's scope gets a
routing note appended (`## Routed from inbox triage (<date>)`) and committed with pathspec, as a
matter of course, then closed. Batch closures: pass every routed memo's ID to a single
`archive-stamp-cli resolve-memo <memo1> <memo2> ... --decision accepted --decision-note "routed
into <baton>" --realized-by "<baton>" --in-repo-capture "<baton>"` call rather than one process per
memo, when `archive-stamp-cli` accepts a list; fall back to one call per distinct baton (not per
memo) otherwise. Stays open: capture didn't land, or an unanswered PM question.

`workday-start-cross-repo-memo-outbox-surface` runs only when `cross-repo/outbox/**` is non-empty
(glob-count precondition, no process cost to check) — outbox drafts awaiting send.

**Dispatch authorization — invoking this skill IS the request.** The dispatches named below are constitutive steps of this skill, not a separate thing to get cleared: invoking a skill requests the actions that skill performs. A harness line permitting dispatch "unless the user requested it" is therefore **satisfied here, not overridden** — no precedence claim is needed and none is made. Re-asking spends the very context the dispatch exists to protect. The rule attaches to skill entry and dissolves no PM-authored gate: keyword-gated skills gate entry, and every gate a skill names for itself still binds — per-session cross-repo-commit assent, ask-before-external-action, and any other this skill's own body names. Tripwire: `UNATTRIBUTED-HARNESS-LINE-IS-NOT-PM`.

**1.45a Inbox blitz — the inbox ends every morning at zero.** **Every open memo is triaged,
verified, and disposed of in the same day's run, however many agents that takes.** Disposal means
closed, or routed into a baton and then closed — a baton is a disposal, not a deferral. The inbox
is a delivery surface, never a backlog: an item still sitting open when the ceremony ends did not
get triaged, whatever else was written about it.

`workday-start-inbox-blitz-assemble`'s `state` sizes the response, never whether items are left
open. `escalate` (open-count or oldest-age over threshold) means surface the counts and fan out;
`inventory` means the day's clear-down is small enough to run inline or on one agent — it is not
a licence to leave a roster standing. `skipped` means the inbox is already empty; nothing to do.

There is no cap on agent count: an inbox that accreted for a fortnight is exactly the case the
blitz exists for, and a bound that leaves part of it untouched re-queues the accretion it was
dispatched to end. A small inbox gets the same rule for the opposite reason — ten memos left open
because ten is under a threshold is how the fortnight's accretion starts.

**Size the fan-out from volume, not from a fixed number.** ~30 memos per triage agent is the
working grain — enough context to see threads across a bucket, small enough to read each memo in
full. Where a `dispatches[]` bucket exceeds that, shard its `memos[]` across as many agents as
the count needs and give every shard the same bucket `brief` verbatim; `brief` and `memos[]` are
passed **verbatim** to every agent, never paraphrased, sharded or not.

**A verify pass rides with its triage and is never the thing that gets dropped.** Each triage
shard's verify pass is part of that shard, not a separate item competing for budget — an
unverified triage report is the failure mode the blitz is built to avoid, since a triage pass
routinely refutes or shrinks a large share of its own findings. Ship both or ship neither.

**Two checks the EM adds to every verify brief, on top of whatever `brief` the op ships.** Both
are failure modes of the verify pass itself, not of any memo, so a verifier that omits them
returns confident wrong answers rather than fewer answers:

- **Already-answered, not just accurate.** Confirming a memo's *claim* is not confirming its
  *ask* is open. Before any verdict, glob the archives on both sides — `cross-repo/archive/`,
  `state/memo-outbox/sent/`, the completions record — for a later memo, resend, or commit that
  discharges it. `AN-ANSWERED-ASK-IS-CLOSED-WHATEVER-ITS-BODY-SAYS` governs the verify pass, not
  only the triage pass's PLAN-WEIGHT rating.
- **Absence is only evidence from the right directory.** "Not in their inbox" is not "never
  delivered" — a delivered memo that gets actioned necessarily *leaves* the inbox. Before
  reporting anything missing, name the directory it would be in if it existed and confirm you
  looked there. The send path is `state/memo-outbox/sent/` plus the ledger; a stale sibling
  directory is residue, never a queue.

**A manifest is a snapshot; the tree moves under it.** Peer sessions archive and close memos
mid-run. An assigned memo that is no longer where the manifest says is a race, not a producer
defect — check the archival commit's timestamp against the assemble's before reporting one.
Tripwires: `A-VERIFY-PASS-THAT-SKIPS-THE-ARCHIVE-CONFIRMS-A-DEAD-ASK`.

**Dispatch in waves, not one simultaneous batch.** The machine carries a dozen-plus concurrent EM
sessions; a 25-agent fan-out fired at once is a machine-wide event. Run triage shards in waves
sized to what the box will carry, each shard's verify following its own triage. Wave structure
paces the grind — it never truncates it.

`supersession_candidates[]` are candidates, never confirmations. Group PLAN-WEIGHT items by
problem/solution space, one baton per space, routed via the default above — that per-space rule governs PLAN-WEIGHT only: **every XS/S item from one blitz
bundles into one baton**, never one each. The standing "classification is a claim at memo-send
time" caveat covers cited *defects*; an **ask** is already-answered as often as a defect is
already-fixed, so before rating one PLAN-WEIGHT glob the sender's `cross-repo/archive/`: a reply
sitting `actioned` there closes the ask whatever its body says. Tripwires:
`SMALL-BLITZ-ITEMS-BUNDLE-INTO-ONE-BATON`, `AN-ANSWERED-ASK-IS-CLOSED-WHATEVER-ITS-BODY-SAYS`,
`A-BLITZ-THAT-LEAVES-MEMOS-UNTRIAGED-DID-NOT-RUN`, `THE-INBOX-ENDS-EVERY-MORNING-AT-ZERO`.

There is deliberately no `/inbox-blitz` skill (skill-accumulation aversion) — do not re-house
this.

## Step 1.5x — 1.11: Advisory Rollup

Each: named CLI, non-empty/stated-exit-code surfaces under its heading, else silent.

- **1.55** `records_query.py completion "nature=roadmap"` top-10 rollup is KILLED from the daily —
  pull a recent-roadmap view on demand instead.
- **1.6** `workday-start-advisory-counters` — batched below with 1.9/1.91/1.92.
- **1.65** `query-records --type bug --where 'severity in (P1,P2) AND status=open'` is KILLED from
  the daily — permanently tripped, so it carries no signal. `/bug-blitz` is the on-demand path.
- **1.66 Test-red delta:** `state/test-red/<machine>.yaml`; absent/malformed → silent (pending the
  emitter). `failing` tri-state — `[]` authoritative-clean, `null` red-but-undeterminable, never
  green/`cleared`. Baseline: `acknowledged.baseline` if unvoided else `previous.failing`; VOID
  (owner unresolvable, or `expires_at` past) → full current red set. One line per cause (`new`,
  void-on-doubt, void-on-expiry, unacknowledged, owner-closed-but-red, `failing:null`), never
  collapsed. All-`persistent` under a live ack → silent. Never run the test tier here; never block
  the ceremony on this step's outcome. Read directly (no spawn).
- **1.7** Glob 4 `*-recheck-due-*-YYYY-MM-DD.md` families → due-today suggestion, due-within-7d
  heads-up. PM-actioned, never auto-executed. Glob only — no spawn.
- **1.72** `check-provisional-expiry.py docs/plans` moves to the weekly group.
- **1.75** `central-run-due` moves to the weekly group.
- **1.8** `verify-snippet-sync project-rag-preamble` moves to the weekly group, with an added
  cheap precondition: run it early when Step 0's already-reported changed-path set includes
  `coordinator/snippets/`, else defer to the weekly cadence. Read that set from Step 0's own
  output; it is not a fact this step establishes for itself.
- **1.82** No detector CLI for CLAUDE_PLUGIN_ROOT source-guard drift — degraded, no check this cadence.

<!-- engine-gap: field=plugin_root.source_guard_drift producer=unknown memo=2026-08-27-claude-klabauter-em-doe-unmarked-obligations-and-four-lost-markers.md -->
- **1.85** `workday-complete-backfill-scan --lookback 7` moves to the weekly group — the 7-day
  window re-scans the same days every morning; 6 of every 7 runs are definitionally redundant.
- **1.86** Completion Reconcile is KILLED from `/workday-start` — `workday-start-reconcile-sweep`
  and the `reconcile-completion-commits` worker it dispatched are both `retired` in the engine
  repo's relocation ledger; the step invokes nothing. The requirement (recording
  `Session-Id:`-trailer commits against a pending-release completion entry) is a live rebuild
  candidate in the engine's kill-ledger, so restore the step only when a successor CLI ships.
- **1.9 / 1.91 / 1.92** Batched into the single `workday-start-advisory-counters` call below.
- **1.11** `cruft-sweep --dry-run` is KILLED from `/workday-start` — it already runs in
  `/workday-complete`, and the skill body has always said so. Reclaimable disk surfacing in the
  evening instead of the morning is not a capability loss; a >1GB accumulation does not become
  urgent within one working day.

**Batched counters (1.6 + 1.9 + 1.91 + 1.92), one shell call:**
`workday-start-advisory-counters improvement-queue`,
`workday-start-advisory-counters push-failures`, `workday-start-advisory-counters local-ahead`,
`workday-start-advisory-counters stale-stashes` — four subcommands of one already-loaded script,
run together instead of as four cold starts.
- improvement-queue: notable at central ≥5/oldest >14d/`recurring≥3`/local ≥1 (judgment, not a
  trigger). Also cross-repo-commitments open count ≥1.
- push-failures: `recent_24h≥1`/`total≥5` → `### Auto-Push Health`; cleanup `> .git/push-failures.log`
  (truncate, never delete). **These counters and the `local-ahead` recovery hint below survive the
  no-ceremony-instructs-a-push ruling deliberately: a health report is an observation, a checkpoint
  is an instruction.** Push handles itself, and a push that has stopped handling itself is exactly
  what nothing else would surface here.
- local-ahead: `ahead_count≥1` → `### Local-Only Branch Warning`; recover `git push origin
  <branch>`, GH007 fix `git config user.email '<id>+<user>@users.noreply.github.com'`.
- stale-stashes: → `### Stale Stashes`, then `advice` verbatim — leads with the safe forward
  action, never a scold (a stash may hold a sibling's only copy of real work). Read-only, never
  `pop`/`apply`/`drop`.


**Maintenance checkpoint — `git.maintenance` daily tier.** Advisory, non-zero reported, ceremony
continues:

`& "$env:COORDINATOR_SETTINGS_HOME\bin\coordinator-invoke.exe" git.maintenance '{"tier":"daily","repo":"<repo-root>"}'`

Shape W above / Shape A/B POSIX — `snippets/resolve-coordinator-bin.md`. `--repo` flag refused
(`scope='none'`); `repo` goes in the JSON params, not omitted.

## Step 1.10: Addon Health Sentinels

`coordinator-doctor-sentinel --full` (writes the sentinel, silent GREEN, brief AMBER/RED) stays
daily. The health scan itself is a Step -0.9 `d-addon-health-*` directive — render `detail` under
`### Addon Health`.

**Batched probes, one shell call:** `check-plugin-drift.py` (live-install git/venv drift),
`check-claude-klabauter-doctor-sentinel` (engine health), `check-engine-drift` (checkout freshness),
`check-forwarder-drift` (derived-vs-installed CLIs, both directions), `check-deferral-orphan-memo`
(unowned aged ask/proposal), `check-deferral-partial-strangle` (partial-strangler),
`check-global-doctrine-mirror 2>&1` (byte-compare `~/.claude/CLAUDE.md` vs. `global-doctrine/`,
remediate `--sync` mirror→`~/.claude` only, after re-authoring in the tracked mirror),
`workday-start-health-probes observer-sidecar-scan --dir archive/daily-summaries` (mirrors the
same WARN shape, naming dates), and `corpus-currency-probe.py` (per landed
`.project-rag-corpus-store/<band>/`, is the local manifest triple behind the declared publish
ref?) — nine named CLIs, one shell invocation, each rendering into `### Addon Health` only when
non-empty. All silent-skip when the engine root/op is unresolvable, or (for the corpus probe)
when the repo has no landed store — a fleet-topology fact, never a health regression. No
multiplexer CLI for these nine exists today; this is the interim shell-level batch, not a new
engine CLI — do not invent one here, that surface is engine-owned, not this skill's to add.

**Memo-outbox tracking.** `python <plugin-root>/bin/memo-outbox-tracking-guard.py` — delivered memos
losing their sender-side record. Exit 1 renders under `### Addon Health`. Daily, because leg 2
fires while a phantom staged deletion is still armed. Repair a leg-1 finding, then record its sha
in `state/memo-outbox/acknowledged-sweeps.json`. Read the module docstring before touching the leg
order.

**Boot currency dependency:** `coordinator-doctor-sentinel --full` above writes P-19's verdict to
`~/.claude/plugins/coordinator-claude/data/doctor-last-run.json`, the only cache
`install_currency_banner()` reads at boot (zero-spawn). `corpus-currency-probe.py` in the same
batch carries the identical dependency shape: it writes `corpus-currency-last-run.json`, and
`corpus_currency_banner()` is the only thing that reads it at boot. Drop or reorder either
sentinel run and its boot line doesn't go quiet — it degrades to `stale-unknown` past the 24h
refresh window.
`<ENGINE-CURRENCY-PROBE-PLACEHOLDER>`: engine leg, added here once C6's contract with
Claude-klabauter-em lands; not yet in this batch.

**1.10.5** MCP registration: per `~/.claude.json mcpServers` entry, skip disabled/off-project,
count `mcp__<server>__` matches; 0 → `### MCP Tool Registration` line + `/<server>:doctor`.

**1.10.6** No auto-reconcile step. `handoff.reconcile_open` is dead (K-026, superseded by K-057)
and is deliberately left unclassified engine-side — classifying or eager-listing it resurrects it
against the kill bar. Do not wire it, and do not read its absence as a gap.

**1.10.7** `bin/check-fixture-sync.sh` if present/executable — exit 1 `FIXTURE DRIFT:` under
`### Cross-Repo Fixture Sync`, re-pin via `cross-repo-memo`, never a direct sibling edit.

**1.10.9** `d-claude-klabauter-bin-sentinel` (Step -0.9) → `### Coordinator-Bin Sentinel` when fired.

## Step 2 / 3 / 3.5: Freshness Checks

No CLI yet derives commit-delta staleness for docs, tests, or the bug sweep from git history —
degraded pending engine producers on all three:
- Doc freshness: `check-harvest-debt` moves to the weekly group.
  <!-- engine-gap: field=freshness.doc_commit_delta producer=unknown memo=cartography-churn-live-caller-and-workday-start-staleness.md -->
- Test staleness: skip this cadence.
  <!-- engine-gap: field=freshness.test_commit_delta producer=unknown memo=cartography-churn-live-caller-and-workday-start-staleness.md -->
- Bug-sweep staleness: `state/bug-backlog/.meta.yaml` date signal only (no commit-count trigger) —
  no backlog and >50 tracked source files suggests a first sweep. Read directly, no spawn.
  <!-- engine-gap: field=freshness.bug_sweep_commit_delta producer=unknown memo=cartography-churn-live-caller-and-workday-start-staleness.md -->

**3.6** `d-rag-staleness-regen` (Step -0.9) → **Project-RAG** line when fired. Flag-only, PM
invokes manually (a reindex can race an open editor).

## Weekly group (gated on `state/.workday-start-weekly-marker`, 7-day mtime)

If the marker is within 7 days, skip this whole group silently. Otherwise run all of the
following in one shell call, then touch the marker:

`orphan-branch-sweep --format text --severity-min warning` (CRITICAL → `### Orphan Sweep` — branch,
PR#, post-merge commits, investigate-first; WARNING → same section, open-a-PR nudge; render after
`### Alignment Check`, before `### Priority Suggestions`), `draft-plan-aging docs/plans` (only if
`docs/plans` has ≥5 entries — exit `1` → "Stale draft plans" + decision prompt; any other non-zero
→ stderr verbatim), `check-harvest-debt` (surface verbatim if non-empty, flag only, never
auto-run `/distill`), `central-run-due` (`[universal]` volume over threshold (150) → Priority
Suggestion w/ per-repo breakdown, read-only, PM-actioned), `verify-snippet-sync
project-rag-preamble` (MISMATCH/MISSING_END → **Preamble Drift**, never auto-fix),
`workday-complete-backfill-scan --lookback 7` (commits-but-no-summary gap → **Daily-Wrap
Coverage**, read-only, never auto-backfills), `check-provisional-expiry.py docs/plans` (expired
`provisional_until:`/`revisit_by:` → ratify/extend/flip-terminal prompt, read-only, never
auto-resolves).

No canonical-structure scaffold runs against `~/.claude` in this group or any other. `~/.claude` is
harness config and backup, holding no coordinator working data, and the
`guard-repo-setup-claude-home-refusal` bash guard refuses a scaffold write targeting it.

## Step 3.7: Blast Radius Advisory

`tier-last-run blast-radius` — advisory only, exit 0 always. Non-empty output → `### Blast
Radius`, one line per declared `ceremony_test_cmds` entry the current change touches (count of
changed files under its `collection_roots` plus that tier's last-run age); silent on no hit or on
a stale sentinel. Never blocks; never runs the tier itself.

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

### Alignment Check
Mismatches or "all aligned" — each names tracker status + archive ship date.

### Orphan Sweep / Agent Worktrees / Auto-Push Health / Addon Health / Test-Red Delta / Blast Radius
Each section omitted unless its own step produced findings.

### Priority Suggestions
Bugs first, then stale sweep/tests, tracker Ready rows, deep debt backlog — by urgency.

### What should today's focus be?
Tracker Ready items, handoff action items, PM-facing options.
```

Per suggestion batch (outside the fence, avoiding nested-fence parse failure): one
`append-goal-event --period day --period-value <today> --text-file <path>` call passing every
suggestion in the batch, not one process per suggestion — accept a list if the CLI supports it,
else the smallest number of calls that covers all suggestions grouped by shared metadata. A batch
of suggestions is multi-line prose: it goes through `--text-file`, never inline `--text`, which
refuses a newline rather than landing a one-line event.

**Marker:** `d-workday-marker-write` (Step -0.9) — write `state/.workday-start-marker` once
complete; `/workstream-start` checks this file.

## Step 5.5 / 5.6

Generate `state/orientation_cache.md` (40-60 lines, SessionStart hook injects it instead of raw
repomap content); skip if `tasks/` absent. Full derivation: wiki.

`d-ceremony-hook-output` (Step -0.9) — print verbatim as a standalone trailing line, after the
briefing (this ceremony's summary settles before this step, unlike the other three). Silent no-op
absent a `workday_start_post_command:` key in `coordinator.local.md`.

## Step 5.7: Offer to Volunteer as Group EM

**This ceremony never nominates.** Run the READ verb only —
`<plugin-root>/bin/group-em-nomination.py who --repo <root>`
(`snippets/resolve-coordinator-bin.md` § CLIs with no launcher) — and report what it says in one
line, followed by a one-line offer to take the role. Then stop. `nominate` runs on the PM's
explicit yes to that offer and on nothing else: not on an empty record, not on a dead holder, not
on a session that looks idle, not because the offer went unanswered.

**Who was nominated is not whether anyone is still watching.** Also run
`<plugin-root>/bin/group-em-watch-cli.py --repo-root <root>` and report its
`GROUP EM WATCH: <verdict>` line alongside the nomination read — different questions, neither
substitutes. Report the verdict as-is; never nominate or nudge off it.

The reason is that `nominate` is last-writer-wins and never refuses. It cannot decline a bad take,
so the judgment has to sit upstream of it — and a ceremony that runs every morning would silently
pass the role around the fleet, displacing live holders who learn about it only if someone
remembers to tell them. Volunteering is a direction-class call: it is the PM's to make.

On the PM's yes, run `nominate --repo <root> --session-id <this session>` and report the verdict.
If it names a displaced holder that is still running, tell that session the role has moved.
Claiming the record is still not entering the mode — `/group-em` stays PM-gated, sends stay gated
per send.

## What This Does NOT Do

Bug-sweep / daily-code-health / deep-architecture-survey / update-docs (dedicated invocations).
Merge to main. Choose work (`/workstream-start`'s Engage section).

## Relationship & Concurrent Safety

Once/day; `/workstream-start` skips redundant checks on a fresh marker. `/workday-complete` is the
evening counterpart. `/update-docs` and `/bug-sweep` are recommended, never auto-dispatched from
here — a PM call. Read-only except `state/.workday-start-marker` and
`state/.workday-start-weekly-marker`. Avoid acting on a stale item a concurrent session already
shipped — Step 1.3 is the (currently degraded) prevention.

If `$ARGUMENTS` is provided: _"Requested focus: {arguments}"_
