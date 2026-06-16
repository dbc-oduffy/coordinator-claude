# scripts/setup.ps1 — Standalone install-chain walker for deep-research-claude (Windows).
#
# 1:1 functional parity with scripts/setup.sh (POSIX bash sibling).
# Any logic present in setup.sh MUST be present here, and vice versa.
# sh+ps1 mirror constraint: docs/plans/2026-06-15-deep-research-install-chain-application-phase-b.md §7 C2
#
# Walks the install-chain DAG declared in docs/install/agent-install-manifest.json,
# checks the single soft dep (coordinator-claude), and reports status.
#
# deep-research is chain step 4 of 5 in the install DAG:
#   holodeck → project-rag-ue-addon → project-rag → deep-research → coordinator-claude (soft)
#
# Usage: pwsh -File scripts/setup.ps1 [-Check] [-SkipDepCheck] [-AcceptMissingDepsRisk]
#              [-Help] [-Version] [-PhaseList] [-LastStatus] [-IAmAgent]
#
# Read-only flags (no install-status write): --help --version --phase-list --last-status --i-am-agent --check
#
# Exit codes:
#   0   success (all deps satisfied, or soft deps absent with override accepted)
#   90  non-interactive/non-TTY dep missing, no override flag pair
#   91  user declined
#   92  agent-direct invocation without override flag pair
#   93  override flag pair incomplete (only one of two flags supplied)
#
# Layout-agnostic repo_root resolution (mirrors setup.sh logic):
#   Flat layout (publish-repo):   scripts/ lives directly under repo root;
#                                 heuristic: ..\docs\install\AGENT.md exists.
#   Nested layout (working-repo): scripts/ lives under plugins\coordinator-claude\deep-research\;
#                                 heuristic: ..\..\coordinator-claude\coordinator\CLAUDE.md exists.
#
# Spec backlink: docs/plans/2026-06-15-deep-research-install-chain-application-phase-b.md §7 C2
# Spec backlink: plugins/coordinator-claude/coordinator/docs/wiki/agent-install-contract.md
#                § Read-only flag carve-out, § Severity semantics

[CmdletBinding()]
param(
    [switch]$Check,                     # read-only dep probe + status report; no state written
                                        # DR-specific read-only extension (contract § Read-only flag carve-out)
    [switch]$SkipDepCheck,              # override flag 1 of 2 (pair with -AcceptMissingDepsRisk)
    [switch]$AcceptMissingDepsRisk,     # override flag 2 of 2 (pair with -SkipDepCheck)
    [switch]$IAmAgent,                  # agent mode: exit 92 with AGENT_MANIFEST_PATH
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
$ScriptName    = 'deep-research-claude setup'
$ChainStep     = 'chain step 4 of 5'
$ChainBanner   = "DR install-chain walker -- $ChainStep"

# ---------------------------------------------------------------------------
# Locate this script and resolve RepoRoot (layout-agnostic).
#
# Two supported layouts (mirrors setup.sh):
#   Flat (publish-repo):    <repo-root>\scripts\setup.ps1
#                           <repo-root>\docs\install\AGENT.md  <- heuristic marker
#   Nested (working-repo):  <wr-root>\plugins\coordinator-claude\deep-research\scripts\setup.ps1
#                           <wr-root>\plugins\coordinator-claude\coordinator\CLAUDE.md <- heuristic marker
#
# DO NOT hardcode plugins\coordinator-claude\deep-research\ — that path does not
# exist in the flat publish-repo layout.
# ---------------------------------------------------------------------------
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

$FlatMarker   = Join-Path (Split-Path -Parent $ScriptDir) 'docs\install\AGENT.md'
$NestedMarker = Join-Path (Split-Path -Parent (Split-Path -Parent $ScriptDir)) 'coordinator-claude\coordinator\CLAUDE.md'

if (Test-Path $FlatMarker) {
    # Flat layout: repo root is parent of scripts\
    $RepoRoot = Split-Path -Parent $ScriptDir
} elseif (Test-Path $NestedMarker) {
    # Nested layout: repo root is the deep-research\ tree root
    $RepoRoot = Split-Path -Parent $ScriptDir
} else {
    # Neither marker found — fall back to scripts\..\
    $RepoRoot = Split-Path -Parent $ScriptDir
}

# ---------------------------------------------------------------------------
# Source dep_check.ps1 and manifest_reader.ps1 from lib\.
# These helpers are provided by C3 (template-copied from project-rag-ue-addon).
# Function signatures pinned from project_rag_ue_addon_scripts\lib\ precedent.
# ---------------------------------------------------------------------------
$LibDir = Join-Path $ScriptDir 'lib'

$DepCheckPs1    = Join-Path $LibDir 'dep_check.ps1'
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
    Write-Host "                           DR-specific read-only extension (chain step 4 of 5)."
    Write-Host "  -SkipDepCheck            Skip dep-chain consent gate (pair with below)."
    Write-Host "  -AcceptMissingDepsRisk   Accept risk of proceeding with soft dep absent."
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
    Write-Host "dep-check:  probe coordinator-claude soft dep and report status"
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
$AddonRunMode = $env:ADDON_RUN_MODE

if ($IAmAgent -or $AddonRunMode -eq 'agent') {
    if ($SkipDepCheck -and $AcceptMissingDepsRisk) {
        # full override pair present — fall through
    } else {
        [Console]::Error.WriteLine("AGENT_MANIFEST_PATH=docs/install/AGENT.md")
        [Console]::Error.WriteLine("[setup] Agent-direct invocation detected. Use /deep-research:setup instead.")
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
# Probe each direct_dep in the manifest and report:
#   present    → acknowledge-and-continue
#   missing    → soft: warn-and-offer-override + continue
#
# MUST NOT write to install-status, manifest, or any persistent state.
# DR repo-specific read-only extension (contract § Read-only flag carve-out).
# Read-only flags (no install-status write): --help --version --phase-list --last-status --i-am-agent --check
# ---------------------------------------------------------------------------
if ($Check) {
    Write-Host "=========================================================="
    Write-Host "  $ChainBanner"
    Write-Host "=========================================================="
    Write-Host "  repo:         deep-research-claude"
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

    # Read deps via manifest reader script (scripts\lib\manifest_reader.ps1 — parity with _dr_manifest_read_ndjson in .sh).
    $NdjsonLines = $null
    try {
        if (Test-Path $ManifestReadPs1) {
            $NdjsonLines = & $ManifestReadPs1 -ManifestPath $ManifestPath
        } else {
            # Fallback: read manifest with Python directly (mirrors sh _dr_manifest_read_ndjson body).
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
    out = {
        'id': dep.get('id', ''),
        'severity': dep.get('severity', ''),
        'sibling_dir_name': dep.get('sibling_dir_name', ''),
        'upstream_url': dep.get('upstream_url', ''),
        'functional_probe_kind': probe_kind,
        'functional_probe_args': probe_args,
        'consumer_install_args': dep.get('consumer_install_args', []),
    }
    print(json.dumps(out, ensure_ascii=True))
"@ $ManifestPath
        }
    } catch {
        [Console]::Error.WriteLine("ERROR: manifest unreadable or corrupt: $ManifestPath")
        exit 1
    }

    $AllSatisfied = $true
    $SiblingRoot = Split-Path -Parent $RepoRoot

    foreach ($DepLine in $NdjsonLines) {
        if ([string]::IsNullOrWhiteSpace($DepLine)) { continue }

        # Parse the NDJSON line natively (manifest_reader.ps1 emits PS-compatible JSON).
        $DepObj = $null
        try { $DepObj = $DepLine | ConvertFrom-Json } catch { continue }

        $DepId       = $DepObj.id
        $DepSeverity = $DepObj.severity

        # Build probe args hashtable from functional_probe_args sub-object.
        $ProbeArgs = @{}
        if ($DepObj.functional_probe_args) {
            $DepObj.functional_probe_args.PSObject.Properties | ForEach-Object {
                $ProbeArgs[$_.Name] = $_.Value
            }
        }

        # Probe via Test-DrDepProbe (C3 authoritative signature — no fallback).
        # Parameters pinned to C3 dep_check.ps1 signature:
        #   -DepId, -SiblingDirName, -ProbeKind, -ProbeArgs, -SiblingRoot, -Python
        $DepStatus = Test-DrDepProbe `
            -DepId          $DepId `
            -SiblingDirName $DepObj.sibling_dir_name `
            -ProbeKind      $DepObj.functional_probe_kind `
            -ProbeArgs      $ProbeArgs `
            -SiblingRoot    $SiblingRoot `
            -Python         $PythonBin

        switch ($DepStatus) {
            'present' {
                Write-Host "  [$DepId] coordinator dep satisfied -- present v"
            }
            'present-but-broken' {
                [Console]::Error.WriteLine("  [$DepId] coordinator dep found but functional probe failed")
                if ($DepSeverity -eq 'soft') {
                    [Console]::Error.WriteLine("  WARNING: soft dep $DepId present-but-broken -- continuing (warn-and-continue).")
                    [Console]::Error.WriteLine("    Override: re-run with -SkipDepCheck -AcceptMissingDepsRisk to suppress.")
                    $AllSatisfied = $false
                }
            }
            'missing' {
                if ($DepSeverity -eq 'soft') {
                    # Soft dep absent: warn loudly + offer override + continue.
                    # AC8 assertion: stderr must contain a warning AND --accept-missing-deps-risk.
                    [Console]::Error.WriteLine("")
                    [Console]::Error.WriteLine("  WARNING: soft dep [$DepId] is absent (missing).")
                    [Console]::Error.WriteLine("  deep-research works without coordinator-claude installed, but chain-walk")
                    [Console]::Error.WriteLine("  functionality is reduced.")
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
    if ($AllSatisfied) {
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
# DR is a pure-coordinator-plugin — no Python deps, no binary installs, no
# Playwright, no libclang. The only install step is the dep-chain walk.
# ---------------------------------------------------------------------------
Write-Host "=========================================================="
Write-Host "  $ChainBanner"
Write-Host "=========================================================="
Write-Host "  repo:      deep-research-claude"
Write-Host "  repo_root: $RepoRoot"
Write-Host ""

# Python pre-flight (required for manifest read).
$PythonBin = Find-Python
if (-not $PythonBin) {
    [Console]::Error.WriteLine("ERROR: no Python interpreter found on PATH (tried python3, python).")
    exit 1
}

# Phase 0: agent-mode detection (mirrors setup.sh).
# Parameters pinned to C3 dep_check.ps1 Invoke-DrRunModePrompt signature:
#   -IAmAgent [bool], -IAmHuman [bool], -Interactive [bool]
Invoke-DrRunModePrompt -IAmAgent $IAmAgent.IsPresent -IAmHuman $false -Interactive $false

# Phase 0: consent gate (mirrors setup.sh).
# Collect the parsed CLI flags as a string array so Test-DrPhaseZeroShouldRun
# can check for read-only flags.  The read-only flags have already been handled
# above (they exit early), but passing the live flag set keeps parity with
# the bash _dr_phase_zero_should_run convention.
$ParsedArgsList = [System.Collections.Generic.List[string]]::new()
if ($Check)                { $ParsedArgsList.Add('--check') }
if ($SkipDepCheck)         { $ParsedArgsList.Add('--skip-dep-check') }
if ($AcceptMissingDepsRisk){ $ParsedArgsList.Add('--accept-missing-deps-risk') }
if ($IAmAgent)             { $ParsedArgsList.Add('--i-am-agent') }
if ($Help)                 { $ParsedArgsList.Add('--help') }
if ($Version)              { $ParsedArgsList.Add('--version') }
if ($PhaseList)            { $ParsedArgsList.Add('--phase-list') }
if ($LastStatus)           { $ParsedArgsList.Add('--last-status') }

# Parameters pinned to C3 dep_check.ps1 Test-DrPhaseZeroShouldRun signature:
#   -ParsedArgs [string[]]
$ShouldRunPhaseZero = Test-DrPhaseZeroShouldRun -ParsedArgs $ParsedArgsList.ToArray()

if ($ShouldRunPhaseZero) {
    # Parameters pinned to C3 dep_check.ps1 Invoke-DrConsentGate signature:
    #   -SkipDepCheck [bool], -AcceptHallucRisk [bool], -Interactive [bool], -BannerPath [string]
    # Note: the PS param is -AcceptHallucRisk (matches bash $AcceptHallucRisk / _accept_risk);
    # the CLI flag is --accept-missing-deps-risk (DR vestigial-path naming per §7 C3 override-flag convention).
    Invoke-DrConsentGate `
        -SkipDepCheck     $SkipDepCheck.IsPresent `
        -AcceptHallucRisk $AcceptMissingDepsRisk.IsPresent `
        -Interactive      $false
}

# Probe all deps and report status.
Write-Host "[setup] Probing direct deps..."

# Parameters pinned to C3 dep_check.ps1 Get-DrDepProbeAll signature:
#   -ManifestPath [string], -Python [string], -SiblingRoot [string]
$SiblingRoot  = Split-Path -Parent $RepoRoot
$ManifestPath = Join-Path $RepoRoot 'docs\install\agent-install-manifest.json'

$ProbeResults = Get-DrDepProbeAll `
    -ManifestPath $ManifestPath `
    -Python       $PythonBin `
    -SiblingRoot  $SiblingRoot

foreach ($ProbeResult in $ProbeResults) {
    if ([string]::IsNullOrWhiteSpace($ProbeResult)) { continue }

    # Get-DrDepProbeAll emits PS hashtable | ConvertTo-Json; parse natively.
    $ProbeObj = $null
    try { $ProbeObj = $ProbeResult | ConvertFrom-Json } catch { continue }

    $DepId       = $ProbeObj.id
    $DepSeverity = $ProbeObj.severity
    $DepStatus   = $ProbeObj.status
    $DepHint     = $ProbeObj.hint

    switch ($DepStatus) {
        'present' {
            Write-Host "[setup] dep [$DepId] ($DepSeverity): coordinator dep satisfied -- present v"
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
Write-Host "[setup] $ChainBanner`: complete."
Write-Host "  deep-research-claude has no Python/binary install phases."
Write-Host "  Use /deep-research:setup to run the full chain-walker via the skill."
Write-Host "=========================================================="
exit 0
