## Source-plan retirement — a live plan the run re-sliced

### 0. Mark (Step 1.1), check (Phase 2 entry)

Step 1.1 marks each live-plan input in `state/roadmap/<run-id>/inventory.md`; Phase 2 entry CHECKS the marks, never re-walks the corpus.

**Verdict qualifier.** A marked plan owes retirement only if at least one of its clusters was verdicted KEEP or MERGE-target. Every cluster DROP/DEFER/MOVE → the plan stays live and untouched.

### 1. Live source plan

An input under `docs/plans/` whose `status:` is NOT `implemented`, `abandoned`, or `superseded` (`landed` with open spine rows and `deferred` are live). Terminal plans, handoffs and research owe nothing.

Read the set off the engine, then intersect it with the inputs: `coordinator-invoke records.query '{"type":"plan","where":"status!=implemented AND status!=abandoned AND status!=superseded","format":"json"}'`.

### 2. Retire in order: migrate, stamp, stand down

**MUST NOT stamp a plan `superseded` before its uniquely load-bearing prose is migrated.**

1. **Migrate** that prose into the inheriting stubs' `## What this covers` / `## Specification`.
2. **Stamp**, both halves, literally:

   ```
   status: superseded
   superseded_by: state/roadmap/<run-id>/STUB-INDEX.md
   ```
3. **Stand down the owed review**: cancel it with a one-line reason naming the roadmap as replacement spine, e.g. "superseded by `state/roadmap/<run-id>/STUB-INDEX.md`; the stubs are the spine." Never defer it. This is not `coordinator/skills/handoff/residue/050-supersession.md`'s stand-down notice (an outbound memo, sent BEFORE its stamp).
