# Preflight Prompt Template

> The preflight stage's prompt in `nlm-preflight.manifest.yaml`. The only placeholders are the closed double-brace set.

## Template

```
You are the NotebookLM preflight stage. Check that NotebookLM can be reached before the run fires. Do no research.

## Steps

1. Run the preflight script off the plugin root, never cwd-relative. A non-empty `CLAUDE_PLUGIN_ROOT` naming a directory wins; otherwise the root comes from `COORDINATOR_ENGINE_ROOT`, then the `.content-root` pointers. It prints one JSON object {ok, remedy, checks}:

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
       [ -n "$_content_root" ] && [ -d "$_content_root/coordinator" ] || { echo "unresolved plugin root" >&2; exit 1; }
       _pr=$_content_root/coordinator
   fi
   _py=$(command -v python3 || command -v python) || { echo "no python interpreter on PATH" >&2; exit 1; }
   "$_py" "$_pr/pipelines/deep-research/notebooklm/nlm-preflight.py"
   ```
   ```powershell
   $sh = if ($env:COORDINATOR_SETTINGS_HOME) { $env:COORDINATOR_SETTINGS_HOME } else { Join-Path ($env:CLAUDE_HOME ?? $HOME) ".coordinator-claude-settings" }
   $pr = $env:CLAUDE_PLUGIN_ROOT
   if (-not ($pr -and (Test-Path $pr -PathType Container))) {
       $doe = $env:COORDINATOR_ENGINE_ROOT
       if (-not ($doe -and (Test-Path (Join-Path $doe "coordinator") -PathType Container))) {
           $doe = $null
           foreach ($f in @((Join-Path $sh "machine-local\.content-root"), (Join-Path ($env:CLAUDE_HOME ?? $HOME) ".claude\.content-root"))) { if (-not $doe -and (Test-Path $f)) { $doe = (Get-Content $f -Raw).Trim() } }
       }
       if (-not ($doe -and (Test-Path (Join-Path $doe "coordinator") -PathType Container))) { Write-Error "unresolved plugin root"; exit 1 }
       $pr = Join-Path $doe "coordinator"
   }
   python (Join-Path $pr "pipelines\deep-research\notebooklm\nlm-preflight.py")
   ```

   When the ladder refuses with "unresolved plugin root", do not run the script and do not search the disk for it. Write `{"ok": false, "remedy": ["unresolved plugin root — tried CLAUDE_PLUGIN_ROOT, COORDINATOR_ENGINE_ROOT, <settings-home>/machine-local/.content-root, <home>/.claude/.content-root"], "checks": {"plugin_root": "unresolved"}}` and return it.

2. Run `ToolSearch("select:mcp__notebooklm-mcp__notebook_query")`. The probe resolves when the tool's schema comes back; it misses when ToolSearch returns no match.

3. Combine: `ok` is true only when the script's `ok` is true AND the probe resolved. Start `remedy` from the script's `remedy` list. When the probe missed, append `! claude mcp add -s user notebooklm-mcp -- notebooklm-mcp` (unless the list already holds it) and `restart Claude Code`, each once. Add a `probe` entry (true or false) to `checks`, keeping the script's `checks`.

## Output

**Write to:** {{scratch_dir}}/preflight.json

Write exactly one JSON object {"ok": boolean, "remedy": [string], "checks": object} and return the same object. Copy remedy strings verbatim; never paraphrase a command. Never use `nlm login --check`. Do not retry a failing script more than once.
```
