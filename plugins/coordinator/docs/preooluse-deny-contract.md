# PreToolUse Deny Contract — Scope Guard Reference

Part of the **scoped-safety-commits** infrastructure. Read this before flipping
`COORDINATOR_SCOPE_STRICT=1`.

See also: `coordinator/bin/scope-flip-readiness`, `coordinator/bin/scope-warning-resolve`,
`coordinator/hooks/scripts/validate-commit.sh` (Check 5).

---

## The Claude Code PreToolUse Hook Deny Contract

A PreToolUse hook receives the pending tool call via stdin (JSON), and its exit
code determines whether Claude Code allows or blocks the call.

**What we know from reading existing hooks in this repo and the Claude Code
hook-authoring notes:**

| Exit code | Effect |
|-----------|--------|
| `0` | Allow the tool call to proceed. Any stdout/stderr is advisory only. |
| non-zero  | Deny/block the tool call. stderr content is surfaced to the EM as an error message. |

**Current behavior in `validate-commit.sh`:** The hook is hard-coded `exit 0`
always (see line 207). Check 5 (scope guard) accumulates warnings but never
blocks — this is the warn-only Phase 2 behavior.

**TODO: verify the exact non-zero exit code that Claude Code treats as a deny.**

The current code uses `exit 2` as the candidate strict-mode deny code (see
`validate-commit.sh` line 204). The comment on that line reads:

> NOTE: exit 2 may need to be exit 1 or stderr-message-based — verify Claude
> Code PreToolUse deny contract before setting COORDINATOR_SCOPE_STRICT=1 in
> Phase 5.

**What is NOT yet verified empirically:**

- Whether Claude Code requires `exit 1` specifically (some hook systems
  distinguish 1 vs 2 — 2 may mean "warning" rather than "deny").
- Whether stderr content is shown verbatim to the EM or is truncated.
- Whether there is a JSON output format for structured deny messages, or whether
  plain text stderr is the interface.
- Whether the deny blocks only the single Bash tool call or the entire turn.

**Recommendation before flipping strict mode:** Run the manual verification
procedure below against the current Claude Code version installed on this
machine.

---

## Manual Verification Procedure

Before setting `COORDINATOR_SCOPE_STRICT=1`, perform this test to confirm the
deny contract:

### Step 1 — Create a minimal test hook

```bash
# Save as /tmp/test-deny-hook.sh and make executable
cat > /tmp/test-deny-hook.sh <<'HOOK'
#!/bin/bash
INPUT=$(timeout 2 cat 2>/dev/null || cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
if echo "$COMMAND" | grep -q "DENY_TEST"; then
  echo "PreToolUse deny test: blocking DENY_TEST command" >&2
  exit 1
fi
exit 0
HOOK
chmod +x /tmp/test-deny-hook.sh
```

### Step 2 — Register as a PreToolUse hook temporarily

In your Claude Code session's hook config (`.claude/settings.json` or the
global hook config), add the test hook for the Bash tool:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [{ "type": "command", "command": "/tmp/test-deny-hook.sh" }]
      }
    ]
  }
}
```

### Step 3 — Trigger the deny

In the Claude Code session, ask the EM to run a command containing `DENY_TEST`:

> Run: `echo DENY_TEST`

### Step 4 — Observe

Record:
- Does Claude Code prevent the Bash call from executing?
- What does the EM see? (The stderr message from the hook? A generic error? Nothing?)
- Does `exit 1` or `exit 2` produce different behavior?

### Step 5 — Update this document

Fill in the "Verified deny behavior" section below with what you observe, then
remove the `TODO` markers.

---

## Verified Deny Behavior

**TODO: fill in after empirical test.**

- Deny exit code: `TODO`
- EM sees stderr: `TODO (yes/no/truncated)`
- JSON output format: `TODO (yes/no — if yes, document schema)`
- Blocks: `TODO (single call / entire turn / other)`
- Tested on Claude Code version: `TODO`
- Test date: `TODO`

---

## Where the Strict-Mode Block Lives

File: `coordinator/hooks/scripts/validate-commit.sh`, lines 192–205 (as of
Phase 2 landing).

```bash
# Strict-mode block (Phase 5 — gated on COORDINATOR_SCOPE_STRICT=1)
if [[ "${COORDINATOR_SCOPE_STRICT:-0}" == "1" && -n "$SCOPE_FOREIGN_FILES" ]]; then
  echo "BLOCKED: commit contains files outside this session's scope:" >&2
  echo "$SCOPE_FOREIGN_FILES" >&2
  echo "" >&2
  echo "Override: set COORDINATOR_OVERRIDE_SCOPE=1 to commit anyway (logged to overrides.log)." >&2
  ...
  exit 2  # PreToolUse deny code — VERIFY before enabling
fi
```

Once the deny contract is verified, update `exit 2` to the correct exit code
and remove the `TODO` comment.

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

*Created: 2026-04-27. Update the "Verified Deny Behavior" section after
empirical testing against the installed Claude Code version.*
