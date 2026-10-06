# WebSearch ledger contract

`websearch-ledger.json` pins the machine-local ledger that records every WebSearch tool call a
session makes: where it lives, what a row holds, and who writes and reads it. The plugin owns the
contract; the engine-side reader consumes it from here and never re-derives it.

## Path

One file per machine and user, shared by every repo and session on the box. That sharing is what
makes it fleet-visible.

`<settings_home>/state/websearch-ledger.jsonl`, where `settings_home` is
`$COORDINATOR_SETTINGS_HOME` when set and non-empty, else `~/.coordinator-claude-settings`.

## Row

One JSON object per line, UTF-8, `\n`-terminated, keys in this order.

| key | type | value |
|---|---|---|
| `v` | int | `1`, the row schema version |
| `ts` | str | UTC ISO-8601, seconds precision, `Z` suffix |
| `session_id` | str | payload `session_id` |
| `agent_id` | str or null | payload `agent_id`; null for a main-session call |
| `outcome` | str | `ok` (PostToolUse) or `failure` (PostToolUseFailure) |
| `cwd` | str or null | payload `cwd` |

A subagent's row carries its parent session's `session_id` and its own `agent_id`, so a
per-session count includes subagent calls and `agent_id` separates them.

Failure rows exist because a WebSearch call that errors fires PostToolUseFailure, not
PostToolUse. The consumer decides whether failures count against a budget.

Query text, URLs and result content are deliberately absent: the ledger stays small and puts no
research content on a fleet-readable surface.

## Writers and reader

Writers: the two existing hooks that already fire on every tool call, through
`_websearch_ledger.record`. PostToolUse writes `ok`; PostToolUseFailure writes `failure`. No
registration is added for this.

Plugin-side reader: `_websearch_ledger.py::count_by_session`, counting rows per `session_id`, `ok` and
`failure` alike. It is the reference semantics for any other reader.

## Write discipline

Append-only, one `os.write` of the full line to an `O_APPEND` descriptor. Concurrent writers can
still leave a torn or partial line, so a reader skips any line that fails to parse or parses to a
non-object. A writer swallows every error: a ledger failure never affects the host hook.

## Ownership beyond the writer

Retention, rotation, the fleet-visible query surface and any budget ceiling belong to the engine
reader. The writer only appends.
