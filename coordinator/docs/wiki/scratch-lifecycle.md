# Scratch Lifecycle for Skill-Emitted Working Notes

> Skills that emit working-notes scratch (`/distill` → `state/scratch/artifact-distillation/<date>-pass<N>/`, `/bug-blitz` → `tasks/scratch/bug-sweep/<date>-<time>/`, etc.) must self-clean on success. Post-ship dirty files in `tasks/scratch/<skill>/` show up as untracked in the next session and read as noise to a fresh EM. Tracking them in git is a two-step (commit-then-delete) anti-pattern.

*Lesson surface: 2026-05-16, claude-unreal-holodeck — 14 distill-pass-23 working files surfaced as untracked after the real outputs (6 archived specs, 22 deleted scaffolds, 6 wiki updates) had already shipped. Bug-sweep had the same shape: files got tracked, then deleted one commit later as obvious post-hoc noise. PM call: scratch artifacts are not useful post-ship.*

## Two acceptable patterns

### Pattern A — emitting skill self-cleans on success

```
Phase N (final, after canonical outputs are committed):
  - rm -rf tasks/scratch/<skill>/<run-id>/
  - git add tasks/scratch/   # if anything was committed; usually no-op
  - log: "Scratch cleaned: <run-id>"
```

The skill's last act is to delete its own working directory. Canonical outputs (the wiki edits, the queue closures, the archive entries, the doc updates) are already committed; the scratch was load-bearing only during the run. Deletion is unconditional on success; on failure the scratch is preserved for diagnosis (and the next run's first act is to inspect it).

### Pattern B — gitignored scratch + breadcrumb

```
.gitignore: tasks/scratch/
Skill writes a one-line receipt:
  tasks/scratch/<skill>/<date>-receipt.txt
  "<skill> run <date> at <time>; outputs: <commit-sha-list>"
```

The scratch directory is never tracked. A small receipt at a stable path provides "yes this skill ran today" provenance without dragging the working notes into git. The receipt is itself optional — `git log --grep '<skill>(...)'` is usually a better provenance trail.

## Anti-patterns

- **Tracking scratch.** Working notes go into a commit, then the next session deletes them as obvious noise. The two-step is pure ceremony.
- **Leaving scratch around "in case it's useful."** It almost never is. The conclusions that were useful are already in the canonical outputs (wiki, queue, archive). The notes that led to those conclusions are not load-bearing once the conclusion has shipped.
- **Conditional clean.** "Delete scratch only if the run was clean / only if no errors / only if PM approves." The conditional is rarely satisfied, scratch accumulates, the next session sees a dirty tree. Make cleanup unconditional on success.

## When scratch IS useful post-ship

Two narrow cases:

1. **Diagnostic artifacts for a failed run.** If the skill failed and the scratch carries diagnostic state, preserving it is correct — the next session's first act is to read it. But "failed" is a structural verdict, not "the EM had to think harder than expected."
2. **Cross-session ledgers that the skill itself reads on next run.** A `tasks/scratch/<skill>/last-run.json` carrying state the next run needs (e.g. "items skipped last time because they were blocked") is legitimate — but at that point it is not scratch, it is the skill's persistent state, and should live somewhere greppable (`tasks/<skill>/state.json`, frontmatter on a tracked file).

Anything that is neither of those is post-ship noise.

## Where this surfaces in this codebase

- `state/scratch/artifact-distillation/<date>-pass<N>/` — `/distill` working notes.
- `tasks/scratch/bug-sweep/<date>-<time>/` — `/bug-blitz` and `/bug-sweep` working notes.
- `tasks/learn-lessons-<date>/` — `/learn-lessons` routing artifacts. (Borderline: the routing manifest is sometimes useful as audit trail for a central-mode run; the per-repo scout records are pure scratch.)

The skill-author convention: name the scratch path under `tasks/scratch/<skill>/<run-id>/` so a single `.gitignore` rule and a single cleanup convention cover them all.

## Cross-references

- [`cleanup-sweep-hazards.md`](./cleanup-sweep-hazards.md) — sibling failure modes for cleanup operations.
- [`writing-skills.md`](./writing-skills.md) — when writing a new skill that emits scratch, name the cleanup phase explicitly.
- [`scoped-safety-commits.md`](./scoped-safety-commits.md) — explicit-path commits keep scratch out of unrelated commits even when it does end up tracked.
