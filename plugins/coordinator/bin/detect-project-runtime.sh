#!/usr/bin/env bash
# detect-project-runtime.sh — Advisory runtime/operational marker scan for
#                              repo-setup Phase 1 context.
#
# Spec backlink: archive/specs/2026-05-06-detect-project-runtime.md
#
# Purpose: Surface what runtime/operational invariants the filesystem of $PWD
# reveals (lockfile → package manager, compose file → Docker, CI dir → CI vendor,
# Infisical refs → no .env). Output is stdout-only ADVISORY context for the PM
# answering repo-setup Phase 2 question 2 — never authoritative.
#
# Output: a one-line summary header + indented bullets per detected stack +
# fixed Notes footer. Exit 0 even when no markers fire.
#
# Cross-platform: pure bash + coreutils. Works on Git Bash MINGW64 (Windows)
# and Linux GNU. Uses `git ls-files` only inside a git repo; falls back to
# filesystem-presence-only when not in a git repo.
#
# Negative-spec: does NOT write files, set env vars, mutate the working tree,
# call external services, or emit structured artifacts (no YAML, no JSON, no
# CONTEXT.md, no sidecar). NO skill, agent, or hook reads this output
# programmatically. Adding a consumer requires a separate plan.

set -euo pipefail

# ---------------------------------------------------------------------------
# Marker detection helpers (each appends to STACK_LINES on hit)
# ---------------------------------------------------------------------------

STACK_LINES=()

# --- Node ----------------------------------------------------------------
if [[ -f package.json ]]; then
  managers=()
  [[ -f bun.lockb ]] && managers+=("bun")
  [[ -f pnpm-lock.yaml ]] && managers+=("pnpm")
  [[ -f yarn.lock ]] && managers+=("yarn")
  [[ -f package-lock.json ]] && managers+=("npm")
  if (( ${#managers[@]} == 0 )); then
    STACK_LINES+=("Node (no lockfile detected)")
  elif (( ${#managers[@]} == 1 )); then
    STACK_LINES+=("Node (${managers[0]})")
  else
    # Multiple lockfiles — monorepo or migration-in-progress signal.
    IFS=,; STACK_LINES+=("Node (multiple lockfiles: ${managers[*]})"); unset IFS
  fi
fi

# --- Python --------------------------------------------------------------
if [[ -f pyproject.toml ]]; then
  STACK_LINES+=("Python (pyproject.toml — poetry/pdm/uv/pip)")
elif compgen -G "requirements*.txt" > /dev/null; then
  STACK_LINES+=("Python (requirements.txt — pip)")
fi

# --- Rust ----------------------------------------------------------------
[[ -f Cargo.toml ]] && STACK_LINES+=("Rust (cargo)")

# --- Go ------------------------------------------------------------------
[[ -f go.mod ]] && STACK_LINES+=("Go (modules)")

# --- Ruby ----------------------------------------------------------------
[[ -f Gemfile ]] && STACK_LINES+=("Ruby (bundler)")

# --- Containers ----------------------------------------------------------
[[ -f Dockerfile ]] && STACK_LINES+=("Docker (image build)")
if [[ -f docker-compose.yml || -f docker-compose.yaml || -f compose.yml || -f compose.yaml ]]; then
  STACK_LINES+=("Docker Compose (multi-service)")
fi

# --- CI ------------------------------------------------------------------
if [[ -d .github/workflows ]] && compgen -G ".github/workflows/*.y*ml" > /dev/null; then
  STACK_LINES+=("GitHub Actions CI")
fi
[[ -f .gitlab-ci.yml ]] && STACK_LINES+=("GitLab CI")

# --- Build entry ---------------------------------------------------------
[[ -f Makefile ]] && STACK_LINES+=("Make (build entry)")

# --- Secrets (layered detection per plan F5) -----------------------------
infisical_present=0
[[ -f infisical.json || -f .infisical.json ]] && infisical_present=1
env_example_present=0
[[ -f .env.example ]] && env_example_present=1

# Check tracked .env files only when inside a git repo
env_tracked=1  # default to "unknown / treat as present" for non-git contexts
if git rev-parse --is-inside-work-tree > /dev/null 2>&1; then
  if git ls-files 2>/dev/null | grep -E '^\.env$|^\.env\.' > /dev/null; then
    env_tracked=1
  else
    env_tracked=0
  fi
fi

if (( infisical_present )) && (( env_tracked == 0 )); then
  STACK_LINES+=("Secrets: Infisical (no .env files tracked)")
fi
if (( env_example_present )) && (( ! infisical_present || env_tracked == 1 )); then
  STACK_LINES+=("Secrets: .env (template only — .env.example present)")
fi
if (( infisical_present )) && (( env_example_present )) && (( env_tracked == 0 )); then
  # Both signals present — list both per plan ("list both if both conditions met")
  STACK_LINES+=("Secrets: .env.example also present (legacy template)")
fi

# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

CWD_BASE="$(basename "$PWD")"

if (( ${#STACK_LINES[@]} == 0 )); then
  echo "Detected: no known stack markers (script saw $PWD)."
  exit 0
fi

echo "Detected runtime profile for ${CWD_BASE}:"
for line in "${STACK_LINES[@]}"; do
  echo "  - ${line}"
done
echo ""
echo "Notes:"
echo "  - This is advisory context for repo-setup. Confirm with the PM before relying on it."
exit 0
