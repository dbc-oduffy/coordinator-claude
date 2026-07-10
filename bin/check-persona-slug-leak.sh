#!/usr/bin/env bash
# check-persona-slug-leak.sh — lowercase/compound persona-slug leak guard.
#
# Sibling to check-registry-codename-leak.sh (registry-derived codenames) but for the
# static PERSONA vocabulary (Patrik, Fru, Palí, Sid, Zolí, Camelia, YK). The
# publish-time-transform.sh NAME_TO_ROLE table historically covered TitleCase/diacritic
# prose forms only (case-sensitive, \b-bounded) — lowercase slugs (patrik, fru, pali,
# zoli, camelia, yk) and compound glued forms (FruFinding) slipped through: \b does not
# fire between two word characters ("Fru"+"Finding" glued with no separator), and the
# table was case-sensitive TitleCase-only so bare lowercase slugs never matched at all.
# This guard scans <target-dir> for residual lowercase/compound persona-slug hits so a
# scratch publish tree can be verified clean after a publish-time-transform.sh --fix pass.
#
# 'sid' is DELIBERATELY EXCLUDED from PERSONA_SLUGS below — 'sid' is a pervasively-used
# abbreviation for "session_id" throughout the coordinator shell/JS surface (`local sid=`,
# `--sid` CLI flags, `<sid>` placeholders, `em_sid`, `stub_sid`, `my_sid`, hundreds of
# occurrences). A blanket lowercase 'sid' scan would produce mass false positives
# unrelated to the Sid persona. See publish-time-transform.sh's NAME_TO_ROLE comment for
# the matching holding decision — this guard and that transform must stay in lockstep.
#
# FUNCTIONAL-HOLD: this guard does NOT flag known functional/parsed persona-slug
# occurrences — JSON schema `reviewer` enum entries (bare-array-item lines and inline
# `"enum": [...]` declarations), `"reviewer": "<slug>"` / `reviewer: '<slug>'` field
# values (JSON and bareword-key JS object-literal forms), and JSON/JS object-key
# literals like `"patrik": patrik_shas`. These are load-bearing runtime identifiers
# (schemas/review.schema.json, artifact-shape-contract.schema.json, the 6 agent-def
# `"reviewer"` JSON examples, lib/workweek-trail-scope.sh) whose consistent rewrite
# requires touching every consumer — out of scope for a mechanical transform pass, so
# they are intentionally held for hand/EM review rather than blanket-rewritten. The
# is_held_line() patterns below MUST mirror publish-time-transform.sh's
# DEPERSONALIZE_PROTECT perl guard exactly (five shapes, one-to-one).
#
# Usage: check-persona-slug-leak.sh <target-dir>
#
# Exit codes:
#   0 — clean (no unheld lowercase/compound persona-slug hits)
#   1 — leak found (file:line report written to stderr)
#   2 — usage error
#
# Spec backlink: chunk C8, publish-time persona-slug hardening (2026-07-09).

# Bash 4+ guard — must be parseable by bash 3.2 (macOS default), so no
# bash-4-only syntax before this check.
if (( BASH_VERSINFO[0] < 4 )); then
  echo "ERROR: check-persona-slug-leak.sh requires bash 4.0 or later." >&2
  echo "       Detected: bash ${BASH_VERSION:-unknown}" >&2
  echo "  macOS ships bash 3.2 as /bin/bash. Install a current bash and put it first on PATH:" >&2
  echo "      brew install bash" >&2
  echo '      export PATH="$(brew --prefix)/bin:$PATH"   # add to ~/.zshrc or ~/.bashrc' >&2
  exit 2
fi

set -euo pipefail

usage() {
  echo "Usage: check-persona-slug-leak.sh <target-dir>" >&2
  echo "  Scans target-dir for lowercase/compound persona-slug hits (patrik, fru, pali," >&2
  echo "  zoli, camelia, yk — 'sid' excluded, see header). Known functional/parsed" >&2
  echo "  occurrences (schema reviewer enums, field values, object keys) are held, not" >&2
  echo "  flagged. Exits 1 on any unheld hit." >&2
  exit 2
}

if [[ $# -ne 1 ]]; then
  usage
fi

target_dir="$1"

if [[ ! -d "$target_dir" ]]; then
  echo "check-persona-slug-leak.sh: target-dir not found: $target_dir" >&2
  exit 2
fi

readonly EXCLUDED_PREFIXES=(
  "archive/" "tasks/" "experiments/" "evals/"
  "docs/plans/" "docs/research/" "docs/decisions/" "docs/specs/"
)

# 'sid' intentionally absent — see header.
readonly PERSONA_SLUGS=( patrik fru pali zoli camelia yk )

# Known CamelCase-glued compound literals (no boundary, exact-string match only).
# Extend as new compounds are discovered — do not attempt a general prefix regex
# (same D5 discipline as codename-provenance-seed.sh).
readonly COMPOUND_SLUGS=( FruFinding )

# Self-protection basenames — mirrors publish-time-transform.sh's EXCLUDED_BASENAMES /
# is_excluded() vocabulary-file skip. The vocabulary tables (this script's PERSONA_SLUGS/
# COMPOUND_SLUGS, the transform's NAME_TO_ROLE) legitimately contain the literal slug
# strings by definition — flagging the definition file itself as a "leak" is a false
# positive, not a real hit.
readonly EXCLUDED_BASENAMES=( "publish-time-transform.sh" "check-persona-names.py" )

is_excluded_path() {
  local rel="$1" pfx base
  base="$(basename "$rel")"
  for b in "${EXCLUDED_BASENAMES[@]}"; do
    [[ "$base" == "$b" ]] && return 0
  done
  case "$base" in *check-persona*|*depersonalize*|*codename-provenance*) return 0 ;; esac
  for pfx in "${EXCLUDED_PREFIXES[@]}"; do
    if [[ "$rel" == "$pfx"* ]]; then return 0; fi
  done
  return 1
}

# Functional-hold line patterns — MUST mirror publish-time-transform.sh's
# DEPERSONALIZE_PROTECT perl guard exactly (five shapes, one-to-one).
is_held_line() {
  local line="$1"
  if [[ "$line" =~ ^[[:space:]]*\"(patrik|fru|pali|zoli|camelia|yk)\",?[[:space:]]*$ ]]; then return 0; fi
  if [[ "$line" =~ \"enum\":[[:space:]]*\[.*\"(patrik|fru|pali|zoli|camelia|yk)\".*\] ]]; then return 0; fi
  if [[ "$line" =~ reviewer[\"\']?:[[:space:]]*[\"\'](patrik|fru|pali|zoli|camelia|yk)[\"\'] ]]; then return 0; fi
  if [[ "$line" =~ [\"\'](patrik|fru|pali|zoli|camelia|yk)[\"\']: ]]; then return 0; fi
  if [[ "$line" =~ \"description\":.*\(e\.g\..*(patrik|fru|pali|zoli|camelia|yk) ]]; then return 0; fi
  return 1
}

found_any=0
report=""

declare -a CANDIDATE_FILES=()
while IFS= read -r -d '' f; do
  rel="${f#"$target_dir"/}"
  if is_excluded_path "$rel"; then continue; fi
  CANDIDATE_FILES+=("$f")
done < <(find "$target_dir" -type f \( -name '*.md' -o -name '*.sh' -o -name '*.py' -o -name '*.json' -o -name '*.ts' -o -name '*.toml' -o -name '*.js' -o -name '*.mjs' \) -print0)

# --- Bounded lowercase slugs ---
slug_alt=$(IFS='|'; echo "${PERSONA_SLUGS[*]}")
for f in "${CANDIDATE_FILES[@]}"; do
  hits=$(grep -nE "(^|[^A-Za-z0-9_])(${slug_alt})([^A-Za-z0-9_]|\$)" "$f" 2>/dev/null || true)
  [[ -z "$hits" ]] && continue
  while IFS= read -r hit; do
    [[ -z "$hit" ]] && continue
    linetext="${hit#*:}"
    if is_held_line "$linetext"; then continue; fi
    found_any=1
    report="${report}${f}:${hit}"$'\n'
  done <<< "$hits"
done

# --- Compound glued slugs (no boundary requirement — exact literal match) ---
for compound in "${COMPOUND_SLUGS[@]}"; do
  for f in "${CANDIDATE_FILES[@]}"; do
    hits=$(grep -nF -- "$compound" "$f" 2>/dev/null || true)
    if [[ -n "$hits" ]]; then
      found_any=1
      report="${report}${f}:${hits}"$'\n'
    fi
  done
done

if [[ "$found_any" -ne 0 ]]; then
  echo "check-persona-slug-leak.sh: lowercase/compound persona-slug hit(s) found." >&2
  echo "  Fix via: coordinator/bin/publish-time-transform.sh --fix <target-dir>" >&2
  echo "  (held functional occurrences are excluded automatically — see script header)." >&2
  printf '%s' "$report" >&2
  exit 1
fi

echo "check-persona-slug-leak.sh: clean — no unheld lowercase/compound persona-slug hits found." >&2
exit 0
