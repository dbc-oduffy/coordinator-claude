---
spec-backlink: docs/plans/2026-07-04-initiative-govern-sweep-prioritize-doe-d.md § C6
---

# Initiative Govern Discipline

> How DoE owns the assignment discipline for the initiative entity: the conservative cut-bar
> that controls when a cluster earns a named initiative, the surface-and-confirm graduation
> rule that keeps humans as the authoring gate, and the prioritization discipline that
> govern-orders open-ended (burn-down) and dated (completion) initiatives. Complements the
> fleet-deliverable-spine substrate — it does not rebuild the entity, FK, or backfill.

The initiative substrate ships the entity (`state/initiatives/<id>.yaml`), the nullable FK
(`initiative:` on artifact frontmatter), and the emit path. This wiki owns the *assignment
discipline* layered on top: when clusters earn a name, who authors the cut, and how the
govern cadence surfaces and orders them.

---

## The Conservative Cut-Bar

**Bias to fewer initiatives, over-populated.** The natural failure mode of an initiative
taxonomy is over-proliferation — every loosely related cluster of work earns a named
initiative, the board fills with low-signal entries, and the taxonomy stops functioning as a
navigational aid. The cut-bar guards against this by defaulting skeptically.

### Frictionless attach-to-existing is the default

Before creating a new initiative, the question is always: *does an existing initiative
already cover this work?* An artifact whose topic overlaps an active initiative should be
attached to that initiative rather than used to justify a new one. The `coordinator-initiative
attach` command exists for this — frictionless FK-write to an existing initiative, no new
entity created.

**The burden of proof is on creation, not attachment.** If the same cluster could plausibly
sit under an existing initiative *and* a new one, the existing one wins.

### Anti-proliferation as a first-class constraint

Initiative proliferation is not a style preference — it is a correctness failure that
degrades the fleet-deliverable board for every consumer. Anti-proliferation is a first-class
constraint enforced at cut-bar time, not a nudge applied post-hoc.

Concrete checks before creating a new initiative:

1. **Does an existing initiative cover this work area?** If yes, attach — do not create.
2. **Is the cluster large enough?** A cluster below the ≥3-item floor (DR-209) does not
   surface as a candidate. A cluster that *just* crosses the floor is a candidate, not a
   decision — apply additional judgment about distinctness from existing initiatives.
3. **Is the label distinctive enough to navigate by?** An initiative label that needs a
   parenthetical to distinguish it from a sibling ("Front-end Performance (auth-forms)" vs
   "Front-end Performance (onboarding)") signals the parent category is the right initiative,
   not two children.
4. **Does the cluster span multiple artifact types or a long time horizon?** Single-type,
   short-horizon clusters belong in the queue triage, not in the initiative taxonomy.

### The ≥3-item cluster floor (DR-209)

The graduation-gate detector (`detect-initiative-candidates`) enforces a hard floor: a
cluster of fewer than 3 unattached items does not surface as a candidate initiative. This
floor exists because below 3 items, the cluster is more likely noise than signal. A cluster
of 2 is a coincidence; a cluster of 3 is a pattern.

**DO NOT bypass the floor** to surface "interesting" 2-item clusters — the false-positive
rate increases sharply below the floor, and false positives are expensive (a named initiative
that dissolves on inspection trains the PM to ignore the detector).

---

## The Surface-and-Confirm Graduation Rule

**Agents detect candidates; humans author the cut.**

The graduation path has two distinct steps:

1. **Detection (automated, read-only):** `detect-initiative-candidates` groups the unattached
   set by shared signal (topic, tag, co-citation, directory), applies the ≥3-item floor, and
   emits candidate clusters with suggested labels. It opens no write handles, accepts no
   output-path argument, and makes no decision about whether a cluster *should* become an
   initiative. This step is purely observational.

2. **Authoring (human-gated):** a human reviews the candidate clusters surfaced during the
   `workweek-complete` initiative-govern sub-step, decides which clusters earn a named
   initiative, and uses `coordinator-initiative create` to mint the entity. The decision is
   the human's — agents do not promote candidates to initiatives autonomously.

**DO NOT auto-create initiatives.** Any code path that writes `state/initiatives/<id>.yaml`
without an explicit human author violates the surface-and-confirm rule. The detector is
structurally constrained (no write handles) to enforce this, but the constraint is also
doctrinal — a detector that could create initiatives would bypass the judgment that prevents
over-proliferation.

### Why this rule exists

The cut-bar requires human judgment that no automated heuristic reliably supplies:
- Whether two clusters are genuinely distinct from an existing initiative.
- Whether the timing is right (an initiative named too early dissolves; too late and the work
  is already finished without attribution).
- Whether the suggested label is business-legible and navigable.

Detectors optimize for recall (surface everything plausibly real). Humans optimize for
precision (mint only what the board needs). Both are required; separating the steps is the
mechanism.

---

## Prioritization Discipline

**How DoE govern-orders open-ended and dated initiatives.**

The initiative schema encodes shape via a single nullable field: `target_date` (`null` ⇒
burn-down / ongoing; ISO date string ⇒ completion / time-bounded). No dedicated `shape` or
`type` field is added — `target_date` is the shape discriminator.

### Burn-down (open-ended) initiatives

`target_date: null`. These are ongoing areas of investment — quality, performance,
infrastructure, observability — where the work never finishes but the pace and prioritization
are governed. Examples: "Tech Debt Reduction", "Test Coverage Lift".

**Govern posture:** surface in the weekly triage cadence, track unattached items flowing into
the cluster, and adjust the active/paused status as other initiatives compete for bandwidth.
Burn-down initiatives do not have a ship date; they have a *priority level* among their peers.

**Priority ordering among burn-down initiatives:** the PM sets priority by setting
`status: active` on the initiatives currently receiving bandwidth and `status: paused` on
those deferred. The `coordinator-initiative list-unattached` lens surfaces the unattached
queue depth per initiative area as an input to the ordering decision — a large unattached
queue in a paused burn-down initiative is a signal to consider reactivating it.

### Completion (dated) initiatives

`target_date: <ISO date>`. These are time-bounded bets with a declared delivery target —
launches, milestones, external commitments. Examples: "Delphi Pro Launch 2026-Q3",
"Fleet Spine Migration 2026-07-15".

**Govern posture:** the `target_date` is a forcing function. In the weekly triage cadence,
unattached work items in the scope of a dated initiative are a higher urgency to attach and
schedule than unattached work items in burn-down initiatives — an unscheduled item inside a
completion initiative's scope is a latent miss.

**Priority ordering between completion and burn-down initiatives:** completion initiatives
with near-term `target_date` outrank burn-down initiatives for bandwidth allocation by
default. The PM may override by setting a burn-down initiative `status: active` while pushing
a dated initiative to `status: paused` — but this is a named exception, not a default.

### Govern teeth — human-triggered, with oversight

**Initiative prioritization is never autonomously dispatched.** The triage cadence (weekly,
at `workweek-complete` Step 4) surfaces the unattached queue depth, candidate clusters, and
current initiative status. The EM presents the picture; the PM makes the ordering call.

Concretely:
- `query-records --unattached` surfaces the unattached queue depth. **First-run note:** initial output is high-volume because handoffs and plans carry an `initiative` FK but most existing records predate the discipline (initiative: null/absent). Run `--unattached --limit 50` for a manageable first pass; re-run with `--type bug`, `--type debt`, etc. for per-type deep inspection.
- `detect-initiative-candidates` surfaces clusters above the ≥3-item floor.
- The PM decides which candidates to name, which burn-down initiatives to reactivate or
  pause, and whether completion initiative `target_date` values are still accurate.
- `coordinator-initiative create` / `attach` are the actioning primitives — human-invoked
  from the PM's side of the triage conversation.

**DO NOT autonomously reorder active/paused status on initiatives based on queue depth or
cluster signal.** The detector and lens are observational inputs to a human decision, not
triggers for automated state changes. An agent that flips `status: paused → active` on an
initiative because the unattached queue grew is bypassing PM-altitude governance.

---

## The Sweep Cadence — Sole Ritual Home

Initiative govern runs once per week at `workweek-complete` Step 4 (Improvement-Queue
Triage). It does NOT run at:

- `workday-complete` — too frequent; daily triage is for queue closure, not initiative cuts.
- `workstream-start` — forward-looking orientation; initiative govern is backward-looking
  accumulation review.
- `workweek-start` — DR-209 suggested this placement, but DoE ratified `workweek-complete`
  (predecessor handoff Key Decision #6): a backward-looking cadence fits the initiative sweep
  better than a forward-looking orientation, and queue-triage teeth already live at complete.

**Negative-spec — DO NOT add an initiative-govern sub-step to `workday-complete`,
`workstream-start`, or `workweek-start`.** The sole ritual home is `workweek-complete`
Step 4.

---

## Cross-Links

- **Initiative entity schema:** `coordinator/schemas/initiative.schema.json` — `id`, `label`,
  `owner`, `status` (`active|paused|shipped|abandoned`), `target_date`.
- **CLI:** `coordinator/bin/coordinator-initiative` — `create` (fail-loud on collision),
  `attach` (FK-write to artifact frontmatter), `list-unattached` (thin wrapper over
  `query-records --unattached`).
- **Unattached lens:** `coordinator/bin/query-records.js` `--unattached` predicate — returns
  every indexed record with `initiative == null` across debt/bug/improvement queues,
  roadmap spinoff-stubs, handoffs, and plans. Set-difference over existing stores; no new
  bucket.
- **Graduation-gate detector:** `coordinator/bin/detect-initiative-candidates` — read-only,
  clusters unattached items, enforces ≥3-item floor, emits candidates only.
- **Weekly ritual:** `coordinator/commands/workweek-complete.md` § Step 4: Improvement-Queue
  Triage — initiative-govern sub-step (run lens + detector, surface candidates, prompt human
  attach/create).
- **Fleet-deliverable spine:** `docs/plans/2026-07-03-fleet-deliverable-spine-identity-and-facets.md`
  *(lives in the sibling `example-orchestration-hub-repo` repo — awareness link, not in-repo navigable)* — the shipped
  substrate this discipline is layered on top of.
