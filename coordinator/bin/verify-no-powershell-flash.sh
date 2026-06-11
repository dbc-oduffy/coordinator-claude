#!/bin/bash
# verify-no-powershell-flash.sh — thin shim; canonical guard is now verify-no-console-flash.sh.
#
# This script is preserved so existing callers by the old name continue to work.
# The guard logic was generalised to cover python/node/variable-interpreter and
# heredoc spawn shapes in addition to powershell/pwsh.
#
# Spec backlink: docs/plans/2026-05-29-windows-console-flash-elimination.md § Chunk 3
#
# Do NOT add logic here — edit bin/verify-no-console-flash.sh instead.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/verify-no-console-flash.sh" "$@"
