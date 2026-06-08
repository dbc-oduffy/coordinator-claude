#!/usr/bin/env bash
# lib/oss-repo-constants.sh — Sourceable constants for coordinator OSS publish repos.
#
# Purpose: single source of truth for the coordinator-claude canonical publish URL
# and owner/repo identifiers. Sourced by any script that needs the coordinator
# publish URL — prevents inline duplication and per-script drift.
#
# Spec backlink: docs/plans/2026-06-01-boot-currency-notification-hook.md § C2
#
# Usage (in any script):
#   source "$(dirname "${BASH_SOURCE[0]}")/../lib/oss-repo-constants.sh"
#   # or with a resolved absolute path — adjust the relative step count as needed.
#
# Negative-spec:
#   - deep-research-claude URL is NOT defined here — it belongs to the spinoff
#     (state/handoffs/2026-06-01_122922_deep-research-currency-notification.md).
#   - This file is SOURCED ONLY — it must not produce any output or side-effects.
#   - No `set -euo pipefail` at file scope — this is a sourced constants file.

# Coordinator-claude publish repo constants.
COORDINATOR_PUBLISH_OWNER="dbc-oduffy"
COORDINATOR_PUBLISH_REPO="coordinator-claude"
COORDINATOR_PUBLISH_URL="https://github.com/${COORDINATOR_PUBLISH_OWNER}/${COORDINATOR_PUBLISH_REPO}.git"
