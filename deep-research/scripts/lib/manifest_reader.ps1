
# manifest_reader.ps1 — PowerShell JSON parser for the agent-install-manifest.
# Reads docs/install/agent-install-manifest.json and emits one NDJSON line per
# direct_dep to stdout. PowerShell parity with scripts/lib/manifest_reader.sh
# (bash sibling). Uses ConvertFrom-Json (native; no third-party modules).
# Spec backlink: docs/plans/2026-06-15-deep-research-install-chain-application-phase-b.md §7 C3
#
# Reader-widen note (2026-05-23 cross-repo agreement): this reader accepts contract versions
# {1, 2} via $knownAccepted. DR ships its manifest at v2; holodeck (DR's downstream
# chain-walker) already accepts {1, 2} per the coordinated reader-widen-first sequencing.
# Mirror the knownAccepted shape from claude-unreal-holodeck/scripts/lib/manifest_reader.ps1.
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

# Reader-widen: accept v1 and v2 during the coordinated 1->2 bump (v2 adds
# optional DirectDep.consumer_install_args; reader-widen-first sequencing per
# cross-repo agreement 2026-05-23-addon-reply-s4-consumer-install-args-coreview.md).
$knownAccepted = @(1, 2)
if ($manifest.agent_install_contract_version -notin $knownAccepted) {
    [Console]::Error.WriteLine("ERROR: manifest agent_install_contract_version=$($manifest.agent_install_contract_version); this reader accepts versions $($knownAccepted -join ',') only.")
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
