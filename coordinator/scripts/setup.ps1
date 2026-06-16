# scripts/setup.ps1 — Standalone install-chain walker for coordinator-claude (Windows).
#
# 1:1 functional parity with scripts/setup.sh (POSIX bash sibling).
# Any logic present in setup.sh MUST be present here, and vice versa.
# sh+ps1 mirror constraint: docs/plans/2026-06-15-coordinator-install-chain-application-phase-b.md §7 C2
#
# Walks the install-chain DAG declared in docs/install/agent-install-manifest.json.
# coordinator-claude is DAG root (direct_deps: []); the walker terminates
# immediately after confirming the empty dep list with:
#   chain walk complete — coordinator-claude is DAG root
# and exits 0.
#
# coordinator-claude is chain step 5 of 5 in the install DAG:
#   holodeck → project-rag-ue-addon → project-rag → deep-research → coordinator-claude (DAG root)
#
# Usage: pwsh -File scripts/setup.ps1 [-Check] [-SkipDepCheck] [-AcceptMissingDepsRisk]
#              [-Help] [-Version] [-PhaseList] [-LastStatus] [-IAmAgent]
#
# Read-only flags (no install-status write): --help --version --phase-list --last-status --i-am-agent --check
#
# Exit codes:
#   0   success (DAG root — no deps to check; or all deps satisfied)
#   90  non-interactive/non-TTY dep missing, no override flag pair
#   91  user declined
#   92  agent-direct invocation without override flag pair
#   93  override flag pair incomplete (only one of two flags supplied)
#
# Layout-agnostic repo_root resolution (mirrors setup.sh logic):
#   Flat layout (publish-repo):   scripts\ lives directly under repo root;
#                                 heuristic: ..\docs\install\AGENT.md exists.
#   Nested layout (working-repo): scripts\ lives under plugins\coordinator-claude\coordinator\;
#                                 heuristic: ..\coordinator\docs\install\AGENT.md exists.
#
# Spec backlink: docs/plans/2026-06-15-coordinator-install-chain-application-phase-b.md §7 C2
# Spec backlink: plugins/coordinator-claude/coordinator/docs/wiki/agent-install-contract.md
#                § Read-only flag carve-out, § Severity semantics

[CmdletBinding()]
param(
    [switch]$Check,                     # read-only dep probe + status report; no state written
                                        # coord-specific read-only extension (contract § Read-only flag carve-out)
    [switch]$SkipDepCheck,              # override flag 1 of 2 (pair with -AcceptMissingDepsRisk)
    [switch]$AcceptMissingDepsRisk,     # override flag 2 of 2 (pair with -SkipDepCheck)
    [switch]$IAmAgent,                  # agent mode: exit 92 with AGENT_MANIFEST_PATH
    [switch]$IAmHuman,                  # human mode: skip agent-mode prompt, proceed directly
    [switch]$Help,                      # read-only: print usage and exit 0
    [switch]$Version,                   # read-only: print script version and exit 0
    [switch]$PhaseList,                 # read-only: list install phases and exit 0
    [switch]$LastStatus                 # read-only: print last install status JSON and exit 0
)

$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------------------
# Script metadata
# ---------------------------------------------------------------------------
$ScriptVersion = '1.0.0'
$ScriptName    = 'coordinator-claude setup'
$ChainStep     = 'chain step 5 of 5'
$ChainBanner   = "coordinator install-chain walker -- $ChainStep"

# ---------------------------------------------------------------------------
# Locate this script and resolve RepoRoot (layout-agnostic).
#
# Two supported layouts (mirrors setup.sh):
#   Flat (publish-repo):    <repo-root>\scripts\setup.ps1
#                           <repo-root>\docs\install\AGENT.md  <- heuristic marker
#   Nested (working-repo):  <wr-root>\plugins\coordinator-claude\coordinator\scripts\setup.ps1
#                           <wr-root>\plugins\coordinator-claude\coordinator\docs\install\AGENT.md <- heuristic marker
#
# DO NOT hardcode plugins\coordinator-claude\coordinator\ — that path does not
# exist in the flat publish-repo layout.
# ---------------------------------------------------------------------------
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

$FlatMarker   = Join-Path (Split-Path -Parent $ScriptDir) 'docs\install\AGENT.md'
$NestedMarker = Join-Path (Split-Path -Parent $ScriptDir) 'coordinator\docs\install\AGENT.md'

# F13: collapsed the flat/nested/fallback elseif/else — all three branches resolved to
# the same `Split-Path -Parent $ScriptDir` because scripts\ is always exactly one level
# below the coordinator/ tree root in both layouts. The probes only differentiate WHICH
# layout-marker exists, not the resulting path. A single assignment with an explanatory
# comment is equivalent and less confusing.
# Flat layout:   scripts/ is at <repo-root>/scripts/     → parent of scripts/ = <repo-root>
# Nested layout: scripts/ is at coordinator/scripts/     → parent of scripts/ = coordinator/
# Both cases:    parent of scripts/ is the correct repo root.
$RepoRoot = Split-Path -Parent $ScriptDir

# ---------------------------------------------------------------------------
# Source dep_check.ps1 and manifest_reader.ps1 from lib\.
# Functions are Co-prefixed (coordinator-claude exports — pinned from C3 lib exports):
#   Test-CoPhaseZeroShouldRun, Invoke-CoRunModePrompt, Test-CoDepProbe, Get-CoDepProbeAll,
#   Initialize-CoVisitedSet, Test-CoVisitedSet, Add-CoVisitedSet,
#   Invoke-CoVisitedSetCrashCleanup, Invoke-CoConsentGate
# ---------------------------------------------------------------------------
$LibDir = Join-Path $ScriptDir 'lib'

$DepCheckPs1     = Join-Path $LibDir 'dep_check.ps1'
$ManifestReadPs1 = Join-Path $LibDir 'manifest_reader.ps1'

if (-not (Test-Path $ManifestReadPs1)) {
    [Console]::Error.WriteLine("ERROR: Cannot find scripts\lib\manifest_reader.ps1.")
    exit 1
}

if (Test-Path $DepCheckPs1) {
    . $DepCheckPs1
} else {
    [Console]::Error.WriteLine("ERROR: Cannot find scripts\lib\dep_check.ps1.")
    [Console]::Error.WriteLine("  Run: git status to verify file presence.")
    exit 1
}

# ---------------------------------------------------------------------------
# Read-only flag short-circuits (no Phase 0 triggered, exit 0).
# Read-only flags (no install-status write): --help --version --phase-list --last-status --i-am-agent --check
# ---------------------------------------------------------------------------

if ($Help) {
    Write-Host "Usage: pwsh -File scripts\setup.ps1 [OPTIONS]"
    Write-Host ""
    Write-Host "  -Help                    Print this help and exit."
    Write-Host "  -Version                 Print script version and exit."
    Write-Host "  -PhaseList               List install phases and exit."
    Write-Host "  -LastStatus              Print last install status JSON and exit."
    Write-Host "  -Check                   Read-only dep probe + status report. No state written."
    Write-Host "                           coord-specific read-only extension (chain step 5 of 5)."
    Write-Host "  -SkipDepCheck            Skip dep-chain consent gate (pair with below)."
    Write-Host "  -AcceptMissingDepsRisk   Accept risk of proceeding with dep absent."
    Write-Host "                           Both flags required together; one alone exits 93."
    Write-Host ""
    Write-Host "Exit codes: 0=ok  90=non-TTY/missing-dep  91=user-declined"
    Write-Host "            92=agent-direct  93=incomplete-override-pair"
    exit 0
}

if ($Version) {
    Write-Host "$ScriptName version $ScriptVersion"
    exit 0
}

if ($PhaseList) {
    Write-Host "dep-check:  coordinator-claude is DAG root -- no upstream deps to probe"
    exit 0
}

if ($LastStatus) {
    Write-Host '{"overall": "no-prior-install"}'
    exit 0
}

# ---------------------------------------------------------------------------
# Override-flag pair integrity check.
# One flag without the other → exit 93.
# (Applies to install runs only; -Check is read-only and does not require the pair.)
# ---------------------------------------------------------------------------
if (-not $Check) {
    if ($SkipDepCheck -and -not $AcceptMissingDepsRisk) {
        [Console]::Error.WriteLine("ERROR: -SkipDepCheck requires -AcceptMissingDepsRisk (both flags required together).")
        exit 93
    }
    if ($AcceptMissingDepsRisk -and -not $SkipDepCheck) {
        [Console]::Error.WriteLine("ERROR: -AcceptMissingDepsRisk requires -SkipDepCheck (both flags required together).")
        exit 93
    }
}

# ---------------------------------------------------------------------------
# Agent-direct short-circuit.
# Fires before the dep-check gate. Exit 92 unless full override pair is present.
# ---------------------------------------------------------------------------
$CoordRunMode = $env:COORDINATOR_RUN_MODE

if ($IAmAgent -or $CoordRunMode -eq 'agent') {
    if ($SkipDepCheck -and $AcceptMissingDepsRisk) {
        # full override pair present — fall through
    } else {
        [Console]::Error.WriteLine("AGENT_MANIFEST_PATH=docs/install/AGENT.md")
        [Console]::Error.WriteLine("[setup] Agent-direct invocation detected. Use /coordinator:setup instead.")
        [Console]::Error.WriteLine("[setup] Agent install guide: docs/install/AGENT.md")
        [Console]::Error.WriteLine("[setup] To run non-interactively, supply both:")
        [Console]::Error.WriteLine("[setup]   -IAmAgent -SkipDepCheck -AcceptMissingDepsRisk")
        exit 92
    }
}

# ---------------------------------------------------------------------------
# Python resolver — required for manifest read and dep probing.
# ---------------------------------------------------------------------------
function Find-Python {
    if (Get-Command python3 -ErrorAction SilentlyContinue) { return 'python3' }
    if (Get-Command python  -ErrorAction SilentlyContinue) { return 'python' }
    return $null
}

# ---------------------------------------------------------------------------
# -Check mode: read-only dep probe.
#
# coordinator-claude is DAG root (direct_deps: []). The manifest probe loop
# emits zero lines; the walker terminates with the DAG-root message.
#
# MUST NOT write to install-status, manifest, or any persistent state.
# coord repo-specific read-only extension (contract § Read-only flag carve-out).
# Read-only flags (no install-status write): --help --version --phase-list --last-status --i-am-agent --check
# ---------------------------------------------------------------------------
if ($Check) {
    Write-Host "=========================================================="
    Write-Host "  $ChainBanner"
    Write-Host "=========================================================="
    Write-Host "  repo:         coordinator-claude"
    Write-Host "  repo_root:    $RepoRoot"
    Write-Host "  mode:         -Check (read-only, no state written)"
    Write-Host ""

    $PythonBin = Find-Python
    if (-not $PythonBin) {
        [Console]::Error.WriteLine("ERROR: no Python interpreter found on PATH (tried python3, python).")
        [Console]::Error.WriteLine("  Python 3.11+ is required to read the install manifest.")
        exit 1
    }

    $ManifestPath = Join-Path $RepoRoot 'docs\install\agent-install-manifest.json'
    if (-not (Test-Path $ManifestPath)) {
        [Console]::Error.WriteLine("WARNING: install manifest not found at $ManifestPath")
        [Console]::Error.WriteLine("  C1 (manifest + AGENT.md) must land before -Check can probe deps.")
        Write-Host ""
        Write-Host "  $ChainBanner`: no manifest to probe -- exiting 0 (check-only mode)."
        exit 0
    }

    # Read deps via manifest reader script (scripts\lib\manifest_reader.ps1).
    $NdjsonLines = $null
    try {
        if (Test-Path $ManifestReadPs1) {
            $NdjsonLines = & $ManifestReadPs1 -ManifestPath $ManifestPath
        } else {
            # Fallback: read manifest with Python directly (mirrors sh _co_manifest_read_ndjson body).
            $NdjsonLines = & $PythonBin -c @"
import json, sys, os
manifest_path = sys.argv[1]
if not os.path.isfile(manifest_path):
    print('ERROR: manifest not found: ' + manifest_path, file=sys.stderr)
    sys.exit(1)
try:
    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)
except json.JSONDecodeError as e:
    print('ERROR: manifest corrupt: ' + str(e), file=sys.stderr)
    sys.exit(1)
version = manifest.get('agent_install_contract_version')
if version not in (1, 2):
    print('ERROR: unrecognised contract version: ' + repr(version), file=sys.stderr)
    sys.exit(1)
for dep in manifest.get('direct_deps', []):
    probe = dep.get('functional_probe', {})
    probe_kind = probe.get('kind', '')
    probe_args = {k: probe[k] for k in ('path', 'expr', 'cmd') if k in probe}
    # F7: removed 'consumer_install_args' from fallback output. manifest_reader.sh:29
    # explicitly documents "Does NOT emit: consumer_install_args". The chain-walker reads
    # those directly from the upstream manifest at Steps 3 and 5.d — not from reader output.
    # Emitting it here creates a contract violation against the documented reader interface.
    out = {
        'id': dep.get('id', ''),
        'severity': dep.get('severity', ''),
        'sibling_dir_name': dep.get('sibling_dir_name', ''),
        'upstream_url': dep.get('upstream_url', ''),
        'functional_probe_kind': probe_kind,
        'functional_probe_args': probe_args,
    }
    print(json.dumps(out, ensure_ascii=True))
"@ $ManifestPath
        }
    } catch {
        [Console]::Error.WriteLine("ERROR: manifest unreadable or corrupt: $ManifestPath")
        exit 1
    }

    $AllSatisfied = $true
    $SiblingRoot  = Split-Path -Parent $RepoRoot
    $DepCount     = 0

    foreach ($DepLine in $NdjsonLines) {
        if ([string]::IsNullOrWhiteSpace($DepLine)) { continue }

        # Parse the NDJSON line natively.
        $DepObj = $null
        try { $DepObj = $DepLine | ConvertFrom-Json } catch { continue }

        $DepCount++
        $DepId       = $DepObj.id
        $DepSeverity = $DepObj.severity

        # Build probe args hashtable from functional_probe_args sub-object.
        $ProbeArgs = @{}
        if ($DepObj.functional_probe_args) {
            $DepObj.functional_probe_args.PSObject.Properties | ForEach-Object {
                $ProbeArgs[$_.Name] = $_.Value
            }
        }

        # Probe via Test-CoDepProbe (C3 authoritative signature — no fallback).
        # Parameters pinned to C3 dep_check.ps1 signature:
        #   -DepId, -SiblingDirName, -ProbeKind, -ProbeArgs, -SiblingRoot, -Python
        $DepStatus = Test-CoDepProbe `
            -DepId          $DepId `
            -SiblingDirName $DepObj.sibling_dir_name `
            -ProbeKind      $DepObj.functional_probe_kind `
            -ProbeArgs      $ProbeArgs `
            -SiblingRoot    $SiblingRoot `
            -Python         $PythonBin

        switch ($DepStatus) {
            'present' {
                Write-Host "  [$DepId] dep satisfied -- present v"
            }
            'present-but-broken' {
                [Console]::Error.WriteLine("  [$DepId] dep found but functional probe failed")
                if ($DepSeverity -eq 'soft') {
                    [Console]::Error.WriteLine("  WARNING: soft dep $DepId present-but-broken -- continuing (warn-and-continue).")
                    [Console]::Error.WriteLine("    Override: re-run with -SkipDepCheck -AcceptMissingDepsRisk to suppress.")
                    $AllSatisfied = $false
                }
            }
            'missing' {
                if ($DepSeverity -eq 'soft') {
                    [Console]::Error.WriteLine("")
                    [Console]::Error.WriteLine("  WARNING: soft dep [$DepId] is absent (missing).")
                    [Console]::Error.WriteLine("  To suppress this warning and accept the missing dep:")
                    [Console]::Error.WriteLine("    pwsh -File scripts\setup.ps1 -SkipDepCheck -AcceptMissingDepsRisk")
                    [Console]::Error.WriteLine("  Or (bash): bash scripts/setup.sh --skip-dep-check --accept-missing-deps-risk")
                    [Console]::Error.WriteLine("")
                    $AllSatisfied = $false
                } else {
                    [Console]::Error.WriteLine("ERROR: hard dep [$DepId] is missing.")
                    exit 90
                }
            }
        }
    }

    Write-Host ""
    # DAG-root termination: coordinator-claude has no direct_deps.
    if ($DepCount -eq 0) {
        Write-Host "chain walk complete -- coordinator-claude is DAG root"
    } elseif ($AllSatisfied) {
        Write-Host "  $ChainBanner`: all deps satisfied."
    } else {
        Write-Host "  $ChainBanner`: soft dep(s) absent -- proceeding (soft dep warn-and-continue)."
    }
    Write-Host "=========================================================="
    exit 0
}

# ---------------------------------------------------------------------------
# Full install body (non-Check mode).
#
# coordinator-claude is DAG root (direct_deps: []). The only install step is
# confirming the empty dep list and emitting the DAG-root termination message.
# ---------------------------------------------------------------------------
Write-Host "=========================================================="
Write-Host "  $ChainBanner"
Write-Host "=========================================================="
Write-Host "  repo:      coordinator-claude"
Write-Host "  repo_root: $RepoRoot"
Write-Host ""

# Python pre-flight (required for manifest read).
$PythonBin = Find-Python
if (-not $PythonBin) {
    [Console]::Error.WriteLine("ERROR: no Python interpreter found on PATH (tried python3, python).")
    exit 1
}

# Resolve manifest path and sibling root before Phase 0 consent gate, so that
# F12's Get-CoDepProbeAll call (inside the if-ShouldRunPhaseZero block) can use them.
# These are also used by the dep-probe loop later in the full install body.
$SiblingRoot  = Split-Path -Parent $RepoRoot
$ManifestPath = Join-Path $RepoRoot 'docs\install\agent-install-manifest.json'

# Phase 0: collect parsed CLI flags as string array so Test-CoPhaseZeroShouldRun
# can check for read-only flags.  The read-only flags have already been handled
# above (they exit early), but passing the live flag set keeps parity with
# the bash _co_phase_zero_should_run convention.
$ParsedArgsList = [System.Collections.Generic.List[string]]::new()
if ($Check)                { $ParsedArgsList.Add('--check') }
if ($SkipDepCheck)         { $ParsedArgsList.Add('--skip-dep-check') }
if ($AcceptMissingDepsRisk){ $ParsedArgsList.Add('--accept-missing-deps-risk') }
if ($IAmAgent)             { $ParsedArgsList.Add('--i-am-agent') }
if ($Help)                 { $ParsedArgsList.Add('--help') }
if ($Version)              { $ParsedArgsList.Add('--version') }
if ($PhaseList)            { $ParsedArgsList.Add('--phase-list') }
if ($LastStatus)           { $ParsedArgsList.Add('--last-status') }

# Parameters pinned to C3 dep_check.ps1 Test-CoPhaseZeroShouldRun signature:
#   -ParsedArgs [string[]]
# F6: test whether Phase 0 should run BEFORE calling Invoke-CoRunModePrompt, mirroring
# setup.sh order (bash calls _co_phase_zero_should_run first, then _co_run_mode_prompt
# only when it returns 0). Previously Invoke-CoRunModePrompt was called unconditionally
# before Test-CoPhaseZeroShouldRun, which emitted the agent-mode prompt even when a
# read-only flag (--check, --help, etc.) should have short-circuited before Phase 0.
$ShouldRunPhaseZero = Test-CoPhaseZeroShouldRun -ParsedArgs $ParsedArgsList.ToArray()

if ($ShouldRunPhaseZero) {
    # Phase 0: agent-mode detection (mirrors setup.sh _co_run_mode_prompt).
    # Parameters pinned to C3 dep_check.ps1 Invoke-CoRunModePrompt signature:
    #   -IAmAgent [bool], -IAmHuman [bool], -Interactive [bool]
    # F6: -IAmHuman now passes $IAmHuman.IsPresent (not hardcoded $false) so that
    # a future -IAmHuman switch maps through correctly, matching setup.sh I_AM_HUMAN logic.
    Invoke-CoRunModePrompt -IAmAgent $IAmAgent.IsPresent -IAmHuman $IAmHuman.IsPresent -Interactive $false

    # Phase 0: consent gate.
    # F12: compute missing hard deps via Get-CoDepProbeAll before calling Invoke-CoConsentGate,
    # mirroring bash _co_consent_gate which builds _missing_hard[] from _co_dep_probe_all.
    # Previously -MissingHardDeps was omitted entirely, so the banner always showed the raw
    # placeholder text instead of the actual missing dep list.
    $MissingHardDepIds = [System.Collections.Generic.List[string]]::new()
    $ProbeResultsForConsent = Get-CoDepProbeAll `
        -ManifestPath $ManifestPath `
        -Python       $PythonBin `
        -SiblingRoot  $SiblingRoot
    foreach ($pLine in $ProbeResultsForConsent) {
        if ([string]::IsNullOrWhiteSpace($pLine)) { continue }
        $pObj = $null
        try { $pObj = $pLine | ConvertFrom-Json } catch { continue }
        if ($pObj.severity -eq 'hard' -and ($pObj.status -eq 'missing' -or $pObj.status -eq 'present-but-broken')) {
            $MissingHardDepIds.Add("$($pObj.id) [$($pObj.status)]")
        }
    }

    # Parameters pinned to C3 dep_check.ps1 Invoke-CoConsentGate signature:
    #   -MissingHardDeps [string[]], -SkipDepCheck [bool], -AcceptMissingDepsRisk [bool],
    #   -Interactive [bool], -BannerPath [string]
    # F16: PS param renamed to -AcceptMissingDepsRisk (was -AcceptHallucRisk, stale name);
    # now matches the CLI flag --accept-missing-deps-risk and bash ACCEPT_MISSING_DEPS_RISK.
    Invoke-CoConsentGate `
        -MissingHardDeps       $MissingHardDepIds.ToArray() `
        -SkipDepCheck          $SkipDepCheck.IsPresent `
        -AcceptMissingDepsRisk $AcceptMissingDepsRisk.IsPresent `
        -Interactive           $false
}

# Probe all deps and report status (coordinator-claude is DAG root; direct_deps is []).
Write-Host "[setup] Probing direct deps..."

# Parameters pinned to C3 dep_check.ps1 Get-CoDepProbeAll signature:
#   -ManifestPath [string], -Python [string], -SiblingRoot [string]
# (F12: $SiblingRoot and $ManifestPath already assigned above Phase 0 block — no re-assign needed.)
$ProbeResults = Get-CoDepProbeAll `
    -ManifestPath $ManifestPath `
    -Python       $PythonBin `
    -SiblingRoot  $SiblingRoot

$DepCount = 0

foreach ($ProbeResult in $ProbeResults) {
    if ([string]::IsNullOrWhiteSpace($ProbeResult)) { continue }

    # Get-CoDepProbeAll emits PS hashtable | ConvertTo-Json; parse natively.
    $ProbeObj = $null
    try { $ProbeObj = $ProbeResult | ConvertFrom-Json } catch { continue }

    $DepCount++
    $DepId       = $ProbeObj.id
    $DepSeverity = $ProbeObj.severity
    $DepStatus   = $ProbeObj.status
    $DepHint     = $ProbeObj.hint

    switch ($DepStatus) {
        'present' {
            Write-Host "[setup] dep [$DepId] ($DepSeverity): dep satisfied -- present v"
        }
        { $_ -in @('present-but-broken', 'missing') } {
            if ($DepSeverity -eq 'soft') {
                [Console]::Error.WriteLine("")
                [Console]::Error.WriteLine("WARNING: soft dep [$DepId] is $DepStatus.")
                if ($DepHint) { [Console]::Error.WriteLine("  Hint: $DepHint") }
                [Console]::Error.WriteLine("  Override: re-run with -SkipDepCheck -AcceptMissingDepsRisk to suppress.")
                [Console]::Error.WriteLine("")
            } else {
                [Console]::Error.WriteLine("ERROR: hard dep [$DepId] is $DepStatus.")
                exit 90
            }
        }
    }
}

Write-Host ""
# DAG-root termination: coordinator-claude has no direct_deps.
if ($DepCount -eq 0) {
    Write-Host "chain walk complete -- coordinator-claude is DAG root"
} else {
    Write-Host "[setup] $ChainBanner`: complete."
}
Write-Host "  coordinator-claude has no Python/binary install phases."
Write-Host "  Use /coordinator:setup to run the full chain-walker via the skill."
Write-Host "=========================================================="
exit 0
