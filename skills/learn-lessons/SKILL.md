---
name: learn-lessons
description: "Processes lessons/ entries as doctrine change-requests, local or central."
version: 1.0.0
---

# learn-lessons — Lesson Processing and Queue Activation

`learn-lessons` processes per-entry `state/lessons/*.yaml` files as change-requests against
doctrine, agent prompts, hooks, scripts, wiki guides, and improvement queues — one destination +
change-kind per lesson, tracking recurrence and archiving discards. Success metric: did doctrine
and queues evolve, not did the file shrink. **Supersedes `coordinator:lesson-triage`** (renamed;
no alias shim). Modes, the routing schema, the fabrication-verify-gate mechanics + recovery
playbook, the Phase 8 report shape, and the heavy-queue promotion-sprint procedure: wiki.

**Announce:** "I'm using the coordinator:learn-lessons skill in `<mode>` mode." Mode default: cwd
`~/.claude` central → `central`; else `local`; PM can override.

## Hard Rules (judgment residue, not engine-enforced)

- **No-defer.** A `wiki-append`/`wiki-new` record with a named destination applies THIS run —
  never "the next pass." Legitimate deferrals: a structurally-required cross-mode block (e.g.
  `strip-local` before its central commit SHA lands), or a record needing PM authorization.
- **Wikis are the default destination.** `doctrine-edit`/`memory-pointer` are doctrine-plane-only
  — a worker NEVER emits either; downgrade to `wiki-*` + `doe_escalation: true` before the record
  reaches the PM gate.
- **Extraction never runs through an LLM** (`coordinator/bin/extract-lessons.py` — a parse, not a
  judgment call; an LLM extraction pass produced a real fabrication incident). Routing judgment
  can, behind the verify gate.
- **Mechanical-contract lessons need an executable witness** (a passing test, live tool behavior,
  official docs) — discard if none can be found or one contradicts the claim; narrative confidence
  alone never overrides a converging set of independent authorities.
- **Domain-looking universals default to `retag-local`**, never a blind `[universal]` string
  replace (corrupts retag history).
- **A `wiki-append`/`wiki-new` target must be reachable** from a real traversal surface (index,
  skill step, dispatch preamble) — not merely exist.
- **Central mode needs a PM decision per record** (apply / defer / reject, batching OK) — never
  auto-applied. Local mode auto-applies discard/wiki-append/retag/dedupe/age-sweep; PM-surfaces
  `doctrine-edit`, `memory-pointer`, `doe_escalation`, `agent-prompt-edit`, `hook-edit`,
  `script-edit`, `snippet-sync-update`, `project-structural`. `strip-local` is NOT PM-surface.
- **Central strips only after its own promotion's commit SHA exists**, same run — never deferred
  to the sibling's next age-sweep.
- **Fail-close:** an undated-universal leak, or a strip-list id with no routed sibling record,
  blocks the run's `COMPLETE` sentinel — surface to the PM, don't push through.
- **Universals-pending:** if ≥ 20 unactioned `[universal]` entries, surface to PM before proceeding.
- **Never fabricate a routing `id`** — every cited id must exist in its extraction, or the
  mechanical verify-gate hard-fails the apply. Never hand-correct a router's fabricated output;
  re-dispatch it instead (launders the fabrication into the audit trail otherwise).

## Phase Flow (invocation pointers — mechanics: wiki)

Discovery roots: `coordinator/bin/learn-lessons-roots.py` (machine-registry-derived, never a
committed list). Extraction: `extract-lessons.py extract`. Routing populates
`candidate_restatements` via `coordinator_core.learn_lessons_assemble.generate_candidates(...)`
(or `learn-lessons-reconcile-candidates` for bulk). Central mode also runs an undated-pass via
`coordinator_core.ops.lessons_filter.filter_undated_universal(extraction_yaml)` (registered op
`lessons.filter_undated_universal`) and drains `state/lessons-outbox/` via
`lessons-outbox-drain.py` (read → assert cross-plane emptiness → group → dedupe → apply → mark
drained). Verify: `extract-lessons.py verify <extraction> <records.yaml>`. Strip-orphan check:
`learn-lessons-age-sweep check-strip-orphans <records.yaml> <strip-list.yaml>`. Local-mode
age-sweep bounds `state/lessons/`: `learn-lessons-age-sweep cutoff` then `age-sweep-lessons.py
--before <cutoff> [--apply]`. Universal-routing queue fork:
`coordinator-lesson-promote` (central-wiki target) / auto-apply (project-local wiki) /
`coordinator-queue-append --schema improvement-queue` (project scope). Recheck-mode delta:
`query-records --type lesson --since <date>`, cadence marker at `state/lesson-triage-recheck-due-
<date>.md`, volume nudge via `coordinator/bin/central-run-due.py`.

Emit the Phase 8 end-of-run report (exempt from the ≤200-word budget — the run's only audit
trail; do not convert to report-by-exception) before writing the `COMPLETE` sentinel; the sentinel
is written last, after every apply/commit lands.

## Anti-Patterns

Auto-applying central promotions without the PM gate. Bespoke extra parameters (modes are the
parameter surface). `git add -A` for strips. True-deleting a discard instead of archiving first.
Conflating the improvement queue with `state/lessons/` (capture queue vs. this periodic router).
Same-session capture-and-validate a lesson as universal. Default-routing to CLAUDE.md instead of a
wiki. Defer-chaining wiki promotions as "candidates for next pass" — every record is (a) applied,
(b) PM-surfaced, or (c) mode-escalated, no fourth bucket. Declaring "no additional work needed"
while project-specific (non-`[universal]`) entries remain un-routed. Full list + rationale: wiki.

## Related

wiki (full reference) · `coordinator/snippets/em-operating-doctrine.md § How to Plan and Hand
Off, "Improvement Queue"`
