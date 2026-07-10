#!/usr/bin/env bash
# lint-frontmatter.sh — thin wrapper that delegates to the Node CLI.
# Spec backlink: archive/specs/2026-05-01-portable-ideas-from-obsidian-research.md §W1
node "$(dirname "$0")/lint-frontmatter.js" "$@" # verify-no-console-flash: allow — on-demand linting utility, not session-hot-path
