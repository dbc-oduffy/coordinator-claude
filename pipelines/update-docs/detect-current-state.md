# Phase 1: Detect Current State (Silent)

1. Source inventory: diff actual source files against any existing directory index —
   undocumented/missing/renamed files, new directories.
2. Plan docs, in priority order: `tasks/<feature>/todo.md`, `docs/plans/` (canonical),
   `~/.claude/plans/` (copy approved items to `docs/plans/`), `tasks/plans/`. Flag
   completed-in-code plans and done-but-marked-in-progress plans.
3. Recent git context (supplementary): `git log --oneline -15`; `git log --oneline
   origin/HEAD..HEAD 2>/dev/null` for unpushed commits.

## The `updatedocs.gates` invocation — one authority

Every later phase's "Detect first" step calls the same op:
`& "$env:COORDINATOR_SETTINGS_HOME\bin\coordinator-invoke.exe" updatedocs.gates '{}'` (Shape W /
Shape A-B POSIX — `snippets/resolve-coordinator-bin.md`). It is a detect-only op: no gate it runs
writes or moves anything, and every guard downstream still runs. Each gate's verdict is tri-state
— a repo it cannot see reads `unavailable`, which means "not checked", never "clean". A phase page
names only its own gate and what that gate does not write; the invocation shape and the
`unavailable`/tri-state semantics live here.
