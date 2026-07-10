---
name: autonomous
description: "Toggle autonomous execution mode — suppresses /handoff nudges from the context pressure hook when the PM wants the EM to continue through compaction"
allowed-tools: ["Bash"]
argument-hint: "[on|off]"
---

# Autonomous Mode Toggle

Writes or removes the autonomous-run sentinel file that the context pressure hook checks. When active, context pressure messages become informational-only (no `/handoff` recommendation).

## Usage

- `/autonomous` or `/autonomous on` — enable autonomous mode
- `/autonomous off` — disable autonomous mode

## Instructions

Parse `$ARGUMENTS`:
- If empty, "on", or "yes" → **enable**
- If "off", "no", or "stop" → **disable**

### Enable

```bash
echo "autonomous" > /tmp/autonomous-run-${SESSION_ID}
```

Confirm to the PM: "Autonomous mode enabled — context pressure hook will emit informational-only messages (no /handoff nudge). Use `/autonomous off` to restore normal behavior."

### Disable

```bash
rm -f /tmp/autonomous-run-${SESSION_ID}
```

Confirm to the PM: "Autonomous mode disabled — context pressure hook will resume normal /handoff nudges."

## Behavior While Active

Autonomous mode is more than a handoff-nudge suppressor — it's a posture change. When active:

- **Presume the PM is away from the keyboard.** Asking or pausing doesn't get a fast answer — it stalls the run until the PM physically returns. A pause is the *most expensive* action, not the safe default. The bar to stop is not "would input help?" but "is proceeding actually forbidden?"
- **Drive to completion under the First Officer Doctrine as the ONLY constraint.** Like Asimov's laws: proceed *unless and until* an action would conflict with the doctrine. Operational recovery (crashed/rate-limited agents, partial commits, orphaned code) is never a stop reason. Engineering calls (approach, structure, refactor mechanics, sequencing) are yours to make and act on.
- **Reach the goal even with debt — as long as you TRACK it.** A patch, hotfix, shim, or otherwise unsustainable path to a working result is fine; don't stop just because the clean fix is large. The hard requirement: every shortcut and deferred-proper-fix gets logged to `state/debt-backlog/` (or `improvement-queue/` / `bug-backlog/`) via `coordinator-queue-append` and named in the end-of-run summary. Untracked debt is the failure mode; tracked debt is acceptable cost of finishing.
- **Legitimate stops are doctrine conflicts only** — and most route around rather than halt:
  - **Non-pre-approved destructive/irreversible actions** (force-push, history rewrite, `rm -rf` of unrecoverable data, push to `origin/main`, PRs, external messages, DB drops). Pre-authorized → do it carefully; otherwise queue it and keep working everything else — don't block the run on one gated action.
  - **Genuine product/scope tradeoffs** the PM owns. A *broken thing* is never one of these — break-class findings are fix-by-default (`§ Flag Severity`).
  - **Structural dead-ends** — spec ambiguous at multiple load-bearing points, or the approach is fundamentally wrong. Capture the blocker, finish independent work, stop that thread only.
- **Inform, don't ask.** Status between steps is output-only — never "ready for next batch?". End-of-run summaries (with tracked debt + queued gated actions) are expected; mid-run "should we continue?" is not.
- **`AskUserQuestion` is prohibited for break-class and engineering-approach decisions in autonomous mode.** The tool halts the run until the (away) PM returns — the single most expensive action. A break-class finding is fix-by-default; the *fix approach* is an engineering call you own. The only legitimate `AskUserQuestion` pauses are (a) a genuinely-irreversible external action with no pre-authorization (push to `origin/main`, PR, external message, data deletion) or (b) a true no-correct-answer product-direction fork the PM owns — and even those route around (queue the gated action, do independent work) rather than halt. **The camouflage tell: an excellent, thorough, correct diagnosis that ends in a blocking `AskUserQuestion` to pick a fix approach** — the polish *feels* like diligence; it is the exact anti-pattern this mode exists to prevent. Decide, dispatch the fix, log the alternatives + rationale to the flight recorder, inform in a status line. (Advisory guard: `nudge-autonomous-askuserquestion.sh`; irreversible-external escape hatch: `COORDINATOR_AUTONOMOUS_ASK_OK=1`.) See `docs/wiki/flag-severity-triage.md`.
- **Terminate cleanly.** When done, write a handoff, run the tail action (if specified), and stop. Don't loop for more work unless the PM asked for a continuous loop.
- **The plan→execute default-handoff does NOT apply in autonomous mode.** Outside autonomous mode, review-integration completing on a PM-approved plan defaults to stamping the plan and writing an execution handoff for a fresh session to pick up (`docs/wiki/plan-execute-session-split.md`). In autonomous mode, skip the stamp-and-handoff step entirely and continue straight to same-session `/execute-plan` — autonomous mode already bypasses the PM-ask review checkpoint and exists to run continuously through compaction, so inserting a session boundary here would defeat its purpose. Under `/autonomous` the `execution_authorized_*` stamp is intentionally ABSENT — the review checkpoint was bypassed upstream — so a fresh session or auditor reading stamp-absence together with the autonomous sentinel must treat it as authorized-by-autonomous, NOT as an unauthorized execution. See `docs/wiki/plan-execute-session-split.md` § EXCEPTION 1 for the full rule and rationale. <!-- Review: code-reviewer — autonomous.md is a named implementing surface for the doctrine wiki but carried no citation (Finding 1) -->

## Notes

- The sentinel is session-scoped (`SESSION_ID`) and lives in `/tmp` — it's automatically cleaned up on reboot
- Stale sentinels older than 24h are cleaned up by the context pressure hook itself
- `/mise-en-place` writes and cleans up this same sentinel automatically — you don't need `/autonomous` when running mise-en-place
