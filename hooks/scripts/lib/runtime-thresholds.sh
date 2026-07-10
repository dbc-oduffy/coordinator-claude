#!/usr/bin/env bash
# hooks/scripts/lib/runtime-thresholds.sh
#
# Purpose: Shared threshold table for the runtime-tripwire actuator system.
#          Exposes runtime_threshold_minutes(MODEL_ID) — echoes the per-model
#          runtime ceiling (in integer minutes) at which the tripwire hooks
#          should fire a wrap-shape nudge.
#
# Spec backlink: docs/plans/2026-06-08-runtime-tripwire-background-executors.md § C1
# Wiki: docs/wiki/runtime-tripwire.md (written in C5; path is stable)
#
# Defaults
# --------
#   Opus   = 25 min  (RUNTIME_TRIPWIRE_OPUS_MIN)
#   Sonnet = 12 min  (RUNTIME_TRIPWIRE_SONNET_MIN)
#     Sonnet=12 gives a 3-min wrap buffer before the 15-min HARD RULE ceiling
#     (CLAUDE.md § Subagent Dispatch); PM-dispositioned 2026-06-08 (F7 finding).
#   Haiku  = 10 min  (RUNTIME_TRIPWIRE_HAIKU_MIN)
#
# Env-var overrides
# -----------------
#   RUNTIME_TRIPWIRE_OPUS_MIN    — override the Opus/unknown default
#   RUNTIME_TRIPWIRE_SONNET_MIN  — override the Sonnet default
#   RUNTIME_TRIPWIRE_HAIKU_MIN   — override the Haiku default
#
# Unknown / empty model
# ---------------------
#   Returns the Opus default (25 min). Mirrors the compaction-advisory's
#   bias-toward-Opus failure direction — a too-large threshold only delays a
#   nudge (safe), whereas a too-small threshold fires spuriously (noisy).
#   Never silently disables the tripwire.
#
# Portability constraints (HARD)
# ------------------------------
#   Bash 3.2 compatible: no declare -A, no mapfile, no ${v^^}, no local -n.
#   BSD coreutils compatible: no sed -i, no grep -P, no date -d / %N,
#   no realpath / readlink -f.
#   The case statement below meets both requirements.

runtime_threshold_minutes() {
  # Usage: runtime_threshold_minutes "$MODEL_ID"
  # Echoes integer minutes (the runtime tripwire threshold for that model family).
  local model="${1:-}"
  case "$model" in
    # Explicit 1M-context variants — matched before bare family arms.
    # Anthropic encodes 1M variants with a "[1m]" suffix (e.g. "claude-opus-4-7[1m]")
    # or a "-1m" infix. Must precede *opus* / *sonnet* / *haiku* to avoid
    # mis-classifying a 1M-context Sonnet as a plain Sonnet.
    # NB: no bare *1m* arm — it would false-match a date/version token.
    *\[1m\]*|*-1m*)  echo "${RUNTIME_TRIPWIRE_OPUS_MIN:-25}" ;;
    # Family fallbacks — survive minor version bumps; pinned arms break.
    *opus*)          echo "${RUNTIME_TRIPWIRE_OPUS_MIN:-25}" ;;
    *sonnet*)        echo "${RUNTIME_TRIPWIRE_SONNET_MIN:-12}" ;;
    *haiku*)         echo "${RUNTIME_TRIPWIRE_HAIKU_MIN:-10}" ;;
    # Unknown model OR empty MODEL_ID: return Opus default.
    # This arm is also the error-recovery path (grep failure / race).
    # Do NOT disable or short-circuit here — return a threshold and continue.
    *)               echo "${RUNTIME_TRIPWIRE_OPUS_MIN:-25}" ;;
  esac
}
