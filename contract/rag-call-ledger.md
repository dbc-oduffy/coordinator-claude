# project-rag call ledger contract

The machine-local ledger records every project-rag tool call a session makes, so a guard or stop
check can tell whether a session or subagent has consulted project-rag. Counts are actual tool_use
payloads, never mentions of a tool name in text.

## Path

`<settings_home>/state/rag-call-ledger.jsonl`, where `settings_home` is
`$COORDINATOR_SETTINGS_HOME` when set and non-empty, else `~/.coordinator-claude-settings`.

## Row

One JSON object per line, UTF-8, `\n`-terminated, keys in this order.

| key | type | value |
|---|---|---|
| `v` | int | `1`, the row schema version |
| `ts` | str | UTC ISO-8601, seconds precision, `Z` suffix |
| `session_id` | str | payload `session_id` |
| `agent_id` | str or null | payload `agent_id`; null for the main thread |
| `tool` | str | payload `tool_name`, an `mcp__` name served by a project-rag server |
| `outcome` | str | `ok` (the call answered) or `down` (project-rag unreachable or erroring) |

No query text or result content is stored.

## Writer and reader

Writer: `_rag_call_ledger.record(payload, outcome)`. It is a no-op for a non-project-rag tool, an
unknown outcome or a missing `session_id`, and swallows every error.

Reader: `_rag_call_ledger.state_for(session_id, agent_id=None)` returns `ok`, `down` or `none` over
the rows with that `session_id` and `agent_id` (None selects the main thread). Any `ok` row wins; else
any `down` row gives `down`; else `none`. A missing or corrupt ledger reads as `none`.

## Write discipline

Append-only, one `os.write` of the full line to an `O_APPEND` descriptor. A reader skips any line that
fails to parse or parses to a non-object. The module spawns no child process.

## Retention

Before an append, a ledger over `MAX_LEDGER_BYTES` (1 MiB) is renamed over `<ledger>.old`, so the live file
stays bounded and the readers scan only it. A session whose rows rotated out reads `none`.
