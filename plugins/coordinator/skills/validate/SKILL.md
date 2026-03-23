---
name: validate
description: Run all CI validation checks locally before committing or creating PRs. Use when about to commit, before /merge-to-main, before /workday-complete, or when the user asks to validate the repo state.
---

# Local CI Validation

Run all CI checks locally to catch issues before they hit the remote pipeline.

## What It Does

Executes `.github/scripts/run-all-checks.py`, which uses convention-based discovery to find and run all `validate-*.py` and `check-*.py` scripts in `.github/scripts/`.

## How to Run

```bash
python .github/scripts/run-all-checks.py
```

Run this command using the Bash tool. Read the full output — every script's pass/fail status and any error details.

## When to Use

- Before committing significant changes
- Before `/merge-to-main` or `/workday-complete`
- After modifying CI scripts, plugin manifests, settings, or memory files
- When the user asks "does everything pass?" or "validate"

## Interpreting Results

- **All PASS**: Safe to proceed with commit/merge
- **Any FAIL**: Fix the failing check before proceeding. The output includes the script name and error details.
- **Script not found**: The repo may not have CI scripts set up. This is not an error in other repos — only applies where `.github/scripts/` exists.

## Integration

This skill complements `verification-before-completion`. That skill requires evidence before claims; this skill provides the evidence for repo-level validation claims.
