# Windows Console-Flash Belt Experiment — Measurement Protocol

> **THIS DOCUMENT DESCRIBES WHAT THE PM EXECUTES.**
> Neither this document nor `console-flash-repro.sh` mutates the registry,
> changes any Windows setting, or modifies your terminal default.
> All machine-state changes described below are manual steps the PM performs.
> No script or command in this document auto-applies anything.

**Spec backlink:** `docs/plans/2026-05-29-windows-console-flash-elimination.md` § Chunk 5  
**Status:** Pending PM measurement  
**Purpose:** Determine whether the Windows Terminal ConPTY default-terminal / delegation
change suppresses the console-window flashes that Claude Central's own code cannot fix —
specifically the hook-interpreter spawns (PreToolUse `node` and `python`) and the
`pwsh` SessionStart hook that Claude Code itself forks, not us.

---

## Background

On Windows, when any process spawns a native **console-subsystem** `.exe` from a
non-console parent (e.g. git-bash running under **mintty**), Windows must allocate a
fresh `conhost.exe` window for the child. That window flashes briefly and exits with
the child process. `-WindowStyle Hidden` does NOT prevent this — it is create-then-hide;
the flash IS the creation event.

**Two suppression layers exist:**

- **Suspenders (Chunks 1–3):** Per-spawn flags (`CREATE_NO_WINDOW`, `windowsHide:true`)
  applied at our own code's `CreateProcess` calls. These fix the spawns we own —
  coordinator scripts and tools. They do NOT fix Claude Code's own internal spawns.
- **Machine-belt (this experiment):** Changing the Windows default-terminal application
  to Windows Terminal routes subprocess allocations through ConPTY, which suppresses
  the console window at the OS level. This is the only lever we have for the spawns
  Claude Code makes itself (PreToolUse hook interpreters, SessionStart `pwsh` hook).

**Critical distinction — default-terminal vs. profile:**  
Our own `docs/wiki/claude-code-platform-gotchas.md` documents this gotcha: changing
Windows Terminal's *profile* settings or *startup* configuration does **not** suppress
subprocess windows. Only changing the **default terminal application** (via Settings →
Default terminal application) + the associated **delegation registry keys** routes
non-Terminal-launched subprocesses through ConPTY. A profile-only change gives a false
negative — the experiment would show no improvement, but the belt was never actually applied.

---

## The Repro Script

```
console-flash-repro.sh [N]
```

`N` = number of spawns per exe type (default 10). Run from git-bash / mintty, **not**
from Windows Terminal itself. Running from WT pre-applies the belt and invalidates the
baseline.

The script spawns `python`, `node`, `powershell.exe`, and `pwsh` in tight loops with
a human-readable pause between phases so you can count flashes per type.

---

## Step 1 — Baseline measurement

1. Open a **git-bash** terminal (Mintty). Do NOT run from Windows Terminal.
2. Run:
   ```
   bash console-flash-repro.sh 10
   ```
3. For each phase, watch the screen and count how many visible console windows flash.
4. Record your counts in the **Before** column below.

---

## Results Table

| Exe | Spawns | Before (flash count) | After (flash count) | Notes |
|-----|--------|---------------------|---------------------|-------|
| `python` / `python.exe` | 10 | | | |
| `node` / `node.exe` | 10 | | | |
| `powershell.exe` (legacy blue) | 10 | | | |
| `pwsh` / `pwsh.exe` (PS 7) | 10 | | | |

---

## Step 2 — Apply the machine-belt lever

> **MANUAL STEPS — PM EXECUTES, NOT THE SCRIPT.**

There are two sub-steps. Both must be applied together for the belt to take effect.

### Sub-step A: Windows Settings — Default terminal application

This is the primary lever. It instructs Windows to route new console-process allocations
through Windows Terminal's ConPTY instead of the legacy `conhost.exe`.

1. Open **Windows Terminal**.
2. Press `Ctrl+,` to open Settings (or click the dropdown arrow → Settings).
3. Click **Startup** in the left sidebar.
4. Find **Default terminal application**.
5. Change the dropdown from `Windows Console Host` (or `Let Windows decide`) to
   **`Windows Terminal`**.
6. Click **Save**.

### Sub-step B: Registry — Delegation keys (verify / set if not already set)

The Settings UI writes to the registry. You can verify or set the keys directly via
`regedit.exe` or `reg query` if the Settings change did not propagate:

**Key path:**
```
HKEY_CURRENT_USER\Console\%%Startup
```

**Values to check:**
| Value name | Type | Expected value (after applying the belt) |
|---|---|---|
| `DelegationConsole` | REG_SZ | `{2EACA947-7F5F-4CFA-BA87-8F7FBEEFBE69}` (Windows Terminal GUID) |
| `DelegationTerminal` | REG_SZ | `{E12CFF52-A866-4C77-9A90-F570A7AA2C6B}` (Windows Terminal GUID) |

> **Note on GUIDs:** These are the GUIDs for Windows Terminal's console delegation handler.
> They are written by the Windows Terminal Settings UI when you select it as the default.
> If your machine shows different GUIDs (non-empty, non-zero), record them here — they may
> be a different installed version of WT. Empty / all-zeros means delegation is not active.

To check current values (read-only query, safe to run):
```
reg query "HKCU\Console\%%Startup" /v DelegationConsole
reg query "HKCU\Console\%%Startup" /v DelegationTerminal
```

If the Settings UI change worked, these queries will return the WT GUIDs above.
If they still show empty / all-zeros after the Settings change, the delegation is not active.

> **DO NOT RUN `reg add` unless the Settings UI failed to set the values.**
> The Settings UI is the preferred path. Only use `reg add` as a manual fallback
> if the UI did not set the delegation keys, and only after confirming this with the PM.

---

## Step 3 — Re-measure

After applying both sub-steps above:

1. Open a **new** git-bash terminal (the change takes effect for new processes).
2. Run:
   ```
   bash console-flash-repro.sh 10
   ```
3. Count flashes for each phase.
4. Record your counts in the **After** column of the results table above.

---

## Step 4 — Decision rule

Compare Before vs. After:

| Outcome | Conclusion | Next action |
|---------|-----------|-------------|
| After column is 0 for all exe types | ConPTY belt is fully effective | Mark AC6 PASS; Chunks 1–3 (suspenders) cover our own scripts; no further machine-level work needed |
| After column reduced but not zero | Partial suppression | Investigate which exe types still flash; check whether delegation keys were set correctly |
| After column unchanged (same as Before) | Belt not effective OR not applied correctly | Re-verify Sub-steps A and B; confirm both delegation keys are set to WT GUIDs; if still unchanged, escalate to the C# shim Addendum |
| After column is 0 only for some exe types | Belt works for WT-hosted spawns but not all | Investigate which parent process is spawning the remaining flashing children |

### Escalation path if belt is insufficient

If the ConPTY belt does not suppress the hook-interpreter and `pwsh` flashes even with
delegation keys confirmed set, the documented next option is a tiny signed C# shim
(`lib/spawn-shim.exe`) that wraps `CreateProcess` with `CREATE_NO_WINDOW=true` and
`bInheritHandles=TRUE`. This is NOT built in this pass. See:

```
docs/plans/2026-05-29-windows-console-flash-elimination.md § Addendum
```

for the full specification of what must be designed before the shim approach is adopted
(build toolchain, signing, binary distribution story, percolation via `setup/publish.sh`).

---

## What this experiment does NOT test

- The per-spawn suppression (`lib/spawn-hidden.sh`, `windowsHide:true`, `CREATE_NO_WINDOW`)
  applied by Chunks 1–3 to spawns that coordinator scripts own. Those are verified separately
  by the Chunk-1/2/3 acceptance tests.
- Any flash from processes other than the four exe types above.
- Cross-machine behavior — this measurement is machine-specific. Other machines running
  git-bash under mintty will exhibit the same flashes; the belt must be applied per-machine.

---

## Relationship to `claude-code-platform-gotchas.md`

The gotchas wiki documents the `-WindowStyle Hidden` limitation:
> `-WindowStyle Hidden` does not prevent the flash; it is create-then-hide. Only
> `CREATE_NO_WINDOW` at the spawning parent prevents the allocation.

That limitation applies equally here: `-WindowStyle Hidden` on the pwsh SessionStart
hook has been present for some time and has NOT suppressed the flash. This experiment
tests whether ConPTY delegation — a different mechanism operating at the OS
console-allocation layer — does what per-spawn flags cannot.
