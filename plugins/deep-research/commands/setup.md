---
description: Set up the deep-research plugin — verify Agent Teams, check pipeline availability, configure NotebookLM. Safe to re-run.
allowed-tools: ["Read", "Bash", "Glob", "AskUserQuestion"]
argument-hint: "[--check-only]"
---

# Deep Research Setup

Verify prerequisites for the deep-research plugin's multi-agent pipelines. All pipelines require Agent Teams; Pipeline D also requires a NotebookLM MCP server.

If `$ARGUMENTS` contains `--check-only`, report status without making changes.

---

## 1. Agent Teams (required)

```bash
echo "${CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS:-not_set}"
```

- If `1`: ready.
- If not set: **All pipelines will fail without this.** Instruct the user to add to `~/.claude/settings.json`:
  ```json
  "env": { "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1" }
  ```
  Takes effect on next Claude Code restart.

---

## 2. Pipeline Availability

Check which pipelines are available by looking for their command files relative to this plugin:

```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT}"
for cmd in web repo structured; do
  test -f "$PLUGIN_DIR/commands/$cmd.md" && echo "$cmd: available" || echo "$cmd: missing"
done
```

Also check for the NotebookLM sub-plugin:

```bash
test -d "$PLUGIN_DIR/notebooklm" && echo "notebooklm: available" || echo "notebooklm: not installed"
```

Report:
- **Pipeline A** (Internet Research) — `/deep-research web`
- **Pipeline B** (Repo Research) — `/deep-research repo`
- **Pipeline C** (Structured Research) — `/deep-research structured`
- **Pipeline D** (NotebookLM Media Research) — `/notebooklm-research` (requires notebooklm sub-plugin)

---

## 3. NotebookLM Setup (Pipeline D only)

**Skip this section if the notebooklm sub-plugin is not installed.**

### 3a. MCP server CLI

Check if `notebooklm-mcp` is available:

```bash
command -v notebooklm-mcp 2>/dev/null || npx --yes notebooklm-mcp --version 2>/dev/null || echo "not_found"
```

- If found: ready.
- If not found: Pipeline D requires the `notebooklm-mcp-cli` package. Install with:
  ```bash
  npm install -g notebooklm-mcp-cli
  ```
  Or see https://github.com/jacob-bd/notebooklm-mcp-cli

### 3b. Authentication

Note that NotebookLM requires Google account authentication. The user must run `nlm login` in their terminal (outside Claude Code) to authenticate. This handles OAuth flow and session cookie extraction.

If auth expires mid-session, the `refresh_auth` MCP tool or re-running `nlm login` will fix it.

### 3c. Enable/disable guidance

Note that the NotebookLM sub-plugin is kept disabled by default to reduce context load. The user should enable it in `~/.claude/settings.json` before running Pipeline D research, and disable it after.

---

## 4. Status Report

```
## Deep Research Setup

| Check                       | Status |
|-----------------------------|--------|
| Agent Teams env var         | ... (REQUIRED) |
| Pipeline A (web)            | ... |
| Pipeline B (repo)           | ... |
| Pipeline C (structured)     | ... |
| Pipeline D (notebooklm)    | ... |
| NotebookLM MCP CLI         | ... (if Pipeline D) |
| NotebookLM auth             | run `nlm login` in terminal |

### Available commands

- `/deep-research web <topic>` — Internet research with iterative deepening
- `/deep-research repo <path>` — Repository assessment (add `--compare`, `--deeper`, `--deepest`)
- `/deep-research structured <spec>` — Schema-conforming batch research
- `/notebooklm-research <topic>` — Media research (YouTube, podcasts, audio)
```

If Agent Teams is not set, make this prominent — nothing will work without it.

End with: _"Run `/deep-research web 'test topic'` to verify the setup works."_
