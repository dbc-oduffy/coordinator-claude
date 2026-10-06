---
name: autonomous
description: "Toggle autonomous mode — the PM-away premise for what counts as a legitimate stop."
allowed-tools: ["Bash"]
argument-hint: "[on|off]"
---

# Autonomous Mode Toggle

Writes or removes the autonomous-run sentinel file. Context-pressure messages never recommend `/handoff`, with or without it: they say commit, checkpoint, and ride compaction.

## Usage

- `/autonomous` or `/autonomous on` — enable autonomous mode
- `/autonomous off` — disable autonomous mode

## Instructions

Run, relaying its own stdout confirmation verbatim (don't re-author it). Shape W
(`coordinator/snippets/resolve-coordinator-bin.md`):

`& "$env:COORDINATOR_SETTINGS_HOME\bin\autonomous-verb.exe" $ARGUMENTS`

## Behavior While Active

PM touchpoints themselves are set by the sizing's `interaction_mode` (hands-on / pm / ceo), not
by this toggle.

Presume the PM is away — don't wait for input. Status between steps is
output-only; no mid-run "should we continue?". Everything else once printed
here (drive-to-completion, tracked debt over stalling, fix-by-default at
scale, the AskUserQuestion bar) is engagement-posture conduct, not a toggle
effect — it applies whether or not this sentinel is set. See
`coordinator/snippets/em-operating-doctrine.md` § How to Decide (the EM
payload) and the wiki (`autonomous-mode-first-officer-posture`) for the
full doctrine.

## Notes

- Sentinel is session-scoped, lives in `/tmp`; stale entries (>24h) and reboot both clear it.
- `/mise-en-place` and `/autonomous` compose independently — see wiki for the interop detail.
