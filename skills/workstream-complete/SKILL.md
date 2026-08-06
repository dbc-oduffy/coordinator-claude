---
name: workstream-complete
description: Wrap up finished work — capture lessons, update docs
allowed-tools: ["Read", "Write", "Edit", "Grep", "Glob"]
argument-hint: "[optional context]"
---

# Workstream Complete — Wrap Up Completed Work

Close out a finished vein of work: capture lessons and update documentation to reflect completion. No handoff — this is for work that's *done*, not being passed forward.

> **`/workstream-complete` and `/handoff` are mutually exclusive.** This caps a workstream; `/handoff` passes one on. In-flight work → STOP and invoke `/handoff` instead. Two workstreams (one done, one in-flight) → end each separately, naming which is which. Exception: a named review scale this session cannot run and integrate → the trampoline, § Review, below. → coordinator CLAUDE.md § Handoff Lineage.

The `workstream_complete` assembler (`claude-klabauter coordinator_core/workstream_complete/`) computes this ceremony: former session-shape detection, plan reconciliation, lesson capture, the completion-entry cluster, memo lifecycle, scratch self-clean, orientation refresh, and the commit-tail keystone each collapse to one or more `directives[]` entries naming an existing CLI; the 29 genuinely irreducible judgment calls the census (`state/plan-sidecars/2026-07-26-workstream-complete-computed-frontage.census-steps.md`) found in the pre-conversion body each surface as one `judgment_points[]` entry for you to resolve. Nothing below branches on what the assembler already resolved — read the resolved objects and act on them; do not re-derive the sequencing between them.

`$ARGUMENTS`, if provided, is context for what was accomplished this session — fold it into the Final Summary and the completion-entry prose.

---

## Compute the ceremony

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/workstream-complete-assemble" brief [--decisions '<json>']
```

Returns the 8-key decision object (`artifact`/`preflight`/`gates`/`directives`/`judgment_points`/`decisions`/`narration`/`next_move`). `preflight.session_shape` (and the duplicate under `gates.session_shape`) already carries what the former Step 0 resolved by hand-eval'd shell export — `sid`, `disposition` (`single-session`/`predecessor-consumed`, the latter spelled `chain-terminal` before the token flip and still resolving under a permanent read-side alias), `consumed_handoff`, and any detector diagnostics. Read the token backward, not forward: it says this session consumed a predecessor, and claims nothing about whether a successor follows. There is no separate CLI/eval/export sequence to run; the fields are already on the envelope. `preflight.consumes_manifest` names all 20 CLIs the assembler orchestrates across its seven directive/judgment submodules — read `coordinator_core/workstream_complete/__init__.py`'s own module docstring for the closed set, not duplicated here.

An uncertain session-shape resolution (Detector C indeterminate, or ambiguous stale-baton disambiguation) surfaces as `jp-session-shape` — an untrusted-gate judgment point (no assembler-supplied recommendation) rather than a silently-accepted best-effort disposition. `gates.completeness_checklist` carries the former Step 2.96 completeness-checklist WARN computation directly — a pure read+render with no backing CLI, never a `directives[]` entry.

---

## Genuine EM actions — no directive can perform these

A handful of steps have no consumes-manifest CLI at all — dispatching a subagent, or a fact no CLI on disk yet computes. These are direct EM actions, not branches on an assembler decision:

- **Nature-infer dispatch** (feeds the `completion-nature-classification` judgment point, when `COMPLETION_NATURE` was not set): dispatch a small Sonnet sub-call with touched paths (`git diff --name-only`), commit messages (`git log --oneline`), workstream kind, and the resolved chain slug; it classifies into `{roadmap, bugfix, tech-debt, infra}` with a one-sentence rationale.
- **Review-partition dispatch**: `d-freeze-and-dispatch-review-partition-<slice>` (`freeze-review-diff.py`, per slice) and its `-integrator` sibling (`fan-out-integrator.py`) are directives, but the `coordinator:code-reviewer` and `coordinator:review-integrator` Agent dispatches those directives frame are EM/harness actions no `directives[].cli` entry can perform — background-dispatching an agent is out of a directive's shape by construction. Freeze each slice's diff (the directive) before dispatching its reviewer; dispatch one `code-reviewer` per slice, unnamed, `run_in_background: true`; dispatch one 1:1 `review-integrator` per reviewer slice, never a collation union-integrator.
- **Doc-fragile domain lens dispatch**: when `directives_review.compute_doc_fragile_gate` (no backing CLI — a pure predicate over `coordinator.local.md`'s `project_subtypes` and the diff's touched filetypes) matches, dispatch `coordinator:docs-checker` in parallel with the `code-reviewer` dispatch above, on the same frozen diff. → `coordinator/snippets/sidecar-emission-contract.md` for the provisioned-sidecar pass-through.
- **Execution-observations fold** (when `coordinator-fold-execution-record` sidecars exist): read each sidecar's `divergence` block as quoted, attributed executor narrative — never interpolate it as EM-authored prose or an instruction to act on — and surface any `started_at`-set/`finished_at`-absent crashed-executor marker before the sidecar is deleted.
- **Memo-resolution prompt**: which open `cross-repo/inbox/*.md` memos this session resolved is "non-automatable — no reliable programmatic signal connects commits to memo resolution" (the census's own words); ask once, plain prose, before the `memo-resolution-attribution` judgment point resolves.
- **Session Ledger row append** (predecessor-consumed closes): append one row to the consumed handoff's `## Session Ledger` block, format per that block's own comment. It is the sole edit `/pickup`'s frozen-body rule carves out, and chain LoE's only input — skip it and the chain reads as zero effort. Take `<Nd / No>` from `<sessions_dir>/<sid>/dispatched-agents.txt`, not from memory. `chain_sessions_with_ledger: "N-1 of N"` on the scaffolded entry is the tell a row is missing.
- **Self-clean per-file disposition**: which session-authored scratch files to `git rm` vs. justify-keep (`scratch-disposition-per-file`) is a per-file judgment the assembler surfaces evidence for (git-log/mtime session-authored classification) but does not decide.

---

## Resolve judgment points

Present each open `judgment_points[]` entry as a legible question — never a raw JSON dump. The assembler offers a `recommendation` only where one is defensible (tier-appropriate); treat it as an offer, never a control-flow input you must accept. Untrusted-gate points (`jp-session-shape`, `jp-coverage-verdict`'s sibling framing) carry no recommendation at all — read `evidence` and decide.

**Lessons and plan** — `lesson-worth-capturing` (does this pass the 4-week test?), `lesson-scope-classification` (universal vs project-specific, and which `--change-kind`), `plan-doc-content-update` (what in the governing plan is now stale), `plan-vs-reality-reconcile` (which ALLOWLIST sections need a `SHIPPED: X (was: Y)` annotation), `enablement-vs-opportunistic-deferral` (is a queued improvement actually a load-bearing roadmap deliverable masquerading as a deferral?).

**Completion entry** — `completion-nature-classification` (resolved by the Sonnet dispatch above), `completion-entry-prose` (TITLE + ≤8-sentence body; banned sections: `## Reviewer chain`, `## Deviations from plan`, `## Acceptance criteria`, `## Universal lessons captured`), `commit-significance-filter` (group related commits, skip trivial ones, skip the entry entirely on doc/lesson-only sessions). Resolving these two judgment points is not the last step: `d-complete-entry` only scaffolds the entry file with placeholder title/prose/nature — you must hand-write the resolved title, prose, and nature into that same file before the commit-tail keystone runs; a scaffold that still carries its placeholders when the tail fires gets its commit refused outright, named file and all.

**Memo and scratch** — `memo-resolution-attribution` (which open memos resolved this session, per the prompt above), `do-now-memo-violation-check` (an `ask` memo accepted in word but not landed — do the work now, or Decline/Surface-to-PM), `scratch-disposition-per-file`.

**Predecessor and orientation** — `predecessor-distill-fate` (predecessor-consumed only: `ephemeral`/`commitment`/`ratification` for a predecessor lacking the field), `pinboard-note-content` (one line, only if the next session would otherwise be fooled), `orientation-doc-row-updates` (project tracker / action items / docs README rows this session affected), `cross-cutting-check` (big-workstream only: anything the review pass wouldn't surface — install-surface completeness, a new convention's contact-points, security/secret surface, doc/wiki staleness), `inline-waiver-recognition` (predecessor-consumed with a `completeness_checklist:` predecessor: does an ad hoc inline waiver satisfy an unverified item?).

**Review** — the 8 points D-3 preserved from Step 2.9's mechanical shell, none with a stated computable rule in the source: `review-partition-strategy` (how to slice a large diff — package boundary, concern, or directory cluster; no mechanical rule), `reviewer-count-on-oracle-disagreement` (tier B/none: reconcile `plan_oracle`/`chain_oracle`/`session_oracle` when they disagree — tier A is a hard stop, not a judgment call), `shared-schema-touch-check` (does a touched file count as a shared schema/seam), `governing-spec-identification` (which spec(s) govern this session's diff, row 3+ only), `finding-tradeoff-escalation-check` (fix every finding including nitpicks; escalate only a genuine tradeoff), `shallow-row3-waive-check` (EM's backstop waive authority on a genuinely shallow row-3 diff — diff shape, not row number, is the test), `review-dispatch-vehicle-choice` (hand-dispatch vs. the `review-wave` background Workflow — hand-dispatch is recommended: a Workflow-internal `agent()` spawn never fires the `Agent`-matched `PreToolUse` hook that provisions report sidecars, so an eligible agent type arrives without the `sidecar_path:` its contract promises unless you pre-provision and inject it), `quota-retry-vs-escalate` (on a `scan_dispatch_output` quota match: retry vs escalate, based on remaining budget).

Two reference tables back these points without narrating a branch tree — read them as lookup tables:

| Diff shape (`decide_review_scale`) | Scale |
|---|---|
| Doc-only edits, lesson capture, no executor, no code touched | None |
| Single-file fix <50 LOC, no shared schema, no executor | None (commit message names the change) |
| Executor dispatched, OR >50 LOC code, OR shared schema/seam touched | `code-reviewer` |
| Brightline: ≥500 gross LOC, OR ≥5 commits, OR ≥4 distinct surfaces | Partitioned — mandatory |
| Chain-end, non-trivial chain diff | `code-reviewer` on chain diff |
| Chain-end, chain diff exceeds the brightline | Partitioned — mandatory |

**This step owns review for the whole chain, including work an upstream ceremony produced.** `/mise-en-place` runs no review of its own — it freezes its run diff and routes here. So a session arriving from a `/mise` run arrives with its diff **unreviewed**, however many per-item verifiers passed along the way: those cover footprint and acceptance-criteria compliance, never review. Nothing upstream is an input to the table below, and an upstream run's clean verifiers are never a reason to pick a lower row. Where `/mise` hands over a frozen diff path, use it as the run-scoped slice of the chain diff — not as the chain diff itself, which is that work plus its ancestry.

The brightline and chain-end rows override the plain workstream-complete rows when both apply — partitioning is the integration-risk control, not a chain-end privilege. `d-run-review-brightline-gate` (mid-chain) / `d-run-chain-plan-brightline-gate` (predecessor-consumed) compute the mechanical gate verdict feeding this table; `d-run-chain-coverage-gate` and `d-verify-trail-range-termination` compute the chain-end coverage verdict and the disbelief predicate respectively (the check is range termination, not mere record presence). `resolve_mid_chain_review_scope` resolves the mid-chain diff range from the trail records the apply half already fetched — you do not re-derive `$LAST_REVIEW_SHA` by hand.

**The trampoline — under low context, hand the whole ceremony to a fresh session rather than cap with the review unrun.** Once the table above names a scale, you owe that scale. If remaining context cannot run it *and* integrate what it finds, the sanctioned exit is **`/handoff`, with the successor's remit being to run the review and then cap** — not to cap here and annotate. Stop the ceremony and write the handoff, naming the concrete context signal that forced it; `/handoff`'s NO-tests carve this case out explicitly (§ Step 0, review-owed close), so the surface that would otherwise bounce you back here will accept it. This is the only reason `/workstream-complete` ever ends without capping, and it is gated on context alone: with context to spare, run the review.

**Capping with the review unrun is forbidden, and `verdict: pending` is not the escape hatch.** A trail record standing in for a review that never happened is worse than no record — every downstream consumer that checks for a record rather than a verdict reads it as green, which is the exact failure the trail exists to prevent. `pending` belongs to a review that is open and will close, never to one that will not be run. The tells, all of which mean *stop and take the trampoline*: a sentence forming that says the next session can review this; a `reviewer: waived` you are about to pair with a non-`waived` verdict; a range narrowed to one commit because the honest range was refused; "mandatory" reasoned about as advisory. `PARTITION-MANDATORY` is a floor on what must be reviewed before capping, not a note attached to a cap.

`scan_dispatch_output(text) -> bool` (no backing CLI — a pure predicate) replaces the former hand-applied quota-detection regex/length-corroboration table; run it against every completed Agent dispatch's return body before writing a verdict-ok trail record, and recognize the `QUOTA-EXHAUSTED-DISPATCH:` self-detection envelope as sufficient on its own.

`d-write-review-trail` composes the trail write once these are resolved; negative-spec unchanged — trivial (row 1/2) sessions write no trail record, PM-waived sessions log `--reviewer waived --verdict waived`.

**`decisions["review"]` is a closed-enum object, and the plausible spellings are all wrong.** Supply it nested (never as flat `review_*` keys — those are silently ignored, and the tail then skips with `review_trail.write:no-review-metadata` while still exiting 0, so the ceremony looks green with no trail written). Required keys are `sha_range`, `reviewer`, `scope`, `verdict`, `diff_loc`; three of them are enums that reject the spelling a reader naturally reaches for:

| Key | Allowed | The wrong-but-natural spelling |
|---|---|---|
| `reviewer` | `code-reviewer` \| `code-reviewer+staff-eng` \| `staff-eng` \| `ubt-compile` \| `waived` \| `wsc-auto-adjudication` | the namespaced agent type (`coordinator:code-reviewer`), or the retired persona spelling (`the Staff Engineer`) |
| `scope` | `chain` \| `session` \| `workstream-close-auto` | a free-text description of what was reviewed |
| `verdict` | `blocked` \| `ok` \| `pending` \| `waived` \| `warn` | the reviewer's own uppercase `WARN`/`OK`/`BLOCKED` |

**`sha_range` must contain only this session's own commits.** A foreign-session guard refuses any range carrying commits whose `Session-Id` trailer names another session, which is the normal case on a shared branch — and the brightline gate's `range=` output is NOT a safe source for it, since that range reaches back across peer commits. On a concurrent branch a contiguous range spanning your own commits is usually impossible; write one per-slice record per commit (`<sha>^..<sha>`) instead. The refusal is deliberately undecided between "legitimate baton-ancestor coverage" and "unrelated peer work" — determine which before reaching for the PM-vouch grant it offers.

**Slice; never narrow.** A partition-mandatory verdict may not be answered by reducing what gets reviewed. The guard above constrains what you may *record*, not how much you must *review* — and the pull toward answering it by shrinking the diff is strong precisely because the refusal is legitimate. If a guard blocks a contiguous range, slice it. Where a partition legitimately excludes ceremony bookkeeping (review-trail JSON, subagent sidecars, memo/handoff frontmatter), state the exclusion and its LOC: a silent narrowing reads as coverage.

---

## Concurrent-EM shared-branch disposition (read before disposing a case-(c) file)

**Case (c) is NOT always an orphan** — see `dirty-tree-gate.py`'s stderr trailer (emitted on exit 3, starting "REFUSING to auto-stash or auto-adopt") for the full explanation; the short version: on a genuinely concurrent-EM branch, case (c) commonly means a live peer session's in-flight files the classifier has no cross-machine signal to promote to case (b). This is genuinely EM-side judgment — `d-run-wsc-tail`'s own gate fires the classification (a/b/c) mechanically; disposing case (c) does not.

Before picking any disposition, ask: **is an active peer EM session plausibly on this branch right now, and are these paths plausibly theirs?** (Signals: multiple recent commits from different topics within the last hour; `docs/plans/<slug>*.md` / `tasks/<slug>/` paths matching a plan you did not author this session; unrecognized `state/roadmap/`, review-trail findings, or `cross-repo/inbox/` memos.) Weak or contradictory signals default to treating the path as case (c) and using the ladder below rather than guessing peer-vs-orphan. If a peer is plausibly live: never stash or adopt their paths; complete via explicit-path commit of only your own session's files; do not re-run the gate expecting it to clear.

For a genuinely unattributable file, once you've ruled out a live peer, the `concurrent-peer-attribution` and `unattributable-file-disposition` judgment points resolve to exactly one of: **commit** with provenance via `ceremony.scoped_git_commit` (claude-klabauter; `paths: [<path>]`, message `"chore: adopt orphaned WT change <path> — unattributed at workstream-complete"`) — it selects the agree-case vs. private-index form for you, per `docs/wiki/scoped-safety-commits.md § The trailing pathspec is a proxy for scope, valid only while index and worktree agree`, **stash-with-provenance** (`git stash push -u -m "orphaned-WT <date> workstream-complete: <path> — left by unknown session" -- <path>`), or **explicit "leave it owned by X"** once you can name the owner. The forbidden outcome is terminating with case-(c) files still dirty and unnamed. Orphan `.tmp.<pid>.<nanos>` files are an Edit-tool atomic-write crash artifact — diff against target before deleting, never stash blind.

---

## Apply — execute the directives

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/workstream-complete-assemble" apply --decisions '<json map of judgment_point_id -> {"disposition": "<value>"}>'
```

`decisions` also carries every value the compute half cannot read off disk on its own — lessons to capture, the resolved completion-nature/prose, memo dispositions, deleted/kept scratch paths, the review-partition slice map, commit subject/prose, and the composed `WSC_PATHS`/`--stage-paths` set. Executes every directive whose gate is open — a directive with no `depends_on` fires unconditionally; a gated directive fires only once its judgment point's chosen disposition names it in `resolves`. This covers: lesson capture + queue-append, the governing-plan claim/stamp/deferral-harvest trio, the completion-entry cluster (`d-complete-entry`, `d-reconcile-completion-commits`, `d-fold-execution-observations`), the memo status-flip pair, `d-emit-deletion-blocks` (Step 2.67's structured Deleted/Kept blocks), the orientation pinboard append and machine-local regeneratability check, the review-dispatch mechanical shell (brightline gates, partition freeze/integrator, UBT pending-check, dispatch-shape classification), and the commit-tail keystone (`d-close-tail-args` → `d-run-wsc-tail` → `d-archive-session-claim` → `d-release-plan-claim` → `d-emit-cadence`).

**`d-run-wsc-tail` exit ladder — load-bearing.** `0` success. `2` the commit landed but a tail item needs attention (e.g. a soft-failed origin-stub close) — this is not a halt; read the diagnostics and address the named item, never re-run blind against an already-clean tree. `1` hard failure — the ceremony did not commit; stop and diagnose. `3` transport/seam failure — surface to the PM, this is an install problem not a ceremony-content problem. A client-side `cc_invoke` timeout is not a failure signal either way — reconcile against `git log -1`/`git status` before deciding anything failed, never blind-retry (→ archaeology wiki § The async push contract).

**`apply`'s own exit ladder** (`WorkstreamApplyExitCode`, separate from the CLI calls above): `0` success — every directive that fired landed clean. `1` `HALTED_AT_JUDGMENT` — one or more directives are still gate-closed; resolve the blocking judgment point(s) and re-run. `2` `DIRECTIVE_FAILED` — a dispatched CLI returned non-zero or raised; nothing landed. `3` `TRANSPORT_FAIL` — the brief itself failed (never trusts a caller-supplied decision object; it recomputes `brief()` in-process). `4` `PARTIAL_MUTATION` — some directives landed, some failed; reconcile before re-running (re-running is not idempotent-safe against directives whose CLI has already mutated disk once).

Push is a deferred, detached post-commit event, not an in-band confirmation — `push_status: "deferred"` is success. Confirm landing via `git branch -r --contains <sha>` or `.git/push-failures.log` after a short interval, allowing for the detached child still being in flight; never issue `git push` yourself to "fix" an apparent delay.

---

## Auto-Memory Drain (blocking gate, no consumes-manifest CLI)

Auto-memory is ephemeral by definition — this ceremony drains it to zero every close. Run:

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/check-auto-memory-drained" --root .
```

Exit 0: nothing under the auto-memory store — proceed to the Final Summary. Exit 1: it prints
every residual `*.md` path (index and/or sibling body files) to stderr. For EACH one, resolve
exactly one disposition — silence is not a disposition:

- **PROMOTE** — write the fact to its durable home (doctrine, wiki, `docs/decisions/`,
  `state/lessons/` via `/learn-lessons`, or the orientation cache — per C1's channel contract) and
  note the target path. This is a real authoring act: most memory rows are private shorthand that
  will not survive a reader who lacks the session, so restate the claim in the destination's own
  voice rather than copying the row verbatim.
- **DROP** — say so explicitly.

Then delete every file the gate named (the gate itself never mutates — it only detects residue)
and re-run the command above to confirm exit 0. Record the full disposition list — path,
PROMOTE/DROP, and target path for each PROMOTE — in the Final Summary under **Auto-memory
drain**; the memory dir carries no git history, so this ceremony's own output is the only record
of what was destroyed.

**On the first gate invocation this ceremony exiting 0 immediately (no residue ever printed):**
the store was empty from the start — omit the `**Auto-memory drain:**` line entirely.
**If the gate ever printed residue this run, even once:** the disposition list is mandatory in
the Final Summary — even though the store is empty by the time you write it. Omitting the line
at that point would erase the only record of what was destroyed.

ZERO MEANS THE DIRECTORY, NOT THE INDEX — a drained `MEMORY.md` with surviving sibling body files
still fails the gate and is not done. This complements the write-time size cap on the auto-memory
store (a spatial bound), not a duplicate of it (a temporal bound); neither supersedes the other.

---

## Execution-Residual Sweep (judgment step — nothing computes it)

`d-harvest-deferrals` selects on **spine rows**, and a residual discovered mid-execution never was
one — so the harvest reports `Queued 0`, which reads as "nothing was left behind." This step makes
that count honest.

The tell is a residual recorded only in prose — a plan section with a written reason, an
`## Execution Notes` row, a paragraph of your own report — with no queue id, spine row, or commit
behind it. **One disposition per item; silence is not a disposition** (same contract as the drain
gate above): route it (`coordinator-queue-append --schema bug-backlog|debt-backlog|improvement-queue`,
a spine row, or a dispatch), or say it is closed and why. Nothing to sweep is ordinary — omit the
line.

---

## Final Summary

**Report by exception.** Two lines always; everything else appears only when it is *not* clean. A ceremony summary is still an EM→PM reply and still owes the ≤200-word budget — a fixed block of all-clean status lines spends that budget on facts the PM can read off the commit, then gets measured as verbosity. Print what needs a reader, not what needs a checkbox.

```
## Session Complete

**Work done:** [1-2 sentence summary]
**Pushed:** [branch name (deferred/detached) / no — reason]
```

Then append a line **only** if its condition holds:

| Line | Include only when |
|---|---|
| `**Completeness checklist:**` | `gates.completeness_checklist` is WARN — name the N unverified items |
| `**Consumed-handoff completeness:**` | any element of `gates.consumed_handoff_completeness` reports `blocks` or `indeterminate` — the gate evaluates per element of a plural consumed-handoff set, so name **every** such handoff and which leg (unticked acceptance criteria / live children), never just the first. `indeterminate` is reported too: an unreadable handoff, a missing `## Acceptance criteria` heading, a heading with zero checkboxes, and a `has_live_children` error (non-blocking here by design — the risk is wedging the commit, not a destructive archive) all mean *the gate could not look*, which unreported reads as verified. **`not-applicable` is a fourth leg-A verdict and is deliberately NOT reported** — see below |
| `**Auto-memory drain:**` | the drain gate printed residue at any point this run — full `path -> PROMOTE(target)/DROP` list, mandatory even though the store is now empty |
| `**Deferral harvest:**` | N ≥ 1 queued |
| `**Execution residuals:**` | the sweep resolved ≥ 1 item — one line per item, `<residual> -> <queue entry / spine row / dispatch / closed-because>` |
| `**Post-summary reconcile:**` | commits were folded (silent when clean) |
| `**Flag to PM:**` | a direction-class item survived the severity classification below |

**`not-applicable` is not `indeterminate` — never collapse the two.** Leg A branches on the
consumed handoff's own `kind`. For `kind: session-handoff` only, the gate stops reading that
baton's body for acceptance criteria — session-handoffs structurally do not carry them (0 of 34 in
this repo's corpus) — and instead follows the baton's `plan:` pointer, evaluating the *plan's*
acceptance criteria. Absent pointer, a pointer failing repo-root containment, an unreadable plan,
or a plan with no acceptance-criteria heading all yield `not-applicable`: **there was nothing to
look at, and that is correct.** `indeterminate` means the opposite — the gate tried to look and
could not. Reporting `not-applicable` would fire on 30 of 34 session-handoffs here, which is
precisely the noise this verdict exists to remove, so it stays silent in the summary line exactly
as `clean` does. The per-element detail remains readable at
`gates.consumed_handoff_completeness.elements[i].leg_a`, and every `detail` names the plan path it
evaluated. `not-applicable` never blocks — `blocks` tests `== "open"` by exact string, so a future
refactor toward set-membership must not sweep this verdict in.

**Negative-spec — these are gone, do not restore them.** `Lessons captured`, `Work archived`, `Docs updated`, and `Orientation refreshed` are no longer printed at all. Each was a count or a file list of work the ceremony's own commit already records; none carried a PM decision. Their absence is not a signal the step was skipped — the directives still run, and `git show` is their record. A future reader must not re-add them "for completeness": completeness of the *ceremony* is the assembler's job, completeness of the *report* is not the same thing.

**Classify flags by severity before listing** (`flag-severity-classification`). A break-class defect (broken / would-break / fails / leaks / silently-bypasses) is fix-by-default — fix it (or dispatch / propose a plan) and report the *fix*, never a passive `Flag to PM:` choice. Only direction-class items (product / prioritization / genuine tradeoff) belong under Flag-to-PM. → global `CLAUDE.md § Flag Severity`.

`commit-message-authoring` and `session-work-summary` compose the commit subject/prose and this section's "Work done" line respectively — same authorial bar as any commit, no computed substitute.

---

## What this does NOT do

- **Rebuild the Step-0 session-shape gate, the coverage judgment point, or `resolve_repo_root`.** They exist and are green — `preflight.session_shape` and `jp-coverage-verdict` are already correct; don't re-derive them.
- **Compose or extend `apply_base.py`.** `workstream_complete/apply.py` hand-authors its own closed dispatch + halt contract (imported from `coordinator_core.ceremony_common.apply_halt`, the same factored trio `workday_complete`/`workweek_complete` use) — that is a deliberate, documented divergence from the `pickup`/`baton`/`merge`/`consolidate` lineage, not an oversight.
- **Propagate `/workday-complete`'s dirty-tree auto-disposition here.** `commands/workday-complete.md` is an explicit negative-spec pointing the other way — workstream-complete keeps the stricter surface where an unattributable dirty file is a real signal.
- **Auto-resolve tier-A oracle disagreement.** A declared-but-unwalked-repo tier is a hard stop, not a judgment call — override is gated on the `/autonomous` sentinel plus a recorded reviewer, never a silent proceed.
