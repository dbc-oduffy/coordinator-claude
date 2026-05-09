# Cleanup, Sweep, and Migration Hazards

**Provenance:** consolidated 2026-05-05 from `tasks/lesson-triage-2026-05-05/SYNTHESIS.md` §B8.

Cleanup operations — `/distill`, `/update-docs`, link-heal, scaffolding-deletion, auto-discovery glob configs — are higher-risk than they look. They run across many files at once, often without per-file judgment, and they routinely undo work nobody noticed they were doing. This guide enumerates the recurring failure modes.

## 1. Scaffolding-Deletion Needs Active-Reference Check

Before deleting a scaffolding directory under `tasks/`, grep for references to its files from any *active* canonical spec — not just its own shipped parent plan. A scratch file's parent workstream may have shipped while the same file is load-bearing for a *different*, still-active workstream.

**Concrete failure:** `/distill` deleted `tasks/scratch/2026-04-30-shakedown2-verification.md` because it lived in a "scratch" dir whose dominant content was post-ship review residue. But the still-active `2026-04-30-shakedown-2-response.md` plan referenced it verbatim as canonical evidence for the WS-G workstream verifier. Recovery via `git show <sha>^:<path>` worked, but only because Phase E's link-heal sweep happened to catch the dangling reference.

**Defense:** before any `rm -rf tasks/<dir>/`, run

```bash
grep -rE "tasks/<dir>/" docs/plans/ tasks/<other-dirs>/ CLAUDE.md MEMORY.md
```

and flag any hits in active (non-archived) docs. Only proceed if every hit is in archived/historical content.

## 2. Sed-Based Link-Heal Over-Rewrites Provenance Frontmatter

When sweeping `s|docs/plans/X.md|archive/specs/X.md|g` across a repo, the regex hits both intended Spec backlinks AND provenance frontmatter fields like `original_path: docs/plans/X.md` — where the original location is the *literal* point of the field.

**Concrete failure:** the distill Phase E sed pass rewrote 98 files correctly for `Spec backlink:` comments, but corrupted `original_path:` provenance frontmatter on 9 wiki entries from `docs/plans/` to `archive/specs/` — making the provenance frontmatter self-referential and lying about where the spec originally lived.

**Defense:** anchor the regex to exclude provenance fields:

```bash
sed -E '/^(original_path|originally|pre-archive):/!s|docs/plans/X.md|archive/specs/X.md|g'
```

OR do a post-sweep audit: grep for the *new* path in fields where the *old* path is semantically correct, restore those before committing.

## 3. Stale Doc References — Repoint Before You Create

When a doc-link-checker surfaces N references to M missing pages, **don't** default to "create M pages." For each missing page, ask: does the referenced content actually need its own surface, or is it already covered by existing pages + a canonical section in CLAUDE.md? Repoint when covered; create only when genuinely missing.

**Concrete failure averted:** the bug-backlog had 8 references to 2 missing wiki pages. The naive fix is "create both." But one page's claimed scope was already 100% covered by existing wiki pages + CLAUDE.md — a new page would have duplicated and drifted. The other page's scope was genuinely unmet. The hybrid fix (create one, repoint the other) was right.

**Defense:** before creating a new doc-surface to satisfy stale references, grep the references' descriptors against existing wiki + CLAUDE.md. If existing surfaces already carry that content, repoint instead of creating.

## 4. Auto-Discovery Globs Sweep In Stale Backups

`structural.py:_discover_overlays()` did `glob('structural_*.sqlite3')` after the env-var check; a 12-day-old `structural_index.v3_backup_*.sqlite3` in the canonical directory got auto-attached as `overlay_0`, and the cross-schema dedup query then failed on a missing-column. Cost: 5-min fix once correctly diagnosed vs. a 2-7h env-var hunt against the wrong cause.

**Defense:** any "or auto-discover" config branch needs either:

1. An explicit glob pattern that excludes obvious backup naming: `*backup*`, `*.bak*`, `*-bak*`, `*.partial`.
2. **Or** explicit registration only — no fall-through glob.

Stale backups are the silent footgun in any "env var → fallback to glob" config layer.

## 5. Defend Structural Invariants With Snapshot Tests, Not Commit-Message Discipline

A commit titled `path-sweep + grep gate + allowlist` silently reverted a prior single-source-of-truth refactor by re-adding 7 trimmed lines to a `Build.cs` file. No future reviewer will catch this from commit messages — the title sounds like it's *enforcing* the invariant, not violating it.

**Defense:** for any structural invariant that load-bearing tests/specs depend on, encode it as a snapshot test (allowlist of permitted lines under version control), not as a norm about commit hygiene. The snapshot blocks scope-expanded commits at CI; norms don't.

## 6. Hardcoded Developer-Machine Paths Hurt Every External Consumer

A SessionStart hook had a hardcoded fallback `$KnownRoots = @("X:\<project-1>", "E:\dev\ue\Keep_Blank")` for graph.db location when env vars were unset. Worked silently on the author's machine. Would have emitted nothing useful (or worse, misleading freshness reports about the wrong codebase) on every external consumer with a different drive layout.

**Defense pattern** for any path-resolution fallback in shipped tooling:

1. Explicit env var override.
2. Marker-convention discovery walking up from cwd (e.g., `Saved/ProjectRag/graph.db`).
3. Silent skip — **never** a hardcoded path.

Add a cwd-scope guard so the tool refuses to act when the resolved root doesn't contain cwd (prevents acting on the wrong project even when discovery succeeds). Same trap exists for any reflexive "preamble" injected into agent prompts that depends on user-scoped configuration but should be project-scoped.

## Skill Checklist Reference

`/distill` and `/update-docs` should reference items 1, 2, and 3 in their dispatch prompts so the agent enforces these checks during sweep operations, not just the EM after the fact.
