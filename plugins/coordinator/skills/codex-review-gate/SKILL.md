---
name: codex-review-gate
description: Run a Codex code review as a second-opinion gate. Returns structured result with findings or graceful skip. Used by /bug-sweep and /workday-complete.
user-invocable: false
---

# Codex Review Gate

Internal skill invoked by `/bug-sweep` and `/workday-complete` to get an independent-model code review via the Codex plugin. Codex (GPT-5.4) provides a different model family's perspective, catching issues that intra-family reviewers may share blind spots on.

## When This Skill Is Called

The calling command provides context:
- **scope**: `"bug-sweep-fixes"` or `"workday-diff"` — informational, for reporting
- **base**: git ref for diff base (default: `origin/main`)
- **required**: `true` or `false` — if false, failure is non-blocking (the normal case)

## Execution

### Step 1: Check diff exists

```bash
git diff --shortstat {base}...HEAD
```

If empty (no changes against base), report and return:
> _"Codex review gate: no diff against {base} — skipped."_

### Step 2: Run the Codex review

Invoke `/codex:review --wait --scope branch --base {base}` via the Skill tool.

This runs the review in the foreground and returns the full output. The Codex plugin handles all path resolution, authentication checks, and CLI invocation internally.

### Step 3: Assess result

Use **exit code only** for success/failure discrimination:
- **Exit code 0** = success. The output contains the review findings.
- **Non-zero exit code** = failure. The output or stderr contains the reason.

Do not use string matching on output headers — that's fragile against plugin format changes.

### Step 4: Report

**On success:**
- Summarize the Codex review: verdict, finding count, and severity breakdown
- Present the full Codex output for the calling command to include in its report
- If findings exist, categorize by severity (P0/P1 = flag to PM, P2 = note for next session)

**On failure (graceful fallback):**
- Extract the reason from output/stderr. Common reasons:
  - `"not installed"` — Codex CLI not installed. Suggest: `/codex:setup`
  - `"not authenticated"` — Codex CLI not logged in. Suggest: `!codex login`
  - Connection/broker errors — Codex infrastructure issue
  - Any other error — report first meaningful line
- Report: _"Codex review gate skipped: {reason}."_
- If `required: false` (the default): continue without blocking. The calling command's existing reviewer output stands alone.
- If `required: true`: halt and report to PM for decision.

## Design Notes

- Codex is **additive, never blocking** in the default configuration. Users on limited ChatGPT plans benefit most from bounded token spend (one review per end-of-day, not continuous).
- The existing persona reviewers (Patrik, Sid, Camelia, Pali) from `/code-health` provide the primary review. Codex is a second opinion from a different model family — complementary, not a replacement.
- Blind spots may be correlated within a model family — if Claude misses a pattern, its reviewer personas (which share the same model family) are more likely to miss it too. Codex mitigates this by providing an independent sample.
