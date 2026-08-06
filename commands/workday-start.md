---
name: workday-start
description: "Morning orient — triage handoffs, surface staleness, align priorities."
allowed-tools: ["Read", "Write", "Grep", "Glob", "Bash", "Agent"]
argument-hint: "[optional day focus]"
---

# Workday Start — Morning Orientation

Prepare the day's workstream-start calls to be maximally efficient. Ensure context is fresh, priorities are clear, and any overnight health findings are surfaced.

**Announce at start:** "I'm running workday-start to prepare the day's context."

## Step -0.9: Assemble the Day-Cadence Brief

Run: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/orient-assemble" brief --cadence day`

The op computes the cadence-invariant orient spine in one read-only pass — EM environment/effort
drift, agent-worktree sweep, addon/doctor health scan, inbound cross-repo memo surfacing,
project-RAG staleness, branch span assertion, open-handoff auto-reconcile observation,
handoff triage (ready-to-fire, awaiting-gate, stale-executing-plan advisory), exec-bit drift,
Claude-klabauter-bin sentinel, the post-ceremony command hook, a read-side report on orphaned in_flight
handoffs, and today's marker-freshness check — the same computation `workstream-start` and
`workweek-start` name for their own cadences. Parse the returned decision object:

- **`directives[]`** — each is an unconditional action; execute it as you reach it, rendering its
  `detail` into the relevant Morning Briefing section (§ Step 5) rather than re-deriving the
  finding by hand.
- **`judgment_points[]`** — genuine EM/PM calls the op cannot resolve for you (e.g. an inbound
  cross-repo memo `ask`/`proposal`/`consult` awaiting Accept/Decline/Surface-to-PM). Resolve each
  before any directive gated on it proceeds; never auto-pick a disposition.
- **`narration`** / **`next_move`** — surface verbatim as the lead of the relevant briefing
  section when non-empty.

Do not narrate the individual checks above as separate steps — the op owns their procedure; this
surface only consumes its output. What follows is the day-specific residue the op does not
compute: session-reaper hygiene, branch setup/reconciliation, the archival/reaper family beyond
its read-side report, and the deeper doctor/engine-drift matrix.

## Step -1: Session Reaper

Run the session reaper before any other work to bound stale-session accumulation. Capture stdout to a log file; do not echo reaped-session lines into the Morning Briefing.

Run: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/workday-start-day-branch-resolve" reap-log`

Non-zero exit (lib not found) → continue; the reaper is hygiene, not a gate.

## Step -0.45: Git-Hook Freshness Self-Heal

Deployed git hooks (`.git/hooks/prepare-commit-msg`, `.git/hooks/post-commit`) are generated at
one-time `repo-setup` and never re-run on a recurring cadence — a hook body ported to a new
implementation (e.g. bash → Python) leaves the deployed hook stale until something re-invokes the
installer. Run both idempotent installer entrypoints once per day so a stale or absent hook
self-heals within a day, without reintroducing the per-session boot cost that boot-time
guardrail/reminder/detector SessionStart hooks were retired to avoid (only the fast orientation
injector survives boot). Full rationale: `pipelines/workday-start-internals.md` § Step -0.45.

Run both idempotent installer entrypoints: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-ensure-prepare-commit-msg-hook"` then `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-ensure-post-commit-hook"`.

<!-- Windows invocation of these extensionless python3-shebang entrypoints (vs their paired
     `.cmd` launchers) is the surface the in-flight macos-first-class-invocation workstream is
     normalizing — this step matches the existing direct-path idiom used by neighbouring steps
     and defers Windows-path specifics to that workstream. -->

Both entrypoints are idempotent: on an already-current deployed hook they no-op silently; on a
stale or absent one they rewrite it atomically. **The common case is silent** — surface a
one-line note in the Morning Briefing (under the environment section) ONLY when an installer
actually repaired a stale/absent hook (e.g. _"prepare-commit-msg hook repaired (stale body)."_).
Non-zero exit (installer absent, lib error) → one-line skip note; do not block the ceremony.

## Step -0.4: Untested-Platform Advisory

Before Branch Setup, warn once if this ceremony is running on a platform this repo declares
present but has never actually verified. Silent when the
platform is tested, or when the manifest hasn't opted into the packageability contract at all.

Run: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/untested-platform-advisory"`

Relay any output verbatim in the Morning Briefing. Non-zero exit or no interpreter found →
continue silently; this is advisory hygiene, not a gate — the helper itself always exits 0.

## Step 0: Branch Setup

Ensure work happens on an active workstream branch and reconcile with `origin/main` daily. Active workstream may be canonical (`work/{machine}/{date-or-span}`) **or** a PM-authorized long-lived bus (`migration/...`, `release/...`, `feature/...`). Daily ritual is **reconcile with origin/main**, not rotation.

**Precedence switch** (evaluate in order; stop at first match): (1) stale-commit (>2 days) → A/B/C Branch Reconciliation flow; (2) already-in-span → silent exit; (3) on main/detached/empty → create `work/{machine}/{today}`; (4) named long-lived bus → skip rename, proceed to reconcile; (5) midnight-rename → atomic rename + one-line briefing notice.

Every off-daily ref operation requires `COORDINATOR_OVERRIDE_BRANCH=1 COORDINATOR_OVERRIDE_BRANCH_REASON="workday-start step 0 <action>"`.

**Run the canonical Step 0 script — do not transcribe the procedure inline:**

Run: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/workday-start-step0"`

The script encapsulates sync-main, the precedence switch (Checks 1–4 + 3.5), the rename procedure (Step 0.4), and the reconcile flow (Step 0.4.5).

**Stdout shape:** one line on IN-SPAN; two lines on FRESH-CUT / NAMED-WORKSTREAM / RENAMED (precedence status + reconcile status: `ALREADY-CURRENT`, `RECONCILED-FF`, or `RECONCILED-MERGE`). Surface both in the Morning Briefing.

Exit codes: `0` success; `2` `STALE-NEEDS-ABC` → invoke A/B/C flow below; `3` `RECONCILE-CONFLICT` → PM resolves; `1` unexpected error → halt.

**Step 0 is not EM-skippable on judgment.** "Reconcile not rotate" governs whether to *abandon* the branch (no), not whether to *rename* the suffix at midnight (yes, via Check 4). Legitimate skips: only the precedence outcomes the script reports (`IN-SPAN`, `NAMED-WORKSTREAM`, `FRESH-CUT`). Any other path MUST execute the rename when Check 4 fires; Step 0.45 catches silent skips. Full rationale: `pipelines/workday-start-internals.md` § Step 0.

### Step 0.45: Post-Step-0 Span Assertion

After the precedence switch resolves, verify the active branch's name covers today — catches EM
judgment-skips, rename failures, and silent fall-throughs. `d-branch-span-mismatch` (Step -0.9's
brief) carries the comparison; when it fires, surface its `detail` verbatim as a top-line
`### Branch Span Mismatch` block (above `### Context Freshness`). Do NOT auto-rename — assertion
is a tripwire, not a retry.

Rationale: "reconcile not rotate" forbids *abandoning* the branch, not skipping the midnight rename.

### Step 0 conflict handling — Branch Reconciliation Decision

When `git merge --no-ff` hits a conflict, abort and produce a **Branch Reconciliation Decision** block naming each conflicting branch.

**Interactive (TTY):** Hard-block until PM chooses:
- **A — Consolidate now:** run `/consolidate-git`; resume after.
- **B — Defer:** write `tasks/.deferred-branches.md` entry: `{branch} | reason: {reason} | re-check: {today+7d} | deferred-by: workday-start {today}`. Surfaced next morning if re-check date passed.
- **C — Archive (abandon):** rename `archive/{machine}/{today}/{branch}` locally; push; delete old ref.

**Non-interactive (no TTY):** Auto-defer with `reason=auto-deferred, awaiting PM` and `re-check={today}`; emit note in Morning Briefing. Next interactive run forces A/B/C.

## Step 0.5: Orphan Branch Sweep

Run: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/orphan-branch-sweep" --format text --severity-min warning`

For each line returned:

- **CRITICAL** entries → surface in the Morning Briefing under a `### Orphan Sweep` section. Include the branch name, the merged PR number, and the count of post-merge commits. Recommend: _"Investigate before opening new work — these commits may be orphaned. Salvage via PR or consolidate into today's branch."_
- **WARNING** entries → surface as a heads-up in the same section. Recommend: _"Open a PR or consolidate before the branch goes stale."_
- **No output** → skip silently (do not emit "no orphans found" — noise).

Append the rendered section to the Morning Briefing template in Step 5 (after `### Alignment Check`, before `### Priority Suggestions`).

## Step 0.6: Agent Worktree Sweep

Classification and disposition (which worktree is reapable vs. needs EM/PM triage) come from Step
-0.9's brief as `d-worktree-reap-*` directives and, for non-benign dirty worktrees, a judgment
point — never re-classify by hand. Each directive names the existing
`agent-worktree-sweep --reap` CLI; execute it as reached. **Why these worktrees are unintended
residue:** git worktrees are structurally banned for parallel agent dispatch fleet-wide — they
degrade badly on Windows (the primary machine and audience) and don't scale to a concurrent
agentic fleet (merge/conflict/integration overhead exceeds the time parallelism saves). Any
worktree found here is leftover from a bypass or an expired PM-permission exception, not a
legitimate dispatch artifact.

**Surface `### Agent Worktrees`** only when a directive fired or a judgment point was raised.

## Step 0.7: Consumed-Marker Frontmatter Sync

Belt-and-suspenders against handoff-frontmatter drift: EMs sometimes mark work shipped with `<!-- consumed: YYYY-MM-DD -->` body markers but forget to flip `status:`/`deployment_state:` in frontmatter, leaving unflipped records in `ready_to_fire` queries.

Run: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/normalize-consumed-frontmatter"`

Idempotent; one-line no-drift notice to stderr when nothing changes. Each change names file + field flips; recurring drift across days is a doctrine signal (consider `coordinator:learn-lessons`). Scans handoffs + plans + decisions + reviews. Strips `gate_dependency:` on flipped records; preserves terminal states — plan/decision axis `superseded`/`abandoned`, handoff axis `shipped`/`continued`/`closed`.

## Step 0.8: Stale-Executing Plan Nudge

The stale-executing-plan advisory (plans whose driving handoff was silently archived by the
boot-time sweep, or where code landed without the EM flipping the plan to `implemented`) is one
of Step -0.9's handoff-triage directives — surface its `detail` verbatim; don't re-query.
Triage: flip to `status:implemented`, `status:abandoned`, or pick back up.

**Also read `tasks/orphan-sweep-notes.md` if present** — the boot-time archival sweep
(claude-klabauter `coordinator_core/ops/session/boot_sweep.py`) appends a line per orphan-archive
event; not assembler-owned (it mutates disk to rotate). Surface alongside the stale-executing
list, then rotate (preserve 4-line header) via: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/workday-start-handoff-triage" trim-notes`

Non-empty on days when concurrent sessions died mid-pickup overnight.

## Step 1: Handoff Triage

Query-driven, not grep-driven. Actionable-now and awaiting-gate handoff triage are Step -0.9
directives (`d-handoff-triage-*`, ported from `workday-start-handoff-triage`'s `ready`/
`awaiting-gate` subcommands) — surface their `detail` verbatim; don't re-query.

### Step 1.1: Actionable-now handoffs

Routing on `kind:` (spinoffs cluster separately) when rendering the directive's detail:

- **`kind: spinoff` and `kind: spinoff-roadmap`** — both are pickup-able forks. List together in a "Spinoffs awaiting pickup" subsection. `spinoff-roadmap` rows additionally cluster by `roadmap_id:` (group all stubs from a single roadmap-planning run) — surface roadmap heading + stub count, not raw rows, when `roadmap_id` is non-empty and the count > 3.
- **`kind: session-handoff`** (or absent) and **`kind: recovery`** — list together in a "Continuation handoffs" subsection. Recovery rows get a `(recovery)` suffix so the PM can see at a glance which continuations came from a crashed/killed prior session.

### Step 1.2: Gated handoffs (always surface count; flag stale subset)

- **If any `awaiting_gate` exist:** surface the full list as a "Gated handoffs" subsection (titles + gate_dependency, not bodies). Morning briefing is the right surface for cross-workstream gate awareness — silently filtering them buries actionable triage decisions (clear gate, retarget, pick up early).
- **If any are >6 days old (≈ one working week):** additionally flag _"{M} handoffs awaiting_gate >6 days — gate may be stuck; consider triage, PM clear-gate, or close out."_
- **If none exist:** skip silently.

**Standalone 14d/7d aging check — retired as a batch nag.** This step used to also force-invoke `bin/handoff-gate-aging` against `state/handoffs/` and surface a separate "past the 14d/7d force-recheck threshold" line. Dropped because `coordinator_core.reconcile.gate_eval` (the resolver every gate-eval-driven pass already runs) surfaces every `awaiting_gate` handoff that needs a human look — via `blocking_notes`/prose `gate_dependency` dominance — unconditionally of calendar age; the "Gated handoffs" full-list surface + the `>6d` nudge two bullets above already give the PM everything the retired check added for that population. The one bucket the resolver never surfaces (real, still-open structured `blocked_by` edges, nothing wrong — `evaluate_gate`'s `not-cleared` verdict) is a deliberate quiet design in `gate_eval.py` itself, not a gap for this ceremony to re-nag around. Full evidence + disposition: `coordinator_core.ops.handoff_gate_aging` module docstring. The predicate itself is not deleted — `handoff-gate-aging` stays runnable ad hoc, and `pickup-assemble` still surfaces it per-handoff as `jgate` evidence.

**Mechanized draft-plan staleness check.** Parallel check for orphaned draft plans — run it against `docs/plans/` unconditionally (not gated on the `awaiting_gate` query above):

Run: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/draft-plan-aging" docs/plans`

- **Exit `1`** (stale draft plans found, one line each): surface under a "Stale draft plans" subsection with a decision prompt — _"{N} draft plans older than 14d with no recent real-work commits and no owning baton — execute / archive / close-DR?"_ List the flagged paths.
- **Exit `0`** (nothing stale): skip silently.
- **Exit `2`** (internal error): surface the stderr diagnostic verbatim under "Stale draft plans"; do not silently drop the malformed record.
- **Exit `3`** (claude-klabauter-link transport failure — the trampoline's own dedicated code, distinct from the `2` internal-error business code): surface the stderr diagnostic verbatim under "Stale draft plans"; a real claude-klabauter-link outage must be visible, not silently treated as "no stale plans."
- **Any other exit code:** treat as transport/internal failure too — surface the stderr diagnostic verbatim under "Stale draft plans" rather than silently skipping.

### Step 1.3: Reconcile pending items against git (MANDATORY before declaring any item actionable)

Per-handoff in `ready_to_fire`: (a) `git log --oneline --since="<handoff-date>" --all` and scan subjects for matching items; (b) Read referenced plan/stub `**Status:**` fields; (c) drop confirmed-closed items, note as "verified-closed since handoff". Empirical baseline: 30–60% of inherited items are already closed. **Full procedure:** `pipelines/workday-start-internals.md` § Step 1.

### Step 1.4: Cross-reference against completed archive (sanity check)

Query the completed archive for recent entries: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/query-completions" --where "created>=$(date -d '30 days ago' +%Y-%m-%d 2>/dev/null || date -v-30d +%Y-%m-%d)" --sort "created" --format json`

**Legacy fallback:** if `query-completions` returns empty AND `archive/completed/legacy/<YYYY-MM>.md` exists, read the legacy monolith for this reconciliation check only (read-only; no writes to the legacy path).

For each `ready_to_fire` handoff, check whether the work it describes appears as completed in the query results — match on workstream names, feature names, commit hashes, or distinctive keywords. If a match is found, flag it: _"Handoff [file] describes [work] — archive/completed shows this shipped on [date] (commit: [hash]). Likely already done — pick up to confirm and archive, or close out?"_

### Step 1.47: Sweep shipped handoffs (deployment-axis archival)

Run the shipped-handoff sweep — idempotent, concurrency-safe, safe to run every `/workday-start`: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/sweep-shipped-handoffs"`

Surface the one-line output in the Morning Briefing under `### Handoffs`:
- If handoffs were archived: include the summary line (e.g. _"3 shipped handoffs archived."_).
- If a SHA resolution warning fires: surface it verbatim (e.g. _"WARNING: 2 shipped handoffs retained — shipped_in SHA no longer resolves."_).
- If nothing was archived (_"no shipped handoffs archived"_): skip silently.

Non-zero exit (script absent, lib error) → one-line note ("shipped-handoff sweep skipped: \<reason\>"); do not block.

### Step 1.473: Promote shipped claimed/in_flight spinoff-roadmap stubs

<!-- Interim closer — retire this step once lvv-09's claimed/in_flight branch (Branch C)
     lands in /workday-complete. -->

<!-- Ordering note: this closer MUST run before Step 1.475's reaper scan. The reaper's
     scan predicate (status==claimed && deployment_state==in_flight, no kind: filter)
     overlaps this closer's scan set on claimed spinoff-roadmap in_flight stubs, but the
     two decisions are disjoint — this step decides deliverable-shipped, the reaper decides
     holder-liveness. Promoting a shipped stub to terminal `shipped` here means Step 1.475's
     liveness gate finds it already terminal and skips it, instead of reaping a live
     deliverable stub as a crash orphan. Closer-before-reaper ordering plus the closer's
     single TOCTOU re-read (immediately before its stamp/ship sequence begins) closes the
     interleaving window between a closer run and a reaper run. A narrower residual race
     remains between the closer's OWN stamp and ship sub-steps (the TOCTOU read is not
     repeated between them): if a concurrent writer flips the record to `closed` in that
     window, the closer still proceeds to ship. This residual is correct-by-construction
     rather than merely acceptable — the closer only reaches ship after its stamp already
     landed a real `shipped_in` SHA, so the deliverable genuinely shipped on origin/main;
     last-writer-wins between the two terminal outcomes (shipped vs closed) resolves to
     the semantically correct state, not an arbitrary race winner. Both outcomes are
     terminal, strictly better than the pre-existing unbounded-in_flight gap. -->

Run the shipped-spinoff-roadmap-stub closer — idempotent, concurrency-safe, safe to run every `/workday-start`: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/promote-shipped-in-flight-stubs"`

Surface the one-line output in the Morning Briefing under `### Handoffs`:
- If any promotion happened, or either advisory line fired: include it verbatim. There are two, and they mean different things — _"N in_flight spinoff-roadmap stubs resolved no-resolving-commits ..."_ is "confirmed not shipped yet"; _"... rollup-derive reported unknown-error — could not determine ship-state ..."_ is "the question could not be answered", most often a stale or unfetched `origin/main` on this box. The second is advisory rather than loud on purpose — going loud there rebuilds the morning false-alarm — but reading it aloud is what stops a box that answers "nothing to promote" every morning from looking clean.
- If silent (nothing promoted, no advisory): skip silently.

Non-zero exit (script absent, lib error) → one-line note ("shipped-stub promotion skipped: \<reason\>"); do not block.

### Step 1.475: Reap orphaned in_flight handoffs (crash-orphan sweep)

Step -0.9's brief accepts one subprocess call to this CLI's `--dry-run` mode (the sole
zero-spawn-budget exception in the assembler) and, when the dry-run finds anything to release or
reclaim, names the live CLI as `d-reaper-orphaned-handoffs` — execute it as reached. It never
mutates frontmatter directly (delegates to `archive-stamp-cli`'s `unconsume-handoff` verb);
dual-reads `status: consumed | claimed` and only a claim whose session is confirmed dead
via the shared liveness predicate has its claim released — the handoff returns to the pool
(`status: open`, `deployment_state: ready_to_fire`, claim fields stripped, a `park_note:`
recording the release) and stays in `state/handoffs/`, never auto-abandoned or archived. A dead
holder that ran a genuine terminal completion ceremony still stamps `shipped`.

Surface the directive's `detail` in the Morning Briefing under `### Handoffs`; nothing to render
when the assembler emitted no directive.

Non-zero exit (script absent, not inside a git repo) → one-line note ("orphan-reap sweep skipped: \<reason\>"); do not block.

### Step 1.5: Report

_"{N} actionable handoffs ({K} continuations, {S} spinoffs incl. {R} roadmap stubs in {G} groups). {G} awaiting_gate (of which {M} >6 days) [if any]. {X} items verified-closed by git reconciliation."_ Omit any clause whose count is zero.

## Step 1.45: Outstanding Cross-Repo Memos

Inbound-memo judgment points (`j-memo-*`) come from Step -0.9's brief — resolve each as
Accept / Decline / Surface-to-PM before proceeding; never silently auto-resolve. Surface under
`#### Outstanding cross-repo memos (DoE attention):`.

**Route-to-baton default:** any surfaced memo — likewise any review finding or triage item encountered during this ceremony — whose subject falls inside the scope of an active handoff (`state/handoffs/*.md`, `status: open|claimed`) gets a routing note appended into that handoff under a dated `## Routed from inbox triage (<YYYY-MM-DD>)` heading (source path cited, handoff frontmatter untouched), and that edit committed with pathspec, as a matter of course. Not held in session context, not left inbox-only, not asked per-instance. The memo's own lifecycle flip still happens only in the `/pickup` memo branch.

Outbox drafts are not assembler-owned — run `workday-start-cross-repo-memo-outbox-surface.py`. Non-empty → surface verbatim under `#### Outbox drafts awaiting send (DoE attention):`. Empty → skip.

Run: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/workday-start-cross-repo-memo-outbox-surface"`

### Step 1.45a: Inbox blitz — count-and-age escalation

The inbox is the one recurring backlog directory with no batch move over it (`state/bug-backlog/` has `/bug-blitz`, `state/lessons/` has `/learn-lessons`, the debt backlog has `/debt-triage`). Its failure mode is **accretion, not volume** — no single day looks bad enough to act on, and sixteen days later there are sixty memos. This step is that batch move, housed here rather than in a skill of its own: the ceremony that already looks at the inbox every morning is the right place to notice it has grown. **There is deliberately no `/inbox-blitz` skill** (skill-accumulation aversion) — do not re-house this.

Run: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/workday-start-inbox-blitz-assemble"`

One JSON object on stdout. Route on `state`:

- `skipped` — claude-klabauter unresolvable or `memo.blitz_buckets` unregistered. Render nothing; never nag about claude-klabauter's activation state.
- `inventory` — **neither** trigger leg tripped. The plain Step 1.45 inventory above stands unchanged; add nothing.
- `escalate` — **either** leg tripped (open count over threshold **or** oldest open memo over the age threshold; defaults 10 / 7 days, both tunable). Surface the counts under `#### Inbox blitz (N open, oldest Nd)` and run the blitz.

**The age leg is the load-bearing one.** A count-only trigger never fires on slow accretion, which is the observed failure mode.

On `escalate`, dispatch **one Sonnet agent per entry in `dispatches[]`** — fyi-tier, dominant correspondent, rest — passing that entry's `brief` **verbatim** and its `memos[]` as scope. The briefs are engine-generated, not paraphrased here, because three of their clauses are non-negotiable and each was earned by a concrete finding: the **fyi sweep is not a rubber stamp** (the sender labels `fyi` from their own vantage and cannot know what is load-bearing for the receiver — this is what surfaced a break-class contract defect), **supersession precedes classification** (or real effort goes into classifying dead asks), and **verification is mandatory** (a memo saying "your X is broken" is a claim to check, not a fact to record). Retyping a brief is how a clause gets dropped; paste it.

Classification vocabulary is fixed in those briefs: DISPATCH-TO-FIX / DISPATCH-TO-IMPLEMENT / PLAN-WEIGHT / REPLY-ONLY / SUPERSEDED. Fix and implement stay split — both dispatch, but repairing a defect and building a surface want different briefs and different verification.

`supersession_candidates[]` are **candidates**, never confirmations: confirming that a later memo *resolves* an earlier one rather than merely touching the same topic is judgment and stays with the EM. Loose matching drops live asks.

When the reports land, group PLAN-WEIGHT items by problem/solution space and cut **one baton per space, not per memo** (`plan_weight_note` carries this verbatim) — the reason is concurrency safety on a shared worktree, not tidiness. Route into an existing open baton wherever one covers the space; that is the route-to-baton default already standing above.

## Step 1.55: Recent Roadmap Orientation

Surface last quarter's top-10 roadmap completions by size — grounding the day in recent delivery context. Count-always pattern: the heading renders regardless of row count.

Run: `python3 "<claude-klabauter-root>/coordinator/bin/lib/records_query.py" completion "nature=roadmap" markdown-list 10 --sort "-loe.tshirt" --since "90d"` (`<claude-klabauter-root>` resolved via `$REPO_CLAUDE_KLABAUTER` / `machine-local get repos.claude_klabauter`).

Render under `#### Recent roadmap (last 90d, top-10 by size)` inside `### Handoffs` (Step 5). One bullet per row; `(none)` when zero rows (expected on new/un-migrated repos). `query-completions.py` with equivalent flags is also accepted.

## Step 1.6: Coordinator-Improvement Queue Check

Read the central improvement queue (resolved via `coordinator-state-root.py --central`'s `improvement-queue/*.yaml`, structured per-entry YAML, claude-klabauter-resident) and the local queue (`state/improvement-queue/*.yaml`, if present in current repo) via the block below. Count `*.yaml` files as active entries per queue; oldest = earliest dated filename (`YYYY-MM-DD-*.yaml`). `[recurring: ≥3]` is now a per-entry field read from inside each YAML entry (not a main-line markdown schema) — read matching entries to surface any.

Run: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/workday-start-advisory-counters" improvement-queue` (emits one line of JSON: central + local entry counts, oldest-by-filename, and any `recurring` flags).

Surface in the Morning Briefing when notable: central ≥ 5 entries, oldest >14 days, any `[recurring: ≥3]`, or local ≥ 1. EM advocates based on depth — judgment, not a threshold trigger. Skip silently when both queues are empty or absent.

Also check `state/cross-repo-commitments/` (directory of YAML entries; if present) — count entries with `status: open`. Surface alongside the queue counts when ≥1: _"N open sibling commitments — oldest Nd (computed from `observed`)"_. Skip silently when the directory is absent or empty.

## Step 1.65: Bug Backlog Depth Check

Read `state/bug-backlog/*.yaml` (structured per-entry YAML dir; if it exists). Use `bin/query-records --type bug --where 'severity in (P1,P2) AND status=open' | wc -l` to count open P1/P2 items. Surface in the Morning Briefing when ≥ 10: moderate (10–19) → `/bug-blitz` suggestion; heavy (≥ 20) → stronger nudge. Skip silently if the `state/bug-backlog/` directory is absent/empty or the count is <10.

## Step 1.66: Test-Red Delta Surface

Companion advisory to Step 1.65 — same altitude, same non-blocking counter shape, one more
morning surface rather than a new ceremony phase. This step consumes the record `state/test-red/<machine>.yaml`
emits per tier. **`failing` is tri-state**, not a plain list: a YAML list (including `[]`) is
authoritative (`[]` means authoritatively clean); `null` means red but the failing set could not be
derived from this run's output — never treated as green, and never folded into a `cleared` delta.
**Comparison baseline:** `acknowledged.baseline` when an acknowledgement is present and not voided,
otherwise `previous.failing`. **Delta vocabulary:** `new` (in current `failing[]`, absent from the
baseline), `cleared` (in the baseline, absent from current), `persistent` (in both). **An
acknowledgement is VOID** — treat as absent, surface the full current red set — when its `owner`
artifact is unresolvable/unparseable, or when `expires_at` (default `acknowledged_at` + 14 days) has
passed.

Resolve the machine token via `machine-local get coordinator.machine_slug`, then check for
`state/test-red/<machine>.yaml` (per-tier mapping, e.g. `tiers: {fast: {...}, plugin-ecosystem:
{...}}`). **Absent or malformed record → emit nothing, silently** — this is the expected state on
every machine until the claude-klabauter-side emitter lands (C0/AC6), not a health regression.

When the record exists and parses, evaluate each tier against the wiki's surfacing rule and
render as a conditional bullet row under the combined `### Orphan Sweep / Agent Worktrees /
Auto-Push Health / Addon Health / Test-Red Delta` heading in Step 5's Morning Briefing template
— non-empty only:

- **`new` non-empty** (vs. `acknowledged.baseline` when present and unvoided, else
  `previous.failing`): _"Test-red: {tier} — {N} new failure(s) since {baseline source}:
  {list}."_
- **`acknowledged` null or voided, and `failing[]` non-empty:**
  - **void-on-doubt** (owner unresolvable): _"Test-red: {tier} — acknowledgement void: owner
    `<path>` unresolvable. {N} failures unsuppressed: {list}."_
  - **void-on-expiry:** _"Test-red: {tier} — acknowledgement expired `<date>`, owner `<path>`
    still open. {N} failures unsuppressed: {list}."_
  - **no acknowledgement at all:** _"Test-red: {tier} — {N} unacknowledged failures: {list}."_
- **acknowledged owner artifact closed/terminal while `failing[]` still non-empty:**
  _"Test-red: {tier} — owning work `<path>` closed but {N} failures remain: {list}."_
- **`failing` is `null`:** _"Test-red: {tier} — red, failing set unavailable (run at {ran_at},
  runner: {runner})."_ Never treat this as green; never fold it into a `cleared` computation.

Each of the four branches above (`new`, void-on-doubt, void-on-expiry, `failing: null`) is a
distinct line — do not collapse any of them into the absent-record skip path, and do not
collapse void-on-doubt and void-on-expiry into a single generic "void" line; their reasons
differ and both must be visible.

**An acknowledged, unexpired red set whose delta is all-`persistent` produces no output at
all** — same convention as Step 1.6's cross-repo-commitments check ("Skip silently when the
directory is absent or empty"): silence is the correct response to nothing actionable, not a
gap in coverage.

Never run the test tier. Never block the ceremony on this step's outcome.

## Step 1.7: Scheduled Rechecks

Glob `tasks/cookbook-recheck-due-*.md`, `state/inspiration-recheck-due-*.md`, `state/lesson-triage-recheck-due-*.md`, and `tasks/recheck-due-*.md`. Each filename ends in `-YYYY-MM-DD.md`. For each:
- **today ≥ due date** → surface in Priority Suggestions: _"Scheduled recheck due: `<filename>` (due {YYYY-MM-DD}). Procedure inside the file."_
- **due within 7 days** → heads-up: _"Scheduled recheck upcoming: `<filename>` (due {YYYY-MM-DD}, in {N} days)."_
- **Otherwise** → skip silently.

No marker files → skip silently. Do not auto-execute — PM-actioned, not auto-dispatched.

## Step 1.72: Outstanding Provisional Decisions

Daily catch for the failure class D1's conservation assertion does not cover — an
unexecuted staged decision (ratification, second rollout stage, park-note hold) sitting in
a plan's `provisional_until:`/`revisit_by:` frontmatter with no reconciler candidate ever
involved. Chosen over `/workweek-start` because this class went undetected for 13 days on
the motivating case; a daily cadence bounds recurrence tighter than a weekly one.

Run: `"${COORDINATOR_PYTHON:-python3}" "$CLAUDE_PLUGIN_ROOT/coordinator/lib/check-provisional-expiry.py" docs/plans`

- **Exit `1`** (expired provisional decisions found, one `EXPIRED:` line each): surface
  under a "Provisional Decisions" subsection with a decision prompt — _"{N} plans have an
  expired provisional_until/revisit_by date — ratify, extend the date with a reason, or
  flip the plan terminal (implemented/deferred/abandoned/superseded)?"_ List the flagged
  lines verbatim.
- **Exit `0`** (nothing expired): skip silently.
- **Exit `2`** (internal error — missing path, unparseable date): surface the stderr
  diagnostic verbatim under "Provisional Decisions"; do not silently drop the malformed
  record.

DoE-side detector, no claude-klabauter involvement. Read-only — never auto-resolves a flagged plan.

## Step 1.75: Central Learn-Lessons Volume Trigger

Run `central-run-due.py` (relative to the coordinator plugin root). It counts `[universal]`
entries accrued across the configured roots since the last **COMPLETE** central run and compares to
`central_volume_threshold` (config, default 150). This is the *volume* companion to the date-based
recheck marker (Step 1.7): a fixed cadence under-runs in busy weeks, when the sibling `state/lessons/`
boot-surface floor balloons fastest.

Run: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/central-run-due"`

- **Prints a `CENTRAL_RUN_DUE` line** (over threshold): surface in Priority Suggestions —
  _"Central learn-lessons due (volume): {N} universals accrued since {date}. Consider `/learn-lessons` central."_
  with the per-repo breakdown.
- **Stderr-only / nothing on stdout** (below threshold, or no COMPLETE sentinel yet — informational stderr on first run): nothing for Priority Suggestions; skip silently.

Read-only and PM-actioned — never auto-dispatch a central run. On a machine without the sibling roots,
unreachable roots are skipped silently (the date-based marker in Step 1.7 still covers the cadence floor).

## Step 1.8: Project-RAG Preamble Drift Check

Run: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/verify-snippet-sync" project-rag-preamble`

- **No consumers found** (exit 0): skip silently.
- **All consumers OK** (exit 0, all `OK`): skip silently.
- **Any MISMATCH or MISSING_END** (exit non-zero): surface under **Preamble Drift**: _"project-rag-preamble drift in [N] consumer(s): [list files]. Run `verify-snippet-sync project-rag-preamble --fix` to repair, then commit all touched files together."_

**Do NOT auto-fix** — investigate which consumer drifted and why; a drift may need to be merged back into the canonical snippet rather than overwritten.

## Step 1.82: CLAUDE_PLUGIN_ROOT Source-Guard Drift Check

No automated enforcement runs here — the fixer that used to is retired with no replacement CLI yet named. Manual spot-check: grep the anchored `_cc_trusted=0` initializer across the corpus for any `="${CLAUDE_PLUGIN_ROOT:-` resolve-site missing the trusted-prefix guard core on the immediately following lines. Any drift found by that manual check surfaces under **Source-Guard Drift** and routes to the PM.

## Step 1.85: Daily-Wrap Coverage Gap Detector

Morning is the T+1 catch point for a skipped `/workday-complete`: a day that ran sessions but never wrapped leaves no `archive/daily-summaries/<day>.md` and no `state/week-changelog/<day>-<machine>.md` block, and nothing in the cadence surfaces it until someone eyeballs the changelog dir (the weekly staleness nudge is too coarse). This step closes that loop — it reuses the **same scanner** that `/workday-complete` Step 3.5 uses to backfill, run here read-only as a nudge.

Run: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/workday-complete-backfill-scan" --lookback 7`

- **Empty output:** no gap — skip silently (the healthy common case).
- **Non-empty:** surface a single non-blocking nudge under **Daily-Wrap Coverage**:
  > _"Daily-wrap gap: {date list} had commits but no daily summary. Run `/workday-complete` to auto-backfill (its Step 3.5 reconstructs each day from the on-disk dated substrate), or backfill manually."_

**Read-only — never auto-backfill here.** Reconstruction needs the per-day analyst dispatch, which is an EM-driven call inside `/workday-complete`; the detector only flags. **Trivial-only days are an EM judgment call** — a day whose only commits are a session-init auto-sweep or a gitignore chore is not real work; eyeball the list and ignore those (mirror `/workday-complete`'s own skip condition) rather than backfilling an empty summary. `covered` keys on the machine-agnostic daily summary (not the per-machine changelog block) to avoid cross-machine false positives on a shared branch.

**Why 7 here vs 14 in `/workday-complete` Step 3.5:** the morning nudge uses the tighter 7-day window to surface the most-recent gap week and reduce noise; older gaps (8–14d) remain silently handled by `/workday-complete` Step 3.5's 14-day backfill.

> Convergence: this morning-side detector complements the workday-complete backfill. Scanner: `bin/workday-complete-backfill-scan.py` (shared with `/workday-complete` Step 3.5).

## Step 1.86: Completion-Entry Reconcile Backstop

Next-session backstop for sessions that closed mid-air without a terminal ceremony (`/workday-complete`, `/handoff`, `/workstream-complete`, or `/quick-wrap`). Detects any `pending-release` completion entry authored by a prior session that has `Session-Id:`-trailer commits not yet recorded in its `commits:` list — the gap the within-session ceremonies cannot catch when a session ends abnormally.

Bounded scan: today + the immediately-prior calendar day only (not the whole archive). Detect mode only — never auto-mutates another session's entry. Keyed on the entry's own `authored_by:` field; works without the prior session being live.

Run: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/workday-start-reconcile-sweep"`

Surface any output under **Completion Reconcile** in the Morning Briefing. Empty output → skip silently. Informational only — never auto-mutates another session's entry. The `reconcile-completion-commits.py` helper's `--append` flag is used by within-session ceremonies (`/workday-complete` Step C3, `/handoff` Step C4); this backstop calls it in detect mode only.

## Step 1.9: Auto-Push Failure Surface

Silent `coordinator-auto-push` failures (Windows case-mismatched branch refs, expired credentials, SSH agent unreachable) accumulate in `.git/push-failures.log` until the next manual push — surfaced here each morning.

Run: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/workday-start-advisory-counters" push-failures` — emits one line of JSON with `total`, `recent_24h`, and `last_line` (`TOTAL`/`RECENT_24H`/`LAST_LINE` below are those fields).

**Surface `### Auto-Push Health`** when `RECENT_24H ≥ 1` OR `TOTAL ≥ 5`:
```
### Auto-Push Health
- [N] failures in last 24h (total log: [M] lines). Most recent: [LAST_LINE].
- Investigate before opening new work — push failures keep firing on every commit until the credential/branch-case/agent issue is resolved.
- Cleanup after fix: `> .git/push-failures.log` (truncate; do not delete — helper appends in-place).
```
**If `RECENT_24H == 0` AND `TOTAL < 5`:** skip silently.

## Step 1.91: Local-Only Work-Branch Surface

Complement to Step 1.9. Step 1.9 surfaces failures that the auto-push hook *captured* into `.git/push-failures.log`; this step catches the silent failure mode where the hook never ran at all (uninstalled, non-executable, routed elsewhere) — in which case `.git/push-failures.log` would never be created and Step 1.9 would report all-green even though commits are stranding on local disk.

Run: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/workday-start-advisory-counters" local-ahead` — emits one line of JSON with `branch`, `eligible`, `ahead_count`, `no_origin`, and `push_failures_log_present`. `CUR_BRANCH` = `branch`; `LOCAL_ONLY_AHEAD` = `ahead_count` when `no_origin` is false; `LOCAL_ONLY_NOORIGIN` = `ahead_count` when `no_origin` is true.

**Surface `### Local-Only Branch Warning`** when `LOCAL_ONLY_AHEAD ≥ 1` OR `LOCAL_ONLY_NOORIGIN ≥ 1`:
```
### Local-Only Branch Warning
- Branch `<CUR_BRANCH>` has [N] commits not on origin (or does not exist on origin at all).
- Auto-push has either not fired or has been failing silently; `.git/push-failures.log` is [present|absent].
- Verify `.git/hooks/post-commit` is present-AND-executable-AND-routed-to-coordinator-auto-push (session-init self-heals this on next boot, but the day's accumulated commits stay stranded until pushed).
- Recover with `git push origin <CUR_BRANCH>`; if the remote rejects on email-privacy (GH007), set `git config user.email '<id>+<user>@users.noreply.github.com'` and make any benign commit before retrying.
```
**Otherwise:** skip silently.

## Step 1.92: Stale-Stash Surface

On a shared tree an unscoped `git stash` sweeps every concurrent session's uncommitted work into one entry, not just the stasher's own. Both execution paths that could create one are now closed (`block_subagent_destructive_action` on the subagent path, the EM main-loop guard on the other), but entries created before those guards — or by a hand-run stash — sit in `git stash list` indefinitely and are found only by accident. Two such caches (19 entries, ~20,900 patch lines of other sessions' in-flight work) were each discovered by chance, one after three weeks. This step is the detector for the pile itself — acting on a stash once found (whose work it is, whether it's safe to pop or must be inspected first) is a separate judgment call, not this step's job.

Run: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/workday-start-advisory-counters" stale-stashes` — emits one line of JSON with `threshold_days` (default 7), `total`, `stale[]` of `{ref, age_days, subject}`, `advice`, and `error`. Read-only (one `git stash list` spawn; never `show`/`pop`/`apply`/`drop`) and advisory — it never gates.

**Surface `### Stale Stashes`** when `stale[]` is non-empty:
```
### Stale Stashes
- [N] stash entries older than [THRESHOLD_DAYS] days (total in list: [M]).
  - <ref> — <age_days>d — <subject>
- <advice, verbatim>
```
**If `stale[]` is empty, or `error` is set:** skip silently.

Surface `advice` **verbatim** — it leads with the safe forward action rather than the violation, per design-as-offers. Rephrasing it into a scold is the failure mode this field exists to prevent; a stale stash may hold a sibling's only copy of real work, so the forward action is inspect-and-recover, never drop.

## Step 1.10: Addon Health Sentinels

**First**, heal canonical-structure drift at `~/.claude` before the doctor fires. The scaffold is idempotent and additive-only (`mkdir -p` + `.gitkeep`; never overwrites READMEs or existing content). Running it here turns manifest-extension drift into a self-healing event instead of a recurring P-12 AMBER nag across every repo's daily health snapshot:

Run: `python3 -m coordinator_core.install.scaffold_structure --root "$HOME/.claude" --manifest-root "$CLAUDE_PLUGIN_ROOT"` with `PYTHONPATH` set to `<claude-klabauter-root>` (resolved via `$REPO_CLAUDE_KLABAUTER` / `machine-local get repos.claude_klabauter`). Skip with a one-line stderr note if either the claude-klabauter root or a Python interpreter is unresolvable.

Silent on no-op (already-scaffolded). Brief on creation (new dirs introduced by manifest evolution). Always safe to re-run. P-12 stays as the detector for *actual* brokenness (scaffold script error, manifest unreadable) — not for "manifest grew and your install hasn't caught up."

**Then**, refresh the coordinator-claude sentinel: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-doctor-sentinel" --full`

Fires all probes and writes `~/.claude/plugins/coordinator-claude/data/doctor-last-run.json`. Silent on GREEN, brief on AMBER/RED. Always exits 0 — advisory only. (`--full` is required: bare invocation now defaults to `--triage` which does not write the sentinel.)

Plugins that ship a doctor skill write a sentinel at `~/.claude/plugins/<plugin>/data/doctor-last-run.json`. The scan itself (`scan-addon-health.py --red-and-stale`, incl. its SessionStart hook-script existence pass) is one of Step -0.9's addon-health directives (`d-addon-health-*`) — render each `detail` under `### Addon Health` (between `### Auto-Push Health` and `### Priority Suggestions`); nothing to do when the assembler emitted none.

Additionally, run `check-plugin-drift.py` to probe git-state and venv-state drift for registered plugin live installs. On non-empty output (exit 1), append into the same `### Addon Health` section:
<!-- [ok-via-git-propagation] lines exit 0 and are intentionally silent here — the state is benign (live content matches source; sentinel will advance on next install). Do not add surfacing for this state; operators who want to inspect sentinel state run the probe directly. -->
```
Plugin propagation: <summary e.g. "project-rag 22 commits behind, venv ok" or "all clean">
```
No `plugin.mirrors` entries → omit silently. `source_is_live` entries (e.g. coordinator) surface as "n/a-by-design" and are not counted as drift.

Additionally, run `check-claude-klabauter-doctor-sentinel.sh` — a read-only consumer of claude-klabauter's health sentinel at `<CLAUDE_KLABAUTER_ROOT>/state/doctor-last-run.json` (claude-klabauter-owned, written by claude-klabauter's `bin/claude-klabauter-doctor-probe.py`; written elsewhere, never here). On non-empty output, append the line verbatim into the same `### Addon Health` section:

Run: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/check-claude-klabauter-doctor-sentinel"`

Nudges on the same three states `check-plugin-drift.py` nudges on: **absent** (doctor never run on this machine), **stale** (>7d since last run, override via `COORDINATOR_CLAUDE_KLABAUTER_DOCTOR_STALE_SEC`), and **RED/AMBER** (echoes the sentinel's `hint`). Silent on fresh GREEN. CLAUDE_KLABAUTER_ROOT resolves via the canonical settings-home seam (`hooks/scripts/_engine_root.py`), env-first via `CLAUDE_KLABAUTER_ROOT`/`REPO_CLAUDE_KLABAUTER`. Degrades to a fully silent skip (exit 0, no output) when CLAUDE_KLABAUTER_ROOT itself cannot resolve (machine has no claude-klabauter checkout registered — a fleet-topology fact, not a health regression).

## Step 1.10.3: Engine Freshness Drift (claude-klabauter engine)

Run `check-engine-drift.py` — a read-only consumer of claude-klabauter's registered `engine.drift` freshness probe (invoked via `python3 -m coordinator_core.invoke engine.drift` from the claude-klabauter repo root; probes whether the running coordinator engine checkout is fresh against its floor). On non-empty output, append the line verbatim into the same `### Addon Health` section:

Run: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/check-engine-drift"`

Offers-not-nags: silent on `state: clean` (engine fresh, nothing to say), an offer line on `state: behind` (echoes the op's `offer` string), and a distinct "cannot verify freshness" notice on `state: indeterminate` (echoes the op's `notice` string). Silent skip — no output, no error — when CLAUDE_KLABAUTER_ROOT cannot resolve (machine has no claude-klabauter checkout registered, a fleet-topology fact not a health regression) OR when the op is not yet registered on the running claude-klabauter (any JSON-RPC `.error` envelope, e.g. the currently-unregistered case on some machines — DoE is a consumer and must never nag about claude-klabauter's activation state). CLAUDE_KLABAUTER_ROOT resolves via the canonical settings-home seam (`hooks/scripts/_engine_root.py`), env-first via `CLAUDE_KLABAUTER_ROOT`/`REPO_CLAUDE_KLABAUTER`.

## Step 1.10.31: Forwarder Drift (claude-klabauter)

Run `check-forwarder-drift.py` — a read-only consumer of claude-klabauter's registered `plugin_health.forwarder_drift` probe. It compares the CLIs *derived* from a live scan of claude-klabauter's `coordinator/bin/` against the forwarders actually *installed*, in both write locations (the settings-home `bin/` and the `~/.claude/bin` compat mirror), in both directions: derived-but-not-installed (a stale install) and installed-but-not-derived (an orphaned forwarder for a deleted CLI). On non-empty output, append the lines verbatim into the same `### Addon Health` section:

Run: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/check-forwarder-drift"`

Offers-not-nags: silent when derived and installed match. On drift it names every affected CLI and states the remedy (re-run the install to regenerate forwarders) — the names are the point, since drift is typically one or two CLIs out of ~300. Silent skip — no output, no error — when CLAUDE_KLABAUTER_ROOT cannot resolve; a machine with no claude-klabauter checkout is a fleet-topology fact, not a health regression, and an OSS consumer must never have `/workday-start` fail at them. Never fails the ceremony: exit 0 even with drift present.

Why this exists: forwarders generate only from a directory scan at install time, so a CLI landing in `coordinator/bin/` afterwards has no forwarder until the next install run — and nothing else reconciles the two sets. That gap has silently stranded CLIs before (e.g. `gen-settings-hooks`, `run-platform-localize`); the symptom is a 127 mid-ceremony with a remediation message that does not name the cause.

## Step 1.10.4: Onboarding Currency Offer (cwd repo)

Run the onboarding currency detector against the cwd repo: `python3 "<claude-klabauter-root>/coordinator/lib/detect-onboarding-offer.py"` (`<claude-klabauter-root>` resolved via `$REPO_CLAUDE_KLABAUTER` / `machine-local get repos.claude_klabauter`).

- **Non-empty output** → append the line verbatim into the `### Addon Health` section (alongside other health findings). The line is offer-shaped — surface it as a PM-facing suggestion, not a warning.
- **Empty output** → silent (repo is current, not a git repo, distribution repo, or already dismissed).

The detector respects the dismissal sentinel (`<repo>/.git/coordinator-onboarding-dismissed`) — once dismissed it never fires again for that repo. The offer text tells the PM how to dismiss.

## Step 1.10.5: MCP Tool Registration

For each entry in `~/.claude.json mcpServers` (top-level AND `projects.<active-cwd>.mcpServers`), confirm tools registered in this session by scanning the deferred-tools registry in `<system-reminder>` for `mcp__<server-name>__`.

1. Read `~/.claude.json` (top-level + per-project `mcpServers`).
2. Per configured server: skip if `enabled: false` or if the per-project block key ≠ active cwd. Otherwise count `mcp__<server-name>__` matches in session context.
3. **0 matches** → emit under `### MCP Tool Registration`: `- <server>: 0 tools registered. Configured at <transport>:<url-or-stdio-cmd>. Investigate with /<server>:doctor.`
4. **>0 matches** → silent.

**Sentinel:** atomically write `~/.claude/plugins/coordinator-claude/data/mcp-registration-last-check.json` (`.tmp` + `mv`) with: `ran_at`, `verdict` (`RED`/`GREEN`), `checked_servers[]` (`name`, `tool_count`, `transport`, `configured_at`), `red_servers[]`. Feeds `scan-addon-health.py`.

**Render:** when section has content, place between `### Addon Health` and `### Priority Suggestions`; otherwise omit heading. Auto-remediation is out of scope — surfacing only.

## Step 1.10.6: Auto-Reconcile Open Handoffs (claude-klabauter)

The `handoff.reconcile_open` observation (surfaced, never forced-live) is one of Step -0.9's
`judgment_points[]` — a per-handoff auto-reconcile candidate, resolved the same as any other
judgment point, never rubber-stamped. Render non-empty results under `### Auto-Reconcile`,
placed immediately after `### Addon Health`; omit the heading entirely when empty.

## Step 1.10.61: Hidden Deferral — Orphaned Memos (claude-klabauter)

Run `check-deferral-orphan-memo.py` — a read-only consumer of claude-klabauter's registered `deferral.detect_orphan_memo` op. On non-empty output, append the line verbatim into the same `### Addon Health` section:

Run: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/check-deferral-orphan-memo"`

Offers-not-nags: silent on `clean` (nothing orphaned, nothing to say), an offer line on `orphans_found` (echoes the op's `offer` string). Silent skip — no output, no error — when CLAUDE_KLABAUTER_ROOT cannot resolve (machine has no claude-klabauter checkout registered, a fleet-topology fact not a health regression) OR when the op is not yet registered on the running claude-klabauter (any JSON-RPC `.error` envelope — DoE is a consumer and must never nag about claude-klabauter's activation state). CLAUDE_KLABAUTER_ROOT resolves via the canonical settings-home seam (`hooks/scripts/_engine_root.py`), env-first via `CLAUDE_KLABAUTER_ROOT`/`REPO_CLAUDE_KLABAUTER`.

**Not a second inbox inventory:** Step 1.45 already lists every outstanding cross-repo memo — this op does not duplicate that roster. It fires only on the actionable-AND-still-open-AND-aged-past-threshold-AND-unowned subset (a memo of kind `ask` or `proposal`, `status: open`, older than the op's default 3-day threshold, with no plan, baton, or decision record referencing it) — the deferral *signal*, not the memo *roster*. It surfaces as its own distinct `[health]` line under `### Addon Health`, never folded into the Step 1.45 list.

## Step 1.10.62: Hidden Deferral — Partial Stranglers (claude-klabauter)

Run `check-deferral-partial-strangle.py` — a read-only consumer of claude-klabauter's registered `deferral.detect_partial_strangle` op. On non-empty output, append the line verbatim into the same `### Addon Health` section:

Run: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/check-deferral-partial-strangle"`

Offers-not-nags: silent on `clean` (no partial stranglers, nothing to say), an offer line on `partial_strangles_found` (echoes the op's `offer` string), and a distinct "cannot verify" notice on `indeterminate` (echoes the op's `notice` string). Silent skip — no output, no error — when CLAUDE_KLABAUTER_ROOT cannot resolve (machine has no claude-klabauter checkout registered, a fleet-topology fact not a health regression) OR when the op is not yet registered on the running claude-klabauter (any JSON-RPC `.error` envelope — DoE is a consumer and must never nag about claude-klabauter's activation state). CLAUDE_KLABAUTER_ROOT resolves via the canonical settings-home seam (`hooks/scripts/_engine_root.py`), env-first via `CLAUDE_KLABAUTER_ROOT`/`REPO_CLAUDE_KLABAUTER`.

## Step 1.10.63: Global Doctrine Mirror Drift (DoE-claude only)

Run `check-global-doctrine-mirror.py` — a read-only DoE-side probe (no claude-klabauter op involved) that
byte-compares the derived `~/.claude/CLAUDE.md` live copy against its authoritative repo-root
`global-doctrine/` source. On non-empty output, append the line(s) verbatim into the same
`### Addon Health` section:

Run: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/check-global-doctrine-mirror" 2>&1`

Silent skip (exit 0, no output) when the DoE-claude repo has no `global-doctrine/` mirror at
`<repo-root>/global-doctrine/` — this is the expected state on every OSS install and on any
DoE-claude clone that predates the mirror, not a health regression. When the mirror exists and
`~/.claude/CLAUDE.md` matches it byte-for-byte, also silent — nothing to say. A mirrored pair
absent on both sides (`CLAUDE.local.md` today) is a not-in-play skip, never a drift hit.
On drift, append a `DRIFT DETECTED:` block naming both absolute paths, both byte sizes, and a
capped diff excerpt; remediate by running `check-global-doctrine-mirror.py --sync` (`~/.claude` ←
mirror, the authoritative direction — never the reverse). A drift hit here means the live copy was
edited out of band: re-author the change in the tracked `global-doctrine/` authoring copy so the
byte cap and the classification ledger see it, then let the sync overwrite the live copy.

## Step 1.10.64: Orphaned Observer Sidecar Sweep

Advisory, non-blocking sweep for the leak class where a backfilled day can sit with a
committed `*.observer.md` strategic-observer sidecar and zero `## Strategic Review` heading
in the corresponding main daily summary — invisible for days because nothing checked
`archive/daily-summaries/` independently of a single `/workday-complete` Step 4d run. This step is that independent check: it runs on a separate
invocation (workday-start), so it sees a prior day's residue regardless of how or whether
that day's `/workday-complete` terminated — the defining property of this leak class is that
it survives the ceremony that produced it, so the detector cannot live only inside that
ceremony.

`archive/daily-summaries/` is per-repo (each repo running the daily-summary ceremony keeps
its own), so this sweeps the CURRENT repo's directory (cwd-relative), not claude-klabauter's own tree —
unlike the Step 1.10.61/1.10.62 deferral detectors, which are JSON-RPC ops scoped to claude-klabauter's
own state, this is a plain filesystem CLI call against wherever `/workday-start` is running.

Run: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/workday-start-health-probes" observer-sidecar-scan --dir archive/daily-summaries`

Mirrors the Step 1.11 cruft-sweep WARN shape (one advisory line, `(non-blocking)`, never
gates morning orientation) extended just enough to name the specific dates rather than only
signal that *something* is wrong. Silent (no output) when: claude-klabauter root is unresolvable (a
fleet-topology fact, not a health regression — matches the deferral detectors' posture);
`archive/daily-summaries/` doesn't exist yet (a repo that has never run the daily-summary
ceremony, not a leak); the scan finds nothing (rc=0); or the scan hits a usage error (rc=2,
e.g. `stitch-observer-sidecar.py` absent on a stale claude-klabauter checkout — that's the Step 1.10.9
sentinel probe's job to catch, not this step's).

## Step 1.10.7: Cross-Repo Paired-Fixture Sync (conditional)

Repos with paired cross-repo writers ship a `bin/check-fixture-sync.sh` that byte-compares declared fixtures against sibling-repo copies. Catches the two fixture copies silently diverging when one repo updates and the partner's is left stale.

If `bin/check-fixture-sync.sh` exists and is executable, run it, capturing both stdout and stderr (drift reports to stdout, config errors to stderr).

- **Exit 0, no output** → in sync or sibling not on machine → skip silently.
- **Exit 1 (drift)** → surface `FIXTURE DRIFT:` lines verbatim under `### Cross-Repo Fixture Sync`. Re-pin both copies byte-identical via `cross-repo-memo` (never a direct sibling edit).
- **Exit 2 (config error)** → surface stderr verbatim; `tests/fixtures/cross-repo-sync.manifest` has a missing local fixture path.

Advisory only — never blocks.

## Step 1.10.8: Exec-Bit Drift Probe (meta-repo only)

**Retired — the reader this step surfaces was deleted.** The `d-exec-bit-*` judgment-point
emitter (`check-all-shebanged-exec-bits.py`'s `workday-start-health-probes.py` wiring) was
removed from the engine's ceremony-probe wiring — the shebang-implies-100755 invariant it
probed for was itself retired as a POSIX-only portability defect. This step keys off the
judgment-point id, never the CLI by name, so it silently produces nothing rather than
erroring — but it can never fire again either way. Left in place (not deleted) purely as a
record of what used to run here, matching the retirement style above (§ Standalone 14d/7d
aging check).

## Step 1.10.9: Coordinator-Bin Sentinel Probe

`d-claude-klabauter-bin-sentinel` (Step -0.9's brief) — the resolved engine-side `coordinator/bin` and
its `archive-stamp-cli` sentinel. Every skill fence fail-louds on this same condition at
invocation time via the resolve-coordinator-bin snippet; this directive surfaces it once, at
day-start, instead of mid-ceremony. Surface under `### Coordinator-Bin Sentinel` when fired.

## Step 1.11: Cruft Sweep Advisory

Surface filesystem-cruft reclaim opportunities when they cross threshold. Layer 1 floor only — Layer 2 (`/cruft-sweep`) is PM-actioned.

Run: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/cruft-sweep" --class all --dry-run --quiet`

Surface one-line `Cruft sweep candidates: <N reclaimable>, last sweep <YYYY-MM-DD>` in the Morning Briefing when EITHER:
- Reclaimable size > 1 GB (read from the dry-run grand-total banner on stderr), OR
- Staleness > 14d (read the most recent row timestamp from the central state cruft-sweep log — resolved via `coordinator-state-root.py --central`'s `cruft-sweep-log.md` (claude-klabauter-resident) — using `tail -1 "<resolved-path>/cruft-sweep-log.md" | awk -F'|' '{gsub(/ /, "", $2); print $2}'`; if the file does not exist, treat as stale).

PM-actioned only — DO NOT auto-invoke `/cruft-sweep` or `cruft-sweep --apply` from this advisory. The apply pass runs automatically in `/workday-complete` Step 1.5; an out-of-session scheduler (cron / Windows Task Scheduler) is optional additional layering for days when Claude Code is not opened.

Silent when below both thresholds.

## Step 2: Doc Freshness

1. Find last update-docs run: `git log --oneline --grep="update-docs\|workday-complete" --since="7 days ago" -1`
2. Find commits since: `git log --oneline <last-update-docs-commit>..HEAD`
3. **Commits exist:** Flag: _"Docs are stale — [N] commits since last update-docs. Recommend `/update-docs` before feature work."_ Do NOT dispatch automatically — it commits files and would race with the working tree.
4. **No commits since:** "Docs are current."
5. Run the harvest-debt probe and surface its output verbatim if non-empty (flag only — never auto-run `/distill`): `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/check-harvest-debt"`

## Step 3: Test Staleness

1. Detect test framework (same as bug-sweep Phase 0).
2. If tests exist: find most recent test-related commit/CI run; find code changes since. **If code changed:** Flag: _"Tests haven't been run since [N] commits ago. Recommend running test suite."_ Don't run automatically — PM decides.
3. No tests → skip silently.

## Step 3.5: Bug Sweep Staleness

Check if a bug sweep should be suggested — based on **code churn since last sweep**, not just calendar time:

1. Read `state/bug-backlog/.meta.yaml` (written by `/bug-sweep`) for its `last_sweep_at:` date and `last_sweep_commit:` hash; count open items by severity by enumerating `state/bug-backlog/*.yaml`.
2. If no backlog exists: count source files (`find . \( -name "*.py" -o -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.cpp" -o -name "*.h" -o -name "*.cs" -o -name "*.go" -o -name "*.rs" \) | grep -v node_modules | grep -v __pycache__ | wc -l`). If >50: _"No bug sweep has ever run ([N] source files). Recommend running bug-sweep."_ If <50, skip silently.
3. If backlog exists: count commits since anchor (`git rev-list --count <sweep-commit>..HEAD`).
4. **Suggest sweep if:** >50 commits AND >7 days since last sweep (churn + time floor prevents sprint-mode nagging), OR >14 days AND >20 commits (moderate churn + time). Message: _"Bug sweep last ran [date] ([N] commits ago). Recommend running bug-sweep before new feature work."_
5. Otherwise: "Bug sweep is current ([N] commits since last sweep)."

## Step 3.6: Project-RAG Staleness (conditional)

Project-RAG staleness (`d-rag-staleness-regen`, from Step -0.9's brief — same resolution
`workstream-start` and `workweek-start` name for their own cadences, computed once per the
shared reader, not three times) — when the directive fires, inline its `detail` into the Morning
Briefing under a new **Project-RAG** line (template below). Silent when the assembler emits none
(current, or no project-RAG tool registered this session).

**Flag-only — never auto-run.** A reindex can race with an open editor. PM invokes manually after `/workday-start` completes.

## Step 4: Priority Alignment

Run: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/whats-next"`

Emits: improvement-queue head (top 5), `docs/project-tracker.md` Ready/Executing rows, open handoffs. Use as-is for § Priority Suggestions; do not reconstruct from prose.

**Reconcile active work against completed archive:** `query-completions.py --where "created>=$(date -d '30 days ago' +%Y-%m-%d 2>/dev/null || date -v-30d +%Y-%m-%d)" --sort "created" --format json` (fallback: `archive/completed/legacy/<YYYY-MM>.md` if query empty). Cross-reference tracker Ready/Executing items and open handoffs:
- **Match found** → Flag: _"Tracker shows [workstream] as [status], but archive/completed records it shipped on [date]."_
- Fuzzy match on names/descriptions — when unsure, flag as "possible match — verify" rather than auto-resolving.
- Report mismatches under **Alignment Check** in the Morning Briefing.

## Step 5: Morning Briefing

Present a concise morning report:

```markdown
## Good Morning — Workday Start

**Date:** YYYY-MM-DD
**Branch:** [current branch]

### Branch Span Mismatch
_(Omit this section entirely unless Step 0.45's `span-assert` exited `1`. When present, render its stdout message verbatim — this is the loudest tripwire in the briefing and PM should see it first.)_

### Context Freshness
- Handoffs: [N] actionable for today, [M] stale (flagged for /update-docs archival)
- Docs: [current / stale — N commits since last update-docs]
- Tests: [current / N commits since last run — suggest running]
- Health: last daily check [today/N days ago], last weekly audit [N days ago]
- Atlas: [N systems mapped, M stale >90 days / no atlas]
- Bug backlog: [N open (P0: X, P1: Y) / empty / no backlog]
- Bug sweep: [current (N commits since) / suggest sweep (N commits since last)]
- Cross-repo commitments: [N open sibling commitments — oldest Nd] _(from Step 1.6; omit this line entirely when the directory is absent or empty, per Step 1.6's skip-silent rule)_
- Project-RAG: [{verdict} — {age}, {code_commits} commits / {asset_changes} assets / verdict source: {recommendation_command}] _(omit this line if verdict is `current`)_
- Tools: [missing optional tools, if any — see below]

### Tool Availability
Check PATH for `scc` (also `~/bin/scc`) and `shellcheck`. Surface install hint for each missing tool (`winget install BenBoyter.scc` / `winget install koalaman.shellcheck`). When both present: _"Tools: scc + shellcheck available."_ Only nag when missing.

**Fan-out tooling:** claude-klabauter `coordinator/bin/fan-out-dispatch.py` (compiler — overlap pass + scoped prompts); dispatch the compiled wave and hold the EM-serial commit (not a skill — no `/fan-out` command). Use for any multi-chunk parallel or serial dispatch instead of hand-authoring executor prompts.

### Handoffs
- **Continuation:** [N open, M aging, K likely-claimed]
- **Shipped sweep:** [N shipped handoffs archived / omit if none / WARNING line verbatim if present]
- **Spinoffs awaiting pickup:** [list each: filename — title — age — workstream]
  _(Omit this bullet if no spinoffs exist.)_
- **Stale spinoffs (≥14 days):** [list each with a one-line nudge]
  _(Omit this bullet if no stale spinoffs exist.)_
- **Tracker:** durable snapshot at `state/handoff-tracker.md` (refreshed by `/workstream-complete` and `/handoff`; ad-hoc: `render-handoff-tracker.py`).

#### Recent roadmap (last 90d, top-10 by size)
_(Results from Step 1.55 query — one bullet per row. Render "(none)" when the query returns zero rows. Heading always present — count-always per orientation-surfacing-doctrine.)_

### Alignment Check
- [N mismatches found between active trackers and completed archive / all aligned]
- [List each mismatch: "Tracker: X is Executing — Archive: shipped YYYY-MM-DD"]
- [List each handoff flagged as likely completed]

### Orphan Sweep / Agent Worktrees / Auto-Push Health / Addon Health / Test-Red Delta
Each section omitted unless its step (0.5 / 0.6 / 1.9 / 1.10 / 1.66) produced surfaceable findings; render only the non-empty rows from that step's structured output.

### Priority Suggestions
Pull from the active state: bugs (top severity first), stale sweep, stale tests, stale atlas, tracker Ready rows, deep debt backlog. Order by urgency, not by template.

### What should today's focus be?
[Surface tracker Ready items, handoff action items, and PM-facing options]
```

After synthesizing the Priority Suggestions, for each suggestion, emit a structured daily goal event. Run one invocation per suggestion (moved outside the Morning Briefing markdown fence per review A-F12, to prevent nested-fence parse failure):

Run: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/append-goal-event" --period day --period-value <today ISO date, e.g. 2026-06-22> --text "<the suggestion>"`

Runs automatically as part of the ceremony — no new manual PM step.

**Set marker:** `d-workday-marker-write` (Step -0.9's brief, AC-7 marker-freshness dedup — the same cadence-parameterized gate `workstream-start` reads and `workweek-start` owns for its own cadence) — write `state/.workday-start-marker` with today's date (single line) once this ceremony completes. Workstream-start checks this one file.

## Step 5.5: Write Orientation Cache

Generate `state/orientation_cache.md` — a compact 40-60 line summary the SessionStart hook injects instead of raw repomap/DIRECTORY content. Skip if `tasks/` doesn't exist. Health Snapshot includes a Step-1 mirrored split: one line for continuation handoffs, a separate line for spinoffs (omitted if N=0).

**Full content derivation per section:** see `pipelines/workday-start-internals.md` § Step 5.5.

## Step 5.6: Project Post-Ceremony Command Hook

Advisory, non-blocking. Calls the generic per-repo post-ceremony command hook so a consumer repo can register its own opt-in command (e.g. a settled-state publish step) to run once orientation has settled. Silent no-op when the repo declares no `workday_start_post_command:` key in `coordinator.local.md`.

`d-ceremony-hook-output` (Step -0.9's brief, cadence-parameterized on `workday-start`) carries the hook's output — print it verbatim; a non-fired directive is a non-blocking WARN, never a hard fail.

**Asymmetric vs the other three ceremonies:** workday-start's user-facing summary is Step 5 (Morning Briefing), which renders BEFORE this Step 5.6 settle point — so the hook line CANNOT be folded into an already-rendered summary template the way workday-complete/workweek-start/workweek-complete do. It emits as a STANDALONE trailing line printed by this step itself, after the Morning Briefing has already been shown. This is fine functionally — it preserves the settle-after-cache-write ordering — but do not try to retrofit the line into the Step 5 template.

## What This Does NOT Do

Run bug-sweep / daily-code-health / deep-architecture-survey / update-docs (dedicated invocations). Merge to main (use `/merge-to-main`). Choose work (`/workstream-start`'s Engage section).

## Relationship & Concurrent Safety

`workday-start` runs once/day; `/workstream-start` runs per-session and skips redundant checks when the marker is fresh. `/workday-complete` is the evening counterpart. `/update-docs` and `/bug-sweep` are recommended (not dispatched) when state warrants. Read-only for all tracking files; writes only `state/.workday-start-marker`. Failure mode to avoid: acting on stale handoff items a concurrent session shipped — Step 1.3's git reconciliation is the prevention.

If `$ARGUMENTS` is provided, include as a focus hint: _"Requested focus: {arguments}"_
