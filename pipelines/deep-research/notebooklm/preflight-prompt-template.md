# Preflight Prompt Template

> The preflight stage's prompt in `nlm-preflight.manifest.yaml`. The only placeholders are the closed double-brace set.

## Template

```
You are the NotebookLM preflight stage. Check that NotebookLM can be reached before the run fires. Do no research.

## Steps

1. Run the preflight script off the plugin root, never cwd-relative. Resolve the plugin root first; the resolver tries `CLAUDE_PLUGIN_ROOT` first, then the installed plugin. It prints one line, the plugin root; call it `<plugin-root>`:

   ```bash
   "${COORDINATOR_SETTINGS_HOME:-${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings}/bin/resolve-coordinator-clone" --content-root
   ```

   On PowerShell 7 the same step is `& (Join-Path ($env:COORDINATOR_SETTINGS_HOME ?? (Join-Path ($env:CLAUDE_HOME ?? $HOME) ".coordinator-claude-settings")) "bin\resolve-coordinator-clone.exe") --content-root`.

   Then run the script, which prints one JSON object {ok, remedy, checks}. `<python>` is the interpreter resolved per `resolve-coordinator-bin.md` § Portability (`python3`, else `python`):

   ```bash
   <python> "<plugin-root>/pipelines/deep-research/notebooklm/nlm-preflight.py"
   ```

   On PowerShell 7: `python (Join-Path "<plugin-root>" "pipelines\deep-research\notebooklm\nlm-preflight.py")`.

   When the resolve step exits non-zero or prints nothing, do not run the script and do not search the disk for it. Write `{"ok": false, "remedy": ["unresolved plugin root — resolve-coordinator-clone --content-root failed: <its stderr line>"], "checks": {"plugin_root": "unresolved"}}` and return it.

2. Run `ToolSearch("select:mcp__notebooklm-mcp__notebook_query")`. The probe resolves when the tool's schema comes back; it misses when ToolSearch returns no match.

3. Combine: `ok` is true only when the script's `ok` is true AND the probe resolved. Start `remedy` from the script's `remedy` list. When the probe missed, append `! claude mcp add -s user notebooklm-mcp -- notebooklm-mcp` (unless the list already holds it) and `restart Claude Code`, each once. Add a `probe` entry (true or false) to `checks`, keeping the script's `checks`.

## Output

**Write to:** {{scratch_dir}}/preflight.json

Write exactly one JSON object {"ok": boolean, "remedy": [string], "checks": object} and return the same object. Copy remedy strings verbatim; never paraphrase a command. Never use `nlm login --check`. Do not retry a failing script more than once.
```
