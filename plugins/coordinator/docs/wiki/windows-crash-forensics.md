---
title: Windows Kernel-Mode Crash Forensics
status: active
kind: doctrine-wiki
created: 2026-05-18
---

# Windows Kernel-Mode Crash Forensics

## Overview

Windows kernel-mode crash triage on developer machines (CI environments differ; this wiki is the dev-box workflow). Event Viewer's "disorderly shutdown" attributions routinely surface the WRONG driver as cause; trust WinDbg/cdb output before event-log attribution. GUI debuggers (windbgx, WinDbg Preview) hang on minidump-only crashes; CLI tools (cdb.exe) succeed.

## 1. Use cdb.exe + Elevated PowerShell, Not windbgx GUI

Source: 2026-05-14 project-rag-ue-addon, lessons.md L54.

The GUI debuggers' "Open minidump" flow stalls on `C:\Windows\Minidump\*.dmp` files. `cdb.exe -z <path-to-dmp>` followed by `!analyze -v` produces the actual fault chain.

Run from an **elevated PowerShell** — non-elevated cdb opens the file but `!analyze -v` returns partial results.

Set the symbol path before the first run:

```powershell
$env:_NT_SYMBOL_PATH = "srv*C:\symbols*https://msdl.microsoft.com/download/symbols"
```

## 2. Run `!analyze -v` Before Trusting Event-Log Driver Attribution

Source: 2026-05-14 project-rag-ue-addon, lessons.md L56.

Event Viewer "disorderly shutdown" entries name a driver from the kernel call stack at shutdown time — not necessarily the FAULTING driver. The crashed driver and the driver that was running at unclean-stop time are often different (especially when fault is in graphics/storage and the unclean-stop driver is a higher-level subsystem).

`!analyze -v` reports `MODULE_NAME` and `FAILURE_BUCKET_ID` keyed on the actual fault frame. Those two fields are the authoritative attribution — event-log driver names are circumstantial.

## 3. Minimum Forensic Toolchain (Install Once Per Dev Box)

- **WinDbg from Microsoft Store** — provides `cdb.exe` under the Windows Kits directory
- **Symbol path env var:** `_NT_SYMBOL_PATH=srv*C:\symbols*https://msdl.microsoft.com/download/symbols`
- **Elevated PowerShell shortcut** pinned to taskbar for crash-triage sessions

Default `cdb.exe` location after WinDbg install:

```
C:\Program Files (x86)\Windows Kits\10\Debuggers\x64\cdb.exe
```

Verify with:

```powershell
Get-Item "C:\Program Files (x86)\Windows Kits\10\Debuggers\x64\cdb.exe"
```

## 4. Where to Find Minidumps

| Dump type | Path |
|---|---|
| Kernel-mode crash | `C:\Windows\Minidump\*.dmp` |
| Recoverable subsystem crash | `C:\Windows\LiveKernelReports\*.dmp` |
| User-mode (WER) | `%LOCALAPPDATA%\CrashDumps\<exe>.<pid>.dmp` |

Kernel minidumps require elevation to read. If `cdb.exe` opens without error but `!analyze -v` returns truncated output, the PowerShell session is not elevated.

## Quick Triage Script

```powershell
# Run from elevated PowerShell
$env:_NT_SYMBOL_PATH = "srv*C:\symbols*https://msdl.microsoft.com/download/symbols"

$dmp = Get-ChildItem C:\Windows\Minidump\*.dmp |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if (-not $dmp) {
    Write-Error "No minidumps found in C:\Windows\Minidump\"
    exit 1
}

Write-Host "Analyzing: $($dmp.FullName)"
& "C:\Program Files (x86)\Windows Kits\10\Debuggers\x64\cdb.exe" `
    -z $dmp.FullName `
    -c "!analyze -v; q"
```

Key output fields to read:

- `MODULE_NAME` — the faulting module (trust this over Event Viewer)
- `FAILURE_BUCKET_ID` — stable identifier for the fault class; useful for searching Microsoft's symbol server and KB articles
- `STACK_TEXT` — full fault chain; read top-to-bottom for the causal sequence

## 5. Crash-Recovery Sweeps All Sibling Repos, Not Just Newest Handoff

Source: 2026-05-17 project-rag.

When a session crashes mid-flight on a workstation with multiple sibling repos (meta + addon + plugin + tools), crash-recovery must enumerate dirty/untracked files **and** the reflog across **every** sibling repo, not stop at the newest handoff in the primary repo. Concurrent EMs routinely touch sibling repos in the same session; a crash leaves partial work in repos the primary handoff never references.

**Crash-recovery sweep checklist:**

1. **Newest handoff in the primary repo** — read for in-flight context.
2. **`git status` in every sibling repo** under the workstation's repo root. Untracked files in a sibling repo may be partial work from the crashed session that the primary handoff did not name.
3. **`git reflog` in every sibling repo** (last ~50 entries). Detached HEADs, partial commits, and stash drops surface here even when working trees look clean.
4. **`git stash list`** in every sibling repo. Mid-crash stashes are recoverable but invisible to `git status`.

Skipping sibling repos because "the handoff didn't mention them" is the failure mode. Concurrent-EM sessions don't always update the primary handoff when they touch siblings — the sweep is the safety net.

## Related

- `docs/wiki/claude-code-platform-gotchas.md` — Windows subprocess pop-ups; MCP idiosyncrasies
- `docs/wiki/implementation-standards-by-domain.md` § Windows
