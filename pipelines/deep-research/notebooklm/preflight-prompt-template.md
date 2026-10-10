# Preflight Prompt Template

> The preflight stage's prompt in `nlm-preflight.manifest.yaml`. The only placeholders are the closed double-brace set.

## Template

```
You are the NotebookLM preflight stage. Check that NotebookLM can be reached before the run fires. Do no research.

## Steps

1. Run the preflight script off the plugin root, never cwd-relative. It prints one JSON object {ok, remedy, checks}:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT:?coordinator plugin root unset — run this from a plugin command/skill, or substitute an absolute path}/pipelines/deep-research/notebooklm/nlm-preflight.py"
   ```
   ```powershell
   python "$env:CLAUDE_PLUGIN_ROOT\pipelines\deep-research\notebooklm\nlm-preflight.py"
   ```

2. Run `ToolSearch("select:mcp__notebooklm-mcp__notebook_query")`. The probe resolves when the tool's schema comes back; it misses when ToolSearch returns no match.

3. Combine: `ok` is true only when the script's `ok` is true AND the probe resolved. Start `remedy` from the script's `remedy` list. When the probe missed, append `! claude mcp add -s user notebooklm-mcp -- notebooklm-mcp` (unless the list already holds it) and `restart Claude Code`, each once. Add a `probe` entry (true or false) to `checks`, keeping the script's `checks`.

## Output

**Write to:** {{scratch_dir}}/preflight.json

Write exactly one JSON object {"ok": boolean, "remedy": [string], "checks": object} and return the same object. Copy remedy strings verbatim; never paraphrase a command. Never use `nlm login --check`. Do not retry a failing script more than once.
```
