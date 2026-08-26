---
name: autonomous
description: "Toggle autonomous mode — suppresses handoff nudges near compaction."
allowed-tools: ["Bash"]
argument-hint: "[on|off]"
---

# Autonomous Mode Toggle

Writes or removes the autonomous-run sentinel file that the context pressure hook checks. When active, context pressure messages become informational-only (no `/handoff` recommendation).

## Usage

- `/autonomous` or `/autonomous on` — enable autonomous mode
- `/autonomous off` — disable autonomous mode

## Instructions

Run, relaying its own stdout confirmation verbatim (don't re-author it). Shape W
(`coordinator/snippets/resolve-coordinator-bin.md`):

`& "$env:COORDINATOR_SETTINGS_HOME\bin\autonomous-verb.cmd" $ARGUMENTS`

## Behavior While Active

A posture change, not just a nudge suppressor — full doctrine: wiki
(`autonomous-mode-first-officer-posture`). Presume the PM is away; drive to
completion over stalling, taking on debt as long as every shortcut lands in
`state/debt-backlog/` (or `improvement-queue/`/`bug-backlog/`) and is named
in the end-of-run summary. Legitimate stops, three categories only: (1)
non-pre-approved destructive/irreversible actions — queue, never halt the
run; (2) genuine product/scope tradeoffs the PM owns — a broken thing is
never one of these, break-class findings are fix-by-default; (3) structural
dead-ends (spec ambiguous at a load-bearing point, or the approach is
fundamentally wrong) — capture the blocker, finish independent work, stop
only that thread. `AskUserQuestion` is prohibited for break-class and
engineering-approach decisions here. Status between steps is output-only.

## Notes

- Sentinel is session-scoped, lives in `/tmp`; stale entries (>24h) and reboot both clear it.
- `/mise-en-place` and `/autonomous` compose independently — see wiki for the interop detail.
