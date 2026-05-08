#!/usr/bin/env bash
# project-rag-detect-wrapper.sh — Cross-platform launcher for project-rag-detect.
#
# On Windows (pwsh available): delegates to project-rag-detect.ps1 via pwsh.
# On POSIX-only systems: delegates to project-rag-detect.sh via bash.
#
# This wrapper exists so hooks.json can reference a single file path rather than
# embedding an inline OR-fallback command that confuses path validators.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if command -v pwsh > /dev/null 2>&1; then
    pwsh -NonInteractive -File "${SCRIPT_DIR}/project-rag-detect.ps1" 2>/dev/null
else
    bash "${SCRIPT_DIR}/project-rag-detect.sh"
fi
