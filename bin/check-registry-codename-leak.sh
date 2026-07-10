#!/usr/bin/env bash
# check-registry-codename-leak.sh — registry-derived novel-leak guard.
#
# Greps <target-dir> for any private-repo codename derived from the machine-local
# registry's repos.* keys, after subtracting the D1 keep-set. Exits non-zero with
# a file:line report if any codename is found; exits 0 if the tree is clean.
#
# Usage: check-registry-codename-leak.sh <target-dir>
#
# Exit codes:
#   0 — clean (no private codenames found)
#   1 — leak found (file:line report written to stderr)
#   2 — usage error
#
# Testability override: if COORDINATOR_CODENAME_REGISTRY_KEYS is set (space- or
# newline-separated list of repos.* keys, e.g.
# "repos.example_cockpit_repo repos.project_rag"), those keys are used instead of
# calling machine-local. This allows fixture tests to inject a synthetic registry
# without a live machine-local installation.
#
# D1 keep-set (prefix-matched against the slug after stripping repos.):
#   project_rag, deep_research, game_dev, web_dev, data_science, coordinator
# These are load-bearing system vocabulary (MCP namespaces, shipped plugin names,
# registry keys) that must NOT be flagged as leaks — see Decision D1 in
# docs/plans/2026-06-27-genericize-provenance-sweeper.md.
# 'coordinator' also keeps 'coordinator_claude'; 'deep_research' also keeps
# 'deep_research_claude'; 'project_rag' also keeps 'project_rag_ue_addon'.
#
# Grep strategy: for each registry slug in scope, derive BOTH the underscore form
# (as-is) AND the hyphen form (replace _ with -) and grep both. Registry keys use
# underscores (example_cockpit_repo) but prose codenames use hyphens (example-cockpit-repo);
# grepping only the underscore form silently misses the exact leak class this guard
# exists to catch.
#
# Spec backlink: docs/plans/2026-06-27-genericize-provenance-sweeper.md § C4 / AC11

# Bash 4+ guard — must be parseable by bash 3.2 (macOS default), so no
# bash-4-only syntax before this check.
if (( BASH_VERSINFO[0] < 4 )); then
  echo "ERROR: check-registry-codename-leak.sh requires bash 4.0 or later." >&2
  echo "       Detected: bash ${BASH_VERSION:-unknown}" >&2
  echo "  macOS ships bash 3.2 as /bin/bash. Install a current bash and put it first on PATH:" >&2
  echo "      brew install bash" >&2
  echo '      export PATH="$(brew --prefix)/bin:$PATH"   # add to ~/.zshrc or ~/.bashrc' >&2
  exit 2
fi

set -euo pipefail

# D1 keep-set — prefix-matched against slug (strip repos. prefix first).
# 'coordinator' matches 'coordinator_claude'; 'deep_research' matches
# 'deep_research_claude'; 'project_rag' matches 'project_rag_ue_addon'.
# 'doe_claude' kept: OSS resolve-coordinator-clone.sh reads repos.doe_claude at runtime (PM-ratified 2026-07-10).
readonly KEEPSET=( project_rag deep_research game_dev web_dev data_science coordinator experiments doe_claude )

usage() {
  echo "Usage: check-registry-codename-leak.sh <target-dir>" >&2
  echo "  Greps target-dir for private-repo codenames from the machine-local registry." >&2
  echo "  Set COORDINATOR_CODENAME_REGISTRY_KEYS to inject a synthetic key list (testing)." >&2
  exit 2
}

if [[ $# -ne 1 ]]; then
  usage
fi

target_dir="$1"

if [[ ! -d "$target_dir" ]]; then
  echo "check-registry-codename-leak.sh: target-dir not found: $target_dir" >&2
  exit 2
fi

# --- Resolve registry keys ---
# Use COORDINATOR_CODENAME_REGISTRY_KEYS if set (testability override);
# else call machine-local (on PATH or at canonical default).
registry_keys=()

if [[ -n "${COORDINATOR_CODENAME_REGISTRY_KEYS:-}" ]]; then
  # Convert spaces/tabs to newlines, read each non-empty token.
  while IFS= read -r _key; do
    _key="${_key#"${_key%%[![:space:]]*}"}"  # ltrim
    _key="${_key%"${_key##*[![:space:]]}"}"  # rtrim
    [[ -n "$_key" ]] && registry_keys+=( "$_key" )
  done < <(printf '%s\n' "$COORDINATOR_CODENAME_REGISTRY_KEYS" | tr ' \t' '\n')
else
  _ml_bin=""
  if command -v machine-local >/dev/null 2>&1; then
    _ml_bin="machine-local"
  elif [[ -x "$HOME/.claude/bin/machine-local" ]]; then
    _ml_bin="$HOME/.claude/bin/machine-local"
  fi

  if [[ -n "$_ml_bin" ]]; then
    while IFS= read -r _key; do
      [[ -n "$_key" ]] && registry_keys+=( "$_key" )
    done < <("$_ml_bin" keys 2>/dev/null | grep '^repos\.' || true)
  else
    # Review: code-reviewer (F2) — distinct WARNING so machine-local-absent is distinguishable
    # from a genuinely-empty registry (previously both silently exited 0 with the same message).
    echo "check-registry-codename-leak.sh: WARNING: machine-local not found; registry lookup skipped." >&2
    echo "  Set COORDINATOR_CODENAME_REGISTRY_KEYS to run without machine-local." >&2
  fi
fi

# --- Subtract keep-set: prefix-match slug against KEEPSET ---
is_kept() {
  local slug="$1"
  local entry
  for entry in "${KEEPSET[@]}"; do
    # Exact match OR prefix+underscore match (e.g. 'coordinator' keeps 'coordinator_claude').
    if [[ "$slug" == "$entry" || "$slug" == "${entry}_"* ]]; then
      return 0
    fi
  done
  return 1
}

leak_slugs=()
for key in "${registry_keys[@]}"; do
  # Strip the 'repos.' prefix.
  slug="${key#repos.}"
  if is_kept "$slug"; then
    continue
  fi
  leak_slugs+=( "$slug" )
done

if [[ ${#leak_slugs[@]} -eq 0 ]]; then
  echo "check-registry-codename-leak.sh: no private codenames to check (empty registry or all keys in keep-set)." >&2
  exit 0
fi

# --- Grep both underscore and hyphen forms, case-insensitively ---
# -I skips binary files (BSD grep + GNU grep both support this flag).
found_any=0
all_hits=""

for slug in "${leak_slugs[@]}"; do
  # Derive hyphen form: replace underscores with hyphens.
  hyphen_form="${slug//_/-}"

  # Build unique patterns list (slug as-is AND hyphen form; skip if identical).
  patterns=( "$slug" )
  if [[ "$hyphen_form" != "$slug" ]]; then
    patterns+=( "$hyphen_form" )
  fi

  for pattern in "${patterns[@]}"; do
    # Review: code-reviewer (F1) — `--` terminates option parsing; prevents a `-`-prefixed slug from being read as a grep flag (error was swallowed by `|| true` → false-clean)
    # Exclude transform scratch (*.bak/*.tmp/*.orig): publish-time-transform.sh --fix
    # and the depersonalize hooks write per-file backups whose content is the PRE-rewrite
    # source (codename-bearing by construction). The guard runs in-hook while those
    # transient files still exist, so scanning them produces false positives on the
    # backup of an already-cleaned file. They are never shippable surfaces — the leak
    # check assesses real content only. --exclude is supported by both GNU and BSD grep.
    hits=$(grep -rni -I --exclude='*.bak' --exclude='*.tmp' --exclude='*.orig' -- "$pattern" "$target_dir" 2>/dev/null || true)
    if [[ -n "$hits" ]]; then
      found_any=1
      all_hits="${all_hits}${hits}"$'\n'
    fi
  done
done

if [[ "$found_any" -ne 0 ]]; then
  echo "check-registry-codename-leak.sh: private codename(s) found in publish tree." >&2
  echo "  Add the codename to coordinator/bin/codename-provenance-seed.sh (rewrite) or" >&2
  echo "  extend the D1 keep-set in this script (load-bearing system vocabulary only):" >&2
  echo "$all_hits" >&2
  exit 1
fi

echo "check-registry-codename-leak.sh: clean — no unregistered private codenames found." >&2
exit 0
