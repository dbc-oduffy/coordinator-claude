# remember

Automatic temporal session memory for Claude Code. Captures what Claude worked on via hooks, summarizes via Haiku, and injects history at session start. Rolling compression keeps memory lean: raw capture → daily summary → weekly roll-up → archive.

## What It Does

The plugin runs invisibly in the background. After enough activity accumulates in a session, a background Haiku process summarizes it and writes to `memory/sessions/`. At the next session start, that history is injected into context automatically — no manual action required.

The `/remember` skill is the manual escape hatch: write a quick handoff note mid-session without waiting for auto-capture.

## How It Works

1. **PostToolUse hook** — monitors session JSONL growth. When estimated new lines exceed the threshold (default: 50 lines), spawns a background `pipeline.js save` process and exits in <100ms (cooldown + delta check keeps it cheap).
2. **Background save** — reads the session JSONL, extracts content, calls Haiku to summarize, writes to `memory/sessions/current.md`.
3. **SessionStart hook** — injects `memory/sessions/handoff.md` (one-shot, cleared after read), today's daily file, `current.md`, and `recent.md` into `additionalContext`. Also spawns background consolidation for any unprocessed past days.
4. **Consolidation** — compresses old daily files into `recent.md` (7-14 day rolling window), then archives them.

## Components

### Skills

| Skill | Purpose |
|-------|---------|
| `remember` | Write a lightweight session note to `tasks/session-note.md` — state, next steps, gotchas. Under 20 lines. |

### Hooks

| Hook | Trigger | Action |
|------|---------|--------|
| `SessionStart` | Session opens | Inject memory context, spawn recovery for unsaved prior sessions, trigger consolidation for unprocessed days |
| `PostToolUse` | After every tool call | Check session growth; if threshold exceeded and cooldown elapsed, spawn background save |

## Prerequisites

- Claude Code CLI
- Node.js (cross-platform — uses `process.execPath` for portable spawning)

## Usage

Memory accumulates automatically. No setup required after installation.

**Manual note:** Use `/remember` to save a quick handoff note mid-session. The next session will receive it as a one-shot inject (read once, then cleared).

**Memory files** (relative to project root):

| File | Contents |
|------|----------|
| `memory/sessions/current.md` | Rolling buffer of current session activity |
| `memory/sessions/handoff.md` | One-shot note from `/remember` — cleared after inject |
| `memory/sessions/daily/YYYY-MM-DD.md` | Per-day compressed summaries |
| `memory/sessions/recent.md` | 7-14 day rolling window |

## Integration

Enriches the coordinator plugin's `/update-docs` and `/workday-complete` when present — those commands surface the session history for context. All integrations gracefully degrade if the plugin is absent or memory files are empty.

## Authors

Dónal O'Duffy & Claude
