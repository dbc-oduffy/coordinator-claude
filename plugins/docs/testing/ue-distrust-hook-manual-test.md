# Manual Test Protocol — ue-knowledge-distrust.sh

**Last updated:** 2026-04-14
**Relates to:** `coordinator/hooks/scripts/ue-knowledge-distrust.sh`
**Automated counterpart:** `coordinator/tests/hooks/ue-knowledge-distrust.test.sh`

---

## 1. Purpose and When to Run

This protocol validates the **behavioral intent** of the UE knowledge-distrust hook — that the distrust signal actually changes how agents approach UE API claims, not merely that the hook outputs the correct text.

The automated shell test (`ue-knowledge-distrust.test.sh`) validates format and registration. This protocol validates *behavior*: do agents consult holodeck-docs before writing UE code when the hook fires, vs. when it doesn't?

**Run this protocol:**
- After any change to `ue-knowledge-distrust.sh` that alters wording or structure
- After any change to agent dispatch logic in the coordinator that might suppress hook injection
- Before a coordinator-claude release if the hook has changed since the last release
- When a hallucination incident is reported in a UE project session (as a regression check)

**Do NOT run** for routine count-update commits (e.g., updating 380K → 421,935). The automated test covers those.

---

## 2. Fixture Specification

You need a minimal `.uproject` directory and a hallucination-prone task prompt. The prompt must reliably trigger hallucination in base LLM behavior — overly-generic UE prompts ("how does GAS work?") won't discriminate; a specific API-assertion task will.

**Fixture directory:** Any directory with a `.uproject` at root or within 3 levels. Recommended: `E:/dev/ue/Keep_Blank` (lightweight, no code).

**Task prompt (use verbatim):**
```
Add a UPROPERTY with EditAnywhere and BlueprintReadOnly to a custom Actor class.
Include the correct module in Build.cs so it compiles. Write the full .h snippet.
```

This prompt targets two confirmed hallucination hotspots: UPROPERTY specifier combinations and Build.cs module names. Without RAG verification, agents frequently produce wrong specifier combos or incorrect module names (e.g., citing `CoreUObject` when `Engine` or a more specific module is required).

---

## 3. Dispatch Protocol

### 3a. Control run (hook suppressed)

Temporarily rename the hook so SessionStart doesn't fire it:

```bash
cd ~/.claude/plugins/coordinator-claude
mv coordinator/hooks/scripts/ue-knowledge-distrust.sh \
   coordinator/hooks/scripts/ue-knowledge-distrust.sh.disabled
```

Start a new Claude Code session in the fixture directory. Dispatch the task prompt to a `ue-gameplay-engineer` agent or equivalent Sonnet specialist. Record:
- Did the agent call `quick_ue_lookup` or `lookup_ue_class` before writing the snippet?
- Does the produced snippet have a verifiable error (wrong specifier combo, wrong module)?

Restore the hook after recording:
```bash
mv coordinator/hooks/scripts/ue-knowledge-distrust.sh.disabled \
   coordinator/hooks/scripts/ue-knowledge-distrust.sh
```

### 3b. Treatment run (hook active)

Start a fresh Claude Code session in the same fixture directory. The hook should fire at SessionStart (visible in the session context if hook injection is working). Dispatch the same task prompt. Record the same signals.

### 3c. Repeat

Run at least 3 trials of each condition (control, treatment) for a meaningful comparison. 5 trials is preferred. Log each trial: session start time, did agent call RAG before writing, was output verifiably correct.

---

## 4. Observable Signals

**Pass signals (treatment condition — hook active):**
- Agent calls `mcp__holodeck-docs__quick_ue_lookup` or `mcp__holodeck-docs__lookup_ue_class` **before** writing the .h snippet
- Agent cites holodeck-docs as the basis for its UPROPERTY specifier choice
- Produced snippet has no known specifier or module errors (cross-check via `check_ue_patterns`)
- Hook output visible at session start: `UE PROJECT DETECTED (Keep_Blank): ...`

**Fail signals:**
- Agent writes the snippet from training knowledge without any holodeck-docs call
- Produced snippet contains a hallucinated specifier combo (e.g., `EditAnywhere | BlueprintReadOnly` without `meta=(...)` required in some contexts, or wrong module in Build.cs)
- Hook output not visible at session start (hook injection not working)

**Threshold for behavioral pass:** ≥4/5 treatment trials result in holodeck-docs being called before the snippet is written. If fewer than 4/5 pass, the hook wording is not strong enough to change behavior — escalate for wording revision.

---

## 5. Failure Triage

**Hook output not visible at session start:**
1. Confirm the hook is registered: `jq '.hooks.SessionStart[] | .hooks[].command' ~/.claude/plugins/coordinator-claude/coordinator/hooks/hooks.json | grep distrust`
2. Confirm Claude Code is loading the coordinator plugin: check `~/.claude/plugins/coordinator-claude/coordinator/hooks/hooks.json` is in the active plugin manifest
3. Run the hook manually to confirm it fires from the fixture directory: `cd E:/dev/ue/Keep_Blank && bash ~/.claude/plugins/coordinator-claude/coordinator/hooks/scripts/ue-knowledge-distrust.sh`
4. If the hook fires manually but not at SessionStart: the coordinator plugin may not be loaded in this project. Check `.claude/coordinator.local.md` or global plugin registration.

**Hook fires but agents still hallucinate ≥2/5 trials:**
- The wording may be too weak. Review the current distrust wording against the three-block schema. Agents skim past boilerplate; if risk categories or tool names are buried or absent, the signal degrades.
- Check whether the dispatched agent spec has its own distrust preamble (domain agents receive the EM hook injection only indirectly). Subagents need preambles in their own spec files.
- Escalate: open a stub to strengthen the distrust wording or add a PreToolUse hook to inject the signal on first UE-relevant tool call.

**Automated test passes but manual test fails:**
- The automated test verifies format, not behavioral reach. If format is correct but behavior is wrong, the issue is hook injection into agent sessions — not hook content. The hook fires only in the EM session; subagents need spec-level preambles. Confirm all domain agent specs have distrust preambles (see stub 12 audit report).

**Future CI hook-point:** Once coordinator-claude has a CI pipeline, the behavioral regression test can be formalized as a scheduled check using a mock dispatcher that counts RAG tool calls per session. Until then, this manual protocol is the behavioral gate. The automated shell test (`ue-knowledge-distrust.test.sh`) is CI-ready today and covers format + registration.
