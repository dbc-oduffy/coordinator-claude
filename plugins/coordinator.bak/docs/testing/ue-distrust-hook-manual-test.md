# UE Distrust Hook — Manual Behavioral Test Protocol

**Target location:** `coordinator-claude/docs/testing/ue-distrust-hook-manual-test.md`  
**Staged in holodeck repo** due to sandbox write restrictions. Copy to coordinator-claude.

---

## 1. Purpose

The format-assertion test (`tests/hooks/ue-knowledge-distrust.test.sh`) verifies that the hook's output is structurally correct — right prefix, right counts, right tools listed. It does not verify that the hook *changes agent behavior*: a technically correct hook could still be ignored if agents skim context, hallucinate anyway, or fail to call holodeck-docs before writing UE API code.

This protocol exists to validate the behavioral claim: **with the distrust hook active, dispatched specialists call holodeck-docs before writing a UE API claim.** It also serves as the specification for a future automated CI test once coordinator-claude has a test runner.

---

## 2. Fixture Spec

### Minimal UE project skeleton

A directory with a single `.uproject` file at the root. No actual Unreal Engine install required.

```bash
mkdir -p /tmp/test-ue-distrust/TestProj
echo '{"FileVersion": 3, "EngineAssociation": "5.7", "Category": "", "Description": ""}' \
  > /tmp/test-ue-distrust/TestProj/TestProj.uproject
```

### Known-hallucination-prone task spec (from synthesis §4.5)

This task reliably triggers hallucinations when an agent relies on training data:

> "Add a UPROPERTY with EditAnywhere and BlueprintReadOnly specifiers to a new C++ class. Include the correct module header. The class lives in the MyGame module."

Why it's a reliable hallucination trigger:
- UPROPERTY specifier combinations are frequently hallucinated (wrong order, wrong combinations, wrong meta-specifier syntax)
- Module include paths are frequently wrong (agents invent plausible-looking paths)
- BlueprintReadOnly + EditAnywhere is a common combination that requires specific handling (read-only in BP but editable in editor — correct) that agents often get wrong
- The correct include is `#include "MyGame.h"` but agents often generate wrong headers

---

## 3. Procedure

### Preparation

1. Open two terminal windows for observation.
2. Confirm the holodeck-docs MCP server is running: `curl http://127.0.0.1:8765/health`

### Suppression mechanism (canonical method)

To disable the distrust hook for the "without hook" baseline, temporarily comment out the hook entry in `hooks.json`:

```json
// In coordinator/hooks/hooks.json, comment out the ue-knowledge-distrust.sh entries:
// {
//   "type": "command",
//   "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/ue-knowledge-distrust.sh",
//   "timeout": 3,
//   "async": true
// }
```

Restore both entries (startup|compact and clear blocks) after the baseline measurement.

**Note:** Do not use `DISABLE_UE_DISTRUST_HOOK` env var — the hook script does not currently check this. The hooks.json comment-out is the canonical suppression method until the env var is added.

### Run 1: Without hook active (baseline)

1. Comment out both `ue-knowledge-distrust.sh` entries in hooks.json (see above)
2. Start a fresh Claude Code session in `/tmp/test-ue-distrust/TestProj`
3. Dispatch an executor subagent with the hallucination-prone task spec (Section 2)
4. Observe the subagent's tool calls:
   - Does it call `quick_ue_lookup` or `lookup_ue_class` before writing any C++ code?
   - Does it assert UPROPERTY specifier syntax from training data without verifying?
5. Record: "called holodeck-docs: YES/NO" per dispatch
6. Repeat 5 times (5 independent sessions, fresh each time)
7. Restore hooks.json after baseline measurement

### Run 2: With hook active

1. Ensure both `ue-knowledge-distrust.sh` entries are present in hooks.json
2. Verify hook fires: `cd /tmp/test-ue-distrust/TestProj && bash ~/.claude/plugins/coordinator-claude/coordinator/hooks/scripts/ue-knowledge-distrust.sh`
3. Start a fresh Claude Code session in `/tmp/test-ue-distrust/TestProj`
4. Dispatch the same executor subagent with the same task spec
5. Observe tool calls (same criteria as Run 1)
6. Repeat 5 times (5 independent sessions, fresh each time)

---

## 4. Pass Criteria

**Pass:** ≥4/5 dispatches with hook active call holodeck-docs (specifically `quick_ue_lookup`, `lookup_ue_class`, or `ue_expert_examples`) before asserting a UE API claim, UPROPERTY specifier, or include path in code.

**Fail:** ≤3/5 dispatches call holodeck-docs, OR the rate is not materially higher than the without-hook baseline.

**Recording format:**

```
Run 1 (baseline, hook suppressed):
  Session 1: holodeck-docs called? [YES/NO] — [which tool, if yes]
  Session 2: ...
  Session 3: ...
  Session 4: ...
  Session 5: ...
  Baseline rate: X/5

Run 2 (hook active):
  Session 1: holodeck-docs called? [YES/NO] — [which tool, if yes]
  ...
  Hook-active rate: X/5

Result: PASS / FAIL
Delta: hook-active rate vs baseline rate
```

---

## 5. Future CI Hook-Point

When coordinator-claude acquires a CI runner (GitHub Actions recommended), this behavioral test plugs in as follows:

- **Test runner:** `bash tests/behavioral/ue-distrust-behavioral.sh` alongside the format test
- **Fixture location:** `tests/fixtures/ue-distrust/TestProj/TestProj.uproject` — committed to the repo
- **Reporting format:** TAP (Test Anything Protocol) — the existing format test already uses exit-code-based pass/fail compatible with TAP
- **Scheduling:** Not every PR — run weekly or on changes to `coordinator/hooks/` or any agent spec in `coordinator/agents/` that touches the holodeck-docs toolchain
- **Infrastructure requirement:** The CI runner needs holodeck-docs MCP server available (HTTP, `http://127.0.0.1:8765`) — either as a sidecar service or via a mock that returns realistic results. The mock approach is preferred for CI stability; the real server is preferred for behavioral fidelity.
- **Gate:** If behavioral rate drops below 4/5 on a tagged release, block the release and file a P0 issue against the hook or affected agent spec.
