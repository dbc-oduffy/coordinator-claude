# Source Gate Prompt Template

> The `source-gate` stage's prompt in `notebooklm.manifest.yaml`. Runs after the scout and before the workers; `halts_unless: ok` ends the run when a scout-provided notebook has no accessible source. The only placeholders are the closed double-brace set.

## Template

```
You are the NotebookLM source-gate stage. Decide whether the scout left every scout-provided notebook at least one usable source. Do no research and no judging of your own: the script decides.

## Steps

1. Resolve the plugin root, then run the gate script. It prints one JSON object {ok, remedy, checks}. The sources path is always {{scratch_dir}}/sources.md, present or not: an absent file is a failure the script reports.

   ```bash
   _sh=${COORDINATOR_SETTINGS_HOME:-${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings}
   if [ -n "$CLAUDE_PLUGIN_ROOT" ] && [ -d "$CLAUDE_PLUGIN_ROOT" ]; then
       _pr=$CLAUDE_PLUGIN_ROOT
   else
       if [ -n "$COORDINATOR_ENGINE_ROOT" ] && [ -d "$COORDINATOR_ENGINE_ROOT/coordinator" ]; then
           _content_root=$COORDINATOR_ENGINE_ROOT
       else
           _content_root=$(cat "$_sh/machine-local/.content-root" 2>/dev/null || cat "${CLAUDE_HOME:-$HOME}/.claude/.content-root" 2>/dev/null)
       fi
       if [ -n "$_content_root" ] && [ -d "$_content_root/coordinator" ]; then _pr=$_content_root/coordinator; else _pr=; fi
   fi
   _py=$(command -v python3 || command -v python)
   if [ -z "$_pr" ] || [ -z "$_py" ]; then echo UNRESOLVED; else "$_py" "$_pr/pipelines/deep-research/notebooklm/nlm-run-gate.py" sources --strategy "{{brief}}" --sources "{{scratch_dir}}/sources.md"; fi
   ```
   ```powershell
   $sh = if ($env:COORDINATOR_SETTINGS_HOME) { $env:COORDINATOR_SETTINGS_HOME } else { Join-Path ($(if ($env:CLAUDE_HOME) { $env:CLAUDE_HOME } else { $HOME })) ".coordinator-claude-settings" }
   $pr = $null
   if ($env:CLAUDE_PLUGIN_ROOT -and (Test-Path -PathType Container $env:CLAUDE_PLUGIN_ROOT)) { $pr = $env:CLAUDE_PLUGIN_ROOT }
   else {
       $doe = $null
       if ($env:COORDINATOR_ENGINE_ROOT -and (Test-Path -PathType Container (Join-Path $env:COORDINATOR_ENGINE_ROOT "coordinator"))) { $doe = $env:COORDINATOR_ENGINE_ROOT }
       else { foreach ($p in @((Join-Path $sh "machine-local\.content-root"), (Join-Path $(if ($env:CLAUDE_HOME) { $env:CLAUDE_HOME } else { $HOME }) ".claude\.content-root"))) { if (-not $doe -and (Test-Path $p)) { $doe = (Get-Content -Raw $p).Trim() } } }
       if ($doe -and (Test-Path -PathType Container (Join-Path $doe "coordinator"))) { $pr = Join-Path $doe "coordinator" }
   }
   if ($pr) { python (Join-Path $pr "pipelines\deep-research\notebooklm\nlm-run-gate.py") sources --strategy "{{brief}}" --sources "{{scratch_dir}}/sources.md" } else { "UNRESOLVED" }
   ```

2. When the output is UNRESOLVED, or the script printed anything other than one JSON object, the gate fails closed: ok is false, remedy is one line naming what happened. For an unresolved root: "unresolved plugin root — tried CLAUDE_PLUGIN_ROOT, COORDINATOR_ENGINE_ROOT, <settings-home>/machine-local/.content-root, $HOME/.claude/.content-root", with checks {"plugin_root": "unresolved"}. For a script error: the script's error text as the remedy. Never return ok true unless the script printed ok true.

## Output

**Write to:** {{scratch_dir}}/source-gate.json

Write exactly one JSON object {"ok": boolean, "remedy": [string], "checks": object} and return the same object, unchanged from the script's output. Copy remedy strings verbatim. Do not retry a failing script more than once.
```
