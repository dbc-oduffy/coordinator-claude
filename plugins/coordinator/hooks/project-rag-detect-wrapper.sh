#!/usr/bin/env bash
# project-rag-detect-wrapper.sh — Cross-platform launcher for project-rag-detect.
#
# On Windows (pwsh available): delegates to project-rag-detect.ps1 via pwsh.
# Falls through to project-rag-detect.sh on any pwsh failure (missing OR ps1 error).
#
# Review: Patrik — restored OR-fallback semantics (pwsh present-but-failing now falls
# through to bash), added -WindowStyle Hidden to suppress console flash on Windows,
# and added set -eu/-o pipefail so SCRIPT_DIR resolution failures are loud.

set -eu -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if command -v pwsh > /dev/null 2>&1; then
    pwsh -NonInteractive -WindowStyle Hidden -File "${SCRIPT_DIR}/project-rag-detect.ps1" 2>/dev/null && exit 0
fi
bash "${SCRIPT_DIR}/project-rag-detect.sh"
