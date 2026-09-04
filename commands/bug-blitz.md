---
name: bug-blitz
description: "Grind the bug backlog and tests; fix small, surface big items to PM."
allowed-tools: ["Agent", "Read", "Write", "Edit", "Bash", "Grep", "Glob", "Skill", "TaskCreate", "TaskUpdate", "TaskGet", "TaskList"]
argument-hint: "[--dry-run | --max=N]"
---

# Bug Blitz — Grind the Bug Backlog and the Test Suite

Two work sources, one pass: `state/bug-backlog/` and the full test suite (Tier-U authorized,
Phase 0.6). No separate triage step — failing tests mint `TF-*` items that ride the same
triage → wave → fix → verify path as backlog bugs. Green suite is part of done once Tier-U is
granted; declined runs the backlog leg only. Empty/absent backlog never halts the run; suite leg
still fires. `backlog-grind-assemble brief bug-blitz` emits `j-bug-blitz-commit-readiness`
(resolve before the first commit), `executor-dispatch-prompt-template`, and
`spinoff-handoff-template` — read them, don't hand-narrate them. Rationale, worked examples, and
full phase mechanics: wiki.

**Announce:** "Running `/bug-blitz` — one authorization ask for the full test suite (baseline +
confirm-green), then aggressive autonomous waves through every fixable item. Default is
dispatch-and-spot-check; defer needs named evidence. Big items surface for your authorization."

## Default Stance

Dispatch, don't defer. Defer ONLY with cited evidence: `already-fixed` (ran it), `file-removed`,
`big` (≥3 files / new module / schema change / new fixtures — "I'd need to think about it" isn't
`big`), `plan-substrate-collision` (named file collision with an actively-rewriting plan).
**NOT valid defer reasons — dispatch signals instead:** "summary-form"/"lacks standalone entry"
(expand inline, don't skip), "P2/judgment-call/refactor-flavor" (P2 ≠ skip if mechanical and
footprint-bounded), "intersects active plan" with no named file collision, "would take careful
thought" (that's what the executor+verifier+spot-check chain is for). Rationale/examples: wiki.

## Severity

P2: no triage, direct dispatch. P1: bulk-verify chunks of ~20, then dispatch. P0: careful
verify+read chunks of ~5, EM spot-checks every verdict. `TF-*` arrive pre-tagged (crash-shape P0,
else P1) but never skip triage — no pre-declared footprint to skip to. Rationale: wiki.

## Spinoff Gate

Before any `big`/themed item reaches the PM list: re-verify it's not a phantom (pattern gone on
HEAD), not mis-sized (reclassify `small` if ≤2 files/<50 lines), not already covered by a live
handoff/plan. Checklist and calibration: wiki.

## Queue Terminus

Four outcomes: dispatch (`small`), solo spinoff (`big`, PM-authorized), close
(already-fixed/file-removed/wontfix), themed baton (N `small` items sharing a thesis, clustered
via `detect-initiative-candidates`, authored as one multi-item handoff). Themed batons ride the
same PM-authorization gate as `big` regardless of size; footprint governs wave dispatch, theme
governs authorship only. Mechanics: wiki.

## Arguments

`--dry-run`: Phases 0-2 only, no Tier-U ask, no dispatch. `--max=N`: cap fixed items
(severity-then-ID order; `TF-*` sorts ahead of P2). Combine for a capped plan with no dispatch.

## Out of Scope

`gh pr merge`/`create` against main, `git push origin main`, hibernate/shutdown/kill-process,
`--no-verify`/`--no-gpg-sign`. No exceptions, no mid-run ask.

## Phase 0 — Preflight

Note backlog presence/count; confirm `git branch --show-current` is
`work/{machine}/{date-or-span}` (fail-closed, no override) and capture as `BLITZ_BRANCH`; mint run
ID; scratch `state/scratch/bug-blitz/{run-id}/`. Mechanics: wiki.

## Phase 0.6 — Tier-U Authorization (skipped under `--dry-run`)

Ask once, before Phase 0.7: *"This run needs the full test suite — once now to baseline, once
after fixes to confirm green. Authorize the full-suite tier for this run?"* Only an explicit
affirmative naming its subject (or a terse "yes" in direct reply) qualifies — general blitz
approval doesn't. Granted → `tier-u-grant-cli grant pm <note>`, proceed; the same session-scoped
token covers Phase 4's re-run (`tier-u-grant-cli check`, no second ask). Declined → write nothing,
backlog-only leg, note the decline in the report.

## Phase 0.7 — Suite Baseline (no-op unless granted)

`coordinator-resolve-validation-cmd --full` resolves `TEST_CMD`: exit 0 full suite; exit 3
fast-tier fallback, report as `fast-fallback`, never call it the full suite; exit 2 unconfigured,
continue backlog-only, name the remediation, never fabricate a command. EM runs it directly (Tier-U
— subagents never run the suite), dispatches `test-evidence-parser` to classify the captured
output. Each `real` failure mints `TF-{run-id}-{n}`; `flake`/`env`/`timeout`/`known-skip` aren't
dispatched. Mechanics: wiki.

**Empty-backlog-and-green-suite short-circuit:** absent/empty backlog AND fully green resolved
suite → skip to a one-line all-clear, no commit. Not reachable under decline/`--dry-run`.

## Phase 0.5 — Severity Split

Tag untagged entries (P2 default; crash/data-loss/security/silent-corruption → P0;
wrong-behavior/breaking-flow → P1), route by tier, emit counts.

## Phase 1 — Verify + Triage

P1/P0 only; P2 skips to Phase 3. Per item: verify still-applies against HEAD
(`still-open`/`already-fixed`/`pattern-changed`/`file-removed`; `already-fixed` carries
`evidence: ran|inspected` — the run's split count sums these), size-classify if open
(`small` default / `big` / `needs-investigation` as a non-terminal flag), declare footprint,
fan out summary-form rows. Never weaken a test assertion to green without evidence it was
wrong — `BLOCKED: assertion-weakening-without-evidence`.

**Pattern-shifted is a dispatch signal, not a defer reason** — a missing symbol at the cited line
is usually the same bug with the symbol renamed or code reshuffled nearby, not a moved/resolved
bug; re-grep the recommended-fix's central noun-phrase before treating it as deferral-eligible.
Evidence bar: `file-removed` needs `ls` confirming absence; `already-fixed` needs the failing case
**run against HEAD** — a sha attests a write, never that this defect stopped reproducing. Where the
artifact resolves through a published mirror, run what the resolver returns
(`[[actioned-means-routed-not-fixed]]`). Tag each closure `ran` or `inspected` (pattern absent plus
a sha) and report the counts separately — both close, but one number hides the weak ones. Neither
closes on "can't find it" alone. Output schema, worked examples: wiki.

## Phase 2 — Plan Waves + Auto-Spinoffs

Resolve every `needs-investigation` row by reading the code (2.0). Spinoffs need explicit PM
authorization per item (2.1) — unauthorized items revert to `needs-investigation`. Drop
already-fixed from active tables (2.2). Group `small` items into file-disjoint waves (2.3);
`--max=N` caps by severity-then-ID. Cluster themed-baton candidates into the same 2.1
authorization message (2.15). One flight-recorder goal task + per-wave tasks (2.4). Announce the
plan, fire Phase 3 immediately — no wait (2.5); `--dry-run` stops here. Full mechanics: wiki.

## Phase 3 — Execute Waves

**Single committer, no exceptions.** Executors edit-and-report only, never stage or commit. EM
commits at the wave gate via `backlog-grind-assemble apply bug-blitz --wave-path <path>...
--granularity per-item --message <single-line msg> --decisions
'{"j-bug-blitz-commit-readiness": {"disposition": "ready-to-commit"}}'` — one commit per item,
never collapsed to `per-wave`. **The judgment point is not optional and its value is an OBJECT.**
Omit `--decisions` and the commit directive stays gated; pass the bare string
`"ready-to-commit"` and older engines read it as a WITHHELD authorization and gate silently,
reporting only `unresolved_judgment_points` with no shape complaint. Current engines widen the
bare string, but write the object form — it is the one shape every version reads as authorized.
Dispatch executors via the `executor-dispatch-prompt-template` directive; verify each DONE with a
Haiku diff-reader (`PASS`/`PATTERN-STILL-PRESENT`/`FOOTPRINT-VIOLATION`/`REGRESSION`); commit PASS
items in deterministic ID order after re-polling `$BLITZ_BRANCH`; `git checkout --` to revert
non-PASS and leave in backlog with an updated `why_blocked`. Full mechanics: wiki.
<!-- engine-gap: field=directives[build_verifier_dispatch].dispatch_entry producer=unknown memo=2026-08-14-doe-claude-em-three-cut-obligations-from-the-corpus-grind.md -->

## Phase 4 — Green-Suite Gate + Report

Re-run the suite (mandatory if any fix dispatched, only if Tier-U was granted). All clear → PASS.
**Disposition splits on whether the failure was already red at baseline:** a pre-existing failure
still red after one corrective wave means stop chasing in-wave — either leave it reverted to
baseline (acceptable) or, if the attempted fix is committed and not working, `git revert` that
non-working fix commit — then surface it as a spinoff candidate; a NEW failure that was green at
baseline is a self-inflicted regression and its revert is **mandatory, not optional**: `git revert
<introducing-sha>` (never `git reset` — branch is pushed), confirm green, name it in the report.
**Loop bound: one corrective wave only, then the forced terminal state above — never a second
corrective wave, in either branch.** Never report green with a known-red suite. Archive every
closed backlog entry via `git mv` to
`archive/bug-backlog/<YYYY-MM>/`, `closed_by:` = commit SHA / prior SHA / `spun-off-<path>`;
commit the moves naming every closed ID. If nothing closed, skip that commit and announce the
no-op. Clean scratch after the backlog commit succeeds. Full mechanics: wiki.

**Report by exception** — two lines always, rest only when not clean:

```markdown
## Bug Blitz Complete

**Backlog:** N → M
**Resolved this run:** F items (backlog: Fb, failing tests fixed: Ft)
```

Add `**Spun off (need plan):**` / `**Re-attempted (still blocked):**` / `**Suite gate:**` /
`**Suite noise (not chased):**` / `**Closed already-fixed:** R ran / I inspected` only when
non-empty — that last one splits by evidence rung because one number over two standards hides
the weaker half from the reader, and from you. Never restore a run-id line, a silent
already-fixed line, or a clean `Suite gate: PASS` line — their absence already means clean.

## Failure Modes, Stop-Early, Relationship to Other Commands

Full tables: wiki. The load-bearing invariants that stay here: never rollback completed waves on
early stop; never fabricate a test command; never weaken an assertion; `git revert` (never `git
reset`) for a self-inflicted regression on a pushed branch.
