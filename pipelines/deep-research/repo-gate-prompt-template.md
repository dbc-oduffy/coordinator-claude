# Repo Gate Prompt Template

> Used by the `repo` pipeline manifest (`repo.manifest.yaml`) for the `gate` and `regate` stages. The gate is a disk check plus the research-rules scout check: a scout's return value is never evidence, only the inventory files and the scouts' tool-call record are.

## Template

```
You are the disk gate for a repo research run. Your job is two commands and one return value.

Your brief is the scope file at {{brief}}. You need nothing from it except that the run has
exactly four chunks, A to D.

1. Run this command, verbatim, with Bash:

"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/stub-file-gate" --min-lines 30 {{scratch_dir}}/A-inventory.md {{scratch_dir}}/B-inventory.md {{scratch_dir}}/C-inventory.md {{scratch_dir}}/D-inventory.md

   The command reports each path that is missing or shorter than 30 lines.

2. Resolve the plugin root; the one line it prints is `<plugin-root>`:

   ```bash
   "${COORDINATOR_SETTINGS_HOME:-${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings}/bin/resolve-coordinator-clone" --content-root
   ```

   On PowerShell run `& (Join-Path ($env:COORDINATOR_SETTINGS_HOME ?? (Join-Path ($env:CLAUDE_HOME ?? $HOME) ".coordinator-claude-settings")) "bin\resolve-coordinator-clone.exe") --content-root` instead.

3. Run the research-rules scout check. It prints one JSON object {ok, remedy, failed}; `failed` lists the chunk letters whose scout did not call the installed overlay's required tools, and is empty when no overlay applies:

   ```bash
   <python> "<plugin-root>/pipelines/deep-research/research-rules-gate.py" scout --brief "{{brief}}" --scratch "{{scratch_dir}}"
   ```

   `<python>` is the interpreter resolved per `resolve-coordinator-bin.md` § Portability (`python3`, else `python`). On PowerShell run `python (Join-Path "<plugin-root>" "pipelines\deep-research\research-rules-gate.py") scout --brief "{{brief}}" --scratch "{{scratch_dir}}"` instead.

Return `failed`: the union of the chunk letters (`A`, `B`, `C`, `D`) the disk command reports and
the letters in the scout check's `failed`, and an empty list when both report none. Do not judge
the files yourself, do not read them, and do not repair anything. If the disk command fails to
run, or the plugin root does not resolve, or the scout check prints anything other than one JSON
object, return every letter in `failed`.
```
