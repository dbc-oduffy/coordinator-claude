# Deletion-List Hygiene

When converting a deletion manifest (markdown table) into a list of paths to feed `git rm`, **anchor on column position**, not on substring-grep of the manifest body. Loose grep sweeps paths the scout *referenced* (cross-references, "see also" mentions, prose citations) into the deletion list.

## Failure mode

Phase 3 produces a manifest like:

```
| Source path | Disposition | Reason |
|---|---|---|
| tasks/foo/notes-2026-04-29.md | DISTILLED → DELETE | folded into docs/wiki/foo.md |
| tasks/bar/raw.md | EPHEMERAL → DELETE | scratch; see also tasks/foo/notes-2026-04-29.md |
```

A naive `grep '\.md' manifest.md` over the manifest body will match `tasks/foo/notes-2026-04-29.md` **twice** — once in the source-path column, once in the reason column where it appears as a backreference. That extra match silently expands the deletion list with referenced (but not approved-for-deletion) paths.

## Required procedure

1. **Column extraction only.** Use `awk -F'|' 'NR>2 {gsub(/^ *| *$/,"",$2); print $2}' manifest.md` to pull the source-path column; equivalent column extractor in any tool is fine.
2. **Per-row validation.** Each extracted cell must parse as a single relative path (no spaces, no commas, no bracket syntax, ends in `.md`). Any cell that fails parse → abort and report the row to the EM.
3. **Fail closed on count mismatch.** Manifest row count (excluding header + separator) must equal extracted-path count. Mismatch = abort.

## Why this lives in distillation specifically

The artifact-distillation pipeline routinely produces manifests where source paths cross-reference each other in the Reason column (e.g., "consolidated into the same wiki guide as `<other-source>`"). Other deletion contexts (commit-time `git status` audit, sweep scripts) operate on filesystem state, not on a manifest body, and aren't subject to this failure mode.

## See also

- `pipelines/artifact-distillation/PIPELINE.md` Phase 5 step 5 — primary consumer
- `coordinator/CLAUDE.md` § Implementation Standards — "Detect-then-silently-pick is a footgun" (related)
