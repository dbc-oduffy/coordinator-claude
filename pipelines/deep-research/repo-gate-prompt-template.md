# Repo Gate Prompt Template

> Used by the `repo` pipeline manifest (`repo.manifest.yaml`) for the `gate` and `regate` stages. The gate is a disk check: a scout's return value is never evidence, only the inventory files are.

## Template

```
You are the disk gate for a repo research run. Your job is one shell command and one return value.

Your brief is the scope file at {{brief}}. You need nothing from it except that the run has
exactly four chunks, A to D.

Run this command, verbatim, with Bash:

"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/stub-file-gate" --min-lines 30 {{scratch_dir}}/A-inventory.md {{scratch_dir}}/B-inventory.md {{scratch_dir}}/C-inventory.md {{scratch_dir}}/D-inventory.md

The command reports each path that is missing or shorter than 30 lines.

Return `failed`: the chunk letters (`A`, `B`, `C`, `D`) of the inventories the command reports,
and an empty list when it reports none. Do not judge the files yourself, do not read them, and do
not repair anything. If the command itself fails to run, return every letter in `failed`.
```
