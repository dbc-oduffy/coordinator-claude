
# manifest_reader.ps1 — PowerShell JSON parser for the agent-install-manifest.
# Reads docs/install/agent-install-manifest.json and emits one NDJSON line per
# direct_dep to stdout. Uses ConvertFrom-Json (native; no third-party modules).
# PS-parity note: the bash sibling reader is the VENDORED coordinator SSOT at
#   scripts/lib/coordinator_prereq/manifest_reader.sh (the old scripts/lib/manifest_reader.sh
#   _dr_ fork was deleted in the 2026-06-23 install-parity reconcile). This PS reader
#   (manifest_reader.ps1) does not resolve Python — it uses ConvertFrom-Json natively.
#   Python resolution for PS installs lives in setup.ps1 Find-Python and dep_check.ps1
#   python_import branch, both of which adopted the Store-stub-hardened functional probe +
#   py launcher fallback on 2026-06-23, achieving parity with coordinator's _co_find_python.
#   See docs/plans/2026-06-23-deep-research-install-parity-with-coordinator.md §8.
# Spec backlink: docs/plans/2026-06-15-deep-research-install-chain-application-phase-b.md §7 C3
#
# Reader-widen note: this reader accepts contract versions {1, 2, 3} via $knownAccepted.
# Widened 2026-06-23 in the fleet-wide simultaneous-merge cutover; DR reads coordinator's
# v3 manifest (DR's own manifest stays v2). No reader-widen-first round-trip.
#
# Output fields per line (JSON object):
#   id, severity, sibling_dir_name, upstream_url,
#   functional_probe_kind, functional_probe_args
#
# Does NOT emit: override_flags (top-level), consumer_install_args (per-dep, v2+)
# — the chain-walker reads those directly from the upstream manifest at Steps 3 and 5.d.
# Callers must not assume a complete dep record from this reader's output.
#
# Exit codes:
#   0  — success; one NDJSON line per dep on stdout
#   1  — manifest file not found or unreadable
#   2  — manifest parse error (corrupt JSON)
#   3  — manifest missing required fields (schema violation)

[CmdletBinding()]
param(
    [string]$ManifestPath = ""
)

# Locate manifest relative to repo root (this script lives at scripts/lib/).
if (-not $ManifestPath) {
    $ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
    $RepoRoot    = Split-Path -Parent (Split-Path -Parent $ScriptDir)
    $ManifestPath = Join-Path $RepoRoot 'docs\install\agent-install-manifest.json'
}

if (-not (Test-Path $ManifestPath)) {
    [Console]::Error.WriteLine("ERROR: manifest not found at $ManifestPath")
    [Console]::Error.WriteLine("  Verify docs/install/agent-install-manifest.json exists (complete checkout required).")
    exit 1
}

$rawJson = $null
try {
    $rawJson = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8
} catch {
    [Console]::Error.WriteLine("ERROR: cannot read manifest at $ManifestPath : $_")
    exit 1
}

$manifest = $null
try {
    $manifest = $rawJson | ConvertFrom-Json
} catch {
    [Console]::Error.WriteLine("ERROR: manifest at $ManifestPath is not valid JSON: $_")
    exit 2
}

# Minimal required-field validation (stdlib-only; jsonschema is test-time only).
$requiredTopLevel = @('agent_install_contract_version', 'repo_id', 'direct_deps')
foreach ($field in $requiredTopLevel) {
    if ($null -eq $manifest.$field) {
        [Console]::Error.WriteLine("ERROR: manifest missing required field '$field' — manifest may be corrupt.")
        exit 3
    }
}

# Reader-widen: accept v1, v2, and v3. v2 added optional DirectDep.consumer_install_args;
# v3 added the optional system_prerequisites array (coordinator root, 2026-06-23). DR reads
# coordinator's manifest during chain-walk, so DR's reader must accept coordinator's v3.
# Widened in the fleet-wide simultaneous-merge cutover (no reader-widen-first round-trip).
$knownAccepted = @(1, 2, 3)
if ($manifest.agent_install_contract_version -notin $knownAccepted) {
    [Console]::Error.WriteLine("ERROR: manifest agent_install_contract_version=$($manifest.agent_install_contract_version); this reader accepts versions $($knownAccepted -join ', ') only.")
    [Console]::Error.WriteLine("  Upgrade deep-research-claude to a version that supports contract version $($manifest.agent_install_contract_version).")
    exit 3
}

foreach ($dep in $manifest.direct_deps) {
    # Extract functional probe fields for NDJSON output.
    $probeKind = $dep.functional_probe.kind
    # functional_probe_args: kind-specific additional fields as a JSON sub-object.
    $probeArgs = [ordered]@{}
    switch ($probeKind) {
        'file_exists'       { $probeArgs['path'] = $dep.functional_probe.path }
        'python_import'     { $probeArgs['expr'] = $dep.functional_probe.expr }
        'command_succeeds'  { $probeArgs['cmd']  = $dep.functional_probe.cmd  }
        'sibling_dir_exists' { <# no extra args #> }
    }

    $line = [ordered]@{
        id                   = $dep.id
        severity             = $dep.severity
        sibling_dir_name     = $dep.sibling_dir_name
        upstream_url         = $dep.upstream_url
        functional_probe_kind = $probeKind
        functional_probe_args = $probeArgs
    }
    # ConvertTo-Json -Compress emits a single line per object (NDJSON).
    $line | ConvertTo-Json -Compress -Depth 5
}
