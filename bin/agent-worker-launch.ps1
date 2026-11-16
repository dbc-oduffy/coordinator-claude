# Run this script by path from the operator's existing PowerShell process.
# Python prepares branch/admission only; the native TUI is a direct child of PowerShell.
param(
    [Parameter(Mandatory=$true)][ValidateSet('codex','grok','agy')][string]$Agent,
    [string]$SessionId,
    [string]$Run,
    [string]$NativeExecutable,
    [switch]$AllowEngineRepo,
    [Parameter(ValueFromRemainingArguments=$true)][string[]]$CliArgs
)
$ErrorActionPreference = 'Stop'
$workerPython = Get-Command python -CommandType Application -ErrorAction Stop | Select-Object -First 1
$workerPrepare = Join-Path $PSScriptRoot 'agent-worker-launch.py'
$workerArgs = @($workerPrepare, $Agent, '--prepare-only')
if ($SessionId) { $workerArgs += @('--session-id', $SessionId) }
if ($Run) { $workerArgs += @('--run', $Run) }
if ($NativeExecutable) { $workerArgs += @('--native-executable', $NativeExecutable) }
if ($AllowEngineRepo) { $workerArgs += '--allow-engine-repo' }
if ($CliArgs) { $workerArgs += '--'; $workerArgs += $CliArgs }
$workerJson = & $workerPython.Source @workerArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$workerPlan = ($workerJson -join "`n") | ConvertFrom-Json
if (-not $workerPlan.argv -or [IO.Path]::GetExtension($workerPlan.argv[0]) -ine '.exe') {
    throw 'Worker plan must name a native executable.'
}
$workerPrevious = @{}
try {
    foreach ($entry in $workerPlan.environment.PSObject.Properties) {
        $workerPrevious[$entry.Name] = [Environment]::GetEnvironmentVariable($entry.Name, 'Process')
        [Environment]::SetEnvironmentVariable($entry.Name, [string]$entry.Value, 'Process')
    }
    $workerBinary = [string]$workerPlan.argv[0]
    $workerCliArgs = @($workerPlan.argv | Select-Object -Skip 1)
    & $workerBinary @workerCliArgs
    $workerExit = $LASTEXITCODE
} finally {
    foreach ($entry in $workerPrevious.GetEnumerator()) {
        [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value, 'Process')
    }
}
exit $workerExit
