---
name: autonomous
description: "Toggle autonomous mode — the PM-away premise for what counts as a legitimate stop."
allowed-tools: ["Bash"]
argument-hint: "[on|off]"
---

# Autonomous Mode Toggle

Declares the PM away: the session drives every stage to completion without waiting on the PM.
Writes or removes the autonomous-run sentinel, which the plugin reads to:

- nudge against any `AskUserQuestion` (`nudge-autonomous-askuserquestion.py`) — the answer is
  the recommendation, acted on;
- refuse `--typed-command` execution stamps (nobody typed it) and require
  `--authorized-by-delegation`, so an executed plan records who authorised it;
- let pickup autofire run batons handed to an autonomous run.

## Usage

- `/autonomous` or `/autonomous on` — enable autonomous mode
- `/autonomous off` — disable autonomous mode

## Instructions

Run, relaying its own stdout confirmation verbatim (don't re-author it). Shape W
(`coordinator/snippets/resolve-coordinator-bin.md`):

`& "$env:COORDINATOR_SETTINGS_HOME\bin\autonomous-verb.exe" <on|off>`

Render the literal `on` or `off` (`off` only when the args say off), never `$ARGUMENTS`:
the verb reads one token and has no note slot; keep any other PM text in your own notes.

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
