# Claims Gate Prompt Template

> The `claims-gate` stage's prompt in `notebooklm.manifest.yaml`. Runs after the workers and before the sweep; `halts_unless: ok` ends the run when the worker fan-out differs from the strategy's `worker_count`, a worker ran outside the strategy, or the strategy's notebooks produced zero claims. The only placeholders are the closed double-brace set.

## Template

```
You are the NotebookLM claims-gate stage. Decide whether the workers produced a run worth sweeping. Do no research and no judging of your own: the script decides.

## Steps

1. Resolve the plugin root; the one line it prints is `<plugin-root>`:

   ```bash
   "${COORDINATOR_SETTINGS_HOME:-${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings}/bin/resolve-coordinator-clone" --content-root
   ```

   On PowerShell run `& (Join-Path ($env:COORDINATOR_SETTINGS_HOME ?? (Join-Path ($env:CLAUDE_HOME ?? $HOME) ".coordinator-claude-settings")) "bin\resolve-coordinator-clone.exe") --content-root` instead.

2. Run the gate script. It reads every <letter>-dispatch.json marker and <letter>-claims.json in the scratch directory and prints one JSON object {ok, remedy, checks}:

   ```bash
   <python> "<plugin-root>/pipelines/deep-research/notebooklm/nlm-run-gate.py" claims --strategy "{{brief}}" --scratch "{{scratch_dir}}"
   ```

   `<python>` is the interpreter resolved per `resolve-coordinator-bin.md` § Portability (`python3`, else `python`). On PowerShell run `python (Join-Path "<plugin-root>" "pipelines\deep-research\notebooklm\nlm-run-gate.py") claims --strategy "{{brief}}" --scratch "{{scratch_dir}}"` instead.

3. When the resolve step exits non-zero or prints nothing, or the script printed anything other than one JSON object, the gate fails closed: ok is false, remedy is one line naming what happened. For an unresolved root: "unresolved plugin root — resolve-coordinator-clone --content-root failed: <its stderr line>", with checks {"plugin_root": "unresolved"}. For a script error: the script's error text as the remedy. Never return ok true unless the script printed ok true.

## Output

**Write to:** {{scratch_dir}}/claims-gate.json

Write exactly one JSON object {"ok": boolean, "remedy": [string], "checks": object} and return the same object, unchanged from the script's output. Copy remedy strings verbatim. Do not retry a failing script more than once.
```
