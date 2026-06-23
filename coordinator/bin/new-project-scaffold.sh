#!/usr/bin/env bash
# bin/new-project-scaffold.sh — deterministic greenfield-scaffold helper for the
# coordinator:new-project skill.
#
# Purpose: create a new project directory, initialise a git repo with branch `main`,
# optionally render a template tree (via render-template-tree.sh), then write minimal
# seed files that downstream repo-setup can consume without interactive prompts.
#
# Parent-dir resolution order (build-for-someone-else's-machine):
#   1. Explicit --parent flag
#   2. COORDINATOR_PROJECTS_ROOT environment variable
#   3. Default $HOME/Code_Projects
#
# This script DOES NOT invoke scaffold-canonical-structure.sh, coordinator-ensure-post-
# commit-hook, coordinator-currency, or coordinator-configure-git. Coordinator onboarding
# is the coordinator:new-project SKILL's responsibility (via repo-setup delegation), not
# this helper's. This boundary is intentional — keep scaffold atomically composable.
#
# Spec backlink: docs/plans/2026-06-22-new-project-bootstrap-skill.md § C3
#
# Usage:
#   new-project-scaffold.sh --name <name> [--parent <dir>] [--template next-app|empty] [--no-smoke]
#
# Arguments:
#   --name <name>         Required. Project name (also the new directory name).
#   --parent <dir>        Parent directory; defaults per resolution order above.
#   --template <t>        Template to render: next-app (default) or empty.
#   --no-smoke            Skip pnpm install/typecheck/test (required for offline/test use).
#
# Exit codes:
#   0  Scaffold created successfully.
#   1  Pre-flight failure (occupied dir, bad args) or smoke failure.

set -euo pipefail

# ---------------------------------------------------------------------------
# DR-148 bash-version guard — must parse on bash 3.2
# ---------------------------------------------------------------------------
if (( BASH_VERSINFO[0] < 4 )); then
    echo "ERROR: bash >= 4 required; install via brew install bash" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Locate sibling scripts relative to THIS script — not cwd
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RENDER_TREE="${SCRIPT_DIR}/render-template-tree.sh"
TEMPLATE_BASE="${SCRIPT_DIR}/../skills/new-project/templates"

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
PROJECT_NAME=""
PARENT_DIR=""
TEMPLATE="next-app"
NO_SMOKE=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --name)
            PROJECT_NAME="${2:-}"
            if [[ -z "$PROJECT_NAME" ]]; then
                echo "ERROR: --name requires a value" >&2
                exit 1
            fi
            shift 2
            ;;
        --parent)
            PARENT_DIR="${2:-}"
            if [[ -z "$PARENT_DIR" ]]; then
                echo "ERROR: --parent requires a value" >&2
                exit 1
            fi
            shift 2
            ;;
        --template)
            TEMPLATE="${2:-}"
            if [[ -z "$TEMPLATE" ]]; then
                echo "ERROR: --template requires a value" >&2
                exit 1
            fi
            shift 2
            ;;
        --no-smoke)
            NO_SMOKE=1
            shift
            ;;
        *)
            echo "ERROR: unknown argument: $1" >&2
            echo "Usage: new-project-scaffold.sh --name <name> [--parent <dir>] [--template next-app|empty] [--no-smoke]" >&2
            exit 1
            ;;
    esac
done

if [[ -z "$PROJECT_NAME" ]]; then
    echo "ERROR: --name is required" >&2
    echo "Usage: new-project-scaffold.sh --name <name> [--parent <dir>] [--template next-app|empty] [--no-smoke]" >&2
    exit 1
fi

if [[ "$TEMPLATE" != "next-app" && "$TEMPLATE" != "empty" ]]; then
    echo "ERROR: --template must be 'next-app' or 'empty'; got: $TEMPLATE" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Parent-dir resolution: flag > env > default
# ---------------------------------------------------------------------------
if [[ -n "$PARENT_DIR" ]]; then
    : # explicit flag wins
elif [[ -n "${COORDINATOR_PROJECTS_ROOT:-}" ]]; then
    PARENT_DIR="$COORDINATOR_PROJECTS_ROOT"
else
    PARENT_DIR="${HOME}/Code_Projects"
fi

TARGET="${PARENT_DIR}/${PROJECT_NAME}"

# ---------------------------------------------------------------------------
# Pre-flight: fail loud if target is non-empty
# ---------------------------------------------------------------------------
if [[ -d "$TARGET" ]]; then
    if [[ -n "$(ls -A "$TARGET" 2>/dev/null)" ]]; then
        echo "ERROR: target directory already exists and is non-empty: $TARGET" >&2
        echo "Remove or rename the existing directory and retry." >&2
        exit 1
    fi
    # Existing but empty dir is OK — we'll use it as-is
fi

# ---------------------------------------------------------------------------
# Create parent and target directories
# ---------------------------------------------------------------------------
mkdir -p "$TARGET"

# ---------------------------------------------------------------------------
# Git init — pin to branch main (portability)
# ---------------------------------------------------------------------------
# Try git init -b main (git >= 2.28). If the flag is not recognised, fall back
# to bare init + symbolic-ref. This eliminates version-string parsing (awk+cut
# 4-subshell chain) and is robust to non-standard git --version output.
# Review: code-reviewer — F9: try-then-fallback replaces fragile version-parse
if ! git init -b main "$TARGET" --quiet 2>/dev/null; then
    git init "$TARGET" --quiet
    git -C "$TARGET" symbolic-ref HEAD refs/heads/main
fi

# ---------------------------------------------------------------------------
# Template render
# ---------------------------------------------------------------------------
# render-template-tree.sh requires its dst to be absent or empty. Because git
# init has already populated $TARGET/.git, we render into a temp staging dir
# and then copy the rendered contents into $TARGET.
if [[ "$TEMPLATE" == "next-app" ]]; then
    TEMPLATE_SRC="${TEMPLATE_BASE}/next-app"
    if [[ ! -d "$TEMPLATE_SRC" ]]; then
        echo "ERROR: next-app template not found at: $TEMPLATE_SRC" >&2
        exit 1
    fi
    if [[ ! -x "$RENDER_TREE" ]]; then
        echo "ERROR: render-template-tree.sh not found or not executable at: $RENDER_TREE" >&2
        exit 1
    fi
    RENDER_STAGING="$(mktemp -d)"
    trap 'rm -rf "$RENDER_STAGING"' EXIT  # Review: code-reviewer — F8: deferred expansion matches render-template-tree.sh pattern; remove SC2064 disable
    "$RENDER_TREE" "$TEMPLATE_SRC" "$RENDER_STAGING" "PROJECT_NAME=${PROJECT_NAME}"
    # Copy rendered files (including dotfiles) into target alongside .git
    cp -a "${RENDER_STAGING}/." "${TARGET}/"
    rm -rf "$RENDER_STAGING"
    trap - EXIT
fi
# empty template: no source tree to render

# ---------------------------------------------------------------------------
# Seed files (always written, for all templates)
# ---------------------------------------------------------------------------
if [[ "$TEMPLATE" == "next-app" ]]; then
    COORDINATOR_PROJECT_TYPE="web-dev"
else
    COORDINATOR_PROJECT_TYPE="general"
fi

cat > "${TARGET}/coordinator.local.md" <<EOF
---
project_type: ${COORDINATOR_PROJECT_TYPE}
---
EOF

cat > "${TARGET}/README.md" <<EOF
# ${PROJECT_NAME}
EOF

# ---------------------------------------------------------------------------
# Smoke (unless --no-smoke) — for next-app only
# ---------------------------------------------------------------------------
if [[ "$NO_SMOKE" -eq 0 && "$TEMPLATE" == "next-app" ]]; then
    echo "Running smoke checks in ${TARGET}..."
    if ! (cd "$TARGET" && pnpm install); then
        echo "ERROR: pnpm install failed — scaffold is incomplete" >&2
        exit 1
    fi
    if ! (cd "$TARGET" && pnpm typecheck); then
        echo "ERROR: pnpm typecheck failed — scaffold is incomplete" >&2
        exit 1
    fi
    if ! (cd "$TARGET" && pnpm test); then
        echo "ERROR: pnpm test failed — scaffold is incomplete" >&2
        exit 1
    fi
    echo "Smoke checks passed."
fi

echo "Scaffold complete: ${TARGET}"
exit 0
