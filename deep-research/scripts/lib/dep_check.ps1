
# dep_check.ps1 — PowerShell dependency-check shell functions.
# 1:1 functional parity with scripts/lib/dep_check.sh (bash sibling).
# Provides Phase 0 logic: agent-mode detection, dep probing, consent gate,
# and the disk-resident visited-set protocol for diamond-DAG/cycle detection.
# Spec backlink: docs/plans/2026-06-15-deep-research-install-chain-application-phase-b.md §7 C3
#
# Source this file (. .\scripts\lib\dep_check.ps1) before calling functions.
#
# Visited-set keyspace: ~/.claude/deep-research-claude/chain-walk-<session-id>.json
# (per agent-install-contract.md § Visited-set protocol; Patrik Finding 4 correction)
#
# Functions exported by this file:
#   Test-DrPhaseZeroShouldRun       — allowlist check; returns $true (run) or $false (skip)
#   Invoke-DrRunModePrompt          — agent-direct y/N prompt; exits 92 on agent-mode
#   Test-DrDepProbe                 — runs functional probe; returns present/missing/present-but-broken
#   Get-DrDepProbeAll               — NDJSON one line per dep
#   Invoke-DrVisitedSetCrashCleanup — Phase 0 entry crash-recovery reaper (>5 min TTL, age-only)
#   Initialize-DrVisitedSet         — creates visited-set file, stale-cleans >1h files
#   Test-DrVisitedSet               — $true if dep already visited
#   Add-DrVisitedSet                — atomic append dep to visited set
#   Invoke-DrConsentGate            — emits banner, enforces confirmation; exits 90/91/93
#
# Exit codes (canonical — shared with bash sibling):
#   90  non-interactive/non-TTY hard-dep-missing (no flag pair)
#   91  double-confirm declined under TTY
#   92  agent-direct-invocation detected
#   93  override-flag-pair-incomplete (only one of two flags provided)

# ---------------------------------------------------------------------------
# Phase-zero read-only flag allowlist
# Canonical list per plugins/coordinator-claude/coordinator/docs/wiki/agent-install-contract.md §Dual-mode script UX.
# Follow-up repos inherit this baseline; add repo-specific flags on top.
# Do NOT scan for these flags inline in setup.ps1 — all logic lives here.
# ---------------------------------------------------------------------------
# ALLOWLIST: --help --version --phase-list --last-status --i-am-agent --check
# (--i-am-agent is listed for documentation completeness; it triggers exit 92
#  via Invoke-DrRunModePrompt BEFORE Phase 0 would run, but we note it here so
#  the allowlist is complete and greppable.)
# (--check is DR's repo-specific read-only extension per contract § Read-only flag carve-out)

function Test-DrPhaseZeroShouldRun {
    <#
    .SYNOPSIS
    Returns $true if Phase 0 (consent gate + chain-walk) should execute.
    Returns $false when a read-only flag is present (caller should skip Phase 0).
    Spec backlink: docs/plans/2026-06-15-deep-research-install-chain-application-phase-b.md §7 C3
    #>
    param([string[]]$ParsedArgs)

    # Read-only flag allowlist — Phase 0 is skipped when any of these are present.
    $readOnlyFlags = @('--help', '--version', '--phase-list', '--last-status', '--i-am-agent',
                       '--check',
                       '-Help', '-Version', '-PhaseList', '-LastStatus', '-IAmAgent',
                       '-Check',
                       '-h', '-?')

    foreach ($arg in $ParsedArgs) {
        if ($readOnlyFlags -contains $arg) {
            return $false
        }
    }
    return $true
}

function Invoke-DrRunModePrompt {
    <#
    .SYNOPSIS
    Phase 0 step (a): detect whether caller is an autonomous agent.
    Prints a y/N prompt on TTY (unless overridden). Exits 92 on agent-mode detection.
    Parity with bash _dr_run_mode_prompt.

    Not called when Test-DrPhaseZeroShouldRun returns $false.
    Not called under --non-interactive or non-TTY (both treated as implicit --i-am-human).
    #>
    param(
        [bool]$IAmAgent  = $false,
        [bool]$IAmHuman  = $false,
        [bool]$Interactive = $false
    )

    # Env-var override takes precedence over flags.
    $runMode = $env:DEEP_RESEARCH_RUN_MODE

    # Flag --i-am-agent: short-circuit as agent mode.
    if ($IAmAgent -or $runMode -eq 'agent') {
        [Console]::Error.WriteLine('AGENT_MANIFEST_PATH=docs/install/AGENT.md')
        [Console]::Error.WriteLine('[setup] Agent-direct invocation detected. Use /deep-research:setup instead.')
        [Console]::Error.WriteLine('[setup] Agent install guide: docs/install/AGENT.md')
        exit 92
    }

    # Flag --i-am-human or env=human: skip prompt, continue as human.
    if ($IAmHuman -or $runMode -eq 'human') { return }

    # Non-TTY or non-interactive: treat as implicit --i-am-human (no prompt text in CI logs).
    # Spec: §3.1(ii) step (a) — prompt skipped under non-interactive/non-TTY [Patrik N-2].
    $isTty = [Environment]::UserInteractive -and -not [Console]::IsInputRedirected
    if (-not $isTty -or -not $Interactive) { return }

    # Interactive TTY without explicit flag: ask.
    $reply = Read-Host 'Are you running this script as an autonomous agent rather than via /deep-research:setup? [y/N]'
    if ([string]::IsNullOrWhiteSpace($reply)) { $reply = 'N' }
    if ($reply -match '^[Yy]$') {
        [Console]::Error.WriteLine('AGENT_MANIFEST_PATH=docs/install/AGENT.md')
        [Console]::Error.WriteLine('[setup] Agent-direct invocation confirmed. Use /deep-research:setup instead.')
        exit 92
    }
}

function Test-DrDepProbe {
    <#
    .SYNOPSIS
    Run the functional probe for a single dep.
    Returns: 'present' | 'missing' | 'present-but-broken'
    Parity with bash _dr_dep_probe.
    Spec backlink: docs/plans/2026-06-15-deep-research-install-chain-application-phase-b.md §7 C3
    #>
    param(
        [Parameter(Mandatory)][string]$DepId,
        [Parameter(Mandatory)][string]$SiblingDirName,
        [Parameter(Mandatory)][string]$ProbeKind,
        [hashtable]$ProbeArgs = @{},
        [string]$SiblingRoot = "",
        [string]$Python = ""
    )

    # Resolve sibling root (parent of deep-research-claude repo or nested working repo).
    if (-not $SiblingRoot) {
        $ScriptDir  = Split-Path -Parent $PSCommandPath
        $RepoRoot   = Split-Path -Parent (Split-Path -Parent $ScriptDir)
        $SiblingRoot = Split-Path -Parent $RepoRoot
    }

    $siblingPath = Join-Path $SiblingRoot $SiblingDirName

    # Implicit sibling_dir_exists check: if folder absent → check nested-layout fallback.
    # In the working meta-repo layout, coordinator-claude lives under
    # plugins/coordinator-claude/coordinator/, not as a sibling repo named coordinator-claude.
    # The sibling_dir_name contract field is shaped for the flat publish-repo layout where
    # X:\deep-research-claude and X:\coordinator-claude are true siblings.
    # In nested working-repo layout we strip the "-claude" suffix and check the sub-folder.
    # Review: code-reviewer — P1 bug (mirror of bash fix): nested-layout probe always
    # returned 'missing' because ...\coordinator-claude doesn't exist; the real path is
    # ...\coordinator (i.e., ~/.claude/plugins/coordinator-claude/coordinator).
    if (-not (Test-Path $siblingPath -PathType Container)) {
        if ($SiblingDirName.EndsWith('-claude')) {
            $bareName    = $SiblingDirName.Substring(0, $SiblingDirName.Length - '-claude'.Length)
            $fallbackPath = Join-Path $SiblingRoot $bareName
            if ($bareName -ne '' -and (Test-Path $fallbackPath -PathType Container)) {
                # Nested-layout: use the "-claude"-stripped sub-folder path.
                $siblingPath = $fallbackPath
            } else {
                return 'missing'
            }
        } else {
            return 'missing'
        }
    }

    # Folder present — now run the functional probe.
    switch ($ProbeKind) {
        'sibling_dir_exists' {
            # Presence check is sufficient.
            return 'present'
        }
        'file_exists' {
            $targetFile = Join-Path $siblingPath $ProbeArgs['path']
            if (Test-Path $targetFile) { return 'present' } else { return 'present-but-broken' }
        }
        'python_import' {
            if (-not $Python) {
                # Resolve Python with a functional probe — not just Get-Command / --version.
                # The Windows 11 WindowsApps Store stub passes existence checks but exits
                # non-zero when actually invoked.  We execute a version-gate expression
                # (sys.version_info >= (3,11)) so the returned candidate is confirmed
                # working AND meets the minimum version. Parity with setup.ps1 Find-Python
                # and bash _co_find_python (Store-stub hardened). PS parity 2026-06-23.
                $versionCheck = 'import sys; sys.exit(0 if sys.version_info[:2] >= (3,11) else 1)'
                foreach ($candidate in @('python3', 'python')) {
                    if (-not (Get-Command $candidate -ErrorAction SilentlyContinue)) { continue }
                    try {
                        & $candidate -c $versionCheck 2>$null
                        if ($LASTEXITCODE -eq 0) { $Python = $candidate; break }
                    } catch {}
                }
                # py launcher fallback — bypasses WindowsApps aliases on Windows.
                if (-not $Python -and (Get-Command 'py' -ErrorAction SilentlyContinue)) {
                    foreach ($pyVer in @('-3.12', '-3.11', '-3', '')) {
                        try {
                            $pyArgs = if ($pyVer -ne '') { @($pyVer, '-c', $versionCheck) } else { @('-c', $versionCheck) }
                            & py @pyArgs 2>$null
                            if ($LASTEXITCODE -eq 0) {
                                $resolveArgs = if ($pyVer -ne '') { @($pyVer, '-c', 'import sys;print(sys.executable)') } else { @('-c', 'import sys;print(sys.executable)') }
                                $resolved = (& py @resolveArgs 2>$null | Out-String).Trim()
                                if ($resolved -and (Test-Path $resolved)) { $Python = $resolved; break }
                            }
                        } catch {}
                    }
                }
            }
            if (-not $Python) { return 'present-but-broken' }
            $expr = $ProbeArgs['expr']
            # Run from caller's cwd, NOT from sibling dir — the probe must match the
            # runtime's actual sys.path resolution (post-`pip install --system -e`).
            # cd-into-sibling would mask the partial-install state the consent gate
            # is supposed to detect (sibling files present but not pip-installed).
            # Parity with bash half: scripts/lib/dep_check.sh python_import branch.
            & $Python -c $expr 2>$null
            if ($LASTEXITCODE -eq 0) { return 'present' } else { return 'present-but-broken' }
        }
        'command_succeeds' {
            $cmd = $ProbeArgs['cmd']
            try {
                # Cross-ported from coord Phase B slice-A F4 (2026-06-15): replaced
                # Invoke-Expression with [scriptblock]::Create to eliminate arbitrary
                # code execution. The manifest is the trust boundary; previously any
                # manifest-controlled cmd string could execute arbitrary PowerShell
                # via Invoke-Expression. ScriptBlock::Create provides controlled
                # interpretation without the eval shape (no environment/argument
                # expansion tricks that bypass Invoke-Expression).
                & ([scriptblock]::Create($cmd)) 2>$null | Out-Null
                if ($LASTEXITCODE -eq 0) { return 'present' } else { return 'present-but-broken' }
            } catch {
                return 'present-but-broken'
            }
        }
        default {
            [Console]::Error.WriteLine("WARNING: unknown probe kind '$ProbeKind' for dep '$DepId'; treating as present-but-broken")
            return 'present-but-broken'
        }
    }
}

function Get-DrDepProbeAll {
    <#
    .SYNOPSIS
    Probe all direct deps from the manifest; emit one NDJSON line per dep.
    Fields: {id, severity, sibling_path, status, hint}
    Parity with bash _dr_dep_probe_all.
    Spec backlink: docs/plans/2026-06-15-deep-research-install-chain-application-phase-b.md §7 C3
    #>
    param(
        [string]$ManifestPath = "",
        [string]$Python       = "",
        [string]$SiblingRoot  = ""
    )

    # Resolve manifest path.
    if (-not $ManifestPath) {
        $ScriptDir    = Split-Path -Parent $PSCommandPath
        $RepoRoot     = Split-Path -Parent (Split-Path -Parent $ScriptDir)
        $ManifestPath = Join-Path $RepoRoot 'docs\install\agent-install-manifest.json'
        if (-not $SiblingRoot) { $SiblingRoot = Split-Path -Parent $RepoRoot }
    }

    # Use manifest_reader.ps1 to get NDJSON per dep.
    $readerScript = Join-Path (Split-Path -Parent $PSCommandPath) 'manifest_reader.ps1'
    if (-not (Test-Path $readerScript)) {
        [Console]::Error.WriteLine("ERROR: manifest_reader.ps1 not found at $readerScript")
        return
    }

    # Direct script invocation (& operator) in the current PowerShell session — NOT a
    # subprocess spawn via `pwsh -NoProfile -File`.  The subprocess form fails silently
    # when pwsh is not on PATH and is inconsistent with how setup.ps1 -Check invokes the
    # same reader (using & $readerScript).  Parity with bash sibling (sources as function).
    # Review: code-reviewer — P2 bug: pwsh subprocess spawn was not parity with bash sibling
    # and would fail silently if pwsh wasn't on PATH; replaced with direct & invocation.
    $lines = & $readerScript -ManifestPath $ManifestPath 2>&1
    if ($LASTEXITCODE -ne 0) {
        foreach ($l in $lines) { [Console]::Error.WriteLine($l) }
        return
    }

    foreach ($line in $lines) {
        $line = ($line | Out-String).Trim()
        if ([string]::IsNullOrWhiteSpace($line)) { continue }

        $dep = $null
        try { $dep = $line | ConvertFrom-Json } catch { continue }

        # Build probe args hashtable from functional_probe_args.
        $probeArgs = @{}
        if ($dep.functional_probe_args) {
            $dep.functional_probe_args.PSObject.Properties | ForEach-Object {
                $probeArgs[$_.Name] = $_.Value
            }
        }

        $status = Test-DrDepProbe `
            -DepId         $dep.id `
            -SiblingDirName $dep.sibling_dir_name `
            -ProbeKind     $dep.functional_probe_kind `
            -ProbeArgs     $probeArgs `
            -SiblingRoot   $SiblingRoot `
            -Python        $Python

        # Compute sibling_path for hint.
        $siblingPath = Join-Path $SiblingRoot $dep.sibling_dir_name

        $hint = switch ($status) {
            'missing'           { "clone from $($dep.upstream_url)" }
            'present-but-broken' { "sibling present but functional probe failed; re-run /deep-research:setup" }
            default             { "" }
        }

        [ordered]@{
            id           = $dep.id
            severity     = $dep.severity
            sibling_path = $siblingPath
            status       = $status
            hint         = $hint
        } | ConvertTo-Json -Compress -Depth 3
    }
}

# ---------------------------------------------------------------------------
# Visited-set protocol — disk-resident concurrency-safe set for chain-walk.
# Spec backlink: plugins/coordinator-claude/coordinator/docs/wiki/agent-install-contract.md § Visited-set protocol
# Schema: { "session_id": "...", "started_at": "ISO8601", "visited": [...] }
# File: ~/.claude/deep-research-claude/chain-walk-<session-id>.json
# (Patrik Finding 4: path uses ~/.claude/<repo-id>/ NOT ~/.<repo-id>/)
# Stale cleanup: files older than 1h deleted by top-level invocation.
# Atomic read-modify-write: temp-then-rename (lock-file pattern via Move via
# [System.IO.File]::Move with overwrite=true; race-safe on NTFS).
# ---------------------------------------------------------------------------

function Invoke-DrVisitedSetCrashCleanup {
    <#
    .SYNOPSIS
    Phase 0 entry crash-recovery reaper for orphan visited-set files.

    .DESCRIPTION
    A crashed install (killed process, power loss, Ctrl-C) leaves a chain-walk-*.json
    file whose session-id is no longer active.  The session-start janitor
    (Initialize-DrVisitedSet) uses a 1h TTL, so a retry within that window silently
    treats the stale entry as an in-progress session and skips dep installation.
    This pass uses a 5-minute TTL, targeting exactly that crash-retry window.

    Visited-set keyspace: ~/.claude/deep-research-claude/ (Patrik Finding 4 correction).

    Complementary surfaces:
      Initialize-DrVisitedSet  — session-start janitor, 1h TTL (DO NOT MODIFY)
      _dr_visited_set_crash_cleanup — bash parity (dep_check.sh)
    #>
    $drDir = Join-Path $env:USERPROFILE '.claude\deep-research-claude'
    if (-not (Test-Path $drDir -PathType Container)) { return }

    $staleThreshold = (Get-Date).AddMinutes(-5)
    Get-ChildItem -Path $drDir -Filter 'chain-walk-*.json' -ErrorAction SilentlyContinue | Where-Object {
        $_.LastWriteTime -lt $staleThreshold
    } | Remove-Item -Force -ErrorAction SilentlyContinue
}

function Initialize-DrVisitedSet {
    <#
    .SYNOPSIS
    Create a fresh visited-set file for this chain-walk session.
    Deletes stale (>1h) chain-walk-*.json files first.
    Returns the session-id string.
    Keyspace: ~/.claude/deep-research-claude/ per contract § Visited-set protocol.
    #>
    param([string]$SessionId = "")

    if (-not $SessionId) {
        $SessionId = [System.Guid]::NewGuid().ToString()
    }

    $drDir = Join-Path $env:USERPROFILE '.claude\deep-research-claude'
    if (-not (Test-Path $drDir)) {
        New-Item -ItemType Directory -Path $drDir -Force | Out-Null
    }

    # Stale-cleanup: remove chain-walk-*.json older than 1 hour.
    $staleThreshold = (Get-Date).AddHours(-1)
    Get-ChildItem -Path $drDir -Filter 'chain-walk-*.json' -ErrorAction SilentlyContinue | Where-Object {
        $_.LastWriteTime -lt $staleThreshold
    } | Remove-Item -Force -ErrorAction SilentlyContinue

    $filePath = Join-Path $drDir "chain-walk-$SessionId.json"
    $data = [ordered]@{
        session_id = $SessionId
        started_at = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
        visited    = @()
    }
    $json = $data | ConvertTo-Json -Depth 3
    # Atomic write: temp then rename.
    $tmp = "$filePath.tmp.$PID"
    try {
        [System.IO.File]::WriteAllText($tmp, $json, [System.Text.UTF8Encoding]::new($false))
        [System.IO.File]::Move($tmp, $filePath, $true)
    } catch {
        if (Test-Path $tmp) { Remove-Item $tmp -Force -ErrorAction SilentlyContinue }
        throw
    }

    return $SessionId
}

function Test-DrVisitedSet {
    <#
    .SYNOPSIS
    Returns $true if the given dep id is already in the visited-set for this session.
    Keyspace: ~/.claude/deep-research-claude/ per contract § Visited-set protocol.
    #>
    param(
        [Parameter(Mandatory)][string]$SessionId,
        [Parameter(Mandatory)][string]$DepId
    )

    $filePath = Join-Path $env:USERPROFILE ".claude\deep-research-claude\chain-walk-$SessionId.json"
    if (-not (Test-Path $filePath)) { return $false }

    try {
        $data = Get-Content -LiteralPath $filePath -Raw -Encoding UTF8 | ConvertFrom-Json
        return ($data.visited -contains $DepId)
    } catch {
        return $false
    }
}

function Add-DrVisitedSet {
    <#
    .SYNOPSIS
    Atomically append a dep id to the visited-set for this session.
    Uses temp-then-rename for atomic read-modify-write.
    Keyspace: ~/.claude/deep-research-claude/ per contract § Visited-set protocol.
    #>
    param(
        [Parameter(Mandatory)][string]$SessionId,
        [Parameter(Mandatory)][string]$DepId
    )

    $filePath = Join-Path $env:USERPROFILE ".claude\deep-research-claude\chain-walk-$SessionId.json"
    $tmp      = "$filePath.tmp.$PID"

    $maxRetries = 5
    for ($i = 0; $i -lt $maxRetries; $i++) {
        try {
            # Read current state.
            $data = Get-Content -LiteralPath $filePath -Raw -Encoding UTF8 | ConvertFrom-Json
            $visitedList = [System.Collections.Generic.List[string]]::new()
            if ($data.visited) { $data.visited | ForEach-Object { $visitedList.Add($_) } }
            if (-not $visitedList.Contains($DepId)) { $visitedList.Add($DepId) }

            # Write updated state atomically.
            $updated = [ordered]@{
                session_id = $data.session_id
                started_at = $data.started_at
                visited    = $visitedList.ToArray()
            }
            $json = $updated | ConvertTo-Json -Depth 3
            [System.IO.File]::WriteAllText($tmp, $json, [System.Text.UTF8Encoding]::new($false))
            [System.IO.File]::Move($tmp, $filePath, $true)
            return
        } catch {
            if (Test-Path $tmp) { Remove-Item $tmp -Force -ErrorAction SilentlyContinue }
            if ($i -lt ($maxRetries - 1)) { Start-Sleep -Milliseconds 50 }
        }
    }
    [Console]::Error.WriteLine("WARNING: could not atomically update visited-set for session $SessionId dep $DepId")
}

# ---------------------------------------------------------------------------
# Override-flag convention — cross-repo localization (ratified 2026-05-09)
#
# Convention: --skip-dep-check + --accept-<repo-risk>-risk
#
# deep-research-claude risk class: vestigial-path (single soft dep on coordinator-claude).
# Flag pair: --skip-dep-check + --accept-missing-deps-risk
# (predecessor §7.2 PM-ratified vestigial-path naming)
#
# Authoritative contract: plugins/coordinator-claude/coordinator/docs/wiki/agent-install-contract.md
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Consent gate
# Spec backlink: docs/plans/2026-06-15-deep-research-install-chain-application-phase-b.md §7 C3
# ---------------------------------------------------------------------------

function Invoke-DrConsentGate {
    <#
    .SYNOPSIS
    Consent gate: emit verbatim banner, enforce double-confirm or flag-pair.
    Parity with bash _dr_consent_gate.
    Gate behavior table (spec §3.3):
      TTY, no flag pair           : banner → confirm1 → confirm2 → proceed; exit 91 on N
      Non-TTY, no flag pair       : banner → exit 90
      TTY, both flags             : banner once → one-line ack → proceed
      Non-TTY, both flags         : banner once to stderr → proceed
      Either, only one flag       : exit 93

    Parameters:
      -MissingHardDeps   : string[] — list of missing hard dep IDs (shown in banner)
      -SkipDepCheck      : bool — --skip-dep-check flag
      -AcceptHallucRisk  : bool — --accept-missing-deps-risk flag
      -Interactive       : bool — whether the session is interactive
      -BannerPath        : path to dep_consent_banner.txt (defaults to sibling of this script)
    #>
    param(
        [string[]]$MissingHardDeps   = @(),
        [bool]$SkipDepCheck          = $false,
        [bool]$AcceptHallucRisk      = $false,
        [bool]$Interactive           = $false,
        [string]$BannerPath          = ""
    )

    # Resolve banner file.
    if (-not $BannerPath) {
        $BannerPath = Join-Path (Split-Path -Parent $PSCommandPath) 'dep_consent_banner.txt'
    }

    # Detect TTY.
    $isTty = [Environment]::UserInteractive -and -not [Console]::IsInputRedirected

    # Exit 93: incomplete flag pair (only one of two flags provided).
    if ($SkipDepCheck -xor $AcceptHallucRisk) {
        [Console]::Error.WriteLine("ERROR: incomplete override flag pair.")
        [Console]::Error.WriteLine("  --skip-dep-check and --accept-missing-deps-risk must be passed TOGETHER.")
        [Console]::Error.WriteLine("  Passing only one produces exit 93 (override-flag-pair-incomplete).")
        exit 93
    }

    # Load banner text (verbatim — single source of truth).
    $bannerText = $null
    if (Test-Path $BannerPath) {
        $bannerText = Get-Content -LiteralPath $BannerPath -Raw -Encoding UTF8
    } else {
        # Fallback inline banner (belt-and-suspenders if file is missing).
        $bannerText = @"
================================================================
WARNING — UNSAFE INSTALL REQUESTED

You are installing deep-research-claude WITHOUT one or more of
its dependency-chain prerequisites:

  <list of missing hard deps, one per line>

Without these, your install will run without a required dependency
that this contract version of deep-research-claude needs.
================================================================
"@
        [Console]::Error.WriteLine("WARNING: dep_consent_banner.txt not found at $BannerPath; using inline fallback.")
    }

    # Substitute the missing deps list placeholder.
    if ($MissingHardDeps.Count -gt 0) {
        $depList = ($MissingHardDeps | ForEach-Object { "  - $_" }) -join "`n"
        $bannerText = $bannerText -replace '  <list of missing hard deps, one per line>', $depList
    }

    # Emit banner.
    [Console]::Error.WriteLine($bannerText)

    if ($SkipDepCheck -and $AcceptHallucRisk) {
        # Both flags present: one-line ack, then proceed.
        [Console]::Error.WriteLine('[setup] Override flags accepted: --skip-dep-check --accept-missing-deps-risk. Proceeding without dep check.')
        return
    }

    # No flag pair.
    if (-not $isTty -or -not $Interactive) {
        # Non-TTY or non-interactive: hard fail.
        [Console]::Error.WriteLine("ERROR: hard dependency missing and no override flags provided.")
        [Console]::Error.WriteLine("  In non-interactive mode, pass --skip-dep-check --accept-missing-deps-risk to override.")
        [Console]::Error.WriteLine("  Or install missing deps first (see banner above).")
        exit 90
    }

    # TTY interactive: double-confirm.
    $confirm1 = Read-Host 'Do you accept the missing-dependency risk and wish to proceed? [y/N]'
    if ([string]::IsNullOrWhiteSpace($confirm1)) { $confirm1 = 'N' }
    if ($confirm1 -notmatch '^[Yy]$') {
        Write-Host '[setup] Aborted at first confirmation prompt.'
        exit 91
    }

    $confirm2 = Read-Host 'Specifically, do you accept that running without required deps may produce contract-violation outcomes? [y/N]'
    if ([string]::IsNullOrWhiteSpace($confirm2)) { $confirm2 = 'N' }
    if ($confirm2 -notmatch '^[Yy]$') {
        Write-Host '[setup] Aborted at second confirmation prompt (contract-violation risk).'
        exit 91
    }

    Write-Host '[setup] Double-confirmation accepted. Proceeding without full dep chain.'
}
