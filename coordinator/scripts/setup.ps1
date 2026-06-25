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
#              [-Help] [-Version] [-Phase <name>] [-PhaseList] [-LastStatus] [-IAmAgent]
#
# Read-only flags (no install-status write): --help --version --phase-list --phase seed-install-spinoff --last-status --i-am-agent --check
#
# Exit codes:
#   0   success (DAG root — no deps to check; or all deps satisfied)
#   90  non-interactive/non-TTY dep missing, no override flag pair
#   91  user declined
#   92  agent-direct invocation without override flag pair
#   93  override flag pair incomplete (only one of two flags supplied)
#
# Env-prerequisite probes (clone_auth, longpaths, uv, ue, pwsh) are bash-only — run setup.sh --preflight for Step Zero env probes (see docs/wiki/coordinator-installer-shape.md § Windows platform — bash-only env-probe layer).
#
# Layout-agnostic repo_root resolution (mirrors setup.sh logic):
#   Flat layout (publish-repo):   scripts\ lives directly under repo root;
#                                 heuristic: ..\docs\install\AGENT.md exists.
#   Nested layout (working-repo): scripts\ lives under plugins\coordinator-claude\coordinator\;
#                                 heuristic: ..\coordinator\docs\install\AGENT.md exists.
#
# Spec backlink: docs/plans/2026-06-15-coordinator-install-chain-application-phase-b.md §7 C2
# Spec backlink: docs/plans/2026-06-17-coordinator-install-seed-phase-and-manifest-alignment.md §C3
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

    # ---------------------------------------------------------------------------
    # -Phase <name> vs -PhaseList prefix-collision resolution (C3 — AC5/AC5b).
    #
    # PowerShell resolves parameter binding using EXACT-MATCH-FIRST then
    # unique-prefix-match. "-Phase foo" is an exact match for [string]$Phase
    # (the name "Phase" == "Phase"), so it routes here and not to $PhaseList.
    # "-PhaseList" is an exact match for [switch]$PhaseList.
    # If a caller omits the value after -Phase (e.g. "-Phase" with no arg),
    # PowerShell will error because [string] is non-nullable without a default;
    # we default to [string]::Empty and handle that downstream.
    # The [Parameter()] attribute is present to anchor this comment and to ensure
    # no future positional-parameter re-numbering accidentally captures a value
    # intended for another param.
    # ---------------------------------------------------------------------------
    [Parameter()]
    [string]$Phase = '',                # read-only: dispatch named install phase; exit 0 on known, non-zero on unknown

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

# chain-preinstall is stateful-by-contract (NOT in the read-only carve-out): the -Phase
# switch sets this marker instead of exiting inline, so the post-parse agent/token gate
# decides exit 92 vs no-op body. Mirrors setup.sh _RUN_CHAIN_PREINSTALL.
# agent-install-contract.md § chain-preinstall phase.
$RunChainPreinstall = $false

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
# Read-only flags (no install-status write): --help --version --phase-list --phase seed-install-spinoff --last-status --i-am-agent --check
# ---------------------------------------------------------------------------

if ($Help) {
    Write-Host "Usage: pwsh -File scripts/setup.ps1 [OPTIONS]"
    Write-Host ""
    Write-Host "  -Help                    Print this help and exit."
    Write-Host "  -Version                 Print script version and exit."
    Write-Host "  -Phase <name>            Dispatch named install phase and exit."
    Write-Host "                           Read-only phases (no state written): seed-install-spinoff"
    Write-Host "                           Stateful phases (gated): chain-preinstall — pre-restart full-install"
    Write-Host "                             seam; requires `$env:COORDINATOR_CHAIN_PREINSTALL_CONSENT (or the override pair)"
    Write-Host "                             in agent mode; no-op body at the DAG root."
    Write-Host "                           Unknown phase values exit non-zero (fail-loud)."
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
    Write-Host "Available -Phase <name> values:"
    Write-Host "  seed-install-spinoff  DAG-root no-op (read-only, no state written)"
    Write-Host "  chain-preinstall      Pre-restart full-install seam (stateful-by-contract; gated by `$env:COORDINATOR_CHAIN_PREINSTALL_CONSENT in agent mode; no-op body at the DAG root)"
    Write-Host ""
    Write-Host "Informational (NOT -Phase <name> values):"
    Write-Host "  dep-check:  coordinator-claude is DAG root -- no upstream deps; chain-walk terminates here"
    exit 0
}

if ($LastStatus) {
    Write-Host '{"overall": "no-prior-install"}'
    exit 0
}

# ---------------------------------------------------------------------------
# -Phase <name> dispatch. Read-only phases (seed-install-spinoff) exit inline in the carve-out;
# stateful phases (chain-preinstall) set a deferred marker and fall through to the agent/token gate.
# Parity with setup.sh --phase <name>.
#
# Prefix-collision note: PowerShell resolves "-Phase foo" as an exact match for
# [string]$Phase (the name "Phase" == "Phase"), NOT as a prefix of [switch]$PhaseList.
# Exact matches always win over prefix matches in PowerShell parameter binding.
# "-PhaseList" (no value) binds exactly to [switch]$PhaseList.
# See param block comment above for full analysis.
# ---------------------------------------------------------------------------
if ($Phase -ne '') {
    # Review: code-reviewer — flag-shaped-value guard: PowerShell's [string]$Phase parameter
    # binding already prevents the "-Phase" with-no-value case at parse time (PowerShell
    # errors before reaching here). However, protect against a caller passing a flag-shaped
    # value like "-Phase --next-flag" which would silently land here as $Phase = '--next-flag'.
    if ($Phase -like '--*') {
        [Console]::Error.WriteLine("ERROR: -Phase requires a phase name, but got a flag-shaped value ('$Phase'). Did you forget the phase name?")
        exit 1
    }
    switch ($Phase) {
        'seed-install-spinoff' {
            # Decision-0 no-op: coordinator-claude is the DAG root (direct_deps: []).
            # The holodeck leaf-bootstrap invokes this phase to seed install batons.
            # Coordinator stitches + drives — it does NOT seed a leg baton for itself.
            # The coordinator's own install is the onboarding handoff, not a spinoff.
            # Downstream repos seed their own leg batons; coordinator's Step 0 sweep
            # discovers them post-reboot. Zero gap in the A→D chain.
            # Read-only carve-out (contract § Read-only flag carve-out): no state written.
            Write-Host "[setup] coordinator-claude is the DAG-root spine: no install-leg baton seeded."
            Write-Host "[setup] seed-install-spinoff: no-op (coordinator stitches + drives; downstream repos seed their own legs)."
            exit 0
        }
        'chain-preinstall' {
            # Stateful-by-contract phase — NOT an inline read-only exit like seed-install-spinoff.
            # Set the marker and DO NOT exit; the post-parse agent/token gate decides exit 92 vs
            # no-op body. Phase-level gate, uniform across legs. agent-install-contract.md § chain-preinstall.
            $RunChainPreinstall = $true
        }
        default {
            [Console]::Error.WriteLine("ERROR: Unknown -Phase value: '$Phase'")
            [Console]::Error.WriteLine("  Use -PhaseList to enumerate all known phase names.")
            exit 1
        }
    }
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
    } elseif ($RunChainPreinstall -and -not [string]::IsNullOrEmpty($env:COORDINATOR_CHAIN_PREINSTALL_CONSENT)) {
        # chain-preinstall phase inside a consented chain walk — fall through.
        # The consent token is the same trust altitude as the override pair (a deliberate
        # redirect-guard escape, not a capability token). agent-install-contract.md § chain-preinstall.
    } else {
        [Console]::Error.WriteLine("AGENT_MANIFEST_PATH=docs/install/AGENT.md")
        [Console]::Error.WriteLine("[setup] Agent-direct invocation detected. Use /coordinator:setup instead.")
        [Console]::Error.WriteLine("[setup] Agent install guide: docs/install/AGENT.md")
        if ($RunChainPreinstall) {
            [Console]::Error.WriteLine("[setup] -Phase chain-preinstall requires a consented chain walk:")
            [Console]::Error.WriteLine("[setup]   set `$env:COORDINATOR_CHAIN_PREINSTALL_CONSENT (the chain-walk token) -- or supply the override pair")
            [Console]::Error.WriteLine("[setup]   -IAmAgent -SkipDepCheck -AcceptMissingDepsRisk")
        } else {
            [Console]::Error.WriteLine("[setup] To run non-interactively, supply both:")
            [Console]::Error.WriteLine("[setup]   -IAmAgent -SkipDepCheck -AcceptMissingDepsRisk")
        }
        exit 92
    }
}

# ---------------------------------------------------------------------------
# chain-preinstall phase body (post-gate). Reached only when the agent/token
# gate above passed (or in non-agent mode). coordinator-claude is the DAG root
# with no script-install body, so chain-preinstall is a no-op here -- it still
# routes THROUGH the gate above (phase-level gate, uniform across legs), then
# exits 0. NOT in the read-only carve-out: stateful-by-contract.
# ---------------------------------------------------------------------------
if ($RunChainPreinstall) {
    Write-Host "coordinator-claude: DAG-root spine -- nothing to preinstall (chain-preinstall no-op body at the root; capability install happens at downstream heavy-install legs)."
    exit 0
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
# Resolve-CoManifestPath — layout-aware manifest resolution (mirrors the bash
# _co_resolve_manifest_path). The install surface ships in two layouts and the
# manifest lands in a DIFFERENT place in each, so callers MUST NOT assume a
# single fixed RepoRoot-relative location:
#   Nested working-tree / mirror layout:  <RepoRoot>\docs\install\...
#   Flat publish-repo-root layout:         <RepoRoot>\..\docs\install\...
#     (published there by the coordinator-claude-toplevel-install flat-mirror)
# Probes both, returns the first that exists (resolved absolute). Returns $null
# and prints remediation to stderr when neither exists.
# ---------------------------------------------------------------------------
function Resolve-CoManifestPath {
    param([Parameter(Mandatory)][string]$RepoRoot)
    # TrimEnd: Split-Path -Parent on a trailing-separator path strips the
    # separator rather than the last segment, yielding the wrong parent.
    $RepoRoot = $RepoRoot.TrimEnd('\','/')
    $rel    = 'docs\install\agent-install-manifest.json'
    $nested = Join-Path $RepoRoot $rel
    $flat   = Join-Path (Split-Path -Parent $RepoRoot) $rel
    # Resolve-Path THROWS on a missing path under $ErrorActionPreference='Stop';
    # -ErrorAction SilentlyContinue + the Test-Path gate keeps a TOCTOU race
    # (file vanishes between probe and resolve) from becoming a hard crash.
    if (Test-Path $nested) {
        $r = Resolve-Path -LiteralPath $nested -ErrorAction SilentlyContinue
        if ($r) { return $r.Path }
    }
    if (Test-Path $flat) {
        $r = Resolve-Path -LiteralPath $flat -ErrorAction SilentlyContinue
        if ($r) { return $r.Path }
    }
    [Console]::Error.WriteLine("ERROR: install manifest not found in either layout location:")
    [Console]::Error.WriteLine("  nested (working-tree/mirror): $nested")
    [Console]::Error.WriteLine("  flat   (publish-repo-root):   $flat")
    [Console]::Error.WriteLine("  Remediation: re-publish BOTH install-surface targets from the meta-repo --")
    [Console]::Error.WriteLine("    bash setup/publish.sh coordinator-claude-toplevel-install   # repo-root docs/install/")
    [Console]::Error.WriteLine("    bash setup/publish.sh coordinator-claude                    # coordinator/ mirror")
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
# Read-only flags (no install-status write): --help --version --phase-list --phase seed-install-spinoff --last-status --i-am-agent --check
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

    # Layout-aware resolution (nested working-tree vs flat publish-repo-root).
    # The resolver prints not-found remediation to stderr on failure.
    $ManifestPath = Resolve-CoManifestPath -RepoRoot $RepoRoot
    if (-not $ManifestPath) {
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
# Layout-aware resolution (nested working-tree vs flat publish-repo-root).
# $null is non-fatal for the DAG-root walker (no direct_deps to probe); the
# dep-probe calls below are guarded on a non-null path.
$ManifestPath = Resolve-CoManifestPath -RepoRoot $RepoRoot
if (-not $ManifestPath) {
    [Console]::Error.WriteLine("[setup] WARNING: proceeding without dep probe -- coordinator-claude is the DAG root (no direct_deps).")
}

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
if ($Phase -ne '')         { $ParsedArgsList.Add("--phase"); $ParsedArgsList.Add($Phase) }
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
    $ProbeResultsForConsent = @()
    if ($ManifestPath) {
        $ProbeResultsForConsent = Get-CoDepProbeAll `
            -ManifestPath $ManifestPath `
            -Python       $PythonBin `
            -SiblingRoot  $SiblingRoot
    }
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
$ProbeResults = @()
if ($ManifestPath) {
    $ProbeResults = Get-CoDepProbeAll `
        -ManifestPath $ManifestPath `
        -Python       $PythonBin `
        -SiblingRoot  $SiblingRoot
}

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
