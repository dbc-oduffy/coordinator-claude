# PreToolUse Deny Contract — Scope Guard Reference

Part of the **scoped-safety-commits** infrastructure. Read this before flipping
`COORDINATOR_SCOPE_STRICT=1`.

See also: `coordinator/bin/scope-flip-readiness`, `coordinator/bin/scope-warning-resolve`,
`coordinator/hooks/scripts/validate-commit.sh` (Check 5).

---

## The Claude Code PreToolUse Hook Deny Contract

A PreToolUse hook receives the pending tool call via stdin (JSON). Two
mechanisms control whether the call proceeds: exit codes (legacy) and
JSON output on stdout (modern, preferred).

### Exit codes

| Exit code | Behavior |
|-----------|----------|
| `0` | Success. stdout parsed for JSON output (see below). Tool proceeds unless JSON denies. |
| `2` | **Blocking error.** Tool call is blocked. stderr fed back to Claude verbatim as the error message. stdout/JSON ignored on non-zero exit. |
| Any other (incl. `1`) | **Non-blocking error.** Tool proceeds anyway. Transcript shows hook-error notice with first line of stderr only. |

The `exit 1` vs `exit 2` distinction is the key footgun: `exit 1` does NOT
block. Use `exit 2` if relying on the exit-code interface.

### JSON output (preferred)

PreToolUse supports structured JSON via `hookSpecificOutput`:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "allow|deny|ask|defer",
    "permissionDecisionReason": "string",
    "updatedInput": { },
    "additionalContext": "string"
  }
}
```

- `permissionDecision: "deny"` blocks the tool call.
- `permissionDecisionReason` is surfaced **verbatim to the EM Claude session**
  when the decision is `"deny"` (and only to the user for `"allow"`/`"ask"`).
- Top-level `decision`/`reason` with values `"approve"`/`"block"` are
  **deprecated** but still map to `"allow"`/`"deny"`.
- JSON is only parsed on `exit 0`.

### Blast radius

A deny blocks **only the single tool call**, not the turn or agent loop.
Claude receives the deny reason as feedback and continues responding within
the same turn — typically by trying an alternative or surfacing the block to
the user.

---

## Verified Deny Behavior

Verified 2026-04-27 against the canonical Claude Code hooks documentation at
https://code.claude.com/docs/en/hooks (also referenced:
https://code.claude.com/docs/en/permissions for deny/ask precedence).

- Deny exit code: `2` (use `exit 2` if going through the exit-code path).
- EM sees stderr: **yes, verbatim** on `exit 2`. On any other non-zero exit,
  only the first line of stderr appears in the transcript (advisory only,
  tool still proceeds).
- JSON output format: **yes**, see schema above. Preferred over `exit 2`
  because `permissionDecisionReason` is purpose-built to surface to Claude
  and avoids the `exit 1` vs `exit 2` footgun.
- Blocks: **single tool call only.** Claude continues the turn.
- Verified by: web research against authoritative Anthropic docs (no in-session
  empirical hook test required — the docs are explicit and unambiguous).
- Verified date: 2026-04-27.

### Implementation choice

`validate-commit.sh` Check 5 uses the JSON form (`permissionDecision: "deny"`
with `permissionDecisionReason` carrying the full block message). This is
the modern interface and survives any future change to exit-code conventions.

---

## Where the Strict-Mode Block Lives

File: `coordinator/hooks/scripts/validate-commit.sh`, in the strict-mode
section near the end of the script.

The block builds a deny reason and emits it as JSON on stdout, then
`exit 0` (so the JSON is parsed). On override, it logs and exits 0 without
emitting JSON, allowing the commit through.

---

## Override Syntax (Verbatim)

When the scope guard blocks a commit and you need to override:

```
Set COORDINATOR_OVERRIDE_SCOPE=1 to bypass scope guard for this commit.
```

Inline usage:

```bash
COORDINATOR_OVERRIDE_SCOPE=1 git commit -m "subject"
```

Or for the safe-commit helper:

```bash
COORDINATOR_OVERRIDE_SCOPE=1 coordinator-safe-commit "subject"
```

Override is logged automatically to `.git/coordinator-sessions/<session_id>/overrides.log`.

**Do not use `--blanket` as a substitute for the override.** `--blanket` is
only valid from `/session-start` and `/workday-complete`. Using it outside those
ceremonies will be rejected by the commit helper. `COORDINATOR_OVERRIDE_SCOPE=1`
is the documented emergency escape hatch.

---

## Related Files

| File | Role |
|------|------|
| `coordinator/hooks/scripts/validate-commit.sh` | PreToolUse hook — contains the scope guard (Check 5) |
| `coordinator/bin/scope-flip-readiness` | Evaluates the flip predicate; run before enabling strict mode |
| `coordinator/bin/scope-warning-resolve` | Marks scope-warning log entries with their resolution |
| `coordinator/bin/scope-soak-enable` | Writes the `.warn-mode-enabled-at` sentinel to start the soak clock |
| `.git/coordinator-sessions/<id>/scope-warnings.log` | Per-session warn log written by validate-commit.sh |
| `.git/coordinator-sessions/.warn-mode-enabled-at` | Soak-start sentinel; written by scope-soak-enable |

---

*Created: 2026-04-27. Verified same day against canonical docs.*
