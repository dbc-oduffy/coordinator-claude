<!-- canonical source for premise-check-consumption. Inline-only: cited by path, no sentinel
     block in any consumer and no verify script, per docs/wiki/coordinator-tripwires/README.md
     § Snippet-sync category 4. -->

## Reading a premise-check report

A premise check resolves a plan's load-bearing citations against the tree. It names the **class**
it checked and nothing beyond it. It is **necessary, not sufficient**: a plan whose every citation
resolves can still be wrong.

**A clean report is not an approval, and does not narrow your review.** Read it as work already
done on one class, not as a verdict on the plan.

**Per-citation verdicts:**

- **RESOLVES** — the cited thing exists and matches the plan's claim on the class checked. Do not
  re-verify it.
- **UNRESOLVED** — the cited thing is absent. A finding to apply; the plan says something false
  about the tree.
- **CONTRADICTED** — the thing exists and the tree says otherwise: a docstring describing a
  different job, a wiki page forbidding the assumption, a sanctioned resolver that raises. The
  path resolving does not soften this — it is the class an existence check misses.
- **UNCHECKABLE** — no surface in this tree settles it. **Not a pass.** The assumption is yours to
  judge, and the report names which one.

**Where no report ran**, the class is unchecked, not clean.

## Reading a can-report-red verdict

`coordinator/bin/instrument-can-report-red.py` answers one intent-free question about one file:
can a value it computes change the status it reports? It never learns what the instrument is for,
which is why one surface serves every reader of this tell. Call it; do not restate its predicate.

- **ARMED** — a computed value reaches the exit. It says nothing about whether the instrument
  measures the right thing.
- **CONSTANT_EXIT / SEALED_EXIT / NO_EXIT_PATH** — the verdict is computed and
  the status cannot move with it, or the file reports no status at all. A green from such an
  instrument is not evidence.
- **UNCHECKABLE** — the file could not be read. Unread is not armed.

Its stated residuals: it follows names through assignment inside one file, so a verdict laundered
through another module, through a file the instrument writes and reads back, or through `exec`
indirection is invisible to it. Where those matter, read the instrument.
