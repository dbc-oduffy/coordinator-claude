<!-- Updated 2026-06-15 by structured-queue-medium-rollout C15: directory-form vs markdown-line distinction; § Cross-Links rewritten -->
<!-- Updated 2026-06-23 by cockpit-contract-ext C2c: central queue migrated to directory-form; markdown-line section retired -->
---
last-updated: 2026-06-15
---

# Backlog Prune Discipline

Backlog-managing skills must close resolved entries and name the closed IDs in the commit subject — the audit trail lives in `git log`, not in graveyard sections appended to the file.

## Queue Shape — Directory-Form

All coordinator queues use the directory-form shape. The legacy markdown-line central queue (`state/coordinator-improvement-queue.md`) was migrated to directory-form in June 2026 (cockpit-contract-ext C2c).

### Directory-Form Queues

**Applies to:** `state/debt-backlog/`, `state/bug-backlog/`, `state/improvement-queue/` (all tiers — project-scoped rows AND central universal rows tagged `queue_scope: central`).

Each entry is one YAML file: `state/<queue>/<id>.yaml`. The directory is the queue; individual files are the entries.

**Closure mechanic:**

1. Stamp closure frontmatter BEFORE moving the file — edit `state/<queue>/<id>.yaml` to set:
   ```yaml
   status: closed
   closed_at: <ISO date>        # e.g. 2026-06-15
   closed_by: <commit-sha>      # SHA of the fix commit
   ```
2. Move the file to archive:
   ```bash
   git mv state/<queue>/<id>.yaml archive/<queue>/<YYYY-MM>/<id>.yaml
   ```
3. Commit the stamped-then-moved file in the same commit as the fix. The commit subject names the closed entry ID.

**Audit trail:** `git log --oneline -- state/<queue>/<id>.yaml` shows the entry's history; `git log --oneline -- archive/<queue>/<YYYY-MM>/<id>.yaml` shows closure history. Git preserves the full per-entry history through the `git mv` because git tracks content, not paths.

**Empty-directory guard:** After batch closures, an empty source directory causes `git mv` to abort. Handle with:
```bash
rmdir state/<queue>/ 2>/dev/null || true
```
Run this after all `git mv` operations in the batch, before committing.

**Never annotate inline.** A `## Closed` section in a directory-form queue's index file (if any) is forbidden — closure is via `git mv` to archive, not inline annotation. There is no index file to annotate; each entry is its own file.

---

## Why This Matters

The queue file (or directory) is a workspace, not a ledger. Its job is to show what is open — nothing else. When a resolved entry stays visible (annotated, crossed out, or flagged `resolution: done`), readers must mentally filter noise on every read. The git log carries the history at zero extra cost; the workspace carries only open work.

For directory-form queues, `git mv` preserves per-entry history through the move, making closed entries queryable in `archive/` without polluting the live queue.

## The Discipline

- **Stamp frontmatter, then `git mv` to archive, in the same commit as the fix.**
- **Name closed entry IDs in the commit subject.** The subject line is the index into `git log`; without it, the audit trail requires reading every diff. Example: `fix: collapse duplicate scout step [closes queue: b7e3d2f1]`.
- **Never annotate "resolved/done/closed/complete" inline** in a YAML entry.

## Anti-Patterns

| Anti-pattern | Why it fails |
|---|---|
| Dropping an entry from the queue without a corresponding commit | "Drop from dispatch queue" is not the same as closing — no paper trail exists |
| Stamping `status: closed` frontmatter WITHOUT the subsequent `git mv` | Entry stays in the live queue dir; `coordinator-queue-append` reads all files in the dir as open; frontmatter alone is not closure |
| Running `git mv` before stamping closure frontmatter | The archived file lands without closure metadata; `closed_at` / `closed_by` are unresolvable after the move without editing the archive |
| Annotating `status: closed` inline without `git mv` for central entries tagged `queue_scope: central` | Same as project entries — central rows use directory-form closure; line-deletion is retired |

## Audit Recipe

To see when an entry was added and when it was closed:

```bash
# Full history for an open entry:
git log --oneline -- state/<queue>/<id>.yaml

# Full history for a closed entry (both sides of the mv):
git log --oneline -- state/<queue>/<id>.yaml
git log --oneline -- archive/<queue>/<YYYY-MM>/<id>.yaml

# See the closure diff:
git log -p -- archive/<queue>/<YYYY-MM>/<id>.yaml | head -40
```

Git preserves the rename-chain across the `git mv`, so the combined history spans both paths.

## Cross-Links

- Canonical rule: `coordinator/CLAUDE.md` § Improvement Queue — closure mechanics, two-tier model.
- Structured-form rollout: `coordinator/CLAUDE.md` § Improvement Queue — directory-form shape + `coordinator-queue-append` CLI.
- Central-queue migration: `docs/plans/2026-06-22-cockpit-contract-ext.md` § C2c — prose→YAML migration of `state/coordinator-improvement-queue.md`.
- Schema docs (per-queue field contracts): `docs/wiki/debt-backlog-schema.md`, `docs/wiki/bug-backlog-schema.md`, `docs/wiki/improvement-queue-schema.md`.
- Applies to:
  - `state/debt-backlog/` (directory-form)
  - `state/bug-backlog/` (directory-form)
  - `state/improvement-queue/` (directory-form — project-scoped rows AND central universal rows tagged `queue_scope: central`)
