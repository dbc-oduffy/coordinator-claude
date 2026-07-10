---
name: validate
description: Use at cadence gates or to validate repo state. Resolves and runs the project's configured fast-test command.
description-budget: 175
version: 2.0.0
spec_backlink: archive/specs/2026-05/2026-05-28-workday-complete-fast-test-resolution.md §3.5
---

# Local CI Validation

Resolve and run the project's fast-tier validation command at cadence gates — merging, completing a workday/workstream, or an explicit 'does everything pass?' check.

<!-- spec: single owner of fast-test resolution; commands/workday-complete.md and commands/workweek-complete.md are thin delegations to this skill -->

## What It Does

Resolves the fast-test command via a three-step resolver (`cs_resolve_fast_test_cmd`), then executes the resolved command and captures its exit code into the `Validation:` enum.

### Resolution order (three steps — no conventional fallback)

1. **`COORDINATOR_FAST_TEST_CMD` env var** — if set and non-empty, use it verbatim. Escape hatch for one-off runs, CI overrides, and dogfood sessions.
2. **`coordinator.local.md` flat `fast_test_cmd:` key** — if `coordinator.local.md` exists at repo root and `fast_test_cmd:` is a non-empty string, use it.
3. **Skip-with-notice** — neither (1) nor (2) resolved. Emit a diagnostic to stderr naming both remediation paths (env var, local.md). Exit 2. Populate `Validation: skipped` and proceed to the next workday/workweek step.

There is no conventional fallback to `.github/scripts/run-all-checks.py`. The meta-repo (`~/.claude`) opts in explicitly by setting `fast_test_cmd: python .github/scripts/run-all-checks.py` in its own `coordinator.local.md`. Every repo must declare its fast-test or receive skip-with-notice.

<!-- negative-spec: no four-step resolution; the Staff Engineer F1 dropped the conventional fallback step; any future reader who adds it back is reintroducing scatter-by-implicit-convention -->

### Trust model

`COORDINATOR_FAST_TEST_CMD` is invoked verbatim with **no sanitization** — set it only from trusted contexts (local shell, CI-managed env, dogfood session). The `coordinator.local.md` `fast_test_cmd:` key is repo-local committed config and inherits whatever trust attaches to that file's review history (it ships through normal PR review). The resolver does NOT validate, escape, or filter either value — the assumption is that whoever set it is trusted to execute arbitrary commands in this repo. An agent or pipeline should NEVER set `COORDINATOR_FAST_TEST_CMD` from an untrusted source (a memo body, a webhook payload, a third-party file).

## How to Run

Source the resolver lib, call `cs_resolve_fast_test_cmd`, then execute the resolved command:

```bash
_cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
_cc_doe="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
_cc_doe="${_cc_doe%/}"   # trailing-slash normalization: prevents //* false-reject on stale/hand-edited .doe-root
_cc_trusted=0
case "$_cc_root" in
  "${CLAUDE_HOME:-$HOME}/.claude/"*) _cc_trusted=1 ;;
esac
[ -n "$_cc_doe" ] && case "$_cc_root" in "$_cc_doe"/*) _cc_trusted=1 ;; esac
case "$_cc_root" in *"/.."*) _cc_trusted=0 ;; esac   # load-bearing traversal check; dotdot-prefixed name (e.g. ..cache) is accepted false-reject edge
[ "${COORDINATOR_PLUGIN_ROOT_TRUSTED:-}" = 1 ] && _cc_trusted=1   # sanctioned --plugin-dir spike opt-out
[ "$_cc_trusted" = 1 ] || { echo "ERROR: coordinator root '$_cc_root' outside trusted prefix — refusing to source; re-run coordinator:install (or set COORDINATOR_PLUGIN_ROOT_TRUSTED=1 for a sanctioned --plugin-dir spike)" >&2; exit 1; }
[ -d "$_cc_root" ] || { echo "ERROR: coordinator root unresolved — ~/.claude/.doe-root missing/invalid; re-run coordinator:install" >&2; exit 1; }
_LIB="${_cc_root}/lib/coordinator-resolve-validation-cmd.sh"
_DIAG_TMP=$(mktemp)
trap 'rm -f "$_DIAG_TMP"' EXIT

if [[ -f "$_LIB" ]]; then
  source "$_LIB"
  FAST_CMD=$(cs_resolve_fast_test_cmd 2>"$_DIAG_TMP")
  RESOLVER_EXIT=$?
else
  echo "WARN: resolver lib not found at $_LIB" >&2
  RESOLVER_EXIT=2
  FAST_CMD=""
fi

if [[ $RESOLVER_EXIT -eq 2 ]]; then
  # skip-with-notice — emit the diagnostic captured to the per-process tmp file
  [[ -s "$_DIAG_TMP" ]] && cat "$_DIAG_TMP" >&2
  VALIDATION_RESULT="skipped"
elif [[ $RESOLVER_EXIT -ne 0 ]]; then
  # Any OTHER resolver non-zero (canonical: exit 127 — bare `python` token but no
  # python3/python on PATH) is a HARD environment failure, NOT a skip. FAST_CMD is
  # empty here, so running it would `bash -c ""` → exit 0 and silently pass. Surface
  # the resolver's diagnostic and mark blocked instead.
  [[ -s "$_DIAG_TMP" ]] && cat "$_DIAG_TMP" >&2
  VALIDATION_RESULT="interp-missing"
else
  "${BASH:-bash}" -c "$FAST_CMD"   # $BASH forwards the current interpreter (DR-148: never bare bash)
  CMD_EXIT=$?
  if [[ $CMD_EXIT -eq 0 ]]; then
    VALIDATION_RESULT="0"
  else
    VALIDATION_RESULT="$CMD_EXIT"
  fi
fi

echo "Validation: $VALIDATION_RESULT"
```

Run this using the Bash tool from the repo root. Read the full output — every script's pass/fail status and any error details.

## Exit Code → `Validation:` Mapping

| Condition | `Validation:` value |
|---|---|
| Resolver exit 2 (skip-with-notice) | `skipped` |
| Resolver exit 127 (bare `python` token, no python3/python on PATH) | `interp-missing` (blocking — NOT a skip) |
| Resolver exit 0, configured command exits 0 | `0` |
| Resolver exit 0, configured command exits non-zero | `<exit-code>` (the non-zero integer) |

The resolver does not pre-parse or probe the command string before execution. A configured command that fails to invoke (missing script, missing binary, syntax error) returns non-zero from the shell and surfaces as a normal `Validation: <exit-code>` — same as a test failure. Exit-code semantics are the contract; no heuristic on the command string.

## When to Use

- At cadence gates: /workstream-complete, /merge-to-main, /workday-complete, /workweek-complete
- NOT a per-commit reflex — commits are quick-saves; mid-work iteration uses the targeted subset. → `docs/wiki/test-design-discipline.md § Posture: Proportional Test-Running`.
- After modifying CI scripts, plugin manifests, settings, or memory files
- When the user asks "does everything pass?" or "validate"

## Interpreting Results

- **`Validation: 0`** — all checks passed. Safe to proceed with commit/merge.
- **`Validation: <non-zero>`** — configured command reported failure. Fix the failing check before proceeding. The command's own output includes the script name and error details.
- **`Validation: skipped`** — resolver found no configured command. Proceed to the next step; fast-tier validation was not run. To enable: set `fast_test_cmd:` in `coordinator.local.md`, or set `$COORDINATOR_FAST_TEST_CMD`. This is distinct from a PM-authorized skip (which is recorded as `N/A`).

## Integration

This skill complements `verification-before-completion`. That skill requires evidence before claims; this skill provides the evidence for repo-level validation claims.

`/workday-complete` Step 1 and `/workweek-complete` Step 2 both delegate to this skill. They do not inline their own resolution logic — this is the single owner.

## Common Mistakes

- **Forgetting to stage files before validating.** Unstaged changes won't be caught by some checks — ensure your working tree reflects intent before running.
- **Committing secrets or credentials.** Check for `.env` files, API keys, and private tokens before staging. CI may catch these, but prevention is better.
- **Skipping JSON and YAML validity checks.** Malformed frontmatter or settings JSON silently breaks plugin loading. Run the validator even for "small" config edits.
- **Leaving empty chunk or stub files.** Empty files in `docs/plans/` or `tasks/` directories can confuse downstream pipeline tools — delete or populate before committing.
- **Not reading the full output.** Skimming past FAIL lines or truncated error details means fixing the wrong thing. Read every script's result completely.
- **Assuming `skipped` means passing.** `Validation: skipped` means no command was configured, not that checks passed. Configure `fast_test_cmd:` to get an actionable signal.
