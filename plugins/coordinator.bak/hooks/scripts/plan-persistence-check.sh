#!/bin/bash
# PostToolUse hook: fires after ExitPlanMode.
# Ensures plan content was written substantively, not as a stub.

cat << 'HOOK_OUTPUT'
{
  "hookSpecificOutput": {
    "hookEventName": "PostToolUse",
    "additionalContext": "PLAN PERSISTENCE — MANDATORY CHECK:\n\nYou just exited plan mode. Before doing ANYTHING else:\n\n1. VERIFY the plan file in ~/.claude/plans/ contains the FULL plan content — not a stub, not a pointer to another location, not 'saved to X'. If the plan file is a stub, you MUST rewrite it now with the full content using the Write tool.\n\n2. CANONICALIZE: Copy the plan to docs/plans/ in the project repo — this is the canonical location for approved plans. Use the naming convention docs/plans/YYYY-MM-DD-<feature-name>.md. Create docs/plans/ if it doesn't exist. Then commit: 'git add docs/plans/<filename> && git commit -m \"plan: <feature-name>\"'. The ~/.claude/plans/ copy is the working draft; docs/plans/ is the record of truth.\n\n3. If subagent reviews (Patrik, Sid, etc.) were part of this planning session, their outputs must be written to disk NOW. Agent outputs exist only in your context — if you don't write them, they're lost on compaction. Review artifacts are intermediate — write them straight to archive (not active folders). The plan document itself must incorporate ALL review findings unless the EM believes they are in error or require PM input. The goal is a polished plan document, not review clutter.\n\n4. UPDATE docs/README.md: If docs/README.md exists, add the new plan to the Plans section.\n\nThis is a hard rule. Plans that exist only in conversation context are plans that don't exist."
  }
}
HOOK_OUTPUT
