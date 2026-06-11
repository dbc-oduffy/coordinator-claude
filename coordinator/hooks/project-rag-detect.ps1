# project-rag-detect.ps1 — SessionStart banner: generic project-RAG freshness
#
# Emits one of three banners to stdout (injected into Claude Code context):
#   fresh        — graph.db mtime >= HEAD commit time
#   stale (N)    — N commits behind HEAD
#   uninitialized — marker present but no graph.db found
#   (silent)     — no marker found, or holodeck context detected (let holodeck hook handle it)
#
# Kill-switch: set COORDINATOR_HOOK_PROJECT_RAG_DETECT_DISABLED=1 to disable
#
# Holodeck dedupe: if .holodeck/ directory or Saved/HolodeckProjectRag/ path is found
# walking up from cwd, this script exits silently — the holodeck-specific hook handles it.
#
# Generic project-RAG detection: looks for .project-rag/manifest.json walking up from cwd.

# --- Kill-switch ---
if ($env:COORDINATOR_HOOK_PROJECT_RAG_DETECT_DISABLED -eq "1") {
    exit 0
}

# --- Helper: walk up from a directory looking for a marker ---
function Find-MarkerUpward {
    param(
        [string]$StartDir,
        [string]$Marker,
        [int]$MaxLevels = 6
    )
    $dir = $StartDir
    for ($i = 0; $i -lt $MaxLevels; $i++) {
        $candidate = Join-Path $dir $Marker
        if (Test-Path $candidate) {
            return $candidate
        }
        $parent = Split-Path $dir -Parent
        if (-not $parent -or $parent -eq $dir) { break }
        $dir = $parent
    }
    return $null
}

$Cwd = (Get-Location).Path

# --- Holodeck dedupe: positive context detection ---
# If we're in a holodeck UE project, let the holodeck-specific hook handle the banner.
$HolodeckDir    = Find-MarkerUpward -StartDir $Cwd -Marker ".holodeck"
$HolodeckSaved  = Find-MarkerUpward -StartDir $Cwd -Marker "Saved\HolodeckProjectRag"
if ($HolodeckDir -or $HolodeckSaved) {
    # Holodeck context detected — exit silently, holodeck hook owns the banner
    exit 0
}

# --- Generic project-RAG detection via marker file ---
$ManifestPath = Find-MarkerUpward -StartDir $Cwd -Marker ".project-rag\manifest.json"
if (-not $ManifestPath) {
    # No project-RAG in this repo — silent exit (no banner pollution)
    exit 0
}

# Derive repo root from manifest path (.project-rag/ is at repo root)
$ProjectRagDir = Split-Path $ManifestPath -Parent
$RepoRoot = Split-Path $ProjectRagDir -Parent

# --- Locate graph.db ---
# Convention: .project-rag/graph.db alongside the manifest
$DbPath = Join-Path $ProjectRagDir "graph.db"

# --- Uninitialized branch ---
if (-not (Test-Path $DbPath)) {
    Write-Output "project-rag: UNINITIALIZED — marker found at $ManifestPath but no graph.db; run the project-RAG indexer before querying"
    exit 0
}

# --- Stat mtime ---
try {
    $DbMtime = (Get-Item $DbPath).LastWriteTime
}
catch {
    Write-Output "project-rag: SKIP — could not stat graph.db (fail open)"
    exit 0
}

$AgeDays = ((Get-Date) - $DbMtime).TotalDays

# --- Verify git is available ---
$git = Get-Command git -ErrorAction SilentlyContinue
if (-not $git) {
    Write-Output "project-rag: SKIP — git not found (fail open)"
    exit 0
}

# --- Find commit built against ---
$MtimeStr = $DbMtime.ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
try {
    $BuiltCommit = & git -C $RepoRoot log -1 "--before=$MtimeStr" --format="%H" 2>$null
    $BuiltCommit = $BuiltCommit.Trim()
}
catch {
    $BuiltCommit = ""
}

if (-not $BuiltCommit) {
    # mtime predates all commits or git failed — treat as uninitialized
    Write-Output "project-rag: UNINITIALIZED — graph.db predates git history; run the project-RAG indexer"
    exit 0
}

# --- Compute commit delta ---
try {
    $DeltaRaw = & git -C $RepoRoot rev-list "${BuiltCommit}..HEAD" --count 2>$null
    $Delta = [int]$DeltaRaw.Trim()
}
catch {
    Write-Output "project-rag: SKIP — git rev-list failed (fail open)"
    exit 0
}

# --- Emit banner ---
if ($Delta -eq 0) {
    Write-Output "project-rag: fresh (HEAD aligned)"
}
else {
    $BaseMsg = "project-rag: STALE — $Delta commits behind HEAD; project-RAG queries may miss recent changes"

    # Escalate to system-reminder block if N > 50 or age > 7 days
    if ($Delta -gt 50 -or $AgeDays -gt 7) {
        Write-Output "<system-reminder>"
        Write-Output $BaseMsg
        if ($Delta -gt 50) {
            Write-Output "  WARNING: $Delta commits — index is significantly out of date. Run the project-RAG indexer to rebuild."
        }
        if ($AgeDays -gt 7) {
            $AgeDaysRound = [math]::Round($AgeDays, 1)
            Write-Output "  WARNING: index is $AgeDaysRound days old. Run the project-RAG indexer to rebuild."
        }
        Write-Output "</system-reminder>"
    }
    else {
        Write-Output $BaseMsg
    }
}

exit 0
