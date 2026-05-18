# Backlog Prune Discipline

Backlog-managing skills must delete resolved entries and name the closed IDs in the commit subject — the audit trail lives in `git log`, not in graveyard sections appended to the file.

## Why Deletion, Not Annotation

The queue file is a workspace, not a ledger. Its job is to show what is open — nothing else. When a resolved entry stays in the file (even crossed out or flagged `resolution: done`), readers must mentally filter noise on every read, and `/update-docs` Phase 11i strips the annotations on the next run anyway, leaving a silent orphan line with no history attached. Deleting the line in the same commit that ships the fix binds the two events together in `git log` at zero extra cost.

## The Discipline

- **Delete the line in the same commit that ships the fix.** The fix commit and the queue-line removal are one atomic unit — splitting them creates a window where the queue misrepresents open work.
- **Name the closed entry IDs in the commit subject.** The subject line is the index into `git log -- <queue-file>`; without it, the audit trail requires reading every diff. Example: `fix: collapse duplicate scout step [closes queue: 2026-05-12 | coordinator | skills/scout.md:44]`.
- **Never append "resolved/done/closed/complete" inline.** Phase 11i strips `resolution: done`, `resolution: in_progress`, and `recurring: 0` sub-lines on every `/update-docs` run. The correct primitive is line deletion, not annotation.

## Anti-Patterns

| Anti-pattern | Why it fails |
|---|---|
| `## History` / `## Closed` / `## Done` section appended to queue file | Phase 11i strips it; entry becomes an orphan with no fix attribution |
| `resolution: done` sub-line under the entry | Stripped by Phase 11i; looks resolved but never leaves the workspace |
| `## Archive` subsection in `bug-backlog.md` | Same stripping rule applies; git log is the archive |
| Marking entry complete without staging the queue file in the same commit | Splits the atomic unit; queue temporarily misrepresents open work |
| Dropping the entry from a dispatch queue without a corresponding commit | "Drop from dispatch queue" is not the same as closing — no paper trail exists |

## Audit Recipe

To see when an entry was added and when it was removed:

```bash
git log --oneline -- tasks/improvement-queue.md
git log --oneline -- tasks/coordinator-improvement-queue.md
git log -p -- tasks/improvement-queue.md | grep "^[-+].*<entry-fragment>"
```

The removal commit subject names the closed entry; the diff confirms the line was deleted, not annotated.

## Cross-Links

- Canonical rule: `coordinator/CLAUDE.md` § Improvement Queue — "On resolution, delete the entry. Commit subject names the closed entry; `git log -- <queue-file>` is the audit trail."
- Phase 11i stripping behavior: same section, "No `## History` / `## Closed` / `## Done` / `## Archive` / `## Closeout` graveyard sections."
- Applies to: `tasks/improvement-queue.md`, `~/.claude/tasks/coordinator-improvement-queue.md`, `tasks/bug-backlog.md`.
