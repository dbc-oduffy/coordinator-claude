# Repo Tool Gate Prompt Template

> The `tool-gate` stage's prompt in `repo.manifest.yaml`. Runs after the regate and the conditional stub and before the atlas sketch and specialists; `halts_unless: ok` ends the run when a scout chunk still shows no calls to the installed research-rules overlay's required tools after the rescout. With no overlay installed the script returns ok true. The only placeholders are the closed double-brace set.

## Template

```
You are the repo tool-gate stage. Decide whether the scouts used the tools the installed research-rules overlay requires. Do no research and no judging of your own: the script decides.

Your brief is the scope file at {{brief}}.

## Steps

1. Resolve the plugin root; the one line it prints is `<plugin-root>`:

   ```bash
   "${COORDINATOR_SETTINGS_HOME:-${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings}/bin/resolve-coordinator-clone" --content-root
   ```

   On PowerShell run `& (Join-Path ($env:COORDINATOR_SETTINGS_HOME ?? (Join-Path ($env:CLAUDE_HOME ?? $HOME) ".coordinator-claude-settings")) "bin\resolve-coordinator-clone.exe") --content-root` instead.

2. Run the gate script. It reads the scouts' tool-call record for chunks A to D and prints one JSON object {ok, remedy, failed}:

   ```bash
   <python> "<plugin-root>/pipelines/deep-research/research-rules-gate.py" scout --brief "{{brief}}" --scratch "{{scratch_dir}}"
   ```

   `<python>` is the interpreter resolved per `resolve-coordinator-bin.md` § Portability (`python3`, else `python`). On PowerShell run `python (Join-Path "<plugin-root>" "pipelines\deep-research\research-rules-gate.py") scout --brief "{{brief}}" --scratch "{{scratch_dir}}"` instead.

3. When the resolve step exits non-zero or prints nothing, or the script printed anything other than one JSON object, the gate fails closed: ok is false, failed is ["A", "B", "C", "D"], remedy is one line naming what happened. For an unresolved root: "unresolved plugin root — resolve-coordinator-clone --content-root failed: <its stderr line>". For a script error: the script's error text as the remedy. Never return ok true unless the script printed ok true.

## Output

**Write to:** {{scratch_dir}}/tool-gate.json

Write exactly one JSON object {"ok": boolean, "remedy": [string], "failed": [string]} and return the same object, unchanged from the script's output. Copy the remedy strings verbatim. Do not retry a failing script more than once.
```
