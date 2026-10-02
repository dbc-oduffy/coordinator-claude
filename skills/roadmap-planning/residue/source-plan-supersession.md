## Source-plan retirement — a live plan the run re-sliced

Left standing, a re-sliced plan and the roadmap's stubs are two live spines over one deliverable. Rationale and divergence notes: wiki `roadmap-planning-residue.md` § Source-plan supersession.

### 0. Mark (Step 1.1), check (Phase 2 entry)

Step 1.1 marks each input that is a live plan in `state/roadmap/<run-id>/inventory.md`; Phase 2 entry CHECKS the marks, never re-walks the corpus.

**Verdict qualifier.** A marked plan owes retirement only if at least one of its clusters was verdicted KEEP or MERGE-target. Every cluster DROP/DEFER/MOVE → the plan stays live and untouched.

### 1. Live source plan

An input under `docs/plans/` whose `status:` is NOT `implemented`, `abandoned`, or `superseded`. `landed` (open spine rows) and `deferred` are NOT terminal and owe retirement when re-sliced. Terminal plans, handoffs and research owe nothing.

Read the set off the engine, then intersect it with the inputs: `coordinator-invoke records.query '{"type":"plan","where":"status!=implemented AND status!=abandoned AND status!=superseded","format":"json"}'`.

### 2. Retire in order: migrate, stamp, stand down

**MUST NOT stamp a plan `superseded` before its uniquely load-bearing prose is migrated** — stamping first strands it.

1. **Migrate** that prose into the inheriting stubs' `## What this covers` / `## Specification`.
2. **Stamp**, both halves, literally:

   ```
   status: superseded
   superseded_by: state/roadmap/<run-id>/STUB-INDEX.md
   ```
3. **Stand down the owed review**: cancel it with a one-line reason naming the roadmap as replacement spine, e.g. "superseded by `state/roadmap/<run-id>/STUB-INDEX.md`; the stubs are the spine." Never defer it with "review once stub boundaries are fixed". The verb is "stand down the owed review"; `coordinator/skills/handoff/residue/050-supersession.md`'s stand-down notice is a different act (outbound memo to an external receiver) and sends BEFORE its stamp, where this one follows it.
