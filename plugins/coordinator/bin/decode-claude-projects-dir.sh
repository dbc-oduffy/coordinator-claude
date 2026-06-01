#!/usr/bin/env bash
# decode-claude-projects-dir.sh — decode ~/.claude/projects/ encoded dir names to repo-shortname candidates
#
# Claude Code encodes invocation cwds into ~/.claude/projects/ subdir names by replacing path separators
# with `-` (single dash for dir separator, doubled for drive `:`). Encoding has varied across versions, so
# this decoder is heuristic — it surfaces candidates for PM review, not authoritative paths.
#
# Output: tab-separated `shortname<TAB>candidate-path<TAB>encoded-dir-name`, deduped on shortname.
# Empty/garbled entries (e.g., `tmp`, `--Users--<user>--.claude`) are dropped.
#
# Used by /update-docs Phase 14 to seed the candidates block in ~/.claude/tasks/repo-registry.md.

set -euo pipefail

if (( BASH_VERSINFO[0] < 4 )); then
    echo "ERROR: decode-claude-projects-dir.sh requires bash 4.0 or later (associative arrays)." >&2
    echo "       Detected: bash ${BASH_VERSION:-unknown}" >&2
    echo "  macOS ships bash 3.2 as /bin/bash. Install a current bash and put it first on PATH:" >&2
    echo "      brew install bash" >&2
    echo '      export PATH="$(brew --prefix)/bin:$PATH"   # add to ~/.zshrc or ~/.bashrc' >&2
    exit 1
fi

PROJECTS_DIR="${1:-${HOME}/.claude/projects}"

if [[ ! -d "${PROJECTS_DIR}" ]]; then
  echo "decode-claude-projects-dir.sh: projects dir not found: ${PROJECTS_DIR}" >&2
  exit 1
fi

declare -A seen

# Pattern observed in projects dir:
#   X---repo-name             → X:/repo-name
#   X--repo-name              → X:/repo-name (alt encoding)
#   X---repo-name--tasks--... → X:/repo-name (subdir suffix; strip after first `--<known-subdir>--`)
#   C---Users--<user>---claude → C:/Users/<user>/.claude
#
# Strategy: strip known subdir suffixes (tasks, plugins, control, docs); take the segment immediately
# after the drive prefix as the shortname. Filter out clearly-garbled entries.

KNOWN_SUFFIX_MARKERS=("--tasks--" "--plugins--" "--control--" "--docs--" "--scratch--")

for entry in "${PROJECTS_DIR}"/*/; do
  [[ -d "${entry}" ]] || continue
  name="$(basename "${entry}")"

  # Skip obvious non-repo entries
  case "${name}" in
    tmp|tmp-*|*-smoketest|""|.|..) continue ;;
    "--Users"*|"AppData-Local-Temp"*) continue ;;  # garbled or temp
    *AppData*) continue ;;
  esac

  # Strip any known-subdir suffix to get the repo-root encoding
  repo_part="${name}"
  for marker in "${KNOWN_SUFFIX_MARKERS[@]}"; do
    if [[ "${repo_part}" == *"${marker}"* ]]; then
      repo_part="${repo_part%%${marker}*}"
    fi
  done

  # Decode drive prefix: leading `X---` or `X--` → `X:/`
  if [[ "${repo_part}" =~ ^([A-Za-z])---(.+)$ ]]; then
    drive="${BASH_REMATCH[1]}"
    rest="${BASH_REMATCH[2]}"
  elif [[ "${repo_part}" =~ ^([A-Za-z])--(.+)$ ]]; then
    drive="${BASH_REMATCH[1]}"
    rest="${BASH_REMATCH[2]}"
  else
    continue  # no recognizable drive prefix
  fi

  # Skip if rest is empty or just dashes
  [[ -n "${rest}" && "${rest}" != "-" ]] || continue

  # Take first path-segment as shortname. The encoding uses `--` as path separator
  # and single `-` as part of names, so we split on `--`, NOT single `-`.
  shortname="${rest%%--*}"

  # Skip empty shortnames or single-letter
  [[ ${#shortname} -ge 2 ]] || continue

  # Build candidate path: lowercase drive + shortname (Windows convention)
  drive_lower="$(echo "${drive}" | tr '[:upper:]' '[:lower:]')"
  candidate_path="${drive_lower}:/${shortname}"

  # Special case: claude-central appears as C---Users--<user>---claude OR C--Users-<user>--claude
  # Extract the username from whichever encoding form is present.
  if [[ "${shortname}" == "Users" && "${rest}" =~ ^Users--([^-]+)---claude ]] && [[ "${rest}" == *"claude"* ]]; then
    username="${BASH_REMATCH[1]}"
    candidate_path="${drive_lower}:/Users/${username}/.claude"
    shortname="claude-central"
  elif [[ "${shortname}" =~ ^Users-([^-]+)$ ]] && [[ "${rest}" == *"claude"* ]]; then
    username="${BASH_REMATCH[1]}"
    candidate_path="${drive_lower}:/Users/${username}/.claude"
    shortname="claude-central"
  fi

  # Suffix collapse: drop `<name>-tasks` / `<name>-docs` if the base `<name>` is already seen.
  # These typically come from Claude Code being invoked inside a tasks/ or docs/ subdir.
  if [[ "${shortname}" == *-tasks || "${shortname}" == *-docs ]]; then
    base="${shortname%-tasks}"
    base="${base%-docs}"
    if [[ -n "${seen[${base}]:-}" ]]; then
      continue
    fi
  fi

  # Dedupe on shortname (first encoding wins)
  if [[ -z "${seen[${shortname}]:-}" ]]; then
    seen[${shortname}]=1
    printf "%s\t%s\t%s\n" "${shortname}" "${candidate_path}" "${name}"
  fi
done

# Smoke-test footer (printed to stderr): assert >0 candidates emitted
count="${#seen[@]}"
if [[ "${count}" -eq 0 ]]; then
  echo "decode-claude-projects-dir.sh: WARNING — zero candidates decoded from ${PROJECTS_DIR}" >&2
  exit 2
fi
echo "decode-claude-projects-dir.sh: ${count} candidate(s) emitted" >&2
