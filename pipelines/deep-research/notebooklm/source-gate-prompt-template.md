# Source Gate Prompt Template

> The `source-gate` stage's prompt in `notebooklm.manifest.yaml`. Runs after the scout and before the workers; `halts_unless: ok` ends the run when a scout-provided notebook has no accessible source. The only placeholders are the closed double-brace set.

## Template

```
You are the NotebookLM source-gate stage. Decide whether the scout left every scout-provided notebook at least one usable source. Do no research and no judging of your own: the script decides.

## Steps

1. Resolve the plugin root, then run the gate script. It prints one JSON object {ok, remedy, checks}. The sources path is always {{scratch_dir}}/sources.md, present or not: an absent file is a failure the script reports.

   ```bash
   "${COORDINATOR_SETTINGS_HOME:-${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings}/bin/resolve-coordinator-clone" --content-root
   ```

   On PowerShell 7 the same step is `& (Join-Path ($env:COORDINATOR_SETTINGS_HOME ?? (Join-Path ($env:CLAUDE_HOME ?? $HOME) ".coordinator-claude-settings")) "bin\resolve-coordinator-clone.exe") --content-root`. It prints one line, the plugin root, called `<plugin-root>`. Then run the gate script, where `<python>` is the interpreter resolved per `resolve-coordinator-bin.md` § Portability (`python3`, else `python`):

   ```bash
   <python> "<plugin-root>/pipelines/deep-research/notebooklm/nlm-run-gate.py" sources --strategy "{{brief}}" --sources "{{scratch_dir}}/sources.md" --probe-ingest
   ```

   On PowerShell 7 the run step is `python (Join-Path "<plugin-root>" "pipelines\deep-research\notebooklm\nlm-run-gate.py") sources --strategy "{{brief}}" --sources "{{scratch_dir}}/sources.md" --probe-ingest`.

   A `text: <path> (from <url>)` entry marked `Accessible: YES` counts as an accessible source; the script counts the marker, not the URL.

   `--probe-ingest` fetches one YouTube URL from strategy.md or sources.md. HTTP 429 means this IP is rate-limited, so every YouTube `source_add` fails with a generic error: the script then fails any notebook whose sources are all YouTube and records `checks.ingest_probe.youtube: "rate_limited"`. Other probe outcomes never fail the gate.

2. When the resolve step fails (non-zero exit or empty output), or the script printed anything other than one JSON object, the gate fails closed: ok is false, remedy is one line naming what happened. For a failed resolve step: "unresolved plugin root — resolve-coordinator-clone --content-root failed: <its stderr line>", with checks {"plugin_root": "unresolved"}. For a script error: the script's error text as the remedy. Never return ok true unless the script printed ok true.

## Output

**Write to:** {{scratch_dir}}/source-gate.json

Write exactly one JSON object {"ok": boolean, "remedy": [string], "checks": object} and return the same object, unchanged from the script's output. Copy remedy strings verbatim. Do not retry a failing script more than once.
```
