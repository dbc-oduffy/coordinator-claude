# Migration Script Conventions

**Purpose.** Rules for scripts that rename, relocate, or restructure files in the repo (path-rename migrations, directory reorganizations, scaffolding reshapes). Two recurring failure modes hit every migration that wasn't written with these in mind.

## 1. Enumerate with `find`, not `grep --include`

**Extension allowlists in `grep --include` silently miss non-standard-extension files.** A migration that gathers its source files with `grep -r --include='*.sh' --include='*.py'` will silently skip `.bats` test runners, `.tmpl` template files, extensionless bin scripts, and any other file the author didn't enumerate. The migration completes with exit 0; the skipped files are left in the old location; downstream tooling breaks on them.

**Use `find` with explicit `-type f`** and add extension pruning only as an opt-in filter — not as the discovery mechanism:

```bash
# Wrong — silently misses .bats, .tmpl, extensionless files
grep -r --include='*.sh' --include='*.py' -l 'old_pattern' .

# Right — enumerate all files, then filter if needed
find . -type f | grep -v '.git' | while IFS= read -r f; do
    # process $f
done
```

When the migration's scope is "all scripts under path X", use `find path/X -type f` with no extension filter at all — let the script decide per-file whether to act.

**Empirical source (queue line 57, 2026-06-08):** a path-rename migration used `grep --include='*.sh' --include='*.py'` and shipped without touching `.bats` runners and extensionless bin scripts that lived alongside the renamed paths. The omission was invisible in CI because the skipped files still resolved (from the old path, which hadn't been deleted yet).

## 2. `rmdir` empty source directories before `git mv`

**`git mv` aborts when the source directory is empty.** A migration that deletes all content from a directory and then tries to `git mv dir/ newdir/` will fail: git cannot move an empty directory (git does not track empty dirs). The migration halts mid-run, leaving the repo in a partially-migrated state.

**Remove empty directories explicitly before any `git mv`** that moves a directory as a unit:

```bash
# After moving/deleting all content out of old_dir:
find old_dir -type d -empty -delete   # rmdir empties (depth-first)
# Now git mv of the remaining non-empty subtree is safe
```

If the migration moves files individually (not directories as a unit), empty-dir cleanup is still required before the final commit: git will silently leave empty dirs in the working tree, and a subsequent `git add` won't stage them (nothing to stage). Clean up with `find . -type d -empty -delete` before committing.

**Empirical source (queue line 58, 2026-06-08):** a path-rename migration moved all files out of a source dir then attempted `git mv old_dir/ new_dir/`. `git mv` aborted on the now-empty source. The migration had to be re-run with an `rmdir` step inserted before the `git mv`.
