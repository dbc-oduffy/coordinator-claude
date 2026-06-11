---
title: "learn-lessons Taxonomy, Routing Bias, and Apply Dispatch"
kind: wiki
created: 2026-05-28
system: learn-lessons
---

# learn-lessons — Lesson Taxonomy, Routing Bias, and Apply Dispatch

> **Spec backlink:** `skills/learn-lessons/SKILL.md` — this wiki carries the taxonomy and routing
> reference content extracted from the skill. The skill's procedural phases point here for the
> closed-enum definitions, routing gate rules, and per-change-kind apply dispatch.

## Routing Bias: Wikis Are the Default, CLAUDE.md Is Exceptional

Apply **extreme skepticism** to any routing record proposing a CLAUDE.md edit or a CLAUDE.md
pointer. The default destination for a captured lesson is **a wiki guide** — either an existing
one (`wiki-append`) or a new one (`wiki-new`). CLAUDE.md and pointer-only additions are the
exceptions, not the rule.

**Why.** CLAUDE.md is load-bearing at every session start. It is not a knowledge base. Every
addition — even a one-line pointer — competes for finite boot-time attention. A plethora of
pointers is the same anti-pattern as a plethora of inline rules: both turn CLAUDE.md into an
index of indexes that nobody reads carefully.

**The mechanism that makes wiki-only lessons land** is the prior-art-checker pre-flight in
`coordinator:plan` (→ `docs/wiki/prior-art-checker.md`). It cross-references plans against the
wiki + lessons + queue corpus. A lesson living in `docs/wiki/<topic>.md` will be surfaced to the
planner when relevant — without consuming CLAUDE.md budget. **If a lesson can be found by
prior-art-check, it does not need to be in CLAUDE.md.**

### The CLAUDE.md justification gate

A `doctrine-edit` (CLAUDE.md content) or `memory-pointer` (CLAUDE.md/MEMORY.md pointer line) is
admissible **only** if the proposal can answer ALL of:

1. **Cross-cutting tripwire.** Does the rule apply to multiple, named surfaces that agents touch
   from cold boot? (Not "useful to know" — "wrong action taken without it.")
2. **Boot-time-greppable required.** Would a planner / EM realistically fail to find this via
   prior-art-check on a relevant plan? Wiki-routing fails ONLY if the lesson cannot be matched
   from a plan's claim surface.
3. **No existing wiki carries the topic.** Confirmed by `grep` against `docs/wiki/`. If a wiki
   exists, `wiki-append` is the correct route — even if the wiki would then need a one-line
   surfacing somewhere agents already look (which is almost never CLAUDE.md).
4. **No existing CLAUDE.md section already covers the shape.** Demotion of a near-duplicate
   into the proposed addition's home wiki is preferred over adding alongside it.

If any check fails (during DoE adjudication of a worker-flagged escalation, or during DoE
self-review of a proposed doctrine-edit plan), downgrade: `doctrine-edit` → `wiki-append` /
`wiki-new` + `doe_escalation: true` (preserve the signal for DoE's separate downstream
consideration — NOT for further apply steps in the current run); `memory-pointer` →
`wiki-append` to the wiki that already carries the topic (the prior-art-checker will surface
it from there — no separate pointer needed).

**Substance and proposed-target are independent.** The original logging EM's `proposed target:` is a suggestion, not a verdict on the lesson's worth. When the proposed target is CLAUDE.md (or a CLAUDE.md pointer) and fails the four-check gate, the default move is **reroute** — pick the right wiki / agent prompt / hook / script surface for the substance — NOT `discard`. Discard is reserved for lessons whose *substance* is ephemeral, already covered by existing doctrine, or factually wrong from the start. "Logger proposed a rule-breaking target, therefore archive" is a category error: it conflates the lesson with its suggested destination. Ask "what problem is this lesson trying to solve, and where does that problem actually live?" before routing.

**Workers MUST NOT emit `change_kind: doctrine-edit` or `change_kind: memory-pointer`.** Route
to `wiki-append` / `wiki-new` and set `doe_escalation: true` (with a one-line
`escalation_reason:`) when the worker believes CLAUDE.md placement deserves DoE consideration.
The EM/consolidator treats any record arriving with either change-kind as a routing error
and downgrades it to the corresponding `wiki-*` before the record reaches PM surfacing.
DoE-authored exceptions (a separate downstream plan, not lifted from worker output) require
all four justification checks answered inline. **Do NOT auto-apply `doctrine-edit` or
`memory-pointer` records, regardless of mode** — they always require DoE authoring, the Staff Engineer
review, and PM surface.

### DoE-only adjudication on CLAUDE.md edits

CLAUDE.md loads at every session start across every project — blast radius is maximum. The receive-side gate must match that asymmetry.

**Workers / scouts MUST NOT propose `change_kind: doctrine-edit` or `change_kind: memory-pointer`.** These are reserved for the DoE (the Director of Engineering or the EM at Claude Central with explicit DoE authority). Worker records using either change-kind are downgraded by the consolidator before PM surfacing:

- Worker sets `doe_escalation: true` on a `wiki-append`/`wiki-new` record with a one-line `escalation_reason:`. The wiki edit lands regardless — escalation is a DoE attention flag, not a blocker.
- If the DoE accepts the escalation, they author a separate `doctrine-edit` plan (NOT lifted from worker output), reviewed by the Staff Engineer, gated on the four-check justification gate + char-budget pre-flight. Many gates before any CLAUDE.md byte changes.

EMs proposing CLAUDE.md targets in `state/lessons.md` is expected and inevitable — the load-bearing gate is on the receive side, not at capture time. The four-check justification gate still applies to DoE-authored proposals; the DoE does not bypass it.

### Pointer-pollution bound

The CLAUDE.md "→ `docs/wiki/<name>.md`" pointer is a tool, not a destination. A run that emits
more than **one** new CLAUDE.md pointer across all routing records is presumptively wrong —
the underlying lessons belong in their wikis, and the wikis are findable by prior-art-check
without a CLAUDE.md hand-hold. Surface to the PM with the full pointer list before applying.

## Per-Lesson Routing Schema

Each lesson processed produces one record:

```yaml
- id: "<repo-shortname>-<entry-id>"
  source: "<file:line>"
  summary: "<one-line title>"
  scope: universal | project | wiki-only | discard
  destinations:
    - target: "<full file path or new-file path>"
      section: "<named section anchor or '(new section)' or '(new file)'>"
      change_kind: <see Change-Kind Taxonomy below>
      rationale: "<one-line why>"
      priority: HIGH | MEDIUM | LOW
      depends_on: "<optional id pointer>"
  open_questions: []
  doe_escalation: false           # workers set true on a wiki-* record when they
                                  # believe DoE should reconsider CLAUDE.md placement
  escalation_reason: ""            # one-line; only meaningful if doe_escalation: true
```

`doe_escalation` is the worker-side flag for "this might be CLAUDE.md-worthy — DoE please
look." It rides on a `wiki-append` or `wiki-new` record; the wiki edit lands regardless.
Workers MUST NOT use `change_kind: doctrine-edit` or `change_kind: memory-pointer` (see
§ Routing Bias above). Records arriving with those change-kinds are treated as routing errors
and downgraded by the consolidator.

## Change-Kind Taxonomy (closed enum)

| Kind | Meaning | Apply mechanism |
|---|---|---|
| `doctrine-edit` | **DoE-ONLY** — edit a CLAUDE.md at a named section. Workers MUST NOT propose; reserved for DoE authoring after escalation review. Must clear the four-check justification gate AND char-budget pre-flight (§ Routing Bias). | DoE-authored plan → the Staff Engineer review → executor; PM surface mandatory |
| `agent-prompt-edit` | Edit a specific agent's prompt file | Plan → reviewer → executor |
| `hook-edit` | Edit a hook script | Plan → reviewer → executor |
| `script-edit` | Edit a helper script in `bin/` | Plan → reviewer → executor |
| `snippet-sync-update` | Edit a synced snippet + run propagation script | Edit + `bin/verify-*-sync.sh --fix` |
| `wiki-new` | Create a new `docs/wiki/` guide. **Default destination** for non-trivial cross-cutting lessons. | Plan → reviewer → executor; update `DIRECTORY_GUIDE.md` |
| `wiki-append` | Append to existing wiki guide at named section. **Default destination** for lessons covered by an existing wiki topic. | Direct executor (low judgment) |
| `memory-pointer` | **DoE-ONLY** — add a one-line pointer to MEMORY.md or CLAUDE.md. Workers MUST NOT propose; reserved for DoE authoring. Same four-check gate as `doctrine-edit`; prior-art-checker should be reached for first. | DoE-authored edit; PM surface mandatory |
| `project-structural` | Change in originating project's repo | Plan → reviewer → executor in that repo |
| `retag-local` | Change `[universal]` → `[<domain>]` tag in place | Direct edit |
| `strip-local` | Delete entry from source file (gated on central commit SHA). In central mode, **DoE auto-applies in the same run** as the central promotion — see Phase 5 § Apply order in `skills/learn-lessons/SKILL.md` and § Per-record apply dispatch below for the pull + content-match + skip-on-drift procedure. | Pull-then-content-match-then-Edit + explicit-pathspec commit; ONLY after depends_on lands |
| `discard` | Archive-then-delete (no migration) | Archive append + direct edit |

## Per-Record Apply Dispatch

Called by Phase 5 (`Authorization and Apply`) in `skills/learn-lessons/SKILL.md`. For each
routing record authorized by the PM (central mode) or within auto-apply bounds (local mode),
dispatch using the rules below.

### CLAUDE.md justification pre-flight (gates `doctrine-edit` and `memory-pointer`)

**Run the § Routing Bias four-check gate FIRST.** Size is a backstop, not the primary
filter. If any of the four checks (cross-cutting tripwire / boot-time-greppable required /
no wiki carries it / no CLAUDE.md section already covers it) fails, the change-kind is
downgraded to `wiki-append` or `wiki-new` before any size measurement happens. A passing
gate-check must be recorded inline in the PM-surfacing block; "size fits" is not a
justification.

### CLAUDE.md char-budget pre-flight (gates `doctrine-edit` targeting any CLAUDE.md)

After the justification gate clears, before dispatching a `doctrine-edit` whose `target` is a
`CLAUDE.md` file, run this pre-flight:

1. Measure current char size: `wc -c <target>`.
2. Estimate addition: char count of the proposed new bullet/section body.
3. Compare projected size (`current + addition`) against thresholds:

| Projected | Action |
|---|---|
| ≤ 36,000 | Proceed normally (≥4K headroom under soft limit). |
| 36,001 – 38,000 | Proceed, but emit a "budget approaching" note to the PM summary so the next addition is on notice. |
| 38,001 – 40,000 | **Gate: identify a demote target first.** The plan must name a specific section to compress to a wiki pointer (or an existing wiki to extend) and include the demote in the same plan. No PM ratification needed if the demote is mechanical (existing wiki carries the topic); surface to PM if creating a new wiki. |
| > 40,000 | **Hard refuse.** The pre-commit hook (`validate-commit.sh` Check 7) will block the commit anyway. Surface to PM with current size, proposed addition size, and the top-3 demote candidates ranked by char savings. |

The same gate applies whether the target is `~/.claude/CLAUDE.md`, `plugins/coordinator/CLAUDE.md`, or any project-level `CLAUDE.md` — the 40K limit is per-file, set by Claude Code's perf warning.

**Rationale.** The two trims in 2026-05-06/07 both held; doctrine creep refilled the budget through ~25 small additions. The hook catches the symptom; this gate catches the cause at the only step where coordinator-doctrine additions are routed (`doctrine-edit` is the closed-enum kind for CLAUDE.md edits per Phase 0 taxonomy).

### Apply dispatch by change-kind

- `doctrine-edit`, `memory-pointer` → **DoE-only.** Workers MUST NOT reach this branch —
  worker records arriving with either change-kind are downgraded to `wiki-*` +
  `doe_escalation: true` at consolidation. Only DoE-authored plans (drafted after reviewing
  the escalation bucket, clearing the four-check justification gate, and clearing the
  char-budget pre-flight) reach this dispatch step. Plan → the Staff Engineer review → integrator →
  executor.
- `wiki-new`, `agent-prompt-edit`, `hook-edit`, `script-edit` → write focused plan, dispatch
  the Staff Engineer for review, integrator on findings, executor.
- `snippet-sync-update` → edit snippet, run `bin/verify-<snippet>-sync.sh --fix`, commit all touched.
- `wiki-append`, `retag-local`, `discard` → direct executor or EM edit.
- `strip-local` → **DoE-applied in the same central run** (cross-repo write from `~/.claude`
  into the sibling repo), gated on the central wiki commit SHA landing first. Procedure per
  record:
  1. `cd <sibling-repo> && git pull --ff-only`. If pull is not fast-forward or working tree
     is dirty in `state/lessons.md`, **skip this strip and emit a one-line warning** —
     don't fight a concurrent EM; the sibling's local-mode Phase 4.5 age-sweep is the
     defence-in-depth that catches residue.
  2. Re-Read `state/lessons.md` and **match the target entry by body content** against the
     extracted record from the Phase 2 extraction (`source:` body), NOT by line number.
     The `<shortname>-L<N>` id reflects the line at extraction time; a concurrent EM
     session may have inserted/removed earlier entries since. Same drift-safe pattern as
     the heavy-queue sprint § Step 5.
  3. If the content match is unambiguous (single hit), Edit out the entry block.
     If zero hits (entry already removed by a sibling EM) or multiple hits (file got weird),
     skip with a one-line warning.
  4. Commit with explicit pathspec: `git add -- state/lessons.md && git commit -m
     "learn-lessons(central): strip <id> — promoted in <central-SHA>"`. Never `git add -A`.

  The sibling's local mode is no longer the primary mechanism for retiring promoted
  universals — central is. Phase 4.5 age-sweep remains the backstop for entries that
  pre-date the central-promotion era, machines where the DoE can't reach all siblings, and
  entries the strip pass skipped on drift.
- `project-structural` → in originating project repo: plan → review → executor.

## Local Mode — Auto-Apply Bounds

Used by Phase 5 (`Authorization and Apply`) in local mode to determine which records apply
automatically vs. require PM surfacing.

**Auto-apply without PM prompt:**
- `discard` of pure-ephemeral entries (archive first per Phase 4)
- `wiki-append` to existing guides — **mandatory same-run apply when destination is named**
- `wiki-new` when (a) destination filename is named, (b) substance is concrete enough for an executor draft, and (c) the new file does not cross into doctrine surfaces. Add `DIRECTORY_GUIDE.md` entry in same executor dispatch. Surface to PM only when the wiki home is itself an unresolved design question.
- `retag-local` within the same file
- Dedupe of obvious duplicates
- Phase 4.5 age-sweep (archive aged `[universal]` entries older than the last completed central run; reversible via archive + git)

**Same-run apply is the default.** When a record lands in the auto-apply bucket, dispatch the apply this run. "Next local pass should fold these" is the defer-chain anti-pattern. If parallel-dispatch budget is tight, serialize — do not defer.

**Surface to PM (do not auto-apply):**
- `doctrine-edit`, `memory-pointer` — **DoE-only.** Downgrade worker-proposed records to `wiki-*` + `doe_escalation: true` before surfacing. The DoE authors a real `doctrine-edit` plan only after reviewing the escalation bucket, clearing the four-check gate, and clearing the char-budget pre-flight.
- `doe_escalation: true` records — surface as a separate "DoE reconsideration" bucket. The wiki edit auto-applies; the escalation flag is a DoE attention notice, NOT a blocker.
- `agent-prompt-edit`, `hook-edit`, `script-edit`, `snippet-sync-update`
- `project-structural` outside the same repo

`strip-local` is **NOT** in the PM-surface bucket — it auto-applies as the second half of the central promotion chain (see Phase 5 § Apply order in `skills/learn-lessons/SKILL.md`). Surfacing a strip-local to the PM is process theater: the PM has already authorized the central promotion that obsoletes the source-repo entry, and every day the entry remains in source bloats `lessons.md` for `/learn-lessons`, the central strip-pass, and `/workstream-start` (sibling files have hit 200–350 KB in roughly a month of high-volume capture).

**Universals-pending escalation.** If ≥ 20 unactioned `[universal]`-tagged entries have accumulated since the last central-mode commit, surface the count to the PM: *"Backlog of N universals — invoke central mode now?"* — and wait. Do not launder the backlog into another "next pass" notice. Emit a one-screen PM summary with surfaced records and a "run /learn-lessons --mode=central" pointer.

## Lesson Scope Classification

Each lesson extracted from `state/lessons.md` is classified into one of four scopes:

| Scope | Meaning | Routing destination |
|---|---|---|
| `universal` | Applies across project types — would fire for any project using the coordinator pipeline | `~/.claude/state/coordinator-improvement-queue.md` (central); tag `[universal]` in source |
| `project` | Applies to the originating project's structure or codebase | Local `state/improvement-queue.md` |
| `wiki-only` | Lesson whose substance belongs directly in a wiki guide (no queue entry needed) | Append-or-promote to `docs/wiki/<topic>.md` |
| `discard` | Ephemeral, already covered by existing doctrine, or factually wrong | Archive (Phase 4) then delete |

**Test for `universal`:** "Would this apply if a different project type used the coordinator pipeline?"

**Conservative on domain-specific candidates.** `retag-local` is the safer default for entries that look universal-tagged but are really domain (UE / game-dev / web-dev / data-science). When applying `retag-local`: do NOT blind string-replace `[universal]` → `[domain]` — a naive replace corrupts prior retag-history comments and any in-body `[universal]` reference. Edit only the tag on the entry's header line. Note also that `extract-lessons.py` sets `tag_universal` if `[universal]` appears *anywhere* in the block, so a leftover in-body mention keeps an entry classified universal after a header-only retag — strip stray in-body occurrences too.

## Per-Project `state/lessons.md` Files Are a Central Mining Surface

**Per-project `state/lessons.md` files accumulate war stories specific to that project's domain. The central-mode run is the mechanism for surfacing universal patterns buried in domain-specific language.**

Triage tier:
- **Tier 1** — pattern applies universally → coordinator structural change (skill/command/agent-prompt/wiki); tag `[universal]`, promote to central queue.
- **Tier 2** — pattern is project-structural → stays in `state/improvement-queue.md` for that repo.
- **Tier 3** — already encoded in existing doctrine → `discard`.

The 2026-04-27 holodeck pass illustrates the signal density: 3 lessons became direct pipeline fixes, 12 became universal coordinator promotions across 15 files — from a single project's lessons file. When the central-mode run is overdue, per-project files are the richest underexplored source of universals.

## Age-Sweep Retained-Count vs. Universals-Count Gap

**After a local-mode age-sweep, `retained-count ≠ [universal]-count` signals untagged universal-shape entries.**

When Phase 4.5 archives aged entries, the remaining retained count minus the `[universal]`-tagged count should be small. A large gap signals entries that look universal in substance but were never tagged — they will be skipped by the central-promotion pass even if they belong there. Before sending a central-promotion memo, cross-check: enumerate `[universal]`-tagged entries vs. total retained; surface the gap as untagged candidates for DoE review. Do not leave the gap as a silent miss.

*Source: 2026-05-28 project-rag; central-promoted.*

## `[universal]` Tag Is Not a Stop-Sign for Local Wiki Folds — Bidirectional

**`[universal]` tag and a local wiki fold are independent in BOTH directions: a tagged entry should ALSO fold into a local wiki if the substance fits; a local-wiki-only entry should ALSO be tagged if the pattern is universal.**

The routing bias section above governs CLAUDE.md placement. A separate, symmetric trap exists for wiki folds: the `[universal]` tag signals "promote to central queue" — but an EM treating it as a stop-sign skips the local `docs/wiki/` fold that would make the lesson discoverable by the prior-art-checker immediately. For every `[universal]` entry, ask "does the substance fit any local wiki?" before defaulting to central-only. The right disposition is often BOTH: tag for central AND append to the relevant local wiki in the same run. The inverse also holds: a `wiki-only` scoped entry with genuine universal substance should get `[universal]` added alongside the wiki fold — the two routing targets are not mutually exclusive.

*Source: 2026-05-28 claude-unreal-holodeck; central-promoted.*

## Cross-Repo Strip — Content-Signature Matching, Not Line-Number Partition

**When the central run strips promoted universals from sibling-repo `state/lessons.md` files, the strip oracle MUST be the extracted-yaml record bodies matched by content, not a fresh partition of the current source state.**

Source files are in motion. Between extraction at time T and strip at time T+N, concurrent EM sessions may add new universals, prune existing ones, or commit adjacent changes. A partition-based strip (re-derive all `tag_universal: true` blocks from current source at apply time) will archive post-extraction additions that were never centrally promoted — promoting the wrong thing.

**Correct procedure (per `skills/learn-lessons/SKILL.md` § strip-local apply):**

1. Re-read `state/lessons.md` at strip time.
2. For each promoted body in the central run's extracted-yaml, match against current source by **normalized first-200-char content signature** (not line number).
3. Strip only entries whose signatures match a promoted body; skip zero-match (already removed) and multi-match (ambiguous) with a warning.
4. Archive provenance header cites the central SHA + "promoted by" — not "discarded."

*Source: 2026-05-28 central run; project-rag had 22 of 29 promoted entries already pruned by concurrent session; 4 retained universals were post-extraction additions correctly left alone by content-match.*
