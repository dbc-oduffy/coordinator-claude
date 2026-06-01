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

## 4. Update baseline (`version.txt`) — re-run after each `git pull`

The coordinator plugin's boot currency-notification hook compares this install's
`version.txt` against deep-research-claude's latest published GitHub release to decide
whether to surface an "update available" nag at session start. For that comparison to
be meaningful, `version.txt` must hold a **deep-research-claude commit SHA** — the
commit this install was cloned/pulled to — not the publish-time placeholder that ships
in the repo (which records the upstream source-repo HEAD and is not a deep-research-claude
commit; comparing it against a release tag would mis-fire as "differs" forever).

**Re-run `/deep-research setup` after every `git pull`** so the baseline tracks the commit
you actually have — otherwise the hook nags "differs" against a stale baseline.

The bash block self-skips in `--check-only` mode (it writes a file):

```bash
if [[ "${ARGUMENTS:-}" == *--check-only* ]]; then
  echo "  SKIP: --check-only mode — version.txt baseline not modified."
else
  DR_ROOT="${CLAUDE_PLUGIN_ROOT}"
  if git -C "$DR_ROOT" rev-parse HEAD > "$DR_ROOT/version.txt" 2>/dev/null; then
    echo "  OK: version.txt update baseline = $(tr -d '[:space:]' < "$DR_ROOT/version.txt")"
  else
    # Not a git checkout (e.g. tarball install): remove the partial/placeholder file so
    # the currency hook treats this install as source_is_live (silent) rather than nagging
    # on a non-comparable baseline.
    rm -f "$DR_ROOT/version.txt" 2>/dev/null
    echo "  NOTE: $DR_ROOT is not a git checkout — version.txt baseline not planted (currency hook stays silent)."
  fi
fi
```

---

## 5. Status Report

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
| Update baseline (version.txt) | ... |

### Available commands

- `/deep-research web <topic>` — Internet research with iterative deepening
- `/deep-research repo <path>` — Repository assessment (add `--compare`, `--deeper`, `--deepest`)
- `/deep-research structured <spec>` — Schema-conforming batch research
- `/notebooklm-research <topic>` — Media research (YouTube, podcasts, audio)
```

If Agent Teams is not set, make this prominent — nothing will work without it.

End with: _"Run `/deep-research web 'test topic'` to verify the setup works."_
