# Attribution

This plugin is a ground-up rebuild inspired by the `remember` plugin from
[claude-plugins-official](https://github.com/anthropics/claude-plugins-official)
(v0.1.0, Community License).

## What we kept (concept)

- The core idea: automatic session memory via background Haiku summarization
- The compression pipeline: JSONL extraction → Haiku summary → layered storage
- The prompt templates (save-session, compress-ndc, consolidate) — proven effective
- The incremental extraction pattern (track JSONL position between saves)
- The /remember skill for manual handoff notes

## What we changed and why

| Change | Why |
|--------|-----|
| **Pure Node.js** (was bash+Python) | Cross-platform. The original had 6 bash scripts + 7 Python modules — a dependency chain that broke on Windows (cygpath, `/tmp`, `stat` differences, `nohup` behavior, `timeout` from coreutils) |
| **Unified storage** in `memory/sessions/` (was `.remember/` at project root) | Integrates with Claude Code's built-in memory system. Eliminates project root pollution and parallel storage conflict |
| **3 compression layers** (was 4) | Dropped `archive.md`. Long-term knowledge belongs in proper memory entries, not an ever-growing archive |
| **Windows-safe atomic writes** (was `noclobber` bash locks) | `fs.renameSync` can't overwrite on Windows. New helper: unlink-then-rename |
| **File-size heuristic** in PostToolUse hook (was `wc -l` line count) | One `statSync` call vs reading entire JSONL. Critical for hot-path performance |
| **Staleness-aware PID guard** (was raw `kill -0`) | Windows recycles PIDs aggressively. Added timestamp-based staleness detection |
| **Coordinator integration** | Hooks into `/session-start`, `/session-end`, `/workday-complete`, `/update-docs` |
| **`process.execPath`** for child spawning (was `node`) | Uses the exact Node binary running the hook — avoids PATH resolution issues |
| **Static ESM imports throughout** | Original had no ESM concerns (bash/Python). Node.js ESM requires all imports at top of module |

## License

The original plugin is under Anthropic's Community License (source-available, use permitted).
This rebuild is original code inspired by the same concepts.
